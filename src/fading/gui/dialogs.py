import os
import tkinter as tk
from tkinter import ttk


class AboutDialog(tk.Toplevel):
    """
    A simple dialog for the 'About' information.
    """

    def __init__(self, master, bg_color="#dcdcdc", *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.title("About")
        self.configure(bg=bg_color)
        self.geometry("320x160")

        text_about = tk.Text(
            self, wrap="word", bg=bg_color, fg="black", width=60, height=10
        )
        text_about.pack(side="top", padx=20, pady=20, fill="both", expand=True)
        text_about.tag_configure("bold", font=("Arial", 10, "bold"))
        text_about.tag_configure("link", foreground="blue", underline=True)

        def open_link():
            import webbrowser

            webbrowser.open_new("https://davidherren.ch")

        def link_enter(evt):
            text_about.config(cursor="hand2")

        def link_leave(evt):
            text_about.config(cursor="arrow")

        text_about.tag_bind("link", "<Button-1>", lambda e: open_link())
        text_about.tag_bind("link", "<Enter>", link_enter)
        text_about.tag_bind("link", "<Leave>", link_leave)

        text_about.insert("1.0", "Horizontal Fading\n", "bold")
        text_about.insert("end", "Version 1.0\n\n")
        text_about.insert("end", "https://davidherren.ch\n\n", "link")
        text_about.insert("end", "Copyright © 2025 by David Herren.")
        text_about.config(state="disabled")

        close_btn = tk.Button(self, text="Close", bg=bg_color, command=self.destroy)
        close_btn.pack(side="bottom", padx=10, pady=10)


class ExportVideoDialog(tk.Toplevel):
    """
    A dialog for crossfade-video export. Collects parameters
    and calls fade_controller.export_crossfade_video or similar.
    """

    def __init__(
        self,
        master,
        controller,
        subfolder_manager,
        ffmpeg_path,
        width,
        height,
        default_crosfades=100,
        *args,
        **kwargs,
    ):
        super().__init__(master, *args, **kwargs)
        self.master = master
        self.controller = controller
        self.subfolder_manager = subfolder_manager
        self.ffmpeg_path = ffmpeg_path
        self.width = width
        self.height = height

        self.title("Export Video")
        self.configure(bg="#dcdcdc")

        # Subfolder combos
        tk.Label(
            self, text=f"Resolution: {width}x{height}px", bg="#dcdcdc", fg="blue"
        ).pack(side="top", padx=5, pady=5)

        frame_sub = tk.Frame(self, bg="#dcdcdc")
        frame_sub.pack(side="top", fill="x", padx=5, pady=2)

        tk.Label(frame_sub, text="Start Folder:", bg="#dcdcdc").pack(
            side="top", padx=5, pady=2
        )
        self.start_cb = ttk.Combobox(
            frame_sub, state="readonly", values=self.subfolder_manager.subfolder_names
        )
        self.start_cb.pack(side="top", padx=5, pady=2)
        if self.subfolder_manager.subfolder_names:
            self.start_cb.current(0)

        tk.Label(frame_sub, text="End Folder:", bg="#dcdcdc").pack(
            side="top", padx=5, pady=2
        )
        self.end_cb = ttk.Combobox(
            frame_sub, state="readonly", values=self.subfolder_manager.subfolder_names
        )
        self.end_cb.pack(side="top", padx=5, pady=2)
        if self.subfolder_manager.subfolder_names:
            self.end_cb.current(len(self.subfolder_manager.subfolder_names) - 1)

        self.start_cb.bind("<<ComboboxSelected>>", self._on_start_changed)

        # Crossfades
        tk.Label(self, text="Crossfades:", bg="#dcdcdc").pack(
            side="top", padx=5, pady=5
        )
        self.steps_var = tk.StringVar(value=str(default_crosfades))
        self.steps_entry = tk.Entry(self, textvariable=self.steps_var)
        self.steps_entry.pack(side="top", padx=5, pady=5)

        # FPS
        tk.Label(self, text="Frames per Second:", bg="#dcdcdc").pack(
            side="top", padx=5, pady=5
        )
        self.fps_var = tk.StringVar(value="25")
        self.fps_entry = tk.Entry(self, textvariable=self.fps_var)
        self.fps_entry.pack(side="top", padx=5, pady=5)

        # Frames per chunk
        tk.Label(self, text="Frames per Chunk:", bg="#dcdcdc").pack(
            side="top", padx=5, pady=5
        )
        self.batch_var = tk.StringVar(value="1000")
        self.batch_entry = tk.Entry(self, textvariable=self.batch_var)
        self.batch_entry.pack(side="top", padx=5, pady=5)

        # Ghost frames
        tk.Label(self, text="Ghost Frames:", bg="#dcdcdc").pack(
            side="top", padx=5, pady=5
        )
        self.ghost_slider = tk.Scale(
            self, from_=0, to=10, orient="horizontal", resolution=1, bg="#dcdcdc"
        )
        self.ghost_slider.set(0)
        self.ghost_slider.pack(side="top", padx=5, pady=5)

        # Vertical splits
        tk.Label(self, text="Vertical Segments:", bg="#dcdcdc").pack(
            side="top", padx=5, pady=5
        )
        self.split_slider = tk.Scale(
            self, from_=1, to=3, orient="horizontal", resolution=1, bg="#dcdcdc"
        )
        self.split_slider.set(1)
        self.split_slider.pack(side="top", padx=5, pady=5)

        self.combined_var = tk.BooleanVar(value=False)
        self.combined_chk = tk.Checkbutton(
            self,
            text="Create one combined video.",
            variable=self.combined_var,
            bg="#dcdcdc",
        )
        self.combined_chk.pack(side="top", padx=5, pady=5)
        self.split_slider.bind("<ButtonRelease-1>", self._on_split_release)
        if self.split_slider.get() == 1:
            self.combined_chk.config(state="disabled")
            self.combined_var.set(False)

        # Workers
        import multiprocessing

        max_cpu = multiprocessing.cpu_count()
        tk.Label(self, text="Workers:", bg="#dcdcdc").pack(side="top", padx=5, pady=5)
        self.worker_slider = tk.Scale(
            self, from_=1, to=max_cpu, orient="horizontal", resolution=1, bg="#dcdcdc"
        )
        self.worker_slider.set(min(8, max_cpu))
        self.worker_slider.pack(side="top", padx=5, pady=5)

        # Delete chunks
        self.delete_var = tk.BooleanVar(value=True)
        self.delete_chk = tk.Checkbutton(
            self,
            text="Delete chunks after merge.",
            variable=self.delete_var,
            bg="#dcdcdc",
        )
        self.delete_chk.pack(side="top", padx=5, pady=5)

        # Progress
        self.prog_frame = tk.Frame(self, bg="#dcdcdc")
        self.prog_frame.pack(side="top", fill="x", padx=10, pady=10)
        tk.Label(self.prog_frame, text="Progress:", bg="#dcdcdc").pack(
            side="top", padx=5, pady=2
        )
        self.progress_bar = ttk.Progressbar(
            self.prog_frame, length=300, mode="determinate"
        )
        self.progress_bar.pack(side="top", padx=10, pady=2)

        # OK button
        tk.Button(self, text="OK", command=self._on_ok, bg="#dcdcdc").pack(
            side="top", padx=5, pady=5
        )

    def _on_start_changed(self, evt=None):
        chosen_start = self.start_cb.get()
        if chosen_start not in self.subfolder_manager.subfolder_names:
            return
        idx_s = self.subfolder_manager.subfolder_names.index(chosen_start)
        new_ends = self.subfolder_manager.subfolder_names[idx_s:]
        self.end_cb.config(values=new_ends)
        self.end_cb.current(len(new_ends) - 1)

    def _on_split_release(self, evt=None):
        if self.split_slider.get() == 1:
            self.combined_chk.config(state="disabled")
            self.combined_var.set(False)
        else:
            self.combined_chk.config(state="normal")

    def _on_ok(self):
        import time
        from tkinter import messagebox

        start_time = time.time()
        try:
            steps_val_ = int(self.steps_var.get())
            fps_val_ = int(self.fps_var.get())
            batch_val_ = int(self.batch_var.get())
            workers_val_ = int(self.worker_slider.get())
            ghost_val_ = int(self.ghost_slider.get())
            split_val_ = int(self.split_slider.get())
            if (
                steps_val_ < 1
                or fps_val_ < 1
                or batch_val_ < 1
                or workers_val_ < 1
                or ghost_val_ < 0
                or split_val_ < 1
            ):
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Invalid export parameters.")
            return

        if not os.path.isfile(self.ffmpeg_path):
            messagebox.showerror("Error", "Invalid ffmpeg path.")
            return

        start_sub = self.start_cb.get()
        end_sub = self.end_cb.get()

        ok_build = self.controller.load_and_prepare_subfolders(
            start_sub, end_sub, self.width, self.height
        )
        if not ok_build:
            messagebox.showerror("Error", "Failed to build subfolder fades.")
            return

        weighting_params = self.controller.get_current_weighting_params()
        final_paths = self.controller.export_crossfade_video(
            chosen_subfolders=self.subfolder_manager.subfolder_names,
            start_sub=start_sub,
            end_sub=end_sub,
            width=self.width,
            height=self.height,
            steps_val=steps_val_,
            fps_val=fps_val_,
            frames_per_batch=batch_val_,
            workers_val=workers_val_,
            ffmpeg_path=self.ffmpeg_path,
            ghost_val=ghost_val_,
            split_val=split_val_,
            delete_chunks=self.delete_var.get(),
            progress_bar=self.progress_bar,
            diag=self,
            weighting_params=weighting_params,
        )

        if split_val_ > 1 and self.combined_var.get() and len(final_paths) > 1:
            from datetime import datetime

            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            combined_path = os.path.join("output", f"{now_str}_combined.mp4")
            self.controller.build_combined_video_hstack(
                final_paths, combined_path, self.ffmpeg_path
            )

        took = round(time.time() - start_time, 2)
        messagebox.showinfo("Info", f"Export done in {took}s.")
        self.destroy()


class ExportMovementDialog(tk.Toplevel):
    """
    A dialog for exporting movement data (JSON).
    """

    def __init__(
        self,
        master,
        controller,
        subfolder_manager,
        width,
        height,
        default_crosfades=100,
        *args,
        **kwargs,
    ):
        super().__init__(master, *args, **kwargs)
        self.master = master
        self.controller = controller
        self.subfolder_manager = subfolder_manager
        self.width = width
        self.height = height

        self.title("Export Movement")
        self.configure(bg="#dcdcdc")

        tk.Label(
            self, text=f"Resolution: {width}x{height}px", bg="#dcdcdc", fg="blue"
        ).pack(side="top", padx=5, pady=5)

        folder_frame = tk.Frame(self, bg="#dcdcdc")
        folder_frame.pack(side="top", fill="x", padx=5, pady=2)

        tk.Label(folder_frame, text="Start Folder:", bg="#dcdcdc").pack(
            side="top", padx=5, pady=2
        )
        self.start_cb = ttk.Combobox(
            folder_frame,
            state="readonly",
            values=self.subfolder_manager.subfolder_names,
        )
        self.start_cb.pack(side="top", padx=5, pady=2)
        if self.subfolder_manager.subfolder_names:
            self.start_cb.current(0)

        tk.Label(folder_frame, text="End Folder:", bg="#dcdcdc").pack(
            side="top", padx=5, pady=2
        )
        self.end_cb = ttk.Combobox(
            folder_frame,
            state="readonly",
            values=self.subfolder_manager.subfolder_names,
        )
        self.end_cb.pack(side="top", padx=5, pady=2)
        if self.subfolder_manager.subfolder_names:
            self.end_cb.current(len(self.subfolder_manager.subfolder_names) - 1)

        self.start_cb.bind("<<ComboboxSelected>>", self._on_start_changed)

        tk.Label(self, text="Crossfades Steps:", bg="#dcdcdc").pack(
            side="top", padx=5, pady=5
        )
        self.steps_var = tk.StringVar(value=str(default_crosfades))
        self.steps_entry = tk.Entry(self, textvariable=self.steps_var)
        self.steps_entry.pack(side="top", padx=5, pady=5)

        tk.Button(self, text="OK", command=self._on_ok, bg="#dcdcdc").pack(
            side="top", padx=5, pady=5
        )

    def _on_start_changed(self, evt=None):
        chosen_start = self.start_cb.get()
        if chosen_start not in self.subfolder_manager.subfolder_names:
            return
        idx_s = self.subfolder_manager.subfolder_names.index(chosen_start)
        new_ends = self.subfolder_manager.subfolder_names[idx_s:]
        self.end_cb.config(values=new_ends)
        self.end_cb.current(len(new_ends) - 1)

    def _on_ok(self):
        from tkinter import messagebox

        try:
            steps_val = int(self.steps_var.get())
            if steps_val < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Invalid steps value.")
            return

        start_sub = self.start_cb.get()
        end_sub = self.end_cb.get()

        ok_build = self.controller.load_and_prepare_subfolders(
            start_sub, end_sub, self.width, self.height
        )
        if not ok_build:
            messagebox.showerror("Error", "Could not build fade for subfolder range.")
            return

        chosen_subfolders = self.subfolder_manager.subfolder_names
        export_obj = self.controller.build_movement_data(
            chosen_subfolders=chosen_subfolders,
            start_sub=start_sub,
            end_sub=end_sub,
            steps_val=steps_val,
            width=self.width,
            height=self.height,
        )
        if not export_obj:
            messagebox.showerror("Error", "Global spline build returned None.")
            return

        path_json = self.controller.save_movement_data(export_obj)
        if path_json:
            messagebox.showinfo("Info", f"Movement exported => {path_json}")
        else:
            messagebox.showerror("Error", "Movement export failed.")

        self.destroy()
