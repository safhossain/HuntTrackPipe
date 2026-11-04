"""One-time: ensure Location_Country / Location_City columns exist, then fill them
from each application's saved posting via Jev + Claude (location fields only).

Usage (repo root, venv active, Excel closed)::

    python -m scripts.one_time.migrate_locations
    python -m scripts.one_time.migrate_locations --dry-run
    python -m scripts.one_time.migrate_locations --limit 3

Does not overwrite non-empty location cells (fill-only-empty). Leaves blank when
neither field is found. Updates ``session.review.values`` for written cells.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow ``python -m scripts.one_time.migrate_locations`` from the repo root.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.columns import list_validation_options  # noqa: E402
from backend.config import settings  # noqa: E402
from backend.excel.tracker import Tracker  # noqa: E402
from backend.logs import setup_logging  # noqa: E402
from backend.pipeline import extract_locations  # noqa: E402
from backend.sessions.store import POSTING_FILE, SessionStore  # noqa: E402

LOCATION_COLUMNS = ("Location_Country", "Location_City")
log = logging.getLogger("htp.migrate_locations")


def _posting_text(store: SessionStore, folder: str, session_text: str | None) -> str:
    if session_text and session_text.strip():
        return session_text
    path = store.folder_path(folder) / POSTING_FILE
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Extract only; do not write Excel or sessions")
    p.add_argument("--limit", type=int, default=0, help="Process at most N sessions (0 = all)")
    p.add_argument("--folder", action="append", default=[], help="Only these folder names (repeatable)")
    args = p.parse_args(argv)

    cfg = settings()
    setup_logging(cfg, console_level=logging.INFO)
    store = SessionStore(cfg.applications_abs)
    tracker = Tracker(cfg.tracker_abs, backups_keep=cfg.backups_keep)

    print(f"tracker: {cfg.tracker_abs}")
    print(f"applications: {cfg.applications_abs}")
    if args.dry_run:
        print("DRY RUN — no writes")

    if not args.dry_run:
        tracker.check_writable()
        added = tracker.ensure_columns(list(LOCATION_COLUMNS))
        if added:
            print(f"added columns: {added}")
        else:
            print(f"columns already present: {list(LOCATION_COLUMNS)}")

    sessions = store.list_sessions()
    if args.folder:
        wanted = set(args.folder)
        sessions = [s for s in sessions if s.folder in wanted]
    if args.limit and args.limit > 0:
        sessions = sessions[: args.limit]

    print(f"sessions to process: {len(sessions)}")
    filled = 0
    blank = 0
    skipped = 0
    errors = 0

    for i, session in enumerate(sessions, start=1):
        folder = session.folder
        text = _posting_text(store, folder, session.posting.text if session.posting else None)
        if not text.strip():
            print(f"[{i}/{len(sessions)}] {folder}: no posting text — skip")
            skipped += 1
            continue
        try:
            ex = extract_locations(text, cfg)
        except Exception as exc:
            print(f"[{i}/{len(sessions)}] {folder}: ERROR {exc}")
            log.exception("extract failed for %s", folder)
            errors += 1
            continue

        country = ex.values.get("Location_Country")
        city = ex.values.get("Location_City")
        payload = {k: v for k, v in (("Location_Country", country), ("Location_City", city)) if v}
        print(
            f"[{i}/{len(sessions)}] {folder}: "
            f"country={country!r} city={city!r}"
            + (f"  warnings={ex.warnings}" if ex.warnings else "")
        )

        if not payload:
            blank += 1
            continue

        if args.dry_run:
            filled += 1
            continue

        try:
            report = tracker.write_row(
                folder,
                payload,
                fill_only_empty=True,
                list_options=list_validation_options(cfg),
            )
            for col, val in report.written.items():
                if col in LOCATION_COLUMNS:
                    session.review.values[col] = val
            if any(c in report.written for c in LOCATION_COLUMNS):
                store.save(session)
                filled += 1
            elif any(c in report.skipped for c in LOCATION_COLUMNS):
                print(f"    (skipped existing cells: { {k: report.skipped[k] for k in LOCATION_COLUMNS if k in report.skipped} })")
                skipped += 1
            else:
                blank += 1
        except Exception as exc:
            print(f"    write ERROR: {exc}")
            log.exception("write failed for %s", folder)
            errors += 1

    print(
        f"done. filled_or_would_fill={filled} blank={blank} skipped={skipped} errors={errors}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
