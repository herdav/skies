# stats.py

import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
import os
import re
import json

class StatsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Statistische Auswertung")
        
        # Liste aller relevanten Zeitzonen, von UTC-11 bis UTC+12
        self.timezones = self._get_timezones()
        
        # --- FRAME: OBERE BEDIENLEISTE ---
        top_frame = tk.Frame(self)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        # Button zum Ordner-Auswählen
        self.select_button = tk.Button(top_frame, text="Ordner auswählen", command=self.select_folder)
        self.select_button.pack(side=tk.LEFT, padx=5)
        
        # Button zum Export der Daten als JSON
        self.export_button = tk.Button(top_frame, text="Export (JSON)", command=self.export_results, state=tk.DISABLED)
        self.export_button.pack(side=tk.LEFT, padx=5)
        
        # Fortschrittsbalken
        self.progress_bar = ttk.Progressbar(top_frame, length=200, mode='determinate')
        self.progress_bar.pack(side=tk.RIGHT, padx=5)
        
        # --- CANVAS + SCROLLBAR für die Tabelle ---
        self.canvas_frame = tk.Frame(self)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.scrollbar = tk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Frame, in dem die Tabelle (Labels) gerendert wird
        self.table_frame = tk.Frame(self.canvas)
        
        # Ein "Fenster" im Canvas erstellen, das unser table_frame enthält
        self.canvas.create_window((0, 0), window=self.table_frame, anchor="nw")
        
        # Callback, wenn sich die Größe ändert => Scrollregion anpassen
        self.table_frame.bind("<Configure>", self.on_frame_configure)
        
        # Hier werden später die Ergebnisse zwischengespeichert
        self.stats = {}
        # Hier wollen wir auch eine Summary ablegen, damit wir es exportieren können
        self.summary_ok_counts = {}
    
    def _get_timezones(self):
        """Erstellt eine Liste aller Zeitzonen von UTC-11 bis UTC+12."""
        tz_list = []
        for i in range(-11, 13):
            if i >= 0:
                tz_list.append(f"UTC+{i}")
            else:
                tz_list.append(f"UTC{i}")
        return tz_list
    
    def select_folder(self):
        """Öffnet den Ordner-Auswahldialog, parst die Unterordner und baut die Ergebnis-Tabelle auf."""
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            # Leert vorherige Tabelle, falls vorhanden
            self.clear_table()
            
            # Ordner parsen
            self.stats = self.parse_subfolders(folder_selected)
            
            # Baue neue Tabelle
            self.build_table()
            
            # Export-Button aktivieren, wenn wir Daten haben
            if self.stats:
                self.export_button.config(state=tk.NORMAL)
    
    def parse_subfolders(self, folder):
        """
        Durchsucht alle Unterordner des gewählten Ordners.
        - Sucht pro Unterordner nach Dateien mit '_merge.png' und setzt Status auf 'ok'.
        - Liest ggf. *.txt-Dateien nach Zeilen mit 'Download failed for UTC-X => ...' und setzt Status auf 'false'.
        
        Speichert das Ergebnis in einem Dict:
            {
                subfolder_name: {tz: 'ok'/'false', ...}
            }
        """
        results = {}
        
        # Alle Einträge im ausgewählten Ordner (erstes Level)
        entries = [e for e in os.scandir(folder) if e.is_dir()]
        
        # Fortschrittsbalken konfigurieren
        total_subfolders = len(entries)
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = total_subfolders
        
        for i, entry in enumerate(entries, start=1):
            subfolder_name = entry.name
            subfolder_path = entry.path
            
            # Standardmäßig alles auf "false" setzen
            tz_status = {tz: "false" for tz in self.timezones}
            
            # 1. Suche nach *_merge.png => status="ok"
            for file in os.scandir(subfolder_path):
                if file.is_file():
                    filename = file.name
                    if filename.endswith("_merge.png"):
                        # Beispiel: UTC-4_20250122_081806_merge.png
                        match = re.match(r"(UTC[+\-]\d+)_.*_merge\.png", filename)
                        if match:
                            tz_found = match.group(1)
                            if tz_found in tz_status:
                                tz_status[tz_found] = "ok"
            
            # 2. Prüfe *.txt-Dateien auf "Download failed..."
            for file in os.scandir(subfolder_path):
                if file.is_file() and file.name.endswith(".txt"):
                    with open(file.path, "r", encoding="utf-8") as txt_file:
                        for line in txt_file:
                            # Beispiel: "Download failed for UTC-4 => UTC-4_20250122_081806.jpg"
                            match_fail = re.search(r"Download failed for (UTC[+\-]\d+)\s*=>", line)
                            if match_fail:
                                tz_failed = match_fail.group(1)
                                if tz_failed in tz_status:
                                    tz_status[tz_failed] = "false"
            
            results[subfolder_name] = tz_status
            
            # Fortschrittsbalken updaten
            self.progress_bar['value'] = i
            self.update_idletasks()
        
        return results
    
    def build_table(self):
        """Erzeugt eine Tabelle (Labels in Grid) zur Anzeige der Auswertungen."""
        # Alte Widgets in table_frame entfernen
        self.clear_table()
        
        # Kopfzeile (erste Zeile mit Spaltenüberschriften)
        # Spalte 0: "Unterordner"
        tk.Label(self.table_frame, text="Unterordner", borderwidth=1, relief="solid").grid(row=0, column=0, sticky="nsew")
        
        # Spalten 1..N: Zeit-Zonen
        for col, tz in enumerate(self.timezones, start=1):
            tk.Label(self.table_frame, text=tz, borderwidth=1, relief="solid").grid(row=0, column=col, sticky="nsew")
        
        # Zusätzliche Spalte: Summe (OK/False)
        sum_col = len(self.timezones) + 1
        tk.Label(self.table_frame, text="Sum (OK/Fail)", borderwidth=1, relief="solid").grid(row=0, column=sum_col, sticky="nsew")
        
        # Zusammenfassungszählung initialisieren
        self.summary_ok_counts = {tz: 0 for tz in self.timezones}
        
        # Pro Unterordner eine Zeile
        subfolders = sorted(self.stats.keys())
        for row, subfolder_name in enumerate(subfolders, start=1):
            tz_status = self.stats[subfolder_name]
            
            # Spalte 0: Name des Unterordners
            tk.Label(self.table_frame, text=subfolder_name, borderwidth=1, relief="solid").grid(row=row, column=0, sticky="nsew")
            
            # Zählen, wie viele "ok" und wie viele "false"
            ok_count = 0
            fail_count = 0
            
            for col, tz in enumerate(self.timezones, start=1):
                status = tz_status[tz]
                if status == "ok":
                    ok_count += 1
                    bg_color = "green"
                    label_text = "ok"
                    self.summary_ok_counts[tz] += 1
                else:
                    fail_count += 1
                    bg_color = "red"
                    label_text = "false"
                
                lbl = tk.Label(self.table_frame, text=label_text, bg=bg_color, borderwidth=1, relief="solid")
                lbl.grid(row=row, column=col, sticky="nsew")
            
            # Spalte: Summe (OK/Fail)
            sum_label = f"{ok_count}/{fail_count}"
            tk.Label(self.table_frame, text=sum_label, borderwidth=1, relief="solid").grid(row=row, column=sum_col, sticky="nsew")
        
        # Letzte Zeile: Zusammenfassungszeile
        final_row = len(subfolders) + 1
        tk.Label(self.table_frame, text="Ergebnis", borderwidth=1, relief="solid").grid(row=final_row, column=0, sticky="nsew")
        
        # Spalten 1..N: summary
        total_subfolders = len(subfolders)
        for col, tz in enumerate(self.timezones, start=1):
            ok_count = self.summary_ok_counts[tz]
            result_text = f"{ok_count}/{total_subfolders}"
            tk.Label(self.table_frame, text=result_text, borderwidth=1, relief="solid").grid(row=final_row, column=col, sticky="nsew")
        
        # Spalte "Sum (OK/Fail)" -> hier vielleicht leer lassen oder ein Fazit
        tk.Label(self.table_frame, text="", borderwidth=1, relief="solid").grid(row=final_row, column=sum_col, sticky="nsew")
        
        # Scrollregion anpassen
        self.canvas.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))
    
    def clear_table(self):
        """Entfernt alle vorhandenen Widgets in der Tabelle."""
        for widget in self.table_frame.winfo_children():
            widget.destroy()
    
    def on_frame_configure(self, event):
        """
        Wird aufgerufen, wenn sich die Größe des table_frame ändert.
        Passt die Scrollregion des Canvas entsprechend an.
        """
        self.canvas.config(scrollregion=self.canvas.bbox("all"))
    
    def export_results(self):
        """
        Exportiert die Ergebnisse (self.stats) zusammen mit einer Summen-Zeile in eine JSON-Datei.
        """
        if not self.stats:
            return
        
        export_data = {
            "subfolders": [],
            "summary": {}
        }
        
        # subfolders: Liste von { name: <>, results: {...}, ok_count: n, fail_count: n }
        for subfolder_name, tz_dict in self.stats.items():
            # Zähle ok/fail
            ok_count = sum(1 for v in tz_dict.values() if v == "ok")
            fail_count = sum(1 for v in tz_dict.values() if v == "false")
            
            subfolder_entry = {
                "name": subfolder_name,
                "results": tz_dict,  # z.B. {"UTC-11": "ok"/"false", ...}
                "ok_count": ok_count,
                "fail_count": fail_count
            }
            export_data["subfolders"].append(subfolder_entry)
        
        # summary: pro Zeitzone: wie viele ok / total
        total_subfolders = len(self.stats)
        summary_dict = {}
        for tz in self.timezones:
            ok_count = self.summary_ok_counts.get(tz, 0)
            summary_dict[tz] = {
                "ok_count": ok_count,
                "total": total_subfolders
            }
        export_data["summary"] = summary_dict
        
        # Pfaddialog
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON-Datei", "*.json"), ("Alle Dateien", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                # Optional: Erfolgsmeldung
                tk.messagebox.showinfo("Export erfolgreich", f"Daten wurden exportiert nach:\n{file_path}")
            except Exception as e:
                tk.messagebox.showerror("Fehler beim Export", str(e))

def main():
    app = StatsApp()
    # Fenster vergrößerbar machen (für Scrollbar hilfreich)
    app.geometry("1200x600")
    app.mainloop()

if __name__ == "__main__":
    main()
