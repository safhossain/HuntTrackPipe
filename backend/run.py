"""CLI for the core pipeline (step 1 of DESIGN.md section 16).

Examples
  python -m backend.run --posting posting.txt
  python -m backend.run --posting posting.txt --url https://... --applied-date 2026-10-11 --applied-through LinkedIn
  python -m backend.run --posting posting.txt --dry-run          # extract only, print, no files/Excel
  python -m backend.run --posting posting.txt --no-jev            # LLM extracts everything
  python -m backend.run --posting posting.txt --no-llm --dry-run  # see Jev decisions only
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from .columns import OPTIONS
from .config import load_settings
from .duplicates import DuplicateError
from .excel.tracker import TrackerError, TrackerLocked
from .logs import setup_logging
from .pipeline import create_application, extract

STATUSES = tuple(OPTIONS["Application_Status"])
APPLIED_THROUGH = tuple(OPTIONS["Applied_Through"])


def _read_posting(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    return Path(arg).read_text(encoding="utf-8")


def _print_section(title: str) -> None:
    print(f"\n== {title} ==")


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m backend.run", description="HuntTrackPipe core pipeline")
    p.add_argument("--posting", required=True, help="path to posting .txt, or '-' for stdin")
    p.add_argument("--url", help="Posting_URL (manual column)")
    p.add_argument("--applied-date", type=date.fromisoformat, help="Applied_Date as YYYY-MM-DD")
    p.add_argument("--status", choices=STATUSES, help="Application_Status (default: Not Applied)")
    p.add_argument("--applied-through", choices=APPLIED_THROUGH, help="Applied_Through")
    p.add_argument("--confirmation", help="Confirmation_#")
    p.add_argument("--no-jev", action="store_true", help="skip Jev; LLM extracts every field")
    p.add_argument("--no-llm", action="store_true", help="skip the LLM; only Jev direct values are used")
    p.add_argument("--dry-run", action="store_true", help="extract and print only; no folder, no Excel write")
    p.add_argument("-y", "--yes", action="store_true", help="do not ask before creating folder + row")
    p.add_argument("--allow-duplicate", action="store_true", help="create even if the posting matches an existing application")
    p.add_argument("--json", action="store_true", help="print machine-readable JSON instead of sections")
    a = p.parse_args(argv)

    cfg = load_settings()
    setup_logging(cfg, console_level=logging.WARNING)  # file gets everything; console stays quiet
    posting = _read_posting(a.posting).strip()
    if not posting:
        print("Posting is empty.", file=sys.stderr)
        return 2

    ex = extract(posting, cfg, use_jev=not a.no_jev, use_llm=not a.no_llm)

    if a.json:
        print(_dump({
            "jev": ex.jev.model_dump(by_alias=True) if ex.jev else None,
            "llm": ex.llm.model_dump(by_alias=True) if ex.llm else None,
            "values": ex.values,
            "warnings": ex.warnings,
        }))
    else:
        if ex.jev:
            _print_section(f"Jev ({ex.jev.model})")
            for key, ans in ex.jev.answers.items():
                if ans.get("type") == "noul":
                    print(f"  {key:<24} noul={ans.get('noul'):.2f}")
                elif ans.get("type") == "choice":
                    print(f"  {key:<24} choice={ans.get('choice')} conf={ans.get('confidence')}")
            d = ex.derived
            print(f"  -> schema fields: {d.schema_fields}")
            print(f"  -> direct values: {d.direct_values}")
            print(f"  -> LLM decides  : {d.low_confidence_choices}")
            print(f"  -> upload mode  : {d.upload_mode} (conf={d.upload_mode_confidence}) docs={d.required_docs}")
            if ex.jev.usage:
                print(f"  usage: {ex.jev.usage}")
        if ex.llm:
            _print_section(f"LLM ({ex.llm.model})")
            print(_dump(ex.llm.output))
            print(f"  usage: {ex.llm.usage}")
        _print_section("Row values")
        for k, v in ex.values.items():
            print(f"  {k:<20} {v}")
        if ex.warnings:
            _print_section("Warnings")
            for w in ex.warnings:
                print(f"  - {w}")

    if a.dry_run:
        return 0

    manual = {
        "Applied_Date": a.applied_date,
        "Posting_URL": a.url,
        "Application_Status": a.status,
        "Applied_Through": a.applied_through,
        "Confirmation_#": a.confirmation,
    }
    if not a.yes:
        ans = input("\nCreate application folder and write the Excel row? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("Aborted; nothing written.")
            return 0

    try:
        session, report = create_application(
            cfg, posting_text=posting, posting_url=a.url, extraction=ex, manual=manual,
            allow_duplicate=a.allow_duplicate,
        )
    except DuplicateError as exc:
        print(f"\n{exc} (re-run with --allow-duplicate)", file=sys.stderr)
        return 5
    except TrackerLocked as exc:
        print(f"\nExcel is locked: {exc}", file=sys.stderr)
        return 3
    except TrackerError as exc:
        print(f"\nTracker error: {exc}", file=sys.stderr)
        return 4

    _print_section("Done")
    print(f"  folder : {cfg.applications_abs / session.folder}")
    print(f"  row    : {report.row} ({'new' if report.created else 'existing'})")
    print(f"  written: {list(report.written)}")
    if report.skipped:
        print(f"  skipped (cell already had a different value): {report.skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
