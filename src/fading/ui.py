import os
import cv2
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import numpy as np
import time
from datetime import datetime
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
  """
  Holds information about a single image:
  
  file_path: the absolute path
  check_var: a BooleanVar (whether the image is included in the fade)
  brightness_value: used for filtering
  offset: numeric offset (for subfolder logic)
  is_proxy: True if this image is a fallback/dummy
  """
  file_path: str
  check_var: tk.BooleanVar
  brightness_value: int
  offset: float
  is_proxy: bool

@dataclass
class SubfolderFadeData:
  """
  Contains the final fade result for a subfolder:
  
  final_image: the BGR (OpenCV) image of the fade
  boundary_positions: list of x-coordinates for segment boundaries
  filenames_at_boundaries: list of (filename, is_proxy)
  average_colors: row-wise color arrays for each segment
  transitions: raw numeric weights (before final width calculation)
  """
  final_image: np.ndarray
  boundary_positions: List[int]
  filenames_at_boundaries: List[tuple]
  average_colors: List[np.ndarray]
  transitions: List[float]

class FadingUI:
  def __init__(self, root: tk.Tk):
    """
    Initializes the main window and basic variables.
    """
    self.root = root
    self.root.title("Horizontal Fading")
    self.root.configure(bg=BG_COLOR)
    self.root.geometry("1400x750")

    self.current_mode = MODE_NONE
    self.image_data: List[ImageData] = []

    self.subfolder_names = []
    self.subfolder_data = {}
    self.subfolder_combo_idx = 0

    self.final_image = None
    self.boundary_positions = []
    self.filenames_at_boundaries = []

    # Stores final fade info per subfolder
    self.subfolder_fade_info = {}

    # For crossfade stepwise (not actively used here)
    self.crossfade_frames = []
    self.crossfade_index = 0
    self.crossfade_active = False

    self._build_ui()

  def _build_ui(self):
    """
    Builds two rows of controls, plus status label, checkbox frame, and canvas.
    """
    # Row 1
    self.top_frame_1 = tk.Frame(self.root, bg=BG_COLOR)
    self.top_frame_1.pack(side="top", fill="x", pady=5)

    self.btn_files = tk.Button(self.top_frame_1, text="Select Images", command=self.on_select_images, bg=BG_COLOR)
    self.btn_files.pack(side="left", padx=5)

    self.btn_single_dir = tk.Button(self.top_frame_1, text="Select Directory", command=self.on_select_directory, bg=BG_COLOR)
    self.btn_single_dir.pack(side="left", padx=5)

    self.btn_subfolders = tk.Button(self.top_frame_1, text="Select Dir with Subfolders", command=self.on_select_subfolders, bg=BG_COLOR)
    self.btn_subfolders.pack(side="left", padx=5)

    self.prev_btn = tk.Button(self.top_frame_1, text="<<", command=self.on_prev_subfolder, bg=BG_COLOR, state="disabled")
    self.prev_btn.pack(side="left", padx=5)

    self.subfolder_combo = ttk.Combobox(self.top_frame_1, state="disabled")
    self.subfolder_combo.pack(side="left", padx=5)
    self.subfolder_combo.bind("<<ComboboxSelected>>", self.on_subfolder_changed)

    self.next_btn = tk.Button(self.top_frame_1, text=">>", command=self.on_next_subfolder, bg=BG_COLOR, state="disabled")
    self.next_btn.pack(side="left", padx=5)

    self.calc_btn = tk.Button(self.top_frame_1, text="Calculate", command=self.on_calculate, bg=BG_COLOR)
    self.calc_btn.pack(side="left", padx=5)

    self.export_btn = tk.Button(self.top_frame_1, text="Export", command=self.on_export, bg=BG_COLOR)
    self.export_btn.pack(side="left", padx=5)

    # Row 2
    self.top_frame_2 = tk.Frame(self.root, bg=BG_COLOR)
    self.top_frame_2.pack(side="top", fill="x", pady=5)

    tk.Label(self.top_frame_2, text="Width:", bg=BG_COLOR).pack(side="left", padx=5)
    self.width_entry = tk.Entry(self.top_frame_2, width=6)
    self.width_entry.insert(0, "3840")
    self.width_entry.pack(side="left", padx=5)

    tk.Label(self.top_frame_2, text="Height:", bg=BG_COLOR).pack(side="left", padx=5)
    self.height_entry = tk.Entry(self.top_frame_2, width=6)
    self.height_entry.insert(0, "720")
    self.height_entry.pack(side="left", padx=5)

    tk.Label(self.top_frame_2, text="Brightness Filter:", bg=BG_COLOR).pack(side="left", padx=5)
    self.brightness_slider = tk.Scale(self.top_frame_2, from_=0, to=255, orient='horizontal', bg=BG_COLOR)
    self.brightness_slider.set(0)
    self.brightness_slider.pack(side="left", padx=5)

    self.filter_btn = tk.Button(self.top_frame_2, text="Filter", command=self.on_filter, bg=BG_COLOR)
    self.filter_btn.pack(side="left", padx=5)

    self.reset_btn = tk.Button(self.top_frame_2, text="Reset", command=self.on_reset, bg=BG_COLOR)
    self.reset_btn.pack(side="left", padx=5)

    tk.Label(self.top_frame_2, text="Influence:", bg=BG_COLOR).pack(side="left", padx=5)
    self.influence_slider = tk.Scale(self.top_frame_2, from_=-4, to=10, resolution=1, orient='horizontal', bg=BG_COLOR)
    self.influence_slider.set(0)
    self.influence_slider.pack(side="left", padx=5)

    tk.Label(self.top_frame_2, text="Max Deviation (%):", bg=BG_COLOR).pack(side="left", padx=5)
    self.damping_slider = tk.Scale(self.top_frame_2, from_=0, to=100, resolution=1, orient='horizontal', bg=BG_COLOR)
    self.damping_slider.set(20)
    self.damping_slider.pack(side="left", padx=5)

    tk.Label(self.top_frame_2, text="Dynamic Segments (%):", bg=BG_COLOR).pack(side="left", padx=5)
    self.dynamic_slider = tk.Scale(self.top_frame_2, from_=0, to=100, resolution=1, orient='horizontal', bg=BG_COLOR)
    self.dynamic_slider.set(0)
    self.dynamic_slider.pack(side="left", padx=5)

    self.export_images_var = tk.BooleanVar(value=False)
    self.export_video_var = tk.BooleanVar(value=True)
    self.img_chk = tk.Checkbutton(self.top_frame_2, text="Export Images", variable=self.export_images_var, bg=BG_COLOR)
    self.img_chk.pack(side="left", padx=5)
    self.vid_chk = tk.Checkbutton(self.top_frame_2, text="Export Video", variable=self.export_video_var, bg=BG_COLOR)
    self.vid_chk.pack(side="left", padx=5)

    self.status_label = tk.Label(self.root, text="", fg="blue", bg=BG_COLOR)
    self.status_label.pack(side="top", fill="x")

    self.checkbox_frame = tk.Frame(self.root, bg=BG_COLOR)
    self.checkbox_frame.pack(side="top", fill="x", pady=5)

    self.display_canvas = tk.Canvas(self.root, bg=BG_COLOR)
    self.display_canvas.pack(side="top", fill="both", expand=True)
    self.display_canvas.bind("<Configure>", self.on_canvas_resized)

  # -------------------------
  # File / Directory
  # -------------------------

  def on_select_images(self):
    """
    Opens a file dialog to select images, sets mode to FILES,
    then builds image_data accordingly.
    """
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
    """
    Selects a single directory and collects all *_fading.png images,
    sets mode to SINGLE_DIR.
    """
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
    """
    Selects a directory that contains multiple subfolders,
    each with *_fading.png images. Sets mode to SUBFOLDERS.
    """
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
    # fill missing offsets with fallback
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

    # Now we can fill the combobox
    self.subfolder_combo["values"] = self.subfolder_names
    self.subfolder_combo.current(0)
    self._load_subfolder_images(0, auto_calc=False)
    self.update_navigation()

  def set_mode(self, mode):
    """
    Sets the current mode (FILES, SINGLE_DIR, SUBFOLDERS).
    """
    self.current_mode = mode
    self.subfolder_combo_idx = 0

  def update_navigation(self):
    """
    Updates UI elements (prev/next buttons, combo) based on current_mode.
    """
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
        self.status_label.config(text=f"{c} images in subfolder idx {self.subfolder_combo_idx}")
    else:
      self.status_label.config(text=f"{c} images loaded.")

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
    """
    Called when the user selects a different subfolder in the combo.
    """
    selection = self.subfolder_combo.get()
    if selection in self.subfolder_names:
      idx = self.subfolder_names.index(selection)
      self._load_subfolder_images(idx, auto_calc=True)

  def _load_subfolder_images(self, idx, auto_calc=True):
    """
    Loads image data for a given subfolder index, optionally auto-calculates.
    """
    for w in self.checkbox_frame.winfo_children():
      w.destroy()
    self.image_data.clear()

    self.subfolder_combo_idx = idx
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
      var = tk.BooleanVar(value=True)
      br = self._calc_brightness(fp)
      filename = os.path.basename(fp)
      prefix = filename.split("_", 1)[0]

      frame_card = tk.Frame(self.checkbox_frame, bg=BG_COLOR, bd=1, relief="solid")
      frame_card.grid(row=0, column=col_idx, padx=5, pady=5, sticky="ew")

      cb = tk.Checkbutton(frame_card, variable=var, bg=BG_COLOR)
      cb.pack(side="top", anchor="center")

      lb_name = tk.Label(frame_card, text=prefix, bg=BG_COLOR)
      lb_name.pack(side="top")

      lb_bright = tk.Label(frame_card, text=str(br), bg=BG_COLOR)
      lb_bright.pack(side="top")

      self.image_data.append(
        ImageData(file_path=fp, check_var=var, brightness_value=br, offset=off_val, is_proxy=px)
      )

    if auto_calc:
      # If brightness slider > 0, apply filter, then build fade
      if self.brightness_slider.get() > 0:
        self.on_filter()
      else:
        self._build_fade_core()
    self.update_navigation()

  # -------------
  # Building image data
  # -------------

  def _build_image_data(self, filepaths: List[str]):
    """
    Creates checkboxes for each file and stores the data in self.image_data.
    """
    for w in self.checkbox_frame.winfo_children():
      w.destroy()
    self.image_data.clear()

    total_files = len(filepaths)
    if total_files == 0:
      return

    self.checkbox_frame.columnconfigure(tuple(range(total_files)), weight=1)
    for idx, fp in enumerate(filepaths):
      var = tk.BooleanVar(value=True)
      br_val = self._calc_brightness(fp)
      offset_val = FadingLogic.parse_utc_offset(fp)

      filename = os.path.basename(fp)
      prefix = filename.split("_", 1)[0]

      frame_card = tk.Frame(self.checkbox_frame, bg=BG_COLOR, bd=1, relief="solid")
      frame_card.grid(row=0, column=idx, padx=5, pady=5, sticky="ew")

      cb = tk.Checkbutton(frame_card, variable=var, bg=BG_COLOR)
      cb.pack(side="top", anchor="center")

      lb_name = tk.Label(frame_card, text=prefix, bg=BG_COLOR)
      lb_name.pack(side="top")

      lb_bright = tk.Label(frame_card, text=str(br_val), bg=BG_COLOR)
      lb_bright.pack(side="top")

      self.image_data.append(
        ImageData(file_path=fp, check_var=var, brightness_value=br_val, offset=offset_val, is_proxy=False)
      )

  def _calc_brightness(self, filepath: str) -> int:
    """
    Calculates mean brightness, or 0 if file not found.
    """
    img = cv2.imread(filepath)
    if img is None:
      return 0
    return int(round(np.mean(img)))

  # -------------
  # Calculation
  # -------------

  def on_calculate(self):
    """
    Builds the fade synchronously, overwriting status_label each time.
    """
    start_t = time.time()
    self.crossfade_active = False
    self.crossfade_frames.clear()

    if self.current_mode == MODE_SUBFOLDERS and self.subfolder_names:
      if self.brightness_slider.get() > 0:
        self.on_filter()
        return
      else:
        self._build_fade_core()
    else:
      self._build_fade_core()

    end_t = time.time()
    elapsed = round(end_t - start_t, 2)
    self.status_label.config(text=f"Calculation done in {elapsed}s.")

  def on_filter(self):
    """
    Applies brightness filter, then rebuilds fade. Overwrites the status text with the filter time.
    """
    start_t = time.time()
    self._reset_checkboxes()
    threshold = self.brightness_slider.get()
    for data_item in self.image_data:
      if data_item.brightness_value < threshold:
        data_item.check_var.set(False)
    self._build_fade_core()
    end_t = time.time()
    elapsed = round(end_t - start_t, 2)
    self.status_label.config(text=f"Filtered < {threshold} in {elapsed}s.")

  def on_reset(self):
    """
    Resets the brightness slider to 0, re-checks all images, and rebuilds the fade.
    """
    self.brightness_slider.set(0)
    self._reset_checkboxes()
    self._build_fade_core()
    self.status_label.config(text="Filter reset, fade recalculated.")

  def _reset_checkboxes(self):
    """
    Ensures all images are included again.
    """
    for data_item in self.image_data:
      data_item.check_var.set(True)

  def _build_fade_core(self):
    """
    Builds the fade with Influence and Deviation, storing final_image and boundary data.
    Uses no time measurement here, as on_calculate/on_filter measure around it.
    """
    active_paths = []
    brightness_list = []
    proxy_list = []
    for d in self.image_data:
      if d.check_var.get():
        active_paths.append(d.file_path)
        brightness_list.append(d.brightness_value)
        proxy_list.append(d.is_proxy)

    if len(active_paths) < 2:
      self.status_label.config(text="Not enough checked images.")
      self.final_image = None
      self.boundary_positions = []
      self.filenames_at_boundaries = []
      self._redraw_canvas()
      return

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
    average_colors = []
    transitions = []
    n = len(active_paths)

    # Load row-wise averages
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

    # Compute transitions with Influence
    influence_val = float(self.influence_slider.get())
    original_transitions = []
    for i in range(n - 1):
      ab = (brightness_list[i] + brightness_list[i+1]) / 2.
      orig_w = 1.0
      if influence_val == 0:
        wgt = 1.0
      else:
        safe_bright = max(1, ab)
        wgt = safe_bright ** influence_val
        if wgt < 1e-6:
          wgt = 0
      transitions.append(wgt)
      original_transitions.append(orig_w)

    total_w = sum(transitions)
    if total_w <= 0:
      self.status_label.config(text="All transitions zero => no fade.")
      self.final_image = None
      self.boundary_positions = []
      self.filenames_at_boundaries = []
      self._redraw_canvas()
      return

    damping_percent = float(self.damping_slider.get())
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

      infl_w_px = int(round(width_total * frac_influenced))
      orig_w_px = int(round(width_total * frac_original))

      diff = infl_w_px - orig_w_px
      max_shift = int(round(orig_w_px * (damping_percent / 100.0)))
      if abs(diff) > max_shift:
        if diff > 0:
          infl_w_px = orig_w_px + max_shift
        else:
          infl_w_px = orig_w_px - max_shift

      seg_w = infl_w_px
      x_end = x_start + seg_w
      if i == (n - 2):
        x_end = width_total
      if x_end > width_total:
        x_end = width_total
      if x_end <= x_start:
        bounds.append(x_start)
        filenames.append((fname, is_proxy_flag))
        continue

      # NumPy broadcasting for segment fade
      leftC = average_colors[i]   # shape (height, 3)
      rightC = average_colors[i+1]
      seg_width = x_end - x_start
      if seg_width < 1:
        bounds.append(x_start)
        filenames.append((fname, is_proxy_flag))
        continue

      x_indices = np.linspace(0.0, 1.0, seg_width, dtype=np.float32).reshape(1, seg_width, 1)
      leftC_resh = leftC.reshape(len(leftC), 1, 3)      # (height,1,3)
      rightC_resh = rightC.reshape(len(rightC), 1, 3)   # (height,1,3)
      grad = (1.0 - x_indices)*leftC_resh + x_indices*rightC_resh  # shape (height, seg_width, 3)
      grad = grad.astype(np.uint8)

      final_result[:, x_start:x_end] = grad
      bounds.append(x_start)
      filenames.append((fname, is_proxy_flag))
      x_start = x_end

    # last boundary
    last_name = os.path.basename(active_paths[-1])
    last_proxy = proxy_list[-1]
    bounds.append(width_total - 1)
    filenames.append((last_name, last_proxy))

    self.final_image = final_result
    self.boundary_positions = bounds
    self.filenames_at_boundaries = filenames

    # if subfolder mode, store
    if self.current_mode == MODE_SUBFOLDERS and self.subfolder_names:
      if self.subfolder_combo_idx < len(self.subfolder_names):
        sf = self.subfolder_names[self.subfolder_combo_idx]
        fade_data = SubfolderFadeData(
          final_image=final_result,
          boundary_positions=bounds[:],
          filenames_at_boundaries=filenames[:],
          average_colors=average_colors[:],
          transitions=transitions[:]
        )
        self.subfolder_fade_info[sf] = fade_data

    self._redraw_canvas()

  # -------------------
  # Export (blocking)
  # -------------------

  def on_export(self):
    """
    Opens a simple Toplevel for Steps/FPS. 
    When user clicks OK, we do everything in the main thread, freezing the UI until done.
    """
    self._build_fade_core()
    if self.final_image is None:
      self.status_label.config(text="No fade to export.")
      return

    diag = tk.Toplevel(self.root)
    diag.title("Export Options (Blocking)")
    diag.configure(bg=BG_COLOR)

    tk.Label(diag, text="Number of Crossfades:", bg=BG_COLOR).pack(side="top", padx=5, pady=5)
    steps_var = tk.StringVar(value="10")
    steps_entry = tk.Entry(diag, textvariable=steps_var)
    steps_entry.pack(side="top", padx=5, pady=5)

    tk.Label(diag, text="Video FPS:", bg=BG_COLOR).pack(side="top", padx=5, pady=5)
    fps_var = tk.StringVar(value="25")
    fps_entry = tk.Entry(diag, textvariable=fps_var)
    fps_entry.pack(side="top", padx=5, pady=5)

    def on_ok():
      """
      Called when user is ready to export. This will block the UI until done.
      """
      start_time = time.time()
      try:
        steps_val = int(steps_var.get())
        fps_val = int(fps_var.get())
        if steps_val < 1 or fps_val < 1:
          raise ValueError
      except ValueError:
        messagebox.showerror("Error", "Please provide valid Steps/FPS.")
        return

      # Build frames or single fade
      frames = []
      if self.current_mode == MODE_SUBFOLDERS and len(self.subfolder_names) > 1:
        frames = self._build_global_subfolder_crossfade(steps_val)
        if not frames and self.final_image is not None:
          frames = [self.final_image]
      else:
        # single fade
        frames = [self.final_image]

      out_folder = "output"
      if not os.path.exists(out_folder):
        os.makedirs(out_folder)

      from fading import FadingLogic
      now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
      inf_val = self.influence_slider.get()
      dev_val = self.damping_slider.get()
      dyn_val = self.dynamic_slider.get()
      file_tag = f"{now_str}_fading_Inf{inf_val}_Dev{dev_val}_Dyn{dyn_val}"

      # Export images if needed
      if self.export_images_var.get():
        for i, frm in enumerate(frames):
          cv2.imwrite(os.path.join(out_folder, f"{file_tag}_{i:03d}.png"), frm)

      # Export video if needed
      if self.export_video_var.get():
        videoname = os.path.join(out_folder, f"{file_tag}.mp4")
        FadingLogic.export_mpeg_video(frames, videoname, fps_val)

      end_time = time.time()
      elapsed = round(end_time - start_time, 2)
      self.status_label.config(text=f"Export done in {elapsed}s => {file_tag}")
      diag.destroy()

    ok_btn = tk.Button(diag, text="OK", command=on_ok, bg=BG_COLOR)
    ok_btn.pack(side="top", padx=5, pady=5)

  # -------------
  # Crossfade logic
  # -------------

  def _build_global_subfolder_crossfade(self, steps: int) -> List[np.ndarray]:
    """
    Builds frames across all subfolders for a blocking export scenario.
    Uses the subfolder_fade_info if available, or final_image fallback.
    """
    frames = []
    n_sub = len(self.subfolder_names)
    if n_sub < 1:
      return frames

    prev_data = None
    for i, sf in enumerate(self.subfolder_names):
      self._load_subfolder_images(i, auto_calc=False)
      if self.brightness_slider.get() > 0:
        self._reset_checkboxes()
        thr = self.brightness_slider.get()
        for d in self.image_data:
          if d.brightness_value < thr:
            d.check_var.set(False)
      self._build_fade_core()
      if self.final_image is None:
        continue

      curr_data = self.subfolder_fade_info.get(sf, None)
      if not curr_data:
        frames.append(self.final_image.copy())
        prev_data = None
        continue

      if prev_data is None:
        frames.append(curr_data.final_image.copy())
      else:
        # do dynamic crossfade
        new_frames = self._build_mix_crossfade(prev_data, curr_data, steps)
        # skip the first to avoid duplicate
        frames.extend(new_frames[1:])
      prev_data = curr_data
    return frames

  def _build_mix_crossfade(self, fadeA: SubfolderFadeData, fadeB: SubfolderFadeData, steps: int) -> List[np.ndarray]:
    """
    Mixes pixel and segment crossfade depending on dynamic slider (0..100).
    Uses NumPy broadcasting for segment approach.
    """
    dyn_val = self.dynamic_slider.get()
    if dyn_val < 1:
      return FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)
    if dyn_val > 99:
      return self._build_segment_interpolated_crossfade(fadeA, fadeB, steps)

    seg_frames = self._build_segment_interpolated_crossfade(fadeA, fadeB, steps)
    pix_frames = FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)

    out_frames = []
    out_frames.append(pix_frames[0].copy())
    alpha = dyn_val / 100.0
    for i in range(1, len(pix_frames)):
      blend = self._blend_two_images(pix_frames[i], seg_frames[i], alpha)
      out_frames.append(blend)
    out_frames.append(pix_frames[-1].copy())
    return out_frames

  def _build_segment_interpolated_crossfade(self, fadeA: SubfolderFadeData, fadeB: SubfolderFadeData, steps: int) -> List[np.ndarray]:
    """
    Builds frames using segment-based interpolation with NumPy broadcasting 
    for better performance, avoiding pixel loops.
    """
    frames = []
    hA, wA, _ = fadeA.final_image.shape
    hB, wB, _ = fadeB.final_image.shape
    if (hA != hB) or (wA != wB):
      return FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)

    bposA = np.array(fadeA.boundary_positions, dtype=np.float32)
    bposB = np.array(fadeB.boundary_positions, dtype=np.float32)
    avgA = fadeA.average_colors
    avgB = fadeB.average_colors

    if len(avgA) != len(avgB) or len(avgA) < 2:
      return FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)

    frames.append(fadeA.final_image.copy())

    # Convert to arrays for vectorization
    arrA = np.stack(avgA, axis=0)  # shape (n_seg, height, 3)
    arrB = np.stack(avgB, axis=0)  # same shape
    n_seg = arrA.shape[0]

    for s in range(1, steps + 1):
      alpha = s / (steps + 1)
      curPos = (1 - alpha)*bposA + alpha*bposB
      colorArr = (1 - alpha)*arrA + alpha*arrB
      colorArr = colorArr.astype(np.uint8)  # shape (n_seg, height,3)

      # build final
      res = np.zeros((hA, wA, 3), dtype=np.uint8)
      x_start = 0
      for i_seg in range(n_seg - 1):
        x_end = int(round(curPos[i_seg+1]))
        if x_end < x_start:
          continue
        if x_end > wA:
          x_end = wA
        seg_w = x_end - x_start
        if seg_w < 1:
          continue

        leftC = colorArr[i_seg]     # shape (height,3)
        rightC = colorArr[i_seg+1]  # shape (height,3)
        x_indices = np.linspace(0.0, 1.0, seg_w, dtype=np.float32).reshape(1, seg_w, 1)
        leftC_resh = leftC.reshape(hA, 1, 3)
        rightC_resh = rightC.reshape(hA, 1, 3)
        grad = (1.0 - x_indices)*leftC_resh + x_indices*rightC_resh
        grad = grad.astype(np.uint8)
        res[:, x_start:x_end] = grad
        x_start = x_end

      frames.append(res)

    frames.append(fadeB.final_image.copy())
    return frames

  def _blend_two_images(self, imgA: np.ndarray, imgB: np.ndarray, alpha: float) -> np.ndarray:
    """
    Blends two images (same size) with given alpha in [0..1], 
    using cv2.addWeighted for vectorized merging.
    """
    hA, wA, _ = imgA.shape
    hB, wB, _ = imgB.shape
    if (hA != hB) or (wA != wB):
      imgB = cv2.resize(imgB, (wA, hA))
    return cv2.addWeighted(imgA, 1.0 - alpha, imgB, alpha, 0)

  # -------------
  # Canvas
  # -------------

  def on_canvas_resized(self, evt=None):
    self._redraw_canvas()

  def _redraw_canvas(self):
    """
    Draws self.final_image on the display_canvas with resizing,
    plus boundary filenames at the bottom.
    """
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
