import os
import re
import json
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime


def hhmmss_to_seconds(hhmmss: str) -> int:
    """
    Convert a string in 'hhmmss' format to an integer representing total seconds.
    """
    if len(hhmmss) != 6:
        return 0
    hh = int(hhmmss[0:2])
    mm = int(hhmmss[2:4])
    ss = int(hhmmss[4:6])
    return hh * 3600 + mm * 60 + ss


def seconds_to_hhmmss_str(total_seconds: int) -> str:
    """
    Convert an integer number of seconds into a string formatted 'Hh Mm Ss'.
    """
    if total_seconds < 0:
        total_seconds = 0
    hh = total_seconds // 3600
    remainder = total_seconds % 3600
    mm = remainder // 60
    ss = remainder % 60
    return f"{hh}h {mm}m {ss}s" if hh > 0 else f"{mm}m {ss}s"


class FolderParser:
    """
    Parses subfolders to determine:
    - which timezone was successful or failed,
    - the time difference between the oldest and newest file name in each subfolder (based on hhmmss),
    - and skip certain folder names.
    """

    RE_FAIL = re.compile(r"Download failed for (UTC[+\-]\d+)\s*=>")
    SKIP_FOLDERS = {"00000000_000000", "99999999_999999"}

    # Now we search for a dash plus 6 digits before the file extension, e.g. "-091840.jpg"
    # That means the file name might look like "UTC+0_20250404-091840.jpg".
    RE_HHMMSS = re.compile(r"-(\d{6})\.")

    def __init__(self, timezones, mode="Merge"):
        """
        :param timezones: list of timezones, e.g. ["UTC-11", ..., "UTC+12"]
        :param mode: "Merge" => only *_merge.png, "Image" => *.png and *.jpg
        """
        self.timezones = timezones
        self.results = {}

        if mode == "Merge":
            # Example: "UTC-4_20250122_081806_merge.png"
            self.re_image = re.compile(r"(UTC[+\-]\d+)_.*_merge\.png")
        else:
            # "Image" => match .png or .jpg (case-insensitive)
            # Example: "UTC-4_20250122-081806.jpg" or ".png"
            self.re_image = re.compile(r"(UTC[+\-]\d+)_.*\.(?:png|jpg)$", re.IGNORECASE)

    def parse(self, root_folder):
        """
        Scan each subfolder in 'root_folder'. For each subfolder:
         - Skip if in SKIP_FOLDERS
         - Initialize all timezones to False
         - Check files:
           - If it matches the image regex, set the corresponding tz to True
           - If a .txt has a "Download failed ..." line, set tz to False
           - Collect hhmmss to calculate min/max difference
        """
        entries = [e for e in os.scandir(root_folder) if e.is_dir()]

        for entry in entries:
            subfolder_name = entry.name
            if subfolder_name in self.SKIP_FOLDERS:
                continue

            tz_status = {tz: False for tz in self.timezones}

            # We'll collect all hhmmss values here to compute min/max
            times_in_subfolder = []

            for file_obj in os.scandir(entry.path):
                if not file_obj.is_file():
                    continue
                filename = file_obj.name

                # Check for matching timezones
                img_match = self.re_image.match(filename)
                if img_match:
                    tz_found = img_match.group(1)
                    if tz_found in tz_status:
                        tz_status[tz_found] = True

                # Check for "Download failed"
                if filename.endswith(".txt"):
                    with open(file_obj.path, "r", encoding="utf-8") as txt_file:
                        for line in txt_file:
                            fail_match = self.RE_FAIL.search(line)
                            if fail_match:
                                tz_failed = fail_match.group(1)
                                if tz_failed in tz_status:
                                    tz_status[tz_failed] = False

                # Extract hhmmss if present
                time_match = self.RE_HHMMSS.search(filename)
                if time_match:
                    hhmmss = time_match.group(1)
                    times_in_subfolder.append(hhmmss)

            ok_count = sum(tz_status.values())
            fail_count = len(tz_status) - ok_count

            # Compute time range (newest - oldest) if we found at least 2 times
            if len(times_in_subfolder) >= 2:
                seconds_list = [hhmmss_to_seconds(t) for t in times_in_subfolder]
                range_sec = max(seconds_list) - min(seconds_list)
                time_range_str = seconds_to_hhmmss_str(range_sec)
            else:
                time_range_str = ""

            self.results[subfolder_name] = {
                "tz_status": tz_status,
                "ok_count": ok_count,
                "fail_count": fail_count,
                "time_range": time_range_str,
            }

        return self.results

    def get_results(self):
        """
        Return the parsed results dictionary.
        """
        return self.results

    def compute_summary(self):
        """
        Compute how many subfolders had each timezone set to True.
        """
        total_subfolders = len(self.results)
        summary_dict = {}
        for tz in self.timezones:
            summary_dict[tz] = {"ok_count": 0, "total": total_subfolders}

        for sub_data in self.results.values():
            for tz, val in sub_data["tz_status"].items():
                if val:
                    summary_dict[tz]["ok_count"] += 1

        return summary_dict


