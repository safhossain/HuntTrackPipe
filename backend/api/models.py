"""Pydantic request / response models for the API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..duplicates import DuplicateHit
from ..sessions.models import QA, Files, JevDerived, JevRecord, LLMRecord, Limit, Session, UploadMode


class ExtractRequest(BaseModel):
    posting_text: str
    use_jev: bool = True
    use_llm: bool = True


class ExtractResponse(BaseModel):
    jev: JevRecord | None = None
    llm: LLMRecord | None = None
    derived: JevDerived = Field(default_factory=JevDerived)
    values: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    duplicates: list[DuplicateHit] = Field(default_factory=list)


class ReextractRequest(BaseModel):
    use_jev: bool = True
    use_llm: bool = True


class DiffEntry(BaseModel):
    column: str
    current: Any = None
    proposed: Any = None
    changed: bool


class ReextractResponse(BaseModel):
    extraction: ExtractResponse
    row: dict[str, Any] | None = None
    diff: list[DiffEntry]


class SettingsUpdate(BaseModel):
    """Partial ``htp.config.json`` update; nested dicts are merged key by key."""

    config: dict[str, Any]


class AddOptionRequest(BaseModel):
    value: str


class AddOptionResponse(BaseModel):
    column: str
    value: str
    options: dict[str, list[str]]
    excel_synced: bool = True
    excel_error: str | None = None


class DropdownColumnDiffModel(BaseModel):
    column: str
    htp: list[str]
    excel: list[str] | None = None
    changed: bool


class DropdownSyncStatusModel(BaseModel):
    status: str  # in_sync | mismatched | locked | missing | error
    columns: list[DropdownColumnDiffModel] = Field(default_factory=list)
    checked_at: str | None = None
    tracker_mtime: float | None = None
    detail: str | None = None


class TrackerStatusResponse(BaseModel):
    locked: bool
    lock_source: str | None = None
    owner_file: str | None = None
    tracker_path: str
    changed_at: str | None = None
    watching: bool = False
    dropdown_sync: DropdownSyncStatusModel
    suggest_sync: bool = False
    claude_credit_low: bool
    openai_credit_low: bool


class LogsResponse(BaseModel):
    path: str
    lines: list[str]


class WriteReportModel(BaseModel):
    row: int
    created: bool
    written: dict[str, Any] = Field(default_factory=dict)
    skipped: dict[str, list[Any]] = Field(default_factory=dict)  # column -> [existing, attempted]


class CreateSessionRequest(BaseModel):
    posting_text: str
    posting_url: str | None = None
    extraction: ExtractResponse
    manual: dict[str, Any] = Field(default_factory=dict)
    allow_duplicate: bool = False
    compensation_estimated: bool = False


class DuplicateSessionRequest(BaseModel):
    """Optional tracker-column overrides applied before the new folder is named."""

    values: dict[str, Any] = Field(default_factory=dict)


class SessionFlagsRequest(BaseModel):
    compensation_estimated: bool | None = None


class SessionFlagsResponse(BaseModel):
    compensation_estimated: bool


class NotesRequest(BaseModel):
    notes: str = ""


class NotesResponse(BaseModel):
    notes: str


class PostingText(BaseModel):
    text: str


class SessionDetail(BaseModel):
    session: Session
    row: dict[str, Any] | None = None
    row_error: str | None = None


class CreateSessionResponse(BaseModel):
    session: Session
    report: WriteReportModel


class SessionSummary(BaseModel):
    folder: str
    created_at: str
    upload_mode: str
    pending_write: bool = False
    row: dict[str, Any] | None = None


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]
    unmanaged: list[str] = Field(default_factory=list)
    tracker_error: str | None = None


class RowWriteRequest(BaseModel):
    values: dict[str, Any]
    force_columns: list[str] = Field(default_factory=list)


class RowWriteResponse(BaseModel):
    report: WriteReportModel
    row: dict[str, Any] | None = None


class FilesView(BaseModel):
    files: Files
    upload_mode: str
    upload_mode_source: str
    required_docs: list[str] = Field(default_factory=list)
    untracked: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    x: str
    candidate: str
    tools: dict[str, Any] = Field(default_factory=dict)


class OrderRequest(BaseModel):
    order: list[int]


class DocTypeRequest(BaseModel):
    doc_type: str | None = None


class IndicesRequest(BaseModel):
    indices: list[int] | None = None


class ConvertRequest(BaseModel):
    target: str


class NameRequest(BaseModel):
    name: str


class UploadModeRequest(BaseModel):
    upload_mode: UploadMode


class QAView(BaseModel):
    qa: QA
    candidate_context_exists: bool
    candidate_context_path: str
    answers_md: str | None = None  # file name when it exists
    organization: str | None = None
    title: str | None = None
    warnings: list[str] = Field(default_factory=list)


class QuestionCreate(BaseModel):
    text: str
    limit: Limit | None = None


class QuestionsCreate(BaseModel):
    questions: list[QuestionCreate]


class QuestionUpdate(BaseModel):
    text: str | None = None
    limit: Limit | None = None
    clear_limit: bool = False
    answer: str | None = None  # manual answer edit


class AnswerRequest(BaseModel):
    ids: list[str] | None = None  # default: every pending question


class RegenerateRequest(BaseModel):
    feedback: str | None = None


class QuestionOrderRequest(BaseModel):
    order: list[str]


class SettingsResponse(BaseModel):
    config: dict[str, Any]
    paths: dict[str, str]
    keys: dict[str, bool]
    tracker_exists: bool
    candidate_context_exists: bool
    tracker_status: TrackerStatusResponse | None = None
