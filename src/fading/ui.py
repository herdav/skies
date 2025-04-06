import os
import time
from typing import List, Optional

import cv2
import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from subfolder import SubfolderManager
from controller import FadeController
from dialogs import AboutDialog, ExportVideoDialog, ExportMovementDialog
from datamodel import ImageData
from fading import ImageHelper

BG_COLOR = "#dcdcdc"
TEXT_BG_COLOR = (220, 220, 220, 255)
TEXT_FONT_SIZE = 12

MODE_NONE = 0
MODE_FILES = 1
MODE_SINGLE_DIR = 2
MODE_SUBFOLDERS = 3

DEFAULT_GAMMA = 2
DEFAULT_DAMPING = 1000
DEFAULT_INFLUENCE = 4
DEFAULT_CROSSFADES = 100
DEFAULT_WIDTH = 1152
DEFAULT_HEIGHT = 216


def create_image_checkboxes(parent_frame, image_data_list, bg_color="#dcdcdc"):
    """
    Creates a row of checkbox cards for each ImageData in image_data_list.
    Each item should have .file_path, .brightness_value, and a .check_var (if not, create it).
    """
    # Clear old entries
    for w in parent_frame.winfo_children():
        w.destroy()

    parent_frame.columnconfigure(tuple(range(len(image_data_list))), weight=1)

    for col_idx, d in enumerate(image_data_list):
        if d.check_var is None:
            d.check_var = tk.BooleanVar(value=True)

        frame_card = tk.Frame(parent_frame, bg=bg_color, bd=1, relief="solid")
        frame_card.grid(row=0, column=col_idx, padx=5, pady=5, sticky="ew")

        cb = tk.Checkbutton(frame_card, variable=d.check_var, bg=bg_color)
        cb.pack(side="top", anchor="center")

        fname = os.path.basename(d.file_path)
        prefix = fname.split("_", 1)[0]

        lb_name = tk.Label(frame_card, text=prefix, bg=bg_color)
        lb_name.pack(side="top")

        lb_bright = tk.Label(frame_card, text=str(d.brightness_value), bg=bg_color)
        lb_bright.pack(side="top")


