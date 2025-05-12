import os
import time
import traceback
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import concurrent.futures
from PIL import Image
import numpy as np


class FadingGenerator:
    """
    Provides a create_fading method that takes an input image path (RGB)
    and produces a fade image (width=fade_width, height=fade_height, bottom cut=fade_cut).
    Saves as *_fading.png (unless a different output_path is given).
    """

    def __init__(self, fade_width, fade_height, fade_cut):
        """
        Store the current fade parameters in the FadingGenerator instance.
        """
        self.fade_width = fade_width
        self.fade_height = fade_height
        self.fade_cut = fade_cut

    def create_fading(self, input_path, output_path=None):
        """
        Creates a fade image from 'input_path' (must be an RGB-compatible format).
        If 'output_path' is None, the default is 'input_path' + '_fading' (before extension).
        Returns the final output_path.
        """
        orig = Image.open(input_path).convert("RGB")
        w, h = orig.size
        orig_np = np.array(orig)

        # Prepare the fade array: width=self.fade_width, full height 'h' initially
        fade_w = self.fade_width
        fade_np = np.full((h, fade_w, 3), 255, dtype=np.uint8)
        min_y, max_y = -1, -1

        # Scan each row, find average color of non-white pixels
        for y in range(h):
            row = orig_np[y]
            mask = ~((row[:, 0] == 255) & (row[:, 1] == 255) & (row[:, 2] == 255))
            valid_pixels = row[mask]

            if len(valid_pixels) > 0:
                avg_color = valid_pixels.mean(axis=0).astype(np.uint8)
            else:
                avg_color = np.array([255, 255, 255], dtype=np.uint8)

            if not np.array_equal(avg_color, [255, 255, 255]):
                if min_y < 0:
                    min_y = y
                max_y = y

            fade_np[y, :, :] = avg_color

        fade_img = Image.fromarray(fade_np, 'RGB')

        # Crop top/bottom so only the region that isn't pure white is used
        if min_y == -1:
            # Entirely white
            cropped_img = fade_img
        else:
            cropped_img = fade_img.crop((0, min_y, fade_w, max_y + 1))

        # Resize to self.fade_height, then cut off self.fade_cut
        fade_res = cropped_img.resize((fade_w, self.fade_height + self.fade_cut), Image.LANCZOS)
        final_h = self.fade_height
        if final_h < 0:
            final_h = 0
        fade_final = fade_res.crop((0, 0, fade_w, final_h))

        # Default output path if none provided
        if not output_path:
            dot_index = input_path.rfind(".")
            if dot_index == -1:
                output_path = input_path + "_fading"
            else:
                output_path = input_path[:dot_index] + "_fading" + input_path[dot_index:]

        fade_final.save(output_path)
        return output_path


def worker_merge(base_path, mask_path):
    """
    Merges 'base_path' (RGBA) with 'mask_path' (RGBA),
    producing base_merge.png. Uses traceback for error details.
    """
    start_t = time.perf_counter()
    result = {
        "success": True,
        "error": None,
        "input": base_path,
        "output": None,
        "time": 0.0
    }
    try:
        base = Image.open(base_path).convert("RGBA")
        mask_img = Image.open(mask_path).convert("RGBA")
        if mask_img.size != base.size:
            mask_img = mask_img.resize(base.size, Image.LANCZOS)
        merged = Image.alpha_composite(base, mask_img)

        dirname, fname = os.path.split(base_path)
        name, _ = os.path.splitext(fname)
        out_name = f"{name}_merge.png"
        out_path = os.path.join(dirname, out_name)
        merged.save(out_path, "PNG")
        result["output"] = out_path
    except Exception:
        result["success"] = False
        result["error"] = traceback.format_exc()

    result["time"] = time.perf_counter() - start_t
    return result


def worker_fade(merge_path, fade_width, fade_height, fade_cut):
    """
    Fades a '_merge' file => '_fading', using the user-chosen fade_width, fade_height, fade_cut.
    Returns a dict with success, error, input, output, time.
    """
    start_t = time.perf_counter()
    result = {
        "success": True,
        "error": None,
        "input": merge_path,
        "output": None,
        "time": 0.0
    }
    try:
        gen = FadingGenerator(fade_width, fade_height, fade_cut)

        if merge_path.endswith("_merge.png"):
            out_path = merge_path.replace("_merge.png", "_fading.png")
        else:
            dirname, fname = os.path.split(merge_path)
            name, _ = os.path.splitext(fname)
            out_path = os.path.join(dirname, name + "_fading.png")

        final = gen.create_fading(merge_path, out_path)
        result["output"] = final
    except Exception:
        result["success"] = False
        result["error"] = traceback.format_exc()

    result["time"] = time.perf_counter() - start_t
    return result


