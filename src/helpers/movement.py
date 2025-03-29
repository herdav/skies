import tkinter as tk
from tkinter import filedialog, messagebox
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from numba import njit, prange


@njit(parallel=True)
def compute_segments_numba(boundaries):
    num_boundaries, n_frames = boundaries.shape
    segments = np.empty((num_boundaries - 1, n_frames), dtype=boundaries.dtype)
    for i in prange(num_boundaries - 1):
        for j in range(n_frames):
            segments[i, j] = (boundaries[i, j] + boundaries[i + 1, j]) / 2
    return segments


@njit(parallel=True)
def compute_bandwidth_numba(boundaries):
    num_boundaries, n_frames = boundaries.shape
    bandwidth = np.empty((num_boundaries - 1, n_frames), dtype=boundaries.dtype)
    for i in prange(num_boundaries - 1):
        for j in range(n_frames):
            bandwidth[i, j] = boundaries[i + 1, j] - boundaries[i, j]
    return bandwidth


@njit()
def compute_cumsum_bandwidth_numba(bandwidth):
    n_segments, n_frames = bandwidth.shape
    cumsum = np.empty((n_segments + 1, n_frames), dtype=bandwidth.dtype)
    for j in prange(n_frames):
        cumsum[0, j] = 0
    for i in prange(n_segments):
        for j in range(n_frames):
            cumsum[i + 1, j] = cumsum[i, j] + bandwidth[i, j]
    return cumsum


