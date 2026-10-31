"""Settings: ``htp.config.json`` (non-secret) + ``.env`` (API keys).

All relative paths in the config are resolved against the repo root (the parent
of this ``backend`` package).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
# Override with HTP_CONFIG=<path> (e.g. to point at a scratch Applications dir).
CONFIG_PATH = Path(os.environ.get("HTP_CONFIG", REPO_ROOT / "htp.config.json"))


class JevSettings(BaseModel):
    model: str = "jev-1.13.0"
    base_url: str = "https://api.typesafe.ai"
    noul_include_threshold: float = 0.35
    choice_direct_confidence: float = 0.7
    doc_noul_threshold: float = 0.5
    job_posting_warn_below: float = 0.5
    timeout_s: float = 30.0
    max_attempts: int = 3


class LLMSettings(BaseModel):
    extract_model: str = "claude-haiku-5-5"
    qa_model: str = "claude-haiku-5-5"
    effort: str = "low"
    max_tokens: int = 2048
    token_warn: int = 80_000


class FileSettings(BaseModel):
    image_dpi: int = 150
    soffice_path: str | None = None


class Settings(BaseModel):
    applications_dir: Path = Path("JobHunting/Applications")
    tracker_path: Path = Path("JobHunting/Applications/job_application_tracker.xlsx")
    candidate_name: str = "Candidate Name"
    candidate_context_path: Path = Path("JobHunting/candidate_context.txt")
    jev: JevSettings = Field(default_factory=JevSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    files: FileSettings = Field(default_factory=FileSettings)
    backups_keep: int = 10
    # Editable dropdown lists (Application_Status, Applied_Through, Found_From).
    # Absent keys fall back to shipped defaults in columns.DEFAULT_OPTIONS.
    options: dict[str, list[str]] = Field(default_factory=dict)

    def _abs(self, p: Path) -> Path:
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()

    @property
    def applications_abs(self) -> Path:
        return self._abs(self.applications_dir)

    @property
    def tracker_abs(self) -> Path:
        return self._abs(self.tracker_path)

    @property
    def candidate_context_abs(self) -> Path:
        return self._abs(self.candidate_context_path)


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    load_dotenv(REPO_ROOT / ".env")
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8-sig"))  # tolerate BOM from Windows editors
        return Settings.model_validate(data)
    return Settings()


@lru_cache(maxsize=1)
def settings() -> Settings:
    return load_settings()


def api_key(name: str) -> str:
    """Return an API key from the environment or raise a readable error."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set. Add it to {REPO_ROOT / '.env'}.")
    return value
