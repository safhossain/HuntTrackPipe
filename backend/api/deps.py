"""Shared helpers for routers."""
from __future__ import annotations

from datetime import date
from typing import Any

from ..columns import DATE_COLUMNS
from ..config import Settings, settings
from ..excel.tracker import Tracker, WriteReport
from ..llm.postprocess import parse_iso_date
from ..sessions.store import SessionStore
from .models import WriteReportModel


def get_settings() -> Settings:
    return settings()


def get_store(cfg: Settings | None = None) -> SessionStore:
    cfg = cfg or settings()
    return SessionStore(cfg.applications_abs)


def get_tracker(cfg: Settings | None = None) -> Tracker:
    cfg = cfg or settings()
    return Tracker(cfg.tracker_abs, backups_keep=cfg.backups_keep)


def report_model(r: WriteReport) -> WriteReportModel:
    return WriteReportModel(
        row=r.row,
        created=r.created,
        written=r.written,
        skipped={k: [a, b] for k, (a, b) in r.skipped.items()},
    )


def coerce_row_values(values: dict[str, Any]) -> dict[str, Any]:
    """JSON -> Excel-ready values: ISO strings in date columns become dates;
    empty strings become None (so they are not written)."""
    out: dict[str, Any] = {}
    for col, v in values.items():
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                v = None
        if v is not None and col in DATE_COLUMNS and not isinstance(v, date):
            parsed = parse_iso_date(v)
            v = parsed if parsed is not None else v
        out[col] = v
    return out