class StatsApp(tk.Tk):
    """
    Main GUI application for displaying folder parsing results.
    """

    def __init__(self):
        super().__init__()
        self.title("Statistical Analysis")

        self.parser = None
        self.selected_folder = None
        self.timezones = self._get_timezones()

        # Top frame (buttons, dropdown)
        top_frame = tk.Frame(self)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        self.select_button = tk.Button(
            top_frame, text="Select Folder", command=self.select_folder
        )
        self.select_button.pack(side=tk.LEFT, padx=5)

        self.mode_var = tk.StringVar(value="Merge")
        self.dropdown = tk.OptionMenu(top_frame, self.mode_var, "Merge", "Image")
        self.dropdown.config(width=7)
        self.dropdown.pack(side=tk.LEFT, padx=5)

        self.calculate_button = tk.Button(
            top_frame,
            text="Calculate",
            command=self.calculate_results,
            state=tk.DISABLED,
        )
        self.calculate_button.pack(side=tk.LEFT, padx=5)

        self.export_button = tk.Button(
            top_frame,
            text="Export as json",
            command=self.export_results,
            state=tk.DISABLED,
        )
        self.export_button.pack(side=tk.LEFT, padx=5)

        # Main scrollable area for the table
        self.canvas_frame = tk.Frame(self)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.canvas_frame)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.scrollbar = tk.Scrollbar(
            self.canvas_frame, orient="vertical", command=self.canvas.yview
        )
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.table_frame = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.table_frame, anchor="nw")
        self.table_frame.bind("<Configure>", self._on_frame_configure)

    def _get_timezones(self):
        tz_list = []
        for i in range(-11, 13):
            if i >= 0:
                tz_list.append(f"UTC+{i}")
            else:
                tz_list.append(f"UTC{i}")
        return tz_list

    def select_folder(self):
        """
        Let user pick a directory, but do not parse immediately.
        Enable 'Calculate' so the user can run the analysis.
        """
        folder_selected = filedialog.askdirectory()
        if not folder_selected:
            return

        self.selected_folder = folder_selected
        self.clear_table()

        self.calculate_button.config(state=tk.NORMAL)
        self.export_button.config(state=tk.DISABLED)

    def calculate_results(self):
        """
        Create a parser with the chosen mode and parse the selected folder.
        Then build the table with the results.
        """
        if not self.selected_folder:
            return

        self.clear_table()

        mode_choice = self.mode_var.get()  # "Merge" or "Image"

        self.parser = FolderParser(self.timezones, mode=mode_choice)
        self.parser.parse(self.selected_folder)

        self._build_table()

        if self.parser.get_results():
            self.export_button.config(state=tk.NORMAL)

    def clear_table(self):
        """
        Remove all widgets in the table frame.
        """
        for widget in self.table_frame.winfo_children():
            widget.destroy()

    def _build_table(self):
        """
        Build the table:
         - Heading row at the top
         - One row per subfolder (sorted by datetime in subfolder name if possible)
         - Repeat the heading row at the bottom
         - Summary row
        """
        results = self.parser.get_results()
        if not results:
            return

        # Collect subfolders with valid datetime
        subfolders_dt = []
        for subfolder_name in results.keys():
            try:
                dt_val = datetime.strptime(subfolder_name, "%Y%m%d_%H%M%S")
                subfolders_dt.append((subfolder_name, dt_val))
            except ValueError:
                pass

        subfolders_dt.sort(key=lambda x: x[1])

        # Build diffs
        diffs_seconds = []
        for idx, (name, dt_val) in enumerate(subfolders_dt):
            if idx == 0:
                continue
            prev_dt = subfolders_dt[idx - 1][1]
            delta = dt_val - prev_dt
            diffs_seconds.append(int(delta.total_seconds()))
        avg_diff = 0
        if diffs_seconds:
            avg_diff = sum(diffs_seconds) / len(diffs_seconds)

        # Columns:
        # col 0 => Subfolder
        # col 1 => Diff
        # col 2 => Range
        # col 3.. => timezones
        # last => Fail

        self._build_heading_row(0)
        row_index = 1

        for idx, (subfolder_name, dt_val) in enumerate(subfolders_dt):
            data = results[subfolder_name]
            tz_status = data["tz_status"]
            fail_count = data["fail_count"]
            time_range_str = data["time_range"]

            # Subfolder
            tk.Label(
                self.table_frame,
                text=subfolder_name,
                borderwidth=1,
                relief="solid",
                anchor="center",
            ).grid(row=row_index, column=0, sticky="nsew")

            # Diff
            if idx == 0:
                diff_str = ""
                diff_sec = None
            else:
                prev_dt = subfolders_dt[idx - 1][1]
                delta = dt_val - prev_dt
                diff_sec = int(delta.total_seconds())
                minutes = diff_sec // 60
                seconds = diff_sec % 60
                diff_str = f"{minutes}m {seconds}s"

            default_bg = self.table_frame.cget("bg")
            diff_bg = default_bg
            diff_fg = "black"
            diff_font = None
            if diff_sec is not None and avg_diff > 0:
                ratio = abs(diff_sec - avg_diff) / avg_diff
                if ratio > 0.05:
                    diff_bg = "#ff0000"
                    diff_fg = "white"
                    diff_font = ("TkDefaultFont", 9, "bold")

            tk.Label(
                self.table_frame,
                text=diff_str,
                bg=diff_bg,
                fg=diff_fg,
                font=diff_font,
                borderwidth=1,
                relief="solid",
                anchor="center",
            ).grid(row=row_index, column=1, sticky="nsew")

            # Range
            tk.Label(
                self.table_frame,
                text=time_range_str,
                borderwidth=1,
                relief="solid",
                anchor="center",
            ).grid(row=row_index, column=2, sticky="nsew")

            # Timezones
            for c_idx, tz in enumerate(self.timezones, start=3):
                status_ok = tz_status[tz]
                cell_bg = "#afffaf" if status_ok else "#ff0000"
                cell_fg = "black" if status_ok else "white"

                tk.Label(
                    self.table_frame,
                    text="",
                    bg=cell_bg,
                    fg=cell_fg,
                    borderwidth=1,
                    relief="solid",
                    anchor="center",
                ).grid(row=row_index, column=c_idx, sticky="nsew")

            # Fail
            sum_col_idx = 3 + len(self.timezones)
            if fail_count == 0:
                sum_text = "0"
                sum_bg = "#00ff00"
                sum_fg = "black"
                sum_font = None
            else:
                sum_text = str(fail_count)
                sum_bg = "#ff0000"
                sum_fg = "white"
                sum_font = ("TkDefaultFont", 9, "bold")

            tk.Label(
                self.table_frame,
                text=sum_text,
                fg=sum_fg,
                bg=sum_bg,
                font=sum_font,
                borderwidth=1,
                relief="solid",
                anchor="center",
            ).grid(row=row_index, column=sum_col_idx, sticky="nsew")

            row_index += 1

        # Repeat heading row
        bottom_heading = row_index
        self._build_heading_row(bottom_heading)
        row_index += 1

        # Summary row
        summary_row = row_index
        summary = self.parser.compute_summary()
        if summary:
            # col 0 => empty
            tk.Label(self.table_frame, text="", borderwidth=1, relief="solid").grid(
                row=summary_row, column=0, sticky="nsew"
            )
            # col 1 => empty
            tk.Label(self.table_frame, text="", borderwidth=1, relief="solid").grid(
                row=summary_row, column=1, sticky="nsew"
            )
            # col 2 => empty
            tk.Label(self.table_frame, text="", borderwidth=1, relief="solid").grid(
                row=summary_row, column=2, sticky="nsew"
            )

            for c_idx, tz in enumerate(self.timezones, start=3):
                ok_count = summary[tz]["ok_count"]
                total = summary[tz]["total"]
                missing = total - ok_count
                if missing == 0:
                    cell_text = "0"
                    cell_bg = "#00ff00"
                    cell_fg = "black"
                    cell_font = None
                else:
                    cell_text = str(missing)
                    cell_bg = "#ff0000"
                    cell_fg = "white"
                    cell_font = ("TkDefaultFont", 9, "bold")

                tk.Label(
                    self.table_frame,
                    text=cell_text,
                    fg=cell_fg,
                    bg=cell_bg,
                    font=cell_font,
                    borderwidth=1,
                    relief="solid",
                    anchor="center",
                ).grid(row=summary_row, column=c_idx, sticky="nsew")

            last_col = 3 + len(self.timezones)
            tk.Label(self.table_frame, text="", borderwidth=1, relief="solid").grid(
                row=summary_row, column=last_col, sticky="nsew"
            )

        # Make columns expand evenly
        total_cols = 3 + len(self.timezones) + 1
        for col_i in range(total_cols):
            self.table_frame.columnconfigure(col_i, weight=1)

        self.canvas.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def _build_heading_row(self, row_idx: int):
        """
        Create a heading row with:
         Subfolder | Diff | Range | <timezones> | Fail
        """
        tk.Label(
            self.table_frame,
            text="Subfolder",
            borderwidth=1,
            relief="solid",
            anchor="center",
        ).grid(row=row_idx, column=0, sticky="nsew")

        tk.Label(
            self.table_frame,
            text="Diff",
            borderwidth=1,
            relief="solid",
            anchor="center",
        ).grid(row=row_idx, column=1, sticky="nsew")

        tk.Label(
            self.table_frame,
            text="Range",
            borderwidth=1,
            relief="solid",
            anchor="center",
        ).grid(row=row_idx, column=2, sticky="nsew")

        for i, tz in enumerate(self.timezones, start=3):
            tk.Label(
                self.table_frame,
                text=tz,
                borderwidth=1,
                relief="solid",
                anchor="center",
            ).grid(row=row_idx, column=i, sticky="nsew")

        last_col = 3 + len(self.timezones)
        tk.Label(
            self.table_frame,
            text="Fail",
            borderwidth=1,
            relief="solid",
            anchor="center",
        ).grid(row=row_idx, column=last_col, sticky="nsew")

    def _on_frame_configure(self, event):
        """
        Adjust the canvas scroll region whenever the frame size changes.
        """
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def export_results(self):
        """
        Export parser results and summary to a JSON file.
        """
        if not self.parser or not self.parser.get_results():
            return

        results = self.parser.get_results()
        summary = self.parser.compute_summary()

        export_data = {"subfolders": [], "summary": {}}

        for subfolder_name, data in results.items():
            tz_bool_dict = data["tz_status"]
            tz_str_dict = {}
            for tz, val in tz_bool_dict.items():
                tz_str_dict[tz] = "ok" if val else "false"

            export_data["subfolders"].append(
                {
                    "name": subfolder_name,
                    "results": tz_str_dict,
                    "ok_count": data["ok_count"],
                    "fail_count": data["fail_count"],
                    "time_range": data["time_range"],
                }
            )

        for tz, sdata in summary.items():
            export_data["summary"][tz] = {
                "ok_count": sdata["ok_count"],
                "total": sdata["total"],
            }

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON file", "*.json"), ("All files", "*.*")],
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                messagebox.showinfo(
                    "Export successful", f"Data has been exported to:\n{file_path}"
                )
            except Exception as e:
                messagebox.showerror("Export error", str(e))


def main():
    app = StatsApp()
    app.geometry("1400x700")
    app.mainloop()


if __name__ == "__main__":
    main()
