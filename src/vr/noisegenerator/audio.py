"""Audio engine for generating and pProcessing noise signals."""

from __future__ import annotations
import threading
import numpy as np

import sounddevice as sd

from helpers import (
    SAMPLE_RATE,
    rand_base,
    colour_beta,
    blue_noise,
    violet_noise,
    pink_noise,
    brown_noise,
    eq_magnitudes,
    apply_eq,
)

LIMIT_ATTACK = 0.1
LIMIT_RELEASE = 0.005


class AudioEngine:
    def __init__(self) -> None:
        # user-visible params
        self.block_size = 1024
        self.fade_pct = 0.0
        self.volume = 0.5  # 50 %
        self.noise_type = "white"
        self.beta = 0.0
        self.dist = "uniform"
        self.eq_gains = [0] * 10

        # internals
        self._pink_state = None
        self._brown_last = 0.0
        self._mag: np.ndarray | None = None
        self._mag_dirty = True
        self._prev_block: np.ndarray | None = None
        self._last_block = np.zeros(self.block_size, dtype=np.float32)
        self._lock = threading.Lock()
        self._gain = 1.0

        self._create_stream()

    def _create_stream(self):
        self.stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            blocksize=self.block_size,
            dtype="float32",
            callback=self._callback,
        )

    def set_block_size(self, size: int) -> None:
        if size == self.block_size:
            return
        active = self.stream.active
        self.stream.stop()
        self.block_size = size
        with self._lock:
            self._prev_block = None
            self._last_block = np.zeros(size, dtype=np.float32)
            self._mag_dirty = True
        self._create_stream()
        if active:
            self.stream.start()

    def update_params(self, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                if not hasattr(self, k):
                    continue
                if getattr(self, k) != v:
                    setattr(self, k, v)
                    if k == "eq_gains":
                        self._mag_dirty = True
                    if k == "fade_pct":
                        self._prev_block = None  # skip one blend

    def start(self):
        self.stream.start()

    def stop(self):
        self.stream.stop()

    def _callback(self, out, frames, _time, status):
        if status:
            print("sounddevice:", status)

        # Atomic snapshot
        with self._lock:
            vol = self.volume
            ntype = self.noise_type
            beta = self.beta
            dist = self.dist
            gains = self.eq_gains.copy()
            fade_pct = self.fade_pct
            prev_blk = None if self._prev_block is None else self._prev_block.copy()
            mag_dirty = self._mag_dirty
            self._mag_dirty = False  # will rebuild now if needed

        # Magnitude rebuild
        rfft_len = frames // 2 + 1
        if mag_dirty or self._mag is None or len(self._mag) != rfft_len:
            self._mag = eq_magnitudes(gains, frames)

        # Noise gen
        if ntype == "white":
            block = rand_base(frames, dist)
        elif ntype == "pink":
            block, self._pink_state = pink_noise(frames, self._pink_state, dist)
        elif ntype == "brown":
            block, self._brown_last = brown_noise(frames, self._brown_last, dist)
        elif ntype == "blue":
            block = blue_noise(frames, dist)
        elif ntype == "violet":
            block = violet_noise(frames, dist)
        else:
            block = colour_beta(rand_base(frames, dist), beta)

        block = apply_eq(block, self._mag)

        #  Cross-fade
        overlap = int(frames * fade_pct / 100)
        if overlap > 0 and prev_blk is not None:
            overlap = min(overlap, frames, len(prev_blk))
            if overlap > 0:
                fade = np.linspace(0, 1, overlap, dtype=np.float32)
                block[:overlap] = prev_blk[-overlap:] * (1 - fade) + block[:overlap] * fade

        # Store current block atomically
        with self._lock:
            self._prev_block = block.copy()
            self._last_block = block.copy()

        #  Output
        peak = np.max(np.abs(block))
        target = 1.0 / max(1.0, peak)  # normalize to prevent clipping
        if target < self._gain:
            self._gain += LIMIT_RELEASE * (target - self._gain)
        else:
            self._gain += LIMIT_ATTACK * (target - self._gain)
        block *= self._gain

        out[:] = (block * vol).reshape(-1, 1)

    def last_block(self) -> np.ndarray:
        with self._lock:
            return self._last_block.copy()
