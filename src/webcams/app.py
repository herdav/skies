import os
import shutil
import threading
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta
from os.path import splitext
from tkinter import simpledialog
from PIL import Image, ImageDraw, ImageFont, ImageTk
from cams import (
    dispatch_download,
    format_utc,
    load_cameras_from_json,
    register_downloads,
)

output_folder = "img"
os.makedirs(output_folder, exist_ok=True)
latest_folder = os.path.join(output_folder, "latest")
os.makedirs(latest_folder, exist_ok=True)


class Tooltip:
    """Simple tooltip for UI elements."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.enter)
        widget.bind("<Leave>", self.leave)

    def enter(self, event):
        x = event.x_root + 20
        y = event.y_root
        self.tip = tw = tk.Toplevel(self.widget)
        tw.overrideredirect(True)
        lbl = tk.Label(tw, text=self.text, bg="#ffffe0", relief="solid", bd=1)
        lbl.pack()
        tw.geometry(f"+{x}+{y}")

    def leave(self, event):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class WebcamApp:
    """UI for webcam downloads."""

    def __init__(self, root):
        self.root = root
        self.root.title("Webcams")

        self.root.geometry(f"1560x900+50+50")

        # Load camera data from JSON and register routines
        data = load_cameras_from_json()
        register_downloads(data)

        # Flatten all lists from the JSON into a single dictionary
        all_items = []
        for val in data.values():
            if isinstance(val, list):
                all_items += val

        self.item_dict = {it["id"]: it for it in all_items}

        # Build main frames
        self.left_frame = tk.Frame(root)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.left_frame)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.container = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.container, anchor="nw")
        self.container.bind(
            "<Configure>",
            lambda e: self.canvas.config(scrollregion=self.canvas.bbox("all")),
        )

        self.right_frame = tk.Frame(root)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y, expand=False)

        # Logging
        self.log_text = tk.Text(self.right_frame, width=40)
        self.log_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Button area
        self.btn_frame = tk.Frame(self.right_frame)
        self.btn_frame.pack(side=tk.TOP, pady=10)
        btn_width = 15

        # Row 0
        self.btn_run_all = tk.Button(
            self.btn_frame,
            text="Run All Selected",
            width=2 * btn_width + 3,
            command=self.on_run_all_clicked,
        )
        self.btn_run_all.grid(row=0, column=0, columnspan=2, pady=5, padx=5)

        # Row 1
        self.btn_deselect_all = tk.Button(
            self.btn_frame,
            text="Deselect All",
            width=btn_width,
            command=self.deselect_all,
        )
        self.btn_deselect_all.grid(row=1, column=0, pady=5, padx=5)
        self.btn_select_all = tk.Button(
            self.btn_frame, text="Select All", width=btn_width, command=self.select_all
        )
        self.btn_select_all.grid(row=1, column=1, pady=5, padx=5)

        # Row 2
        self.latest_btn = tk.Button(
            self.btn_frame,
            text="Latest",
            width=btn_width,
            command=self.show_latest_images,
        )
        self.latest_btn.grid(row=2, column=0, pady=5, padx=5)
        self.default_btn = tk.Button(
            self.btn_frame,
            text="Default",
            width=btn_width,
            command=self.show_default_images,
        )
        self.default_btn.grid(row=2, column=1, pady=5, padx=5)

        # Row 3
        self.mask_btn = tk.Button(
            self.btn_frame, text="Mask", width=btn_width, command=self.toggle_mask
        )
        self.mask_btn.grid(row=3, column=0, pady=5, padx=5)
        self.btn_export_merge = tk.Button(
            self.btn_frame,
            text="Export Merge",
            width=btn_width,
            command=self.export_merge,
        )
        self.btn_export_merge.grid(row=3, column=1, pady=5, padx=5)

        # Row 4
        self.btn_autorun = tk.Button(
            self.btn_frame,
            text="Auto Run",
            width=2 * btn_width + 3,
            command=self.on_autorun_clicked,
        )
        self.btn_autorun.grid(row=4, column=0, columnspan=2, pady=5, padx=5)

        # Row 5
        self.btn_quit = tk.Button(
            self.btn_frame, text="Quit", width=btn_width, command=self.on_quit_clicked
        )
        self.btn_quit.grid(row=5, column=0, pady=5, padx=5)
        self.btn_clear_history = tk.Button(
            self.btn_frame,
            text="Clear History",
            width=btn_width,
            command=self.clear_history,
        )
        self.btn_clear_history.grid(row=5, column=1, pady=5, padx=5)

        # Label for time left (red text)
        self.lbl_time_left = tk.Label(self.btn_frame, text="", fg="red")
        self.lbl_time_left.grid(row=6, column=0, columnspan=2, pady=5, padx=5)

        # Internal variables
        self.photo_images = {}
        self.selected_items = {}
        self.download_times = {}
        self.cell_frames = {}
        self.frame_colors = {}
        self.original_pil_images = {}
        self.mask_state = False
        self.slot_mode = {}
        self.export_items = {}

        self.auto_run_active = False
        self.auto_run_end_dt = None
        self.cycle_seconds = 120
        self.run_count = 0
        self.last_run_folder_time = None

        # This will store the time when the current run was started (for auto-run logic).
        self.current_run_start = None

        # Prepare UTC IDs
        self.all_utc_ids = [format_utc(i) for i in range(-11, 13)]
        for u in self.all_utc_ids:
            if u not in self.item_dict:
                self.item_dict[u] = {"id": u, "url": None}

        for u in self.all_utc_ids:
            self.selected_items[u] = tk.BooleanVar(value=bool(self.item_dict[u]["url"]))
            self.export_items[u] = tk.BooleanVar(value=bool(self.item_dict[u]["url"]))
            self.slot_mode[u] = "latest"

        self.current_mode = "latest"
        self.latest_btn.config(relief=tk.SUNKEN)
        self.default_btn.config(relief=tk.RAISED)

        # Worker thread reference
        self.worker_thread = None

        self.load_images()

    def log(self, msg):
        """Writes a message into the log text widget."""
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def clear_history(self):
        """Clears the log text."""
        self.log_text.delete("1.0", tk.END)
        self.log("History cleared")

    def safe_log(self, msg):
        self.root.after(0, lambda: self.log(msg))

    def safe_set_frame_color(self, utcid, color):
        self.root.after(0, lambda: self.set_frame_color(utcid, color))

    def safe_update_cell(self, utcid):
        self.root.after(0, lambda: self.update_cell(utcid))

    def on_quit_clicked(self):
        """Closes the application window."""
        self.root.destroy()

    def select_all(self):
        """Sets all URLs to active/export."""
        for u in self.all_utc_ids:
            if self.item_dict[u]["url"]:
                self.selected_items[u].set(True)
                self.export_items[u].set(True)
        self.load_images()

    def deselect_all(self):
        """Deactivates all camera slots."""
        for u in self.all_utc_ids:
            self.selected_items[u].set(False)
            self.export_items[u].set(False)
        self.load_images()

    def on_run_all_clicked(self):
        """
        Starts a new run if not already running, creates a timestamped folder,
        and spawns the worker thread. Records the start time for timing logic.
        """
        self.current_run_start = datetime.now()

        if self.last_run_folder_time is not None:
            delta = self.current_run_start - self.last_run_folder_time
            real_cycle_sec = delta.total_seconds()
            # self.log(f"Effective cycle time: {real_cycle_sec:.1f}s")
        self.last_run_folder_time = self.current_run_start

        now_str = self.current_run_start.strftime("%Y%m%d_%H%M%S")
        self.run_folder = os.path.join(output_folder, now_str)
        os.makedirs(self.run_folder, exist_ok=True)

        self.run_count += 1
        line_no = f"{self.run_count:04d}"
        self.log(
            f"Run {line_no} started, images or error logs\nwill be stored in: {self.run_folder}"
        )

        if self.worker_thread and self.worker_thread.is_alive():
            self.log("Downloads are already in progress...")
            return

        self.worker_thread = threading.Thread(target=self.run_bot, daemon=True)
        self.worker_thread.start()

    def run_bot(self):
        """
        Performs the download for each selected item in a background thread.
        At the end, schedules 'on_run_finished' in the main thread.
        """
        # current_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.auto_run_active:
            cycle_info = (
                f"set {int(self.cycle_seconds)}s per cycle ---------------------"
            )
        else:
            cycle_info = "----------------------------------------"

        self.safe_log(f"{cycle_info}")

        for u in self.all_utc_ids:
            if self.selected_items[u].get():
                it = self.item_dict[u]
                if not it.get("url"):
                    self.safe_log(f"No URL for {u}, skipping")
                    continue

                # Cyan for active download start
                self.safe_set_frame_color(u, "#00FFFF")

                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                potential_jpg_name = f"{it['id']}_{timestamp_str}.jpg"
                potential_jpg_path = os.path.join(self.run_folder, potential_jpg_name)

                attempts = 3
                success = False
                local_file = None
                newfile = False

                for attempt in range(attempts):
                    ok, newfile, local_file = self.dispatch_with_path(it)
                    if ok:
                        success = True
                        break
                    else:
                        # Orange frame for retry
                        if attempt < attempts - 1:
                            self.safe_log(
                                f"Download attempt {attempt+1} failed for {it['id']},\nretrying..."
                            )
                            self.safe_set_frame_color(u, "#FFA500")
                        else:
                            # Red frame on final failure
                            self.safe_set_frame_color(u, "#FF0000")
                            error_msg = (
                                f"Download failed after {attempts} attempts\n"
                                f"for {it['id']}, error file safed as\n{os.path.splitext(potential_jpg_name)[0]}.txt"
                            )
                            self.safe_log(error_msg)
                            error_txt_path = (
                                os.path.splitext(potential_jpg_path)[0] + ".txt"
                            )
                            try:
                                with open(error_txt_path, "w", encoding="utf-8") as f:
                                    f.write(error_msg + "\n")
                            except:
                                pass

                if not success:
                    # Go to next item
                    self.safe_update_cell(u)
                    continue
                else:
                    # Download succeeded
                    if newfile:
                        self.safe_set_frame_color(u, "#00FF00")
                    else:
                        if self.slot_mode[u] == "latest":
                            self.safe_set_frame_color(u, "#A9A9A9")
                        else:
                            self.safe_set_frame_color(u, "#D3D3D3")

                    if local_file:
                        base_name = os.path.basename(local_file)
                        new_path = os.path.join(self.run_folder, base_name)
                        if local_file != new_path:
                            try:
                                shutil.move(local_file, new_path)
                            except Exception as e:
                                self.safe_log(
                                    f"Cannot move file {local_file} to {new_path}: {e}"
                                )
                                new_path = local_file

                        # Auto-run + Mask => also create a merged variant
                        if (
                            self.auto_run_active
                            and self.mask_state
                            and os.path.exists(new_path)
                        ):
                            try:
                                self.save_masked_variant(it["id"], new_path)
                            except Exception as me:
                                self.safe_log(
                                    f"Error creating masked image {new_path}: {me}"
                                )

                        # Copy to "latest" folder
                        self.write_latest_variant(it["id"], new_path)

                self.safe_update_cell(u)

        # Once all downloads are done, call on_run_finished in the main thread
        self.root.after(0, self.on_run_finished)

    def on_run_finished(self):
        """
        Called when the current run (worker thread) is fully finished.
        Decides if and when the next auto-run cycle should start.
        """
        if not self.auto_run_active:
            return

        now = datetime.now()
        if now >= self.auto_run_end_dt:
            self.log(f"Auto-run ended at {now}")
            self.auto_run_active = False
            self.btn_autorun.config(text="Auto Run", fg="black")
            self.lbl_time_left.config(text="")
            return

        run_duration = (now - self.current_run_start).total_seconds()
        if run_duration < self.cycle_seconds:
            # Wait for the remaining time to fulfill the cycle
            wait_ms = int(self.cycle_seconds - run_duration) * 1000
            self.log(f"Run finished in {int(run_duration)}s\n")
            self.root.after(wait_ms, self.start_next_run)
        else:
            # We already exceeded the cycle time, so start immediately
            self.log(
                f"Run took {int(run_duration)}s, exceeding cycle time.\nStarting next run immediately.\n"
            )
            self.start_next_run()

    def start_next_run(self):
        """
        Helper method to start the next run if auto-run is still active.
        Triggers 'on_run_all_clicked' to begin a new cycle.
        """
        if not self.auto_run_active:
            return
        self.update_time_left()
        self.on_run_all_clicked()

    def dispatch_with_path(self, item):
        """
        Calls the download routine and determines the local file path.
        Returns (ok, new_file, local_file_path).
        """
        item_id = item["id"]
        prev_files = set(os.listdir(output_folder))

        ok, new_file = dispatch_download(item, self.safe_log)
        local_file_path = None

        if ok:
            new_set = set(os.listdir(output_folder)) - prev_files
            found_file = None
            for nf in new_set:
                if nf.startswith(item_id + "_"):
                    found_file = nf
                    break
            if found_file:
                local_file_path = os.path.join(output_folder, found_file)
            else:
                matches = [
                    f for f in os.listdir(output_folder) if f.startswith(item_id + "_")
                ]
                if matches:
                    chosen = sorted(matches, reverse=True)[0]
                    local_file_path = os.path.join(output_folder, chosen)

        return (ok, new_file, local_file_path)

    def save_masked_variant(self, item_id, file_path):
        """
        Creates a merged mask image from file_path and stores it as _merge.png.
        """
        from PIL import Image

        base_img = Image.open(file_path).convert("RGBA")
        merged = self.apply_mask_to_pil(item_id, base_img)
        if merged:
            name, _ = os.path.splitext(file_path)
            out_path = name + "_merge.png"
            merged.save(out_path, "PNG")
            self.safe_log(f"Mask merged saved: {out_path}")

    def write_latest_variant(self, item_id, timestamped_path):
        """
        Copies the new timestamped file into the 'latest' folder.
        Removes any old version for this item first (so only one file per item remains).
        """
        # Remove old files with same prefix
        old_files = [
            f for f in os.listdir(latest_folder) if f.startswith(item_id + "_")
        ]
        for oldf in old_files:
            try:
                os.remove(os.path.join(latest_folder, oldf))
            except:
                pass

        # Copy the new file
        base = os.path.basename(timestamped_path)
        dest = os.path.join(latest_folder, base)
        try:
            shutil.copy2(timestamped_path, dest)
            self.safe_log(f"{dest}")
        except Exception as e:
            self.safe_log(f"Could not copy to latest: {e}")

    def reload_image(self, it):
        """
        Spawns a background thread to reload a single camera slot.
        """
        threading.Thread(
            target=self.reload_image_worker, args=(it,), daemon=True
        ).start()

    def reload_image_worker(self, it):
        """
        Download logic for the single reload in a background thread.
        """
        u = it["id"]
        if not it.get("url"):
            self.safe_log(f"No URL for {u}, skipping reload")
            return
        self.slot_mode[u] = "latest"
        self.safe_set_frame_color(u, "#00FFFF")

        ok, newf, local_file = self.dispatch_with_path(it)
        if not ok:
            self.safe_set_frame_color(u, "#FF0000")
        else:
            if newf:
                self.safe_set_frame_color(u, "#00FF00")
            else:
                if self.slot_mode[u] == "latest":
                    self.safe_set_frame_color(u, "#A9A9A9")
                else:
                    self.safe_set_frame_color(u, "#D3D3D3")

            if local_file:
                # Also copy to latest
                stamp_name = os.path.basename(local_file)
                dest_name = os.path.join(latest_folder, stamp_name)
                old_files = [
                    f for f in os.listdir(latest_folder) if f.startswith(u + "_")
                ]
                for oldf in old_files:
                    try:
                        os.remove(os.path.join(latest_folder, oldf))
                    except:
                        pass

                try:
                    shutil.copy2(local_file, dest_name)
                    self.safe_log(f"Latest image updated:\n{dest_name}")
                except Exception as e:
                    self.safe_log(f"Failed to copy to latest:\n{e}")

        self.safe_update_cell(u)

    def load_images(self):
        """
        Clears and rebuilds the grid of camera slots.
        """
        for w in self.container.winfo_children():
            w.destroy()
        self.cell_frames.clear()

        cols = 6
        for idx, utc in enumerate(self.all_utc_ids):
            r = idx // cols
            c = idx % cols
            self.create_cell(utc, r, c)

    def create_cell(self, utcid, row, col):
        """
        Creates a cell (frame) for a single camera slot.
        """
        color = "#D3D3D3" if self.slot_mode[utcid] == "default" else "#A9A9A9"
        cell = tk.Frame(
            self.container,
            bd=2,
            highlightthickness=2,
            highlightbackground=color,
            highlightcolor=color,
        )
        cell.grid(row=row, column=col, padx=5, pady=5, sticky="nw")
        self.cell_frames[utcid] = cell

        if utcid in self.frame_colors:
            c_ = self.frame_colors[utcid]
            cell.config(highlightbackground=c_, highlightcolor=c_)

        self.update_cell(utcid)

    def update_cell(self, utcid):
        """
        Updates the UI elements for a given camera slot (thumbnail, labels, etc.).
        """
        cell = self.cell_frames.get(utcid)
        if not cell:
            return
        for ch in cell.winfo_children():
            ch.destroy()

        it = self.item_dict[utcid]
        img, filename_shown = self.get_cell_image_and_label(it, 180, 120)
        self.photo_images[utcid] = img

        lbl_img = tk.Label(cell, image=img, bg="white")
        lbl_img.pack(side=tk.TOP, pady=2)

        # Click to open full if available
        if self.has_local_file(it["id"]):
            lbl_img.config(cursor="hand2")
            lbl_img.bind("<Button-1>", lambda e: self.open_full_image(it))
        else:
            if utcid not in self.frame_colors:
                if self.slot_mode[utcid] == "latest":
                    self.set_frame_color(utcid, "#A9A9A9")
                else:
                    self.set_frame_color(utcid, "#D3D3D3")

        tk.Label(cell, text=filename_shown).pack(side=tk.TOP, pady=2)

        row_line = tk.Frame(cell)
        row_line.pack(side=tk.TOP, pady=2)

        cb_state = "normal" if it["url"] else "disabled"
        active_cb = tk.Checkbutton(
            row_line,
            text="Active",
            variable=self.selected_items[utcid],
            state=cb_state,
            command=lambda: self.on_active_changed(utcid),
        )
        active_cb.pack(side=tk.LEFT, padx=3)

        rb_state = "normal" if it["url"] else "disabled"
        rb = tk.Button(
            row_line,
            text="Reload",
            command=lambda i=it: self.reload_image(i),
            state=rb_state,
        )
        rb.pack(side=tk.LEFT, padx=3)

        export_cb = tk.Checkbutton(
            row_line, text="Export", variable=self.export_items[utcid], state=cb_state
        )
        if not self.selected_items[utcid].get():
            export_cb.config(state="disabled")
            self.export_items[utcid].set(False)
        export_cb.pack(side=tk.LEFT, padx=3)

        # Link
        if it["url"]:
            link_line = tk.Frame(cell)
            link_line.pack(side=tk.TOP, pady=2)
            link_lbl = tk.Label(link_line, text="Link", fg="blue", cursor="hand2")
            link_lbl.pack(side=tk.LEFT, padx=3)
            link_lbl.bind("<Button-1>", lambda e, url=it["url"]: webbrowser.open(url))
            Tooltip(link_lbl, it["url"])

    def on_active_changed(self, utcid):
        """
        Handles checkbox changes for 'Active' -> also toggles 'Export'.
        """
        if self.selected_items[utcid].get():
            self.export_items[utcid].set(True)
        else:
            self.export_items[utcid].set(False)
        self.update_cell(utcid)

    def get_cell_image_and_label(self, it, w, h):
        """
        Fetches the correct image for the cell, either from default or latest folder.
        If mask_state is True, applies the mask if present.
        """
        if self.slot_mode[it["id"]] == "default":
            default_path = os.path.join(output_folder, "default")
            prefix = it["id"] + "_"
            if not os.path.exists(default_path):
                return self.create_placeholder(w, h, it["id"]), it["id"]
            candidates = [f for f in os.listdir(default_path) if f.startswith(prefix)]
            if not candidates:
                return self.create_placeholder(w, h, it["id"]), it["id"]
            chosen = sorted(candidates, reverse=True)[0]
            full_path = os.path.join(default_path, chosen)
        else:
            # Latest mode
            prefix = it["id"] + "_"
            flist = [f for f in os.listdir(latest_folder) if f.startswith(prefix)]
            if not flist:
                return self.create_placeholder(w, h, it["id"]), it["id"]
            chosen = sorted(flist, reverse=True)[0]
            full_path = os.path.join(latest_folder, chosen)

        try:
            pil_img = Image.open(full_path).convert("RGBA")
            self.original_pil_images[it["id"]] = pil_img.copy()
            if self.mask_state:
                masked = self.apply_mask_to_pil(it["id"], pil_img)
                if masked:
                    pil_img = masked
            pil_img.thumbnail((w, h), Image.LANCZOS)
            return ImageTk.PhotoImage(pil_img), chosen
        except:
            return self.create_placeholder(w, h, it["id"]), it["id"]

    def has_local_file(self, utcid):
        """
        Checks if there's a 'latest' file for the given ID.
        """
        prefix = utcid + "_"
        flist = [f for f in os.listdir(latest_folder) if f.startswith(prefix)]
        return len(flist) > 0

    def create_placeholder(self, w, h, txt):
        """
        Creates a simple gray placeholder image with given text.
        """
        img = Image.new("RGB", (w, h), (220, 220, 220))
        d = ImageDraw.Draw(img)
        f = ImageFont.load_default()
        box = d.textbbox((0, 0), txt, font=f)
        x = (w - box[2]) // 2
        y = (h - box[3]) // 2
        d.text((x, y), txt, font=f, fill=(0, 0, 0))
        return ImageTk.PhotoImage(img)

    def open_full_image(self, it):
        """
        Opens a fullscreen window to display the chosen image in large size.
        Click to close.
        """
        u = it["id"]
        if not self.has_local_file(u):
            return
        top = tk.Toplevel(self.root)
        top.attributes("-fullscreen", True)
        fr = tk.Frame(top, bg="black")
        fr.pack(fill="both", expand=True)
        lbl = tk.Label(fr, bg="black")
        lbl.pack(fill="both", expand=True)
        lbl.bind("<Button-1>", lambda e: top.destroy())

        base_pil = self.original_pil_images.get(u)
        if not base_pil:
            lbl.original_pil = self.create_placeholder_img(800, 600, u)
        else:
            if self.mask_state:
                masked = self.apply_mask_to_pil(u, base_pil)
                if masked:
                    lbl.original_pil = masked
                else:
                    lbl.original_pil = base_pil
            else:
                lbl.original_pil = base_pil

        lbl.image_tk = None

        def on_resize(evt):
            w_ = fr.winfo_width()
            h_ = fr.winfo_height()
            if w_ < 1 or h_ < 1:
                return
            ow, oh = lbl.original_pil.size
            ratio_img = ow / oh
            ratio_fr = w_ / h_
            if ratio_img > ratio_fr:
                new_w = w_
                new_h = int(new_w / ratio_img)
            else:
                new_h = h_
                new_w = int(new_h * ratio_img)
            if new_w < 1:
                new_w = 1
            if new_h < 1:
                new_h = 1

            scaled = lbl.original_pil.resize((new_w, new_h), Image.LANCZOS)
            lbl.image_tk = ImageTk.PhotoImage(scaled)
            lbl.config(image=lbl.image_tk)

        fr.bind("<Configure>", on_resize)
        fr.update_idletasks()
        on_resize(None)

    def create_placeholder_img(self, w, h, txt):
        """
        Placeholder PIL image for fullscreen mode if no real image is found.
        """
        img = Image.new("RGB", (w, h), (220, 220, 220))
        d = ImageDraw.Draw(img)
        f = ImageFont.load_default()
        box = d.textbbox((0, 0), txt, font=f)
        x = (w - box[2]) // 2
        y = (h - box[3]) // 2
        d.text((x, y), txt, font=f, fill=(0, 0, 0))
        return img

    def show_latest_images(self):
        """
        Switches all slots to 'latest' mode and refreshes the grid.
        """
        self.current_mode = "latest"
        self.latest_btn.config(relief=tk.SUNKEN)
        self.default_btn.config(relief=tk.RAISED)
        for u in self.all_utc_ids:
            self.slot_mode[u] = "latest"
            self.set_frame_color(u, "#A9A9A9")
        self.load_images()

    def show_default_images(self):
        """
        Switches all slots to 'default' mode and refreshes the grid.
        """
        self.current_mode = "default"
        self.default_btn.config(relief=tk.SUNKEN)
        self.latest_btn.config(relief=tk.RAISED)
        for u in self.all_utc_ids:
            self.slot_mode[u] = "default"
            self.set_frame_color(u, "#D3D3D3")
        self.load_images()

    def toggle_mask(self):
        """
        Toggles the mask overlay on/off and reloads the grid.
        """
        self.mask_state = not self.mask_state
        if self.mask_state:
            self.mask_btn.config(relief=tk.SUNKEN)
        else:
            self.mask_btn.config(relief=tk.RAISED)
        self.load_images()

    def set_frame_color(self, utcid, color):
        """
        Sets the frame highlight color for a given slot.
        """
        self.frame_colors[utcid] = color
        c = self.cell_frames.get(utcid)
        if c:
            c.config(
                highlightthickness=2, highlightbackground=color, highlightcolor=color
            )

    def apply_mask_to_pil(self, utcid, base_pil):
        """
        If a mask file for this ID exists in 'img/mask', merges it onto the base image.
        """
        mask_path = os.path.join(output_folder, "mask")
        if not os.path.exists(mask_path):
            return None
        mask_filename = f"{utcid}_mask.png".replace(":", "")
        mask_full = os.path.join(mask_path, mask_filename)
        if not os.path.exists(mask_full):
            return None

        base_rgba = base_pil.copy().convert("RGBA")
        mask_img = Image.open(mask_full).convert("RGBA")
        if mask_img.size != base_rgba.size:
            mask_img = mask_img.resize(base_rgba.size, Image.LANCZOS)
        merged = Image.alpha_composite(base_rgba, mask_img)
        return merged

    def export_merge(self):
        """
        Creates merged images for all 'Export' items in a 'merge' folder,
        using mask overlay if available.
        """
        merge_dir = os.path.join(output_folder, "merge")
        os.makedirs(merge_dir, exist_ok=True)

        for utc in self.all_utc_ids:
            if not self.export_items[utc].get():
                continue
            it = self.item_dict[utc]
            prefix = it["id"] + "_"

            if self.slot_mode[it["id"]] == "default":
                default_path = os.path.join(output_folder, "default")
                if not os.path.exists(default_path):
                    continue
                candidates = [
                    f for f in os.listdir(default_path) if f.startswith(prefix)
                ]
                if not candidates:
                    continue
                chosen = sorted(candidates, reverse=True)[0]
                full_path = os.path.join(default_path, chosen)
            else:
                flist = [f for f in os.listdir(latest_folder) if f.startswith(prefix)]
                if not flist:
                    continue
                chosen = sorted(flist, reverse=True)[0]
                full_path = os.path.join(latest_folder, chosen)

            try:
                pil_img = Image.open(full_path).convert("RGBA")
            except:
                continue

            merged = self.apply_mask_to_pil(it["id"], pil_img)
            if not merged:
                continue

            name, _ = os.path.splitext(chosen)
            out_name = f"{name}_merge.png"
            out_path = os.path.join(merge_dir, out_name)
            try:
                merged.save(out_path, "PNG")
                self.log(f"Exported:\n{out_name}")
            except Exception as e:
                self.log(f"Export error {out_name}: {e}")

    def on_autorun_clicked(self):
        """
        Toggles the auto-run feature. If starting, prompt for cycle/end time.
        If stopping, cancel auto-run and clear display.
        """
        if not self.auto_run_active:
            # Starting auto-run
            if not self.configure_auto_run_settings():
                return
            self.auto_run_active = True
            self.btn_autorun.config(text="Stop", fg="red")
            self.update_time_left()
            # Start first run immediately
            self.on_run_all_clicked()
        else:
            # Stopping auto-run
            self.auto_run_active = False
            self.btn_autorun.config(text="Auto Run", fg="black")
            self.lbl_time_left.config(text="")

    def configure_auto_run_settings(self):
        """
        Prompts the user for cycle time and end datetime for auto-run.
        Returns True if successful, False if canceled.
        """
        cycle_str = simpledialog.askstring(
            "Auto-Run Settings",
            "Cycle time in seconds:",
            initialvalue=str(self.cycle_seconds),
            parent=self.root,
        )
        if cycle_str is None:
            return False
        try:
            self.cycle_seconds = int(cycle_str)
        except:
            self.cycle_seconds = 120

        default_end = (datetime.now() + timedelta(minutes=30)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        end_str = simpledialog.askstring(
            "Auto-Run Settings",
            "End date/time (YYYY-MM-DD HH:MM:SS):",
            initialvalue=default_end,
            parent=self.root,
        )
        if end_str is None:
            return False

        try:
            self.auto_run_end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
        except:
            self.auto_run_end_dt = datetime.now() + timedelta(minutes=30)

        return True

    def update_time_left(self):
        """
        Updates the label showing remaining time for auto-run.
        Called repeatedly every 1 second while auto-run is active.
        """
        if not self.auto_run_active:
            self.lbl_time_left.config(text="")
            return
        now = datetime.now()
        delta = self.auto_run_end_dt - now
        if delta.total_seconds() < 0:
            self.lbl_time_left.config(text="")
            return

        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        time_str = f"{h:02d}:{m:02d}:{s:02d} left"
        self.lbl_time_left.config(text=time_str)

        if self.auto_run_active:
            self.root.after(1000, self.update_time_left)
