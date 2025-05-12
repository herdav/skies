# src/main.py
"""Main entry point for the webcam application."""

from tkinter import Tk

from controller import WebcamController
from gui.window import WebcamWindow


def main() -> None:
    root = Tk()
    controller = WebcamController()
    app = WebcamWindow(root, controller)
    controller.attach_view(app)
    root.mainloop()


if __name__ == "__main__":
    main()
