"""Fullscreen drag selector for calibrating on-screen button regions."""

from __future__ import annotations

import tkinter as tk


def capture_region_drag() -> list[int] | None:
    """Block until the user drags a rectangle or presses Escape.

    Returns [left, top, width, height] in screen coordinates, or None if cancelled.
    """

    result: list[int] | None = None
    start_screen: tuple[int, int] | None = None
    start_canvas: tuple[int, int] | None = None
    rect_id: int | None = None

    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    root.geometry(f"{screen_w}x{screen_h}+0+0")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.28)
    root.configure(cursor="crosshair", bg="#000000")

    canvas = tk.Canvas(root, highlightthickness=0, bg="#000000", cursor="crosshair")
    canvas.pack(fill=tk.BOTH, expand=True)

    hint = tk.Label(
        root,
        text="Drag over the button to mark it  •  ESC to cancel",
        font=("Segoe UI", 12, "bold"),
        fg="#ffffff",
        bg="#111827",
        padx=14,
        pady=8,
    )
    hint.place(relx=0.5, y=18, anchor="n")

    def normalize_box(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
        left = max(0, min(x0, x1))
        top = max(0, min(y0, y1))
        right = min(screen_w, max(x0, x1))
        bottom = min(screen_h, max(y0, y1))
        width = max(1, right - left)
        height = max(1, bottom - top)
        return left, top, width, height

    def on_press(event: tk.Event) -> None:
        nonlocal start_screen, start_canvas, rect_id
        start_screen = (int(event.x_root), int(event.y_root))
        start_canvas = (int(event.x), int(event.y))
        if rect_id is not None:
            canvas.delete(rect_id)
        rect_id = canvas.create_rectangle(
            start_canvas[0],
            start_canvas[1],
            start_canvas[0],
            start_canvas[1],
            outline="#38bdf8",
            width=2,
            fill="#0ea5e9",
            stipple="gray50",
        )

    def on_drag(event: tk.Event) -> None:
        nonlocal rect_id
        if start_canvas is None or rect_id is None:
            return
        canvas.coords(rect_id, start_canvas[0], start_canvas[1], int(event.x), int(event.y))

    def on_release(event: tk.Event) -> None:
        nonlocal result
        if start_screen is None:
            return
        result = list(
            normalize_box(
                start_screen[0],
                start_screen[1],
                int(event.x_root),
                int(event.y_root),
            )
        )
        root.quit()

    def on_cancel(_event: tk.Event | None = None) -> None:
        nonlocal result
        result = None
        root.quit()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_cancel)

    root.deiconify()
    root.lift()
    root.focus_force()
    root.mainloop()
    try:
        root.destroy()
    except tk.TclError:
        pass
    return result
