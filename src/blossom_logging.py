"""Central logging for Blossom — writes to %LOCALAPPDATA%\\Blossom\\logs\\.

Files:
  logs.txt    — main session log (INFO and above; DEBUG when BLOSSOM_LOG_DEBUG=1)
  errors.log  — ERROR and CRITICAL only
  logs.txt.1 … — rotated backups when logs.txt exceeds the size limit
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import IO, TextIO

from blossom_dirs import LOGS_DIR, ensure_app_data_dirs, reveal_folder_in_explorer

_CONFIGURED = False
_LOCK = threading.Lock()

MAIN_LOG_NAME = "logs.txt"
ERRORS_LOG_NAME = "errors.log"

# 5 MB per file, keep 5 rotated backups for the main log; 2 MB × 3 for errors.
_MAIN_MAX_BYTES = 5 * 1024 * 1024
_MAIN_BACKUP_COUNT = 5
_ERRORS_MAX_BYTES = 2 * 1024 * 1024
_ERRORS_BACKUP_COUNT = 3

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(component)-18s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _ComponentFilter(logging.Filter):
    """Ensure every record has a short component label for the log line."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "component", None):
            name = record.name
            if name.startswith("blossom."):
                record.component = name.split(".", 1)[1]
            elif name == "blossom":
                record.component = "app"
            else:
                record.component = name
        return True


class _StdStreamWriter(TextIO):
    """Redirect print() / stderr into the Blossom log without losing console output."""

    def __init__(self, logger: logging.Logger, level: int, *, is_stderr: bool = False) -> None:
        self._logger = logger
        self._level = level
        self._is_stderr = is_stderr
        self._buffer = ""
        self._original: IO[str] | None = getattr(sys, "__stdout__" if not is_stderr else "__stderr__", None)

    def write(self, message: str) -> int:
        if not message:
            return 0
        self._buffer += message
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit_line(line)
        if self._original is not None:
            try:
                self._original.write(message)
            except Exception:
                pass
        return len(message)

    def flush(self) -> None:
        if self._buffer:
            self._emit_line(self._buffer.rstrip("\r"))
            self._buffer = ""
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        if self._original is not None:
            try:
                return self._original.isatty()
            except Exception:
                pass
        return False

    def _emit_line(self, line: str) -> None:
        text = line.rstrip("\r")
        if not text:
            return
        component, message = _parse_bracket_tag(text)
        level = self._level
        if self._is_stderr and not text.startswith("Traceback"):
            # Heuristic: stderr lines that look like errors get ERROR level.
            lowered = text.lower()
            if any(token in lowered for token in ("error", "failed", "exception", "fatal")):
                level = logging.ERROR
            elif any(token in lowered for token in ("warn", "warning")):
                level = logging.WARNING
        self._logger.log(level, message, extra={"component": component})


def _parse_bracket_tag(line: str) -> tuple[str, str]:
    """Turn ``[macro] started`` into component ``macro``, message ``started``."""
    if line.startswith("[") and "]" in line[:48]:
        end = line.index("]")
        tag = line[1:end].strip() or "app"
        rest = line[end + 1 :].strip()
        return tag, rest or line
    return "stdio", line


def main_log_path() -> Path:
    return LOGS_DIR / MAIN_LOG_NAME


def errors_log_path() -> Path:
    return LOGS_DIR / ERRORS_LOG_NAME


def log_paths() -> dict[str, Path]:
    return {
        "folder": LOGS_DIR,
        "main": main_log_path(),
        "errors": errors_log_path(),
    }


