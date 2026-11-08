"""End-to-end steps shared by the CLI and (later) the API.

posting -> Jev -> derive -> schema -> LLM -> row values -> folder + session + Excel row
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .columns import ENGINE_COLUMNS, EXTRACTED_COLUMNS, MANUAL_COLUMNS, list_validation_options
from .config import Settings
from .duplicates import DuplicateError, find_duplicates, posting_hash
from .excel.tracker import Tracker, TrackerError, WriteReport
from .jev.client import JevClient
from .jev.derive import derive
from .jev.questions import (
    CHOICE_COLUMNS,
    EMPLOYMENT_TYPE_VALUES,
    EXISTENCE,
    QUESTIONS,
    ROLE_CATEGORY_VALUES,
)
from .llm.client import selected_client
from .llm.postprocess import row_values
from .llm.prompts import EXTRACTION_SYSTEM
from .llm.schema_builder import build_schema
from .naming import folder_name
from .sessions.models import JevDerived, JevRecord, LLMRecord, Posting, Review, Session, utc_now
from .sessions.store import SessionStore

log = logging.getLogger("htp.pipeline")

# First-pass Jev questions exclude role_category (classified after subroles exist).
PRIMARY_QUESTIONS = {k: v for k, v in QUESTIONS.items() if k != "role_category"}


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
        upload_mode="separate_uploads",
        warnings=["Jev skipped: all fields sent to the LLM."],
    )


def run_jev(posting_text: str, cfg: Settings) -> JevRecord:
    client = JevClient(cfg.jev)
    resp = client.ask(posting_text, PRIMARY_QUESTIONS)
    d = derive(resp.answers, cfg.jev)
    d.warnings = resp.warnings + d.warnings
    return JevRecord(model=resp.model, answers=resp.answers, usage=resp.usage, derived=d)


def run_llm(posting_text: str, derived: JevDerived, cfg: Settings) -> LLMRecord:
    schema = build_schema(derived)
    res = selected_client(cfg).structured(
        model=cfg.selected_llm.extract_model,
        system=EXTRACTION_SYSTEM,
        user=f"<job_posting>\n{posting_text}\n</job_posting>",
        schema=schema,
    )
    rec = LLMRecord(model=res.model, schema=schema, output=res.output, usage=res.usage)
    derived.warnings.extend(res.warnings)
    return rec


def classify_role_category(
    posting_text: str,
    cfg: Settings,
    *,
    subrole_categories: str | None = None,
) -> tuple[str, dict[str, Any], list[str]]:
    """Second Jev choice: map posting (+ optional subroles) to one of the Role_Category values.

    Always returns an Excel value (never blank). A valid Jev choice is kept even
    below ``choice_direct_confidence``; unknown/missing choice falls back to
    ``Other tech``.
    """
    warnings: list[str] = []
    client = JevClient(cfg.jev)
    state = {
        "posting": posting_text,
        "subrole_categories": (subrole_categories or "").strip(),
    }
    resp = client.ask(posting_text, {"role_category": QUESTIONS["role_category"]}, state=state)
    warnings.extend(resp.warnings)
    ans = resp.answers.get("role_category") or {}
    choice = ans.get("choice") if ans.get("type") == "choice" else None
    conf = ans.get("confidence")
    try:
        conf_f = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf_f = None
    if choice in ROLE_CATEGORY_VALUES:
        if conf_f is None or conf_f < cfg.jev.choice_direct_confidence:
            warnings.append(
                f"role_category choice={choice} conf={conf_f} below "
                f"{cfg.jev.choice_direct_confidence}; kept anyway."
            )
        return ROLE_CATEGORY_VALUES[choice], ans, warnings
    fallback = ROLE_CATEGORY_VALUES["other_tech"]
    if choice is not None:
        warnings.append(f"role_category unknown choice {choice!r}; using {fallback!r}.")
    else:
        warnings.append(f"role_category: no usable Jev choice; using {fallback!r}.")
    return fallback, ans, warnings


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

    if use_jev:
        role, ans, w = classify_role_category(
            posting_text, cfg, subrole_categories=ex.values.get("Subrole_Categories"),
        )
        if ex.jev is not None:
            ex.jev.answers = {**ex.jev.answers, "role_category": ans}
        ex.values["Role_Category"] = role
        ex.derived.warnings.extend(w)

    ex.warnings = list(ex.derived.warnings)
    return ex


# Location-only existence keys (used by the one-time location migration).
LOCATION_EXISTENCE: dict[str, str] = {
    "has_location_country": "location_country",
    "has_location_city": "location_city",
}


def _noul_prob(answers: dict[str, Any], key: str) -> float | None:
    a = answers.get(key)
    if not a or a.get("type") != "noul":
        return None
    try:
        return float(a["noul"])
    except (KeyError, TypeError, ValueError):
        return None


def extract_locations(posting_text: str, cfg: Settings) -> Extraction:
    """Jev + LLM for Location_Country / Location_City only (cheaper migration path)."""
    ex = Extraction()
    questions = {k: QUESTIONS[k] for k in LOCATION_EXISTENCE}
    client = JevClient(cfg.jev)
    resp = client.ask(posting_text, questions)
    d = JevDerived()
    for key, fld in LOCATION_EXISTENCE.items():
        p = _noul_prob(resp.answers, key)
        if p is None:
            d.warnings.append(f"Jev returned no answer for {key}; including {fld}.")
            d.schema_fields.append(fld)
        elif p >= cfg.jev.noul_include_threshold:
            d.schema_fields.append(fld)
    d.warnings = resp.warnings + d.warnings
    ex.jev = JevRecord(model=resp.model, answers=resp.answers, usage=resp.usage, derived=d)
    ex.derived = d

    llm_output: dict[str, Any] = {}
    if d.schema_fields:
        ex.llm = run_llm(posting_text, d, cfg)
        llm_output = ex.llm.output
    else:
        d.warnings.append("Jev gated out both location fields; LLM call skipped.")

    ex.values = row_values(d, llm_output)
    ex.warnings = list(d.warnings)
    return ex


def extract_employment_type(posting_text: str, cfg: Settings) -> Extraction:
    """Jev (+ LLM if low confidence) for Employment_Type only."""
    ex = Extraction()
    client = JevClient(cfg.jev)
    resp = client.ask(posting_text, {"employment_type": QUESTIONS["employment_type"]})
    d = JevDerived()
    ans = resp.answers.get("employment_type") or {}
    choice = ans.get("choice") if ans.get("type") == "choice" else None
    conf = ans.get("confidence")
    try:
        conf_f = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf_f = None
    if choice in EMPLOYMENT_TYPE_VALUES and conf_f is not None and conf_f >= cfg.jev.choice_direct_confidence:
        d.direct_values["Employment_Type"] = EMPLOYMENT_TYPE_VALUES[choice]
    else:
        d.low_confidence_choices.append("employment_type")
        if choice is not None and choice not in EMPLOYMENT_TYPE_VALUES:
            d.warnings.append(f"employment_type unknown choice {choice!r}; sending to LLM.")
    d.warnings = resp.warnings + d.warnings
    ex.jev = JevRecord(model=resp.model, answers=resp.answers, usage=resp.usage, derived=d)
    ex.derived = d

    llm_output: dict[str, Any] = {}
    if d.low_confidence_choices:
        ex.llm = run_llm(posting_text, d, cfg)
        llm_output = ex.llm.output

    ex.values = row_values(d, llm_output)
    ex.warnings = list(d.warnings)
    return ex


def create_application(
    cfg: Settings,
    *,
    posting_text: str,
    posting_url: str | None,
    extraction: Extraction,
    manual: dict[str, Any] | None = None,
    date_created: date | None = None,
    allow_duplicate: bool = False,
    compensation_estimated: bool = False,
) -> tuple[Session, WriteReport]:
    """Create the folder + session.json, then write the Excel row.

    Order matters: the Excel lock is checked first so a locked workbook does not
    leave an orphan folder behind. Raises ``DuplicateError`` when the posting
    matches an existing session unless ``allow_duplicate``.
    """
    store = SessionStore(cfg.applications_abs)
    tracker = Tracker(cfg.tracker_abs, backups_keep=cfg.backups_keep)
    tracker.check_writable()

    today = date_created or date.today()
    vals = dict(extraction.values)
    if not allow_duplicate:
        hits = find_duplicates(cfg, posting_text, vals)
        if hits:
            log.info("duplicate posting refused: %s", [h.model_dump() for h in hits])
            raise DuplicateError(hits)
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
    upload_mode = extraction.derived.upload_mode
    if upload_mode == "not_stated":
        upload_mode = "separate_uploads"
    session = Session(
        folder=name,
        posting=Posting(text=posting_text, url=posting_url, hash=posting_hash(posting_text)),
        jev=extraction.jev,
        llm=extraction.llm,
        review=Review(values=row, compensation_estimated=bool(compensation_estimated)),
        upload_mode=upload_mode,
    )
    store.create(session)
    log.info("created %s (jev=%s llm=%s)", name, bool(extraction.jev), bool(extraction.llm))

    try:
        report = tracker.write_row(name, row, list_options=list_validation_options(cfg))
    except Exception:
        session.review.pending_write = {"values": row, "force_columns": []}
        store.save(session)
        raise
    session.review.written_at = utc_now()
    store.save(session)
    return session, report


def duplicate_application(
    cfg: Settings,
    source: Session,
    *,
    values: dict[str, Any] | None = None,
    date_created: date | None = None,
) -> tuple[Session, WriteReport]:
    """Clone an application into a new folder (today's date in the name).

    Copies posting text, Jev/LLM records, and upload mode. Files and Q&A start
    empty. ``values`` overrides tracker columns *before* the folder is named, so
    a new Requisition_ID lands in the folder name. Always allows a duplicate
    posting hash (this is an intentional second application).
    """
    tracker = Tracker(cfg.tracker_abs, backups_keep=cfg.backups_keep)
    base: dict[str, Any] = {}
    try:
        row = tracker.read_row(source.folder)
        if row:
            base = dict(row)
    except (TrackerError, OSError):
        base = {}
    if not base:
        base = dict(source.review.values)

    for col in ENGINE_COLUMNS:
        base.pop(col, None)
    base.pop("Folder", None)

    overrides = values or {}
    unknown = [k for k in overrides if k not in EXTRACTED_COLUMNS and k not in MANUAL_COLUMNS]
    if unknown:
        raise ValueError(f"Not a tracker column: {unknown}")
    merged = {**base, **overrides}

    extracted = {k: merged[k] for k in EXTRACTED_COLUMNS if k in merged}
    manual = {k: merged[k] for k in MANUAL_COLUMNS if k in merged}

    if source.jev is not None:
        derived = source.jev.derived.model_copy(deep=True)
    else:
        derived = JevDerived()
    derived.upload_mode = source.upload_mode if source.upload_mode != "not_stated" else "separate_uploads"

    ex = Extraction(
        jev=source.jev,
        llm=source.llm,
        derived=derived,
        values=extracted,
    )
    posting_url = manual.get("Posting_URL") or source.posting.url

    session, report = create_application(
        cfg,
        posting_text=source.posting.text,
        posting_url=posting_url if isinstance(posting_url, str) else None,
        extraction=ex,
        manual=manual,
        date_created=date_created or date.today(),
        allow_duplicate=True,
        compensation_estimated=source.review.compensation_estimated,
    )
    store = SessionStore(cfg.applications_abs)
    changed = False
    if source.upload_mode_source == "user":
        session.upload_mode = source.upload_mode if source.upload_mode != "not_stated" else "separate_uploads"
        session.upload_mode_source = "user"
        changed = True
    if source.notes:
        session.notes = source.notes
        changed = True
    if changed:
        store.save(session)
    log.info("duplicated %s -> %s", source.folder, session.folder)
    return session, report
