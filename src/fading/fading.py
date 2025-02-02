import os
import cv2
import re
import numpy as np
from typing import Tuple, List
from datamodel import SubfolderFadeData
from scipy.interpolate import CubicSpline

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
    export_images: bool,
    use_spline: bool = True
  ):
    """
    Performs an on-the-fly subfolder crossfade using a keyframe approach.
    
    Instead of performing separate crossfades for each subfolder transition, a global
    transition is created over all keyframes. The x-positions (segment boundaries) are
    interpolated using either a CubicSpline (if use_spline=True) or linear interpolation,
    while the average colors are interpolated linearly.
    
    Args:
      ui_obj: The UI object containing image data and subfolder info.
      writer: OpenCV VideoWriter to write the output video.
      steps: Number of intermediate frames per keyframe transition.
      progress_bar: Tkinter progress bar widget.
      diag: Tkinter dialog window for progress updates.
      out_folder: Output folder path.
      file_tag: File tag for naming output files.
      export_images: Boolean flag to export individual frame images.
      use_spline: Boolean flag to enable (True) or disable (False) spline interpolation for x positions.
    """
    n_sub = len(ui_obj.subfolder_names)
    if n_sub < 2:
      return

    # Dynamic segments slider (not used in this spline-based approach)
    dyn_val = ui_obj.dynamic_slider.get()

    # ---------------------------------------------------------------------
    # PHASE 1: PRECOMPUTE KEYFRAMES
    # ---------------------------------------------------------------------
    keyframes_data = []
    for i, sf in enumerate(ui_obj.subfolder_names):
      # Load subfolder i (without auto_calc for manual brightness filtering)
      ui_obj._load_subfolder_images(i, auto_calc=False)
      # Optional brightness filter if slider > 0
      if ui_obj.brightness_slider.get() > 0:
        ui_obj._reset_checkboxes()
        thr = ui_obj.brightness_slider.get()
        for d in ui_obj.image_data:
          if d.brightness_value < thr:
            d.check_var.set(False)
      # Build fade; this populates subfolder_fade_info[sf]
      ui_obj._call_build_fade_core()
      fadeData = ui_obj.subfolder_fade_info.get(sf, None)
      if fadeData is None:
        fadeData = SubfolderFadeData(
          final_image=ui_obj.final_image.copy(),
          boundary_positions=[],
          filenames_at_boundaries=[],
          average_colors=[],
          transitions=[]
        )
      keyframes_data.append(fadeData)
    if len(keyframes_data) < 2:
      return

    # ---------------------------------------------------------------------
    # PHASE 2: BUILD GLOBAL ANIMATION
    # ---------------------------------------------------------------------
    # Each keyframe is assumed to contain:
    #   - boundary_positions: list of x-coordinates for segment boundaries
    #   - average_colors: list of average color arrays (each of shape (h, 3))
    keyframe_times = np.linspace(0, 1, len(keyframes_data))
    n_boundaries = len(keyframes_data[0].boundary_positions)
    
    if use_spline:
      # Use CubicSpline for exact interpolation.
      boundary_splines = []
      for j in range(n_boundaries):
        positions = [keyframes_data[i].boundary_positions[j] for i in range(len(keyframes_data))]
        spline = CubicSpline(keyframe_times, positions)
        boundary_splines.append(spline)
    else:
      boundary_splines = None

    total_frames = steps * (len(keyframes_data) - 1)

    for f in range(total_frames + 1):
      t_global = f / total_frames

      # Interpolate x-positions for segment boundaries:
      if boundary_splines is not None:
        global_boundaries = [int(round(float(spline(t_global)))) for spline in boundary_splines]
      else:
        pos = t_global * (len(keyframes_data) - 1)
        i = int(np.floor(pos))
        local_t = pos - i
        if i >= len(keyframes_data) - 1:
          i = len(keyframes_data) - 2
          local_t = 1.0
        global_boundaries = [
          int(round((1 - local_t) * keyframes_data[i].boundary_positions[j] +
                    local_t * keyframes_data[i + 1].boundary_positions[j]))
          for j in range(n_boundaries)
        ]

      # Interpolate colors linearly between the two keyframes:
      pos = t_global * (len(keyframes_data) - 1)
      i = int(np.floor(pos))
      local_t = pos - i
      if i >= len(keyframes_data) - 1:
        i = len(keyframes_data) - 2
        local_t = 1.0
      global_avg_colors = []
      for j in range(n_boundaries):
        colorA = keyframes_data[i].average_colors[j]
        colorB = keyframes_data[i+1].average_colors[j]
        global_color = np.clip((1 - local_t) * colorA + local_t * colorB, 0, 255).astype(np.uint8)
        global_avg_colors.append(global_color)

      # Ensure boundaries cover the full image width.
      h, w, _ = keyframes_data[0].final_image.shape
      if global_boundaries[0] != 0:
        global_boundaries.insert(0, 0)
        global_avg_colors.insert(0, global_avg_colors[0])
      if global_boundaries[-1] != w:
        global_boundaries.append(w)
        global_avg_colors.append(global_avg_colors[-1])
      
      # Ensure that boundaries are strictly increasing.
      for idx in range(1, len(global_boundaries)):
        if global_boundaries[idx] <= global_boundaries[idx-1]:
          global_boundaries[idx] = global_boundaries[idx-1] + 1
          if global_boundaries[idx] > w:
            global_boundaries[idx] = w

      # Build the current frame using horizontal gradients between the interpolated colors.
      frame = np.zeros((h, w, 3), dtype=np.uint8)
      for j in range(len(global_boundaries) - 1):
        x0 = global_boundaries[j]
        x1 = global_boundaries[j + 1]
        seg_w = x1 - x0
        # # If segment width is less than 1 pixel, force a minimum of 1 pixel.
        # if seg_w < 1:
        #   seg_w = 1
        #   x1 = min(x0 + 1, w)
        left_color = global_avg_colors[j].reshape(h, 1, 3)
        right_color = global_avg_colors[j + 1].reshape(h, 1, 3)
        x_indices = np.linspace(0.0, 1.0, seg_w).reshape(1, seg_w, 1)
        grad = (1.0 - x_indices) * left_color + x_indices * right_color
        # Assign gradient only if the slice shape matches.
        if frame[:, x0:x1].shape[1] == grad.shape[1]:
          frame[:, x0:x1] = grad.astype(np.uint8)
      if writer is not None:
        writer.write(frame)
      if export_images:
        cv2.imwrite(os.path.join(out_folder, f"{file_tag}_global_{f:03d}.png"), frame)
      progress_bar['value'] = f
      diag.update_idletasks()
      
  @staticmethod
  def parse_utc_offset(filepath: str) -> float:
    """
    Parses the UTC offset from a file name.
    """
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
    """
    Returns a fallback image path for a missing offset.
    """
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
    """
    Returns the next available output subfolder path.
    """
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
    """
    Creates and returns a path to a dummy black image for a missing offset.
    """
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
    """
    Calculates the horizontal average of an image.
    """
    return np.mean(image, axis=1).astype(np.uint8)

  @staticmethod
  def generate_fading_gradient(colors_left: np.ndarray, colors_right: np.ndarray, width: int) -> np.ndarray:
    """
    Generates a horizontal gradient between two color arrays.
    """
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
    Performs a simple pixel-based crossfade by linearly blending imgA and imgB over 'steps' frames.
    """
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
    Creates a single horizontal fade from a set of active_paths.
    Returns a tuple (final_image, boundary_positions, filenames_at_boundaries, average_colors).
    If something fails (e.g., not enough paths), returns None.
    
    The influence_val affects how brightness influences the transition weighting.
    The damping_percent limits deviation from the original distribution.
    """
    if len(active_paths) < 2:
      return None
    final_result = np.zeros((height_total, width_total, 3), dtype=np.uint8)
    bounds = []
    filenames = []
    average_colors = []
    n = len(active_paths)
    loaded_colors = []
    for idx, path in enumerate(active_paths):
      img = cv2.imread(path)
      if img is None:
        dummy = np.zeros((10, 10, 3), dtype=np.uint8)
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
      grad = (1.0 - x_indices) * leftC_resh + x_indices * rightC_resh
      grad = grad.astype(np.uint8)
      final_result[:, x_start:x_end] = grad
      bounds.append(x_start)
      filenames.append((fname, is_proxy_flag))
      x_start = x_end
    last_name = os.path.basename(active_paths[-1])
    last_proxy = proxy_list[-1]
    bounds.append(width_total - 1)
    filenames.append((last_name, last_proxy))
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
    Performs a segment-based crossfade interpolation between two fades.
    
    If use_easing is True, a cubic ease-in-out function is applied to the interpolation parameter.
    Otherwise, a linear interpolation is used.
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
      alpha = ease_in_out_cubic(t) if use_easing else t
      alpha = max(0.0, min(1.0, alpha))
      curPos = (1.0 - alpha) * bposA + alpha * bposB
      colorArr = (1.0 - alpha) * arrA + alpha * arrB
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
        grad = (1.0 - x_indices) * leftC_resh + x_indices * rightC_resh
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
    
    If the sizes differ, imgB is resized to match imgA.
    """
    hA, wA, _ = imgA.shape
    hB, wB, _ = imgB.shape
    if (hA != hB) or (wA != wB):
      imgB = cv2.resize(imgB, (wA, hA))
    return cv2.addWeighted(imgA, 1.0 - alpha, imgB, alpha, 0)
