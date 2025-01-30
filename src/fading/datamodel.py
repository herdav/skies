from dataclasses import dataclass
from typing import List
import tkinter as tk
import numpy as np

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
