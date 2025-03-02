import concurrent.futures
import cv2
import math
import numpy as np
import os
import re
import subprocess
import time
from datetime import datetime
from scipy.interpolate import CubicSpline
from typing import List, Tuple

from datamodel import FadeParams

MIN_SEG_DIST = 6  # 6 if resolution >= 5760x1080px


class ImageHelper:
    @staticmethod
    def calculate_brightness(filepath: str, gamma_val: float = 2.0) -> int:
        img = cv2.imread(filepath)
        if img is None:
            return 0
        br = round(np.mean(img))
        eff = (br / 255.0) ** gamma_val * 255
        return int(eff)


class FadingLogic:
    @staticmethod
    def parse_utc_offset(filepath: str) -> float:
        # Extract the base file name from the given filepath
        base = os.path.basename(filepath)
        # Try to match the UTC pattern in the file name
        m = re.match(r"^(UTC[+-]\d+(?:\.\d+)?).*", base, re.IGNORECASE)
        if m:
            s2 = re.match(r"UTC([+-]\d+(?:\.\d+)?).*", m.group(1), re.IGNORECASE)
            if s2:
                try:
                    return float(s2.group(1))
                except:
                    pass
        # If no UTC pattern is found, attempt to extract the value up to the first underscore
        underscore_index = base.find("_")
        if underscore_index != -1:
            value_str = base[:underscore_index]
            try:
                return float(value_str)
            except:
                pass
        # Return a default value if no valid pattern is found
        return 9999

    @staticmethod
    def fallback_for_offset(
        i: int, offset: float, subfolder_names: list, subfolder_data: dict
    ) -> Tuple[str, bool]:
        if i == 0:
            for k in range(1, len(subfolder_names)):
                om = subfolder_data[subfolder_names[k]]
                if offset in om:
                    return om[offset][0], True
            return FadingLogic.create_black_dummy(offset), True
        if i == len(subfolder_names) - 1:
            for k in range(len(subfolder_names) - 2, -1, -1):
                om = subfolder_data[subfolder_names[k]]
                if offset in om:
                    return om[offset][0], True
            return FadingLogic.create_black_dummy(offset), True

        for k in range(i + 1, len(subfolder_names)):
            om = subfolder_data[subfolder_names[k]]
            if offset in om:
                return om[offset][0], True
        for k in range(i - 1, -1, -1):
            om = subfolder_data[subfolder_names[k]]
            if offset in om:
                return om[offset][0], True
        return FadingLogic.create_black_dummy(offset), True

    @staticmethod
    def create_black_dummy(offset: float) -> str:
        if not os.path.exists("temp"):
            os.makedirs("temp")
        sign = "+" if offset >= 0 else ""
        fname = f"UTC{sign}{offset}_dummy.png"
        path = os.path.join("temp", fname)
        dummy = np.zeros((10, 10, 3), dtype=np.uint8)
        cv2.imwrite(path, dummy)
        return path

    @staticmethod
    def calculate_horizontal_average(image: np.ndarray) -> np.ndarray:
        return np.mean(image, axis=1).astype(np.uint8)

    @staticmethod
    def build_horizontal_fade(
        active_paths: list[str],
        brightness_list: list[int],
        proxy_list: list[bool],
        fade_params: FadeParams,
    ):
        """
        Builds a horizontal fade based on either a Exponential weighting or a Parabola weighting.
        If weighting == 'Exponential', weights = (brightness/255)^influence.
        If weighting == 'Parabola', weights = [1 - ((b-midpoint)/midpoint)^2]^influence.
        Then damping is applied, and segments are built.

        Returns:
          (final_img, boundaries, filenames, loaded_colors)
        """

        if len(active_paths) < 2:
            return None

        w_total = fade_params.width
        h_total = fade_params.height
        influence_val = fade_params.influence
        damping_val = fade_params.damping
        gamma_val = fade_params.gamma
        midpoint_val = fade_params.midpoint
        weighting = getattr(fade_params, "weighting", "Parabola")  # default if missing

        final_img = np.zeros((h_total, w_total, 3), dtype=np.uint8)
        boundaries = []
        fnames = []
        n = len(active_paths)

        # load row-average
        loaded_colors = []
        for i, p in enumerate(active_paths):
            img = cv2.imread(p)
            if img is None:
                # fallback
                dummy = np.zeros((10, 10, 3), dtype=np.uint8)
                ratio = float(h_total) / 10.0
                new_w = max(1, int(10 * ratio))
                rz = cv2.resize(dummy, (new_w, h_total))
                avg = np.mean(rz, axis=1).astype(np.uint8)
            else:
                ratio = float(h_total) / float(img.shape[0])
                new_w = max(1, int(img.shape[1] * ratio))
                rz = cv2.resize(img, (new_w, h_total))
                avg = np.mean(rz, axis=1).astype(np.uint8)
            loaded_colors.append(avg)

        transitions = []
        original = []
        for i in range(n - 1):
            ab = (brightness_list[i] + brightness_list[i + 1]) * 0.5
            if ab < 0:
                ab = 0
            if ab > 255:
                ab = 255

            if weighting == "Exponential":
                # exponential => wraw = (ab/255)
                w_lin = ab / 255.0
                if w_lin < 0:
                    w_lin = 0
                if w_lin > 1:
                    w_lin = 1
                if influence_val != 0:
                    wgt_final = w_lin**influence_val
                else:
                    wgt_final = w_lin
            else:
                # square parabola => w_parab = 1 - ((ab-mid)/mid)^2
                norm = (ab - midpoint_val) / float(midpoint_val)
                wraw = 1.0 - (norm * norm)
                if wraw < 0:
                    wraw = 0
                if influence_val != 0:
                    wgt_final = wraw**influence_val
                else:
                    wgt_final = wraw

            transitions.append(wgt_final)
            original.append(1.0)

        sum_w = sum(transitions)
        if sum_w <= 0:
            return None
        sum_o = sum(original)

        segw_float = []
        for i in range(n - 1):
            w_i = transitions[i]
            frac_inf = w_i / sum_w
            frac_ori = original[i] / sum_o
            infl_w = w_total * frac_inf
            orig_w = w_total * frac_ori
            diff = infl_w - orig_w
            max_shift = orig_w * (damping_val / 100.0)
            if abs(diff) > max_shift:
                if diff > 0:
                    infl_w = orig_w + max_shift
                else:
                    infl_w = orig_w - max_shift
            segw_float.append(infl_w)

        # distribute
        seg_int = FadingLogic.distribute_segment_widths(segw_float, w_total)

        x_start = 0
        for i in range(n - 1):
            seg_pix = seg_int[i]
            fname = os.path.basename(active_paths[i])
            is_proxy = proxy_list[i]

            if seg_pix <= 0:
                boundaries.append(x_start)
                fnames.append((fname, is_proxy))
                continue

            leftC = loaded_colors[i]
            rightC = loaded_colors[i + 1]
            x_end = x_start + seg_pix
            if x_end > w_total:
                x_end = w_total
            seg_w = x_end - x_start
            if seg_w < 1:
                boundaries.append(x_start)
                fnames.append((fname, is_proxy))
                continue

            xi = np.linspace(0.0, 1.0, seg_w, dtype=np.float32).reshape(1, seg_w, 1)
            leftC_resh = leftC.reshape(h_total, 1, 3)
            rightC_resh = rightC.reshape(h_total, 1, 3)
            grad = (1.0 - xi) * leftC_resh + xi * rightC_resh
            grad = grad.astype(np.uint8)

            from fading import MIN_SEG_DIST

            if seg_w < MIN_SEG_DIST:
                # fill with average
                avg_neighbor = 0.5 * leftC_resh + 0.5 * rightC_resh
                avg_neighbor = avg_neighbor.astype(np.uint8)
                grad = np.repeat(avg_neighbor, seg_w, axis=1)

            final_img[:, x_start : x_start + seg_w] = grad

            boundaries.append(x_start)
            fnames.append((fname, is_proxy))
            x_start = x_end

        lastn = os.path.basename(active_paths[-1])
        lastpx = proxy_list[-1]
        boundaries.append(w_total - 1)
        fnames.append((lastn, lastpx))

        return (final_img, boundaries, fnames, loaded_colors)

    @staticmethod
    def distribute_segment_widths(w_list: list[float], width_total: int) -> list[int]:
        """
        Converts float segment widths to int,
        ensuring sum(...) == width_total.
        """
        sm = sum(w_list)
        if sm <= 0:
            out = [0] * (len(w_list) - 1)
            out.append(width_total)
            return out
        # check if sum close to width_total
        if abs(sm - width_total) < 1e-5:
            w_scaled = w_list[:]
        elif sm > width_total:
            factor = width_total / sm
            w_scaled = [wi * factor for wi in w_list]
        else:
            leftover = width_total - sm
            w_scaled = [wi + (wi / sm) * leftover for wi in w_list]

        w_int = [int(round(x)) for x in w_scaled]
        diff = width_total - sum(w_int)

        if diff > 0:
            idx = 0
            while diff > 0 and idx < len(w_int):
                w_int[idx] += 1
                diff -= 1
                idx += 1
                if idx >= len(w_int):
                    idx = 0
        elif diff < 0:
            diff = abs(diff)
            idx = 0
            while diff > 0 and idx < len(w_int):
                if w_int[idx] > 0:
                    w_int[idx] -= 1
                    diff -= 1
                idx += 1
                if idx >= len(w_int):
                    idx = 0

        return w_int

    @staticmethod
    def subfolder_interpolation_data(
        subfolder_names: List[str], subfolder_fade_info: dict, steps: int
    ):
        """
        Prepares global interpolation data from subfolder fades.
        """
        m = len(subfolder_names)
        if m < 2:
            return None
        fadeDatas = []
        for sf in subfolder_names:
            fd = subfolder_fade_info.get(sf, None)
            if not fd:
                return None
            fadeDatas.append(fd)
        h, w, _ = fadeDatas[0].final_image.shape
        bpos_count = len(fadeDatas[0].boundary_positions)
        if bpos_count < 1:
            return None

        keyframe_times = np.linspace(0, 1, m)
        boundary_splines_data = []
        for j in range(bpos_count):
            arr_j = []
            for fd in fadeDatas:
                if j < len(fd.boundary_positions):
                    arr_j.append(fd.boundary_positions[j])
                else:
                    arr_j.append(fd.boundary_positions[-1])
            boundary_splines_data.append(arr_j)

        color_splines_data = []
        for j in range(bpos_count):
            c_list = []
            for fd in fadeDatas:
                if j < len(fd.average_colors):
                    c_list.append(fd.average_colors[j])
                else:
                    c_list.append(fd.average_colors[-1])
            color_splines_data.append(c_list)

        total_frames = steps * (m - 1)
        return (
            keyframe_times,
            boundary_splines_data,
            color_splines_data,
            w,
            h,
            total_frames,
        )

    @staticmethod
    def build_spline_frame(
        frame_idx: int,
        t_global: float,
        keyframe_times: np.ndarray,
        boundary_splines_data: List[List[float]],
        color_splines_data: List[List[np.ndarray]],
        w: int,
        h: int,
    ):

        n_boundaries = len(boundary_splines_data)
        global_boundaries = []

        # 1) Evaluate x-positions (boundaries)
        for j in range(n_boundaries):
            arr_j = boundary_splines_data[j]
            spl_j = CubicSpline(keyframe_times, arr_j)
            # spl_j = PchipInterpolator(keyframe_times, arr_j)
            x_val = float(spl_j(t_global))
            global_boundaries.append(int(round(x_val)))

        # 2) Evaluate color row-average
        # We'll do linear interpolation between the two keyframes
        m = len(keyframe_times)
        pos = t_global * (m - 1)
        i2 = int(np.floor(pos))
        local_t = pos - i2
        if i2 >= m - 1:
            i2 = m - 2
            local_t = 1.0

        global_avg_colors = []
        for j in range(n_boundaries):
            c_list = color_splines_data[j]
            cA = c_list[i2]
            cB = c_list[i2 + 1]
            c_mix = np.clip((1.0 - local_t) * cA + local_t * cB, 0, 255).astype(
                np.uint8
            )
            global_avg_colors.append(c_mix)

        # 3) Enforce strictly increasing boundaries
        if n_boundaries > 0:
            if global_boundaries[0] != 0:
                global_boundaries.insert(0, 0)
                global_avg_colors.insert(0, global_avg_colors[0])
            if global_boundaries[-1] != w:
                global_boundaries.append(w)
                global_avg_colors.append(global_avg_colors[-1])
            for ix in range(1, len(global_boundaries)):
                if global_boundaries[ix] <= global_boundaries[ix - 1]:
                    global_boundaries[ix] = global_boundaries[ix - 1] + 1
                    if global_boundaries[ix] > w:
                        global_boundaries[ix] = w

        # 4) Build the frame using these boundaries + average colors
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        for j in range(len(global_boundaries) - 1):
            x0 = global_boundaries[j]
            x1 = global_boundaries[j + 1]
            seg_w = x1 - x0
            if seg_w < 1:
                seg_w = 1
                x1 = x0 + 1

            leftC = global_avg_colors[j].reshape(h, 1, 3)
            rightC = global_avg_colors[j + 1].reshape(h, 1, 3)
            xi = np.linspace(0.0, 1.0, seg_w).reshape(1, seg_w, 1)
            grad = (1.0 - xi) * leftC + xi * rightC
            grad = grad.astype(np.uint8)

            # if seg_w < MIN_SEG_DIST => recolor entire gradient with average of leftC & rightC
            if seg_w < MIN_SEG_DIST:
                # debug-print
                # print(f"[DEBUG] Frame {frame_idx}, segment j={j}, seg_w={seg_w} => recolor (Variant B).")
                avgC = 0.5 * leftC + 0.5 * rightC
                avgC = avgC.astype(np.uint8)
                grad = np.repeat(avgC, seg_w, axis=1)

            try:
                frame[:, x0:x1] = grad
            except ValueError as e:
                print("[ERROR] dimension mismatch in build_spline_frame:", e)

        return (frame_idx, frame, None)

    @staticmethod
    def export_crossfade_video(
        keyframe_times: np.ndarray,
        boundary_splines_data: List[List[float]],
        color_splines_data: List[List[np.ndarray]],
        w: int,
        h: int,
        total_frames: int,
        fps_val: int,
        frames_per_batch: int,
        worker_count: int,
        ffmpeg_path: str,
        out_folder: str,
        file_tag: str,
        progress_bar,
        diag,
        delete_chunks: bool = True,
        ghost_count: int = 5,
        split_count: int = 1,
    ):
        """
        Renders frames => partial .mp4 in 'output/chunk' => merges => final in 'output'.
        Also applies:
          - 'ghosting' effect with 'ghost_count' frames
          - horizontal splitting into 'split_count' parts => each part gets its own .mp4

        We'll store chunkfiles separately for each part. Then do a final merge per part.

        Args:
            keyframe_times, boundary_splines_data, color_splines_data: data from subfolder_interpolation_data
            w, h: Frame dimension
            total_frames: how many frames total
            fps_val: frames per second
            frames_per_batch: chunk size
            worker_count: concurrency
            ffmpeg_path: path to ffmpeg
            out_folder: e.g. 'output'
            file_tag: naming prefix for mp4
            progress_bar, diag: for UI updating
            delete_chunks: if True, remove chunk files after merge
            ghost_count: frames for ghosting variant B
            split_count: how many horizontal splits (1..3)
        """

        # This will hold the chunk path-lists per "part"
        # e.g. if split_count=3 => chunk_paths_per_part = [[],[],[]]
        chunk_paths_per_part = [[] for _ in range(split_count)]

        chunk_folder = os.path.join(out_folder, "chunk")
        if not os.path.exists(chunk_folder):
            os.makedirs(chunk_folder)

        if progress_bar:
            progress_bar["maximum"] = total_frames + 1
            progress_bar["value"] = 0

        tasks = []
        for f_idx in range(total_frames + 1):
            t = f_idx / total_frames
            tasks.append((f_idx, t))

        chunk_idx = 1
        start_i = 0
        chunk_total = math.ceil((total_frames + 1) / frames_per_batch)

        # function to compute the 'width' of each part
        # handle if not divisible
        def get_part_slice(p: int, split_count: int, frame_width: int):
            """
            For part p in [0..split_count-1], returns (x_start, x_end)
            so the final segments sum up to frame_width.
            """
            base_w = frame_width // split_count
            remainder = frame_width % split_count
            x_start = p * base_w
            # distribute remainder among the first 'remainder' parts
            if p < remainder:
                x_start += p
                part_w = base_w + 1
            else:
                x_start += remainder
                part_w = base_w
            x_end = x_start + part_w
            return x_start, x_end

        while start_i <= total_frames:
            end_i = min(start_i + frames_per_batch, total_frames + 1)

            # create video writers for each part
            # chunk_name e.g. {file_tag}_chunk_001_part_1.mp4
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer_parts = []
            for p in range(split_count):
                # figure out slice w
                xs, xe = get_part_slice(p, split_count, w)
                part_w = xe - xs
                part_h = h

                chunk_name = f"{file_tag}_chunk_{chunk_idx:03d}_part_{p+1}.mp4"
                chunk_path = os.path.join(chunk_folder, chunk_name)
                # remember this path to merge later
                chunk_paths_per_part[p].append(chunk_path)

                vw = cv2.VideoWriter(
                    chunk_path, fourcc, float(fps_val), (part_w, part_h), True
                )
                writer_parts.append(vw)

            chunk_start_time = time.time()
            print(
                f"[INFO] building chunk {chunk_idx}/{chunk_total}, frames {start_i}..{end_i-1} at {datetime.now().strftime('%H:%M:%S')}"
            )

            subset = tasks[start_i:end_i]

            # ghost buffer
            carry_over_ghost_frames = []

            # 1) Build raw frames in parallel
            with concurrent.futures.ProcessPoolExecutor(
                max_workers=worker_count
            ) as executor:
                fut_map = {}
                for fid, tg in subset:
                    fut = executor.submit(
                        FadingLogic.build_spline_frame,
                        fid,
                        tg,
                        keyframe_times,
                        boundary_splines_data,
                        color_splines_data,
                        w,
                        h,
                    )
                    fut_map[fut] = fid

                result_frames = {}
                for fut in concurrent.futures.as_completed(fut_map):
                    fi = fut_map[fut]
                    try:
                        (ret_idx, frame, err) = fut.result()
                        if err:
                            print(f"[ERROR] Worker error frame {ret_idx}: {err}")
                        else:
                            result_frames[ret_idx] = frame
                    except Exception as exc:
                        print(f"[ERROR] Crash frame {fi}: {exc}")

                    if progress_bar:
                        progress_bar["value"] += 1
                        diag.update_idletasks()

            # 2) Write frames in ascending order, applying ghosting if ghost_count>0
            # but note: we also do splitting => each part gets a slice
            for fid in range(start_i, end_i):
                raw_frame = result_frames.get(fid, None)
                if raw_frame is None:
                    continue

                # ghosting
                if ghost_count > 0:
                    # sum up with ghost_buffer
                    acc = raw_frame.astype(np.float32)
                    for gfr in carry_over_ghost_frames:
                        acc += gfr.astype(np.float32)
                    divisor = 1 + len(carry_over_ghost_frames)
                    if divisor > ghost_count:
                        divisor = ghost_count
                    ghosted_frame = (acc / float(divisor)).astype(np.uint8)

                    # push to buffer
                    carry_over_ghost_frames.append(ghosted_frame)
                    if len(carry_over_ghost_frames) > (ghost_count - 1):
                        carry_over_ghost_frames.pop(0)

                    frame_out = ghosted_frame
                else:
                    # no ghosting
                    frame_out = raw_frame

                # 3) split horizontally, write each part
                for p in range(split_count):
                    x_start, x_end = get_part_slice(p, split_count, w)
                    slice_part = frame_out[:, x_start:x_end]
                    writer_parts[p].write(slice_part)

            # done chunk => release all writers
            for wpart in writer_parts:
                wpart.release()

            chunk_time = time.time() - chunk_start_time
            c_mins = int(chunk_time // 60)
            c_secs = int(chunk_time % 60)
            if c_mins > 0:
                print(f"[INFO] chunk {chunk_idx} done in {c_mins}min {c_secs}s.")
            else:
                print(f"[INFO] chunk {chunk_idx} done in {c_secs}s.")

            start_i = end_i
            chunk_idx += 1

        # MERGE step => now we have 'split_count' sets of chunkfiles
        final_mp4_list = []
        for p in range(split_count):
            now_s = datetime.now().strftime("%Y%m%d_%H%M%S")
            list_path = os.path.join(f"chunk_{now_s}_part_{p+1}.txt")
            with open(list_path, "w", encoding="utf-8") as f:
                for cpath in chunk_paths_per_part[p]:
                    f.write(f"file '{cpath}'\n")

            final_mp4 = os.path.join(out_folder, f"{file_tag}_part_{p+1}.mp4")
            cmd = [
                ffmpeg_path,
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                list_path,
                "-c",
                "copy",
                final_mp4,
            ]
            print("[MERGE] running:", " ".join(cmd))
            ret = subprocess.run(cmd, check=False)
            if ret.returncode == 0:
                print(f"[MERGE] success => {final_mp4}")
                if delete_chunks:
                    # remove chunkfiles for part p
                    for cp in chunk_paths_per_part[p]:
                        try:
                            os.remove(cp)
                        except:
                            pass
                    try:
                        os.remove(list_path)
                    except:
                        pass
                final_mp4_list.append(final_mp4)
            else:
                print(f"[MERGE] ffmpeg merge failed => code {ret.returncode}")

        # done
        print(f"[INFO] Finished split_count={split_count}, final files:")
        for fmp4 in final_mp4_list:
            print("  ", fmp4)
