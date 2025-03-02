import os
import re
import json
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime


class FolderParser:
    """
    Parses subfolders to determine whether each timezone was successful or failed.
    Skips certain folder names and stores results for the rest.
    """

    RE_MERGE = re.compile(r"(UTC[+\-]\d+)_.*_merge\.png")
    RE_FAIL = re.compile(r"Download failed for (UTC[+\-]\d+)\s*=>")

    SKIP_FOLDERS = {"00000000_000000", "99999999_999999"}

    def __init__(self, timezones):
        """
        Initialize parser with a list of timezones.
        """
        self.timezones = timezones
        self.results = {}

    def parse(self, root_folder):
        """
        Parse each subfolder in 'root_folder', scanning for *_merge.png (ok)
        and .txt logs indicating failed downloads (false).

        Skip folders named in SKIP_FOLDERS.

        :param root_folder: The directory to parse
        :return: Dictionary with parsing results
        """
        entries = [e for e in os.scandir(root_folder) if e.is_dir()]

        for entry in entries:
            subfolder_name = entry.name

            # Skip certain folder names
            if subfolder_name in self.SKIP_FOLDERS:
                continue

            # Initialize tz_status with booleans (False by default)
            tz_status = {tz: False for tz in self.timezones}

            # Scan each file in the subfolder once
            for file_obj in os.scandir(entry.path):
                if not file_obj.is_file():
                    continue
                filename = file_obj.name
                merge_match = self.RE_MERGE.match(filename)
                if merge_match:
                    tz_found = merge_match.group(1)
                    if tz_found in tz_status:
                        tz_status[tz_found] = True
                elif filename.endswith(".txt"):
                    with open(file_obj.path, "r", encoding="utf-8") as txt_file:
                        for line in txt_file:
                            fail_match = self.RE_FAIL.search(line)
                            if fail_match:
                                tz_failed = fail_match.group(1)
                                if tz_failed in tz_status:
                                    tz_status[tz_failed] = False

            # Summations for each subfolder
            ok_count = sum(tz_status.values())
            fail_count = len(tz_status) - ok_count

            self.results[subfolder_name] = {
                "tz_status": tz_status,
                "ok_count": ok_count,
                "fail_count": fail_count
            }

        return self.results

    def get_results(self):
        """
        Return the parsed results dictionary.
        """
        return self.results

    def compute_summary(self):
        """
        Compute the summary of how many subfolders had each timezone set to ok.

        :return: Dict of timezones with {ok_count: X, total: Y}
        """
        total_subfolders = len(self.results)
        summary_dict = {}
        for tz in self.timezones:
            summary_dict[tz] = {
                "ok_count": 0,
                "total": total_subfolders
            }

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
        """
        Initialize the main window, layout, and widgets.
        """
        super().__init__()
        self.title("Statistical Analysis")

        # Parser will be created once a folder is selected
        self.parser = None

        # Build timezone list
        self.timezones = self._get_timezones()

        # Top frame with buttons
        top_frame = tk.Frame(self)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        self.select_button = tk.Button(
            top_frame,
            text="Select Folder",
            command=self.select_folder
        )
        self.select_button.pack(side=tk.LEFT, padx=5)

        self.export_button = tk.Button(
            top_frame,
            text="Export as json",
            command=self.export_results,
            state=tk.DISABLED
        )
        self.export_button.pack(side=tk.LEFT, padx=5)

        # Main scrollable area for the table
        self.canvas_frame = tk.Frame(self)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.canvas_frame)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.scrollbar = tk.Scrollbar(
            self.canvas_frame,
            orient="vertical",
            command=self.canvas.yview
        )
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Frame inside canvas to hold the table rows
        self.table_frame = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.table_frame, anchor="nw")

        self.table_frame.bind("<Configure>", self._on_frame_configure)

    def _get_timezones(self):
        """
        Build a list of timezones from UTC-11 to UTC+12.
        """
        tz_list = []
        for i in range(-11, 13):
            if i >= 0:
                tz_list.append(f"UTC+{i}")
            else:
                tz_list.append(f"UTC{i}")
        return tz_list

    def select_folder(self):
        """
        Ask user for a directory, parse it, and build the table.
        """
        folder_selected = filedialog.askdirectory()
        if not folder_selected:
            return

        # Clear existing table
        for widget in self.table_frame.winfo_children():
            widget.destroy()

        # Create parser, parse the folder
        self.parser = FolderParser(self.timezones)
        self.parser.parse(folder_selected)

        # Build the table
        self._build_table()

        if self.parser.get_results():
            self.export_button.config(state=tk.NORMAL)

    def _build_table(self):
        """
        Build the table with:
          1) Heading row at the top
          2) Subfolder rows (sorted by datetime)
          3) Heading row again at the bottom
          4) Summary row
        Also compute average of Diffs (seconds). If a Diff cell is ±5% off that average,
        color it red with white text.
        """
        results = self.parser.get_results()
        if not results:
            return

        # Gather subfolders with dt
        subfolders_dt = []
        for subfolder_name in results.keys():
            try:
                dt_val = datetime.strptime(subfolder_name, "%Y%m%d_%H%M%S")
                subfolders_dt.append((subfolder_name, dt_val))
            except ValueError:
                pass

        # Sort them
        subfolders_dt.sort(key=lambda x: x[1])

        # Compute diffs in seconds (for the 2..N subfolders)
        # Store them so we can compute average
        diffs_seconds = []
        for idx, (name, dt_val) in enumerate(subfolders_dt):
            if idx == 0:
                # no diff
                continue
            prev_dt = subfolders_dt[idx - 1][1]
            delta = dt_val - prev_dt
            diffs_seconds.append(int(delta.total_seconds()))

        # Compute average
        avg_diff = 0
        if diffs_seconds:
            avg_diff = sum(diffs_seconds) / len(diffs_seconds)  # float

        # We'll define columns like:
        # col 0 => "Subfolder"
        # col 1 => "Diff"
        # col 2.. => timezones
        # last => sum cell

        # 1) Heading row at the top
        self._build_heading_row(row_index=0)
        row_index = 1

        # 2) Subfolder rows
        for idx, (subfolder_name, dt_val) in enumerate(subfolders_dt):
            data = results[subfolder_name]
            tz_status = data["tz_status"]
            ok_count = data["ok_count"]
            fail_count = data["fail_count"]

            # Subfolder name
            tk.Label(
                self.table_frame,
                text=subfolder_name,
                borderwidth=1,
                relief="solid",
                anchor="center"
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

            # Determine background for diff cell
            # By default, use parent's background:
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
                borderwidth=1,
                relief="solid",
                anchor="center",
                bg=diff_bg,
                fg=diff_fg,
                font=diff_font
            ).grid(row=row_index, column=1, sticky="nsew")

            # Timezones
            for c_idx, tz in enumerate(self.timezones, start=2):
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
                    anchor="center"
                ).grid(row=row_index, column=c_idx, sticky="nsew")

            # Sum cell
            sum_col_idx = 2 + len(self.timezones)
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
                anchor="center"
            ).grid(row=row_index, column=sum_col_idx, sticky="nsew")

            row_index += 1

        # 3) Heading row again at the bottom
        bottom_heading_row = row_index
        self._build_heading_row(row_index=bottom_heading_row)
        row_index += 1

        # 4) Summary row
        summary_row = row_index
        summary = self.parser.compute_summary()
        if summary:
            # col 0 => blank
            tk.Label(
                self.table_frame,
                text="",
                borderwidth=1,
                relief="solid",
                anchor="center"
            ).grid(row=summary_row, column=0, sticky="nsew")

            # col 1 => blank
            tk.Label(
                self.table_frame,
                text="",
                borderwidth=1,
                relief="solid",
                anchor="center"
            ).grid(row=summary_row, column=1, sticky="nsew")

            for c_idx, tz in enumerate(self.timezones, start=2):
                ok_c = summary[tz]["ok_count"]
                total = summary[tz]["total"]
                missing = total - ok_c
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
                    anchor="center"
                ).grid(row=summary_row, column=c_idx, sticky="nsew")

            # last column blank
            last_col = 2 + len(self.timezones)
            tk.Label(
                self.table_frame,
                text="",
                borderwidth=1,
                relief="solid",
                anchor="center"
            ).grid(row=summary_row, column=last_col, sticky="nsew")
            row_index += 1

        # Let columns expand equally
        total_cols = 2 + len(self.timezones) + 1
        for col_i in range(total_cols):
            self.table_frame.columnconfigure(col_i, weight=1)

        self.canvas.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def _build_heading_row(self, row_index):
        """
        Build the heading row at the given row_index:
          Subfolder | Diff | <timezones> | "Fail"
        """
        tk.Label(
            self.table_frame,
            text="Subfolder",
            borderwidth=1,
            relief="solid",
            anchor="center"
        ).grid(row=row_index, column=0, sticky="nsew")

        tk.Label(
            self.table_frame,
            text="Diff",
            borderwidth=1,
            relief="solid",
            anchor="center"
        ).grid(row=row_index, column=1, sticky="nsew")

        for i, tz in enumerate(self.timezones, start=2):
            tk.Label(
                self.table_frame,
                text=tz,
                borderwidth=1,
                relief="solid",
                anchor="center"
            ).grid(row=row_index, column=i, sticky="nsew")

        last_col = 2 + len(self.timezones)
        tk.Label(
            self.table_frame,
            text="Fail",  # was empty before, now user wants "Fail"
            borderwidth=1,
            relief="solid",
            anchor="center"
        ).grid(row=row_index, column=last_col, sticky="nsew")

    def _on_frame_configure(self, event):
        """
        Adjust canvas scroll region whenever the frame size changes.
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

        export_data = {
            "subfolders": [],
            "summary": {}
        }

        for subfolder_name, data in results.items():
            tz_bool_dict = data["tz_status"]
            tz_str_dict = {}
            for tz, val in tz_bool_dict.items():
                # Convert boolean to "ok"/"false" for export
                tz_str_dict[tz] = "ok" if val else "false"

            export_data["subfolders"].append({
                "name": subfolder_name,
                "results": tz_str_dict,
                "ok_count": data["ok_count"],
                "fail_count": data["fail_count"]
            })

        for tz, sdata in summary.items():
            export_data["summary"][tz] = {
                "ok_count": sdata["ok_count"],
                "total": sdata["total"]
            }

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON file", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                messagebox.showinfo(
                    "Export successful",
                    f"Data has been exported to:\n{file_path}"
                )
            except Exception as e:
                messagebox.showerror("Export error", str(e))


def main():
    """
    Launch the StatsApp and run the main event loop.
    """
    app = StatsApp()
    app.geometry("1200x600")
    app.mainloop()


if __name__ == "__main__":
    main()
