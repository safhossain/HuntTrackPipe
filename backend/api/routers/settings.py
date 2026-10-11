from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from ...columns import META
from ...config import CONFIG_PATH, Settings, settings
from ...logs import log_path, setup_logging, tail
from ..deps import get_settings
from ..models import LogsResponse, SettingsResponse, SettingsUpdate

router = APIRouter(tags=["settings"])
log = logging.getLogger("htp.api")
KEYS = ("TYPESAFE_API_KEY", "ANTHROPIC_API_KEY")


@router.get("/meta")
def meta() -> dict:
    return META


def _view(cfg: Settings) -> SettingsResponse:
    return SettingsResponse(
        config=config_json(cfg),
        paths={
            "applications_dir": str(cfg.applications_abs),
            "tracker_path": str(cfg.tracker_abs),
            "candidate_context_path": str(cfg.candidate_context_abs),
            "config_path": str(CONFIG_PATH),
            "log_path": str(log_path(cfg)),
        },
        keys={k: bool(os.environ.get(k)) for k in KEYS},
        tracker_exists=cfg.tracker_abs.exists(),
        candidate_context_exists=cfg.candidate_context_abs.exists(),
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings_view() -> SettingsResponse:
    return _view(get_settings())


def config_json(cfg: Settings) -> dict[str, Any]:
    """``Settings`` as it is written to htp.config.json (paths with forward slashes)."""
    data = cfg.model_dump(mode="json")
    for key in ("applications_dir", "tracker_path", "candidate_context_path"):
        data[key] = Path(data[key]).as_posix()
    return data


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def apply_settings_update(patch: dict[str, Any], path: Path = CONFIG_PATH) -> Settings:
    current = config_json(settings())
    merged = deep_merge(current, patch)
    try:
        cfg = Settings.model_validate(merged)
    except ValidationError as exc:
        errors = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        raise HTTPException(400, f"Invalid settings: {errors}")
    path.write_text(json.dumps(config_json(cfg), indent=2) + "\n", encoding="utf-8")
    settings.cache_clear()
    cfg = settings()
    setup_logging(cfg)  # follow the applications dir if it moved
    log.info("settings updated: %s", sorted(patch))
    return cfg


@router.put("/settings", response_model=SettingsResponse)
def update_settings(req: SettingsUpdate) -> SettingsResponse:
    return _view(apply_settings_update(req.config))


@router.get("/logs", response_model=LogsResponse)
def get_logs(lines: int = Query(200, ge=1, le=2000)) -> LogsResponse:
    cfg = get_settings()
    return LogsResponse(path=str(log_path(cfg)), lines=tail(cfg, lines))
