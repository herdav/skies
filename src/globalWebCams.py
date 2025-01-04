# globalWebCams.py
# Created by David Herren
# Version 2025-01-04

import os, json, webbrowser, tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFont
from datetime import datetime

from routines.skylinewebcams import SkylinewebcamsBot
from routines.webcamimage import download_webcam_image
from routines.dynamicjpg import download_dynamic_jpg
from routines.youtube import download_youtube_screenshot
from routines.faratel import download_faratel_screenshot

output_folder = "img"
os.makedirs(output_folder, exist_ok=True)

def load_cameras_from_json():
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
    s = "+" if i >= 0 else ""
    return f"UTC{s}{i}"

class Tooltip:
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
    def __init__(self, root):
        self.root = root
        self.root.title("globalWebCams")
        self.root.geometry("1200x800")

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

        self.right_frame = tk.Frame(root, width=300)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = tk.Text(self.right_frame, width=40)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.btn_frame = tk.Frame(root)
        self.btn_frame.pack(pady=10)

        tk.Button(self.btn_frame, text="Run All Selected", command=self.run_bot).pack(side=tk.LEFT, padx=5)
        tk.Button(self.btn_frame, text="Select All", command=self.select_all).pack(side=tk.LEFT, padx=5)
        tk.Button(self.btn_frame, text="Deselect All", command=self.deselect_all).pack(side=tk.LEFT, padx=5)
        tk.Button(self.btn_frame, text="Clear History", command=self.clear_history).pack(side=tk.LEFT, padx=5)

        self.photo_images = {}
        self.selected_items = {}
        self.download_times = {}
        self.cell_frames = {}
        self.frame_colors = {}

        all_items = (
            self.faratelUrls
            + self.skylinewebcamsUrls
            + self.webcamimageUrls
            + self.dynamicjpgUrls
            + self.youtubeVideos
        )
        self.item_dict = {}
        for it in all_items:
            self.item_dict[it["id"]] = it

        self.all_utc_ids = [format_utc(i) for i in range(-11, 13)]
        for u in self.all_utc_ids:
            if u not in self.item_dict:
                self.item_dict[u] = {"id": u, "url": None}
            self.selected_items[u] = tk.BooleanVar(value=True)

        self.load_images()

    def log(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def clear_history(self):
        self.log_text.delete("1.0", tk.END)
        self.log("Cleared history")

    def select_all(self):
        for u in self.all_utc_ids:
            if self.item_dict[u]["url"]:
                self.selected_items[u].set(True)
            else:
                self.selected_items[u].set(False)
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

    def download_faratel(self, it):
        prev_files = set(os.listdir(output_folder))
        f = download_faratel_screenshot(it["url"], it["id"])
        new_files = set(os.listdir(output_folder)) - prev_files
        found_new = any(x.startswith(it["id"] + "_") for x in new_files)
        if f and found_new:
            self.download_times[it["id"]] = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log(f"Faratel screenshot: {it['id']}")
            return (True, True)
        return (True, False)

    def download_skyline(self, it):
        prev_files = set(os.listdir(output_folder))
        bot = SkylinewebcamsBot(it["url"], it["id"])
        bot.load_website()
        bot.accept_consent()
        bot.interact_with_webcam()
        bot.activate_fullscreen_and_hide_elements()
        bot.quit()
        new_files = set(os.listdir(output_folder)) - prev_files
        found_new = any(f.startswith(it["id"] + "_") for f in new_files)
        if found_new:
            self.download_times[it["id"]] = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log(f"Skyline downloaded: {it['id']}")
        return (True, found_new)

    def download_webcamimage(self, it):
        prev_files = set(os.listdir(output_folder))
        f = download_webcam_image(it["url"], it["id"])
        new_files = set(os.listdir(output_folder)) - prev_files
        found_new = any(x.startswith(it["id"] + "_") for x in new_files)
        if f and found_new:
            self.download_times[it["id"]] = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log(f"Webcam downloaded: {it['id']}")
            return (True, True)
        return (True, False)

    def download_dynamicjpg(self, it):
        prev_files = set(os.listdir(output_folder))
        f = download_dynamic_jpg(
            url=it["url"],
            element_id=it.get("id"),
            element_class=it.get("class"),
            src_pattern=it.get("src"),
            image_id=it["id"]
        )
        new_files = set(os.listdir(output_folder)) - prev_files
        found_new = any(x.startswith(it["id"] + "_") for x in new_files)
        if f and found_new:
            self.download_times[it["id"]] = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log(f"Dynamic JPG downloaded: {it['id']}")
            return (True, True)
        return (True, False)

    def download_youtube(self, it):
        prev_files = set(os.listdir(output_folder))
        f = download_youtube_screenshot(it["url"], it["id"])
        new_files = set(os.listdir(output_folder)) - prev_files
        found_new = any(x.startswith(it["id"] + "_") for x in new_files)
        if f and found_new:
            self.download_times[it["id"]] = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log(f"YouTube screenshot: {it['id']}")
            return (True, True)
        return (True, False)

    def reload_image(self, it):
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
        for w in self.container.winfo_children():
            w.destroy()
        self.cell_frames.clear()
        cols = 6
        for idx, utc in enumerate(self.all_utc_ids):
            r = idx // cols
            c = idx % cols
            self.create_cell(utc, r, c)

    def create_cell(self, utcid, row, col):
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
        cell = self.cell_frames.get(utcid)
        if not cell:
            return
        for ch in cell.winfo_children():
            ch.destroy()

        it = self.item_dict[utcid]
        img = self.get_tk_image(it, 180, 120)
        self.photo_images[it["id"]] = img

        lbl_img = tk.Label(cell, image=img, bg="white")
        lbl_img.pack(side=tk.TOP, pady=2)

        has_file = self.has_local_file(it["id"])

        # If there is a local file, we allow full-screen on click
        if has_file:
            lbl_img.config(cursor="hand2")
            lbl_img.bind("<Button-1>", lambda e: self.open_full_image(it))

        t = self.download_times.get(utcid, "N/A")
        tk.Label(cell, text=f"{utcid} {t}").pack(side=tk.TOP, pady=2)

        row_line = tk.Frame(cell)
        row_line.pack(side=tk.TOP, pady=2)

        # We only disable 'Reload' if there's NO URL
        # If there's a URL but no local file, we keep 'Reload' enabled
        if it["url"]:
            cb_state = "normal"
            rb_state = "normal"
        else:
            cb_state = "disabled"
            rb_state = "disabled"

        cb = tk.Checkbutton(row_line, text="Aktiv", variable=self.selected_items[utcid], state=cb_state)
        cb.pack(side=tk.LEFT, padx=3)

        rb = tk.Button(row_line, text="Reload", command=lambda i=it: self.reload_image(i), state=rb_state)
        rb.pack(side=tk.LEFT, padx=3)

        # Link label only if there's a URL
        if it["url"]:
            link_lbl = tk.Label(row_line, text="Link", fg="blue", cursor="hand2")
            link_lbl.pack(side=tk.LEFT, padx=3)
            link_lbl.bind("<Button-1>", lambda e, url=it["url"]: webbrowser.open(url))
            Tooltip(link_lbl, it["url"])

    def has_local_file(self, utcid):
        if not os.path.exists(output_folder):
            return False
        pre = utcid + "_"
        flist = [f for f in os.listdir(output_folder) if f.startswith(pre)]
        return len(flist) > 0

    def get_tk_image(self, it, w, h):
        if not os.path.exists(output_folder):
            return self.create_placeholder(w,h,it["id"])
        prefix = it["id"] + "_"
        flist = [f for f in os.listdir(output_folder) if f.startswith(prefix)]
        if flist:
            latest = sorted(flist, reverse=True)[0]
            path = os.path.join(output_folder, latest)
            try:
                im = Image.open(path)
                im.thumbnail((w,h), Image.LANCZOS)
                return ImageTk.PhotoImage(im)
            except:
                return self.create_placeholder(w,h,it["id"])
        else:
            return self.create_placeholder(w,h,it["id"])

    def create_placeholder(self, w, h, txt):
        img = Image.new("RGB",(w,h),(220,220,220))
        d = ImageDraw.Draw(img)
        f = ImageFont.load_default()
        box = d.textbbox((0,0), txt, font=f)
        x = (w - box[2])//2
        y = (h - box[3])//2
        d.text((x,y), txt, font=f, fill=(0,0,0))
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

        orig = self.get_original_pil(it)
        if not orig:
            orig = self.create_placeholder_img(800,600,it["id"])
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

    def get_original_pil(self, it):
        if not os.path.exists(output_folder):
            return None
        prefix = it["id"] + "_"
        files = [f for f in os.listdir(output_folder) if f.startswith(prefix)]
        if not files:
            return None
        latest = sorted(files, reverse=True)[0]
        path = os.path.join(output_folder, latest)
        try:
            return Image.open(path)
        except:
            return None

    def create_placeholder_img(self, w,h,txt):
        img = Image.new("RGB",(w,h),(220,220,220))
        d = ImageDraw.Draw(img)
        f = ImageFont.load_default()
        box = d.textbbox((0,0), txt, font=f)
        x = (w-box[2])//2
        y = (h-box[3])//2
        d.text((x,y), txt, font=f, fill=(0,0,0))
        return img

if __name__ == "__main__":
    root = tk.Tk()
    WebcamApp(root)
    root.mainloop()
