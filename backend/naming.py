"""Folder and file naming rules (DESIGN.md section 8).

Folder:   {Requisition_ID}_{Organization}_{Position_Title}_{Date_Created}
X token:  Requisition_ID | {Organization}_{Position_Title} | Organization | Position_Title | Date_Created
Inputs:   {count}_<original-name>.<ext>
Finals:   {Candidate_Name}_{DocType}_{X}.<ext>
Combined: {Candidate_Name}_{X}.pdf
"""
from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Iterable
from datetime import date

NULL = "null"
COMPONENT_MAX = 60
PATH_MAX = 200

DOC_TYPES = ("Resume", "CoverLetter", "Transcript", "Portfolio", "References", "Other")

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTI_DASH = re.compile(r"-{2,}")
_WS = re.compile(r"\s+")


def sanitize(value: str | None, max_len: int = COMPONENT_MAX) -> str | None:
    """Make a string safe for a Windows path component. Returns None if nothing is left."""
    if value is None:
        return None
    s = unicodedata.normalize("NFKC", str(value)).strip()
    s = _ILLEGAL.sub("", s)
    s = _WS.sub("-", s)
    s = _MULTI_DASH.sub("-", s)
    s = s.strip("-. ")
    if not s:
        return None
    if len(s) > max_len:
        s = s[:max_len].rstrip("-. ")
    return s or None


def _or_null(value: str | None) -> str:
    return sanitize(value) or NULL


def folder_base_name(
    requisition_id: str | None,
    organization: str | None,
    position_title: str | None,
    date_created: date,
    *,
    now_ts: int | None = None,
) -> str:
    """Folder name before collision handling."""
    req, org, title = _or_null(requisition_id), _or_null(organization), _or_null(position_title)
    name = f"{req}_{org}_{title}_{date_created.isoformat()}"
    if req == org == title == NULL:
        name += f"_{now_ts if now_ts is not None else int(time.time())}"
    return name


def resolve_collision(name: str, existing: Iterable[str]) -> str:
    """Append _2, _3, ... until ``name`` is not in ``existing`` (case-insensitive)."""
    taken = {e.lower() for e in existing}
    if name.lower() not in taken:
        return name
    n = 2
    while f"{name}_{n}".lower() in taken:
        n += 1
    return f"{name}_{n}"


def folder_name(
    requisition_id: str | None,
    organization: str | None,
    position_title: str | None,
    date_created: date,
    existing: Iterable[str] = (),
    *,
    base_path_len: int = 0,
    now_ts: int | None = None,
) -> str:
    """Final folder name: base name, trimmed to the path budget, then de-duplicated."""
    name = folder_base_name(requisition_id, organization, position_title, date_created, now_ts=now_ts)
    budget = PATH_MAX - base_path_len - 1
    if len(name) > budget > 0:
        # Trim the title component first (it is the longest in practice).
        req, org, title = _or_null(requisition_id), _or_null(organization), _or_null(position_title)
        fixed = len(f"{req}_{org}__{date_created.isoformat()}")
        title = title[: max(1, budget - fixed)].rstrip("-. ") or NULL
        name = f"{req}_{org}_{title}_{date_created.isoformat()}"
    return resolve_collision(name, existing)


def x_token(
    requisition_id: str | None,
    organization: str | None,
    position_title: str | None,
    date_created: date,
) -> str:
    """The {X} part of final/combined file names, by priority."""
    req, org, title = sanitize(requisition_id), sanitize(organization), sanitize(position_title)
    if req:
        return req
    if org and title:
        return f"{org}_{title}"
    if org:
        return org
    if title:
        return title
    return date_created.isoformat()


def candidate_token(candidate_name: str) -> str:
    return sanitize(candidate_name) or "Candidate"


def input_file_name(index: int, original_name: str) -> str:
    stem, dot, ext = original_name.rpartition(".")
    if not dot:
        stem, ext = original_name, ""
    safe_stem = sanitize(stem) or "file"
    safe_ext = sanitize(ext.lower()) if ext else None
    return f"{index}_{safe_stem}" + (f".{safe_ext}" if safe_ext else "")


def final_file_name(candidate_name: str, doc_type: str, x: str, ext: str) -> str:
    if doc_type not in DOC_TYPES:
        raise ValueError(f"doc_type must be one of {DOC_TYPES}, got {doc_type!r}")
    return f"{candidate_token(candidate_name)}_{doc_type}_{x}.{ext.lstrip('.').lower()}"


def combined_file_name(candidate_name: str, x: str) -> str:
    return f"{candidate_token(candidate_name)}_{x}.pdf"
