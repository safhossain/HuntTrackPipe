"""Tracker column registry: which columns the engine extracts, which are
manual, and the dropdown options (mirrors the Excel data validations).

Shipped defaults live here. ``Application_Status``, ``Applied_Through`` and
``Found_From`` can be overridden via ``htp.config.json`` ``options`` and grown
from the UI; Excel list validations are synced from the resolved lists.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from .jev.questions import EMPLOYMENT_TYPE_VALUES, ROLE_CATEGORY_VALUES, WORK_MODE_VALUES
from .naming import DOC_TYPES

if TYPE_CHECKING:
    from .config import Settings

EXTRACTED_COLUMNS: tuple[str, ...] = (
    "Requisition_ID",
    "Organization",
    "Position_Title",
    "Location_Country",
    "Location_City",
    "Compensation",
    "Work_Mode",
    "Employment_Type",
    "Deadline",
    "Recruiter_Name",
    "Recruiter_Contact",
    "Role_Category",
    "Subrole_Categories",
    "Position_Level",
)

MANUAL_COLUMNS: tuple[str, ...] = (
    "Applied_Date",
    "Posting_URL",
    "Application_Status",
    "Outcome",
    "Applied_Through",
    "Found_From",
)

ENGINE_COLUMNS: tuple[str, ...] = ("Days_Since_Applied", "Folder")

DATE_COLUMNS: tuple[str, ...] = ("Applied_Date", "Deadline")

# Columns the UI may grow; Work_Mode / Employment_Type / Outcome / Role_Category stay code-only.
EDITABLE_OPTION_COLUMNS: tuple[str, ...] = (
    "Application_Status",
    "Applied_Through",
    "Found_From",
)

# Reinforced onto the Applications table body on every tracker write / sync.
LIST_SYNC_COLUMNS: tuple[str, ...] = (
    "Work_Mode",
    "Employment_Type",
    "Application_Status",
    "Outcome",
    "Applied_Through",
    "Found_From",
    "Role_Category",
)

DEFAULT_OPTIONS: dict[str, list[str]] = {
    "Work_Mode": list(WORK_MODE_VALUES.values()),
    "Employment_Type": list(EMPLOYMENT_TYPE_VALUES.values()),
    "Application_Status": ["Not Applied", "Applied", "Recruiter-Screening", "Technical Interview", "Final Round"],
    "Outcome": ["Pending", "Early interest", "Withdrawn", "Rejected", "Offer", "Accepted"],
    "Applied_Through": ["Org-Portal", "Indeed", "LinkedIn", "Email", "Workday", "Greenhouse", "AshbyHQ", "UltiPro", "Other"],
    "Found_From": ["HiringCafe", "LinkedIn", "Indeed", "GCJobs", "CRA", "Other"],
    "Role_Category": list(ROLE_CATEGORY_VALUES.values()),
}

# Back-compat alias for shipped defaults (prefer resolved_options()).
OPTIONS = DEFAULT_OPTIONS


def _dropdown_order(values: Iterable[str]) -> list[str]:
    return sorted(values, key=lambda value: (value.casefold() == "other", value.casefold()))


def resolved_options(cfg_options: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    """Alphabetized dropdowns with config overrides and Other at the end."""
    out = dict(DEFAULT_OPTIONS)
    if cfg_options:
        for key in EDITABLE_OPTION_COLUMNS:
            if key in cfg_options and cfg_options[key] is not None:
                out[key] = cfg_options[key]
    return {key: _dropdown_order(values) for key, values in out.items()}


def editable_list_options(cfg: Settings) -> dict[str, list[str]]:
    """Editable dropdown lists only (Sync dock / Add…)."""
    opts = resolved_options(cfg.options)
    return {k: opts[k] for k in EDITABLE_OPTION_COLUMNS}


def list_validation_options(cfg: Settings) -> dict[str, list[str]]:
    """All list columns HTP mirrors into Excel table-body data validations."""
    opts = resolved_options(cfg.options)
    return {k: opts[k] for k in LIST_SYNC_COLUMNS}


def meta_payload(cfg: Settings | None = None) -> dict[str, Any]:
    cfg_options = cfg.options if cfg is not None else None
    return {
        "extracted_columns": list(EXTRACTED_COLUMNS),
        "manual_columns": list(MANUAL_COLUMNS),
        "engine_columns": list(ENGINE_COLUMNS),
        "date_columns": list(DATE_COLUMNS),
        "options": resolved_options(cfg_options),
        "editable_option_columns": list(EDITABLE_OPTION_COLUMNS),
        "doc_types": _dropdown_order(DOC_TYPES),
        "upload_modes": ["single_document", "separate_uploads", "single_combined_file", "not_stated"],
    }


# Static snapshot (defaults only). Prefer ``meta_payload(settings())`` in the API.
META = meta_payload(None)
