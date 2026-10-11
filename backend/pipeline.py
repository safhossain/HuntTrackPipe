"""End-to-end steps shared by the CLI and (later) the API.

posting -> Jev -> derive -> schema -> Claude -> row values -> folder + session + Excel row
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .config import Settings
from .excel.tracker import Tracker, WriteReport
from .jev.client import JevClient
from .jev.derive import derive
from .jev.questions import CHOICE_COLUMNS, EXISTENCE, QUESTIONS
from .llm.client import ClaudeClient
from .llm.postprocess import row_values
from .llm.prompts import EXTRACTION_SYSTEM
from .llm.schema_builder import build_schema
from .naming import folder_name
from .sessions.models import JevDerived, JevRecord, LLMRecord, Posting, Review, Session, utc_now
from .sessions.store import SessionStore

MANUAL_COLUMNS = ("Applied_Date", "Posting_URL", "Application_Status", "Applied_Through", "Confirmation_#")


@dataclass
class Extraction:
    jev: JevRecord | None = None
    llm: LLMRecord | None = None
    derived: JevDerived = field(default_factory=JevDerived)
    values: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def derived_without_jev() -> JevDerived:
    """Fallback when Jev is skipped: ask the LLM for everything."""
    return JevDerived(
        schema_fields=list(EXISTENCE.values()),
        low_confidence_choices=[fld for _, fld, _ in CHOICE_COLUMNS.values()],
        warnings=["Jev skipped: all fields sent to the LLM."],
    )


def run_jev(posting_text: str, cfg: Settings) -> JevRecord:
    client = JevClient(cfg.jev)
    resp = client.ask(posting_text, QUESTIONS)
    d = derive(resp.answers, cfg.jev)
    d.warnings = resp.warnings + d.warnings
    return JevRecord(model=resp.model, answers=resp.answers, usage=resp.usage, derived=d)


def run_llm(posting_text: str, derived: JevDerived, cfg: Settings) -> LLMRecord:
    schema = build_schema(derived)
    client = ClaudeClient(cfg.llm)
    res = client.structured(
        model=cfg.llm.extract_model,
        system=EXTRACTION_SYSTEM,
        user=f"<job_posting>\n{posting_text}\n</job_posting>",
        schema=schema,
    )
    rec = LLMRecord(model=res.model, schema=schema, output=res.output, usage=res.usage)
    derived.warnings.extend(res.warnings)
    return rec


def extract(posting_text: str, cfg: Settings, *, use_jev: bool = True, use_llm: bool = True) -> Extraction:
    ex = Extraction()
    if use_jev:
        ex.jev = run_jev(posting_text, cfg)
        ex.derived = ex.jev.derived
    else:
        ex.derived = derived_without_jev()

    llm_output: dict[str, Any] = {}
    needs_llm = bool(ex.derived.schema_fields or ex.derived.low_confidence_choices)
    if use_llm and needs_llm:
        ex.llm = run_llm(posting_text, ex.derived, cfg)
        llm_output = ex.llm.output
    elif use_llm and not needs_llm:
        ex.derived.warnings.append("Jev gated out every field; LLM call skipped.")

    ex.values = row_values(ex.derived, llm_output)
    ex.warnings = list(ex.derived.warnings)
    return ex


def create_application(
    cfg: Settings,
    *,
    posting_text: str,
    posting_url: str | None,
    extraction: Extraction,
    manual: dict[str, Any] | None = None,
    date_created: date | None = None,
) -> tuple[Session, WriteReport]:
    """Create the folder + session.json, then write the Excel row.

    Order matters: the Excel lock is checked first so a locked workbook does not
    leave an orphan folder behind.
    """
    store = SessionStore(cfg.applications_abs)
    tracker = Tracker(cfg.tracker_abs, backups_keep=cfg.backups_keep)
    tracker.check_writable()

    today = date_created or date.today()
    vals = dict(extraction.values)
    manual = {k: v for k, v in (manual or {}).items() if v not in (None, "")}
    unknown = [k for k in manual if k not in MANUAL_COLUMNS]
    if unknown:
        raise ValueError(f"Not a manual column: {unknown}")
    if posting_url and "Posting_URL" not in manual:
        manual["Posting_URL"] = posting_url

    name = folder_name(
        vals.get("Requisition_ID"),
        vals.get("Organization"),
        vals.get("Position_Title"),
        today,
        existing=store.existing_folder_names(),
        base_path_len=len(str(store.root)),
    )

    row = {**vals, **manual}
    session = Session(
        folder=name,
        posting=Posting(text=posting_text, url=posting_url),
        jev=extraction.jev,
        llm=extraction.llm,
        review=Review(values=row),
        upload_mode=extraction.derived.upload_mode,
    )
    store.create(session)

    try:
        report = tracker.write_row(name, row)
    except Exception:
        session.review.pending_write = row
        store.save(session)
        raise
    session.review.written_at = utc_now()
    store.save(session)
    return session, report
