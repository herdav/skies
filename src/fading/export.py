import os
import cv2
import numpy as np
from fading import FadingLogic

def perform_export(
  frames: list,
  out_folder: str,
  file_tag: str,
  fps: int,
  export_images: bool = True,
  export_video: bool = True
):
  """
  Blocking export in the main thread.
  Writes images if export_images is True,
  writes an MP4 video if export_video is True.
  """
  if not frames:
    return

  if not os.path.exists(out_folder):
    os.makedirs(out_folder)

  if export_images:
    for i, frm in enumerate(frames):
      cv2.imwrite(os.path.join(out_folder, f"{file_tag}_{i:03d}.png"), frm)

  if export_video:
    # Reuse FadingLogic.export_mpeg_video for writing MP4
    videoname = os.path.join(out_folder, f"{file_tag}.mp4")
    FadingLogic.export_mpeg_video(frames, videoname, fps)
