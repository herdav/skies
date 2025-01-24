# ui.py

import os
import cv2
import tkinter as tk
from tkinter import filedialog, ttk, simpledialog, messagebox
import numpy as np
import time
from PIL import Image, ImageTk, ImageDraw, ImageFont
from dataclasses import dataclass
from typing import List

from fading import FadingLogic

BG_COLOR = "#dcdcdc"
TEXT_BG_COLOR = (220, 220, 220, 255)
TEXT_FONT_SIZE = 12

MODE_NONE = 0
MODE_FILES = 1
MODE_SINGLE_DIR = 2
MODE_SUBFOLDERS = 3

@dataclass
class ImageData:
    # Container for each image's data
    file_path: str
    check_var: tk.BooleanVar
    brightness_value: int
    offset: float
    is_proxy: bool

class FadingUI:
    # Main GUI class
    def __init__(self, root: tk.Tk):
        # Initialize main window
        self.root = root
        self.root.title("Horizontal Fading - Single-Thread Export")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry("1400x750")

        self.current_mode = MODE_NONE

        # Data containers
        self.image_data: List[ImageData] = []
        self.subfolder_names = []
        self.subfolder_data = {}
        self.subfolder_combo_idx = 0

        self.final_image = None
        self.boundary_positions = []
        self.filenames_at_boundaries = []

        # Crossfade frames
        self.crossfade_frames = []
        self.crossfade_index = 0
        self.crossfade_active = False

        self._build_ui()

    def _build_ui(self):
        # Top controls
        self.top_frame = tk.Frame(self.root, bg=BG_COLOR)
        self.top_frame.pack(side="top", fill="x", pady=5)

        # File/Directory selection
        self.btn_files = tk.Button(self.top_frame, text="Select Images",
                                   command=self.on_select_images, bg=BG_COLOR)
        self.btn_files.pack(side="left", padx=5)

        self.btn_single_dir = tk.Button(self.top_frame, text="Select Directory",
                                        command=self.on_select_directory, bg=BG_COLOR)
        self.btn_single_dir.pack(side="left", padx=5)

        self.btn_subfolders = tk.Button(self.top_frame, text="Select Dir with Subfolders",
                                        command=self.on_select_subfolders, bg=BG_COLOR)
        self.btn_subfolders.pack(side="left", padx=5)

        # Subfolder nav
        self.prev_btn = tk.Button(self.top_frame, text="<<",
                                  command=self.on_prev_subfolder, bg=BG_COLOR, state="disabled")
        self.prev_btn.pack(side="left", padx=5)

        self.subfolder_combo = ttk.Combobox(self.top_frame, state="disabled")
        self.subfolder_combo.pack(side="left", padx=5)
        self.subfolder_combo.bind("<<ComboboxSelected>>", self.on_subfolder_changed)

        self.next_btn = tk.Button(self.top_frame, text=">>",
                                  command=self.on_next_subfolder, bg=BG_COLOR, state="disabled")
        self.next_btn.pack(side="left", padx=5)

        # Image size
        tk.Label(self.top_frame, text="Width:", bg=BG_COLOR).pack(side="left", padx=5)
        self.width_entry = tk.Entry(self.top_frame, width=6)
        self.width_entry.insert(0, "3840")
        self.width_entry.pack(side="left", padx=5)

        tk.Label(self.top_frame, text="Height:", bg=BG_COLOR).pack(side="left", padx=5)
        self.height_entry = tk.Entry(self.top_frame, width=6)
        self.height_entry.insert(0, "1080")
        self.height_entry.pack(side="left", padx=5)

        # Calculate & Export
        self.calc_btn = tk.Button(self.top_frame, text="Calculate",
                                  command=self.on_calculate, bg=BG_COLOR)
        self.calc_btn.pack(side="left", padx=5)

        self.export_btn = tk.Button(self.top_frame, text="Export",
                                    command=self.on_export, bg=BG_COLOR)
        self.export_btn.pack(side="left", padx=5)

        # Brightness filter
        tk.Label(self.top_frame, text="Brightness Filter:", bg=BG_COLOR).pack(side="left", padx=5)
        self.brightness_slider = tk.Scale(self.top_frame, from_=0, to=255,
                                          orient='horizontal', bg=BG_COLOR)
        self.brightness_slider.set(0)
        self.brightness_slider.pack(side="left", padx=5)

        self.filter_btn = tk.Button(self.top_frame, text="Filter",
                                    command=self.on_filter, bg=BG_COLOR)
        self.filter_btn.pack(side="left", padx=5)

        self.reset_btn = tk.Button(self.top_frame, text="Reset",
                                   command=self.on_reset, bg=BG_COLOR)
        self.reset_btn.pack(side="left", padx=5)

        # Influence
        tk.Label(self.top_frame, text="Influence (-10..+10):", bg=BG_COLOR).pack(side="left", padx=5)
        self.influence_slider = tk.Scale(self.top_frame, from_=-10, to=10, resolution=1,
                                         orient='horizontal', bg=BG_COLOR)
        self.influence_slider.set(0)
        self.influence_slider.pack(side="left", padx=5)

        # Deviation as percentage
        tk.Label(self.top_frame, text="Max Deviation (%):", bg=BG_COLOR).pack(side="left", padx=5)
        self.damping_slider = tk.Scale(self.top_frame, from_=0, to=50, resolution=1,
                                       orient='horizontal', bg=BG_COLOR)
        self.damping_slider.set(20)
        self.damping_slider.pack(side="left", padx=5)

        # Export checkboxes
        self.export_images_var = tk.BooleanVar(value=True)
        self.export_video_var = tk.BooleanVar(value=False)

        self.img_chk = tk.Checkbutton(self.top_frame, text="Export Images",
                                      variable=self.export_images_var, bg=BG_COLOR)
        self.img_chk.pack(side="left", padx=5)

        self.vid_chk = tk.Checkbutton(self.top_frame, text="Export Video",
                                      variable=self.export_video_var, bg=BG_COLOR)
        self.vid_chk.pack(side="left", padx=5)

        # Status label
        self.status_label = tk.Label(self.root, text="", fg="blue", bg=BG_COLOR)
        self.status_label.pack(side="top", fill="x")

        # Checkbox/data building
        self.checkbox_frame = tk.Frame(self.root, bg=BG_COLOR)
        self.checkbox_frame.pack(side="top", fill="x", pady=5)

        # Canvas display
        self.display_canvas = tk.Canvas(self.root, bg=BG_COLOR)
        self.display_canvas.pack(side="top", fill="both", expand=True)
        self.display_canvas.bind("<Configure>", self.on_canvas_resized)

    # Crossfade logic without separate buttons
    def on_cf_prev(self):
        if not self.crossfade_active or self.crossfade_index <= 0:
            return
        self.crossfade_index -= 1
        self._show_crossfade_frame()

    def on_cf_next(self):
        if not self.crossfade_active or self.crossfade_index >= len(self.crossfade_frames) - 1:
            return
        self.crossfade_index += 1
        self._show_crossfade_frame()

    def _show_crossfade_frame(self):
        if not self.crossfade_frames:
            return
        frame = self.crossfade_frames[self.crossfade_index]
        self._draw_in_canvas(frame)

    # File selection
    def on_select_images(self):
        files = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif")]
        )
        if not files:
            return
        self.set_mode(MODE_FILES)
        sorted_paths = sorted(files, key=FadingLogic.parse_utc_offset)
        self._build_image_data(sorted_paths)
        self.update_navigation()

    def on_select_directory(self):
        folder = filedialog.askdirectory(title="Select Directory")
        if not folder:
            return
        self.set_mode(MODE_SINGLE_DIR)
        found_files = []
        for item in os.listdir(folder):
            if item.lower().endswith("_fading.png"):
                found_files.append(os.path.join(folder, item))
        found_files = sorted(found_files, key=FadingLogic.parse_utc_offset)
        self._build_image_data(found_files)
        self.update_navigation()

    def on_select_subfolders(self):
        folder = filedialog.askdirectory(title="Select Directory (with Subfolders)")
        if not folder:
            return
        self.set_mode(MODE_SUBFOLDERS)
        self.subfolder_names.clear()
        self.subfolder_data.clear()

        subfolders = []
        for item in os.listdir(folder):
            path_sub = os.path.join(folder, item)
            if os.path.isdir(path_sub):
                subfolders.append(item)
        subfolders.sort()

        all_offsets = set()
        for sf in subfolders:
            sp = os.path.join(folder, sf)
            fl = []
            for it in os.listdir(sp):
                if it.lower().endswith("_fading.png"):
                    fl.append(os.path.join(sp, it))
            fl = sorted(fl, key=FadingLogic.parse_utc_offset)
            if not fl:
                continue
            offset_map = {}
            for fpath in fl:
                off_val = FadingLogic.parse_utc_offset(fpath)
                offset_map[off_val] = (fpath, False)
                all_offsets.add(off_val)
            self.subfolder_names.append(sf)
            self.subfolder_data[sf] = offset_map

        if not self.subfolder_names or not all_offsets:
            self.status_label.config(text="No suitable subfolders found.")
            return

        all_offsets_sorted = sorted(list(all_offsets))
        for i, sf in enumerate(self.subfolder_names):
            om = self.subfolder_data[sf]
            new_map = {}
            for off in all_offsets_sorted:
                if off in om:
                    new_map[off] = om[off]
                else:
                    path, is_proxy = FadingLogic.fallback_for_offset(i, off, self.subfolder_names, self.subfolder_data)
                    new_map[off] = (path, is_proxy)
            self.subfolder_data[sf] = new_map

        self.subfolder_combo["values"] = self.subfolder_names
        self.subfolder_combo.current(0)
        self._load_subfolder_images(0, auto_calc=False)
        self.update_navigation()

    # Subfolder navigation
    def on_prev_subfolder(self):
        if self.crossfade_active:
            self.crossfade_active = False
            self.crossfade_frames.clear()
        idx = self.subfolder_combo_idx - 1
        if idx < 0:
            self.prev_btn.config(state="disabled")
            return
        self.subfolder_combo.current(idx)
        self._load_subfolder_images(idx, auto_calc=True)

    def on_next_subfolder(self):
        if self.crossfade_active:
            self.crossfade_active = False
            self.crossfade_frames.clear()
        idx = self.subfolder_combo_idx + 1
        if idx >= len(self.subfolder_names):
            self.next_btn.config(state="disabled")
            return
        self.subfolder_combo.current(idx)
        self._load_subfolder_images(idx, auto_calc=True)

    def on_subfolder_changed(self, evt=None):
        selection = self.subfolder_combo.get()
        if selection in self.subfolder_names:
            idx = self.subfolder_names.index(selection)
            self._load_subfolder_images(idx, auto_calc=True)

    # Calculate
    def on_calculate(self):
        self.crossfade_active = False
        self.crossfade_frames.clear()
        if self.current_mode == MODE_SUBFOLDERS and self.subfolder_names:
            if self.brightness_slider.get() > 0:
                self.on_filter()
            else:
                self._build_fade_core()
        else:
            self._build_fade_core()
        self.update_navigation()

    # Export
    def on_export(self):
        self._build_fade_core()
        out_folder = FadingLogic.get_next_output_subfolder()

        diag = tk.Toplevel(self.root)
        diag.title("Export Options")
        diag.configure(bg=BG_COLOR)

        if self.current_mode == MODE_SUBFOLDERS and len(self.subfolder_names) > 1:
            # Subfolder crossfade
            tk.Label(diag, text="Number of Crossfades:", bg=BG_COLOR).pack(side="top", padx=5, pady=5)
            steps_var = tk.StringVar(value="10")
            steps_entry = tk.Entry(diag, textvariable=steps_var)
            steps_entry.pack(side="top", padx=5, pady=5)

            tk.Label(diag, text="Video FPS:", bg=BG_COLOR).pack(side="top", padx=5, pady=5)
            fps_var = tk.StringVar(value="25")
            fps_entry = tk.Entry(diag, textvariable=fps_var)
            fps_entry.pack(side="top", padx=5, pady=5)

            def on_ok():
                start_time = time.time()
                try:
                    steps_val = int(steps_var.get())
                    fps_val = int(fps_var.get())
                    if steps_val < 1 or fps_val < 1:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("Error", "Please provide valid Steps/FPS.")
                    return

                frames = self._build_global_subfolder_crossfade(steps_val)
                if not frames and self.final_image is None:
                    self.status_label.config(text="No frames built.")
                    diag.destroy()
                    return

                # Export images
                if self.export_images_var.get():
                    for i, frm in enumerate(frames):
                        cv2.imwrite(os.path.join(out_folder, f"global_{i:03d}.png"), frm)

                # Export video
                if self.export_video_var.get():
                    videoname = os.path.join(out_folder, "all_subfolders_crossfade.mp4")
                    FadingLogic.export_mpeg_video(frames, videoname, fps_val)

                end_time = time.time()
                elapsed = end_time - start_time
                self.status_label.config(text=f"Export done => time: {elapsed:.2f}s")
                diag.destroy()

            tk.Button(diag, text="OK", command=on_ok, bg=BG_COLOR).pack(side="top", padx=5, pady=5)

        else:
            # Single fade
            tk.Label(diag, text="Video FPS:", bg=BG_COLOR).pack(side="top", padx=5, pady=5)
            fps_var = tk.StringVar(value="25")
            fps_entry = tk.Entry(diag, textvariable=fps_var)
            fps_entry.pack(side="top", padx=5, pady=5)

            def on_ok():
                start_time = time.time()
                try:
                    fps_val = int(fps_var.get())
                    if fps_val < 1:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("Error", "Please provide a valid FPS.")
                    return

                if self.final_image is None:
                    self.status_label.config(text="No fade to export.")
                    diag.destroy()
                    return

                # Single image
                if self.export_images_var.get():
                    cv2.imwrite(os.path.join(out_folder, "single_horizontalfading.png"), self.final_image)

                # Video
                if self.export_video_var.get():
                    frames = [self.final_image] * fps_val
                    videoname = os.path.join(out_folder, "single_horizontalfading.mp4")
                    FadingLogic.export_mpeg_video(frames, videoname, fps_val)

                end_time = time.time()
                elapsed = end_time - start_time
                self.status_label.config(text=f"Export done => time: {elapsed:.2f}s")
                diag.destroy()

    def on_filter(self):
        self._reset_checkboxes()
        threshold = self.brightness_slider.get()
        for data_item in self.image_data:
            if data_item.brightness_value < threshold:
                data_item.check_var.set(False)
        self.status_label.config(text=f"Filtered < {threshold}, building fade.")
        self._build_fade_core()

    def on_reset(self):
        self.brightness_slider.set(0)
        for data_item in self.image_data:
            data_item.check_var.set(True)
        self.status_label.config(text="All checkboxes enabled. Recalculating.")
        self._build_fade_core()

    # Build fade
    def _build_fade_core(self):
        self.crossfade_active = False
        self.crossfade_frames.clear()

        active_paths = []
        brightness_list = []
        proxy_list = []
        for data_item in self.image_data:
            if data_item.check_var.get():
                active_paths.append(data_item.file_path)
                brightness_list.append(data_item.brightness_value)
                proxy_list.append(data_item.is_proxy)

        if len(active_paths) < 2:
            self.status_label.config(text="Not enough checked images.")
            self.final_image = None
            self.boundary_positions = []
            self.filenames_at_boundaries = []
            self._redraw_canvas()
            return

        # Validate width/height
        try:
            width_total = int(self.width_entry.get())
            height_total = int(self.height_entry.get())
            if width_total < 10 or height_total < 10:
                raise ValueError
        except ValueError:
            self.status_label.config(text="Width/Height error.")
            return

        final_result = np.zeros((height_total, width_total, 3), dtype=np.uint8)
        bounds = []
        filenames = []
        t0 = time.time()
        average_colors = []

        # Prepare color slices
        for path in active_paths:
            img = cv2.imread(path)
            if img is None:
                dummy = np.zeros((10, 10, 3), dtype=np.uint8)
                ratio = height_total / 10
                new_w = max(1, int(10 * ratio))
                resized = cv2.resize(dummy, (new_w, height_total))
                avg = FadingLogic.calculate_horizontal_average(resized)
                average_colors.append(avg)
            else:
                ratio = height_total / img.shape[0]
                new_w = max(1, int(img.shape[1] * ratio))
                resized = cv2.resize(img, (new_w, height_total))
                avg = FadingLogic.calculate_horizontal_average(resized)
                average_colors.append(avg)

        # Compute transitions
        influence_val = float(self.influence_slider.get())
        transitions = []
        original_transitions = []
        n = len(average_colors)

        for i in range(n - 1):
            ab = (brightness_list[i] + brightness_list[i + 1]) / 2.0
            original_weight = 1.0
            if influence_val == 0:
                weight = 1.0
            else:
                safe_bright = max(1, ab)
                weight = safe_bright ** influence_val
                if weight < 1e-6:
                    weight = 0
            transitions.append(weight)
            original_transitions.append(original_weight)

        total_w = sum(transitions)
        if total_w <= 0:
            self.status_label.config(text="All transitions zero => no fade.")
            self.final_image = None
            self.boundary_positions = []
            self.filenames_at_boundaries = []
            self._redraw_canvas()
            return

        # Deviation as percentage
        damping_percent = self.damping_slider.get()
        sum_orig = sum(original_transitions)

        x_start = 0
        for i in range(n - 1):
            w_i = transitions[i]
            fname = os.path.basename(active_paths[i])
            is_proxy_flag = proxy_list[i]
            if w_i <= 0:
                bounds.append(x_start)
                filenames.append((fname, is_proxy_flag))
                continue

            frac_influenced = w_i / total_w
            frac_original = original_transitions[i] / sum_orig

            influenced_width_px = int(round(width_total * frac_influenced))
            original_width_px = int(round(width_total * frac_original))

            diff = influenced_width_px - original_width_px
            max_shift = int(round(original_width_px * (damping_percent / 100.0)))

            if abs(diff) > max_shift:
                if diff > 0:
                    influenced_width_px = original_width_px + max_shift
                else:
                    influenced_width_px = original_width_px - max_shift

            seg_w = influenced_width_px
            x_end = x_start + seg_w
            if i == (n - 2):
                x_end = width_total
            if x_end > width_total:
                x_end = width_total
            if x_end <= x_start:
                bounds.append(x_start)
                filenames.append((fname, is_proxy_flag))
                continue

            grad = FadingLogic.generate_fading_gradient(average_colors[i], average_colors[i+1], x_end - x_start)
            final_result[:, x_start:x_end] = grad
            bounds.append(x_start)
            filenames.append((fname, is_proxy_flag))
            x_start = x_end

        last_name = os.path.basename(active_paths[-1])
        last_proxy = proxy_list[-1]
        bounds.append(width_total - 1)
        filenames.append((last_name, last_proxy))

        self.final_image = final_result
        self.boundary_positions = bounds
        self.filenames_at_boundaries = filenames
        elapsed = round(time.time() - t0, 2)
        self.status_label.config(text=f"Processing complete in {elapsed}s. Used {len(active_paths)} images.")
        self._redraw_canvas()

    def _build_global_subfolder_crossfade(self, steps: int) -> list:
        frames = []
        n_sub = len(self.subfolder_names)
        if n_sub < 1:
            return []
        prev_img = None
        for i, sf in enumerate(self.subfolder_names):
            self._load_subfolder_images(i, auto_calc=False)
            if self.brightness_slider.get() > 0:
                self.on_filter()
            else:
                self._build_fade_core()
            if self.final_image is None:
                continue
            current = self.final_image.copy()
            if prev_img is None:
                frames.append(current)
            else:
                seq = FadingLogic.build_crossfade_sequence(prev_img, current, steps)
                for k in range(1, len(seq)):
                    frames.append(seq[k])
            prev_img = current
        return frames

    def _calc_brightness(self, filepath: str) -> int:
        img = cv2.imread(filepath)
        if img is None:
            return 0
        return int(round(np.mean(img)))

    # Checkbox/data building
    def _build_image_data(self, filepaths):
        for widget in self.checkbox_frame.winfo_children():
            widget.destroy()
        self.image_data.clear()

        total_files = len(filepaths)
        if total_files == 0:
            return

        self.checkbox_frame.columnconfigure(tuple(range(total_files)), weight=1)
        for idx, fp in enumerate(filepaths):
            selected_var = tk.BooleanVar(value=True)
            brightness_value = self._calc_brightness(fp)
            offset_value = FadingLogic.parse_utc_offset(fp)

            filename = os.path.basename(fp)
            prefix = filename.split("_", 1)[0]

            frame_card = tk.Frame(self.checkbox_frame, bg=BG_COLOR, bd=1, relief="solid")
            frame_card.grid(row=0, column=idx, padx=5, pady=5, sticky="ew")

            cb = tk.Checkbutton(frame_card, variable=selected_var, bg=BG_COLOR)
            cb.pack(side="top", anchor="center")

            lb_name = tk.Label(frame_card, text=prefix, bg=BG_COLOR)
            lb_name.pack(side="top")

            lb_bright = tk.Label(frame_card, text=str(brightness_value), bg=BG_COLOR)
            lb_bright.pack(side="top")

            self.image_data.append(
                ImageData(
                    file_path=fp,
                    check_var=selected_var,
                    brightness_value=brightness_value,
                    offset=offset_value,
                    is_proxy=False
                )
            )

    def _load_subfolder_images(self, idx, auto_calc=True):
        self.subfolder_combo_idx = idx
        for widget in self.checkbox_frame.winfo_children():
            widget.destroy()
        self.image_data.clear()

        sf = self.subfolder_names[idx]
        offset_map = self.subfolder_data[sf]
        file_info = []
        for off_val, (fp, px) in offset_map.items():
            file_info.append((fp, px, off_val))
        file_info.sort(key=lambda x: x[2])

        total_files = len(file_info)
        if total_files == 0:
            return

        self.checkbox_frame.columnconfigure(tuple(range(total_files)), weight=1)
        for col_idx, (fp, px, off_val) in enumerate(file_info):
            selected_var = tk.BooleanVar(value=True)
            brightness_val = self._calc_brightness(fp)
            filename = os.path.basename(fp)
            prefix = filename.split("_", 1)[0]

            frame_card = tk.Frame(self.checkbox_frame, bg=BG_COLOR, bd=1, relief="solid")
            frame_card.grid(row=0, column=col_idx, padx=5, pady=5, sticky="ew")

            cb = tk.Checkbutton(frame_card, variable=selected_var, bg=BG_COLOR)
            cb.pack(side="top", anchor="center")

            lb_name = tk.Label(frame_card, text=prefix, bg=BG_COLOR)
            lb_name.pack(side="top")

            lb_bright = tk.Label(frame_card, text=str(brightness_val), bg=BG_COLOR)
            lb_bright.pack(side="top")

            self.image_data.append(
                ImageData(
                    file_path=fp,
                    check_var=selected_var,
                    brightness_value=brightness_val,
                    offset=off_val,
                    is_proxy=px
                )
            )

        if auto_calc:
            if self.brightness_slider.get() > 0:
                self.on_filter()
            else:
                self._build_fade_core()
        self.update_navigation()

    def _reset_checkboxes(self):
        for data_item in self.image_data:
            data_item.check_var.set(True)

    def _draw_in_canvas(self, bgr_image):
        self.display_canvas.delete("all")
        cw = self.display_canvas.winfo_width()
        ch = self.display_canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        oh, ow, _ = bgr_image.shape

        scale = cw / ow
        disp_h = int(oh * scale)
        if disp_h > ch:
            scale = ch / oh
            disp_h = ch
        disp_w = int(ow * scale)

        scaled = cv2.resize(bgr_image, (disp_w, disp_h))
        disp_rgb = cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(disp_rgb)
        photo_img = ImageTk.PhotoImage(pil_img)
        self.display_canvas.create_image(0, 0, anchor="nw", image=photo_img)
        self.display_canvas.image = photo_img

    def on_canvas_resized(self, event=None):
        self._redraw_canvas()

    def _redraw_canvas(self):
        if self.final_image is None:
            self.display_canvas.delete("all")
            return
        cw = self.display_canvas.winfo_width()
        ch = self.display_canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        self.display_canvas.delete("all")
        self.display_canvas.txt_refs = []

        oh, ow, _ = self.final_image.shape
        scale = cw / ow
        disp_h = int(oh * scale)
        if disp_h > ch:
            scale = ch / oh
            disp_h = ch
        disp_w = int(ow * scale)

        scaled = cv2.resize(self.final_image, (disp_w, disp_h))
        disp_rgb = cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(disp_rgb)
        photo_img = ImageTk.PhotoImage(pil_img)
        self.display_canvas.create_image(0, 0, anchor="nw", image=photo_img)
        self.display_canvas.image = photo_img

        try:
            font = ImageFont.truetype("arial.ttf", TEXT_FONT_SIZE)
        except:
            font = ImageFont.load_default()

        for i, (x_off, (fname, is_proxy)) in enumerate(zip(self.boundary_positions, self.filenames_at_boundaries)):
            x_scaled = int(x_off * scale)
            if i == len(self.boundary_positions) - 1:
                x_scaled = max(0, x_scaled - 40)

            color = (255, 0, 0) if is_proxy else (0, 0, 0)
            tmp_img = Image.new("RGBA", (1, 1), TEXT_BG_COLOR)
            d = ImageDraw.Draw(tmp_img)
            bbox = d.textbbox((0, 0), fname, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            box_w = tw + 20
            box_h = th + 20
            label_img = Image.new("RGBA", (box_w, box_h), TEXT_BG_COLOR)
            dd = ImageDraw.Draw(label_img)
            dd.text((10, 10), fname, font=font, fill=color)
            rotated = label_img.rotate(90, expand=True)
            rph = ImageTk.PhotoImage(rotated)
            y_bottom = ch
            self.display_canvas.create_image(x_scaled, y_bottom, anchor="sw", image=rph)
            self.display_canvas.txt_refs.append(rph)

    def set_mode(self, mode):
        self.current_mode = mode
        self.subfolder_combo_idx = 0
        self.update_navigation()

    def update_navigation(self):
        if self.current_mode == MODE_SUBFOLDERS and len(self.subfolder_names) > 1:
            self.subfolder_combo.config(state="readonly")
            if self.subfolder_combo_idx > 0:
                self.prev_btn.config(state="normal")
            else:
                self.prev_btn.config(state="disabled")
            if self.subfolder_combo_idx < len(self.subfolder_names) - 1:
                self.next_btn.config(state="normal")
            else:
                self.next_btn.config(state="disabled")
        else:
            self.subfolder_combo.config(state="disabled")
            self.prev_btn.config(state="disabled")
            self.next_btn.config(state="disabled")

        if self.crossfade_active:
            pass

        c = len(self.image_data)
        if self.current_mode == MODE_SUBFOLDERS and self.subfolder_names:
            if self.subfolder_combo_idx < len(self.subfolder_names):
                sf = self.subfolder_names[self.subfolder_combo_idx]
                self.status_label.config(text=f"Subfolder '{sf}': {c} images.")
            else:
                self.status_label.config(text=f"{c} images in subfolder idx {self.subfolder_combo_idx}")
        else:
            self.status_label.config(text=f"{c} images loaded.")
