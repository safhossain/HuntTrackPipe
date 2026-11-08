from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from ...columns import EXTRACTED_COLUMNS, list_validation_options
from ...duplicates import posting_hash
from ...excel.tracker import TrackerError, TrackerLocked
from ...pipeline import Extraction, create_application, duplicate_application, extract
from ...sessions.models import Posting, utc_now
from ..deps import coerce_row_values, get_settings, get_store, get_tracker, report_model
from ..models import (
    CreateSessionRequest,
    CreateSessionResponse,
    DiffEntry,
    DuplicateSessionRequest,
    ExtractResponse,
    PostingText,
    ReextractRequest,
    ReextractResponse,
    RowWriteRequest,
    RowWriteResponse,
    SessionDetail,
    NotesRequest,
    NotesResponse,
    SessionFlagsRequest,
    SessionFlagsResponse,
    SessionListResponse,
    SessionSummary,
)

log = logging.getLogger("htp.api")

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _rows_by_folder() -> tuple[dict[str, dict[str, Any]], str | None]:
    try:
        rows = get_tracker().read_all()
    except (TrackerError, OSError) as exc:
        return {}, str(exc)
    return {str(r.get("Folder")): r for r in rows if r.get("Folder")}, None


@router.get("", response_model=SessionListResponse)
def list_sessions() -> SessionListResponse:
    store = get_store()
    rows, err = _rows_by_folder()
    sessions = [
        SessionSummary(
            folder=s.folder,
            created_at=s.created_at,
            upload_mode=s.upload_mode,
            pending_write=s.review.pending_write is not None,
            row=rows.get(s.folder),
        )
        for s in store.list_sessions()
    ]
    return SessionListResponse(sessions=sessions, unmanaged=store.unmanaged_folders(), tracker_error=err)


@router.post("", response_model=CreateSessionResponse)
def create_session(req: CreateSessionRequest) -> CreateSessionResponse:
    text = req.posting_text.strip()
    if not text:
        raise HTTPException(400, "Posting text is empty.")
    ex = Extraction(
        jev=req.extraction.jev,
        llm=req.extraction.llm,
        derived=req.extraction.derived,
        values=coerce_row_values(req.extraction.values),
        warnings=req.extraction.warnings,
    )
    session, report = create_application(
        get_settings(),
        posting_text=text,
        posting_url=(req.posting_url or "").strip() or None,
        extraction=ex,
        manual=coerce_row_values(req.manual),
        allow_duplicate=req.allow_duplicate,
        compensation_estimated=req.compensation_estimated,
    )
    return CreateSessionResponse(session=session, report=report_model(report))


def _load_or_404(folder: str):
    store = get_store()
    try:
        return store, store.load(folder)
    except FileNotFoundError:
        raise HTTPException(404, f"No session for folder {folder!r}")


@router.get("/{folder}", response_model=SessionDetail)
def get_session(folder: str) -> SessionDetail:
    _, session = _load_or_404(folder)
    row, err = None, None
    try:
        row = get_tracker().read_row(folder)
    except (TrackerError, OSError) as exc:
        err = str(exc)
    return SessionDetail(session=session, row=row, row_error=err)


@router.post("/{folder}/duplicate", response_model=CreateSessionResponse)
def duplicate_session(folder: str, req: DuplicateSessionRequest) -> CreateSessionResponse:
    """Clone this application into a new folder dated today.

    Copies posting + Jev/LLM; files and Q&A start empty. Pass ``values`` to
    change identifying fields (e.g. Requisition_ID) before the folder is named.
    """
    _, source = _load_or_404(folder)
    session, report = duplicate_application(
        get_settings(),
        source,
        values=coerce_row_values(req.values),
    )
    return CreateSessionResponse(session=session, report=report_model(report))


@router.put("/{folder}/flags", response_model=SessionFlagsResponse)
def put_session_flags(folder: str, req: SessionFlagsRequest) -> SessionFlagsResponse:
    """Persist UI-only session flags (not Excel columns), e.g. Compensation Estimated."""
    store, session = _load_or_404(folder)
    if req.compensation_estimated is not None:
        session.review.compensation_estimated = req.compensation_estimated
    store.save(session)
    return SessionFlagsResponse(compensation_estimated=session.review.compensation_estimated)


