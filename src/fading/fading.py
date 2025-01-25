# fading.py

import cv2
import numpy as np
import os
import re
from typing import Tuple

class FadingLogic:
  """
  Holds all fading and crossfade related logic.
  """

  @staticmethod
  def parse_utc_offset(filepath: str) -> float:
    """
    Extracts a numeric UTC offset from filenames starting with 'UTC+...' or 'UTC-...'.
    If not found, returns 9999.
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
    Searches for a fallback image for a certain offset if the current subfolder doesn't have it.
    Returns (path, is_proxy).
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
    Creates a 'output' folder if needed, then returns the next available subfolder '001', '002', etc.
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
    Creates a small black dummy image in 'temp' folder with a name that indicates the offset.
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
    Calculates the horizontal average color for each row.
    """
    return np.mean(image, axis=1).astype(np.uint8)

  @staticmethod
  def generate_fading_gradient(colors_left: np.ndarray, colors_right: np.ndarray, width: int) -> np.ndarray:
    """
    Creates a horizontal gradient from colors_left to colors_right over 'width' columns.
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
  def build_crossfade_sequence(imgA: np.ndarray, imgB: np.ndarray, steps: int) -> list:
    """
    Builds frames to crossfade from imgA to imgB over 'steps' intermediate frames.
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
    Exports a list of frames as MP4 video at the given fps.
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
