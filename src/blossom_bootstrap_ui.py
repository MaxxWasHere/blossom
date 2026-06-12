"""Bootstrap splash window — Blossom pink-aurora aesthetic (tkinter)."""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from typing import Callable

# Blossom palette (matches assets/blossom-loading.css)
_BG_ROOT = "#0a0809"
_BG_CARD = "#161014"
_BORDER = "#3a2a32"
_ACCENT = "#e891a8"
_ACCENT_TEXT = "#f5c6d4"
_TEXT_PRIMARY = "#ece8ea"
_TEXT_SECONDARY = "#a8a0a4"
_TEXT_MUTED = "#6e6468"
_ERROR = "#f0a0a8"
_PROGRESS_TRACK = "#1a1216"
_AURORA_1 = "#e87cc0"
_AURORA_2 = "#c46d88"
# rgba(255,255,255,0.08) composited on _BG_CARD — tkinter has no alpha hex
_SPINNER_TRACK = "#292329"

_WINDOW_W = 440
_WINDOW_H = 400
_CLOSE_DELAY_MS = 480


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return Path(__file__).resolve().parent.parent


def _icon_path() -> Path | None:
    root = _bundle_root()
    for rel in ("icon.ico", "assets/blossom.png", "assets/icon.ico", "blossom.png"):
        path = root / rel
        if path.is_file():
            return path
    return None


def _logo_path() -> Path | None:
    root = _bundle_root()
    for rel in ("assets/blossom.png", "blossom.png"):
        path = root / rel
        if path.is_file():
            return path
    return None


def _format_bytes(value: int) -> str:
    n = max(0, int(value))
    if n <= 0:
        return "0 MB"
    mb = n / (1024 * 1024)
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    if mb >= 10:
        return f"{mb:.0f} MB"
    return f"{mb:.1f} MB"


