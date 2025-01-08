# globalWebCams.py

import os
import json
import webbrowser
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFont
from datetime import datetime

from routines.skylinewebcams import download_skyline_screenshot
from routines.webcamimage import download_webcam_image
from routines.dynamicjpg import download_dynamic_jpg
from routines.youtube import download_youtube_screenshot
from routines.faratel import download_faratel_screenshot

output_folder = "img"
os.makedirs(output_folder, exist_ok=True)

def load_cameras_from_json():
    """Load JSON data and return lists."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, "webcams.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return (
        data.get("faratelcams", []),
        data.get("skylinewebcams", []),
        data.get("webcamimage", []),
        data.get("dynamicjpg", []),
        data.get("youtube", [])
    )

def format_utc(i):
    """Return something like UTC+2 or UTC-3."""
    s = "+" if i >= 0 else ""
    return f"UTC{s}{i}"

class Tooltip:
    """Mouseover tooltip."""
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
    """Main window."""
    def __init__(self, root):
        self.root = root
        self.root.title("globalWebCams")

        # Full screen width, example height
        screen_w = self.root.winfo_screenwidth()
        self.root.geometry(f"{screen_w}x900+0+0")

        (
            self.faratelUrls,
            self.skylinewebcamsUrls,
            self.webcamimageUrls,
            self.dynamicjpgUrls,
            self.youtubeVideos
        ) = load_cameras_from_json()

        # Left area with scrolling
        self.left_frame = tk.Frame(root)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.left_frame)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.container = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.container, anchor="nw")
        self.container.bind("<Configure>", lambda e: self.canvas.config(scrollregion=self.canvas.bbox("all")))

        # Right area with log and buttons
        self.right_frame = tk.Frame(root)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y, expand=False)

        self.log_text = tk.Text(self.right_frame, width=40)
        self.log_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.btn_frame = tk.Frame(self.right_frame)
        self.btn_frame.pack(side=tk.TOP, pady=10)

        # Vertically stacked buttons
        tk.Button(self.btn_frame, text="Run All Selected", command=self.run_bot).pack(side=tk.TOP, pady=5)
        tk.Button(self.btn_frame, text="Select All", command=self.select_all).pack(side=tk.TOP, pady=5)
        tk.Button(self.btn_frame, text="Deselect All", command=self.deselect_all).pack(side=tk.TOP, pady=5)
        tk.Button(self.btn_frame, text="Clear History", command=self.clear_history).pack(side=tk.TOP, pady=5)
        tk.Button(self.btn_frame, text="Latest", command=self.show_latest_images).pack(side=tk.TOP, pady=5)
        tk.Button(self.btn_frame, text="Default", command=self.show_default_images).pack(side=tk.TOP, pady=5)
        tk.Button(self.btn_frame, text="Mask", command=self.apply_mask).pack(side=tk.TOP, pady=5)
        tk.Button(self.btn_frame, text="Demask", command=self.remove_mask).pack(side=tk.TOP, pady=5)

        # Dictionaries
        self.photo_images = {}
        self.selected_items = {}
        self.download_times = {}
        self.cell_frames = {}
        self.frame_colors = {}

        # Keep original images and possible overlays
        self.original_pil_images = {}
        self.overlayed_images = {}

        # Gather items
        all_items = (
            self.faratelUrls
            + self.skylinewebcamsUrls
            + self.webcamimageUrls
            + self.dynamicjpgUrls
            + self.youtubeVideos
        )
        self.item_dict = {it["id"]: it for it in all_items}

        # All UTC slots
        self.all_utc_ids = [format_utc(i) for i in range(-11, 13)]

        # For missing URL, store dummy
        for u in self.all_utc_ids:
            if u not in self.item_dict:
                self.item_dict[u] = {"id": u, "url": None}
            self.selected_items[u] = tk.BooleanVar(value=bool(self.item_dict[u]["url"]))

        self.load_images()

    def log(self, msg):
        """Log text."""
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def clear_history(self):
        """Clear log."""
        self.log_text.delete("1.0", tk.END)
        self.log("History cleared")

    def select_all(self):
        """Select all with URL."""
        for u in self.all_utc_ids:
            if self.item_dict[u]["url"]:
                self.selected_items[u].set(True)
        self.load_images()

    def deselect_all(self):
        """Deselect all."""
        for u in self.all_utc_ids:
            self.selected_items[u].set(False)
        self.load_images()

    def run_bot(self):
        """Download for all selected."""
        for u in self.all_utc_ids:
            if self.selected_items[u].get():
                it = self.item_dict[u]
                if not it.get("url"):
                    self.log(f"No URL for {u}, skipping")
                    continue
                self.set_frame_color(u, "#00FFFF")
                self.root.update_idletasks()
                ok, newfile = self.download_item(it)
                if not ok or not newfile:
                    self.set_frame_color(u, "#FF0000")
                else:
                    self.set_frame_color(u, "#00FF00")
                self.update_cell(u)
                self.root.update_idletasks()

    def set_frame_color(self, utcid, color):
        """Color cell frame."""
        self.frame_colors[utcid] = color
        c = self.cell_frames.get(utcid)
        if c:
            c.config(highlightthickness=2, highlightbackground=color, highlightcolor=color)

    def download_item(self, it):
        """Route to correct download func."""
        try:
            i = it["id"]
            if i in [x["id"] for x in self.faratelUrls]:
                return self.download_faratel(it)
            elif i in [x["id"] for x in self.skylinewebcamsUrls]:
                return self.download_skyline(it)
            elif i in [x["id"] for x in self.webcamimageUrls]:
                return self.download_webcamimage(it)
            elif i in [x["id"] for x in self.dynamicjpgUrls]:
                return self.download_dynamicjpg(it)
            elif i in [x["id"] for x in self.youtubeVideos]:
                return self.download_youtube(it)
            else:
                return (False, False)
        except Exception as e:
            self.log(f"Error: {e}")
            return (False, False)

    def check_new_file(self, item_id, result, prev_files, msg):
        """Check for newly created file."""
        if not result:
            return (True, False)
        new_files = set(os.listdir(output_folder)) - prev_files
        found_new = any(f.startswith(item_id + "_") for f in new_files)
        if found_new:
            self.download_times[item_id] = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log(f"{msg}: {item_id}")
            return (True, True)
        return (True, False)

    def download_faratel(self, it):
        prev = set(os.listdir(output_folder))
        res = download_faratel_screenshot(it["url"], it["id"])
        return self.check_new_file(it["id"], res, prev, "Faratel")

    def download_skyline(self, it):
        prev = set(os.listdir(output_folder))
        res = download_skyline_screenshot(it["url"], it["id"])
        return self.check_new_file(it["id"], res, prev, "Skyline")

    def download_webcamimage(self, it):
        prev = set(os.listdir(output_folder))
        res = download_webcam_image(it["url"], it["id"])
        return self.check_new_file(it["id"], res, prev, "Webcam")

    def download_dynamicjpg(self, it):
        prev = set(os.listdir(output_folder))
        res = download_dynamic_jpg(
            url=it["url"],
            element_id=it.get("id"),
            element_class=it.get("class"),
            src_pattern=it.get("src"),
            image_id=it["id"]
        )
        return self.check_new_file(it["id"], res, prev, "Dynamic JPG")

    def download_youtube(self, it):
        prev = set(os.listdir(output_folder))
        res = download_youtube_screenshot(it["url"], it["id"])
        return self.check_new_file(it["id"], res, prev, "YouTube")

    def reload_image(self, it):
        """Manual reload for a slot."""
        u = it["id"]
        if not it.get("url"):
            self.log(f"No URL for {u}, skipping reload")
            return
        self.set_frame_color(u, "#00FFFF")
        self.root.update_idletasks()
        ok, newf = self.download_item(it)
        if not ok or not newf:
            self.set_frame_color(u, "#FF0000")
        else:
            self.set_frame_color(u, "#00FF00")
        self.update_cell(u)
        self.root.update_idletasks()

    def load_images(self):
        """Build or rebuild grid of cells."""
        for w in self.container.winfo_children():
            w.destroy()
        self.cell_frames.clear()

        cols = 6
        for idx, utc in enumerate(self.all_utc_ids):
            r = idx // cols
            c = idx % cols
            self.create_cell(utc, r, c)

    def create_cell(self, utcid, row, col):
        """Make a cell with placeholder or real content."""
        color = self.frame_colors.get(utcid, "#ccc")
        cell = tk.Frame(
            self.container,
            bd=2,
            highlightthickness=2,
            highlightbackground=color,
            highlightcolor=color
        )
        cell.grid(row=row, column=col, padx=5, pady=5, sticky="nw")
        self.cell_frames[utcid] = cell
        self.update_cell(utcid)

    def update_cell(self, utcid):
        """Refresh cell content."""
        cell = self.cell_frames.get(utcid)
        if not cell:
            return
        for ch in cell.winfo_children():
            ch.destroy()

        it = self.item_dict[utcid]

        # No URL => empty placeholder
        if not it["url"]:
            self.selected_items[utcid].set(False)
            img = self.create_placeholder(180, 120, "")
        else:
            img = self.get_tk_image(it, 180, 120)

        self.photo_images[utcid] = img
        lbl_img = tk.Label(cell, image=img, bg="white")
        lbl_img.pack(side=tk.TOP, pady=2)

        # Fullscreen if local file
        if self.has_local_file(it["id"]):
            lbl_img.config(cursor="hand2")
            lbl_img.bind("<Button-1>", lambda e: self.open_full_image(it))

        if it["url"]:
            t = self.download_times.get(utcid, "N/A")
            tk.Label(cell, text=f"{utcid} {t}").pack(side=tk.TOP, pady=2)

        row_line = tk.Frame(cell)
        row_line.pack(side=tk.TOP, pady=2)

        cb_state = "normal" if it["url"] else "disabled"
        cb = tk.Checkbutton(row_line, text="Active", variable=self.selected_items[utcid], state=cb_state)
        cb.pack(side=tk.LEFT, padx=3)

        rb_state = "normal" if it["url"] else "disabled"
        rb = tk.Button(row_line, text="Reload", command=lambda i=it: self.reload_image(i), state=rb_state)
        rb.pack(side=tk.LEFT, padx=3)

        if it["url"]:
            link_lbl = tk.Label(row_line, text="Link", fg="blue", cursor="hand2")
            link_lbl.pack(side=tk.LEFT, padx=3)
            link_lbl.bind("<Button-1>", lambda e, url=it["url"]: webbrowser.open(url))
            Tooltip(link_lbl, it["url"])

    def has_local_file(self, utcid):
        """Check local directory."""
        if not os.path.exists(output_folder):
            return False
        prefix = utcid + "_"
        flist = [f for f in os.listdir(output_folder) if f.startswith(prefix)]
        return len(flist) > 0

    def get_tk_image(self, it, w, h):
        """Load latest local file, scale or placeholder."""
        if not os.path.exists(output_folder):
            return self.create_placeholder(w, h, "")

        prefix = it["id"] + "_"
        flist = [f for f in os.listdir(output_folder) if f.startswith(prefix)]
        if flist:
            latest = sorted(flist, reverse=True)[0]
            path = os.path.join(output_folder, latest)
            try:
                pil_img = Image.open(path)
                self.original_pil_images[it["id"]] = pil_img.copy()
                pil_img.thumbnail((w, h), Image.LANCZOS)
                return ImageTk.PhotoImage(pil_img)
            except:
                return self.create_placeholder(w, h, it["id"])
        else:
            return self.create_placeholder(w, h, it["id"])

    def create_placeholder(self, w, h, txt):
        """Create gray placeholder."""
        img = Image.new("RGB", (w, h), (220, 220, 220))
        d = ImageDraw.Draw(img)
        f = ImageFont.load_default()
        box = d.textbbox((0, 0), txt, font=f)
        x = (w - box[2]) // 2
        y = (h - box[3]) // 2
        d.text((x, y), txt, font=f, fill=(0, 0, 0))
        return ImageTk.PhotoImage(img)

    def open_full_image(self, it):
        """Fullscreen popup."""
        if not self.has_local_file(it["id"]):
            return
        top = tk.Toplevel(self.root)
        top.attributes("-fullscreen", True)
        fr = tk.Frame(top, bg="black")
        fr.pack(fill="both", expand=True)
        lbl = tk.Label(fr, bg="black")
        lbl.pack(fill="both", expand=True)
        lbl.bind("<Button-1>", lambda e: top.destroy())

        orig = self.get_original_pil(it)
        if not orig:
            orig = self.create_placeholder_img(800, 600, "")
        lbl.original_pil = orig
        lbl.image_tk = None

        def on_resize(evt):
            w_ = fr.winfo_width()
            h_ = fr.winfo_height()
            if w_ < 1 or h_ < 1:
                return
            ow, oh = lbl.original_pil.size
            r_img = ow / oh
            r_fr = w_ / h_
            if r_img > r_fr:
                new_w = w_
                new_h = int(new_w / r_img)
            else:
                new_h = h_
                new_w = int(new_h * r_img)
            if new_w < 1: new_w = 1
            if new_h < 1: new_h = 1
            scaled = lbl.original_pil.resize((new_w, new_h), Image.LANCZOS)
            lbl.image_tk = ImageTk.PhotoImage(scaled)
            lbl.config(image=lbl.image_tk)

        fr.bind("<Configure>", on_resize)
        fr.update_idletasks()
        on_resize(None)

    def get_original_pil(self, it):
        """Return original PIL if any."""
        return self.original_pil_images.get(it["id"], None)

    def create_placeholder_img(self, w, h, txt):
        """Large placeholder PIL."""
        img = Image.new("RGB", (w, h), (220, 220, 220))
        d = ImageDraw.Draw(img)
        f = ImageFont.load_default()
        box = d.textbbox((0, 0), txt, font=f)
        x = (w - box[2]) // 2
        y = (h - box[3]) // 2
        d.text((x, y), txt, font=f, fill=(0, 0, 0))
        return img

    def show_latest_images(self):
        """Reload the normal latest images in all slots."""
        self.overlayed_images.clear()
        for utc in self.all_utc_ids:
            self.update_cell(utc)

    def show_default_images(self):
        """Load images from img/default that match UTC..._..., if present."""
        default_path = os.path.join(output_folder, "default")
        for utc in self.all_utc_ids:
            cell = self.cell_frames.get(utc)
            if not cell:
                continue

            # If slot is empty (no URL), skip or show empty placeholder
            it = self.item_dict[utc]
            if not it["url"]:
                # Show empty placeholder
                ph = self.create_placeholder(180, 120, "")
                self.photo_images[utc] = ph
                self._update_cell_label(cell, ph)
                continue

            # Try to find a file UTC+X_... in default folder
            pattern = utc + "_"  # e.g. UTC+2_
            candidates = [f for f in os.listdir(default_path) if f.startswith(pattern)]
            if candidates:
                # If multiple, pick the first or the newest
                # e.g. newest:
                chosen = sorted(candidates, reverse=True)[0]
                path = os.path.join(default_path, chosen)
                try:
                    pil_img = Image.open(path)
                    pil_img.thumbnail((180, 120), Image.LANCZOS)
                    tk_img = ImageTk.PhotoImage(pil_img)
                    self.photo_images[utc] = tk_img
                except:
                    self.photo_images[utc] = self.create_placeholder(180, 120, utc)
            else:
                # No matching file => placeholder with slot name
                self.photo_images[utc] = self.create_placeholder(180, 120, utc)

            self._update_cell_label(cell, self.photo_images[utc])

    def _update_cell_label(self, cell, tk_img):
        """Helper to update the main label in a cell."""
        for ch in cell.winfo_children():
            if isinstance(ch, tk.Label) and ch.cget("bg") == "white":
                ch.config(image=tk_img)
                ch.image = tk_img

    def apply_mask(self):
        """Overlay alpha masks from img/mask onto the current images only if local image is present."""
        mask_path = os.path.join(output_folder, "mask")
        for utc in self.all_utc_ids:
            cell = self.cell_frames.get(utc)
            if not cell:
                continue
            # If no original image, skip
            if utc not in self.original_pil_images:
                continue

            # Prepare mask
            mask_filename = f"{utc}_mask.png".replace(":", "")
            mask_full = os.path.join(mask_path, mask_filename)
            if not os.path.exists(mask_full):
                continue

            try:
                # Merge
                base_pil = self.original_pil_images[utc].copy().convert("RGBA")
                mask_img = Image.open(mask_full).convert("RGBA")
                merged = Image.alpha_composite(base_pil, mask_img)
                merged.thumbnail((180, 120), Image.LANCZOS)
                self.overlayed_images[utc] = merged
                tk_img = ImageTk.PhotoImage(merged)
                self.photo_images[utc] = tk_img
                # Update cell label
                self._update_cell_label(cell, tk_img)
            except:
                pass

    def remove_mask(self):
        """Remove mask overlay. Return to last normal image or empty if no URL."""
        self.overlayed_images.clear()
        # Just call update_cell again
        for utc in self.all_utc_ids:
            self.update_cell(utc)

if __name__ == "__main__":
    root = tk.Tk()
    WebcamApp(root)
    root.mainloop()
