"""Bootstrap splash — lightweight tkinter with custom titlebar."""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from typing import Callable

_WINDOW_W = 400
_WINDOW_H = 300
_TITLEBAR_H = 32
_CLOSE_DELAY_MS = 480
_FADE_STEPS = 12

# Pink theme — solid 6-digit hex only (tkinter requirement).
_BG_ROOT = "#0a0809"
_BG_CARD = "#161014"
_BG_TRACK = "#241a1e"
_ACCENT = "#e891a8"
_ACCENT_DIM = "#c46d88"
_TEXT = "#ece8ea"
_TEXT_MUTED = "#6e6468"
_BORDER = "#241a1e"
_DANGER = "#ef4444"
_BTN_HOVER = "#1c1519"
_CLOSE_HOVER = "#3a1820"


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return Path(__file__).resolve().parent.parent


def _logo_path() -> Path | None:
    for name in ("assets/blossom.png", "blossom.png"):
        path = _bundle_root() / name
        if path.is_file():
            return path
    return None


def _fmt_bytes(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{int(value)} B"


class BootstrapUI:
    """Thread-safe tkinter splash with a custom titlebar."""

    def __init__(self, *, channel: str, version: str = "") -> None:
        self._channel = channel
        self._version = version
        self._queue: queue.Queue[tuple[str, tuple]] = queue.Queue()
        self._closed = threading.Event()
        self._close_scheduled = False
        self._root: tk.Tk | None = None
        self._result: list[int] = [1]
        self._worker: Callable[[BootstrapUI], int] | None = None

        self._indeterminate = True
        self._progress = 0.0
        self._bytes_text = ""
        self._anim_phase = 0.0
        self._anim_job: str | None = None
        self._fade_job: str | None = None
        self._drag_x = 0
        self._drag_y = 0
        self._logo_image: tk.PhotoImage | None = None
        self._message_var: tk.StringVar | None = None
        self._version_var: tk.StringVar | None = None
        self._error_var: tk.StringVar | None = None

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

    def set_phase(self, phase: str) -> None:
        pass

    def show_error(self, message: str) -> None:
        self._run_on_main(self._show_error_impl, message)

    def close(self) -> None:
        self._run_on_main(self._close_impl)

    def schedule_close(self, delay_ms: int = _CLOSE_DELAY_MS) -> None:
        self._run_on_main(self._schedule_close_impl, delay_ms)

    def _brand_title(self) -> str:
        return "Blossom Beta" if self._channel == "beta" else "Blossom"

    def _init_tk_vars(self) -> None:
        root = self._root
        assert root is not None
        self._message_var = tk.StringVar(master=root, value="Starting Blossom…")
        self._version_var = tk.StringVar(master=root, value="")
        self._error_var = tk.StringVar(master=root, value="")

    def _set_message_impl(self, message: str) -> None:
        if self._message_var is None or self._error_var is None:
            return
        self._message_var.set(message.strip() or "…")
        self._error_var.set("")

    def _set_version_impl(self, version: str) -> None:
        if self._version_var is None:
            return
        text = version.strip()
        self._version_var.set(f"v{text}" if text else "")

    def _set_progress_impl(self, downloaded: int, total: int) -> None:
        if total > 0:
            self._indeterminate = False
            self._progress = max(0.0, min(1.0, downloaded / total))
            self._bytes_text = f"{_fmt_bytes(downloaded)} / {_fmt_bytes(total)}"
        else:
            self._indeterminate = True
            self._bytes_text = _fmt_bytes(downloaded) if downloaded else ""
        self._redraw_progress()

    def _set_indeterminate_impl(self, active: bool) -> None:
        self._indeterminate = bool(active)
        if self._indeterminate:
            self._progress = 0.0
            self._bytes_text = ""
        self._redraw_progress()

    def _show_error_impl(self, message: str) -> None:
        if self._message_var is None or self._error_var is None:
            return
        self._indeterminate = False
        self._error_var.set(message.strip())
        self._message_var.set("Something went wrong")
        self._redraw_progress()

    def _schedule_close_impl(self, delay_ms: int) -> None:
        if self._close_scheduled or self._closed.is_set():
            return
        self._close_scheduled = True
        self._indeterminate = False
        self._progress = 1.0
        self._bytes_text = ""
        if self._message_var is not None:
            self._message_var.set("Blossom is ready")
        if self._error_var is not None:
            self._error_var.set("")
        self._redraw_progress()
        delay = max(0.05, delay_ms / 1000.0)
        root = self._root
        if root is not None:
            root.after(int(delay * 1000), self._fade_out_and_close)

    def _fade_out_and_close(self) -> None:
        root = self._root
        if root is None or self._closed.is_set():
            return

        step = [0]

        def _tick() -> None:
            if root is None or self._closed.is_set():
                return
            step[0] += 1
            alpha = max(0.0, 1.0 - step[0] / _FADE_STEPS)
            try:
                root.wm_attributes("-alpha", alpha)
            except tk.TclError:
                self._close_impl()
                return
            if step[0] >= _FADE_STEPS:
                self._close_impl()
            else:
                self._fade_job = root.after(28, _tick)

        _tick()

    def _close_impl(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        if self._anim_job and self._root is not None:
            try:
                self._root.after_cancel(self._anim_job)
            except tk.TclError:
                pass
        if self._fade_job and self._root is not None:
            try:
                self._root.after_cancel(self._fade_job)
            except tk.TclError:
                pass
        root = self._root
        if root is not None:
            try:
                root.quit()
                root.destroy()
            except tk.TclError:
                pass

    def _poll_queue(self) -> None:
        root = self._root
        if root is None or self._closed.is_set():
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
            root.after(16, self._poll_queue)

    def _bind_drag(self, widget: tk.Widget) -> None:
        widget.bind("<ButtonPress-1>", self._start_drag, add="+")
        widget.bind("<B1-Motion>", self._on_drag, add="+")

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event: tk.Event) -> None:
        root = self._root
        if root is None:
            return
        x = root.winfo_x() + event.x - self._drag_x
        y = root.winfo_y() + event.y - self._drag_y
        root.geometry(f"+{x}+{y}")

    def _titlebar_button(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable[[], None],
        *,
        hover: str = _BTN_HOVER,
    ) -> tk.Label:
        btn = tk.Label(
            parent,
            text=text,
            width=3,
            font=("Segoe UI", 11),
            fg=_TEXT_MUTED,
            bg=_BG_CARD,
            cursor="hand2",
        )
        btn.bind("<Button-1>", lambda _e: command())
        btn.bind("<Enter>", lambda _e: btn.configure(bg=hover, fg=_TEXT))
        btn.bind("<Leave>", lambda _e: btn.configure(bg=_BG_CARD, fg=_TEXT_MUTED))
        return btn

    def _redraw_progress(self) -> None:
        canvas = getattr(self, "_progress_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 2)
        height = max(canvas.winfo_height(), 2)
        pad = 1
        track_y1 = pad
        track_y2 = height - pad
        canvas.create_rectangle(
            0, track_y1, width, track_y2, fill=_BG_TRACK, outline=_BORDER, width=0
        )

        if self._error_var is not None and self._error_var.get():
            return

        if self._indeterminate:
            span = max(36, int(width * 0.28))
            offset = int((width + span) * self._anim_phase) - span
            x1 = max(0, offset)
            x2 = min(width, offset + span)
            if x2 > x1:
                canvas.create_rectangle(x1, track_y1, x2, track_y2, fill=_ACCENT, outline="")
            if self._anim_job is None and not self._close_scheduled:
                self._schedule_anim()
        else:
            fill_w = max(0, int(width * self._progress))
            if fill_w > 0:
                canvas.create_rectangle(
                    0, track_y1, fill_w, track_y2, fill=_ACCENT, outline=""
                )

        meta = getattr(self, "_progress_meta", None)
        if meta is not None:
            if self._indeterminate and not self._bytes_text:
                meta.configure(text="")
            elif self._bytes_text:
                pct = int(self._progress * 100) if not self._indeterminate else 0
                prefix = f"{pct}%" if not self._indeterminate and self._progress > 0 else ""
                meta.configure(
                    text=f"{prefix}  {self._bytes_text}".strip() if prefix else self._bytes_text
                )
            else:
                meta.configure(text="")

    def _schedule_anim(self) -> None:
        root = self._root
        if root is None or self._closed.is_set() or not self._indeterminate:
            return

        def _tick() -> None:
            if self._closed.is_set() or not self._indeterminate:
                self._anim_job = None
                return
            self._anim_phase = (self._anim_phase + 0.04) % 1.0
            self._redraw_progress()
            self._anim_job = root.after(40, _tick)

        self._anim_job = root.after(40, _tick)

    def _build_ui(self) -> None:
        root = self._root
        assert root is not None

        root.title(self._brand_title())
        root.overrideredirect(True)
        root.configure(bg=_BG_ROOT)
        root.geometry(f"{_WINDOW_W}x{_WINDOW_H}")
        try:
            root.wm_attributes("-alpha", 1.0)
        except tk.TclError:
            pass

        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = max(0, (sw - _WINDOW_W) // 2)
        y = max(0, (sh - _WINDOW_H) // 2)
        root.geometry(f"{_WINDOW_W}x{_WINDOW_H}+{x}+{y}")

        shell = tk.Frame(root, bg=_BORDER, padx=1, pady=1)
        shell.pack(fill="both", expand=True)

        body = tk.Frame(shell, bg=_BG_ROOT)
        body.pack(fill="both", expand=True)

        titlebar = tk.Frame(body, bg=_BG_CARD, height=_TITLEBAR_H)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        self._bind_drag(titlebar)

        brand = tk.Frame(titlebar, bg=_BG_CARD)
        brand.pack(side="left", padx=(10, 0))
        self._bind_drag(brand)

        logo_path = _logo_path()
        if logo_path is not None:
            try:
                self._logo_image = tk.PhotoImage(file=str(logo_path))
                small = self._logo_image.subsample(max(1, self._logo_image.width() // 16), max(1, self._logo_image.height() // 16))
                icon = tk.Label(brand, image=small, bg=_BG_CARD)
                icon.image = small
                icon.pack(side="left", padx=(0, 6))
                self._bind_drag(icon)
            except tk.TclError:
                pass

        title_font = tkfont.Font(family="Segoe UI", size=9)
        title = tk.Label(
            brand,
            text=self._brand_title(),
            font=title_font,
            fg=_TEXT,
            bg=_BG_CARD,
        )
        title.pack(side="left")
        self._bind_drag(title)

        controls = tk.Frame(titlebar, bg=_BG_CARD)
        controls.pack(side="right")

        min_btn = self._titlebar_button(controls, "−", self._minimize_impl)
        min_btn.pack(side="left")
        close_btn = self._titlebar_button(
            controls, "×", self._close_impl, hover=_CLOSE_HOVER
        )
        close_btn.pack(side="left")
        close_btn.bind("<Enter>", lambda _e: close_btn.configure(fg=_DANGER))
        close_btn.bind("<Leave>", lambda _e: close_btn.configure(fg=_TEXT_MUTED))

        content = tk.Frame(body, bg=_BG_ROOT, padx=28, pady=18)
        content.pack(fill="both", expand=True)

        if logo_path is not None and self._logo_image is not None:
            try:
                big = self._logo_image.subsample(
                    max(1, self._logo_image.width() // 72),
                    max(1, self._logo_image.height() // 72),
                )
                logo = tk.Label(content, image=big, bg=_BG_ROOT)
                logo.image = big
                logo.pack(pady=(4, 10))
            except tk.TclError:
                pass

        msg_font = tkfont.Font(family="Segoe UI", size=10)
        tk.Label(
            content,
            textvariable=self._message_var,
            font=msg_font,
            fg=_TEXT,
            bg=_BG_ROOT,
            wraplength=_WINDOW_W - 56,
            justify="center",
        ).pack(pady=(0, 6))

        err_font = tkfont.Font(family="Segoe UI", size=9)
        tk.Label(
            content,
            textvariable=self._error_var,
            font=err_font,
            fg=_DANGER,
            bg=_BG_ROOT,
            wraplength=_WINDOW_W - 56,
            justify="center",
        ).pack(pady=(0, 8))

        progress_wrap = tk.Frame(content, bg=_BG_ROOT)
        progress_wrap.pack(fill="x", pady=(8, 4))

        self._progress_canvas = tk.Canvas(
            progress_wrap,
            height=8,
            bg=_BG_ROOT,
            highlightthickness=0,
            bd=0,
        )
        self._progress_canvas.pack(fill="x")
        self._progress_canvas.bind("<Configure>", lambda _e: self._redraw_progress())

        self._progress_meta = tk.Label(
            progress_wrap,
            text="",
            font=tkfont.Font(family="Segoe UI", size=8),
            fg=_TEXT_MUTED,
            bg=_BG_ROOT,
            anchor="w",
        )
        self._progress_meta.pack(fill="x", pady=(4, 0))

        tk.Label(
            content,
            textvariable=self._version_var,
            font=tkfont.Font(family="Segoe UI", size=8),
            fg=_ACCENT_DIM,
            bg=_BG_ROOT,
        ).pack(side="bottom", pady=(12, 0))

        if self._version:
            self._set_version_impl(self._version)

        self._redraw_progress()
        self._schedule_anim()

    def _minimize_impl(self) -> None:
        root = self._root
        if root is None:
            return
        try:
            root.iconify()
        except tk.TclError:
            pass

    def run(self, worker: Callable[[BootstrapUI], int]) -> int:
        """Show splash, run worker on a background thread, return its exit code."""
        self._worker = worker
        self._root = tk.Tk()
        self._init_tk_vars()
        self._build_ui()
        self._poll_queue()

        def _worker_wrapper() -> None:
            assert self._worker is not None
            try:
                self._result[0] = self._worker(self)
            except Exception as error:  # noqa: BLE001
                self.show_error(str(error))
                self._result[0] = 1
            finally:
                if self._result[0] == 0:
                    self.schedule_close()

        threading.Thread(target=_worker_wrapper, name="BlossomBootstrap", daemon=True).start()
        self._root.mainloop()
        return self._result[0]