def _debug_enabled() -> bool:
    raw = os.environ.get("BLOSSOM_LOG_DEBUG", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def setup_logging(app_component: str = "app", *, debug: bool | None = None) -> logging.Logger:
    """Configure file logging once per process. Safe to call from bootstrap and main UI."""
    global _CONFIGURED
    with _LOCK:
        if _CONFIGURED:
            return get_logger(app_component)

        ensure_app_data_dirs()
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        level = logging.DEBUG if (debug if debug is not None else _debug_enabled()) else logging.INFO
        root = logging.getLogger("blossom")
        root.setLevel(level)
        root.handlers.clear()
        root.propagate = False

        formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
        component_filter = _ComponentFilter()

        main_handler = RotatingFileHandler(
            main_log_path(),
            maxBytes=_MAIN_MAX_BYTES,
            backupCount=_MAIN_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        main_handler.setLevel(level)
        main_handler.setFormatter(formatter)
        main_handler.addFilter(component_filter)

        errors_handler = RotatingFileHandler(
            errors_log_path(),
            maxBytes=_ERRORS_MAX_BYTES,
            backupCount=_ERRORS_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        errors_handler.setLevel(logging.ERROR)
        errors_handler.setFormatter(formatter)
        errors_handler.addFilter(component_filter)

        root.addHandler(main_handler)
        root.addHandler(errors_handler)

        install_exception_hooks(root)
        _redirect_stdio(root)

        _CONFIGURED = True
        logger = get_logger(app_component)
        try:
            from blossom_updater import APP_VERSION, build_channel, display_version

            version_label = display_version()
            channel = build_channel()
        except Exception:
            version_label = "unknown"
            channel = "unknown"

        logger.info(
            "Logging initialized — version %s (%s channel). Folder: %s",
            version_label,
            channel,
            LOGS_DIR,
        )
        logger.info("Main log: %s | Errors: %s", main_log_path(), errors_log_path())
        return logger


def get_logger(component: str) -> logging.Logger:
    """Return a namespaced logger (e.g. ``get_logger('macro')`` → ``blossom.macro``)."""
    name = component.strip() or "app"
    if name.startswith("blossom."):
        return logging.getLogger(name)
    return logging.getLogger(f"blossom.{name}")


def install_exception_hooks(root: logging.Logger | None = None) -> None:
    """Log uncaught exceptions from the main thread and from ``threading`` workers."""
    log = root or get_logger("exceptions")

    def _handle(exc_type, exc_value, exc_tb) -> None:
        if exc_type is KeyboardInterrupt:
            log.info("Interrupted by user (KeyboardInterrupt)")
            return
        log.error(
            "Uncaught exception — %s: %s",
            getattr(exc_type, "__name__", exc_type),
            exc_value,
            exc_info=(exc_type, exc_value, exc_tb),
            extra={"component": "uncaught"},
        )

    sys.excepthook = _handle

    if hasattr(threading, "excepthook"):
        _orig_thread_hook = threading.excepthook

        def _thread_handle(args) -> None:  # type: ignore[no-untyped-def]
            log.error(
                "Uncaught exception in thread %r — %s: %s",
                args.thread.name if args.thread else "?",
                getattr(args.exc_type, "__name__", args.exc_type),
                args.exc_value,
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
                extra={"component": "thread"},
            )
            if _orig_thread_hook is not None:
                try:
                    _orig_thread_hook(args)
                except Exception:
                    pass

        threading.excepthook = _thread_handle  # type: ignore[attr-defined]


def _redirect_stdio(root: logging.Logger) -> None:
    if getattr(sys, "__stdout__", None) is not None and not isinstance(sys.stdout, _StdStreamWriter):
        sys.__stdout__ = sys.stdout
        sys.stdout = _StdStreamWriter(root, logging.INFO, is_stderr=False)
    if getattr(sys, "__stderr__", None) is not None and not isinstance(sys.stderr, _StdStreamWriter):
        sys.__stderr__ = sys.stderr
        sys.stderr = _StdStreamWriter(root, logging.WARNING, is_stderr=True)


def read_recent_logs(*, max_lines: int = 300, include_errors: bool = True) -> str:
    """Return the tail of logs.txt (and optionally errors.log) for support / copy."""
    max_lines = max(20, min(int(max_lines), 2000))
    chunks: list[str] = []

    main_path = main_log_path()
    if main_path.is_file():
        chunks.append(_tail_file(main_path, max_lines))

    if include_errors:
        err_path = errors_log_path()
        if err_path.is_file() and err_path.stat().st_size > 0:
            err_tail = _tail_file(err_path, min(80, max_lines // 3))
            if err_tail.strip():
                chunks.append(f"--- {ERRORS_LOG_NAME} (recent) ---\n{err_tail}")

    if not chunks:
        return (
            f"No log entries yet. Logs are written to:\n{LOGS_DIR}\n"
            f"Expected file: {main_path}"
        )
    header = (
        f"Blossom diagnostic log excerpt\n"
        f"Folder: {LOGS_DIR}\n"
        f"{'=' * 60}\n"
    )
    return header + "\n".join(chunks)


def _tail_file(path: Path, max_lines: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        if len(lines) <= max_lines:
            return "".join(lines)
        return "".join(lines[-max_lines:])
    except OSError as error:
        return f"(could not read {path.name}: {error})\n"


def open_logs_folder() -> dict[str, object]:
    """Open the logs directory in Explorer (Windows)."""
    ensure_app_data_dirs()
    return reveal_folder_in_explorer(LOGS_DIR)


def log_bridge_error(method: str, error: BaseException) -> None:
    """Record a pywebview API failure with traceback."""
    get_logger("bridge").error(
        "API %s failed: %s\n%s",
        method,
        error,
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        extra={"component": "bridge"},
    )
