"""Normalize LLM output + Jev direct values into Excel row values."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from ..sessions.models import JevDerived
from .schema_builder import FIELD_TO_COLUMN, MAX_ROLE_CATEGORIES

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iso_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and _ISO.match(value.strip()):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def row_values(derived: JevDerived, llm_output: dict[str, Any]) -> dict[str, Any]:
    """Return {Excel column: value} in Excel column order (deadline as date when ISO)."""
    out: dict[str, Any] = {}
    for fld, column in FIELD_TO_COLUMN.items():
        if column in derived.direct_values:
            out[column] = derived.direct_values[column]
            continue
        if fld not in llm_output:
            continue
        raw = llm_output[fld]
        if fld == "subrole_categories":
            cats = [c for c in (_clean_str(x) for x in (raw or [])) if c][:MAX_ROLE_CATEGORIES]
            out[column] = ", ".join(cats) if cats else None
        elif fld == "deadline":
            out[column] = parse_iso_date(raw) or _clean_str(raw)
        else:
            out[column] = _clean_str(raw)
    return out