class FadingUI:
    """
    The main Tkinter-based UI class for Horizontal Fading.
    It delegates subfolder logic to SubfolderManager and fade calculations/exports to FadeController.
    """

    def __init__(self, root: tk.Tk, ffmpeg_path: str = ""):
        """
        Initializes the FadingUI with a root Tk window and an optional ffmpeg_path from config.
        """
        self.root = root
        self.root.title("Horizontal Fading")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry("1500x800")

        # If we got a path from config.json, use it. Otherwise fallback.
        if ffmpeg_path:
            self.ffmpeg_path = ffmpeg_path
        else:
            # fallback if user didn't define a config
            self.ffmpeg_path = (
                r"C:\Users\herda\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft."
                r"Winget.Source_8wekyb3d8bbwe\ffmpeg-7.1-essentials_build\bin\ffmpeg.exe"
            )

        self.current_mode = MODE_NONE
        self.image_data: List[ImageData] = []

        # Subfolder
        self.subfolder_manager = SubfolderManager()
        self.subfolder_names: List[str] = []
        self.subfolder_combo_idx = 0

        # Fade logic
        self.fade_controller = FadeController(self.subfolder_manager)
        self.subfolder_fade_info = {}

        # final fade results
        self.final_image: Optional[cv2.Mat] = None
        self.boundary_positions: List[int] = []
        self.filenames_at_boundaries: List[tuple] = []

        # playback state
        self._is_playing = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        Creates all the UI widgets: top frames, subfolder nav, filter sliders, canvas, status label, etc.
        """
        self.top_container = tk.Frame(self.root, bg=BG_COLOR)
        self.top_container.pack(side="top", fill="x")

        # Right side => curve_frame
        self.curve_frame = tk.Frame(self.top_container, bg=BG_COLOR)
        self.curve_frame.pack(side="right", fill="y", padx=5, pady=5)

        self.curve_canvas_width = 256
        self.curve_canvas_height = 100
        self.curve_canvas = tk.Canvas(
            self.curve_frame,
            width=self.curve_canvas_width,
            height=self.curve_canvas_height,
            bg=BG_COLOR,
        )
        self.curve_canvas.pack(side="top", fill="both", expand=True, padx=5, pady=5)

        # Left side => top_frame_1 + top_frame_2
        self.left_col_frame = tk.Frame(self.top_container, bg=BG_COLOR)
        self.left_col_frame.pack(side="left", fill="x", expand=True)

        self._setup_top_frame_1()
        self._setup_top_frame_2()

        self.checkbox_frame = tk.Frame(self.root, bg=BG_COLOR)
        self.checkbox_frame.pack(side="top", fill="x", pady=5)

        # display_canvas for final fade
        self.display_canvas = tk.Canvas(self.root, bg=BG_COLOR)
        self.display_canvas.pack(side="top", fill="both", expand=True)
        self.display_canvas.bind("<Configure>", self.canvas_resized)

        # status_label
        self.status_label = tk.Label(self.root, text="", fg="blue", bg=BG_COLOR)
        self.status_label.pack(side="top", fill="x")

        # initial draw
        self._draw_weight_curve()

    def _setup_top_frame_1(self) -> None:
        """
        Creates and places the main buttons (Files, Directory, Subfolders, etc.) in top_frame_1.
        """
        self.top_frame_1 = tk.Frame(self.left_col_frame, bg=BG_COLOR)
        self.top_frame_1.pack(side="top", fill="x", pady=5)

        # row of buttons
        btn_files = tk.Button(
            self.top_frame_1, text="Files", command=self.select_images, bg=BG_COLOR
        )
        btn_files.pack(side="left", padx=5)

        btn_single_dir = tk.Button(
            self.top_frame_1,
            text="Directory",
            command=self.select_directory,
            bg=BG_COLOR,
        )
        btn_single_dir.pack(side="left", padx=5)

        btn_subfolders = tk.Button(
            self.top_frame_1,
            text="Subfolders",
            command=self._ui_select_subfolders,
            bg=BG_COLOR,
        )
        btn_subfolders.pack(side="left", padx=5)

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
        self.subfolder_combo.bind("<<ComboboxSelected>>", self.subfolder_changed)

        self.next_btn = tk.Button(
            self.top_frame_1,
            text=">>",
            command=self.next_subfolder,
            bg=BG_COLOR,
            state="disabled",
        )
        self.next_btn.pack(side="left", padx=5)

        self.play_btn = tk.Button(
            self.top_frame_1, text="Play", command=self._play_clicked, bg=BG_COLOR
        )
        self.play_btn.pack(side="left", padx=5)

        self.stop_btn = tk.Button(
            self.top_frame_1, text="Stop", command=self._stop_clicked, bg=BG_COLOR
        )
        self.stop_btn.pack(side="left", padx=5)

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

        self.export_movement_btn = tk.Button(
            self.top_frame_1,
            text="Export Movement",
            command=self.export_movement,
            bg=BG_COLOR,
        )
        self.export_movement_btn.pack(side="left", padx=5)

        self.ffmpeg_btn = tk.Button(
            self.top_frame_1,
            text="Path to FFmpeg",
            command=self.set_ffmpeg_executable,
            bg=BG_COLOR,
        )
        self.ffmpeg_btn.pack(side="left", padx=5)

        quit_btn = tk.Button(
            self.top_frame_1, text="Quit", command=self.on_quit, bg=BG_COLOR
        )
        quit_btn.pack(side="left", padx=5)

        about_btn = tk.Button(
            self.top_frame_1, text="?", command=self.show_about_dialog, bg=BG_COLOR
        )
        about_btn.pack(side="left", padx=5)

    def _setup_top_frame_2(self) -> None:
        """
        Creates the second row of controls: width/height, brightness slider, filter, gamma, damping, weighting, etc.
        """
        self.top_frame_2 = tk.Frame(self.left_col_frame, bg=BG_COLOR)
        self.top_frame_2.pack(side="top", fill="x", pady=5)

        # width
        width_frame = tk.Frame(self.top_frame_2, bg=BG_COLOR)
        width_frame.pack(side="left", padx=5)
        tk.Label(width_frame, text="Width:", bg=BG_COLOR).pack(side="top")
        self.width_entry = tk.Entry(width_frame, width=6)
        self.width_entry.insert(0, DEFAULT_WIDTH)
        self.width_entry.pack(side="top")

        # height
        height_frame = tk.Frame(self.top_frame_2, bg=BG_COLOR)
        height_frame.pack(side="left", padx=5)
        tk.Label(height_frame, text="Height:", bg=BG_COLOR).pack(side="top")
        self.height_entry = tk.Entry(height_frame, width=6)
        self.height_entry.insert(0, DEFAULT_HEIGHT)
        self.height_entry.pack(side="top")

        # brightness
        brightness_frame = tk.Frame(self.top_frame_2, bg=BG_COLOR)
        brightness_frame.pack(side="left", padx=5)
        tk.Label(brightness_frame, text="Brightness:", bg=BG_COLOR).pack(side="top")
        self.brightness_slider = tk.Scale(
            brightness_frame, from_=0, to=255, orient="horizontal", bg=BG_COLOR
        )
        self.brightness_slider.set(0)
        self.brightness_slider.pack(side="top")

        filter_btn = tk.Button(
            self.top_frame_2, text="Filter", command=self.filter_brightness, bg=BG_COLOR
        )
        filter_btn.pack(side="left", padx=5)

        reset_btn = tk.Button(
            self.top_frame_2,
            text="Reset",
            command=self.reset_filter_brightness,
            bg=BG_COLOR,
        )
        reset_btn.pack(side="left", padx=5)

        # gamma
        gamma_frame = tk.Frame(self.top_frame_2, bg=BG_COLOR)
        gamma_frame.pack(side="left", padx=5)
        tk.Label(gamma_frame, text="Gamma:", bg=BG_COLOR).pack(side="top")
        self.gamma_slider = tk.Scale(
            gamma_frame,
            from_=0,
            to=10,
            resolution=1,
            orient="horizontal",
            bg=BG_COLOR,
            command=lambda val: self._draw_weight_curve(),
        )
        self.gamma_slider.set(DEFAULT_GAMMA)
        self.gamma_slider.pack(side="top")
        self.gamma_slider.bind("<ButtonRelease-1>", lambda e: self._slider_released())

        # influence
        influence_frame = tk.Frame(self.top_frame_2, bg=BG_COLOR)
        influence_frame.pack(side="left", padx=5)
        tk.Label(influence_frame, text="Influence:", bg=BG_COLOR).pack(side="top")
        self.influence_slider = tk.Scale(
            influence_frame,
            from_=0,
            to=10,
            resolution=1,
            orient="horizontal",
            bg=BG_COLOR,
            command=self._draw_weight_curve,
        )
        self.influence_slider.set(DEFAULT_INFLUENCE)
        self.influence_slider.pack(side="top")
        self.influence_slider.bind(
            "<ButtonRelease-1>", lambda e: self._slider_released()
        )

        # damping
        damping_frame = tk.Frame(self.top_frame_2, bg=BG_COLOR)
        damping_frame.pack(side="left", padx=5)
        tk.Label(damping_frame, text="Damping:", bg=BG_COLOR).pack(side="top")
        self.damping_slider = tk.Scale(
            damping_frame,
            from_=0,
            to=100,
            resolution=1,
            orient="horizontal",
            bg=BG_COLOR,
        )
        self.damping_slider.set(DEFAULT_DAMPING)
        self.damping_slider.pack(side="top")
        self.damping_slider.bind("<ButtonRelease-1>", lambda e: self._slider_released())

        # weighting
        weight_frame = tk.Frame(self.top_frame_2, bg=BG_COLOR)
        weight_frame.pack(side="left", padx=5)
        tk.Label(weight_frame, text="Weighting:", bg=BG_COLOR).pack(side="top")
        self.weighting_var = tk.StringVar(value="Exponential")
        self.weighting_cb = ttk.Combobox(
            weight_frame,
            textvariable=self.weighting_var,
            values=["Exponential", "Parabola"],
            state="readonly",
        )
        self.weighting_cb.pack(side="top")
        self.weighting_cb.bind("<<ComboboxSelected>>", self._weighting_changed)

        # midpoint
        midpoint_frame = tk.Frame(self.top_frame_2, bg=BG_COLOR)
        midpoint_frame.pack(side="left", padx=5)
        self.midpoint_label = tk.Label(midpoint_frame, text="Midpoint:", bg=BG_COLOR)
        self.midpoint_label.pack(side="top")
        self.midpoint_var = tk.IntVar(value=128)
        self.midpoint_slider = tk.Scale(
            midpoint_frame,
            from_=1,
            to=255,
            orient="horizontal",
            variable=self.midpoint_var,
            bg=BG_COLOR,
            command=lambda val: self._draw_weight_curve(),
        )
        self.midpoint_slider.pack(side="top")
        self.midpoint_slider.bind(
            "<ButtonRelease-1>", lambda e: self._slider_released()
        )

    def show_about_dialog(self) -> None:
        """
        Opens the AboutDialog from dialogs.py
        """
        dlg = AboutDialog(self.root)
        dlg.grab_set()

    def on_quit(self) -> None:
        """Destroys the root window."""
        self.root.destroy()

    def set_ffmpeg_executable(self) -> None:
        """
        Allows the user to pick ffmpeg.exe for video export.
        """
        path = filedialog.askopenfilename(
            title="Select ffmpeg.exe",
            filetypes=[("exe", "*.exe"), ("All", "*.*")],
        )
        if path:
            self.ffmpeg_path = path

    # --------------------------------------------------------------------
    # Subfolder logic
    # --------------------------------------------------------------------
    def _ui_select_subfolders(self) -> None:
        folder = filedialog.askdirectory(title="Select Directory with Subfolders")
        if not folder:
            return

        self.set_mode(MODE_SUBFOLDERS)
        self.subfolder_manager.select_subfolders(folder)
        self.subfolder_manager.fill_missing_images()

        self.subfolder_names = self.subfolder_manager.subfolder_names
        if not self.subfolder_names:
            self.status_label.config(text="No suitable subfolders found.")
            return

        self.subfolder_combo["values"] = self.subfolder_names
        self.subfolder_combo.current(0)
        self._create_subfolder_cards(0, auto_calc=False)
        self.update_navigation()
        self.calculate_fade()

    def set_mode(self, mode: int) -> None:
        """Sets the current mode (FILES, SINGLE_DIR or SUBFOLDERS)."""
        self.current_mode = mode
        self.subfolder_combo_idx = 0

    def update_navigation(self) -> None:
        """
        Updates the navigation buttons (prev/next) and subfolder combo states
        based on current_mode and subfolder indexes.
        """
        if self.current_mode == MODE_SUBFOLDERS and len(self.subfolder_names) > 1:
            self.subfolder_combo.config(state="readonly")
            self.prev_btn.config(
                state="normal" if self.subfolder_combo_idx > 0 else "disabled"
            )
            self.next_btn.config(
                state="normal"
                if self.subfolder_combo_idx < len(self.subfolder_names) - 1
                else "disabled"
            )
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

    def prev_subfolder(self) -> None:
        idx = self.subfolder_combo_idx - 1
        if idx < 0:
            self.prev_btn.config(state="disabled")
            return
        self.subfolder_combo.current(idx)
        self._create_subfolder_cards(idx, auto_calc=True)

    def next_subfolder(self) -> None:
        idx = self.subfolder_combo_idx + 1
        if idx >= len(self.subfolder_names):
            self.next_btn.config(state="disabled")
            return
        self.subfolder_combo.current(idx)
        self._create_subfolder_cards(idx, auto_calc=True)

    def subfolder_changed(self, evt=None) -> None:
        val = self.subfolder_combo.get()
        if val in self.subfolder_names:
            idx = self.subfolder_names.index(val)
            self._create_subfolder_cards(idx, auto_calc=True)

    def _create_subfolder_cards(self, idx: int, auto_calc: bool = True) -> None:
        # Clear old
        for w in self.checkbox_frame.winfo_children():
            w.destroy()
        self.image_data.clear()

        self.subfolder_combo_idx = idx
        sf = self.subfolder_names[idx]
        gamma_val = self._get_gamma()

        fi = self.subfolder_manager.get_subfolder_image_data(sf, gamma_val)
        if not fi:
            self.status_label.config(text="No images in subfolder.")
            return

        self.image_data.extend(fi)

        # Use our local create_image_checkboxes function:
        create_image_checkboxes(self.checkbox_frame, self.image_data)

        if auto_calc:
            if self.brightness_slider.get() > 0:
                self.filter_brightness()
            else:
                self.calculate_fade()

        self.update_navigation()

    # --------------------------------------------------------------------
    # File selection logic
    # --------------------------------------------------------------------
    def select_images(self) -> None:
        """
        Lets user pick multiple image files. Sort them by brightness (with gamma=2),
        store them in self.image_data, then show checkboxes and do a fade calc.
        """
        files = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.tiff *.tif")],
        )
        if not files:
            return

        self.set_mode(MODE_FILES)
        self._create_image_cards(list(files))
        self.update_navigation()
        self.calculate_fade()

    def select_directory(self) -> None:
        """
        Lets user pick a single directory. We'll scan for *_fading.png
        and treat them as 'single-dir mode'.
        """
        folder = filedialog.askdirectory(title="Select Directory")
        if not folder:
            return
        self.set_mode(MODE_SINGLE_DIR)

        found = []
        for it in os.listdir(folder):
            if it.lower().endswith("_fading.png"):
                found.append(os.path.join(folder, it))

        found = sorted(found, key=lambda p: ImageHelper.calculate_brightness(p, 2.0))
        self._create_image_cards(found)
        self.update_navigation()
        self.calculate_fade()

    def _create_image_cards(self, filepaths: List[str]) -> None:
        # Clear old
        for w in self.checkbox_frame.winfo_children():
            w.destroy()
        self.image_data.clear()

        if not filepaths:
            return

        gamma_val = self._get_gamma()
        fi = []
        for fp in filepaths:
            brv = ImageHelper.calculate_brightness(fp, gamma_val)
            fi.append(
                ImageData(
                    file_path=fp,
                    check_var=None,
                    brightness_value=brv,
                    offset=0,
                    is_proxy=False,
                )
            )

        self.image_data.extend(fi)
        create_image_checkboxes(self.checkbox_frame, self.image_data)

    # --------------------------------------------------------------------
    # Brightness filtering & fade
    # --------------------------------------------------------------------
    def filter_brightness(self) -> None:
        start_t = time.time()
        thr = self.brightness_slider.get()

        self.fade_controller.filter_brightness(self.image_data, thr)
        self._run_fade_calculation()

        el = time.time() - start_t
        self.status_label.config(text=f"Filtered < {thr} in {round(el, 2)}s.")

    def reset_filter_brightness(self) -> None:
        start_t = time.time()
        self.fade_controller.reset_brightness_filter(
            self.image_data, self.brightness_slider
        )
        self._run_fade_calculation()

        el = time.time() - start_t
        self.status_label.config(text=f"Filter reset in {round(el, 2)}s.")

    def calculate_fade(self) -> None:
        start_t = time.time()
        self._recalc_brightness()
        self._run_fade_calculation()
        el = time.time() - start_t
        self.status_label.config(text=f"Calculation done in {round(el, 2)}s.")

    def _recalc_brightness(self) -> None:
        gv = self._get_gamma()
        self.fade_controller.gamma_val = gv
        self.fade_controller.recalc_brightness(self.image_data)

    def _run_fade_calculation(self) -> None:
        start_t = time.time()
        w_ = self._get_width()
        h_ = self._get_height()
        if w_ < 10 or h_ < 10:
            self.status_label.config(text="Width/Height error.")
            return

        self.fade_controller.set_weighting_params(
            gamma_val=self._get_gamma(),
            influence_val=float(self.influence_slider.get()),
            damping_val=float(self.damping_slider.get()),
            midpoint_val=float(self.midpoint_var.get()),
            weighting_mode=self.weighting_var.get(),
        )

        result = self.fade_controller.build_horizontal_fade_cache(
            self.image_data, w_, h_
        )
        if not result:
            self.final_image = None
            self.boundary_positions = []
            self.filenames_at_boundaries = []
            self._draw_canvas()
            self.status_label.config(text="Not enough checked images.")
            return

        (
            self.final_image,
            self.boundary_positions,
            self.filenames_at_boundaries,
            avgcols,
        ) = result

        # If subfolders mode, store subfolder fade info if needed
        if self.current_mode == MODE_SUBFOLDERS and self.subfolder_names:
            idx = self.subfolder_combo_idx
            if idx < len(self.subfolder_names):
                sf = self.subfolder_names[idx]
                self.fade_controller.subfolder_fade_info[sf] = None

        self._draw_canvas()
        el = time.time() - start_t
        self.status_label.config(text=f"Calculation done in {round(el, 2)}s.")

    # --------------------------------------------------------------------
    # Export
    # --------------------------------------------------------------------
    def export_current_image(self) -> None:
        if self.final_image is None:
            self.status_label.config(text="No fade to export.")
            return

        wpar = self.fade_controller.get_current_weighting_params()
        out_folder = "output"
        if not os.path.exists(out_folder):
            os.makedirs(out_folder)
        now_s = time.strftime("%Y%m%d_%H%M%S")
        tag = f"{now_s}_fading_g{wpar['gamma']}i{wpar['influence']}d{wpar['damping']}m{wpar['midpoint']}_current.png"
        file_path = os.path.join(out_folder, tag)
        cv2.imwrite(file_path, self.final_image)
        self.status_label.config(text=f"Exported current => {file_path}")

    def export_video(self) -> None:
        w_, h_ = self._get_width(), self._get_height()
        diag = ExportVideoDialog(
            master=self.root,
            controller=self.fade_controller,
            subfolder_manager=self.subfolder_manager,
            ffmpeg_path=self.ffmpeg_path,
            width=w_,
            height=h_,
            default_crosfades=DEFAULT_CROSSFADES,
        )
        diag.grab_set()
        self.root.wait_window(diag)

    def export_movement(self) -> None:
        w_, h_ = self._get_width(), self._get_height()
        diag = ExportMovementDialog(
            master=self.root,
            controller=self.fade_controller,
            subfolder_manager=self.subfolder_manager,
            width=w_,
            height=h_,
            default_crosfades=DEFAULT_CROSSFADES,
        )
        diag.grab_set()
        self.root.wait_window(diag)

    # --------------------------------------------------------------------
    # Canvas + Weight Curve
    # --------------------------------------------------------------------
    def canvas_resized(self, evt=None) -> None:
        """Called when display_canvas is resized."""
        self._draw_canvas()

    def _draw_canvas(self) -> None:
        """Renders self.final_image onto display_canvas with boundary labels."""
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
        except Exception:
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
            self.display_canvas.create_image(x_scaled, y_bottom, anchor="sw", image=rph)
            self.display_canvas.txt_refs.append(rph)

    def _draw_weight_curve(self, evt=None) -> None:
        """
        Draws the weighting curve (Exponential or Parabola) on self.curve_canvas
        using the gamma, influence, and midpoint sliders.
        """
        mode = self.weighting_var.get()
        gamma_val = float(self.gamma_slider.get())
        influence_val = float(self.influence_slider.get())
        midpoint = float(self.midpoint_var.get())

        w_can = self.curve_canvas_width
        h_can = self.curve_canvas_height
        margin = 5
        plot_width = w_can - 2 * margin
        plot_height = h_can - 2 * margin

        points = []
        for x in range(256):
            xg = ((x / 255.0) ** gamma_val) * 255.0
            if mode == "Exponential":
                lin_0to1 = min(max(xg / 255.0, 0), 1)
                wraw = lin_0to1**influence_val if influence_val != 0 else lin_0to1
            else:
                norm = (xg - midpoint) / midpoint
                w_parab = 1.0 - (norm * norm)
                w_parab = max(w_parab, 0)
                wraw = w_parab**influence_val if influence_val != 0 else w_parab

            wraw = min(max(wraw, 0), 1)
            xplot = margin + plot_width * (x / 255.0)
            yplot = margin + plot_height * (1.0 - wraw)
            points.append((xplot, yplot))

        self.curve_canvas.delete("all")
        for i in range(255):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            self.curve_canvas.create_line(x1, y1, x2, y2, fill="blue", width=1)

    def _weighting_changed(self, evt=None) -> None:
        is_exp = self.weighting_var.get() == "Exponential"
        if is_exp:
            self.midpoint_slider.config(state="disabled")
            self.midpoint_label.config(fg="gray")
        else:
            self.midpoint_slider.config(state="normal")
            self.midpoint_label.config(fg="black")

        self._draw_weight_curve()
        self.calculate_fade()

    def _slider_released(self) -> None:
        """
        Called when user releases gamma/influence/damping slider,
        so we update the curve and recalc fade.
        """
        self._draw_weight_curve()
        self.calculate_fade()

    def _get_gamma(self) -> float:
        """
        Returns the gamma slider value as float; defaults to 2.0 if invalid.
        """
        try:
            val = float(self.gamma_slider.get())
            if val <= 0:
                raise ValueError
            return val
        except ValueError:
            return 2.0

    def _get_width(self) -> int:
        """Returns the user-entered width or a default if invalid."""
        try:
            return int(self.width_entry.get())
        except ValueError:
            return 1152

    def _get_height(self) -> int:
        """Returns the user-entered height or a default if invalid."""
        try:
            return int(self.height_entry.get())
        except ValueError:
            return 216

    # --------------------------------------------------------------------
    # Subfolder playback
    # --------------------------------------------------------------------
    def _play_clicked(self) -> None:
        """
        Called when user clicks 'Play' in subfolder mode.
        Moves through subfolders with a delay.
        """
        if self.current_mode == MODE_SUBFOLDERS:
            self._is_playing = True
            self.play_btn.config(relief="sunken", bg="red", fg="white")
            self._play_next()

    def _stop_clicked(self) -> None:
        """Stops the subfolder playback."""
        self._is_playing = False
        self.play_btn.config(relief="raised", bg=BG_COLOR, fg="black")

    def _play_next(self) -> None:
        """Helper for subfolder playback. Advances subfolder_combo_idx in a timed loop."""
        if not self._is_playing:
            self.play_btn.config(relief="raised")
            return

        if self.subfolder_combo_idx < len(self.subfolder_names) - 1:
            self.next_subfolder()
            self.root.after(1500, self._play_next)
        else:
            self._is_playing = False
            self.play_btn.config(relief="raised")
