from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from ...columns import EDITABLE_OPTION_COLUMNS, list_validation_options, meta_payload, resolved_options
from ...config import CONFIG_PATH, Settings, settings
from ...excel.dropdown_sync import dropdown_cache, sync_dropdowns_to_excel
from ...excel.lock_watch import lock_watch
from ...excel.status import tracker_status_dict
from ...excel.tracker import Tracker, TrackerError, TrackerLocked
from ...logs import log_path, setup_logging, tail
from ..deps import get_settings
from ..models import (
    AddOptionRequest,
    AddOptionResponse,
    LogsResponse,
    SettingsResponse,
    SettingsUpdate,
    TrackerStatusResponse,
)

router = APIRouter(tags=["settings"])
log = logging.getLogger("htp.api")
KEYS = ("TYPESAFE_API_KEY", "ANTHROPIC_API_KEY")


@router.get("/meta")
def meta() -> dict:
    return meta_payload(get_settings())


def _tracker_status(cfg: Settings, *, force_compare: bool = False) -> TrackerStatusResponse:
    return TrackerStatusResponse.model_validate(tracker_status_dict(cfg, force_compare=force_compare))


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
        tracker_status=_tracker_status(cfg),
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
    # Retarget lock watch when the tracker path may have changed.
    lock_watch.retarget(cfg.tracker_abs)
    dropdown_cache.clear()
    log.info("settings updated: %s", sorted(patch))
    return cfg


@router.put("/settings", response_model=SettingsResponse)
def update_settings(req: SettingsUpdate) -> SettingsResponse:
    return _view(apply_settings_update(req.config))


@router.get("/tracker/status", response_model=TrackerStatusResponse)
def get_tracker_status(force: bool = Query(False)) -> TrackerStatusResponse:
    """Lock state (``~$`` watch + probe) and dropdown DV sync vs HTP options."""
    return _tracker_status(get_settings(), force_compare=force)


@router.post("/meta/options/sync", response_model=TrackerStatusResponse)
def sync_options_to_excel() -> TrackerStatusResponse:
    """Push HTP editable dropdown lists into Excel list validations."""
    cfg = get_settings()
    snap = lock_watch.probe()
    if snap.locked:
        raise TrackerLocked(
            f"{Path(cfg.tracker_abs).name} appears to be open in Excel. Close it and sync again."
        )
    try:
        sync_dropdowns_to_excel(cfg)
    except TrackerLocked:
        raise
    except (TrackerError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc
    log.info("dropdown options synced to excel")
    return _tracker_status(cfg, force_compare=True)


@router.post("/meta/options/{column}", response_model=AddOptionResponse)
def add_option(column: str, req: AddOptionRequest) -> AddOptionResponse:
    """Append a value to an editable dropdown list, persist to config, sync Excel DV."""
    if column not in EDITABLE_OPTION_COLUMNS:
        raise HTTPException(400, f"Column {column!r} is not editable. Allowed: {list(EDITABLE_OPTION_COLUMNS)}")
    value = (req.value or "").strip()
    if not value:
        raise HTTPException(400, "Option value is empty.")
    if "," in value:
        raise HTTPException(400, "Option values cannot contain commas (Excel list delimiter).")

    cfg = get_settings()
    current = resolved_options(cfg.options)
    if value in current[column]:
        raise HTTPException(409, f"{value!r} is already in {column}.")

    # Seed all three editable lists on first write so config owns the vocab going forward.
    seeded = {k: list(current[k]) for k in EDITABLE_OPTION_COLUMNS}
    seeded[column].append(value)
    cfg = apply_settings_update({"options": seeded})

    excel_synced = True
    excel_error: str | None = None
    try:
        Tracker(cfg.tracker_abs, backups_keep=cfg.backups_keep).sync_list_validations(list_validation_options(cfg))
        dropdown_cache.clear()
    except TrackerLocked as exc:
        excel_synced = False
        excel_error = str(exc)
        log.info("option %s=%r saved; excel sync deferred (locked)", column, value)
    except (TrackerError, OSError) as exc:
        excel_synced = False
        excel_error = str(exc)
        log.warning("option %s=%r saved; excel sync failed: %s", column, value, exc)

    log.info("added option %s=%r excel_synced=%s", column, value, excel_synced)
    return AddOptionResponse(
        column=column,
        value=value,
        options=resolved_options(cfg.options),
        excel_synced=excel_synced,
        excel_error=excel_error,
    )


@router.get("/logs", response_model=LogsResponse)
def get_logs(lines: int = Query(200, ge=1, le=2000)) -> LogsResponse:
    cfg = get_settings()
    return LogsResponse(path=str(log_path(cfg)), lines=tail(cfg, lines))
