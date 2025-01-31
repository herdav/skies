import cv2
import numpy as np
import os
import re
from typing import Tuple, List
from datamodel import SubfolderFadeData

class FadingLogic:
  """
  Holds all basic fading and crossfade related logic.
  """
  
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
    On-the-fly subfolder crossfade:
      - Loops over ui_obj.subfolder_names
      - For each subfolder transition i -> i+1, 
        loads i and i+1, calls _call_build_fade_core, 
        immediately writes frames to 'writer' 
        without returning a huge list.

    progress_bar: used to .step() or set value after each subfolder
    diag: the Toplevel window, so we can call diag.update_idletasks()
    out_folder, file_tag: if export_images == True, we can also store frames on the fly.
    """

    n_sub = len(ui_obj.subfolder_names)
    if n_sub < 2:
      return

    # We'll iterate over pairs (i -> i+1)
    for i in range(n_sub - 1):
      # load subfolder i
      ui_obj._load_subfolder_images(i, auto_calc=False)
      # apply brightness filter if needed
      if ui_obj.brightness_slider.get() > 0:
        ui_obj._reset_checkboxes()
        thr = ui_obj.brightness_slider.get()
        for d in ui_obj.image_data:
          if d.brightness_value < thr:
            d.check_var.set(False)
      ui_obj._call_build_fade_core()
      # this yields ui_obj.final_image for subfolder i

      fadeDataA = ui_obj.subfolder_fade_info.get(ui_obj.subfolder_names[i], None)
      if not fadeDataA:
        # fallback
        fadeDataA = SubfolderFadeData(
          final_image=ui_obj.final_image.copy(),
          boundary_positions=[],
          filenames_at_boundaries=[],
          average_colors=[],
          transitions=[]
        )

      # load subfolder i+1
      ui_obj._load_subfolder_images(i + 1, auto_calc=False)
      if ui_obj.brightness_slider.get() > 0:
        ui_obj._reset_checkboxes()
        thr = ui_obj.brightness_slider.get()
        for d in ui_obj.image_data:
          if d.brightness_value < thr:
            d.check_var.set(False)
      ui_obj._call_build_fade_core()
      fadeDataB = ui_obj.subfolder_fade_info.get(ui_obj.subfolder_names[i+1], None)
      if not fadeDataB:
        fadeDataB = SubfolderFadeData(
          final_image=ui_obj.final_image.copy(),
          boundary_positions=[],
          filenames_at_boundaries=[],
          average_colors=[],
          transitions=[]
        )

      # Now we do a crossfade i -> i+1 on the fly
      FadingLogic._crossfade_two_subfolder_data_onto_writer(
        fadeDataA, fadeDataB, writer, steps, out_folder, file_tag, export_images
      )

      # After finishing crossfade for subfolder i->i+1:
      progress_bar['value'] += 1
      diag.update_idletasks()
      # release any large memory if needed
      # e.g. del fadeDataA, fadeDataB ?

  @staticmethod
  def _crossfade_two_subfolder_data_onto_writer(
    fadeA: SubfolderFadeData,
    fadeB: SubfolderFadeData,
    writer: cv2.VideoWriter,
    steps: int,
    out_folder: str,
    file_tag: str,
    export_images: bool
  ):
    """
    Builds crossfade frames from fadeA -> fadeB on the fly.
    Writes each frame directly to 'writer' (if not None).
    Optionally also saves each frame to disk if export_images is True.

    No large list is accumulated in memory.
    """
    if fadeA is None or fadeB is None:
      return

    hA, wA, _ = fadeA.final_image.shape
    hB, wB, _ = fadeB.final_image.shape
    if (hA != hB) or (wA != wB):
      # fallback: just do a normal crossfade of final_image shapes
      frames = FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)
      # but we still do on-the-fly writing
      for idx, fr in enumerate(frames):
        if writer is not None:
          writer.write(fr)
        if export_images:
          cv2.imwrite(os.path.join(out_folder, f"{file_tag}_subfade_{idx:03d}.png"), fr)
      return

    # If subfolder data has average_colors, boundary_positions, etc. => do segment approach
    # Or just do the simpler approach? 
    # We re-use the "build_segment_interpolated_crossfade" if dyn_val>some, 
    # or "build_crossfade_sequence" if dyn_val<some...
    # For simplicity, let's do a single approach. You can adapt as needed.

    # Example: purely pixel crossfade
    frames = FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)
    for idx, fr in enumerate(frames):
      if writer is not None:
        writer.write(fr)
      if export_images:
        # you can store them with subfolder i info
        cv2.imwrite(os.path.join(out_folder, f"{file_tag}_subfade_{idx:03d}.png"), fr)

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
  def build_crossfade_sequence(imgA: np.ndarray, imgB: np.ndarray, steps: int) -> list:
    frames = []
    hA, wA, _ = imgA.shape
    hB, wB, _ = imgB.shape
    if (hA != hB) or (wA != wB):
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
    Formerly _build_fade_core. Returns (final_image, boundary_positions, filenames_at_boundaries)
    or None if no fade is built.
    """
    import cv2
    import numpy as np

    n = len(active_paths)
    if n < 2:
      return None

    final_result = np.zeros((height_total, width_total, 3), dtype=np.uint8)
    bounds = []
    filenames = []
    average_colors = []
    transitions = []

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
      return None  # no fade

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

      leftC = average_colors[i]
      rightC = average_colors[i+1]
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

    return (final_result, bounds, filenames)

  @staticmethod
  def build_global_subfolder_crossfade(ui_obj, steps: int) -> List[np.ndarray]:
    """
    Formerly _build_global_subfolder_crossfade, 
    but since it references data in ui_obj, we pass ui_obj here.
    Alternatively, we could pass subfolder_names, subfolder_data, etc.
    Returns a list of frames.
    """
    frames = []
    n_sub = len(ui_obj.subfolder_names)
    if n_sub < 1:
      return frames

    prev_data = None
    for i, sf in enumerate(ui_obj.subfolder_names):
      ui_obj._load_subfolder_images(i, auto_calc=False)
      # apply brightness filter if needed
      if ui_obj.brightness_slider.get() > 0:
        ui_obj._reset_checkboxes()
        thr = ui_obj.brightness_slider.get()
        for d in ui_obj.image_data:
          if d.brightness_value < thr:
            d.check_var.set(False)
      ui_obj._call_build_fade_core()
      if ui_obj.final_image is None:
        continue

      curr_data = ui_obj.subfolder_fade_info.get(sf, None)
      if not curr_data:
        frames.append(ui_obj.final_image.copy())
        prev_data = None
        continue

      if prev_data is None:
        frames.append(curr_data.final_image.copy())
      else:
        new_frames = FadingLogic.build_mix_crossfade(prev_data, curr_data, ui_obj.dynamic_slider.get(), steps)
        frames.extend(new_frames[1:])
      prev_data = curr_data
    return frames

  @staticmethod
  def build_mix_crossfade(
      fadeA: SubfolderFadeData,
      fadeB: SubfolderFadeData,
      dyn_val: float,
      steps: int
    ) -> List[np.ndarray]:
    """
    Formerly _build_mix_crossfade. 
    Mixes pixel fade and segment fade depending on dyn_val (0..100).
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
  def build_segment_interpolated_crossfade(fadeA: SubfolderFadeData, fadeB: SubfolderFadeData, steps: int) -> List[np.ndarray]:
    """
    Formerly _build_segment_interpolated_crossfade. 
    Uses vector approach with broadcasting.
    """
    frames = []
    hA, wA, _ = fadeA.final_image.shape
    hB, wB, _ = fadeB.final_image.shape
    if (hA != hB) or (wA != wB):
      return FadingLogic.build_crossfade_sequence(fadeA.final_image, fadeB.final_image, steps)

    import numpy as np
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
    hA2 = hA
    wA2 = wA

    for s in range(1, steps + 1):
      alpha = s / (steps + 1)
      curPos = (1 - alpha)*bposA + alpha*bposB
      colorArr = (1 - alpha)*arrA + alpha*arrB
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
    Formerly _blend_two_images. 
    Blends two images using cv2.addWeighted.
    """
    hA, wA, _ = imgA.shape
    hB, wB, _ = imgB.shape
    if (hA != hB) or (wA != wB):
      imgB = cv2.resize(imgB, (wA, hA))
    return cv2.addWeighted(imgA, 1.0 - alpha, imgB, alpha, 0)
