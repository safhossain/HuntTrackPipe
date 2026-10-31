"""Compare HTP editable dropdown options against Excel list data-validations.

Only safe to run when the tracker is not locked (see ``lock_watch``). Results
are cached by tracker mtime + options fingerprint so repeat status reads are cheap.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from ..columns import EDITABLE_OPTION_COLUMNS, editable_list_options
from ..config import Settings
from .tracker import Tracker, TrackerError, TrackerLocked

log = logging.getLogger("htp.tracker")

SyncStatusName = Literal["in_sync", "mismatched", "locked", "missing", "error"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class ColumnDiff:
    column: str
    htp: list[str]
    excel: list[str] | None
    changed: bool


@dataclass
class DropdownSyncResult:
    status: SyncStatusName
    columns: list[ColumnDiff] = field(default_factory=list)
    checked_at: str | None = None
    tracker_mtime: float | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "columns": [
                {"column": c.column, "htp": c.htp, "excel": c.excel, "changed": c.changed}
                for c in self.columns
            ],
            "checked_at": self.checked_at,
            "tracker_mtime": self.tracker_mtime,
            "detail": self.detail,
        }


def _options_fingerprint(options: dict[str, list[str]]) -> str:
    payload = {k: options.get(k, []) for k in EDITABLE_OPTION_COLUMNS}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _stat_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


class DropdownSyncCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._result: DropdownSyncResult | None = None
        self._key: tuple[str, float | None, str] | None = None  # path, mtime, fp

    def clear(self) -> None:
        with self._lock:
            self._result = None
            self._key = None

    def get_cached(self, tracker_path: Path, options: dict[str, list[str]]) -> DropdownSyncResult | None:
        with self._lock:
            if self._result is None or self._key is None:
                return None
            mtime = _stat_mtime(tracker_path)
            key = (str(tracker_path.resolve()), mtime, _options_fingerprint(options))
            if key != self._key:
                return None
            return self._result

    def store(self, tracker_path: Path, options: dict[str, list[str]], result: DropdownSyncResult) -> None:
        with self._lock:
            mtime = result.tracker_mtime if result.tracker_mtime is not None else _stat_mtime(tracker_path)
            try:
                resolved = str(tracker_path.resolve())
            except OSError:
                resolved = str(tracker_path)
            self._key = (resolved, mtime, _options_fingerprint(options))
            self._result = result


dropdown_cache = DropdownSyncCache()


def compare_dropdowns(cfg: Settings, *, locked: bool, force: bool = False) -> DropdownSyncResult:
    """Compare editable HTP options to Excel list DVs.

    When ``locked`` is true, returns ``status=locked`` without opening the workbook
    (caller must gate on lock watch / probe first).
    """
    options = editable_list_options(cfg)
    path = cfg.tracker_abs

    if locked:
        return DropdownSyncResult(
            status="locked",
            columns=[ColumnDiff(column=c, htp=options[c], excel=None, changed=False) for c in EDITABLE_OPTION_COLUMNS],
            checked_at=_utc_now(),
            detail="Tracker appears open in Excel; close it before checking dropdown sync.",
        )

    if not path.exists():
        return DropdownSyncResult(
            status="missing",
            checked_at=_utc_now(),
            detail=f"Tracker not found: {path}",
        )

    if not force:
        cached = dropdown_cache.get_cached(path, options)
        if cached is not None:
            return cached

    try:
        excel_lists = Tracker(path, backups_keep=cfg.backups_keep).read_list_options(EDITABLE_OPTION_COLUMNS)
    except TrackerLocked:
        return DropdownSyncResult(
            status="locked",
            checked_at=_utc_now(),
            detail="Tracker became locked while reading dropdowns.",
        )
    except (TrackerError, OSError) as exc:
        log.warning("dropdown compare failed: %s", exc)
        return DropdownSyncResult(status="error", checked_at=_utc_now(), detail=str(exc))

    cols: list[ColumnDiff] = []
    mismatched = False
    for name in EDITABLE_OPTION_COLUMNS:
        htp = list(options[name])
        excel = excel_lists.get(name)
        changed = excel != htp
        if changed:
            mismatched = True
        cols.append(ColumnDiff(column=name, htp=htp, excel=excel, changed=changed))

    result = DropdownSyncResult(
        status="mismatched" if mismatched else "in_sync",
        columns=cols,
        checked_at=_utc_now(),
        tracker_mtime=_stat_mtime(path),
    )
    dropdown_cache.store(path, options, result)
    log.info("dropdown compare status=%s mismatched_cols=%s", result.status, [c.column for c in cols if c.changed])
    return result


def sync_dropdowns_to_excel(cfg: Settings) -> DropdownSyncResult:
    """Push HTP editable options into Excel list validations, then re-compare."""
    options = editable_list_options(cfg)
    tracker = Tracker(cfg.tracker_abs, backups_keep=cfg.backups_keep)
    tracker.sync_list_validations(options)
    dropdown_cache.clear()
    return compare_dropdowns(cfg, locked=False, force=True)
