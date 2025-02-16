import os
import cv2
import re
import numpy as np
from typing import Tuple, List
from datamodel import FadeParams
import concurrent.futures
import subprocess
from datetime import datetime
import time

MIN_SEG_DIST = 6  # 6 if resolution is 5760x1080px


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
            s2 = re.match(r"UTC([+-]\d+(?:\.\d+)?).*",
                          m.group(1), re.IGNORECASE)
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
        active_paths: List[str],
        brightness_list: List[int],
        proxy_list: List[bool],
        fade_params: FadeParams
    ):
        """
        Performs a horizontal fade, with a check for very narrow segments.
        Any segment below MIN_SEG_DIST pixels wide is simply recolored
        to match the average of its neighbors.
        """

        if len(active_paths) < 2:
            return None

        w_total = fade_params.width
        h_total = fade_params.height
        influence_val = fade_params.influence
        damping_val = fade_params.damping

        # final fade image
        final_img = np.zeros((h_total, w_total, 3), dtype=np.uint8)
        boundaries = []
        fnames = []
        n = len(active_paths)

        # 1) Load row-average colors
        loaded_colors = []
        for i, path in enumerate(active_paths):
            img = cv2.imread(path)
            if img is None:
                # fallback dummy
                dummy = np.zeros((10, 10, 3), dtype=np.uint8)
                ratio = float(h_total)/10.0
                new_w = max(1, int(10*ratio))
                rz = cv2.resize(dummy, (new_w, h_total))
                avg = FadingLogic.calculate_horizontal_average(rz)
            else:
                ratio = float(h_total) / float(img.shape[0])
                new_w = max(1, int(img.shape[1] * ratio))
                rz = cv2.resize(img, (new_w, h_total))
                avg = FadingLogic.calculate_horizontal_average(rz)
            loaded_colors.append(avg)

        # 2) Compute transition weights
        transitions = []
        original = []
        for i in range(n-1):
            ab = (brightness_list[i] + brightness_list[i+1]) * 0.5
            if influence_val == 0:
                wgt = 1.0
            else:
                safe_bright = max(1, ab)
                wgt = (safe_bright ** influence_val)
                if wgt < 1e-6:
                    wgt = 0
            transitions.append(wgt)
            original.append(1.0)

        sum_w = sum(transitions)
        if sum_w <= 0:
            return None
        sum_o = sum(original)

        # 3) Distribute segment widths with damping
        segw_float = []
        for i in range(n-1):
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

        seg_int = FadingLogic.distribute_segment_widths(segw_float, w_total)

        # 4) Build the fade
        x_start = 0
        for i in range(n-1):
            seg_pix = seg_int[i]
            fname = os.path.basename(active_paths[i])
            is_proxy = proxy_list[i]

            if seg_pix <= 0:
                boundaries.append(x_start)
                fnames.append((fname, is_proxy))
                continue

            leftC = loaded_colors[i]
            rightC = loaded_colors[i+1]

            x_end = x_start + seg_pix
            if x_end > w_total:
                x_end = w_total
            seg_w = x_end - x_start
            if seg_w < 1:
                boundaries.append(x_start)
                fnames.append((fname, is_proxy))
                continue

            # construct gradient
            xi = np.linspace(
                0.0, 1.0, seg_w, dtype=np.float32).reshape(1, seg_w, 1)
            leftC_resh = leftC.reshape(h_total, 1, 3)
            rightC_resh = rightC.reshape(h_total, 1, 3)
            grad = (1.0 - xi) * leftC_resh + xi * rightC_resh
            grad = grad.astype(np.uint8)

            # If segment < MIN_SEG_DIST, recolor it to neighbors' average
            if seg_w < MIN_SEG_DIST:
                # simply set grad to the average of leftC and rightC
                avg_neighbor = 0.5 * leftC_resh + 0.5 * rightC_resh
                avg_neighbor = avg_neighbor.astype(np.uint8)
                grad = np.repeat(avg_neighbor, seg_w, axis=1)

            # place into final_img
            try:
                final_img[:, x_start: x_start + seg_w] = grad
            except ValueError as e:
                print("[ERROR] dimension mismatch:", e)

            boundaries.append(x_start)
            fnames.append((fname, is_proxy))
            x_start = x_end

        # add last boundary
        lastn = os.path.basename(active_paths[-1])
        lastpx = proxy_list[-1]
        boundaries.append(w_total - 1)
        fnames.append((lastn, lastpx))

        return (final_img, boundaries, fnames, loaded_colors)

    @staticmethod
    def distribute_segment_widths(w_list: List[float], width_total: int) -> List[int]:
        sm = sum(w_list)
        if sm <= 0:
            out = [0] * (len(w_list) - 1)
            out.append(width_total)
            return out
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
    def build_cubicspline_subfolders(
        subfolder_names: List[str], subfolder_fade_info: dict, steps: int
    ):
        """
        Creates a cubic spline across subfolders => total_frames= steps*(m-1).
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
        h: int
    ):
        from scipy.interpolate import CubicSpline

        n_boundaries = len(boundary_splines_data)
        global_boundaries = []

        # 1) Evaluate x-positions (boundaries)
        for j in range(n_boundaries):
            arr_j = boundary_splines_data[j]
            spl_j = CubicSpline(keyframe_times, arr_j)
            x_val = float(spl_j(t_global))
            global_boundaries.append(int(round(x_val)))

        # 2) Evaluate color row-average
        # We'll do linear interpolation between the two keyframes
        m = len(keyframe_times)
        pos = t_global*(m-1)
        i2 = int(np.floor(pos))
        local_t = pos - i2
        if i2 >= m-1:
            i2 = m-2
            local_t = 1.0

        global_avg_colors = []
        for j in range(n_boundaries):
            c_list = color_splines_data[j]
            cA = c_list[i2]
            cB = c_list[i2+1]
            c_mix = np.clip((1.0 - local_t)*cA + local_t *
                            cB, 0, 255).astype(np.uint8)
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
                if global_boundaries[ix] <= global_boundaries[ix-1]:
                    global_boundaries[ix] = global_boundaries[ix-1] + 1
                    if global_boundaries[ix] > w:
                        global_boundaries[ix] = w

        # 4) Build the frame using these boundaries + average colors
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        for j in range(len(global_boundaries)-1):
            x0 = global_boundaries[j]
            x1 = global_boundaries[j+1]
            seg_w = x1 - x0
            if seg_w < 1:
                seg_w = 1
                x1 = x0+1

            leftC = global_avg_colors[j].reshape(h, 1, 3)
            rightC = global_avg_colors[j+1].reshape(h, 1, 3)
            xi = np.linspace(0.0, 1.0, seg_w).reshape(1, seg_w, 1)
            grad = (1.0 - xi)*leftC + xi*rightC
            grad = grad.astype(np.uint8)

            # if seg_w < MIN_SEG_DIST => recolor entire gradient with average of leftC & rightC
            if seg_w < MIN_SEG_DIST:
                # debug-print
                # print(f"[DEBUG] Frame {frame_idx}, segment j={j}, seg_w={seg_w} => recolor (Variant B).")
                avgC = 0.5*leftC + 0.5*rightC
                avgC = avgC.astype(np.uint8)
                grad = np.repeat(avgC, seg_w, axis=1)

            try:
                frame[:, x0:x1] = grad
            except ValueError as e:
                print("[ERROR] dimension mismatch in build_spline_frame:", e)

        return (frame_idx, frame, None)

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
        ghost_count: int = 5
    ):
        """
        Renders frames => partial .mp4 in 'output/chunk' => merges => final in 'output'.
        Also applies a 'ghosting' effect with 'ghost_count' frames of recursion,
        meaning each new frame is averaged with its previously ghosted frames.

        Args:
            keyframe_times: The normalized t-values for each subfolder keyframe (0..1).
            boundary_splines_data: A list of boundary positions (in px) for each segment, per keyframe.
            color_splines_data: A list of average-color arrays for each segment, per keyframe.
            w, h: Frame dimensions (px).
            total_frames: The total number of frames to render (crossfade steps*(m-1)).
            fps_val: Video frames per second.
            frames_per_batch: How many frames we encode in one chunk.
            worker_count: Number of parallel processes for CPU-bound tasks.
            ffmpeg_path: Path to ffmpeg.exe.
            out_folder: Destination folder (e.g. 'output').
            file_tag: Used for naming the .mp4 output file(s).
            progress_bar: A tkinter Progressbar to update UI progress.
            diag: The tk.Toplevel window for refreshing UI.
            delete_chunks: If True, intermediate chunk files will be deleted after merging.
            ghost_count: Number of frames to blend in a rolling ghosting manner.
                        Must be >= 1. For example, 5 means each new frame is
                        ( raw_frame + 4 previous ghosted frames ) / 5.
        """
        import math

        # We'll store the last ghost_count-1 "ghosted" frames to handle chunk transitions.
        carry_over_ghost_frames = []

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

        chunk_paths = []
        start_i = 0
        chunk_idx = 1
        chunk_total = math.ceil((total_frames + 1) / frames_per_batch)

        while start_i <= total_frames:
            end_i = min(start_i + frames_per_batch, total_frames + 1)
            chunk_name = f"{file_tag}_chunk_{chunk_idx:03d}.mp4"
            chunk_path = os.path.join(chunk_folder, chunk_name)
            chunk_paths.append(chunk_path)

            chunk_start_time = time.time()
            print(
                f"[INFO] building chunk {chunk_idx}/{chunk_total}, frames {start_i}..{end_i-1} at {datetime.now().strftime('%H:%M:%S')}"
            )

            subset = tasks[start_i:end_i]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(
                chunk_path, fourcc, float(fps_val), (w, h), True
            )

            # We'll use a local buffer for ghost frames in this chunk.
            # Initialize it with carry_over_ghost_frames from previous chunk.
            ghost_buffer = [gf for gf in carry_over_ghost_frames]
            carry_over_ghost_frames = []  # reset after copying

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

                # Collect frames in completion order
                result_frames = {}
                for fut in concurrent.futures.as_completed(fut_map):
                    fi = fut_map[fut]
                    try:
                        (ret_idx, frame, err) = fut.result()
                        if err:
                            print(
                                f"[ERROR] Worker error frame {ret_idx}: {err}")
                        else:
                            result_frames[ret_idx] = frame
                    except Exception as exc:
                        print(f"[ERROR] Crash frame {fi}: {exc}")

                    if progress_bar:
                        progress_bar["value"] += 1
                        diag.update_idletasks()

            # Now we must write frames in ascending order to the chunk,
            # applying the ghosting effect.
            for fid in range(start_i, end_i):
                raw_frame = result_frames.get(fid, None)
                if raw_frame is None:
                    continue

                # Convert to float32 for summation
                # ghost_buffer already stored ghosted frames as uint8, so convert each to float32
                acc = raw_frame.astype(np.float32)
                # We add the existing ghosted frames from the buffer
                for gfr in ghost_buffer:
                    acc += gfr.astype(np.float32)

                # Determine the actual divisor:
                # always sums (raw_frame + all ghosted frames).
                # We want in total ghost_count frames if ghost_buffer already has (ghost_count-1).
                divisor = 1 + len(ghost_buffer)
                # But we want to ensure it doesn't exceed 'ghost_count'
                # If len(ghost_buffer) >= ghost_count-1, we do a full average over ghost_count.
                # If ghost_buffer is smaller at the chunk start, we do partial.
                # We typically clamp to ghost_count if divisor > ghost_count,
                # but if ghost_buffer is long, we pop from it. Let's see:
                if divisor > ghost_count:
                    # This can occur if ghost_buffer is bigger than ghost_count-1 for some reason
                    # (shouldn't happen if we handle the buffer size carefully).
                    divisor = ghost_count

                # finalize ghosted frame
                ghosted_frame = (acc / float(divisor)).astype(np.uint8)

                # push this ghosted frame into the buffer
                ghost_buffer.append(ghosted_frame)
                # keep only the last (ghost_count - 1)
                if len(ghost_buffer) > (ghost_count - 1):
                    ghost_buffer.pop(0)

                # write to video
                writer.write(ghosted_frame)

            writer.release()

            chunk_time = time.time() - chunk_start_time
            c_mins = int(chunk_time // 60)
            c_secs = int(chunk_time % 60)
            if c_mins > 0:
                print(
                    f"[INFO] chunk {chunk_idx} done in {c_mins}min {c_secs}s."
                )
            else:
                print(f"[INFO] chunk {chunk_idx} done in {c_secs}s.")

            # After finishing this chunk, store last ghost_count-1 ghosted frames
            # so next chunk can continue the "ghost" effect over chunk boundary.
            if len(ghost_buffer) > 0:
                carry_over_ghost_frames = ghost_buffer[-(ghost_count - 1):]

            start_i = end_i
            chunk_idx += 1

        # MERGE step
        now_s = datetime.now().strftime("%Y%m%d_%H%M%S")
        list_path = os.path.join(f"chunk_{now_s}.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for cpath in chunk_paths:
                f.write(f"file '{cpath}'\n")

        final_mp4 = os.path.join(out_folder, f"{file_tag}.mp4")
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
                for cp in chunk_paths:
                    try:
                        os.remove(cp)
                    except:
                        pass
                try:
                    os.remove(list_path)
                except:
                    pass
        else:
            print(f"[MERGE] ffmpeg merge failed => code {ret.returncode}")
