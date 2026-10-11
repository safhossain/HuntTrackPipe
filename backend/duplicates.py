"""Duplicate-posting detection (DESIGN.md section 15).

Two signals, both cheap and local:
* the normalised posting text hashes to the same value as an existing session's posting;
* the extracted Requisition_ID (+ Organization when both have one) matches an existing session.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from pydantic import BaseModel

from .config import Settings
from .sessions.store import SessionStore

_WS = re.compile(r"\s+")


class DuplicateHit(BaseModel):
    folder: str
    reason: str  # "same posting text" | "same requisition id" | ...


class DuplicateError(ValueError):
    def __init__(self, hits: list[DuplicateHit]):
        self.hits = hits
        folders = ", ".join(h.folder for h in hits)
        super().__init__(f"This posting looks like an existing application: {folders}. Create anyway to proceed.")


def posting_hash(text: str) -> str:
    norm = _WS.sub(" ", text).strip().lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _s(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    return s or None


def find_duplicates(cfg: Settings, posting_text: str, values: dict[str, Any] | None = None) -> list[DuplicateHit]:
    """Compare against every managed session (posting.txt hash + review values)."""
    store = SessionStore(cfg.applications_abs)
    h = posting_hash(posting_text)
    req = _s((values or {}).get("Requisition_ID"))
    org = _s((values or {}).get("Organization"))
    hits: list[DuplicateHit] = []
    for s in store.list_sessions():
        reasons: list[str] = []
        if (s.posting.hash or posting_hash(s.posting.text)) == h:
            reasons.append("same posting text")
        if req:
            s_req = _s(s.review.values.get("Requisition_ID"))
            s_org = _s(s.review.values.get("Organization"))
            if s_req == req and (not org or not s_org or s_org == org):
                reasons.append("same requisition id")
        if reasons:
            hits.append(DuplicateHit(folder=s.folder, reason=" + ".join(reasons)))
    return hits
