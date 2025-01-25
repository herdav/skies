# ui.py

import os
import cv2
import tkinter as tk
from tkinter import filedialog, ttk, simpledialog, messagebox
import numpy as np
import time
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw, ImageFont
from dataclasses import dataclass
from typing import List
import threading

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
  Holds information about each image:
  - file_path: The absolute file path
  - check_var: A Tkinter BooleanVar for including/excluding
  - brightness_value: mean brightness for filtering
  - offset: numeric offset (used in subfolder logic)
  - is_proxy: True if this is a dummy/fallback
  """
  file_path: str
  check_var: tk.BooleanVar
  brightness_value: int
  offset: float
  is_proxy: bool

@dataclass
class SubfolderFadeData:
  """
  Contains final fade info for a subfolder:
  - final_image: The BGR fade result
  - boundary_positions: The x-coordinates of boundaries
  - filenames_at_boundaries: pairs (filename, is_proxy)
  - average_colors: row-wise color arrays for each segment
  - transitions: list of numeric weights (before final width calc)
  """
  final_image: np.ndarray
  boundary_positions: List[int]
  filenames_at_boundaries: List[tuple]
  average_colors: List[np.ndarray]
  transitions: List[float]

class FadingUI:
  """
  Main GUI class that handles:
  - File/Subfolder logic
  - Helligkeits-Filter, Influence, Deviation
  - Dynamic Slider for segment-based fade
  - Calculation & Export with a single Toplevel for param input + progress
  """

  def __init__(self, root: tk.Tk):
    """
    Initialize the main Tk window and data structures.
    """
    self.root = root
    self.root.title("Horizontal Fading - Single Toplevel Export with Progress")
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

    # For storing fade info per subfolder
    self.subfolder_fade_info = {}

    # Crossfade frames for potential stepwise viewing
    self.crossfade_frames = []
    self.crossfade_index = 0
    self.crossfade_active = False

    # Threaded export state
    self.export_thread = None
    self.export_done = False
    self.export_stop_flag = False
    self.export_progress = 0
    self.export_total = 0

    # We'll keep a reference to the export Toplevel
    self.export_window = None
    self.progress_bar = None

    self._build_ui()

  def _build_ui(self):
    """
    Builds the GUI in two lines (frames).
    """
    # First row
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

    # Second row
    self.top_frame_2 = tk.Frame(self.root, bg=BG_COLOR)
    self.top_frame_2.pack(side="top", fill="x", pady=5)

    tk.Label(self.top_frame_2, text="Width:", bg=BG_COLOR).pack(side="left", padx=5)
    self.width_entry = tk.Entry(self.top_frame_2, width=6)
    self.width_entry.insert(0, "3840")
    self.width_entry.pack(side="left", padx=5)

    tk.Label(self.top_frame_2, text="Height:", bg=BG_COLOR).pack(side="left", padx=5)
    self.height_entry = tk.Entry(self.top_frame_2, width=6)
    self.height_entry.insert(0, "1080")
    self.height_entry.pack(side="left", padx=5)

    tk.Label(self.top_frame_2, text="Brightness Filter:", bg=BG_COLOR).pack(side="left", padx=5)
    self.brightness_slider = tk.Scale(self.top_frame_2, from_=0, to=255, orient='horizontal', bg=BG_COLOR)
    self.brightness_slider.set(0)
    self.brightness_slider.pack(side="left", padx=5)

    self.filter_btn = tk.Button(self.top_frame_2, text="Filter", command=self.on_filter, bg=BG_COLOR)
    self.filter_btn.pack(side="left", padx=5)

    self.reset_btn = tk.Button(self.top_frame_2, text="Reset", command=self.on_reset, bg=BG_COLOR)
    self.reset_btn.pack(side="left", padx=5)

    tk.Label(self.top_frame_2, text="Influence (-10..+10):", bg=BG_COLOR).pack(side="left", padx=5)
    self.influence_slider = tk.Scale(self.top_frame_2, from_=-10, to=10, resolution=1, orient='horizontal', bg=BG_COLOR)
    self.influence_slider.set(0)
    self.influence_slider.pack(side="left", padx=5)

    tk.Label(self.top_frame_2, text="Max Deviation (%):", bg=BG_COLOR).pack(side="left", padx=5)
    self.damping_slider = tk.Scale(self.top_frame_2, from_=0, to=50, resolution=1, orient='horizontal', bg=BG_COLOR)
    self.damping_slider.set(20)
    self.damping_slider.pack(side="left", padx=5)

    tk.Label(self.top_frame_2, text="Dynamic Segments (%):", bg=BG_COLOR).pack(side="left", padx=5)
    self.dynamic_slider = tk.Scale(self.top_frame_2, from_=0, to=100, resolution=1, orient='horizontal', bg=BG_COLOR)
    self.dynamic_slider.set(0)
    self.dynamic_slider.pack(side="left", padx=5)

    self.export_images_var = tk.BooleanVar(value=True)
    self.export_video_var = tk.BooleanVar(value=False)
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

  # ----------------
  # File / Directory / Subfolder logic
  # ----------------

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
    self.subfolder_fade_info.clear()

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
    # Fill missing offsets with fallback
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

  # -------------
  # Calculation
  # -------------

  def on_calculate(self):
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
    self.status_label.config(text=f"Calculation done in {elapsed}s. {self.status_label.cget('text')}")

  def on_filter(self):
    start_t = time.time()
    self._reset_checkboxes()
    threshold = self.brightness_slider.get()
    for data_item in self.image_data:
      if data_item.brightness_value < threshold:
        data_item.check_var.set(False)
    self._build_fade_core()
    end_t = time.time()
    elapsed = round(end_t - start_t, 2)
    self.status_label.config(text=f"Filtered < {threshold} in {elapsed}s. {self.status_label.cget('text')}")

  def on_reset(self):
    self.brightness_slider.set(0)
    self._reset_checkboxes()
    self._build_fade_core()
    self.status_label.config(text="Reset filter. Recalculated fade.")

  def _reset_checkboxes(self):
    for data_item in self.image_data:
      data_item.check_var.set(True)

  def _build_fade_core(self):
    """
    Builds the fade with Influence and Deviation. Stores final_image, boundary_positions, etc.
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

    # parse width/height
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

    # Prepare average row-colors
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

    # Influence-based weighting
    influence_val = float(self.influence_slider.get())
    original_transitions = []
    for i in range(n - 1):
      ab = (brightness_list[i] + brightness_list[i+1]) / 2.0
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

    # If in subfolder mode, store result
    if self.current_mode == MODE_SUBFOLDERS and self.subfolder_names:
      if self.subfolder_combo_idx < len(self.subfolder_names):
        sf_key = self.subfolder_names[self.subfolder_combo_idx]
        fade_data = SubfolderFadeData(
          final_image=final_result,
          boundary_positions=bounds[:],
          filenames_at_boundaries=filenames[:],
          average_colors=average_colors[:],
          transitions=transitions[:]
        )
        self.subfolder_fade_info[sf_key] = fade_data

    self._redraw_canvas()

  # ----------------
  # CROSSFADE
  # ----------------

  def _build_global_subfolder_crossfade(self, steps: int) -> List[np.ndarray]:
    frames = []
    n_sub = len(self.subfolder_names)
    if n_sub < 1:
      return frames

    prev_data = None
    for i, sf in enumerate(self.subfolder_names):
      self._load_subfolder_images(i, auto_calc=False)
      if self.brightness_slider.get() > 0:
        self.on_filter()
      else:
        self._build_fade_core()
      if self.final_image is None:
        continue

      current_data = self.subfolder_fade_info.get(sf, None)
      if current_data is None:
        frames.append(self.final_image.copy())
        prev_data = None
        continue

      if prev_data is None:
        frames.append(current_data.final_image.copy())
      else:
        new_frames = self._build_mix_crossfade(prev_data, current_data, steps)
        for idx_f in range(1, len(new_frames)):
          frames.append(new_frames[idx_f])

      prev_data = current_data
    return frames

  def _build_mix_crossfade(self, fadeA: SubfolderFadeData, fadeB: SubfolderFadeData, steps: int) -> List[np.ndarray]:
    dyn_val = self.dynamic_slider.get()
    if dyn_val < 1:
      return FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)
    if dyn_val > 99:
      return self._build_segment_interpolated_crossfade(fadeA, fadeB, steps)

    seg_frames = self._build_segment_interpolated_crossfade(fadeA, fadeB, steps)
    pix_frames = FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)

    frames = []
    frames.append(pix_frames[0].copy())
    alpha_dyn = dyn_val / 100.0
    for i in range(1, len(pix_frames)):
      blended = self._blend_two_images(pix_frames[i], seg_frames[i], alpha_dyn)
      frames.append(blended)
    frames.append(pix_frames[-1].copy())
    return frames

  def _build_segment_interpolated_crossfade(self, fadeA: SubfolderFadeData, fadeB: SubfolderFadeData, steps: int) -> List[np.ndarray]:
    frames = []
    hA, wA, _ = fadeA.final_image.shape
    hB, wB, _ = fadeB.final_image.shape
    if hA != hB or wA != wB:
      return FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)

    bposA = np.array(fadeA.boundary_positions, dtype=np.float32)
    bposB = np.array(fadeB.boundary_positions, dtype=np.float32)
    avgA = fadeA.average_colors
    avgB = fadeB.average_colors
    if len(avgA) != len(avgB) or len(avgA) < 2:
      return FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)

    frames.append(fadeA.final_image.copy())
    for s in range(1, steps + 1):
      alpha = s / (steps + 1)
      curPos = (1 - alpha)*bposA + alpha*bposB
      blended_colors = []
      for i_col in range(len(avgA)):
        ca = avgA[i_col]
        cb = avgB[i_col]
        c_blend = (1 - alpha)*ca + alpha*cb
        blended_colors.append(c_blend.astype(np.uint8))

      res = np.zeros((hA, wA, 3), dtype=np.uint8)
      x_start = 0
      for i_seg in range(len(avgA) - 1):
        x_end = int(round(curPos[i_seg+1]))
        if x_end < x_start:
          continue
        if x_end > wA:
          x_end = wA
        grad = FadingLogic.generate_fading_gradient(blended_colors[i_seg], blended_colors[i_seg+1], x_end - x_start)
        res[:, x_start:x_end] = grad
        x_start = x_end
      frames.append(res)
    frames.append(fadeB.final_image.copy())
    return frames

  def _blend_two_images(self, imgA: np.ndarray, imgB: np.ndarray, alpha: float) -> np.ndarray:
    hA, wA, _ = imgA.shape
    hB, wB, _ = imgB.shape
    if (hA != hB) or (wA != wB):
      imgB = cv2.resize(imgB, (wA, hA))
    return cv2.addWeighted(imgA, 1.0 - alpha, imgB, alpha, 0)

  def _load_subfolder_images(self, idx, auto_calc=True):
    for widget in self.checkbox_frame.winfo_children():
      widget.destroy()
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
      br_val = self._calc_brightness(fp)
      filename = os.path.basename(fp)
      prefix = filename.split("_", 1)[0]

      frame_card = tk.Frame(self.checkbox_frame, bg=BG_COLOR, bd=1, relief="solid")
      frame_card.grid(row=0, column=col_idx, padx=5, pady=5, sticky="ew")

      cb = tk.Checkbutton(frame_card, variable=var, bg=BG_COLOR)
      cb.pack(side="top", anchor="center")

      lb_name = tk.Label(frame_card, text=prefix, bg=BG_COLOR)
      lb_name.pack(side="top")

      lb_bright = tk.Label(frame_card, text=str(br_val), bg=BG_COLOR)
      lb_bright.pack(side="top")

      self.image_data.append(
        ImageData(
          file_path=fp,
          check_var=var,
          brightness_value=br_val,
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

  def _build_image_data(self, filepaths: List[str]):
    for widget in self.checkbox_frame.winfo_children():
      widget.destroy()
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
        ImageData(
          file_path=fp,
          check_var=var,
          brightness_value=br_val,
          offset=offset_val,
          is_proxy=False
        )
      )

  def _calc_brightness(self, filepath: str) -> int:
    img = cv2.imread(filepath)
    if img is None:
      return 0
    return int(round(np.mean(img)))

  # ----------------
  # Export
  # ----------------

  def on_export(self):
    """
    Opens a single Toplevel to ask Steps/FPS, then in the same window we show a progressbar.
    """
    self._build_fade_core()
    if self.final_image is None:
      self.status_label.config(text="No fade to export.")
      return

    diag = tk.Toplevel(self.root)
    diag.title("Export Options")
    diag.configure(bg=BG_COLOR)

    # Frame for param input
    param_frame = tk.Frame(diag, bg=BG_COLOR)
    param_frame.pack(side="top", fill="x", padx=10, pady=10)

    tk.Label(param_frame, text="Number of Crossfades:", bg=BG_COLOR).pack(side="top", padx=5, pady=2)
    steps_var = tk.StringVar(value="10")
    steps_entry = tk.Entry(param_frame, textvariable=steps_var)
    steps_entry.pack(side="top", padx=5, pady=2)

    tk.Label(param_frame, text="Video FPS:", bg=BG_COLOR).pack(side="top", padx=5, pady=2)
    fps_var = tk.StringVar(value="25")
    fps_entry = tk.Entry(param_frame, textvariable=fps_var)
    fps_entry.pack(side="top", padx=5, pady=2)

    def on_start_export():
      """
      User clicked 'Start Export'. Hide param input, show progress in the same window.
      """
      try:
        steps_val = int(steps_var.get())
        fps_val = int(fps_var.get())
        if steps_val < 1 or fps_val < 1:
          raise ValueError
      except ValueError:
        messagebox.showerror("Error", "Please provide valid Steps/FPS.")
        return

      # Remove param_frame
      param_frame.pack_forget()

      # Show progress bar / Cancel in the same diag
      progress_frame = tk.Frame(diag, bg=BG_COLOR)
      progress_frame.pack(side="top", fill="x", padx=10, pady=10)

      self.progress_bar = ttk.Progressbar(progress_frame, length=300, mode='determinate')
      self.progress_bar.pack(side="top", padx=10, pady=10)
      self.progress_bar['value'] = 0
      self.progress_bar['maximum'] = 1  # adjusted later

      def on_cancel():
        self.export_stop_flag = True

      cancel_btn = tk.Button(progress_frame, text="Cancel", command=on_cancel, bg=BG_COLOR)
      cancel_btn.pack(side="top", padx=5, pady=5)

      # Start export in thread
      self._run_export_in_thread(steps_val, fps_val, diag)

    start_btn = tk.Button(diag, text="Start Export", command=on_start_export, bg=BG_COLOR)
    start_btn.pack(side="top", padx=5, pady=5)

  def _run_export_in_thread(self, steps: int, fps: int, diag: tk.Toplevel):
    """
    Prepares frames for export, spawns a background thread.
    'diag' remains open until the thread is done or fails.
    """
    self.export_done = False
    self.export_stop_flag = False
    self.export_progress = 0

    # Build frames (global crossfade) or single fade
    frames_preview = self._build_global_subfolder_crossfade(steps)
    if not frames_preview and self.final_image is not None:
      frames_preview = [self.final_image]

    # Decide how many total items we have
    if self.export_images_var.get():
      self.export_total = len(frames_preview)
    else:
      self.export_total = 1

    if self.progress_bar:
      self.progress_bar['maximum'] = self.export_total
      self.progress_bar['value'] = 0

    def target():
      """
      The real export logic in the background thread.
      """
      start_t = time.time()

      base_output = "output"
      if not os.path.exists(base_output):
        os.makedirs(base_output)

      # If user wants images => new subfolder
      if self.export_images_var.get():
        export_folder = FadingLogic.get_next_output_subfolder()
      else:
        export_folder = base_output

      now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
      inf_val = self.influence_slider.get()
      dev_val = self.damping_slider.get()
      dyn_val = self.dynamic_slider.get()
      file_tag = f"{now_str}_fading_Inf{inf_val}_Dev{dev_val}_Dyn{dyn_val}"

      # Save images if requested
      if self.export_images_var.get():
        for i, frm in enumerate(frames_preview):
          if self.export_stop_flag:
            break
          cv2.imwrite(os.path.join(export_folder, f"{file_tag}_{i:03d}.png"), frm)
          self.export_progress += 1
          time.sleep(0.05)  # simulate time

      # Save video if requested
      if not self.export_stop_flag and self.export_video_var.get():
        video_name = os.path.join(base_output, f"{file_tag}.mp4")
        FadingLogic.export_mpeg_video(frames_preview, video_name, fps)

      end_t = time.time()
      elapsed = round(end_t - start_t, 2)
      self.status_label.config(text=f"Export done in {elapsed}s => {file_tag}")
      self.export_done = True

    self.export_thread = threading.Thread(target=target, daemon=True)
    self.export_thread.start()

    # Keep reference to diag
    self.export_window = diag
    self.root.after(100, self._check_export_thread)

  def _check_export_thread(self):
    """
    Periodically checks if export_thread is running, updates progress bar, closes diag on success.
    """
    if self.export_done:
      # Thread finished => close diag
      if self.export_window and self.export_window.winfo_exists():
        self.export_window.destroy()
      return

    if self.export_thread and not self.export_thread.is_alive():
      # Unexpected stop
      if self.export_window and self.export_window.winfo_exists():
        self.export_window.destroy()
      self.status_label.config(text="Export thread stopped unexpectedly.")
      return

    if self.export_window and self.export_window.winfo_exists() and self.progress_bar:
      self.progress_bar['value'] = self.export_progress

    self.root.after(200, self._check_export_thread)

  # -------------
  # Canvas
  # -------------

  def on_canvas_resized(self, evt=None):
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
