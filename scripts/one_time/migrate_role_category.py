"""One-time: delete Confirmation_#, sync list DVs (incl. Role_Category), classify
Role_Category for each session from posting + existing Subrole_Categories.

Does **not** re-extract Subrole_Categories.

Usage (repo root, venv active, Excel closed)::

    python -m scripts.one_time.migrate_role_category
    python -m scripts.one_time.migrate_role_category --dry-run
    python -m scripts.one_time.migrate_role_category --limit 3
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
from backend.pipeline import classify_role_category  # noqa: E402
from backend.sessions.store import POSTING_FILE, SessionStore  # noqa: E402

log = logging.getLogger("htp.migrate_role_category")


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
        removed = tracker.delete_columns(["Confirmation_#"])
        print(f"deleted columns: {removed or '(Confirmation_# already absent)'}")
        touched = tracker.sync_list_validations(list_validation_options(cfg))
        print(f"synced list DVs: {touched}")

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

        row = None
        try:
            row = tracker.read_row(folder)
        except Exception as exc:
            log.warning("read_row %s: %s", folder, exc)

        # Prefer Excel subroles; fall back to session (legacy Role_Categories key).
        subroles = None
        if row:
            subroles = row.get("Subrole_Categories") or row.get("Role_Categories")
        if not subroles:
            subroles = session.review.values.get("Subrole_Categories") or session.review.values.get("Role_Categories")
        if isinstance(subroles, str):
            subroles = subroles.strip() or None
        else:
            subroles = None

        # Remap legacy session key even when we leave Role_Category blank.
        if "Role_Categories" in session.review.values and "Subrole_Categories" not in session.review.values:
            session.review.values["Subrole_Categories"] = session.review.values.pop("Role_Categories")
        elif "Role_Categories" in session.review.values:
            session.review.values.pop("Role_Categories", None)
        session.review.values.pop("Confirmation_#", None)

        try:
            role, _ans, warnings = classify_role_category(text, cfg, subrole_categories=subroles)
        except Exception as exc:
            print(f"[{i}/{len(sessions)}] {folder}: ERROR {exc}")
            log.exception("classify failed for %s", folder)
            errors += 1
            continue

        print(
            f"[{i}/{len(sessions)}] {folder}: Role_Category={role!r} subroles={subroles!r}"
            + (f"  warnings={warnings}" if warnings else "")
        )

        if not args.dry_run:
            try:
                store.save(session)
            except Exception as exc:
                print(f"    session save ERROR: {exc}")
                errors += 1

        if not role:
            blank += 1
            continue

        if args.dry_run:
            filled += 1
            continue

        try:
            report = tracker.write_row(
                folder,
                {"Role_Category": role},
                fill_only_empty=True,
                list_options=list_validation_options(cfg),
            )
            if "Role_Category" in report.written:
                session.review.values["Role_Category"] = role
                store.save(session)
                filled += 1
            elif "Role_Category" in report.skipped:
                print(f"    (skipped existing: {report.skipped['Role_Category']})")
                skipped += 1
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