class MergeFadingApp:
    """
    A tkinter-based GUI for merging images (optional masks) and then fading them.

    - If no mask is selected => fade all files that end with _merge
      (if none, a message appears).
    - If masks are selected => merges only files that match the prefixes (and
      do not contain _merge, _fading, or the exclude string),
      then fades only the newly created _merge files.

    A Reset button clears Directory and Masks. The number of workers is
    controlled by a Scale. Additionally, fade_width, fade_height, and fade_cut
    can be adjusted via text fields at the top.
    """

    def __init__(self, root):
        """
        Creates the main window and initializes internal states.
        """
        self.root = root
        self.root.title("Vertical Fading")

        # Directory / Mask state
        self.selected_dir = None
        self.prefix_map = {}

        # Exclude substring
        self.exclude_var = tk.StringVar(value="_fading")

        # Worker selection
        self.cpu_count = os.cpu_count() or 1
        default_workers = max(1, self.cpu_count - 2)
        self.worker_count_var = tk.IntVar(value=default_workers)

        # Fade parameters
        self.fade_width_var = tk.IntVar(value=100)
        self.fade_height_var = tk.IntVar(value=2160)
        self.fade_cut_var = tk.IntVar(value=20)

        # Concurrency
        self.executor = None
        self.futures = []
        self.results_list = []
        self.errors_list = []
        self.times_list = []
        self.start_time = 0.0
        self.processing_in_progress = False
        self.canceled = False

        self.setup_ui()

    def setup_ui(self):
        """
        Builds the main user interface, placing all relevant fields (fade params, etc.)
        plus the merges/fading controls in a vertical layout.
        """
        top_frame = tk.Frame(self.root)
        top_frame.pack(padx=10, pady=10)

        # Row for fade_width
        tk.Label(top_frame, text="Fade Width:").pack(anchor="w")
        tk.Entry(top_frame, textvariable=self.fade_width_var).pack(fill="x", pady=2)

        # Row for fade_height
        tk.Label(top_frame, text="Fade Height:").pack(anchor="w")
        tk.Entry(top_frame, textvariable=self.fade_height_var).pack(fill="x", pady=2)

        # Row for fade_cut
        tk.Label(top_frame, text="Fade Cut:").pack(anchor="w")
        tk.Entry(top_frame, textvariable=self.fade_cut_var).pack(fill="x", pady=2)

        # Worker scale
        tk.Label(top_frame, text="Number of workers:").pack(anchor="w")
        self.scale_workers = tk.Scale(
            top_frame,
            from_=1,
            to=self.cpu_count,
            orient=tk.HORIZONTAL,
            variable=self.worker_count_var,
            length=300
        )
        self.scale_workers.pack(pady=5)

        # Directory + Label
        btn_dir = tk.Button(top_frame, text="Load Directory", command=self.on_load_directory)
        btn_dir.pack(fill="x", pady=2)
        self.lbl_dir = tk.Label(top_frame, text="(No directory)", fg="blue")
        self.lbl_dir.pack(anchor="w", pady=2)

        # Mask(s) + Label
        btn_mask = tk.Button(top_frame, text="Load Mask(s)", command=self.on_load_masks)
        btn_mask.pack(fill="x", pady=2)
        self.lbl_masks = tk.Label(top_frame, text="(No masks)", fg="blue", justify="left")
        self.lbl_masks.pack(anchor="w", pady=2)

        # Exclude string
        tk.Label(top_frame, text="Exclude from Mask:").pack(anchor="w")
        self.entry_exclude = tk.Entry(top_frame, textvariable=self.exclude_var)
        self.entry_exclude.pack(fill="x", pady=2)

        # Start, Reset, Close
        btn_start = tk.Button(top_frame, text="Start", command=self.on_start)
        btn_start.pack(fill="x", pady=2)
        btn_reset = tk.Button(top_frame, text="Reset", command=self.on_reset)
        btn_reset.pack(fill="x", pady=2)
        btn_close = tk.Button(top_frame, text="Close", command=self.root.destroy)
        btn_close.pack(fill="x", pady=2)

        # Progress + status
        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(pady=5)

        self.lbl_status = tk.Label(self.root, text="")
        self.lbl_status.pack()

        self.lbl_final = tk.Label(self.root, text="", fg="blue")
        self.lbl_final.pack(pady=5)

    def on_reset(self):
        """
        Resets directory, mask, exclude pattern, fade parameters, status, etc.
        """
        self.selected_dir = None
        self.prefix_map.clear()
        self.lbl_dir.config(text="(No directory)")
        self.lbl_masks.config(text="(No masks)")
        self.exclude_var.set("_fading")
        self.fade_width_var.set(100)
        self.fade_height_var.set(2160)
        self.fade_cut_var.set(20)
        self.lbl_status.config(text="")
        self.lbl_final.config(text="")
        self.progress["value"] = 0

    def on_load_directory(self):
        """
        Opens a directory dialog to pick the folder containing images to merge/fade.
        """
        d = filedialog.askdirectory(title="Select Directory")
        if d:
            self.selected_dir = d
            self.lbl_dir.config(text=d)

    def on_load_masks(self):
        """
        Loads multiple PNG masks. The prefix is everything up to the first underscore.
        If no underscore, use the entire basename. Shows up to 8 prefixes per line.
        """
        ftypes = [("PNG Files", "*.png"), ("All Files", "*.*")]
        selected = filedialog.askopenfilenames(title="Select Mask(s)", filetypes=ftypes)
        if not selected:
            return
        self.prefix_map.clear()
        for path in selected:
            base = os.path.basename(path)
            name, _ = os.path.splitext(base)
            if "_" in name:
                prefix = name.split("_", 1)[0]
            else:
                prefix = name
            self.prefix_map[prefix] = path

        if self.prefix_map:
            sorted_keys = sorted(self.prefix_map.keys())
            lines = []
            for i in range(0, len(sorted_keys), 8):
                chunk = sorted_keys[i:i+8]
                lines.append(", ".join(chunk))
            txt = "\n".join(lines)
        else:
            txt = "(No masks)"
        self.lbl_masks.config(text=txt)

    def on_start(self):
        """
        Starts merging/fading based on whether any masks are loaded.
        If no masks => fade all *_merge. If masks => merge + fade new merges.
        """
        if not self.selected_dir:
            messagebox.showinfo("No Directory", "Please select a directory.")
            return

        self.lbl_final.config(text="")
        self.lbl_status.config(text="Preparing tasks...")
        self.progress["value"] = 0
        self.processing_in_progress = True
        self.canceled = False
        self.results_list = []
        self.errors_list = []
        self.times_list = []
        self.futures = []
        self.start_time = time.perf_counter()

        if not self.prefix_map:
            merges = self.find_all_merge()
            if not merges:
                messagebox.showinfo("No merges found",
                                    "No '_merge' files in directory, nothing to fade.")
                self.finish_all()
                return
            self.run_fade_pass(merges)
        else:
            to_merge = self.find_for_merge()
            if not to_merge:
                messagebox.showinfo("No Merge Candidates",
                                    "No files to merge found (maybe excluded or prefix mismatch).")
                self.finish_all()
                return
            self.run_merge_pass(to_merge)

    def find_all_merge(self):
        """
        Recursively finds all files ending with '_merge' (before extension) in self.selected_dir.
        Returns a list of full paths.
        """
        merges = []
        exts = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
        for root_dir, _, files in os.walk(self.selected_dir or ""):
            for f in files:
                fl = f.lower()
                if any(fl.endswith(e) for e in exts):
                    base_noext, _ = os.path.splitext(f)
                    if base_noext.endswith("_merge"):
                        merges.append(os.path.join(root_dir, f))
        return merges

    def find_for_merge(self):
        """
        Searches images that:
          - do not contain '_merge' or '_fading' in the base,
          - do not contain exclude_var in the base,
          - have a prefix that matches an entry in prefix_map.
        Returns a list of tuples (image_path, mask_path).
        """
        result = []
        exclude_str = self.exclude_var.get().strip().lower()
        exts = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")

        for root_dir, _, files in os.walk(self.selected_dir or ""):
            for f in files:
                fl = f.lower()
                if any(fl.endswith(e) for e in exts):
                    base_noext, _ = os.path.splitext(f)
                    # skip if base includes _merge or _fading
                    if "_merge" in base_noext or "_fading" in base_noext:
                        continue
                    # skip if excludestring is in base
                    if exclude_str and exclude_str in base_noext:
                        continue

                    # determine prefix
                    if "_" in base_noext:
                        pr = base_noext.split("_", 1)[0]
                    else:
                        pr = base_noext

                    if pr in self.prefix_map:
                        fullp = os.path.join(root_dir, f)
                        result.append((fullp, self.prefix_map[pr]))
        return result

    def run_merge_pass(self, merge_list):
        """
        Launches the merge tasks for a list of (image, mask) pairs.
        """
        self.progress["maximum"] = len(merge_list)
        self.progress["value"] = 0
        wcount = max(1, self.worker_count_var.get())

        self.executor = concurrent.futures.ProcessPoolExecutor(max_workers=wcount)
        self.lbl_status.config(text=f"Merging {len(merge_list)} items...")

        for (imgp, maskp) in merge_list:
            fut = self.executor.submit(worker_merge, imgp, maskp)
            self.futures.append(fut)

        self.root.after(100, self.check_merge_done)

    def check_merge_done(self):
        """
        Monitors the merge tasks. Once finished, collects new merges and triggers fading.
        """
        if self.canceled or not self.processing_in_progress:
            return

        done_count = sum(f.done() for f in self.futures)
        self.progress["value"] = done_count
        self.lbl_status.config(text=f"Merging... {done_count}/{len(self.futures)}")

        for f in self.futures:
            if f.done() and not hasattr(f, "_merge_done"):
                setattr(f, "_merge_done", True)
                try:
                    res = f.result()
                    if res["success"]:
                        self.results_list.append(res["output"])
                    else:
                        self.errors_list.append(
                            f"{os.path.basename(res['input'])}: {res['error']}"
                        )
                    self.times_list.append(res["time"])
                except Exception as e:
                    self.errors_list.append(str(e))

        if done_count < len(self.futures):
            self.root.after(100, self.check_merge_done)
        else:
            merged_paths = [r for r in self.results_list if r and r.endswith("_merge.png")]
            self.finish_merge_pass(merged_paths)

    def finish_merge_pass(self, merged_paths):
        """
        After merging is done, we shut down the executor. If merges exist,
        we do a new fade pass on them. Otherwise we skip fading.
        """
        if self.executor:
            self.executor.shutdown(wait=False)

        self.futures.clear()
        if not merged_paths:
            messagebox.showinfo("No merges created",
                                "No *_merge files were created, skipping fading.")
            self.finish_all()
            return

        self.progress["maximum"] = len(merged_paths)
        self.progress["value"] = 0
        wcount = max(1, self.worker_count_var.get())

        self.executor = concurrent.futures.ProcessPoolExecutor(max_workers=wcount)
        self.lbl_status.config(text=f"Fading {len(merged_paths)} merges...")

        # Retrieve user fade parameters
        fade_w = self.fade_width_var.get()
        fade_h = self.fade_height_var.get()
        fade_c = self.fade_cut_var.get()

        for p in merged_paths:
            fut = self.executor.submit(worker_fade, p, fade_w, fade_h, fade_c)
            self.futures.append(fut)

        self.root.after(100, self.check_fade_done)

    def run_fade_pass(self, merges_list):
        """
        Runs the fade process on a list of existing _merge files (no masks).
        If merges_list is empty, it shows a message and ends.
        """
        self.futures.clear()
        self.progress["maximum"] = len(merges_list)
        self.progress["value"] = 0
        if not merges_list:
            messagebox.showinfo("No merges found", "Nothing to fade.")
            self.finish_all()
            return

        wcount = max(1, self.worker_count_var.get())
        self.executor = concurrent.futures.ProcessPoolExecutor(max_workers=wcount)

        self.lbl_status.config(text=f"Fading {len(merges_list)} merges...")

        # Retrieve user fade parameters
        fade_w = self.fade_width_var.get()
        fade_h = self.fade_height_var.get()
        fade_c = self.fade_cut_var.get()

        for m in merges_list:
            fut = self.executor.submit(worker_fade, m, fade_w, fade_h, fade_c)
            self.futures.append(fut)

        self.root.after(100, self.check_fade_done)

    def check_fade_done(self):
        """
        Monitors the fade tasks. Once all done, calls finish_all().
        """
        if self.canceled or not self.processing_in_progress:
            return

        done_count = sum(f.done() for f in self.futures)
        self.progress["value"] = done_count
        self.lbl_status.config(text=f"Fading... {done_count}/{len(self.futures)}")

        for f in self.futures:
            if f.done() and not hasattr(f, "_fading_done"):
                setattr(f, "_fading_done", True)
                try:
                    res = f.result()
                    if res["success"]:
                        self.results_list.append(res["output"])
                    else:
                        self.errors_list.append(
                            f"{os.path.basename(res['input'])}: {res['error']}"
                        )
                    self.times_list.append(res["time"])
                except Exception as e:
                    self.errors_list.append(str(e))

        if done_count < len(self.futures):
            self.root.after(100, self.check_fade_done)
        else:
            self.finish_all()

    def finish_all(self):
        """
        Once merging/fading is fully done, we shut down the executor
        and display final stats or an error summary, if any.
        """
        if self.executor:
            self.executor.shutdown(wait=False)

        elapsed = time.perf_counter() - self.start_time
        self.lbl_status.config(text="All done.")
        total = len(self.times_list)
        if total > 0:
            avg = sum(self.times_list) / total
            msg = (f"Processed {total} tasks.\n"
                   f"Avg time per task: {avg:.2f}s\n"
                   f"Total time: {int(elapsed)}s")
            if self.errors_list:
                msg += "\nErrors:\n" + ", ".join(self.errors_list)
            self.lbl_final.config(text=msg)
        else:
            self.lbl_final.config(text="No images processed.")
        self.processing_in_progress = False


def main():
    """
    Starts the tkinter GUI, instantiating MergeFadingApp and running mainloop.
    """
    root = tk.Tk()
    app = MergeFadingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
