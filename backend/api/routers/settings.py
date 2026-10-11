from __future__ import annotations

import os

from fastapi import APIRouter

from ...columns import META
from ..deps import get_settings
from ..models import SettingsResponse

router = APIRouter(tags=["settings"])


@router.get("/meta")
def meta() -> dict:
    return META


@router.get("/settings", response_model=SettingsResponse)
def get_settings_view() -> SettingsResponse:
    cfg = get_settings()
    return SettingsResponse(
        config=cfg.model_dump(mode="json"),
        paths={
            "applications_dir": str(cfg.applications_abs),
            "tracker_path": str(cfg.tracker_abs),
            "candidate_context_path": str(cfg.candidate_context_abs),
        },
        keys={k: bool(os.environ.get(k)) for k in ("TYPESAFE_API_KEY", "ANTHROPIC_API_KEY")},
        tracker_exists=cfg.tracker_abs.exists(),
        candidate_context_exists=cfg.candidate_context_abs.exists(),
    )
