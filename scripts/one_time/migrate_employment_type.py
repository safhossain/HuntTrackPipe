"""One-time: sync Employment_Type list DV, clear all Employment_Type cells, then
re-classify every session from its posting (Jev choice; LLM enum if low conf).

Usage (repo root, venv active, Excel closed)::

    python -m scripts.one_time.migrate_employment_type
    python -m scripts.one_time.migrate_employment_type --dry-run
    python -m scripts.one_time.migrate_employment_type --limit 3
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.columns import list_validation_options  # noqa: E402
from backend.config import settings  # noqa: E402
from backend.excel.tracker import Tracker  # noqa: E402
from backend.logs import setup_logging  # noqa: E402
from backend.pipeline import extract_employment_type  # noqa: E402
from backend.sessions.store import POSTING_FILE, SessionStore  # noqa: E402

COLUMN = "Employment_Type"
log = logging.getLogger("htp.migrate_employment_type")


def _posting_text(store: SessionStore, folder: str, session_text: str | None) -> str:
    if session_text and session_text.strip():
        return session_text
    path = store.folder_path(folder) / POSTING_FILE
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Classify only; no Excel / session writes")
    p.add_argument("--limit", type=int, default=0, help="Process at most N sessions (0 = all)")
    p.add_argument("--folder", action="append", default=[], help="Only these folder names (repeatable)")
    p.add_argument(
        "--skip-clear",
        action="store_true",
        help="Do not clear Employment_Type first (still force-overwrite on write)",
    )
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
        opts = list_validation_options(cfg)
        touched = tracker.sync_list_validations(opts)
        print(f"synced list DVs: {touched}")
        if not args.skip_clear:
            cleared = tracker.clear_column_body(COLUMN)
            print(f"cleared {COLUMN}: {cleared} non-empty cells")

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
            ex = extract_employment_type(text, cfg)
        except Exception as exc:
            print(f"[{i}/{len(sessions)}] {folder}: ERROR {exc}")
            log.exception("extract failed for %s", folder)
            errors += 1
            continue

        value = ex.values.get(COLUMN)
        print(
            f"[{i}/{len(sessions)}] {folder}: {COLUMN}={value!r}"
            + (f"  warnings={ex.warnings}" if ex.warnings else "")
        )

        if not value:
            blank += 1
            if not args.dry_run:
                session.review.values.pop(COLUMN, None)
                try:
                    store.save(session)
                except Exception as exc:
                    print(f"    session save ERROR: {exc}")
                    errors += 1
            continue

        if args.dry_run:
            filled += 1
            continue

        try:
            report = tracker.write_row(
                folder,
                {COLUMN: value},
                fill_only_empty=False,
                force_columns={COLUMN},
                list_options=list_validation_options(cfg),
            )
            if COLUMN in report.written:
                session.review.values[COLUMN] = value
                store.save(session)
                filled += 1
            else:
                blank += 1
        except Exception as exc:
            print(f"    write ERROR: {exc}")
            log.exception("write failed for %s", folder)
            errors += 1

    print(f"done. filled_or_would_fill={filled} blank={blank} skipped={skipped} errors={errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
