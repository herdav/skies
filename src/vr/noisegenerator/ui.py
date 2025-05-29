"""UI for the Noise Generator application."""

from __future__ import annotations

import json
from typing import List

import numpy as np
from PySide6 import QtCore, QtWidgets
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from audio import AudioEngine
from helpers import BANDS, SAMPLE_RATE, colour_beta, eq_magnitudes, rand_base


def set_dark(ax):
    """Apply dark styling to a matplotlib Axes."""
    ax.set_facecolor("#000000")
    ax.tick_params(colors="#cccccc")
    ax.xaxis.label.set_color("#ffffff")
    ax.yaxis.label.set_color("#ffffff")
    for spine in ax.spines.values():
        spine.set_edgecolor("#777777")
    ax.grid(True, which="both", color="#444444", alpha=0.6)


class MainWindow(QtWidgets.QMainWindow):
    """Main application window for the Noise Generator."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Noise Generator")
        self.engine = AudioEngine()
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)

        # Control column
        controls = QtWidgets.QVBoxLayout()
        root.addLayout(controls)

        # Noise colour
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["white", "pink", "brown", "blue", "violet", "custom β"])
        controls.addWidget(self.type_combo)

        # β-slider (hidden by default)
        self.beta_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)  # type: ignore
        self.beta_slider.setRange(-20, 20)  # −2 … +2
        self.beta_slider.setValue(0)
        self.beta_slider.hide()
        controls.addWidget(self.beta_slider)

        # Distribution selector
        controls.addWidget(QtWidgets.QLabel("Distribution"))
        self.dist_combo = QtWidgets.QComboBox()
        self.dist_combo.addItems(["uniform", "normal", "laplace", "cauchy"])
        controls.addWidget(self.dist_combo)

        # Block size selector
        controls.addWidget(QtWidgets.QLabel("Block size"))
        self.block_combo = QtWidgets.QComboBox()
        self.block_combo.addItems(["256", "512", "1024", "2048", "4096"])
        self.block_combo.setCurrentText("1024")
        controls.addWidget(self.block_combo)

        # Cross-fade slider
        controls.addWidget(QtWidgets.QLabel("Cross-fade %"))
        self.fade_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)  # type: ignore
        self.fade_slider.setRange(0, 100)
        self.fade_slider.setValue(0)
        controls.addWidget(self.fade_slider)

        # Volume
        controls.addWidget(QtWidgets.QLabel("Volume"))
        self.vol_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)  # type: ignore
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(50)
        controls.addWidget(self.vol_slider)

        # EQ
        eq_group = QtWidgets.QGroupBox("10-Band EQ (dB)")
        eq_layout = QtWidgets.QHBoxLayout(eq_group)
        self.eq_sliders: List[QtWidgets.QSlider] = []
        for low, high in BANDS:
            box = QtWidgets.QVBoxLayout()
            slider = QtWidgets.QSlider(QtCore.Qt.Vertical)  # type: ignore
            slider.setRange(-12, 12)
            slider.setValue(0)
            slider.setFixedWidth(28)
            self.eq_sliders.append(slider)
            label = QtWidgets.QLabel(f"{low}\n{high}")
            label.setAlignment(QtCore.Qt.AlignHCenter)  # type: ignore
            box.addWidget(slider, 1)
            box.addWidget(label)
            eq_layout.addLayout(box)
        controls.addWidget(eq_group)

        self.reset_eq_btn = QtWidgets.QPushButton("Reset EQ")
        controls.addWidget(self.reset_eq_btn)

        # Play / Stop
        play_row = QtWidgets.QHBoxLayout()
        self.play_btn = QtWidgets.QPushButton("Play")
        self.stop_btn = QtWidgets.QPushButton("Stop")
        play_row.addWidget(self.play_btn)
        play_row.addWidget(self.stop_btn)
        controls.addLayout(play_row)

        # WAV-Export
        export_row = QtWidgets.QHBoxLayout()
        self.export_btn = QtWidgets.QPushButton("Export WAV")
        self.len_spin = QtWidgets.QSpinBox()
        self.len_spin.setRange(1, 600)
        self.len_spin.setValue(30)
        export_row.addWidget(self.export_btn)
        export_row.addWidget(QtWidgets.QLabel("sec"))
        export_row.addWidget(self.len_spin)
        controls.addLayout(export_row)

        # Preset save / load
        preset_row = QtWidgets.QHBoxLayout()
        self.save_preset_btn = QtWidgets.QPushButton("Save Preset")
        self.load_preset_btn = QtWidgets.QPushButton("Load Preset")
        preset_row.addWidget(self.save_preset_btn)
        preset_row.addWidget(self.load_preset_btn)
        controls.addLayout(preset_row)

        # Plot
        fig = Figure(figsize=(5, 4), facecolor="#000000")
        self.canvas = FigureCanvas(fig)
        root.addWidget(self.canvas, 2)

        self.ax = fig.add_subplot(111)
        set_dark(self.ax)
        self.ax.set_xscale("log")
        self.ax.set_xlim(20, 20_000)
        self.ax.set_ylim(-60, 60)
        self.ax.set_xlabel("Frequency [Hz]")
        self.ax.set_ylabel("dB")

        freqs = np.fft.rfftfreq(self.engine.block_size, 1 / SAMPLE_RATE)
        (self.spec_line,) = self.ax.plot(freqs, np.full_like(freqs, -60), color="#00ff80")
        (self.eq_line,) = self.ax.plot(freqs, np.zeros_like(freqs), color="#0080ff")

        # Signal wiring
        self.type_combo.currentTextChanged.connect(self._update_visibility)
        self.beta_slider.valueChanged.connect(self._push_params)
        self.dist_combo.currentTextChanged.connect(self._push_params)
        self.block_combo.currentTextChanged.connect(self._change_block_size)
        self.fade_slider.valueChanged.connect(self._push_params)
        self.vol_slider.valueChanged.connect(self._push_params)
        for s in self.eq_sliders:
            s.valueChanged.connect(self._push_params)
        self.reset_eq_btn.clicked.connect(self._reset_eq)

        self.play_btn.clicked.connect(self._start_audio)
        self.stop_btn.clicked.connect(self._stop_audio)
        self.export_btn.clicked.connect(self._export_wav)
        self.save_preset_btn.clicked.connect(self._save_preset)
        self.load_preset_btn.clicked.connect(self._load_preset)

        # Live-spectrum timer
        timer = QtCore.QTimer(self)
        timer.setInterval(80)  # ≈12.5 fps
        timer.timeout.connect(self._update_spectrum)
        timer.start()

        self._update_visibility()  # initial push

    # --- Parameter handling ---
    def _update_visibility(self) -> None:
        self.beta_slider.setVisible(self.type_combo.currentText() == "custom β")
        self._push_params()

    def _push_params(self) -> None:
        noise_type = (
            "beta" if self.type_combo.currentText() == "custom β" else self.type_combo.currentText()
        )
        self.engine.update_params(
            noise_type=noise_type,
            beta=self.beta_slider.value() / 10.0,
            dist=self.dist_combo.currentText(),
            fade_pct=self.fade_slider.value(),
            volume=self.vol_slider.value() / 100.0,
            eq_gains=[s.value() for s in self.eq_sliders],
        )
        self._update_eq_curve()

    def _change_block_size(self) -> None:
        self.engine.set_block_size(int(self.block_combo.currentText()))
        self._push_params()

    def _reset_eq(self) -> None:
        for s in self.eq_sliders:
            s.setValue(0)
        self._push_params()

    # --- Audio control ---
    def _start_audio(self) -> None:
        self._push_params()
        self.engine.start()
        self.play_btn.setStyleSheet("background:#d22;color:#ffffff")

    def _stop_audio(self) -> None:
        self.engine.stop()
        self.play_btn.setStyleSheet("")

    # --- Plots ---
    def _update_eq_curve(self) -> None:
        mag = eq_magnitudes([s.value() for s in self.eq_sliders], self.engine.block_size)
        freqs = np.fft.rfftfreq(self.engine.block_size, 1 / SAMPLE_RATE)
        self.eq_line.set_data(freqs, 20 * np.log10(mag + 1e-12))
        self.canvas.draw_idle()

    def _update_spectrum(self) -> None:
        if not self.engine.stream.active:
            return
        block = self.engine.last_block()
        spectrum = np.abs(np.fft.rfft(block))
        db = 20 * np.log10(spectrum + 1e-12)
        freqs = np.fft.rfftfreq(len(block), 1 / SAMPLE_RATE)
        self.spec_line.set_data(freqs, db)
        self.canvas.draw_idle()

    # --- Export / presets ---
    def _export_wav(self) -> None:
        from scipy.io import wavfile

        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save WAV", ".", "WAV files (*.wav)")
        if not path:
            return

        seconds = self.len_spin.value()
        total = seconds * SAMPLE_RATE
        beta = self.beta_slider.value() / 10.0
        dist = self.dist_combo.currentText()
        colour = self.type_combo.currentText()
        gains = [s.value() for s in self.eq_sliders]
        mag = eq_magnitudes(gains, self.engine.block_size)

        buf = np.empty(total, dtype=np.float32)
        pos = 0
        while pos < total:
            n = min(self.engine.block_size, total - pos)
            if colour == "white":
                block = rand_base(n, dist)
            elif colour == "pink":
                block = colour_beta(rand_base(n, dist), -1.0)
            elif colour == "brown":
                block = colour_beta(rand_base(n, dist), -2.0)
            elif colour == "blue":
                block = colour_beta(rand_base(n, dist), +1.0)
            elif colour == "violet":
                block = colour_beta(rand_base(n, dist), +2.0)
            else:
                block = colour_beta(rand_base(n, dist), beta)
            block = np.fft.irfft(np.fft.rfft(block) * mag[: len(np.fft.rfft(block))], n)
            buf[pos : pos + n] = block
            pos += n

        wavfile.write(path, SAMPLE_RATE, buf)

    def _save_preset(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Preset", ".", "Preset (*.json)")
        if not path:
            return
        preset = {
            "type": self.type_combo.currentText(),
            "beta": self.beta_slider.value(),
            "dist": self.dist_combo.currentText(),
            "block": self.block_combo.currentText(),
            "fade": self.fade_slider.value(),
            "volume": self.vol_slider.value(),
            "gains": [s.value() for s in self.eq_sliders],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(preset, fh, indent=2)

    def _load_preset(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Preset", ".", "Preset (*.json)")
        if not path:
            return
        with open(path, "r", encoding="utf-8") as fh:
            p = json.load(fh)

        self.type_combo.setCurrentText(p.get("type", "white"))
        self.beta_slider.setValue(p.get("beta", 0))
        self.dist_combo.setCurrentText(p.get("dist", "uniform"))
        self.block_combo.setCurrentText(p.get("block", "1024"))
        self.fade_slider.setValue(p.get("fade", 0))
        self.vol_slider.setValue(p.get("volume", 50))
        for s, g in zip(self.eq_sliders, p.get("gains", [0] * 10)):
            s.setValue(g)
        self._push_params()
