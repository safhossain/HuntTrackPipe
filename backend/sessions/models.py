"""Pydantic models for ``session.json`` (DESIGN.md section 4)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1

UploadMode = Literal["single_document", "separate_uploads", "single_combined_file", "not_stated"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Posting(BaseModel):
    text: str
    url: str | None = None
    hash: str | None = None  # posting_hash(text); None for sessions created before step 5


class JevDerived(BaseModel):
    schema_fields: list[str] = Field(default_factory=list)
    direct_values: dict[str, str] = Field(default_factory=dict)
    low_confidence_choices: list[str] = Field(default_factory=list)
    upload_mode: UploadMode = "not_stated"
    upload_mode_confidence: float | None = None
    required_docs: list[str] = Field(default_factory=list)
    is_job_posting: float | None = None
    warnings: list[str] = Field(default_factory=list)


class JevRecord(BaseModel):
    model: str
    at: str = Field(default_factory=utc_now)
    answers: dict[str, Any]
    usage: dict[str, Any] = Field(default_factory=dict)
    derived: JevDerived


class LLMRecord(BaseModel):
    model: str
    at: str = Field(default_factory=utc_now)
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")
    output: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class Review(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    written_at: str | None = None
    pending_write: dict[str, Any] | None = None
    # UI-only flag; not written to Excel. Marks Compensation as a user estimate.
    compensation_estimated: bool = False


class InputFile(BaseModel):
    index: int
    file: str
    doc_type: str | None = None
    original: str
    size: int | None = None
    pages: int | None = None
    added_at: str = Field(default_factory=utc_now)


class FinalFile(BaseModel):
    file: str
    doc_type: str
    from_index: int | None = Field(default=None, alias="from")
    at: str = Field(default_factory=utc_now)

    model_config = {"populate_by_name": True}


class CombinedFile(BaseModel):
    file: str
    from_indices: list[int]
    pages: int | None = None
    at: str = Field(default_factory=utc_now)


class Files(BaseModel):
    inputs: list[InputFile] = Field(default_factory=list)
    finals: list[FinalFile] = Field(default_factory=list)
    combined: CombinedFile | None = None


class Limit(BaseModel):
    unit: Literal["chars", "words"]
    value: int


class Question(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    text: str
    limit: Limit | None = None
    status: Literal["pending", "answered"] = "pending"
    answer: str | None = None
    feedback: str | None = None  # last revision feedback given to the model
    answered_at: str | None = None
    model: str | None = None  # model id, or "manual" when the user typed/edited the answer
    note: str | None = None  # engine remark, e.g. "still 12 chars over the limit after re-ask"
    created_at: str = Field(default_factory=utc_now)


class QA(BaseModel):
    questions: list[Question] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)  # cumulative input/output tokens
    last_answered_at: str | None = None


class Session(BaseModel):
    schema_version: int = SCHEMA_VERSION
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: str = Field(default_factory=utc_now)
    folder: str
    posting: Posting
    jev: JevRecord | None = None
    llm: LLMRecord | None = None
    review: Review = Field(default_factory=Review)
    upload_mode: UploadMode = "not_stated"
    upload_mode_source: Literal["jev", "user"] = "jev"
    files: Files = Field(default_factory=Files)
    qa: QA = Field(default_factory=QA)
    notes: str = ""  # free-text Notes tab; session.json only
