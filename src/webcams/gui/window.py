# src/gui/window.py
"""Tkinter front-end for the webcam application."""

# All business logic lives in controller.py or the webscraper package; this file
# only handles the graphical interface, user interaction and thread-safe updates.

from __future__ import annotations

import os
import shutil
import threading
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import simpledialog
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageTk

from webscraper import (
    dispatch_download,
    format_utc,
    load_cameras_from_json,
    register_downloads,
)

from .tooltip import Tooltip

OUTPUT_FOLDER = "img"
Path(OUTPUT_FOLDER, "latest").mkdir(parents=True, exist_ok=True)
latest_folder = os.path.join(OUTPUT_FOLDER, "latest")


class WebcamWindow:
    """GUI window."""

    MAX_ATTEMPTS = 3

    def __init__(self, root: tk.Tk, controller: Any | None = None) -> None:
        self.root = root
        self.controller = controller
        self.root.title("Webcams")
        self.root.geometry("1560x900+50+50")

        # --- data ---
        data = load_cameras_from_json()
        register_downloads(data)

        flat: List[Dict[str, Any]] = [it for v in data.values() if isinstance(v, list) for it in v]
        self.item_dict: Dict[str, Dict[str, Any]] = {it["image_id"]: it for it in flat}

        # --- GUI frames ---
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

        # --- log area ---
        self.log_text = tk.Text(self.right_frame, width=40)
        self.log_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # --- buttons ---
        self.btn_frame = tk.Frame(self.right_frame)
        self.btn_frame.pack(side=tk.TOP, pady=10)
        bw = 15

        self.btn_run_all = tk.Button(
            self.btn_frame,
            text="Run All Selected",
            width=2 * bw + 3,
            command=self.on_run_all_clicked,
        )
        self.btn_run_all.grid(row=0, column=0, columnspan=2, pady=5, padx=5)

        self.btn_deselect_all = tk.Button(
            self.btn_frame, text="Deselect All", width=bw, command=self.deselect_all
        )
        self.btn_deselect_all.grid(row=1, column=0, pady=5, padx=5)
        self.btn_select_all = tk.Button(
            self.btn_frame, text="Select All", width=bw, command=self.select_all
        )
        self.btn_select_all.grid(row=1, column=1, pady=5, padx=5)

        self.latest_btn = tk.Button(
            self.btn_frame, text="Latest", width=bw, command=self.show_latest_images
        )
        self.latest_btn.grid(row=2, column=0, pady=5, padx=5)
        self.default_btn = tk.Button(
            self.btn_frame, text="Default", width=bw, command=self.show_default_images
        )
        self.default_btn.grid(row=2, column=1, pady=5, padx=5)

        self.mask_btn = tk.Button(self.btn_frame, text="Mask", width=bw, command=self.toggle_mask)
        self.mask_btn.grid(row=3, column=0, pady=5, padx=5)
        self.btn_export_merge = tk.Button(
            self.btn_frame, text="Export Merge", width=bw, command=self.export_merge
        )
        self.btn_export_merge.grid(row=3, column=1, pady=5, padx=5)

        self.btn_autorun = tk.Button(
            self.btn_frame, text="Auto Run", width=2 * bw + 3, command=self.on_autorun_clicked
        )
        self.btn_autorun.grid(row=4, column=0, columnspan=2, pady=5, padx=5)

        self.btn_quit = tk.Button(
            self.btn_frame, text="Quit", width=bw, command=self.on_quit_clicked
        )
        self.btn_quit.grid(row=5, column=0, pady=5, padx=5)
        self.btn_clear_history = tk.Button(
            self.btn_frame, text="Clear History", width=bw, command=self.clear_history
        )
        self.btn_clear_history.grid(row=5, column=1, pady=5, padx=5)

        self.lbl_time_left = tk.Label(self.btn_frame, text="", fg="red")
        self.lbl_time_left.grid(row=6, column=0, columnspan=2, pady=5, padx=5)

        # --- state ---
        self.photo_images: Dict[str, ImageTk.PhotoImage] = {}
        self.selected_items: Dict[str, tk.BooleanVar] = {}
        self.export_items: Dict[str, tk.BooleanVar] = {}
        self.cell_frames: Dict[str, tk.Frame] = {}
        self.frame_colors: Dict[str, str] = {}
        self.original_pil_images: Dict[str, Image.Image] = {}
        self.slot_mode: Dict[str, str] = {}
        self.mask_state = False

        self.auto_run_active = False
        self.auto_run_end_dt: datetime | None = None
        self.cycle_seconds = 120
        self.run_count = 0
        self.run_folder: str | None = None
        self.current_run_start: datetime | None = None
        self.worker_thread: threading.Thread | None = None

        # Prepare UTC ID list and related variables
        self.all_utc_ids = [format_utc(i) for i in range(-11, 13)]
        for utc in self.all_utc_ids:
            if utc not in self.item_dict:
                self.item_dict[utc] = {"image_id": utc, "url": None}
            self.selected_items[utc] = tk.BooleanVar(value=bool(self.item_dict[utc]["url"]))
            self.export_items[utc] = tk.BooleanVar(value=bool(self.item_dict[utc]["url"]))
            self.slot_mode[utc] = "latest"

        self.current_mode = "latest"
        self.latest_btn.config(relief=tk.SUNKEN)

        # Build initial grid
        self.load_images()

    # --- log utils ---
    def log(self, msg: str) -> None:
        """Write a line into the log pane."""
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def safe_log(self, msg: str) -> None:
        """Thread-safe wrapper for log()."""
        self.root.after(0, lambda: self.log(msg))

    # --- ui helpers ---
    def set_frame_color(self, utcid: str, color: str) -> None:
        """Change the highlight color of one slot."""
        self.frame_colors[utcid] = color
        frame = self.cell_frames.get(utcid)
        if frame:
            frame.config(highlightthickness=2, highlightbackground=color, highlightcolor=color)

    def safe_set_frame_color(self, utcid: str, color: str) -> None:
        self.root.after(0, lambda: self.set_frame_color(utcid, color))

    def safe_update_cell(self, utcid: str) -> None:
        self.root.after(0, lambda: self.update_cell(utcid))

    # --- selection ---
    def select_all(self) -> None:
        """Activate all cameras that have a URL."""
        for utc in self.all_utc_ids:
            if self.item_dict[utc]["url"]:
                self.selected_items[utc].set(True)
                self.export_items[utc].set(True)
        self.load_images()

    def deselect_all(self) -> None:
        """Deactivate all cameras."""
        for utc in self.all_utc_ids:
            self.selected_items[utc].set(False)
            self.export_items[utc].set(False)
        self.load_images()

    # --- run / autorun ---
    def on_run_all_clicked(self) -> None:
        """Start a download run for all selected items."""
        self.current_run_start = datetime.now()
        self.run_folder = os.path.join(
            OUTPUT_FOLDER, self.current_run_start.strftime("%Y%m%d_%H%M%S")
        )
        os.makedirs(self.run_folder, exist_ok=True)

        self.run_count += 1
        self.log(f"Run {self.run_count:04d} started -> {self.run_folder}")

        if self.worker_thread and self.worker_thread.is_alive():
            self.log("Downloads already running.")
            return

        self.worker_thread = threading.Thread(target=self.run_routines, daemon=True)
        self.worker_thread.start()

    def run_routines(self) -> None:
        """Background thread that performs all downloads (with retries)."""
        # Header line in the log pane
        self.safe_log(
            f"set {int(self.cycle_seconds)}s per cycle ---------------------"
            if self.auto_run_active
            else "----------------------------------------"
        )

        for utc in self.all_utc_ids:
            if not self.selected_items[utc].get():
                continue

            item = self.item_dict[utc]
            if not item.get("url"):
                self.safe_log(f"No URL for {utc}, skipping …")
                continue

            self.slot_mode[utc] = "latest"
            self.safe_set_frame_color(utc, "#00FFFF")  # cyan starting

            success, new_file, local_file = False, False, None
            for attempt in range(self.MAX_ATTEMPTS):
                ok, new_file, local_file = self.dispatch_with_path(item)
                if ok:
                    success = True
                    break
                if attempt < self.MAX_ATTEMPTS - 1:
                    # orange → retry in progress
                    self.safe_set_frame_color(utc, "#FFA500")
                    self.safe_log(f"{utc}: attempt {attempt + 1} failed, retrying …")

            # --- final result ---
            if not success or local_file is None:
                # red border, write stub (only in auto-run)
                self.safe_set_frame_color(utc, "#FF0000")
                self._write_error_stub(item["image_id"])
            else:
                # green = new file, grey = unchanged
                self.safe_set_frame_color(
                    utc,
                    "#00FF00"
                    if new_file
                    else "#A9A9A9"
                    if self.slot_mode[utc] == "latest"
                    else "#D3D3D3",
                )
                # move / mask / latest handling
                self._store_run_file(item["image_id"], local_file)

            self.safe_update_cell(utc)

        # schedule post-run handler back on the main thread
        self.root.after(0, self.on_run_finished)

    def on_run_finished(self) -> None:
        """Called when the worker thread has finished one full cycle."""
        if not self.auto_run_active:
            return

        now = datetime.now()
        if now >= self.auto_run_end_dt:
            self.log(f"Auto-run ended at {now}")
            self.auto_run_active = False
            self.btn_autorun.config(text="Auto Run", fg="black")
            self.lbl_time_left.config(text="")
            return

        run_time = (now - self.current_run_start).total_seconds()
        wait_ms = max(0, int(self.cycle_seconds - run_time)) * 1000
        self.log(f"Run finished in {int(run_time)} s")
        self.root.after(wait_ms, self.start_next_run)

    def start_next_run(self) -> None:
        """Helper for auto-run loop."""
        if not self.auto_run_active:
            return
        self.update_time_left()
        self.on_run_all_clicked()

    # --- autorun config ---
    def on_autorun_clicked(self) -> None:
        """Toggle auto-run on/off."""
        if not self.auto_run_active:
            if not self.configure_auto_run_settings():
                return
            self.auto_run_active = True
            self.btn_autorun.config(text="Stop", fg="red")
            self.update_time_left()
            self.on_run_all_clicked()
        else:
            self.auto_run_active = False
            self.btn_autorun.config(text="Auto Run", fg="black")
            self.lbl_time_left.config(text="")

    def configure_auto_run_settings(self) -> bool:
        """Ask the user for cycle time and end-datetime."""
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
        except Exception:
            self.cycle_seconds = 120

        default_end = (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
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
        except Exception:
            self.auto_run_end_dt = datetime.now() + timedelta(minutes=30)
        return True

    def update_time_left(self) -> None:
        """Update the red label showing remaining auto-run time."""
        if not self.auto_run_active:
            self.lbl_time_left.config(text="")
            return
        delta = self.auto_run_end_dt - datetime.now()
        if delta.total_seconds() <= 0:
            self.lbl_time_left.config(text="")
            return
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        self.lbl_time_left.config(text=f"{h:02d}:{m:02d}:{s:02d} left")
        self.root.after(1000, self.update_time_left)

    # --- view switch ---
    def show_latest_images(self) -> None:
        """Switch every slot to *latest* mode and reload the grid."""
        self.current_mode = "latest"
        self.latest_btn.config(relief=tk.SUNKEN)
        self.default_btn.config(relief=tk.RAISED)
        for utc in self.all_utc_ids:
            self.slot_mode[utc] = "latest"
            self.set_frame_color(utc, "#A9A9A9")
        self.load_images()

    def show_default_images(self) -> None:
        """Switch every slot to *default* mode and reload the grid."""
        self.current_mode = "default"
        self.default_btn.config(relief=tk.SUNKEN)
        self.latest_btn.config(relief=tk.RAISED)
        for utc in self.all_utc_ids:
            self.slot_mode[utc] = "default"
            self.set_frame_color(utc, "#D3D3D3")
        self.load_images()

    def toggle_mask(self) -> None:
        """Enable/disable mask overlay and refresh thumbnails."""
        self.mask_state = not self.mask_state
        self.mask_btn.config(relief=tk.SUNKEN if self.mask_state else tk.RAISED)
        self.load_images()

    # --- misc buttons ---
    def on_quit_clicked(self) -> None:
        self.root.destroy()

    def clear_history(self) -> None:
        self.log_text.delete("1.0", tk.END)
        self.log("History cleared")

    # --- grid logic ---
    def load_images(self) -> None:
        """Rebuild the entire grid of camera slots."""
        for child in self.container.winfo_children():
            child.destroy()
        self.cell_frames.clear()

        cols = 6
        for idx, utc in enumerate(self.all_utc_ids):
            r, c = divmod(idx, cols)
            self.create_cell(utc, r, c)

    def create_cell(self, utcid: str, row: int, col: int) -> None:
        """Create a single thumbnail cell."""
        default_color = "#D3D3D3" if self.slot_mode[utcid] == "default" else "#A9A9A9"
        cell = tk.Frame(
            self.container,
            bd=2,
            highlightthickness=2,
            highlightbackground=default_color,
            highlightcolor=default_color,
        )
        cell.grid(row=row, column=col, padx=5, pady=5, sticky="nw")
        self.cell_frames[utcid] = cell

        if utcid in self.frame_colors:
            c = self.frame_colors[utcid]
            cell.config(highlightbackground=c, highlightcolor=c)

        self.update_cell(utcid)

    def update_cell(self, utcid: str) -> None:
        """Refresh thumbnail and controls for one slot."""
        cell = self.cell_frames.get(utcid)
        if not cell:
            return
        for child in cell.winfo_children():
            child.destroy()

        item = self.item_dict[utcid]
        img, label_txt = self.get_cell_image_and_label(item, 180, 120)
        self.photo_images[utcid] = img  # keep reference

        lbl_img = tk.Label(cell, image=img, bg="white")
        lbl_img.pack(side=tk.TOP, pady=2)

        if self.has_local_file(item["image_id"]):
            lbl_img.config(cursor="hand2")
            lbl_img.bind("<Button-1>", lambda _e, it=item: self.open_full_image(it))

        tk.Label(cell, text=label_txt).pack(side=tk.TOP, pady=2)

        row_controls = tk.Frame(cell)
        row_controls.pack(side=tk.TOP, pady=2)

        state = "normal" if item["url"] else "disabled"
        active_cb = tk.Checkbutton(
            row_controls,
            text="Active",
            variable=self.selected_items[utcid],
            state=state,
            command=lambda u=utcid: self.on_active_changed(u),
        )
        active_cb.pack(side=tk.LEFT, padx=3)

        tk.Button(
            row_controls, text="Reload", command=lambda it=item: self.reload_image(it), state=state
        ).pack(side=tk.LEFT, padx=3)

        export_cb = tk.Checkbutton(row_controls, text="Export", variable=self.export_items[utcid])
        if not self.selected_items[utcid].get():
            export_cb.config(state="disabled")
            self.export_items[utcid].set(False)
        export_cb.pack(side=tk.LEFT, padx=3)

        if item["url"]:
            link_line = tk.Frame(cell)
            link_line.pack(side=tk.TOP, pady=2)
            link_lbl = tk.Label(link_line, text="Link", fg="blue", cursor="hand2")
            link_lbl.pack(side=tk.LEFT, padx=3)
            link_lbl.bind("<Button-1>", lambda _e, url=item["url"]: webbrowser.open(url))
            Tooltip(link_lbl, item["url"])

    # --- active/checkbox ---
    def on_active_changed(self, utcid: str) -> None:
        """Keep export checkbox in sync with active checkbox."""
        if self.selected_items[utcid].get():
            self.export_items[utcid].set(True)
        else:
            self.export_items[utcid].set(False)
        self.update_cell(utcid)

    # --- image helpers ---
    def get_cell_image_and_label(
        self, item: Dict[str, Any], w: int, h: int
    ) -> Tuple[ImageTk.PhotoImage, str]:
        """Return (Tk image, filename/label) for one slot."""
        mode = self.slot_mode[item["image_id"]]
        base_dir = os.path.join(OUTPUT_FOLDER, "default") if mode == "default" else latest_folder
        prefix = item["image_id"] + "_"

        candidates = [f for f in os.listdir(base_dir) if f.startswith(prefix)]
        if not candidates:
            return self.create_placeholder(w, h, item["image_id"]), item["image_id"]

        chosen = sorted(candidates, reverse=True)[0]
        full_path = os.path.join(base_dir, chosen)

        try:
            pil_img = Image.open(full_path).convert("RGBA")
            self.original_pil_images[item["image_id"]] = pil_img.copy()
            if self.mask_state and (masked := self.apply_mask_to_pil(item["image_id"], pil_img)):
                pil_img = masked
            pil_img.thumbnail((w, h), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(pil_img), chosen
        except Exception:
            return self.create_placeholder(w, h, item["image_id"]), item["image_id"]

    def create_placeholder(self, w: int, h: int, txt: str) -> ImageTk.PhotoImage:
        """Simple grey placeholder with center text."""
        img = Image.new("RGB", (w, h), (220, 220, 220))
        d = ImageDraw.Draw(img)
        fnt = ImageFont.load_default()
        box = d.textbbox((0, 0), txt, font=fnt)
        d.text(((w - box[2]) // 2, (h - box[3]) // 2), txt, font=fnt, fill=0)
        return ImageTk.PhotoImage(img)

    def has_local_file(self, utcid: str) -> bool:
        """True if a 'latest' image exists for this ID."""
        return any(f.startswith(utcid + "_") for f in os.listdir(latest_folder))

    def open_full_image(self, item: Dict[str, Any]) -> None:
        """Open fullscreen window with the latest image (click to close)."""
        utcid = item["image_id"]
        if not self.has_local_file(utcid):
            return

        top = tk.Toplevel(self.root)
        top.attributes("-fullscreen", True)
        fr = tk.Frame(top, bg="black")
        fr.pack(fill="both", expand=True)
        lbl = tk.Label(fr, bg="black")
        lbl.pack(fill="both", expand=True)
        lbl.bind("<Button-1>", lambda _e: top.destroy())

        base_pil = self.original_pil_images.get(utcid)
        lbl.original_pil = (
            self.apply_mask_to_pil(utcid, base_pil) if self.mask_state and base_pil else base_pil
        ) or self.create_placeholder_img(800, 600, utcid)
        lbl.image_tk = None  # will be set in on_resize

        def on_resize(_: Any) -> None:
            w_, h_ = fr.winfo_width(), fr.winfo_height()
            if w_ < 1 or h_ < 1:
                return
            ow, oh = lbl.original_pil.size
            ratio_img = ow / oh
            ratio_fr = w_ / h_
            new_w, new_h = (
                (w_, int(w_ / ratio_img)) if ratio_img > ratio_fr else (int(h_ * ratio_img), h_)
            )
            new_w = max(1, new_w)
            new_h = max(1, new_h)
            scaled = lbl.original_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
            lbl.image_tk = ImageTk.PhotoImage(scaled)
            lbl.config(image=lbl.image_tk)

        fr.bind("<Configure>", on_resize)
        fr.update_idletasks()
        on_resize(None)

    def create_placeholder_img(self, w: int, h: int, txt: str) -> Image.Image:
        """Placeholder PIL image for fullscreen mode."""
        img = Image.new("RGB", (w, h), (220, 220, 220))
        d = ImageDraw.Draw(img)
        fnt = ImageFont.load_default()
        box = d.textbbox((0, 0), txt, font=fnt)
        d.text(((w - box[2]) // 2, (h - box[3]) // 2), txt, font=fnt, fill=0)
        return img

    # --- public API ---
    def populate_slots(self, all_utc_ids, item_dict):
        """Called once by Controller right after the window is instantiated.

        The Controller passes its own UTC-list and item-dictionary so the GUI
        can rebuild the grid.  We simply replace the internal references and
        call the normal loader.
        """
        # keep the objects the Controller owns (no deep copy!)
        self.all_utc_ids = all_utc_ids
        self.item_dict = item_dict

        # rebuild the per-slot state dictionaries
        self.selected_items = {
            utc: tk.BooleanVar(value=bool(item_dict[utc]["url"])) for utc in all_utc_ids
        }
        self.export_items = {
            utc: tk.BooleanVar(value=bool(item_dict[utc]["url"])) for utc in all_utc_ids
        }
        self.slot_mode = {utc: self.current_mode for utc in all_utc_ids}

        self.load_images()

    # --- mask / merge ---
    def toggle_mask_state(self, state: bool) -> None:
        """Explicitly set mask state (not used by UI)."""
        self.mask_state = state
        self.load_images()

    def apply_mask_to_pil(self, utcid: str, base_pil: Image.Image) -> Image.Image | None:
        """If a mask exists for this ID, overlay it on the base image and return."""
        mask_dir = os.path.join(OUTPUT_FOLDER, "mask")
        mask_file = os.path.join(mask_dir, f"{utcid}_mask.png".replace(":", ""))
        if not os.path.exists(mask_file):
            return None
        mask_img = Image.open(mask_file).convert("RGBA")
        if mask_img.size != base_pil.size:
            mask_img = mask_img.resize(base_pil.size, Image.Resampling.LANCZOS)
        return Image.alpha_composite(base_pil.convert("RGBA"), mask_img)

    def export_merge(self) -> None:
        """Create merged (masked) PNGs for every slot whose Export checkbox is set."""
        merge_dir = os.path.join(OUTPUT_FOLDER, "merge")
        os.makedirs(merge_dir, exist_ok=True)

        for utc in self.all_utc_ids:
            if not self.export_items[utc].get():
                continue
            item = self.item_dict[utc]
            prefix = item["image_id"] + "_"
            folder = (
                os.path.join(OUTPUT_FOLDER, "default")
                if self.slot_mode[item["image_id"]] == "default"
                else latest_folder
            )
            candidates = [f for f in os.listdir(folder) if f.startswith(prefix)]
            if not candidates:
                continue
            chosen = sorted(candidates, reverse=True)[0]
            full_path = os.path.join(folder, chosen)

            try:
                pil_img = Image.open(full_path).convert("RGBA")
            except Exception:
                continue

            merged = self.apply_mask_to_pil(item["image_id"], pil_img)
            if not merged:
                continue

            name, _ = os.path.splitext(chosen)
            out_name = f"{name}_merge.png"
            try:
                merged.save(os.path.join(merge_dir, out_name), "PNG")
                self.log(f"Exported: {out_name}")
            except Exception as e:
                self.log(f"Export error {out_name}: {e}")

    # --- reload / dispatch ---
    def reload_image(self, item: Dict[str, Any]) -> None:
        """Spawn a background thread to download/refresh a single slot."""
        threading.Thread(target=self.reload_image_worker, args=(item,), daemon=True).start()

    def reload_image_worker(self, item: Dict[str, Any]) -> None:
        """Download logic for single-slot reload."""
        utc = item["image_id"]
        if not item.get("url"):
            self.safe_log(f"No URL for {utc}, skipping reload")
            return
        self.slot_mode[utc] = "latest"
        self.safe_set_frame_color(utc, "#00FFFF")

        ok, newf, local_file = self.dispatch_with_path(item)
        if not ok:
            self.safe_set_frame_color(utc, "#FF0000")
        else:
            self.safe_set_frame_color(
                utc,
                "#00FF00" if newf else "#A9A9A9" if self.slot_mode[utc] == "latest" else "#D3D3D3",
            )
            if local_file:
                # copy to latest
                stamp = os.path.basename(local_file)
                dest = os.path.join(latest_folder, stamp)
                for old in [f for f in os.listdir(latest_folder) if f.startswith(utc + "_")]:
                    try:
                        os.remove(os.path.join(latest_folder, old))
                    except Exception:
                        pass
                try:
                    shutil.copy2(local_file, dest)
                    self.safe_log(f"Latest updated: {dest}")
                except Exception as e:
                    self.safe_log(f"Failed to copy: {e}")

        self.safe_update_cell(utc)

    # --- file helpers ---
    def dispatch_with_path(self, item: Dict[str, Any]) -> Tuple[bool, bool, str | None]:
        """Wrapper around dispatch_download that also returns the filepath."""
        item_id = item["image_id"]
        prev_files = set(os.listdir(OUTPUT_FOLDER))

        ok, new_file = dispatch_download(item, self.safe_log)
        local_file = None
        if ok:
            new_set = set(os.listdir(OUTPUT_FOLDER)) - prev_files
            found = next((nf for nf in new_set if nf.startswith(item_id + "_")), None)
            if not found:
                matches = [f for f in os.listdir(OUTPUT_FOLDER) if f.startswith(item_id + "_")]
                found = sorted(matches, reverse=True)[0] if matches else None
            if found:
                local_file = os.path.join(OUTPUT_FOLDER, found)
        return ok, new_file, local_file

    def _store_run_file(self, item_id: str, local_file: str) -> None:
        """Move downloaded file to the current run folder + handle masks/latest."""
        if not self.run_folder:
            return
        base = os.path.basename(local_file)
        new_path = os.path.join(self.run_folder, base)
        if local_file != new_path:
            try:
                shutil.move(local_file, new_path)
            except Exception as e:
                self.safe_log(f"Cannot move {local_file} to {new_path}: {e}")
                new_path = local_file

        if self.auto_run_active and self.mask_state and os.path.exists(new_path):
            try:
                self.save_masked_variant(item_id, new_path)
            except Exception as ex:
                self.safe_log(f"Mask merge error {new_path}: {ex}")

        self.write_latest_variant(item_id, new_path)

    def _write_error_stub(self, item_id: str) -> None:
        """
        Create an empty *.txt* file inside *self.run_folder* so later scripts
        can see that this slot produced no image in this cycle.

        The filename is identical to the one a new JPG would have had, just
        with '.txt' instead of '.jpg'.
        """
        if not (self.auto_run_active and self.run_folder):
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stub_path = os.path.join(self.run_folder, f"{item_id}_{ts}.txt")
        try:
            with open(stub_path, "w", encoding="utf-8") as fh:
                fh.write(
                    f"Download failed or produced no new file for {item_id} "
                    f"at {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                )
            self.safe_log(f"Stub written: {stub_path}")
        except OSError as exc:
            self.safe_log(f"Cannot create stub {stub_path}: {exc}")

    def save_masked_variant(self, item_id: str, file_path: str) -> None:
        """Create and store a merged (mask) variant beside the original file."""
        base = Image.open(file_path).convert("RGBA")
        merged = self.apply_mask_to_pil(item_id, base)
        if merged:
            merged.save(f"{os.path.splitext(file_path)[0]}_merge.png", "PNG")
            self.safe_log(f"Mask merged saved for {item_id}")

    def write_latest_variant(self, item_id: str, timestamped_path: str) -> None:
        """Copy the newest file into /latest (one file per camera)."""
        for old in [f for f in os.listdir(latest_folder) if f.startswith(item_id + "_")]:
            try:
                os.remove(os.path.join(latest_folder, old))
            except Exception:
                pass
        dest = os.path.join(latest_folder, os.path.basename(timestamped_path))
        try:
            shutil.copy2(timestamped_path, dest)
            self.safe_log(dest)
        except Exception as e:
            self.safe_log(f"Could not copy to latest: {e}")
