"""Assemble tracker lock + dropdown-sync status for the API."""
from __future__ import annotations

from typing import Any

from ..config import Settings
from .dropdown_sync import compare_dropdowns
from .lock_watch import lock_watch


def tracker_status_dict(cfg: Settings, *, force_compare: bool = False) -> dict[str, Any]:
    snap = lock_watch.probe()  # cheap ~$ exists() backup if a FS event was missed
    sync = compare_dropdowns(cfg, locked=snap.locked, force=force_compare)
    suggest = (not snap.locked) and sync.status == "mismatched"
    return {
        "locked": snap.locked,
        "lock_source": snap.lock_source,
        "owner_file": snap.owner_file,
        "tracker_path": snap.tracker_path or str(cfg.tracker_abs),
        "changed_at": snap.changed_at,
        "watching": snap.watching,
        "dropdown_sync": sync.as_dict(),
        "suggest_sync": suggest,
    }
