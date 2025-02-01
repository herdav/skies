import os
import cv2
import re
import numpy as np
from typing import Tuple, List
from datamodel import SubfolderFadeData

class FadingLogic:
  @staticmethod
  def crossfade_subfolders_onto_writer(
    ui_obj,
    writer: cv2.VideoWriter,
    steps: int,
    progress_bar,
    diag,
    out_folder: str,
    file_tag: str,
    export_images: bool
  ):
    """
    On-the-fly subfolder crossfade using a keyframe approach.
    We do NOT do a separate crossfade for each subfolder i->i+1 independently.
    Instead, we:

    1) Collect 'keyframes' by loading each subfolder, calling build_fade_core, 
       storing the boundary positions and average colors in subfolder_fade_info.

    2) Then we do one global pass building transitions 
       from subfolder 0->1->2->...->(n-1). 
       This creates a fluid movement with no 'stop' at each boundary.
    """

    n_sub = len(ui_obj.subfolder_names)
    if n_sub < 2:
      return

    # dynamic segments slider
    dyn_val = ui_obj.dynamic_slider.get()

    # -------------------------------------------------
    # PHASE 1: PRECOMPUTE KEYFRAMES
    # -------------------------------------------------
    # We'll gather a 'SubfolderFadeData' for each subfolder i
    # by loading each subfolder, applying brightness filter if needed,
    # then calling build_fade_core. 
    # The result is stored in ui_obj.subfolder_fade_info[sf].
    
    keyframes_data = []

    for i, sf in enumerate(ui_obj.subfolder_names):
      # 1) load subfolder i => no auto_calc, so we can manually do a brightness filter
      ui_obj._load_subfolder_images(i, auto_calc=False)

      # optional brightness filter if slider>0
      if ui_obj.brightness_slider.get() > 0:
        ui_obj._reset_checkboxes()
        thr = ui_obj.brightness_slider.get()
        for d in ui_obj.image_data:
          if d.brightness_value < thr:
            d.check_var.set(False)

      # 2) call build fade => this populates subfolder_fade_info[sf]
      ui_obj._call_build_fade_core()

      # retrieve the fadeData from subfolder_fade_info
      fadeData = ui_obj.subfolder_fade_info.get(sf, None)
      if fadeData is None:
        # fallback: empty
        fadeData = SubfolderFadeData(
          final_image=ui_obj.final_image.copy(),
          boundary_positions=[],
          filenames_at_boundaries=[],
          average_colors=[],
          transitions=[]
        )
      keyframes_data.append(fadeData)

    # if there's only 1 subfolder with images, we cannot crossfade
    if len(keyframes_data) < 2:
      return

    # -------------------------------------------------
    # PHASE 2: BUILD GLOBAL ANIMATION
    # -------------------------------------------------
    # We'll do a single pass over subfolders from i=0..(n_sub-2),
    # each time building transitions i->i+1 in 'steps' frames.
    # We handle 'pixel only', 'segment only', or 'mix' depending on dyn_val.
    # Then we write frames on-the-fly to 'writer', also exporting images if requested.
    # We'll update the progress bar once per subfolder transition.

    for i in range(n_sub - 1):
      # update progress bar 
      progress_bar['value'] = i
      diag.update_idletasks()

      fadeA = keyframes_data[i]
      fadeB = keyframes_data[i + 1]

      # decide method based on dyn_val
      if dyn_val < 1:
        # purely pixel crossfade
        frames = FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)
      elif dyn_val > 99:
        # purely segment approach
        frames = FadingLogic.build_segment_interpolated_crossfade(fadeA, fadeB, steps)
      else:
        # mixed crossfade
        frames = FadingLogic.build_mix_crossfade(fadeA, fadeB, dyn_val, steps)

      # on-the-fly writing:
      # typically frames has steps+2 items (start, steps of crossfade, end)
      # you can skip the last frame to avoid duplicates 
      # if you want a super-smooth sequence with no 'stop'. 
      
      for idx, fr in enumerate(frames):
        if writer is not None:
          writer.write(fr)
        if export_images:
          # store frames with subfolder i info if you like
          cv2.imwrite(os.path.join(out_folder, f"{file_tag}_{i}_{idx:03d}.png"), fr)

  @staticmethod
  def parse_utc_offset(filepath: str) -> float:
    base = os.path.basename(filepath)
    match = re.match(r"^(UTC[+-]\d+(?:\.\d+)?).*", base, re.IGNORECASE)
    if match:
      sub = re.match(r"UTC([+-]\d+(?:\.\d+)?)", match.group(1), re.IGNORECASE)
      if sub:
        try:
          return float(sub.group(1))
        except ValueError:
          pass
    return 9999

  @staticmethod
  def fallback_for_offset(i: int, offset: float, subfolder_names: list, subfolder_data: dict) -> Tuple[str, bool]:
    if i == 0:
      for k in range(1, len(subfolder_names)):
        om = subfolder_data[subfolder_names[k]]
        if offset in om:
          return om[offset][0], True
      return FadingLogic.create_black_dummy_image(offset), True

    if i == len(subfolder_names) - 1:
      for k in range(len(subfolder_names) - 2, -1, -1):
        om = subfolder_data[subfolder_names[k]]
        if offset in om:
          return om[offset][0], True
      return FadingLogic.create_black_dummy_image(offset), True

    for k in range(i + 1, len(subfolder_names)):
      om = subfolder_data[subfolder_names[k]]
      if offset in om:
        return om[offset][0], True
    for k in range(i - 1, -1, -1):
      om = subfolder_data[subfolder_names[k]]
      if offset in om:
        return om[offset][0], True

    return FadingLogic.create_black_dummy_image(offset), True

  @staticmethod
  def get_next_output_subfolder() -> str:
    base = "output"
    if not os.path.exists(base):
      os.makedirs(base)
    i = 1
    while True:
      path = os.path.join(base, f"{i:03d}")
      if not os.path.exists(path):
        os.makedirs(path)
        return path
      i += 1

  @staticmethod
  def create_black_dummy_image(offset: float) -> str:
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
  def generate_fading_gradient(colors_left: np.ndarray, colors_right: np.ndarray, width: int) -> np.ndarray:
    height = colors_left.shape[0]
    if width < 1:
      return np.zeros((height, 0, 3), dtype=np.uint8)

    x_indices = np.linspace(0.0, 1.0, width).reshape(1, width, 1)
    left = colors_left.reshape(height, 1, 3)
    right = colors_right.reshape(height, 1, 3)
    grad = (1.0 - x_indices) * left + x_indices * right
    return grad.astype(np.uint8)

  @staticmethod
  def build_crossfade_sequence(imgA: np.ndarray, imgB: np.ndarray, steps: int) -> List[np.ndarray]:
    """
    Simple pixel-based crossfade:
    linearly blends from imgA to imgB over 'steps' intermediate frames.
    """
    frames = []
    hA, wA, _ = imgA.shape
    hB, wB, _ = imgB.shape
    if (hA != hB) or (wA != wB):
      # fallback => resize B
      imgB = cv2.resize(imgB, (wA, hA))
    frames.append(imgA.copy())
    for i in range(1, steps + 1):
      alpha = i / (steps + 1)
      blend = cv2.addWeighted(imgA, 1.0 - alpha, imgB, alpha, 0)
      frames.append(blend)
    frames.append(imgB.copy())
    return frames

  @staticmethod
  def export_mpeg_video(frames: list, filename: str, fps: int = 25):
    """
    Exports a list of frames to an MP4 video file.
    """
    if not frames:
      return
    height, width, _ = frames[0].shape
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, float(fps), (width, height), True)
    if not out.isOpened():
      return
    for f in frames:
      out.write(f)
    out.release()

  @staticmethod
  def build_fade_core(
      active_paths: List[str],
      brightness_list: List[int],
      proxy_list: List[bool],
      width_total: int,
      height_total: int,
      influence_val: float,
      damping_percent: float
    ):
    """
    Creates a single horizontal fade from a set of 'active_paths'.
    Returns (final_image, boundary_positions, filenames_at_boundaries, average_colors).
    If something fails (like not enough paths), returns None.

    The 'influence_val' affects how brightness influences transition weighting.
    'damping_percent' limits how far we deviate from the original distribution.
    """
    if len(active_paths) < 2:
      return None

    final_result = np.zeros((height_total, width_total, 3), dtype=np.uint8)
    bounds = []
    filenames = []
    average_colors = []

    n = len(active_paths)

    # 1) load average color for each path
    loaded_colors = []
    for idx, path in enumerate(active_paths):
      img = cv2.imread(path)
      if img is None:
        # black dummy
        dummy = np.zeros((10,10,3), dtype=np.uint8)
        ratio = height_total / 10.0
        new_w = max(1, int(10 * ratio))
        resized = cv2.resize(dummy, (new_w, height_total))
        avg = FadingLogic.calculate_horizontal_average(resized)
      else:
        ratio = float(height_total) / float(img.shape[0])
        new_w = max(1, int(img.shape[1] * ratio))
        resized = cv2.resize(img, (new_w, height_total))
        avg = FadingLogic.calculate_horizontal_average(resized)
      loaded_colors.append(avg)

    # 2) compute transition weighting
    transitions = []
    original_transitions = []
    for i in range(n - 1):
      ab = (brightness_list[i] + brightness_list[i+1]) / 2.0
      orig_w = 1.0
      if influence_val == 0:
        wgt = 1.0
      else:
        safe_bright = max(1, ab)
        wgt = (safe_bright ** influence_val)
        if wgt < 1e-6:
          wgt = 0
      transitions.append(wgt)
      original_transitions.append(orig_w)

    total_w = sum(transitions)
    if total_w <= 0:
      return None

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

      leftC = loaded_colors[i]
      rightC = loaded_colors[i+1]
      seg_width = x_end - x_start
      if seg_width < 1:
        bounds.append(x_start)
        filenames.append((fname, is_proxy_flag))
        continue

      x_indices = np.linspace(0.0, 1.0, seg_width, dtype=np.float32).reshape(1, seg_width, 1)
      leftC_resh = leftC.reshape(height_total, 1, 3)
      rightC_resh = rightC.reshape(height_total, 1, 3)
      grad = (1.0 - x_indices)*leftC_resh + x_indices*rightC_resh
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

    # Return 4 items if you want to do segment-based crossfade:
    # For backwards compatibility in this example,
    # we used to return only 3. We'll do 4 to allow segment approach:
    return (final_result, bounds, filenames, loaded_colors)

  @staticmethod
  def build_mix_crossfade(
      fadeA: SubfolderFadeData,
      fadeB: SubfolderFadeData,
      dyn_val: float,
      steps: int
    ) -> List[np.ndarray]:
    """
    Mixes pixel fade and segment fade depending on dyn_val (0..100).
    If dyn_val < 1 => pure pixel,
       dyn_val > 99 => pure segment,
       else => an alpha-blend of both approaches in each frame.
    """
    if dyn_val < 1:
      return FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)
    if dyn_val > 99:
      return FadingLogic.build_segment_interpolated_crossfade(fadeA, fadeB, steps)

    seg_frames = FadingLogic.build_segment_interpolated_crossfade(fadeA, fadeB, steps)
    pix_frames = FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)

    out_frames = []
    out_frames.append(pix_frames[0].copy())
    alpha = dyn_val / 100.0
    for i in range(1, len(pix_frames)):
      blend = FadingLogic.blend_two_images(pix_frames[i], seg_frames[i], alpha)
      out_frames.append(blend)
    out_frames.append(pix_frames[-1].copy())
    return out_frames

  @staticmethod
  def build_segment_interpolated_crossfade(fadeA, fadeB, steps: int, use_easing: bool = False):
    """
    If use_easing=True, we do a cubic ease-in-out (easeInOutCubic).
    If use_easing=False, we do a linear interpolation alpha = t.
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

    arrA = np.stack(avgA, axis=0)
    arrB = np.stack(avgB, axis=0)
    n_seg = arrA.shape[0]
    hA2, wA2 = hA, wA

    def ease_in_out_cubic(t: float) -> float:
      if t < 0.5:
        return 4.0 * (t**3)
      else:
        return 1.0 - 4.0 * ((1.0 - t)**3)

    for s in range(1, steps + 1):
      t = s / (steps + 1)
      if use_easing:
        alpha = ease_in_out_cubic(t)
      else:
        # linear
        alpha = t

      # optional clamp
      alpha = max(0.0, min(1.0, alpha))

      # boundary interpolation
      curPos = (1.0 - alpha)*bposA + alpha*bposB
      # color interpolation
      colorArr = (1.0 - alpha)*arrA + alpha*arrB
      colorArr = colorArr.astype(np.uint8)

      res = np.zeros((hA2, wA2, 3), dtype=np.uint8)
      x_start = 0
      for i_seg in range(n_seg - 1):
        x_end = int(round(curPos[i_seg+1]))
        if x_end < x_start:
          continue
        if x_end > wA2:
          x_end = wA2
        seg_w = x_end - x_start
        if seg_w < 1:
          continue

        leftC = colorArr[i_seg]
        rightC = colorArr[i_seg+1]
        x_indices = np.linspace(0.0, 1.0, seg_w, dtype=np.float32).reshape(1, seg_w, 1)
        leftC_resh = leftC.reshape(hA2, 1, 3)
        rightC_resh = rightC.reshape(hA2, 1, 3)
        grad = (1.0 - x_indices)*leftC_resh + x_indices*rightC_resh
        grad = grad.astype(np.uint8)
        res[:, x_start:x_end] = grad
        x_start = x_end

      frames.append(res)

    frames.append(fadeB.final_image.copy())
    return frames

  @staticmethod
  def blend_two_images(imgA: np.ndarray, imgB: np.ndarray, alpha: float) -> np.ndarray:
    """
    Blends two images of the same size using cv2.addWeighted.
    If sizes differ, we resize B to match A.
    """
    hA, wA, _ = imgA.shape
    hB, wB, _ = imgB.shape
    if (hA != hB) or (wA != wB):
      imgB = cv2.resize(imgB, (wA, hA))
    return cv2.addWeighted(imgA, 1.0 - alpha, imgB, alpha, 0)
