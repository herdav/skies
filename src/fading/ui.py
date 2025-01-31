import os
import cv2
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import numpy as np
import time
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw, ImageFont
from typing import List

# DataClasses (ImageData, SubfolderFadeData)
from datamodel import ImageData, SubfolderFadeData

# Fade logic (extracted from the UI)
import fading


BG_COLOR = "#dcdcdc"
TEXT_BG_COLOR = (220, 220, 220, 255)
TEXT_FONT_SIZE = 12

MODE_NONE = 0
MODE_FILES = 1
MODE_SINGLE_DIR = 2
MODE_SUBFOLDERS = 3

class FadingUI:
  """
  Main GUI class for the horizontal fading application.
  It delegates the actual fade logic to 'fading.py' and the export logic to 'export.py'.
  """

  def __init__(self, root: tk.Tk):
    """
    Initializes the main window, sets up necessary variables and states.
    """
    self.root = root
    self.root.title("Horizontal Fading")
    self.root.configure(bg=BG_COLOR)
    self.root.geometry("1400x750")

    # Current mode: e.g., MODE_FILES, MODE_SINGLE_DIR, MODE_SUBFOLDERS
    self.current_mode = MODE_NONE

    # List of ImageData objects (one for each image)
    self.image_data: List[ImageData] = []

    # Subfolder handling
    self.subfolder_names = []
    self.subfolder_data = {}
    self.subfolder_combo_idx = 0

    # Final fade result stored here
    self.final_image = None
    self.boundary_positions = []
    self.filenames_at_boundaries = []

    # Per-subfolder fade info
    self.subfolder_fade_info = {}

    # Crossfade frames for potential stepwise viewing (not actively used)
    self.crossfade_frames = []
    self.crossfade_index = 0
    self.crossfade_active = False

    # Build the entire UI layout
    self._build_ui()

    # A simple cache for performance to avoid re-building the fade
    # when input parameters haven't changed
    self._last_fade_cache = {
      "active_paths": None,
      "brightness_list": None,
      "proxy_list": None,
      "width": None,
      "height": None,
      "influence": None,
      "damping": None,
      "result": None  # Tuple: (final_image, boundary_positions, filenames_at_boundaries)
    }

  def _build_ui(self):
    """
    Creates two rows of controls and places a status label, 
    checkbox frame, and canvas for displaying the final fade.
    """
    # First row (top_frame_1)
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

    # Second row (top_frame_2)
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
  # File / Directory logic
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
    sorted_paths = sorted(files, key=fading.FadingLogic.parse_utc_offset)
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
    found_files = sorted(found_files, key=fading.FadingLogic.parse_utc_offset)
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
      fl = sorted(fl, key=fading.FadingLogic.parse_utc_offset)
      if not fl:
        continue
      offset_map = {}
      for fpath in fl:
        off_val = fading.FadingLogic.parse_utc_offset(fpath)
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
          path, is_proxy = fading.FadingLogic.fallback_for_offset(i, off, self.subfolder_names, self.subfolder_data)
          new_map[off] = (path, is_proxy)
      self.subfolder_data[sf] = new_map

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
    """
    Moves to the previous subfolder if available.
    """
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
    """
    Moves to the next subfolder if available.
    """
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
    Called when the user selects a different subfolder in the combo box.
    """
    selection = self.subfolder_combo.get()
    if selection in self.subfolder_names:
      idx = self.subfolder_names.index(selection)
      self._load_subfolder_images(idx, auto_calc=True)

  def _load_subfolder_images(self, idx, auto_calc=True):
    """
    Loads image data for a given subfolder index, optionally calls build fade.
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
      if self.brightness_slider.get() > 0:
        self.on_filter()
      else:
        self._call_build_fade_core()
    self.update_navigation()

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
      offset_val = fading.FadingLogic.parse_utc_offset(fp)

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
    Builds the fade synchronously, overwriting status_label with the time it took.
    """
    start_t = time.time()
    self.crossfade_active = False
    self.crossfade_frames.clear()

    if self.current_mode == MODE_SUBFOLDERS and self.subfolder_names:
      if self.brightness_slider.get() > 0:
        self.on_filter()
        return
      else:
        self._call_build_fade_core()
    else:
      self._call_build_fade_core()

    end_t = time.time()
    elapsed = round(end_t - start_t, 2)
    self.status_label.config(text=f"Calculation done in {elapsed}s.")

  def on_filter(self):
    """
    Applies a brightness filter, then rebuilds the fade. Overwrites status_label with the time it took.
    """
    start_t = time.time()
    self._reset_checkboxes()
    threshold = self.brightness_slider.get()
    for data_item in self.image_data:
      if data_item.brightness_value < threshold:
        data_item.check_var.set(False)
    self._call_build_fade_core()
    end_t = time.time()
    elapsed = round(end_t - start_t, 2)
    self.status_label.config(text=f"Filtered < {threshold} in {elapsed}s.")

  def on_reset(self):
    """
    Resets the brightness slider to 0, re-checks all images, and rebuilds the fade.
    """
    self.brightness_slider.set(0)
    self._reset_checkboxes()
    self._call_build_fade_core()
    self.status_label.config(text="Filter reset, fade recalculated.")

  def _reset_checkboxes(self):
    """
    Ensures all images are included again.
    """
    for data_item in self.image_data:
      data_item.check_var.set(True)

  def _call_build_fade_core(self):
    """
    Calls the fade logic in fading.py, checks if parameters have changed 
    to avoid redundant big loops, storing the result in a cache.
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

    influence_val = float(self.influence_slider.get())
    damping_val = float(self.damping_slider.get())

    # Performance cache
    cache = self._last_fade_cache
    same_input = (
      cache["active_paths"] == tuple(active_paths)
      and cache["brightness_list"] == tuple(brightness_list)
      and cache["proxy_list"] == tuple(proxy_list)
      and cache["width"] == width_total
      and cache["height"] == height_total
      and cache["influence"] == influence_val
      and cache["damping"] == damping_val
    )

    if same_input and cache["result"] is not None:
      # Use cached result
      (self.final_image, self.boundary_positions, self.filenames_at_boundaries) = cache["result"]
      self._redraw_canvas()
      return

    # Otherwise, recompute
    result_tuple = fading.FadingLogic.build_fade_core(
      active_paths, brightness_list, proxy_list,
      width_total, height_total,
      influence_val, damping_val
    )
    if result_tuple is None:
      self.final_image = None
      self.boundary_positions = []
      self.filenames_at_boundaries = []
      self._redraw_canvas()
      return

    (self.final_image, self.boundary_positions, self.filenames_at_boundaries) = result_tuple

    # If subfolder mode, store in subfolder_fade_info
    if self.current_mode == MODE_SUBFOLDERS and self.subfolder_names:
      if self.subfolder_combo_idx < len(self.subfolder_names):
        sf = self.subfolder_names[self.subfolder_combo_idx]
        # For a fully correct approach, you'd also retrieve average_colors and transitions 
        # from the logic function if needed. 
        avg_colors = []
        transitions = []
        fade_data = SubfolderFadeData(
          final_image=self.final_image,
          boundary_positions=self.boundary_positions[:],
          filenames_at_boundaries=self.filenames_at_boundaries[:],
          average_colors=avg_colors[:],
          transitions=transitions[:]
        )
        self.subfolder_fade_info[sf] = fade_data

    # Update cache
    cache["active_paths"] = tuple(active_paths)
    cache["brightness_list"] = tuple(brightness_list)
    cache["proxy_list"] = tuple(proxy_list)
    cache["width"] = width_total
    cache["height"] = height_total
    cache["influence"] = influence_val
    cache["damping"] = damping_val
    cache["result"] = (self.final_image, self.boundary_positions, self.filenames_at_boundaries)

    self._redraw_canvas()

  def on_export(self):
    """
    Blocking export with on-the-fly encoding and a progress bar that updates 
    when each subfolder transition is completed.
    """
    self._call_build_fade_core()
    if self.final_image is None:
      self.status_label.config(text="No fade to export.")
      return

    diag = tk.Toplevel(self.root)
    diag.title("Export Options (Blocking, On-the-fly)")
    diag.configure(bg=BG_COLOR)

    tk.Label(diag, text="Number of Crossfades:", bg=BG_COLOR).pack(side="top", padx=5, pady=5)
    steps_var = tk.StringVar(value="10")
    steps_entry = tk.Entry(diag, textvariable=steps_var)
    steps_entry.pack(side="top", padx=5, pady=5)

    tk.Label(diag, text="Video FPS:", bg=BG_COLOR).pack(side="top", padx=5, pady=5)
    fps_var = tk.StringVar(value="25")
    fps_entry = tk.Entry(diag, textvariable=fps_var)
    fps_entry.pack(side="top", padx=5, pady=5)

    # We'll add a progress bar below that
    progress_frame = tk.Frame(diag, bg=BG_COLOR)
    progress_frame.pack(side="top", fill="x", padx=10, pady=10)

    prog_label = tk.Label(progress_frame, text="Subfolder Progress:", bg=BG_COLOR)
    prog_label.pack(side="top", padx=5, pady=2)

    progress_bar = ttk.Progressbar(progress_frame, length=300, mode='determinate')
    progress_bar.pack(side="top", padx=10, pady=2)

    # We haven't set maximum yet, because we first read the subfolder count

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

      out_folder = "output"
      if not os.path.exists(out_folder):
        os.makedirs(out_folder)

      now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
      inf_val = self.influence_slider.get()
      dev_val = self.damping_slider.get()
      dyn_val = self.dynamic_slider.get()
      file_tag = f"{now_str}_fading_Inf{inf_val}_Dev{dev_val}_Dyn{dyn_val}"

      # Construct the video writer on the fly
      height, width, _ = self.final_image.shape  # use final_image shape
      fourcc = cv2.VideoWriter_fourcc(*'mp4v')
      video_name = os.path.join(out_folder, f"{file_tag}.mp4")

      # If the user only wants images, skip creating writer
      # (But let's handle the case: if export_video_var == True, then do writer)
      writer = None
      if self.export_video_var.get():
        writer = cv2.VideoWriter(video_name, fourcc, float(fps_val), (width, height), True)

      # We'll pass the writer to a new on-the-fly subfolder crossfade
      # Meanwhile, if the user also wants images, 
      # we can store them on the fly as well... or skip it for now.

      # Decide how many subfolders to process
      n_sub = len(self.subfolder_names)
      progress_bar['value'] = 0
      if self.current_mode == MODE_SUBFOLDERS and n_sub > 1:
        # We'll set the progress bar max to the number of transitions: n_sub-1
        progress_bar['maximum'] = n_sub - 1

        # Actually do the on-the-fly subfolder crossfade
        fading.FadingLogic.crossfade_subfolders_onto_writer(
          ui_obj=self,
          writer=writer,
          steps=steps_val,
          progress_bar=progress_bar,
          diag=diag,
          out_folder=out_folder,
          file_tag=file_tag,
          export_images=self.export_images_var.get()
        )
      else:
        # If not multiple subfolders, we just have one final_image or so
        # We can just write that single image or single fade on the fly:
        if writer is not None:
          # just write final_image as a single frame repeated, or skip
          writer.write(self.final_image)
        # If export images is True
        if self.export_images_var.get():
          cv2.imwrite(os.path.join(out_folder, f"{file_tag}_000.png"), self.final_image)

      if writer is not None:
        writer.release()

      end_time = time.time()
      elapsed = round(end_time - start_time, 2)
      self.status_label.config(text=f"Export done in {elapsed}s => {file_tag}")
      diag.destroy()

    ok_btn = tk.Button(diag, text="OK", command=on_ok, bg=BG_COLOR)
    ok_btn.pack(side="top", padx=5, pady=5)

  def on_canvas_resized(self, evt=None):
    """
    Called when the canvas is resized; triggers a redraw of the final image.
    """
    self._redraw_canvas()

  def _redraw_canvas(self):
    """
    Draws self.final_image on the display_canvas. 
    Uses resizing to fit the canvas and also draws boundary filenames at the bottom.
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
