"""Logging: console + rotating file under ``<applications_dir>/.htp_logs/htp.log``.

Call ``setup_logging(cfg)`` once (API start-up, CLI main). Modules use
``logging.getLogger("htp.<area>")``. ``tail(cfg, n)`` serves the Settings page.
"""
from __future__ import annotations

import logging
import logging.handlers
from collections import deque
from pathlib import Path

from .config import Settings

LOG_DIR = ".htp_logs"
LOG_FILE = "htp.log"
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_console: logging.Handler | None = None
_file: logging.handlers.RotatingFileHandler | None = None


def log_path(cfg: Settings) -> Path:
    return cfg.applications_abs / LOG_DIR / LOG_FILE


def setup_logging(cfg: Settings, level: int = logging.INFO, console_level: int | None = None) -> Path | None:
    """Attach console + file handlers to the ``htp`` logger.

    Idempotent; calling again with a config whose applications dir moved
    re-points the file handler (settings update, tests). ``console_level``
    defaults to ``level``; the CLI raises it to WARNING so the file still
    records every call while stdout stays readable.
    """
    global _console, _file
    root = logging.getLogger("htp")
    root.setLevel(level)
    fmt = logging.Formatter(FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    if _console is None:
        _console = logging.StreamHandler()
        _console.setFormatter(fmt)
        _console.setLevel(console_level if console_level is not None else level)
        root.addHandler(_console)
        # Quiet noisy third-party loggers (pdf2docx prints every page at INFO).
        for name in ("pdf2docx", "httpx", "anthropic"):
            logging.getLogger(name).setLevel(logging.WARNING)

    path = log_path(cfg)
    if _file is not None:
        if Path(_file.baseFilename) == path:
            return path
        root.removeHandler(_file)
        _file.close()
        _file = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _file = logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        _file.setFormatter(fmt)
        root.addHandler(_file)
    except OSError as exc:  # unwritable applications dir: console only
        root.warning("file logging disabled: %s", exc)
        return None
    return path


def tail(cfg: Settings, lines: int = 200) -> list[str]:
    path = log_path(cfg)
    if not path.exists():
        return []
    with path.open(encoding="utf-8", errors="replace") as fh:
        return [ln.rstrip("\n") for ln in deque(fh, maxlen=max(1, min(lines, 2000)))]
