"""Excel tracker lock state driven by the ``~$workbook.xlsx`` owner file.

Excel creates that sibling file when the workbook is open and deletes it on
close. A filesystem watcher turns create/delete into ``sigON`` / ``sigOFF`` so
HTP can grey out writes without polling the workbook itself. A cheap
``exists()`` probe on status reads is a backup if an event was missed.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .tracker import owner_file_for

log = logging.getLogger("htp.tracker")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


UnlockCallback = Callable[[], None]


@dataclass
class LockSnapshot:
    locked: bool
    lock_source: str | None  # "owner_file" | None
    owner_file: str | None
    tracker_path: str
    changed_at: str | None
    watching: bool


class _OwnerHandler(FileSystemEventHandler):
    def __init__(self, watch: "TrackerLockWatch"):
        super().__init__()
        self._watch = watch

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watch._on_fs_event(Path(str(event.src_path)), created=True)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watch._on_fs_event(Path(str(event.src_path)), created=False)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        # Excel sometimes replaces via rename; treat dest create / src delete.
        if hasattr(event, "dest_path") and event.dest_path:
            self._watch._on_fs_event(Path(str(event.dest_path)), created=True)
        self._watch._on_fs_event(Path(str(event.src_path)), created=False)


class TrackerLockWatch:
    """Process-wide lock state for the configured tracker workbook."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tracker: Path | None = None
        self._owner: Path | None = None
        self._locked = False
        self._changed_at: str | None = None
        self._observer: Observer | None = None
        self._on_unlock: UnlockCallback | None = None
        self._watching = False

    def set_unlock_callback(self, cb: UnlockCallback | None) -> None:
        with self._lock:
            self._on_unlock = cb

    def start(self, tracker_path: Path) -> LockSnapshot:
        with self._lock:
            self._stop_observer_unlocked()
            self._tracker = Path(tracker_path)
            self._owner = owner_file_for(self._tracker)
            was = self._locked
            self._locked = self._owner.exists()
            self._changed_at = _utc_now()
            self._start_observer_unlocked()
            snap = self._snapshot_unlocked()
            if was and not self._locked:
                self._fire_unlock_unlocked()
            log.info(
                "lock watch start tracker=%s locked=%s watching=%s",
                self._tracker, self._locked, self._watching,
            )
            return snap

    def retarget(self, tracker_path: Path) -> LockSnapshot:
        """Point the watcher at a new tracker path (Settings change)."""
        return self.start(tracker_path)

    def stop(self) -> None:
        with self._lock:
            self._stop_observer_unlocked()
            self._watching = False
            log.info("lock watch stopped")

    def probe(self) -> LockSnapshot:
        """Re-stat the owner file (backup if a FS event was missed)."""
        with self._lock:
            if self._owner is None:
                return self._snapshot_unlocked()
            now = self._owner.exists()
            if now != self._locked:
                prev = self._locked
                self._locked = now
                self._changed_at = _utc_now()
                log.info("lock probe transition locked=%s -> %s", prev, now)
                if prev and not now:
                    self._fire_unlock_unlocked()
            return self._snapshot_unlocked()

    def snapshot(self) -> LockSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def force_locked(self, locked: bool, *, source: str = "owner_file") -> None:
        """Test helper / manual override."""
        with self._lock:
            prev = self._locked
            self._locked = locked
            self._changed_at = _utc_now()
            if prev and not locked:
                self._fire_unlock_unlocked()

    # ---- internals --------------------------------------------------------
    def _snapshot_unlocked(self) -> LockSnapshot:
        owner = self._owner
        return LockSnapshot(
            locked=self._locked,
            lock_source="owner_file" if self._locked else None,
            owner_file=str(owner) if owner and self._locked else (str(owner) if owner else None),
            tracker_path=str(self._tracker) if self._tracker else "",
            changed_at=self._changed_at,
            watching=self._watching,
        )

    def _fire_unlock_unlocked(self) -> None:
        cb = self._on_unlock
        if cb is None:
            return
        try:
            cb()
        except Exception:
            log.exception("unlock callback failed")

    def _is_owner_path(self, path: Path) -> bool:
        assert self._owner is not None
        if path.name.lower() != self._owner.name.lower():
            return False
        try:
            return path.parent.resolve() == self._owner.parent.resolve()
        except OSError:
            return True  # name matched; parent resolve can fail mid-delete

    def _on_fs_event(self, path: Path, *, created: bool) -> None:
        with self._lock:
            if self._owner is None or not self._is_owner_path(path):
                return
            prev = self._locked
            self._locked = True if created else self._owner.exists()
            if self._locked == prev:
                return
            self._changed_at = _utc_now()
            log.info("lock event %s -> locked=%s (%s)", "create" if created else "delete", self._locked, path.name)
            if prev and not self._locked:
                self._fire_unlock_unlocked()

    def _start_observer_unlocked(self) -> None:
        assert self._tracker is not None and self._owner is not None
        parent = self._tracker.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.warning("lock watch: cannot ensure parent dir %s: %s", parent, exc)
            self._watching = False
            return
        handler = _OwnerHandler(self)
        observer = Observer()
        try:
            observer.schedule(handler, str(parent), recursive=False)
            observer.daemon = True
            observer.start()
            self._observer = observer
            self._watching = True
        except Exception as exc:
            log.warning("lock watch: observer failed (%s); status reads will probe ~$", exc)
            self._observer = None
            self._watching = False

    def _stop_observer_unlocked(self) -> None:
        obs = self._observer
        self._observer = None
        if obs is not None:
            try:
                obs.stop()
                obs.join(timeout=5)
            except Exception:
                log.exception("lock watch: observer stop failed")


# Process singleton used by the API lifespan.
lock_watch = TrackerLockWatch()