class BootstrapUI:
    """Thread-safe tkinter splash with progress and error display."""

    def __init__(self, *, channel: str, version: str = "") -> None:
        self._channel = channel
        self._version = version
        self._queue: queue.Queue[tuple[str, tuple]] = queue.Queue()
        self._closed = threading.Event()
        self._root: tk.Tk | None = None
        self._message_var: tk.StringVar | None = None
        self._pct_var: tk.StringVar | None = None
        self._bytes_var: tk.StringVar | None = None
        self._version_var: tk.StringVar | None = None
        self._error_var: tk.StringVar | None = None
        self._error_frame: tk.Frame | None = None
        self._progress_fill: tk.Canvas | None = None
        self._progress_track_id: int | None = None
        self._progress_fill_id: int | None = None
        self._spinner_angle = 0
        self._spinner_canvas: tk.Canvas | None = None
        self._spinner_visible = True
        self._show_progress = False
        self._progress_pct = 0.0
        self._target_pct = 0.0
        self._indeterminate = True
        self._indeterminate_pos = 0.0
        self._indeterminate_dir = 1
        self._close_scheduled = False

    def _run_on_main(self, fn: Callable[..., None], *args) -> None:
        self._queue.put(("call", (fn, args)))

    def set_message(self, message: str) -> None:
        self._run_on_main(self._set_message_impl, message)

    def set_version(self, version: str) -> None:
        self._version = version
        self._run_on_main(self._set_version_impl, version)

    def set_progress(self, downloaded: int, total: int) -> None:
        self._run_on_main(self._set_progress_impl, downloaded, total)

    def set_indeterminate(self, active: bool = True) -> None:
        self._run_on_main(self._set_indeterminate_impl, active)

    def show_error(self, message: str) -> None:
        self._run_on_main(self._show_error_impl, message)

    def close(self) -> None:
        self._run_on_main(self._close_impl)

    def schedule_close(self, delay_ms: int = _CLOSE_DELAY_MS) -> None:
        self._run_on_main(self._schedule_close_impl, delay_ms)

    def _set_message_impl(self, message: str) -> None:
        if self._message_var is not None:
            self._message_var.set(message)
        if self._error_var is not None and self._error_frame is not None:
            self._error_var.set("")
            self._error_frame.pack_forget()

    def _set_version_impl(self, version: str) -> None:
        if self._version_var is not None:
            label = version.strip()
            if label:
                self._version_var.set(label.upper())

    def _progress_track_width(self) -> int:
        if self._progress_fill is None or self._progress_track_id is None:
            return 380
        bbox = self._progress_fill.bbox(self._progress_track_id)
        if not bbox:
            return 380
        return max(1, bbox[2] - bbox[0])

    def _apply_progress_fill(self, pct: float) -> None:
        if self._progress_fill is None or self._progress_fill_id is None:
            return
        track_w = self._progress_track_width()
        width = max(0, int(track_w * (pct / 100.0)))
        self._progress_fill.coords(self._progress_fill_id, 0, 0, width, 10)

    def _set_spinner_visible(self, visible: bool) -> None:
        self._spinner_visible = visible
        if self._spinner_canvas is None:
            return
        if visible:
            self._spinner_canvas.pack(pady=(0, 14))
        else:
            self._spinner_canvas.pack_forget()

    def _set_progress_impl(self, downloaded: int, total: int) -> None:
        self._show_progress = True
        self._indeterminate = False
        self._set_spinner_visible(False)
        if total > 0:
            pct = min(100.0, max(0.0, (downloaded / total) * 100.0))
            self._target_pct = pct
            if self._pct_var is not None:
                self._pct_var.set(f"{pct:.0f}%")
            if self._bytes_var is not None:
                self._bytes_var.set(f"{_format_bytes(downloaded)} / {_format_bytes(total)}")
        else:
            if self._pct_var is not None:
                self._pct_var.set("Downloading…")
            if self._bytes_var is not None:
                self._bytes_var.set(_format_bytes(downloaded))

    def _set_indeterminate_impl(self, active: bool) -> None:
        self._indeterminate = active
        self._show_progress = active
        self._set_spinner_visible(not active)
        if active:
            self._target_pct = 0.0
            self._progress_pct = 0.0
            if self._pct_var is not None:
                self._pct_var.set("Starting…")
            if self._bytes_var is not None:
                self._bytes_var.set("")

    def _show_error_impl(self, message: str) -> None:
        if self._root is None:
            return
        self._set_message_impl("Something went wrong")
        if self._error_var is not None and self._error_frame is not None:
            self._error_var.set(message)
            self._error_frame.pack(fill=tk.X, pady=(0, 10), before=self._spinner_canvas)
        self._set_indeterminate_impl(True)

    def _schedule_close_impl(self, delay_ms: int) -> None:
        if self._close_scheduled or self._closed.is_set() or self._root is None:
            return
        self._close_scheduled = True
        self._root.after(max(0, delay_ms), self._close_impl)

    def _close_impl(self) -> None:
        if self._root is not None:
            try:
                self._root.quit()
                self._root.destroy()
            except tk.TclError:
                pass
        self._closed.set()

    def _pump_queue(self) -> None:
        if self._root is None:
            return
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "call":
                    fn, args = payload
                    fn(*args)
        except queue.Empty:
            pass
        if not self._closed.is_set():
            self._root.after(40, self._pump_queue)

    def _animate_spinner(self) -> None:
        if self._closed.is_set() or self._spinner_canvas is None or not self._spinner_visible:
            if not self._closed.is_set() and self._root is not None:
                self._root.after(70, self._animate_spinner)
            return
        self._spinner_angle = (self._spinner_angle + 28) % 360
        self._spinner_canvas.delete("spinner")
        cx, cy, r = 21, 21, 16
        self._spinner_canvas.create_arc(
            cx - r,
            cy - r,
            cx + r,
            cy + r,
            start=self._spinner_angle,
            extent=100,
            style=tk.ARC,
            outline=_ACCENT,
            width=3,
            tags="spinner",
        )
        self._spinner_canvas.create_oval(
            cx - r,
            cy - r,
            cx + r,
            cy + r,
            outline=_SPINNER_TRACK,
            width=3,
            tags="spinner",
        )
        self._root.after(70, self._animate_spinner)

    def _animate_progress(self) -> None:
        if self._closed.is_set() or self._root is None:
            return
        if self._indeterminate:
            track_w = self._progress_track_width()
            sweep = max(40, int(track_w * 0.38))
            self._indeterminate_pos += 0.035 * self._indeterminate_dir
            if self._indeterminate_pos >= 1.0:
                self._indeterminate_pos = 1.0
                self._indeterminate_dir = -1
            elif self._indeterminate_pos <= 0.0:
                self._indeterminate_pos = 0.0
                self._indeterminate_dir = 1
            x0 = int((track_w + sweep) * self._indeterminate_pos) - sweep
            x1 = x0 + sweep
            if self._progress_fill is not None and self._progress_fill_id is not None:
                self._progress_fill.coords(self._progress_fill_id, x0, 0, x1, 10)
        elif abs(self._progress_pct - self._target_pct) > 0.4:
            self._progress_pct += (self._target_pct - self._progress_pct) * 0.35
            self._apply_progress_fill(self._progress_pct)
        elif self._progress_pct != self._target_pct:
            self._progress_pct = self._target_pct
            self._apply_progress_fill(self._progress_pct)
        self._root.after(50, self._animate_progress)

    def _draw_aurora(self, canvas: tk.Canvas) -> None:
        w = _WINDOW_W
        h = _WINDOW_H
        canvas.create_oval(-80, -90, 260, 290, fill=_AURORA_1, outline="", stipple="gray25", tags="aurora")
        canvas.create_oval(w - 220, h - 240, w + 60, h + 40, fill=_AURORA_2, outline="", stipple="gray25", tags="aurora")
        canvas.tag_lower("aurora")

    def _on_progress_resize(self, _event: tk.Event) -> None:
        if self._progress_fill is None or self._progress_track_id is None:
            return
        width = max(1, self._progress_fill.winfo_width())
        self._progress_fill.coords(self._progress_track_id, 0, 0, width, 10)
        if self._indeterminate:
            return
        self._apply_progress_fill(self._progress_pct)

    def _build_window(self) -> None:
        root = tk.Tk()
        self._root = root
        root.title("Blossom")
        root.configure(bg=_BG_ROOT)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self._close_impl)

        icon = _icon_path()
        if icon is not None:
            try:
                if icon.suffix.lower() == ".ico":
                    root.iconbitmap(default=str(icon))
                else:
                    img = tk.PhotoImage(file=str(icon))
                    root.iconphoto(True, img)
                    root._icon_ref = img  # type: ignore[attr-defined]
            except tk.TclError:
                pass

        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = max(0, (sw - _WINDOW_W) // 2)
        y = max(0, (sh - _WINDOW_H) // 2)
        root.geometry(f"{_WINDOW_W}x{_WINDOW_H}+{x}+{y}")

        bg = tk.Canvas(root, width=_WINDOW_W, height=_WINDOW_H, bg=_BG_ROOT, highlightthickness=0)
        bg.pack(fill=tk.BOTH, expand=True)
        self._draw_aurora(bg)

        outer = tk.Frame(bg, bg=_BG_ROOT)
        bg.create_window(_WINDOW_W // 2, _WINDOW_H // 2, window=outer, width=_WINDOW_W - 56, height=_WINDOW_H - 56)

        card = tk.Frame(
            outer,
            bg=_BG_CARD,
            highlightbackground=_BORDER,
            highlightthickness=1,
            padx=30,
            pady=26,
        )
        card.pack(fill=tk.BOTH, expand=True)

        logo = _logo_path()
        if logo is not None:
            try:
                logo_img = tk.PhotoImage(file=str(logo))
                if logo_img.width() > 72:
                    factor = max(1, logo_img.width() // 72)
                    logo_img = logo_img.subsample(factor, factor)
                tk.Label(card, image=logo_img, bg=_BG_CARD).pack(pady=(0, 10))
                card._logo_ref = logo_img  # type: ignore[attr-defined]
            except tk.TclError:
                pass

        brand = "Blossom"
        if self._channel == "beta":
            brand = "Blossom Beta"

        tk.Label(
            card,
            text=brand,
            font=("Segoe UI", 18, "bold"),
            fg=_ACCENT_TEXT,
            bg=_BG_CARD,
        ).pack()

        self._message_var = tk.StringVar(value="Starting Blossom…")
        tk.Label(
            card,
            textvariable=self._message_var,
            font=("Segoe UI", 10),
            fg=_TEXT_SECONDARY,
            bg=_BG_CARD,
            wraplength=340,
            justify=tk.CENTER,
        ).pack(pady=(8, 12))

        self._error_var = tk.StringVar(value="")
        self._error_frame = tk.Frame(card, bg=_BG_CARD)
        tk.Label(
            self._error_frame,
            textvariable=self._error_var,
            font=("Segoe UI", 9),
            fg=_ERROR,
            bg=_BG_CARD,
            wraplength=340,
            justify=tk.CENTER,
        ).pack()

        self._spinner_canvas = tk.Canvas(
            card, width=42, height=42, bg=_BG_CARD, highlightthickness=0
        )
        self._spinner_canvas.pack(pady=(0, 14))

        progress_frame = tk.Frame(card, bg=_BG_CARD)
        progress_frame.pack(fill=tk.X, pady=(0, 8))

        self._progress_fill = tk.Canvas(
            progress_frame,
            height=10,
            bg=_PROGRESS_TRACK,
            highlightthickness=1,
            highlightbackground=_BORDER,
        )
        self._progress_fill.pack(fill=tk.X)
        self._progress_fill.bind("<Configure>", self._on_progress_resize)
        self._progress_track_id = self._progress_fill.create_rectangle(
            0, 0, 380, 10, fill=_PROGRESS_TRACK, outline=""
        )
        self._progress_fill_id = self._progress_fill.create_rectangle(
            0, 0, 0, 10, fill=_ACCENT, outline=""
        )

        meta = tk.Frame(progress_frame, bg=_BG_CARD)
        meta.pack(fill=tk.X, pady=(8, 0))
        self._pct_var = tk.StringVar(value="Starting…")
        self._bytes_var = tk.StringVar(value="")
        tk.Label(
            meta,
            textvariable=self._pct_var,
            font=("Segoe UI", 9, "bold"),
            fg=_ACCENT_TEXT,
            bg=_BG_CARD,
            anchor=tk.W,
        ).pack(side=tk.LEFT)
        tk.Label(
            meta,
            textvariable=self._bytes_var,
            font=("Segoe UI", 9),
            fg=_TEXT_SECONDARY,
            bg=_BG_CARD,
            anchor=tk.E,
        ).pack(side=tk.RIGHT)

        self._version_var = tk.StringVar(value=self._version.upper() if self._version else "")
        tk.Label(
            card,
            textvariable=self._version_var,
            font=("Segoe UI", 8),
            fg=_TEXT_MUTED,
            bg=_BG_CARD,
        ).pack(pady=(12, 0))

        self._animate_spinner()
        self._animate_progress()
        self._pump_queue()
        if self._version:
            self._set_version_impl(self._version)

    def run(self, worker: Callable[["BootstrapUI"], int]) -> int:
        """Show splash, run worker on a background thread, return its exit code."""
        result: list[int] = [1]

        def _worker_wrapper() -> None:
            try:
                result[0] = worker(self)
            except Exception as error:  # noqa: BLE001
                self.show_error(str(error))
                result[0] = 1
            finally:
                if result[0] == 0:
                    self.schedule_close()

        self._build_window()
        assert self._root is not None
        thread = threading.Thread(target=_worker_wrapper, name="BlossomBootstrap", daemon=True)
        thread.start()
        self._root.mainloop()
        thread.join(timeout=2.0)
        return result[0]
