import os
import json
from datetime import datetime
from typing import List, Dict

from datamodel import ImageData, SubfolderFadeData, FadeParams
from fading import FadingLogic, ImageHelper


class FadeController:
    """
    This class handles fade calculations, subfolder building, caching, exports, etc.
    For subfolder management, we assume you have a subfolder_manager available or
    you pass subfolder_data in the methods that need it.
    """

    def __init__(self, subfolder_manager):
        self.subfolder_manager = subfolder_manager
        # A dictionary subfolder_name -> SubfolderFadeData
        self.subfolder_fade_info: Dict[str, SubfolderFadeData] = {}

        # One simple cache for the "current" fade
        self._last_fade_cache = {
            "active_paths": None,
            "brightness_list": None,
            "proxy_list": None,
            "width": None,
            "height": None,
            "gamma": None,
            "influence": None,
            "damping": None,
            "midpoint": None,
            "weighting": None,
            "result": None,
        }

        # Current weighting parameters - can be updated from UI
        self.gamma_val = 2.0
        self.influence_val = 4.0
        self.damping_val = 100.0
        self.midpoint_val = 128.0
        self.weighting_mode = "Exponential"

    def set_weighting_params(
        self, gamma_val, influence_val, damping_val, midpoint_val, weighting_mode
    ):
        """
        Called by the UI to update the weighting/gamma parameters.
        """
        self.gamma_val = gamma_val
        self.influence_val = influence_val
        self.damping_val = damping_val
        self.midpoint_val = midpoint_val
        self.weighting_mode = weighting_mode

    def get_current_weighting_params(self) -> dict:
        """
        Returns the current weighting params as a dictionary.
        """
        return {
            "gamma": self.gamma_val,
            "influence": self.influence_val,
            "damping": self.damping_val,
            "midpoint": self.midpoint_val,
            "weighting": self.weighting_mode,
        }

    def recalc_brightness(self, image_data: List[ImageData]) -> None:
        """
        Recompute brightness for each ImageData, using self.gamma_val.
        """
        for d in image_data:
            d.brightness_value = ImageHelper.calculate_brightness(
                d.file_path, self.gamma_val
            )

    def filter_brightness(self, image_data: List[ImageData], threshold: int) -> None:
        """
        Sets check_var=False for images below threshold.
        """
        for d in image_data:
            if d.brightness_value < threshold:
                if d.check_var:
                    d.check_var.set(False)

    def reset_brightness_filter(
        self, image_data: List[ImageData], brightness_slider
    ) -> None:
        """
        Resets the brightness slider to 0 and re-checks all images.
        """
        brightness_slider.set(0)
        for d in image_data:
            if d.check_var:
                d.check_var.set(True)

    def build_horizontal_fade_cache(
        self, image_data: List[ImageData], width: int, height: int
    ):
        """
        Uses the caching mechanism to avoid re-running build_horizontal_fade if possible.
        Returns (final_img, boundary_positions, filenames_at_boundaries, avgcols) or None.
        """
        active_paths = []
        brightness_list = []
        proxy_list = []
        for d in image_data:
            if d.check_var and d.check_var.get():
                active_paths.append(d.file_path)
                brightness_list.append(d.brightness_value)
                proxy_list.append(d.is_proxy)

        if len(active_paths) < 2:
            return None

        c = self._last_fade_cache
        same_input = (
            c["active_paths"] == tuple(active_paths)
            and c["brightness_list"] == tuple(brightness_list)
            and c["proxy_list"] == tuple(proxy_list)
            and c["width"] == width
            and c["height"] == height
            and c["gamma"] == self.gamma_val
            and c["influence"] == self.influence_val
            and c["damping"] == self.damping_val
            and c["midpoint"] == self.midpoint_val
            and c["weighting"] == self.weighting_mode
        )
        if same_input and c["result"] is not None:
            return c["result"]

        fade_params = FadeParams(
            width=width,
            height=height,
            gamma=self.gamma_val,
            influence=self.influence_val,
            damping=self.damping_val,
            midpoint=self.midpoint_val,
            weighting=self.weighting_mode,
        )
        result = FadingLogic.build_horizontal_fade(
            active_paths, brightness_list, proxy_list, fade_params
        )

        c["active_paths"] = tuple(active_paths)
        c["brightness_list"] = tuple(brightness_list)
        c["proxy_list"] = tuple(proxy_list)
        c["width"] = width
        c["height"] = height
        c["gamma"] = self.gamma_val
        c["influence"] = self.influence_val
        c["damping"] = self.damping_val
        c["midpoint"] = self.midpoint_val
        c["weighting"] = self.weighting_mode
        c["result"] = result

        return result

    def load_and_prepare_subfolders(
        self, start_sub: str, end_sub: str, width: int, height: int
    ) -> bool:
        """
        Example: builds subfolder fades for the range [start_sub..end_sub] with current weighting params.
        """
        subfolders = self.subfolder_manager.subfolder_names
        if start_sub not in subfolders or end_sub not in subfolders:
            return False

        idx_s = subfolders.index(start_sub)
        idx_e = subfolders.index(end_sub)
        if idx_s > idx_e:
            return False

        sub_list = subfolders[idx_s : idx_e + 1]
        if len(sub_list) < 2:
            return False

        wparams = self.get_current_weighting_params()

        # Build each subfolder's fade
        for sf in sub_list:
            off_map = self.subfolder_manager.subfolder_data[sf]
            # create image data
            fi = []
            for off_val, (fp, px) in sorted(off_map.items(), key=lambda x: x[0]):
                brv = ImageHelper.calculate_brightness(fp, wparams["gamma"])
                fi.append(
                    ImageData(
                        file_path=fp,
                        check_var=None,
                        brightness_value=brv,
                        offset=off_val,
                        is_proxy=px,
                    )
                )

            if len(fi) < 2:
                return False

            fade_params = FadeParams(
                width=width,
                height=height,
                gamma=wparams["gamma"],
                influence=wparams["influence"],
                damping=wparams["damping"],
                midpoint=wparams["midpoint"],
                weighting=wparams["weighting"],
            )
            paths = [x.file_path for x in fi]
            br_list = [x.brightness_value for x in fi]
            px_list = [x.is_proxy for x in fi]

            result = FadingLogic.build_horizontal_fade(
                paths, br_list, px_list, fade_params
            )
            if not result:
                return False
            (fimg, bpos, fnames, avgcols) = result

            self.subfolder_fade_info[sf] = SubfolderFadeData(
                final_image=fimg,
                boundary_positions=bpos,
                filenames_at_boundaries=fnames,
                average_colors=avgcols,
                transitions=[],
            )
        return True

    def export_crossfade_video(
        self,
        chosen_subfolders: List[str],
        start_sub: str,
        end_sub: str,
        width: int,
        height: int,
        steps_val: int,
        fps_val: int,
        frames_per_batch: int,
        workers_val: int,
        ffmpeg_path: str,
        ghost_val: int,
        split_val: int,
        delete_chunks: bool,
        progress_bar,
        diag,
        weighting_params: dict,
    ) -> List[str]:
        """
        Actually exports a crossfade video for subfolder range [start_sub..end_sub].
        Returns the list of part MP4 paths.
        """
        if start_sub not in chosen_subfolders or end_sub not in chosen_subfolders:
            return []
        idx_s = chosen_subfolders.index(start_sub)
        idx_e = chosen_subfolders.index(end_sub)
        if idx_s > idx_e:
            return []

        sub_list = chosen_subfolders[idx_s : idx_e + 1]
        if len(sub_list) < 2:
            return []

        # Use subfolder_interpolation_data from fading
        from fading import FadingLogic

        ret_spline = FadingLogic.subfolder_interpolation_data(
            sub_list, self.subfolder_fade_info, steps_val
        )
        if not ret_spline:
            return []

        (
            keyframe_times,
            boundary_splines_data,
            color_splines_data,
            w,
            h,
            total_frames,
        ) = ret_spline

        out_folder = "output"
        if not os.path.exists(out_folder):
            os.makedirs(out_folder)

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        igam = weighting_params["gamma"]
        iinf = weighting_params["influence"]
        idam = weighting_params["damping"]
        imid = weighting_params["midpoint"]

        ftag = f"{now_str}_fading_g{igam}i{iinf}d{idam}m{imid}"

        FadingLogic.export_crossfade_video(
            keyframe_times=keyframe_times,
            boundary_splines_data=boundary_splines_data,
            color_splines_data=color_splines_data,
            w=w,
            h=h,
            total_frames=total_frames,
            fps_val=fps_val,
            frames_per_batch=frames_per_batch,
            worker_count=workers_val,
            ffmpeg_path=ffmpeg_path,
            out_folder=out_folder,
            file_tag=ftag,
            progress_bar=progress_bar,
            diag=diag,
            delete_chunks=delete_chunks,
            ghost_count=ghost_val,
            split_count=split_val,
        )

        # gather part files
        paths = []
        for i in range(1, split_val + 1):
            pmp4 = os.path.join(out_folder, f"{ftag}_part-{i}.mp4")
            if os.path.isfile(pmp4):
                paths.append(pmp4)
        return paths

    def build_combined_video_hstack(
        self, part_paths: List[str], out_path: str, ffmpeg_path: str
    ) -> None:
        """
        Uses ffmpeg hstack to combine multiple part videos horizontally.
        """
        if len(part_paths) < 2:
            return
        import subprocess

        cmd = [ffmpeg_path]
        for p in part_paths:
            cmd += ["-i", p]
        # build filter
        input_refs = "".join(f"[{i}:v]" for i in range(len(part_paths)))
        filter_str = f"{input_refs}hstack=inputs={len(part_paths)}"
        cmd += [
            "-filter_complex",
            filter_str,
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "fast",
            "-c:a",
            "copy",
            out_path,
        ]
        subprocess.run(cmd, check=False)

    def build_movement_data(
        self,
        chosen_subfolders: List[str],
        start_sub: str,
        end_sub: str,
        steps_val: int,
        width: int,
        height: int,
    ) -> dict:
        """
        Builds a dict describing movement data for the subfolder range [start_sub..end_sub].
        """
        if start_sub not in chosen_subfolders or end_sub not in chosen_subfolders:
            return {}
        idx_s = chosen_subfolders.index(start_sub)
        idx_e = chosen_subfolders.index(end_sub)
        if idx_s > idx_e:
            return {}

        sub_list = chosen_subfolders[idx_s : idx_e + 1]
        if len(sub_list) < 2:
            return {}

        from fading import FadingLogic

        ret_spline = FadingLogic.subfolder_interpolation_data(
            sub_list, self.subfolder_fade_info, steps_val
        )
        if not ret_spline:
            return {}

        (
            keyframe_times,
            boundary_splines_data,
            color_splines_data,
            w,
            h,
            total_frames,
        ) = ret_spline
        movement_data = []
        for frame_idx in range(total_frames + 1):
            frame_info = FadingLogic.build_movement_data(
                frame_idx, keyframe_times, boundary_splines_data, w, total_frames
            )
            movement_data.append(frame_info)

        export_obj = {
            "width": w,
            "height": h,
            "total_frames": total_frames,
            "subfolders": sub_list,
            "movement_data": movement_data,
            "keyframe_times": keyframe_times.tolist(),
        }
        return export_obj

    def save_movement_data(self, export_obj: dict) -> str:
        if not export_obj:
            return ""
        out_folder = "output"
        if not os.path.exists(out_folder):
            os.makedirs(out_folder)
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        path_json = os.path.join(out_folder, f"{now_str}_movement.json")
        try:
            with open(path_json, "w", encoding="utf-8") as f:
                json.dump(export_obj, f, indent=4)
        except Exception:
            return ""
        return path_json
