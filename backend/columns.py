"""Tracker column registry: which columns the engine extracts, which are
manual, and the dropdown options (mirrors the Excel data validations)."""
from __future__ import annotations

from .jev.questions import EMPLOYMENT_TYPE_VALUES, WORK_MODE_VALUES
from .naming import DOC_TYPES

EXTRACTED_COLUMNS: tuple[str, ...] = (
    "Requisition_ID",
    "Organization",
    "Position_Title",
    "Compensation",
    "Work_Mode",
    "Employment_Type",
    "Deadline",
    "Recruiter_Name",
    "Recruiter_Contact",
    "Role_Categories",
    "Position_Level",
)

MANUAL_COLUMNS: tuple[str, ...] = (
    "Applied_Date",
    "Posting_URL",
    "Application_Status",
    "Outcome",
    "Applied_Through",
    "Confirmation_#",
    "Found_From",
)

ENGINE_COLUMNS: tuple[str, ...] = ("Days_Since_Applied", "Folder")

DATE_COLUMNS: tuple[str, ...] = ("Applied_Date", "Deadline")

OPTIONS: dict[str, list[str]] = {
    "Work_Mode": list(WORK_MODE_VALUES.values()),
    "Employment_Type": list(EMPLOYMENT_TYPE_VALUES.values()),
    "Application_Status": ["Not Applied", "Applied", "Recruiter-Screening", "Technical Interview", "Final Round"],
    "Outcome": ["Pending", "Withdrawn", "Rejected", "Offer", "Accepted"],
    "Applied_Through": ["Org-Portal", "Indeed", "LinkedIn", "Email", "Workday", "Greenhouse", "AshbyHQ", "UltiPro", "Other"],
    "Found_From": ["HiringCafe", "LinkedIn", "Indeed", "GCJobs", "CRA", "Other"],
}

META = {
    "extracted_columns": list(EXTRACTED_COLUMNS),
    "manual_columns": list(MANUAL_COLUMNS),
    "engine_columns": list(ENGINE_COLUMNS),
    "date_columns": list(DATE_COLUMNS),
    "options": OPTIONS,
    "doc_types": list(DOC_TYPES),
    "upload_modes": ["single_document", "separate_uploads", "single_combined_file", "not_stated"],
}
