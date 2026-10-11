"""Build the strict JSON schema for the extraction call from Jev's decisions.

Rules (DESIGN.md section 7): only gated fields are present, every property is
required and nullable, ``additionalProperties: false``. Claude's structured
outputs do not accept ``maxItems``; the 3-category cap lives in the description
and is enforced in ``postprocess``.
"""
from __future__ import annotations

from typing import Any

from ..jev.questions import EMPLOYMENT_TYPE_VALUES, WORK_MODE_VALUES
from ..sessions.models import JevDerived

MAX_ROLE_CATEGORIES = 3

# field -> Excel column
FIELD_TO_COLUMN: dict[str, str] = {
    "requisition_id": "Requisition_ID",
    "organization": "Organization",
    "position_title": "Position_Title",
    "compensation": "Compensation",
    "work_mode": "Work_Mode",
    "employment_type": "Employment_Type",
    "deadline": "Deadline",
    "recruiter_name": "Recruiter_Name",
    "recruiter_contact": "Recruiter_Contact",
    "role_categories": "Role_Categories",
    "position_level": "Position_Level",
}


def _nullable_string(description: str) -> dict[str, Any]:
    return {"type": ["string", "null"], "description": description}


def _nullable_enum(values: list[str], description: str) -> dict[str, Any]:
    return {
        "anyOf": [{"type": "string", "enum": values}, {"type": "null"}],
        "description": description,
    }


FIELD_SPECS: dict[str, dict[str, Any]] = {
    "requisition_id": _nullable_string(
        "The requisition / job / reference ID exactly as written (e.g. 'R-98765', 'JR0012'). null if none."
    ),
    "organization": _nullable_string(
        "Name of the hiring organization (not the job board or staffing agency, unless it is hiring for itself). null if unknown."
    ),
    "position_title": _nullable_string("The job title exactly as written. null if none."),
    "compensation": _nullable_string(
        "Pay as written, including currency and period, e.g. 'CAD 80,000-95,000 / year' or '$35/hour'. null if no numeric pay is stated."
    ),
    "work_mode": _nullable_enum(
        list(WORK_MODE_VALUES.values()),
        "Where the work happens. 'TBD' only if the posting says it is to be determined; 'Unknown' if not mentioned.",
    ),
    "employment_type": _nullable_enum(
        list(EMPLOYMENT_TYPE_VALUES.values()),
        "Employment type. 'Unknown' if not mentioned.",
    ),
    "deadline": _nullable_string(
        "Application closing date as YYYY-MM-DD if a date is given. If only a phrase is given (e.g. 'Open until filled') return that phrase. null if nothing is stated."
    ),
    "recruiter_name": _nullable_string("Full name of the named contact person (recruiter / hiring manager). null if none."),
    "recruiter_contact": _nullable_string("Email, phone or profile URL of the named contact person. null if none."),
    "role_categories": {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            f"Between 1 and {MAX_ROLE_CATEGORIES} short labels for the technical area of the role, most specific first "
            "(e.g. 'Backend', 'Frontend', 'Full-stack', 'Mobile', 'DevOps', 'Cloud', 'Data Engineering', 'Machine Learning', "
            f"'QA', 'Embedded', 'Security'). Never more than {MAX_ROLE_CATEGORIES}. Empty array if it cannot be inferred."
        ),
    },
    "position_level": _nullable_string(
        "A single seniority label for the role, e.g. 'Intern', 'Co-op', 'Junior', 'Intermediate', 'Senior', 'Staff', 'Lead', 'Manager'. "
        "Infer from stated level or years of experience. null if nothing indicates the level."
    ),
}


def ordered_fields(derived: JevDerived) -> list[str]:
    wanted = set(derived.schema_fields) | set(derived.low_confidence_choices)
    return [f for f in FIELD_SPECS if f in wanted]


def build_schema(derived: JevDerived) -> dict[str, Any]:
    fields = ordered_fields(derived)
    if not fields:
        raise ValueError("No fields selected for extraction; nothing to ask the LLM.")
    return {
        "type": "object",
        "properties": {f: FIELD_SPECS[f] for f in fields},
        "required": fields,
        "additionalProperties": False,
    }
