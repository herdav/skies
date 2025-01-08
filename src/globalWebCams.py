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
    """Load cam data."""
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
    """Format like UTC+2 or UTC-3."""
    s = "+" if i >= 0 else ""
    return f"UTC{s}{i}"

class Tooltip:
    """Simple tooltip."""
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

        screen_w = self.root.winfo_screenwidth()
        self.root.geometry(f"{screen_w}x900+0+0")

        (
            self.faratelUrls,
            self.skylinewebcamsUrls,
            self.webcamimageUrls,
            self.dynamicjpgUrls,
            self.youtubeVideos
        ) = load_cameras_from_json()

        self.left_frame = tk.Frame(root)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.left_frame)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.container = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.container, anchor="nw")
        self.container.bind("<Configure>", lambda e: self.canvas.config(scrollregion=self.canvas.bbox("all")))

        self.right_frame = tk.Frame(root)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y, expand=False)

        self.log_text = tk.Text(self.right_frame, width=40)
        self.log_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.btn_frame = tk.Frame(self.right_frame)
        self.btn_frame.pack(side=tk.TOP, pady=10)

        btn_width = 15
        tk.Button(self.btn_frame, text="Run All Selected", width=btn_width, command=self.run_bot).pack(side=tk.TOP, pady=5)
        tk.Button(self.btn_frame, text="Select All", width=btn_width, command=self.select_all).pack(side=tk.TOP, pady=5)
        tk.Button(self.btn_frame, text="Deselect All", width=btn_width, command=self.deselect_all).pack(side=tk.TOP, pady=5)
        tk.Button(self.btn_frame, text="Clear History", width=btn_width, command=self.clear_history).pack(side=tk.TOP, pady=5)
        tk.Button(self.btn_frame, text="Latest", width=btn_width, command=self.show_latest_images).pack(side=tk.TOP, pady=5)
        tk.Button(self.btn_frame, text="Default", width=btn_width, command=self.show_default_images).pack(side=tk.TOP, pady=5)
        self.mask_btn = tk.Button(self.btn_frame, text="Mask: OFF", width=btn_width, command=self.toggle_mask)
        self.mask_btn.pack(side=tk.TOP, pady=5)

        tk.Button(self.btn_frame, text="Export Merge", width=btn_width, command=self.export_merge).pack(side=tk.TOP, pady=5)

        self.photo_images = {}
        self.selected_items = {}
        self.download_times = {}
        self.cell_frames = {}
        self.frame_colors = {}
        self.original_pil_images = {}
        self.mask_state = False
        self.item_dict = {}

        all_items = (
            self.faratelUrls
            + self.skylinewebcamsUrls
            + self.webcamimageUrls
            + self.dynamicjpgUrls
            + self.youtubeVideos
        )
        self.item_dict = {it["id"]: it for it in all_items}
        self.all_utc_ids = [format_utc(i) for i in range(-11, 13)]

        for u in self.all_utc_ids:
            if u not in self.item_dict:
                self.item_dict[u] = {"id": u, "url": None}
            self.selected_items[u] = tk.BooleanVar(value=bool(self.item_dict[u]["url"]))

        self.current_mode = "latest"
        self.load_images()

    def log(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def clear_history(self):
        self.log_text.delete("1.0", tk.END)
        self.log("History cleared")

    def select_all(self):
        for u in self.all_utc_ids:
            if self.item_dict[u]["url"]:
                self.selected_items[u].set(True)
        self.load_images()

    def deselect_all(self):
        for u in self.all_utc_ids:
            self.selected_items[u].set(False)
        self.load_images()

    def run_bot(self):
        for u in self.all_utc_ids:
            if self.selected_items[u].get():
                it = self.item_dict[u]
                if not it.get("url"):
                    self.log(f"No URL for {u}, skipping")
                    continue
                self.set_frame_color(u, "#00FFFF")  # Busy
                self.root.update_idletasks()

                ok, newfile = self.download_item(it)
                if not ok:
                    self.set_frame_color(u, "#FF0000")  # Error
                else:
                    if newfile:
                        self.set_frame_color(u, "#00FF00")  # New image => green
                    else:
                        # No new file => if not set, lightgray
                        if u not in self.frame_colors:
                            self.set_frame_color(u, "#D3D3D3")
                self.update_cell(u)
                self.root.update_idletasks()

    def set_frame_color(self, utcid, color):
        self.frame_colors[utcid] = color
        c = self.cell_frames.get(utcid)
        if c:
            c.config(highlightthickness=2, highlightbackground=color, highlightcolor=color)

    def download_item(self, it):
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
        if not result:
            return (False, False)
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
        u = it["id"]
        if not it.get("url"):
            self.log(f"No URL for {u}, skipping reload")
            return

        self.set_frame_color(u, "#00FFFF")
        self.root.update_idletasks()

        ok, newf = self.download_item(it)
        if not ok:
            self.set_frame_color(u, "#FF0000")
        else:
            if newf:
                self.set_frame_color(u, "#00FF00")
            else:
                if u not in self.frame_colors:
                    self.set_frame_color(u, "#D3D3D3")
        self.update_cell(u)
        self.root.update_idletasks()

    def load_images(self):
        for w in self.container.winfo_children():
            w.destroy()
        self.cell_frames.clear()

        cols = 6
        for idx, utc in enumerate(self.all_utc_ids):
            r = idx // cols
            c = idx % cols
            self.create_cell(utc, r, c)

    def create_cell(self, utcid, row, col):
        if self.current_mode == "latest":
            default_color = "#A9A9A9"  # darkgray
        else:
            default_color = "#D3D3D3"  # lightgray

        cell = tk.Frame(
            self.container,
            bd=2,
            highlightthickness=2,
            highlightbackground=default_color,
            highlightcolor=default_color
        )
        cell.grid(row=row, column=col, padx=5, pady=5, sticky="nw")
        self.cell_frames[utcid] = cell

        # If a custom color is set, apply it
        if utcid in self.frame_colors:
            color = self.frame_colors[utcid]
            cell.config(highlightbackground=color, highlightcolor=color)

        self.update_cell(utcid)

    def update_cell(self, utcid):
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

        if self.has_local_file(it["id"]):
            lbl_img.config(cursor="hand2")
            lbl_img.bind("<Button-1>", lambda e: self.open_full_image(it))
        else:
            # Empty slot => frame color lightgray
            if utcid not in self.frame_colors:
                self.set_frame_color(utcid, "#D3D3D3")

        tk.Label(cell, text=filename_shown).pack(side=tk.TOP, pady=2)

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

    def get_cell_image_and_label(self, it, w, h):
        if not os.path.exists(output_folder):
            return self.create_placeholder(w, h, it["id"]), it["id"]

        prefix = it["id"] + "_"
        flist = [f for f in os.listdir(output_folder) if f.startswith(prefix)]
        if not flist:
            return self.create_placeholder(w, h, it["id"]), it["id"]

        if self.current_mode == "latest":
            chosen = sorted(flist, reverse=True)[0]
            full_path = os.path.join(output_folder, chosen)
        else:
            default_path = os.path.join(output_folder, "default")
            pattern = it["id"] + "_"
            candidates = []
            if os.path.exists(default_path):
                candidates = [f for f in os.listdir(default_path) if f.startswith(pattern)]
            if candidates:
                chosen = sorted(candidates, reverse=True)[0]
                full_path = os.path.join(default_path, chosen)
            else:
                chosen = sorted(flist, reverse=True)[0]
                full_path = os.path.join(output_folder, chosen)

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
        if not os.path.exists(output_folder):
            return False
        prefix = utcid + "_"
        flist = [f for f in os.listdir(output_folder) if f.startswith(prefix)]
        return len(flist) > 0

    def create_placeholder(self, w, h, txt):
        img = Image.new("RGB", (w, h), (220, 220, 220))
        d = ImageDraw.Draw(img)
        f = ImageFont.load_default()
        box = d.textbbox((0, 0), txt, font=f)
        x = (w - box[2]) // 2
        y = (h - box[3]) // 2
        d.text((x, y), txt, font=f, fill=(0, 0, 0))
        return ImageTk.PhotoImage(img)

    def open_full_image(self, it):
        if not self.has_local_file(it["id"]):
            return
        top = tk.Toplevel(self.root)
        top.attributes("-fullscreen", True)
        fr = tk.Frame(top, bg="black")
        fr.pack(fill="both", expand=True)
        lbl = tk.Label(fr, bg="black")
        lbl.pack(fill="both", expand=True)
        lbl.bind("<Button-1>", lambda e: top.destroy())

        base_pil = self.original_pil_images.get(it["id"])
        if not base_pil:
            lbl.original_pil = self.create_placeholder_img(800, 600, it["id"])
        else:
            if self.mask_state:
                masked = self.apply_mask_to_pil(it["id"], base_pil)
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

    def create_placeholder_img(self, w, h, txt):
        img = Image.new("RGB", (w, h), (220, 220, 220))
        d = ImageDraw.Draw(img)
        f = ImageFont.load_default()
        box = d.textbbox((0, 0), txt, font=f)
        x = (w - box[2]) // 2
        y = (h - box[3]) // 2
        d.text((x, y), txt, font=f, fill=(0, 0, 0))
        return img

    def show_latest_images(self):
        self.current_mode = "latest"
        self.load_images()

    def show_default_images(self):
        self.current_mode = "default"
        self.load_images()

    def toggle_mask(self):
        self.mask_state = not self.mask_state
        self.mask_btn.config(text=f"Mask: {'ON' if self.mask_state else 'OFF'}")
        self.load_images()

    def apply_mask_to_pil(self, utcid, base_pil):
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
        """Exports merged images (only if mask exists) as PNG."""
        merge_dir = os.path.join(output_folder, "merge")
        os.makedirs(merge_dir, exist_ok=True)

        for utc in self.all_utc_ids:
            it = self.item_dict[utc]
            if not self.has_local_file(it["id"]):
                continue
            # Check if a mask is present
            mask_path = os.path.join(output_folder, "mask")
            mask_filename = f"{it['id']}_mask.png".replace(":", "")
            mask_full = os.path.join(mask_path, mask_filename)
            if not os.path.exists(mask_full):
                continue  # no mask => skip

            prefix = it["id"] + "_"
            flist = [f for f in os.listdir(output_folder) if f.startswith(prefix)]
            if not flist:
                continue

            if self.current_mode == "default":
                default_path = os.path.join(output_folder, "default")
                if os.path.exists(default_path):
                    candidates = [f for f in os.listdir(default_path) if f.startswith(prefix)]
                    if candidates:
                        chosen = sorted(candidates, reverse=True)[0]
                        full_path = os.path.join(default_path, chosen)
                    else:
                        chosen = sorted(flist, reverse=True)[0]
                        full_path = os.path.join(output_folder, chosen)
                else:
                    chosen = sorted(flist, reverse=True)[0]
                    full_path = os.path.join(output_folder, chosen)
            else:
                chosen = sorted(flist, reverse=True)[0]
                full_path = os.path.join(output_folder, chosen)

            try:
                pil_img = Image.open(full_path).convert("RGBA")
            except:
                continue

            merged = self.apply_mask_to_pil(it["id"], pil_img)
            if not merged:
                continue

            # always export as .png
            name, _ = os.path.splitext(chosen)
            out_name = f"{name}_merge.png"
            out_path = os.path.join(merge_dir, out_name)
            try:
                merged.save(out_path, "PNG")
                self.log(f"Exported merged: {out_name}")
            except Exception as e:
                self.log(f"Export error {out_name}: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    WebcamApp(root)
    root.mainloop()
