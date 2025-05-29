"""Helpers for audio processing tasks."""

from __future__ import annotations
import numpy as np
from scipy import signal

SAMPLE_RATE = 44_100


def rand_base(n: int, dist: str = "uniform") -> np.ndarray:
    """Generate a random base signal of length n."""
    if dist == "uniform":
        x = np.random.uniform(-1.0, 1.0, n)
    elif dist == "normal":
        x = np.random.normal(0.0, 1.0, n)
    elif dist == "laplace":
        x = np.random.laplace(0.0, 1.0, n)
    elif dist == "cauchy":
        x = np.tanh(np.random.standard_cauchy(n))  # tame huge tails
    else:
        raise ValueError(dist)
    return x.astype(np.float32)


def colour_beta(x: np.ndarray, beta: float) -> np.ndarray:
    """Colour a signal with a power-law filter."""
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SAMPLE_RATE)
    with np.errstate(divide="ignore"):
        spec *= np.where(freqs == 0, 0, freqs ** (beta / 2))
    y = np.fft.irfft(spec, len(x))
    return y / (np.max(np.abs(y)) + 1e-12)


def blue_noise(n, d="uniform"):
    """Generate blue noise, which has a power spectral density that increases with frequency."""
    return colour_beta(rand_base(n, d), +1)


def violet_noise(n, d="uniform"):
    """Generate violet noise, which has a power spectral density that increases with frequency squared."""
    return colour_beta(rand_base(n, d), +2)


PINK_B = [0.049922035, 0.050612699, 0.050612699, 0.049922035]
PINK_A = [1, -2.494956002, 2.017265875, -0.5221894]


def pink_noise(n, zi=None, d="uniform"):
    """Generate pink noise, which has a power spectral density that decreases with frequency."""
    x = rand_base(n, d)
    if zi is None:
        zi = signal.lfilter_zi(PINK_B, PINK_A)
    y, zf = signal.lfilter(PINK_B, PINK_A, x, zi=zi)
    return y / (np.max(np.abs(y)) + 1e-12), zf


def brown_noise(n, last=0.0, d="uniform"):
    """Generate brown noise, which has a power spectral density that decreases with frequency squared."""
    y = np.cumsum(rand_base(n, d)) + last
    y -= np.mean(y)
    return y / (np.max(np.abs(y)) + 1e-12), y[-1]


# --- Equalizer ---
BANDS = [
    (20, 60),
    (60, 120),
    (120, 250),
    (250, 500),
    (500, 1_000),
    (1_000, 2_000),
    (2_000, 4_000),
    (4_000, 6_000),
    (6_000, 10_000),
    (10_000, 20_000),
]


def eq_magnitudes(gain_db, n_fft):
    """Calculate equalizer magnitudes for given gain in dB."""
    freqs = np.fft.rfftfreq(n_fft, 1 / SAMPLE_RATE)
    log_f = np.log10(freqs + 1e-12)
    centres = np.log10([np.sqrt(lo * hi) for lo, hi in BANDS])
    gains = np.interp(log_f, centres, gain_db, left=gain_db[0], right=gain_db[-1])
    return 10 ** (gains / 20)


def apply_eq(block, mags):
    """Apply equalization to a block of audio data using given magnitudes."""
    spec = np.fft.rfft(block) * mags[: len(np.fft.rfft(block))]
    y = np.fft.irfft(spec, len(block))
    return y / (np.max(np.abs(y)) + 1e-12)


# --- Cross-fade window ---
def hann_fade(n):
    """Generate a Hann window for cross-fading."""
    fade = 0.5 * (1 - np.cos(2 * np.pi * np.arange(n) / (n - 1)))
    return fade.astype(np.float32), (1 - fade).astype(np.float32)
