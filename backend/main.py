"""FastAPI app.  Run:  uvicorn backend.main:app --reload --reload-dir backend --port 8010"""
from __future__ import annotations

import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api.routers import extract, files, sessions, settings
from .excel.tracker import TrackerError, TrackerLocked
from .files.convert import ConversionError
from .jev.client import JevError
from .llm.client import LLMError

app = FastAPI(title="HuntTrackPipe API", version="0.1.0")

API = "/api"
app.include_router(extract.router, prefix=API)
app.include_router(sessions.router, prefix=API)
app.include_router(files.router, prefix=API)
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
    print(f"[jev] {exc}")
    return _err(502, exc)


@app.exception_handler(LLMError)
async def _llm(_: Request, exc: LLMError):
    print(f"[llm] {exc}")
    return _err(502, exc)


@app.exception_handler(FileExistsError)
async def _exists(_: Request, exc: FileExistsError):
    return _err(409, exc)


@app.exception_handler(FileNotFoundError)
async def _missing(_: Request, exc: FileNotFoundError):
    return _err(404, exc)


@app.exception_handler(ConversionError)
async def _conversion(_: Request, exc: ConversionError):
    print(f"[files] {exc}")
    return _err(400, exc)


@app.exception_handler(ValueError)
async def _value(_: Request, exc: ValueError):
    return _err(400, exc)


@app.exception_handler(RuntimeError)
async def _runtime(_: Request, exc: RuntimeError):
    # e.g. missing API key from config.api_key()
    traceback.print_exc()
    return _err(500, exc)
