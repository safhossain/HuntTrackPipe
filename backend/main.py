"""FastAPI app.  Run:  uvicorn backend.main:app --reload --reload-dir backend --port 8010"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api.routers import extract, files, qa, sessions, settings
from .config import settings as get_settings
from .duplicates import DuplicateError
from .excel.dropdown_sync import compare_dropdowns, dropdown_cache
from .excel.lock_watch import lock_watch
from .excel.tracker import TrackerError, TrackerLocked
from .files.convert import ConversionError
from .jev.client import JevError
from .llm.client import LLMError
from .logs import setup_logging
from .qa.answer import CandidateContextMissing

log = logging.getLogger("htp.api")


def _on_tracker_unlocked() -> None:
    """sigOFF: safe to open the workbook — refresh dropdown drift once."""
    cfg = get_settings()
    dropdown_cache.clear()
    result = compare_dropdowns(cfg, locked=False, force=True)
    log.info("tracker unlocked; dropdown_sync=%s", result.status)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    cfg = get_settings()
    path = setup_logging(cfg)
    lock_watch.set_unlock_callback(_on_tracker_unlocked)
    snap = lock_watch.start(cfg.tracker_abs)
    if not snap.locked:
        compare_dropdowns(cfg, locked=False, force=True)
    log.info(
        "API started; applications_dir=%s tracker=%s log=%s locked=%s watching=%s",
        cfg.applications_abs, cfg.tracker_abs, path, snap.locked, snap.watching,
    )
    try:
        yield
    finally:
        lock_watch.stop()
        log.info("API stopped")


app = FastAPI(title="HuntTrackPipe API", version="0.1.0", lifespan=_lifespan)

API = "/api"
app.include_router(extract.router, prefix=API)
app.include_router(sessions.router, prefix=API)
app.include_router(files.router, prefix=API)
app.include_router(qa.router, prefix=API)
app.include_router(settings.router, prefix=API)


@app.get(f"{API}/health")
def health() -> dict:
    return {"ok": True}


def _err(status: int, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": str(exc), "type": type(exc).__name__})


@app.exception_handler(TrackerLocked)
async def _locked(_: Request, exc: TrackerLocked):
    return _err(423, exc)


@app.exception_handler(TrackerError)
async def _tracker(_: Request, exc: TrackerError):
    return _err(400, exc)


@app.exception_handler(JevError)
async def _jev(_: Request, exc: JevError):
    log.error("jev: %s", exc)
    return _err(502, exc)


@app.exception_handler(LLMError)
async def _llm(_: Request, exc: LLMError):
    log.error("llm: %s", exc)
    return _err(502, exc)


@app.exception_handler(DuplicateError)
async def _duplicate(_: Request, exc: DuplicateError):
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc), "type": "DuplicateError", "duplicates": [d.model_dump() for d in exc.hits]},
    )


@app.exception_handler(FileExistsError)
async def _exists(_: Request, exc: FileExistsError):
    return _err(409, exc)


@app.exception_handler(CandidateContextMissing)
async def _no_context(_: Request, exc: CandidateContextMissing):
    return _err(412, exc)  # precondition: the user must write candidate_context.txt first


@app.exception_handler(FileNotFoundError)
async def _missing(_: Request, exc: FileNotFoundError):
    return _err(404, exc)


@app.exception_handler(ConversionError)
async def _conversion(_: Request, exc: ConversionError):
    log.error("files: %s", exc)
    return _err(400, exc)


@app.exception_handler(ValueError)
async def _value(_: Request, exc: ValueError):
    return _err(400, exc)


@app.exception_handler(RuntimeError)
async def _runtime(_: Request, exc: RuntimeError):
    # e.g. missing API key from config.api_key()
    log.exception("unhandled: %s", exc)
    return _err(500, exc)
