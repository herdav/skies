import os
import time
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import cv2
from PIL import Image, ImageTk, ImageDraw, ImageFont
from typing import List
from datamodel import ImageData, SubfolderFadeData, FadeParams
import fading
from datetime import datetime
import multiprocessing

BG_COLOR = "#dcdcdc"
TEXT_BG_COLOR = (220, 220, 220, 255)
TEXT_FONT_SIZE = 12

MODE_NONE = 0
MODE_FILES = 1
MODE_SINGLE_DIR = 2
MODE_SUBFOLDERS = 3

DEFAULT_GAMMA = 2
DEFAULT_DAMPING = 100
DEFAULT_INFLUENCE = 4.0
DEFAULT_CROSSFADES = 100


class FadingUI:
    def __init__(self, root: tk.Tk):
        """
        Initializes the main window and state.
        """
        self.root = root
        self.root.title("Horizontal Fading")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry("1400x750")

        self.ffmpeg_path = r"C:\ffmpeg\bin\ffmpeg.exe"

        self.current_mode = MODE_NONE
        self.image_data: List[ImageData] = []

        self.subfolder_names = []
        self.subfolder_data = {}
        self.subfolder_combo_idx = 0
        self.subfolder_fade_info = {}

        self.final_image = None
        self.boundary_positions = []
        self.filenames_at_boundaries = []

        # Simple cache for single fade usage
        self._last_fade_cache = {
            "active_paths": None,
            "brightness_list": None,
            "proxy_list": None,
            "width": None,
            "height": None,
            "gamma": None,
            "influence": None,
            "damping": None,
            "result": None,
        }

        self._setup_ui()

    def _setup_ui(self):
        # First row
        self.top_frame_1 = tk.Frame(self.root, bg=BG_COLOR)
        self.top_frame_1.pack(side="top", fill="x", pady=5)

        self.btn_files = tk.Button(
            self.top_frame_1, text="Files", command=self.select_images, bg=BG_COLOR
        )
        self.btn_files.pack(side="left", padx=5)

        self.btn_single_dir = tk.Button(
            self.top_frame_1,
            text="Directory",
            command=self.select_directory,
            bg=BG_COLOR,
        )
        self.btn_single_dir.pack(side="left", padx=5)

        self.btn_subfolders = tk.Button(
            self.top_frame_1,
            text="Dir Subfolders",
            command=self.select_subfolders,
            bg=BG_COLOR,
        )
        self.btn_subfolders.pack(side="left", padx=5)

        self.prev_btn = tk.Button(
            self.top_frame_1,
            text="<<",
            command=self.prev_subfolder,
            bg=BG_COLOR,
            state="disabled",
        )
        self.prev_btn.pack(side="left", padx=5)

        self.subfolder_combo = ttk.Combobox(self.top_frame_1, state="disabled")
        self.subfolder_combo.pack(side="left", padx=5)
        self.subfolder_combo.bind(
            "<<ComboboxSelected>>", self.subfolder_changed)

        self.next_btn = tk.Button(
            self.top_frame_1,
            text=">>",
            command=self.next_subfolder,
            bg=BG_COLOR,
            state="disabled",
        )
        self.next_btn.pack(side="left", padx=5)

        self.calc_btn = tk.Button(
            self.top_frame_1, text="Calculate", command=self.calculate_fade, bg=BG_COLOR
        )
        self.calc_btn.pack(side="left", padx=5)

        self.export_current_btn = tk.Button(
            self.top_frame_1,
            text="Export Current",
            command=self.export_current_image,
            bg=BG_COLOR,
        )
        self.export_current_btn.pack(side="left", padx=5)

        self.export_video_btn = tk.Button(
            self.top_frame_1,
            text="Export Video",
            command=self.export_video,
            bg=BG_COLOR,
        )
        self.export_video_btn.pack(side="left", padx=5)

        self.ffmpeg_btn = tk.Button(
            self.top_frame_1,
            text="Path to FFmpeg",
            command=self.set_ffmpeg_executable,
            bg=BG_COLOR,
        )
        self.ffmpeg_btn.pack(side="left", padx=5)

        self.quit_btn = tk.Button(
            self.top_frame_1, text="Quit", command=self.on_quit, bg=BG_COLOR
        )
        self.quit_btn.pack(side="left", padx=5)

        # Second row
        self.top_frame_2 = tk.Frame(self.root, bg=BG_COLOR)
        self.top_frame_2.pack(side="top", fill="x", pady=5)

        tk.Label(self.top_frame_2, text="Width:",
                 bg=BG_COLOR).pack(side="left", padx=5)
        self.width_entry = tk.Entry(self.top_frame_2, width=6)
        self.width_entry.insert(0, "3840")
        self.width_entry.pack(side="left", padx=5)

        tk.Label(self.top_frame_2, text="Height:", bg=BG_COLOR).pack(
            side="left", padx=5
        )
        self.height_entry = tk.Entry(self.top_frame_2, width=6)
        self.height_entry.insert(0, "720")
        self.height_entry.pack(side="left", padx=5)

        tk.Label(self.top_frame_2, text="Brightness:", bg=BG_COLOR).pack(
            side="left", padx=5
        )
        self.brightness_slider = tk.Scale(
            self.top_frame_2, from_=0, to=255, orient="horizontal", bg=BG_COLOR
        )
        self.brightness_slider.set(0)
        self.brightness_slider.pack(side="left", padx=5)

        self.filter_btn = tk.Button(
            self.top_frame_2, text="Filter", command=self.filter_brightness, bg=BG_COLOR
        )
        self.filter_btn.pack(side="left", padx=5)

        self.reset_btn = tk.Button(
            self.top_frame_2, text="Reset", command=self.reset_filter_brightness, bg=BG_COLOR
        )
        self.reset_btn.pack(side="left", padx=5)

        tk.Label(self.top_frame_2, text="Gamma:",
                 bg=BG_COLOR).pack(side="left", padx=5)
        self.gamma_entry = tk.Entry(self.top_frame_2, width=4)
        self.gamma_entry.insert(0, str(DEFAULT_GAMMA))
        self.gamma_entry.pack(side="left", padx=5)

        tk.Label(self.top_frame_2, text="Influence:", bg=BG_COLOR).pack(
            side="left", padx=5
        )
        self.influence_slider = tk.Scale(
            self.top_frame_2,
            from_=-4,
            to=10,
            resolution=1,
            orient="horizontal",
            bg=BG_COLOR,
        )
        self.influence_slider.set(DEFAULT_INFLUENCE)
        self.influence_slider.pack(side="left", padx=5)

        tk.Label(self.top_frame_2, text="Damping:",
                 bg=BG_COLOR).pack(side="left", padx=5)
        self.damping_entry = tk.Entry(self.top_frame_2, width=6)
        self.damping_entry.insert(0, str(DEFAULT_DAMPING))
        self.damping_entry.pack(side="left", padx=5)

        self.status_label = tk.Label(
            self.root, text="", fg="blue", bg=BG_COLOR)
        self.status_label.pack(side="top", fill="x")

        self.checkbox_frame = tk.Frame(self.root, bg=BG_COLOR)
        self.checkbox_frame.pack(side="top", fill="x", pady=5)

        self.display_canvas = tk.Canvas(self.root, bg=BG_COLOR)
        self.display_canvas.pack(side="top", fill="both", expand=True)
        self.display_canvas.bind("<Configure>", self.canvas_resized)

    def on_quit(self):
        self.root.destroy()

    def set_ffmpeg_executable(self):
        """Pick ffmpeg.exe, store in self.ffmpeg_path."""
        path = filedialog.askopenfilename(
            title="Select ffmpeg.exe", filetypes=[("exe", "*.exe"), ("All", "*.*")]
        )
        if path:
            self.ffmpeg_path = path

    # ------------- Subfolder Nav -----------
    def prev_subfolder(self):
        idx = self.subfolder_combo_idx - 1
        if idx < 0:
            self.prev_btn.config(state="disabled")
            return
        self.subfolder_combo.current(idx)
        self._create_subfolder_cards(idx, auto_calc=True)

    def next_subfolder(self):
        idx = self.subfolder_combo_idx + 1
        if idx >= len(self.subfolder_names):
            self.next_btn.config(state="disabled")
            return
        self.subfolder_combo.current(idx)
        self._create_subfolder_cards(idx, auto_calc=True)

    def subfolder_changed(self, evt=None):
        val = self.subfolder_combo.get()
        if val in self.subfolder_names:
            idx = self.subfolder_names.index(val)
            self._create_subfolder_cards(idx, auto_calc=True)

    def set_mode(self, mode):
        self.current_mode = mode
        self.subfolder_combo_idx = 0

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

        c = len(self.image_data)
        if self.current_mode == MODE_SUBFOLDERS and self.subfolder_names:
            if self.subfolder_combo_idx < len(self.subfolder_names):
                sf = self.subfolder_names[self.subfolder_combo_idx]
                self.status_label.config(text=f"Subfolder '{sf}': {c} images.")
            else:
                self.status_label.config(
                    text=f"{c} images in subfolder idx={self.subfolder_combo_idx}"
                )
        else:
            self.status_label.config(text=f"{c} images loaded.")

    # -------------- FILE / DIR --------------
    def select_images(self):
        files = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[
                ("Image Files", "*.png *.jpg *.jpeg *.bmp *.tiff *.tif")],
        )
        if not files:
            return
        self.set_mode(MODE_FILES)
        sorted_paths = sorted(files, key=fading.FadingLogic.parse_utc_offset)
        self._create_image_cards(sorted_paths)
        self.update_navigation()
        self.calculate_fade()

    def select_directory(self):
        folder = filedialog.askdirectory(title="Select Directory")
        if not folder:
            return
        self.set_mode(MODE_SINGLE_DIR)
        found = []
        for it in os.listdir(folder):
            if it.lower().endswith("_fading.png"):
                found.append(os.path.join(folder, it))
        found = sorted(found, key=fading.FadingLogic.parse_utc_offset)
        self._create_image_cards(found)
        self.update_navigation()
        self.calculate_fade()

    def select_subfolders(self):
        folder = filedialog.askdirectory(
            title="Select Directory (with Subfolders)")
        if not folder:
            return
        self.set_mode(MODE_SUBFOLDERS)
        self.subfolder_names.clear()
        self.subfolder_data.clear()

        subs = []
        for it in os.listdir(folder):
            p_sub = os.path.join(folder, it)
            if os.path.isdir(p_sub):
                subs.append(it)
        subs.sort()

        all_offsets = set()
        for sf in subs:
            sp = os.path.join(folder, sf)
            fl = []
            for itm in os.listdir(sp):
                if itm.lower().endswith("_fading.png"):
                    fl.append(os.path.join(sp, itm))
            fl = sorted(fl, key=fading.FadingLogic.parse_utc_offset)
            if not fl:
                continue
            om = {}
            for fpath in fl:
                off_val = fading.FadingLogic.parse_utc_offset(fpath)
                om[off_val] = (fpath, False)
                all_offsets.add(off_val)
            self.subfolder_names.append(sf)
            self.subfolder_data[sf] = om

        if not self.subfolder_names or not all_offsets:
            self.status_label.config(text="No suitable subfolders found.")
            return

        all_off_sorted = sorted(list(all_offsets))
        for i, sf in enumerate(self.subfolder_names):
            om = self.subfolder_data[sf]
            new_map = {}
            for off in all_off_sorted:
                if off in om:
                    new_map[off] = om[off]
                else:
                    path, px = fading.FadingLogic.fallback_for_offset(
                        i, off, self.subfolder_names, self.subfolder_data
                    )
                    new_map[off] = (path, px)
            self.subfolder_data[sf] = new_map

        self.subfolder_combo["values"] = self.subfolder_names
        self.subfolder_combo.current(0)
        self._create_subfolder_cards(0, auto_calc=False)
        self.update_navigation()
        self.calculate_fade()

    # -------------- CREATE CHECKBOX --------------
    def _create_subfolder_cards(self, idx, auto_calc=True):
        for w in self.checkbox_frame.winfo_children():
            w.destroy()
        self.image_data.clear()

        self.subfolder_combo_idx = idx
        sf = self.subfolder_names[idx]
        off_map = self.subfolder_data[sf]
        fi = []
        for off_val, (fp, px) in off_map.items():
            fi.append((fp, px, off_val))
        fi.sort(key=lambda x: x[2])
        if not fi:
            return

        gamma_val = self._get_gamma()
        self.checkbox_frame.columnconfigure(tuple(range(len(fi))), weight=1)

        for col_idx, (fp, px, offv) in enumerate(fi):
            var = tk.BooleanVar(value=True)
            br = fading.ImageHelper.calculate_brightness(fp, gamma_val)
            filename = os.path.basename(fp)
            prefix = filename.split("_", 1)[0]

            frame_card = tk.Frame(
                self.checkbox_frame, bg=BG_COLOR, bd=1, relief="solid"
            )
            frame_card.grid(row=0, column=col_idx, padx=5, pady=5, sticky="ew")

            cb = tk.Checkbutton(frame_card, variable=var, bg=BG_COLOR)
            cb.pack(side="top", anchor="center")

            lb_name = tk.Label(frame_card, text=prefix, bg=BG_COLOR)
            lb_name.pack(side="top")

            lb_bright = tk.Label(frame_card, text=str(br), bg=BG_COLOR)
            lb_bright.pack(side="top")

            self.image_data.append(
                ImageData(
                    file_path=fp,
                    check_var=var,
                    brightness_value=br,
                    offset=offv,
                    is_proxy=px,
                )
            )
        if auto_calc:
            if self.brightness_slider.get() > 0:
                self.filter_brightness()
            else:
                self.calculate_fade()
        self.update_navigation()

    def _create_image_cards(self, filepaths: List[str]):
        for w in self.checkbox_frame.winfo_children():
            w.destroy()
        self.image_data.clear()

        if not filepaths:
            return
        gamma_val = self._get_gamma()
        self.checkbox_frame.columnconfigure(
            tuple(range(len(filepaths))), weight=1)

        for idx, fp in enumerate(filepaths):
            var = tk.BooleanVar(value=True)
            brv = fading.ImageHelper.calculate_brightness(fp, gamma_val)
            offv = fading.FadingLogic.parse_utc_offset(fp)
            filename = os.path.basename(fp)
            prefix = filename.split("_", 1)[0]

            frame_card = tk.Frame(
                self.checkbox_frame, bg=BG_COLOR, bd=1, relief="solid"
            )
            frame_card.grid(row=0, column=idx, padx=5, pady=5, sticky="ew")

            cb = tk.Checkbutton(frame_card, variable=var, bg=BG_COLOR)
            cb.pack(side="top", anchor="center")

            lb_name = tk.Label(frame_card, text=prefix, bg=BG_COLOR)
            lb_name.pack(side="top")

            lb_bright = tk.Label(frame_card, text=str(brv), bg=BG_COLOR)
            lb_bright.pack(side="top")

            self.image_data.append(
                ImageData(
                    file_path=fp,
                    check_var=var,
                    brightness_value=brv,
                    offset=offv,
                    is_proxy=False,
                )
            )

    def _get_gamma(self):
        try:
            val = float(self.gamma_entry.get())
            if val <= 0:
                raise ValueError
            return val
        except ValueError:
            return 2.0

    # ------------- Calculation / Filter / Reset -------------
    def calculate_fade(self):
        start_t = time.time()
        self._recalc_brightness()
        self._run_fade_calculation()
        el = time.time() - start_t
        # convert to min s style
        mins = int(el // 60)
        secs = int(el % 60)
        if mins > 0:
            self.status_label.config(
                text=f"Calculation done in {mins}min {secs}s.")
        else:
            self.status_label.config(text=f"Calculation done in {secs}s.")

    def _recalc_brightness(self):
        gv = self._get_gamma()
        for d in self.image_data:
            d.brightness_value = fading.ImageHelper.calculate_brightness(
                d.file_path, gv
            )

    def filter_brightness(self):
        start_t = time.time()
        thr = self.brightness_slider.get()
        self._select_all_checkboxes()
        for d in self.image_data:
            if d.brightness_value < thr:
                d.check_var.set(False)
        self._run_fade_calculation()
        el = time.time() - start_t
        mins = int(el // 60)
        secs = int(el % 60)
        if mins > 0:
            self.status_label.config(
                text=f"Filtered < {thr} in {mins}min {secs}s.")
        else:
            self.status_label.config(text=f"Filtered < {thr} in {secs}s.")

    def reset_filter_brightness(self):
        self.brightness_slider.set(0)
        self._select_all_checkboxes()
        self.calculate_fade()
        self.status_label.config(text="Filter reset, fade recalculated.")

    def _select_all_checkboxes(self):
        for d in self.image_data:
            d.check_var.set(True)

    def _run_fade_calculation(self):
        active_paths = []
        br_list = []
        px_list = []
        for d in self.image_data:
            if d.check_var.get():
                active_paths.append(d.file_path)
                br_list.append(d.brightness_value)
                px_list.append(d.is_proxy)

        if len(active_paths) < 2:
            self.final_image = None
            self.boundary_positions = []
            self.filenames_at_boundaries = []
            self._draw_canvas()
            self.status_label.config(text="Not enough checked images.")
            return

        try:
            w_ = int(self.width_entry.get())
            h_ = int(self.height_entry.get())
            if w_ < 10 or h_ < 10:
                raise ValueError
        except ValueError:
            self.status_label.config(text="Width/Height error.")
            return

        gam = float(self.gamma_entry.get())
        inf = float(self.influence_slider.get())
        dam = float(self.damping_entry.get())

        c = self._last_fade_cache
        same_input = (
            c["active_paths"] == tuple(active_paths)
            and c["brightness_list"] == tuple(br_list)
            and c["proxy_list"] == tuple(px_list)
            and c["width"] == w_
            and c["height"] == h_
            and c["gamma"] == gam
            and c["influence"] == inf
            and c["damping"] == dam
        )
        if same_input and c["result"] is not None:
            (
                self.final_image,
                self.boundary_positions,
                self.filenames_at_boundaries,
                avgc,
            ) = c["result"]
            self._draw_canvas()
            return

        fpar = FadeParams(width=w_, height=h_, gamma=gam,
                          influence=inf, damping=dam)
        res = fading.FadingLogic.build_horizontal_fade(
            active_paths, br_list, px_list, fpar)
        if not res:
            self.final_image = None
            self.boundary_positions = []
            self.filenames_at_boundaries = []
            self._draw_canvas()
            return
        (
            self.final_image,
            self.boundary_positions,
            self.filenames_at_boundaries,
            avgcols,
        ) = res

        if self.current_mode == MODE_SUBFOLDERS and self.subfolder_names:
            if self.subfolder_combo_idx < len(self.subfolder_names):
                sf = self.subfolder_names[self.subfolder_combo_idx]
                from datamodel import SubfolderFadeData

                fdat = SubfolderFadeData(
                    final_image=self.final_image,
                    boundary_positions=self.boundary_positions[:],
                    filenames_at_boundaries=self.filenames_at_boundaries[:],
                    average_colors=avgcols[:],
                    transitions=[],
                )
                self.subfolder_fade_info[sf] = fdat

        c["active_paths"] = tuple(active_paths)
        c["brightness_list"] = tuple(br_list)
        c["proxy_list"] = tuple(px_list)
        c["width"] = w_
        c["height"] = h_
        c["gamma"] = gam
        c["influence"] = inf
        c["damping"] = dam
        c["result"] = (
            self.final_image,
            self.boundary_positions,
            self.filenames_at_boundaries,
            avgcols,
        )
        self._draw_canvas()

    # ------------- Export Current -------------
    def export_current_image(self):
        if self.final_image is None:
            self.status_label.config(text="No fade to export.")
            return
        out_folder = "output"
        if not os.path.exists(out_folder):
            os.makedirs(out_folder)
        now_s = datetime.now().strftime("%Y%m%d_%H%M%S")
        gam_ = self.gamma_entry.get()
        inf_ = self.influence_slider.get()
        dam_ = self.damping_entry.get()
        ftag = f"{now_s}_fading_g{gam_}i{inf_}d{dam_}"
        png_name = os.path.join(out_folder, f"{ftag}_current.png")
        cv2.imwrite(png_name, self.final_image)
        self.status_label.config(text=f"Exported current => {png_name}")

    # ------------- Export Video -------------
    def export_video(self):
        """
        Opens a dialog to configure crossfade-video export.
        It prompts for number of crossfades, FPS, frames per batch, workers, 
        delete-chunks option, and now also 'Ghost Frames'.
        """

        if self.current_mode != MODE_SUBFOLDERS or len(self.subfolder_names) < 2:
            self.status_label.config(
                text="Need multiple subfolders for global approach."
            )
            return

        diag = tk.Toplevel(self.root)
        diag.title("Export")
        diag.configure(bg=BG_COLOR)

        # --- Steps (Crossfades) ---
        tk.Label(diag, text="Number of Crossfades:", bg=BG_COLOR).pack(
            side="top", padx=5, pady=5
        )
        steps_var = tk.StringVar(value=str(DEFAULT_CROSSFADES))
        steps_entry = tk.Entry(diag, textvariable=steps_var)
        steps_entry.pack(side="top", padx=5, pady=5)

        # --- FPS ---
        tk.Label(diag, text="Frames per Second:", bg=BG_COLOR).pack(
            side="top", padx=5, pady=5
        )
        fps_var = tk.StringVar(value="25")
        fps_entry = tk.Entry(diag, textvariable=fps_var)
        fps_entry.pack(side="top", padx=5, pady=5)

        # --- Frames per Batch ---
        tk.Label(diag, text="Frames per Chunk:", bg=BG_COLOR).pack(
            side="top", padx=5, pady=5
        )
        batch_var = tk.StringVar(value="1000")
        batch_entry = tk.Entry(diag, textvariable=batch_var)
        batch_entry.pack(side="top", padx=5, pady=5)

        # --- Ghost Frames ---
        tk.Label(diag, text="Ghost Frames:", bg=BG_COLOR).pack(
            side="top", padx=5, pady=5
        )
        ghost_var = tk.StringVar(value="3")
        ghost_entry = tk.Entry(diag, textvariable=ghost_var)
        ghost_entry.pack(side="top", padx=5, pady=5)

        # --- Workers ---
        tk.Label(diag, text="Workers:", bg=BG_COLOR).pack(
            side="top", padx=5, pady=5
        )
        max_cpu = multiprocessing.cpu_count()
        worker_slider = tk.Scale(
            diag,
            from_=1,
            to=max_cpu,
            orient="horizontal",
            resolution=1,
            bg=BG_COLOR
        )
        # Set a default (for example 8) if 8 <= max_cpu, otherwise max_cpu
        default_workers = 8 if 8 <= max_cpu else max_cpu
        worker_slider.set(default_workers)
        worker_slider.pack(side="top", padx=5, pady=5)

        prog_frame = tk.Frame(diag, bg=BG_COLOR)
        prog_frame.pack(side="top", fill="x", padx=10, pady=10)
        tk.Label(prog_frame, text="Progress:", bg=BG_COLOR).pack(
            side="top", padx=5, pady=2
        )
        progress_bar = ttk.Progressbar(
            prog_frame, length=300, mode="determinate"
        )

        delete_var = tk.BooleanVar(value=True)
        delete_chk = tk.Checkbutton(
            diag, text="Delete chunks after merge?", variable=delete_var, bg=BG_COLOR
        )
        delete_chk.pack(side="top", padx=5, pady=5)

        progress_bar.pack(side="top", padx=10, pady=2)

        def on_ok():
            start_export = time.time()
            try:
                steps_val = int(steps_var.get())
                fps_val = int(fps_var.get())
                frames_val = int(batch_var.get())
                workers_val = int(worker_slider.get())
                ghost_val = int(ghost_var.get())
                if steps_val < 1 or fps_val < 1 or frames_val < 1 or workers_val < 1 or ghost_val < 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Error", "Invalid steps/fps/frames-batch/worker/ghost-frame number."
                )
                return

            if not os.path.isfile(self.ffmpeg_path):
                self.status_label.config(text="Invalid ffmpeg path.")
                return

            # 1) build single fade for each subfolder => subfolder_fade_info
            if not self._build_subfolder_fades():
                messagebox.showerror(
                    "Error", "Could not build fade for subfolders."
                )
                return

            # 2) build global spline
            ret_spline = fading.FadingLogic.build_cubicspline_subfolders(
                self.subfolder_names, self.subfolder_fade_info, steps_val
            )
            if not ret_spline:
                messagebox.showerror(
                    "Error", "Global spline build returned None."
                )
                return
            (keyframe_times, b_splines, c_splines,
             w_, h_, total_frames) = ret_spline
            print(f"[INFO] Global Spline => total_frames={total_frames}")

            out_folder = "output"
            if not os.path.exists(out_folder):
                os.makedirs(out_folder)

            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            igam = self.gamma_entry.get()
            iinf = self.influence_slider.get()
            idev = self.damping_entry.get()
            ftag = f"{now_str}_fading_g{igam}i{iinf}d{idev}"

            # 3) partial frames => chunk => final merge
            fading.FadingLogic.export_crossfade_video(
                keyframe_times=keyframe_times,
                boundary_splines_data=b_splines,
                color_splines_data=c_splines,
                w=w_,
                h=h_,
                total_frames=total_frames,
                fps_val=fps_val,
                frames_per_batch=frames_val,
                worker_count=workers_val,
                ffmpeg_path=self.ffmpeg_path,
                out_folder=out_folder,
                file_tag=ftag,
                progress_bar=progress_bar,
                diag=diag,
                delete_chunks=delete_var.get(),
                ghost_count=ghost_val
            )
            diag.destroy()
            elap = time.time() - start_export
            mins = int(elap // 60)
            secs = int(elap % 60)
            if mins > 0:
                self.status_label.config(
                    text=f"Export done in {mins}min {secs}s."
                )
            else:
                self.status_label.config(text=f"Export done in {secs}s.")

        ok_btn = tk.Button(diag, text="OK", command=on_ok, bg=BG_COLOR)
        ok_btn.pack(side="top", padx=5, pady=5)

    def _build_subfolder_fades(self):
        """
        For each subfolder in subfolder_names, build a single fade (via build_horizontal_fade).
        """
        if len(self.subfolder_names) < 2:
            return False
        w_, h_ = self._get_dimensions()
        gam_ = float(self.gamma_entry.get())
        inf_ = float(self.influence_slider.get())
        dam_ = float(self.damping_entry.get())

        for sf in self.subfolder_names:
            off_map = self.subfolder_data[sf]
            fi = []
            for off_val, (fp, px) in off_map.items():
                fi.append((fp, px, off_val))
            fi.sort(key=lambda x: x[2])

            self.image_data.clear()
            g_ = self._get_gamma()
            for fp, px, offv in fi:
                var = tk.BooleanVar(value=True)
                br = fading.ImageHelper.calculate_brightness(fp, g_)
                self.image_data.append(
                    ImageData(
                        file_path=fp,
                        check_var=var,
                        brightness_value=br,
                        offset=offv,
                        is_proxy=px,
                    )
                )

            active_p = []
            br_l = []
            px_l = []
            for d in self.image_data:
                if d.check_var.get():
                    active_p.append(d.file_path)
                    br_l.append(d.brightness_value)
                    px_l.append(d.is_proxy)
            if len(active_p) < 2:
                return False
            fpar = FadeParams(
                width=w_, height=h_, gamma=gam_, influence=inf_, damping=dam_
            )
            r = fading.FadingLogic.build_horizontal_fade(
                active_p, br_l, px_l, fpar)
            if not r:
                return False
            (fimg, bpos, fnames, avgcols) = r
            self.subfolder_fade_info[sf] = SubfolderFadeData(
                final_image=fimg,
                boundary_positions=bpos,
                filenames_at_boundaries=fnames,
                average_colors=avgcols,
                transitions=[],
            )
        return True

    def _get_dimensions(self):
        try:
            w_ = int(self.width_entry.get())
            h_ = int(self.height_entry.get())
            if w_ < 10 or h_ < 10:
                raise ValueError
            return (w_, h_)
        except ValueError:
            return (3840, 720)

    def canvas_resized(self, evt=None):
        self._draw_canvas()

    def _draw_canvas(self):
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

        sc = cv2.resize(self.final_image, (disp_w, disp_h))
        dsp = cv2.cvtColor(sc, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(dsp)
        photo_img = ImageTk.PhotoImage(pil_img)
        self.display_canvas.create_image(0, 0, anchor="nw", image=photo_img)
        self.display_canvas.image = photo_img

        try:
            font = ImageFont.truetype("arial.ttf", TEXT_FONT_SIZE)
        except:
            font = ImageFont.load_default()

        for i, (x_off, (fname, px)) in enumerate(
            zip(self.boundary_positions, self.filenames_at_boundaries)
        ):
            x_scaled = int(x_off * scale)
            if i == len(self.boundary_positions) - 1:
                x_scaled = max(0, x_scaled - 40)
            color = (255, 0, 0) if px else (0, 0, 0)
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
            self.display_canvas.create_image(
                x_scaled, y_bottom, anchor="sw", image=rph)
            self.display_canvas.txt_refs.append(rph)
