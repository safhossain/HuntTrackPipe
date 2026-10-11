"""Pydantic request / response models for the API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..sessions.models import JevDerived, JevRecord, LLMRecord, Session


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


class SettingsResponse(BaseModel):
    config: dict[str, Any]
    paths: dict[str, str]
    keys: dict[str, bool]
    tracker_exists: bool
    candidate_context_exists: bool