class MovementData:
    """
    Handles loading data from JSON and computing segments, bandwidth and cumulative bandwidth.
    """

    def __init__(self):
        self.frame_indices = None  # 1D array of frame indices
        self.boundaries = None  # 2D array with shape (num_boundaries, n_frames)
        self.total_frames = None
        self.width = None
        self.num_boundaries = 0
        self.cache = {}  # Cache for computed arrays

    def load_from_json(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        movement_data = data.get("movement_data", [])
        if not movement_data:
            raise ValueError("No movement data found in JSON.")
        self.total_frames = data.get("total_frames")
        self.width = data.get("width")
        self.num_boundaries = len(movement_data[0].get("boundaries", []))
        boundaries_list = [[] for _ in range(self.num_boundaries)]
        frame_indices = []
        for entry in movement_data:
            frame_indices.append(entry.get("frame"))
            b_vals = entry.get("boundaries", [])
            for j in range(self.num_boundaries):
                boundaries_list[j].append(b_vals[j])
        self.frame_indices = np.array(frame_indices)
        self.boundaries = np.array([np.array(lst) for lst in boundaries_list])
        self.cache.clear()

    def compute_segments(self):
        """Compute segments using Numba parallelization (midpoint between adjacent boundaries)."""
        if self.boundaries is None:
            return None
        if "segments" not in self.cache:
            self.cache["segments"] = compute_segments_numba(self.boundaries)
        return self.cache["segments"]

    def compute_bandwidth(self):
        """Compute bandwidth using Numba parallelization (difference between adjacent boundaries)."""
        if self.boundaries is None:
            return None
        if "bandwidth" not in self.cache:
            self.cache["bandwidth"] = compute_bandwidth_numba(self.boundaries)
        return self.cache["bandwidth"]

    def compute_cumsum_bandwidth(self):
        """Compute cumulative bandwidth using Numba parallelization for stacking."""
        if self.boundaries is None:
            return None
        n_frames = len(self.frame_indices)
        if "cumsum_bandwidth" not in self.cache:
            bw = self.compute_bandwidth()  # shape (num_boundaries-1, n_frames)
            self.cache["cumsum_bandwidth"] = compute_cumsum_bandwidth_numba(bw)
        return self.cache["cumsum_bandwidth"]


class MovementDataViewer:
    """
    Handles GUI elements, user interactions, and plotting.
    """

    def __init__(self, master):
        self.master = master
        self.master.title("Movement Data Viewer")
        self.data = MovementData()
        self.use_colormap = False

        # Lists for checkboxes (Boundaries, Segments, Bandwidth)
        self.boundary_vars = []
        self.segment_vars = []
        self.bandwidth_vars = []

        self.canvas = None
        self.toolbar = None

        self.build_gui()

    def build_gui(self):
        # Create left control panel and right plot area
        self.controls_frame = tk.Frame(self.master)
        self.controls_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        self.top_controls = tk.Frame(self.controls_frame)
        self.top_controls.pack(fill=tk.X)
        tk.Button(self.top_controls, text="Import JSON", command=self.import_json).pack(
            pady=5
        )
        self.btn_colormap = tk.Button(
            self.top_controls, text="Colormap: Off", command=self.toggle_colormap
        )
        self.btn_colormap.pack(pady=5)

        # Three columns for Boundaries, Segments, Bandwidth
        self.check_frames = tk.Frame(self.controls_frame)
        self.check_frames.pack(fill=tk.BOTH, expand=True)
        # Boundaries column
        self.boundaries_frame = tk.Frame(self.check_frames, bd=2, relief="groove")
        self.boundaries_frame.grid(row=0, column=0, padx=5, pady=5, sticky="n")
        tk.Label(self.boundaries_frame, text="Boundaries").pack()
        self.boundaries_check_frame = tk.Frame(self.boundaries_frame)
        self.boundaries_check_frame.pack()
        # Segments column
        self.segments_frame = tk.Frame(self.check_frames, bd=2, relief="groove")
        self.segments_frame.grid(row=0, column=1, padx=5, pady=5, sticky="n")
        tk.Label(self.segments_frame, text="Segments").pack()
        self.segments_check_frame = tk.Frame(self.segments_frame)
        self.segments_check_frame.pack()
        # Bandwidth column
        self.bandwidth_frame = tk.Frame(self.check_frames, bd=2, relief="groove")
        self.bandwidth_frame.grid(row=0, column=2, padx=5, pady=5, sticky="n")
        tk.Label(self.bandwidth_frame, text="Bandwidth").pack()
        self.bandwidth_check_frame = tk.Frame(self.bandwidth_frame)
        self.bandwidth_check_frame.pack()

        self.plot_frame = tk.Frame(self.master)
        self.plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

    def toggle_colormap(self):
        self.use_colormap = not self.use_colormap
        self.btn_colormap.config(
            text=f"Colormap: {'On' if self.use_colormap else 'Off'}"
        )
        self.draw_plot()

    def import_json(self):
        filepath = filedialog.askopenfilename(
            title="Select JSON File", filetypes=[("JSON Files", "*.json")]
        )
        if not filepath:
            return
        try:
            self.data.load_from_json(filepath)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        # Clear and recreate checkboxes for the three columns
        for widget in self.boundaries_check_frame.winfo_children():
            widget.destroy()
        for widget in self.segments_check_frame.winfo_children():
            widget.destroy()
        for widget in self.bandwidth_check_frame.winfo_children():
            widget.destroy()
        self.boundary_vars.clear()
        self.segment_vars.clear()
        self.bandwidth_vars.clear()

        # Boundaries column: All/None buttons and numbered checkboxes (default off)
        b_btn_frame = tk.Frame(self.boundaries_check_frame)
        b_btn_frame.pack(fill=tk.X, pady=2)
        tk.Button(b_btn_frame, text="All", command=self.select_all_boundaries).pack(
            side=tk.LEFT, padx=2
        )
        tk.Button(b_btn_frame, text="None", command=self.deselect_boundaries).pack(
            side=tk.LEFT, padx=2
        )
        for j in range(self.data.num_boundaries):
            var = tk.BooleanVar(value=False)
            self.boundary_vars.append(var)
            tk.Checkbutton(
                self.boundaries_check_frame,
                text=str(j),
                variable=var,
                command=self.draw_plot,
            ).pack(anchor="w")

        # Segments column: default off
        if self.data.num_boundaries > 1:
            s_btn_frame = tk.Frame(self.segments_check_frame)
            s_btn_frame.pack(fill=tk.X, pady=2)
            tk.Button(s_btn_frame, text="All", command=self.select_all_segments).pack(
                side=tk.LEFT, padx=2
            )
            tk.Button(s_btn_frame, text="None", command=self.deselect_segments).pack(
                side=tk.LEFT, padx=2
            )
            for j in range(self.data.num_boundaries - 1):
                var = tk.BooleanVar(value=False)
                self.segment_vars.append(var)
                tk.Checkbutton(
                    self.segments_check_frame,
                    text=str(j),
                    variable=var,
                    command=self.draw_plot,
                ).pack(anchor="w")

        # Bandwidth column: default on
        if self.data.num_boundaries > 1:
            bw_btn_frame = tk.Frame(self.bandwidth_check_frame)
            bw_btn_frame.pack(fill=tk.X, pady=2)
            tk.Button(bw_btn_frame, text="All", command=self.select_all_bandwidth).pack(
                side=tk.LEFT, padx=2
            )
            tk.Button(bw_btn_frame, text="None", command=self.deselect_bandwidth).pack(
                side=tk.LEFT, padx=2
            )
            for j in range(self.data.num_boundaries - 1):
                var = tk.BooleanVar(value=True)
                self.bandwidth_vars.append(var)
                tk.Checkbutton(
                    self.bandwidth_check_frame,
                    text=str(j),
                    variable=var,
                    command=self.draw_plot,
                ).pack(anchor="w")
        self.draw_plot()

    def select_all_boundaries(self):
        for var in self.boundary_vars:
            var.set(True)
        self.draw_plot()

    def deselect_boundaries(self):
        for var in self.boundary_vars:
            var.set(False)
        self.draw_plot()

    def select_all_segments(self):
        for var in self.segment_vars:
            var.set(True)
        self.draw_plot()

    def deselect_segments(self):
        for var in self.segment_vars:
            var.set(False)
        self.draw_plot()

    def select_all_bandwidth(self):
        for var in self.bandwidth_vars:
            var.set(True)
        self.draw_plot()

    def deselect_bandwidth(self):
        for var in self.bandwidth_vars:
            var.set(False)
        self.draw_plot()

    def draw_plot(self):
        if self.data.frame_indices is None:
            return

        for widget in self.plot_frame.winfo_children():
            widget.destroy()

        fig, ax = plt.subplots(figsize=(8, 6))
        # Remove title and axis labels
        ax.set_title("")
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.set_xlim(0, self.data.total_frames)
        ax.set_ylim(0, self.data.width)
        num_boundaries = self.data.num_boundaries
        frame_indices = self.data.frame_indices

        # Plot Boundaries
        for j in range(num_boundaries):
            if not self.boundary_vars[j].get():
                continue
            y_values = self.data.boundaries[j]
            if self.use_colormap:
                baseline = y_values[0]
                deviations = np.abs(y_values - baseline)
                max_abs = np.max(deviations)
                norm = (
                    deviations / max_abs if max_abs != 0 else np.zeros_like(deviations)
                )
                colors = plt.cm.viridis(norm)
                ax.scatter(frame_indices, y_values, c=colors, s=4)
            else:
                color = plt.get_cmap("tab10")(j % 10)
                ax.scatter(frame_indices, y_values, color=color, s=4)

        # Plot Segments
        if num_boundaries > 1:
            segments = self.data.compute_segments()
            for j in range(segments.shape[0]):
                if not self.segment_vars[j].get():
                    continue
                seg = segments[j]
                if self.use_colormap:
                    baseline = seg[0]
                    deviations = np.abs(seg - baseline)
                    max_abs = np.max(deviations)
                    norm = (
                        deviations / max_abs
                        if max_abs != 0
                        else np.zeros_like(deviations)
                    )
                    colors = plt.cm.viridis(norm)
                    ax.scatter(frame_indices, seg, c=colors, s=4)
                else:
                    color = plt.get_cmap("tab10")((j + 5) % 10)
                    ax.scatter(frame_indices, seg, color=color, s=4)

        # Plot Bandwidth as stacked bar chart (vectorized)
        if num_boundaries > 1:
            bw = self.data.compute_bandwidth()  # shape: (n_segments, n_frames)
            cumsum_bw = (
                self.data.compute_cumsum_bandwidth()
            )  # shape: (n_segments+1, n_frames)
            n_frames = len(frame_indices)
            threshold = 1000
            if n_frames > threshold:
                ds_factor = n_frames // threshold
                ds_indices = np.arange(0, n_frames, ds_factor)
            else:
                ds_indices = np.arange(n_frames)
            ds_frame_indices = frame_indices[ds_indices]
            # Calculate bar width so that bars are adjacent
            if len(ds_frame_indices) > 1:
                bar_width = ds_frame_indices[1] - ds_frame_indices[0]
            else:
                bar_width = 1.0
            for j in range(bw.shape[0]):
                if not self.bandwidth_vars[j].get():
                    continue
                ds_bw = bw[j, ds_indices]
                ds_bottom = cumsum_bw[j, ds_indices]
                if self.use_colormap:
                    baseline = ds_bw[0]
                    deviations = np.abs(ds_bw - baseline)
                    max_abs = np.max(deviations)
                    norm = (
                        deviations / max_abs
                        if max_abs != 0
                        else np.zeros_like(deviations)
                    )
                    colors = plt.cm.viridis(norm)
                    ax.bar(
                        ds_frame_indices,
                        ds_bw,
                        bottom=ds_bottom,
                        color=colors,
                        width=bar_width,
                        align="edge",
                        alpha=0.7,
                    )
                else:
                    color = plt.get_cmap("tab10")((j + 2) % 10)
                    ax.bar(
                        ds_frame_indices,
                        ds_bw,
                        bottom=ds_bottom,
                        color=color,
                        width=bar_width,
                        align="edge",
                        alpha=0.7,
                    )

        fig.tight_layout()
        self.canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.plot_frame)
        self.toolbar.update()
        self.canvas._tkcanvas.pack(fill=tk.BOTH, expand=True)


if __name__ == "__main__":
    root = tk.Tk()
    viewer = MovementDataViewer(root)
    root.mainloop()