@router.put("/{folder}/notes", response_model=NotesResponse)
def put_session_notes(folder: str, req: NotesRequest) -> NotesResponse:
    """Free-text Notes tab body (session.json only)."""
    store, session = _load_or_404(folder)
    session.notes = req.notes
    store.save(session)
    return NotesResponse(notes=session.notes)


@router.put("/{folder}/posting", response_model=Posting)
def put_session_posting(folder: str, req: PostingText) -> Posting:
    if not req.text.strip():
        raise HTTPException(400, "Posting text is empty.")
    return get_store().update_posting(folder, req.text, posting_hash(req.text))


@router.put("/{folder}/row", response_model=RowWriteResponse)
def write_row(folder: str, req: RowWriteRequest) -> RowWriteResponse:
    """Write edited cells. Columns in ``force_columns`` overwrite existing values;
    everything else is fill-only-empty."""
    store, session = _load_or_404(folder)
    values = coerce_row_values(req.values)
    tracker = get_tracker()
    lists = list_validation_options(get_settings())
    try:
        report = tracker.write_row(folder, values, force_columns=set(req.force_columns), list_options=lists)
    except TrackerLocked:
        prev = session.review.pending_write or {"values": {}, "force_columns": []}
        session.review.pending_write = {
            "values": {**prev.get("values", {}), **req.values},
            "force_columns": sorted(set(prev.get("force_columns", [])) | set(req.force_columns)),
        }
        store.save(session)
        raise
    session.review.values.update({k: v for k, v in values.items() if v is not None})
    session.review.pending_write = None
    session.review.written_at = utc_now()
    store.save(session)
    return RowWriteResponse(report=report_model(report), row=tracker.read_row(folder))


def _norm(v: Any) -> Any:
    """Comparable form of a cell / extracted value (dates -> ISO, blanks -> None)."""
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def row_diff(current: dict[str, Any] | None, proposed: dict[str, Any]) -> list[DiffEntry]:
    """Per-column comparison for every extracted column (never manual/engine ones)."""
    current = current or {}
    out: list[DiffEntry] = []
    for col in EXTRACTED_COLUMNS:
        cur, new = _norm(current.get(col)), _norm(proposed.get(col))
        out.append(DiffEntry(column=col, current=cur, proposed=new, changed=cur != new))
    return out


@router.post("/{folder}/reextract", response_model=ReextractResponse)
def reextract(folder: str, req: ReextractRequest) -> ReextractResponse:
    """Run Jev/LLM again on the stored posting and return a per-column diff
    against the Excel row. Nothing is written; the UI applies chosen columns
    through ``PUT /row`` with ``force_columns``. The new Jev/LLM records replace
    the ones in session.json so the Log tab shows the latest run."""
    store, session = _load_or_404(folder)
    cfg = get_settings()
    ex = extract(session.posting.text, cfg, use_jev=req.use_jev, use_llm=req.use_llm)
    row = None
    try:
        row = get_tracker().read_row(folder)
    except (TrackerError, OSError) as exc:
        log.warning("reextract %s: tracker unreadable (%s); diffing against session values", folder, exc)
    baseline = row if row is not None else session.review.values
    if ex.jev is not None:
        session.jev = ex.jev
    if ex.llm is not None:
        session.llm = ex.llm
    store.save(session)
    diff = row_diff(baseline, ex.values)
    log.info("reextract %s: %d column(s) differ", folder, sum(d.changed for d in diff))
    return ReextractResponse(
        extraction=ExtractResponse(jev=ex.jev, llm=ex.llm, derived=ex.derived, values=ex.values, warnings=ex.warnings),
        row=row,
        diff=diff,
    )


@router.post("/{folder}/row/retry", response_model=RowWriteResponse)
def retry_pending(folder: str) -> RowWriteResponse:
    store, session = _load_or_404(folder)
    pending = session.review.pending_write
    if not pending:
        raise HTTPException(400, "Nothing pending for this session.")
    tracker = get_tracker()
    values = coerce_row_values(pending.get("values", {}))
    report = tracker.write_row(
        folder,
        values,
        force_columns=set(pending.get("force_columns", [])),
        list_options=list_validation_options(get_settings()),
    )
    session.review.values.update({k: v for k, v in values.items() if v is not None})
    session.review.pending_write = None
    session.review.written_at = utc_now()
    store.save(session)
    return RowWriteResponse(report=report_model(report), row=tracker.read_row(folder))
