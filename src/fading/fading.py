# fading.py

import cv2
import numpy as np
import os
import re
from typing import Tuple

class FadingLogic:
    # Parse UTC offset from filename
    @staticmethod
    def parse_utc_offset(filepath: str) -> float:
        # Match filenames like UTC+2.5 or UTC-1
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

    # Fallback if subfolder i lacks offset
    @staticmethod
    def fallback_for_offset(i: int, offset: float, subfolder_names: list, subfolder_data: dict) -> Tuple[str, bool]:
        # If first subfolder
        if i == 0:
            for k in range(1, len(subfolder_names)):
                om = subfolder_data[subfolder_names[k]]
                if offset in om:
                    return om[offset][0], True
            return FadingLogic.create_black_dummy_image(offset), True

        # If last subfolder
        if i == len(subfolder_names) - 1:
            for k in range(len(subfolder_names) - 2, -1, -1):
                om = subfolder_data[subfolder_names[k]]
                if offset in om:
                    return om[offset][0], True
            return FadingLogic.create_black_dummy_image(offset), True

        # If in the middle
        for k in range(i + 1, len(subfolder_names)):
            om = subfolder_data[subfolder_names[k]]
            if offset in om:
                return om[offset][0], True
        for k in range(i - 1, -1, -1):
            om = subfolder_data[subfolder_names[k]]
            if offset in om:
                return om[offset][0], True

        # No fallback found
        return FadingLogic.create_black_dummy_image(offset), True

    # Create new subfolder for outputs
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

    # Create black dummy image for fallback
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

    # Calculate horizontal average
    @staticmethod
    def calculate_horizontal_average(image: np.ndarray) -> np.ndarray:
        return np.mean(image, axis=1).astype(np.uint8)

    # Generate a horizontal gradient via vectorized approach
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

    # Build crossfade frames
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

    # Export frames as MP4
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
