# src/gui/tooltip.py
"""Tooltip module for the GUI."""

import tkinter as tk


class Tooltip:
    """Simple tooltip for UI elements."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.enter)
        widget.bind("<Leave>", self.leave)

    def enter(self, event):
        """Show the tooltip when the mouse enters the widget."""
        x = event.x_root + 20
        y = event.y_root
        self.tip = tw = tk.Toplevel(self.widget)
        tw.overrideredirect(True)
        lbl = tk.Label(tw, text=self.text, bg="#ffffe0", relief="solid", bd=1)
        lbl.pack()
        tw.geometry(f"+{x}+{y}")

    def leave(self, _):
        """Destroy the tooltip when the mouse leaves the widget."""
        if self.tip:
            if self.tip and self.tip.winfo_exists():
                self.tip.destroy()
            self.tip = None
