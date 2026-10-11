"""Files tab + standalone converter (DESIGN.md section 10)."""
from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ...excel.tracker import TrackerError
from ...files import convert as cv
from ...files.manager import FileManager, x_for
from ...sessions.models import Session
from ..deps import get_settings, get_store, get_tracker
from ..models import (
    ConvertRequest,
    DocTypeRequest,
    FilesView,
    IndicesRequest,
    NameRequest,
    OrderRequest,
    UploadModeRequest,
)

router = APIRouter(tags=["files"])
S = "/sessions/{folder}/files"

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _manager() -> FileManager:
    return FileManager(get_settings())


def _load(folder: str) -> Session:
    try:
        return get_store().load(folder)
    except FileNotFoundError:
        raise HTTPException(404, f"No session for folder {folder!r}")


def _row(folder: str) -> dict | None:
    try:
        return get_tracker().read_row(folder)
    except (TrackerError, OSError):
        return None


def _view(session: Session, fm: FileManager) -> FilesView:
    cfg = get_settings()
    return FilesView(
        files=session.files,
        upload_mode=session.upload_mode,
        upload_mode_source=session.upload_mode_source,
        required_docs=session.jev.derived.required_docs if session.jev else [],
        untracked=fm.untracked(session),
        missing=fm.missing(session),
        x=x_for(session, _row(session.folder)),
        candidate=cfg.candidate_name,
        tools={**cv.tool_status(cfg.files), "targets": list(cv.CONVERT_TARGETS)},
    )


def _save_view(session: Session, fm: FileManager) -> FilesView:
    get_store().save(session)
    return _view(session, fm)


# -- listing / manifest ------------------------------------------------------------


@router.get(S, response_model=FilesView)
def list_files(folder: str) -> FilesView:
    return _view(_load(folder), _manager())


@router.post(S, response_model=FilesView)
async def upload_files(folder: str, files: list[UploadFile] = File(...)) -> FilesView:
    session, fm = _load(folder), _manager()
    for up in files:
        data = await up.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{up.filename} exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        if not data:
            raise HTTPException(400, f"{up.filename} is empty")
        fm.add_input_bytes(session, up.filename or "file", data)
    return _save_view(session, fm)


@router.post(f"{S}/adopt", response_model=FilesView)
def adopt_file(folder: str, req: NameRequest) -> FilesView:
    session, fm = _load(folder), _manager()
    fm.adopt(session, req.name)
    return _save_view(session, fm)


@router.put(f"{S}/order", response_model=FilesView)
def reorder_files(folder: str, req: OrderRequest) -> FilesView:
    session, fm = _load(folder), _manager()
    fm.reorder(session, req.order)
    return _save_view(session, fm)


@router.put(f"{S}/upload-mode", response_model=FilesView)
def set_upload_mode(folder: str, req: UploadModeRequest) -> FilesView:
    session, fm = _load(folder), _manager()
    session.upload_mode = req.upload_mode
    jev_mode = session.jev.derived.upload_mode if session.jev else None
    session.upload_mode_source = "jev" if req.upload_mode == jev_mode else "user"
    return _save_view(session, fm)


@router.post(f"{S}/final", response_model=FilesView)
def make_finals(folder: str, req: IndicesRequest) -> FilesView:
    session, fm = _load(folder), _manager()
    x = x_for(session, _row(folder))
    indices = req.indices if req.indices is not None else [i.index for i in session.files.inputs if i.doc_type]
    if not indices:
        raise HTTPException(400, "No inputs with a document type to finalize.")
    for i in indices:
        fm.make_final(session, i, x)
    return _save_view(session, fm)


@router.post(f"{S}/combine", response_model=FilesView)
def combine_files(folder: str, req: IndicesRequest) -> FilesView:
    session, fm = _load(folder), _manager()
    fm.combine(session, req.indices, x_for(session, _row(folder)))
    return _save_view(session, fm)


@router.delete(f"{S}/output/{{name}}", response_model=FilesView)
def delete_output(folder: str, name: str) -> FilesView:
    session, fm = _load(folder), _manager()
    fm.delete_output(session, name)
    return _save_view(session, fm)


@router.get(f"{S}/thumb/{{name}}")
def thumbnail(folder: str, name: str, width: int = 240):
    session, fm = _load(folder), _manager()
    width = max(64, min(width, 1200))
    try:
        path = fm.thumbnail(session, name, width)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get(f"{S}/download/{{name}}")
def download(folder: str, name: str, inline: bool = False):
    session, fm = _load(folder), _manager()
    try:
        path = fm.path_of(session, name)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    disposition = "inline" if inline else "attachment"
    return FileResponse(path, filename=name, content_disposition_type=disposition)


@router.put(f"{S}/{{index}}", response_model=FilesView)
def set_doc_type(folder: str, index: int, req: DocTypeRequest) -> FilesView:
    session, fm = _load(folder), _manager()
    fm.set_doc_type(session, index, req.doc_type)
    return _save_view(session, fm)


@router.delete(f"{S}/{{index}}", response_model=FilesView)
def delete_input(folder: str, index: int) -> FilesView:
    session, fm = _load(folder), _manager()
    fm.remove_input(session, index)
    return _save_view(session, fm)


@router.post(f"{S}/{{index}}/convert", response_model=FilesView)
def convert_input(folder: str, index: int, req: ConvertRequest) -> FilesView:
    session, fm = _load(folder), _manager()
    fm.convert_input(session, index, req.target)
    return _save_view(session, fm)


# -- standalone converter -------------------------------------------------------------


@router.get("/files/tools")
def tools() -> dict:
    return {**cv.tool_status(get_settings().files), "targets": list(cv.CONVERT_TARGETS)}


@router.post("/files/convert")
async def convert_standalone(file: UploadFile = File(...), target: str = Form(...)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    tmp = Path(tempfile.mkdtemp(prefix="htp_conv_"))
    cleanup = BackgroundTask(shutil.rmtree, tmp, True)
    try:
        src = tmp / "in" / (Path(file.filename or "file").name or "file")
        src.parent.mkdir()
        src.write_bytes(data)
        outs = cv.convert(src, target, tmp / "out", get_settings().files)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    if len(outs) == 1:
        return FileResponse(outs[0], filename=outs[0].name, background=cleanup)
    zpath = tmp / f"{src.stem}_{target}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for o in outs:
            zf.write(o, o.name)
    return FileResponse(zpath, filename=zpath.name, media_type="application/zip", background=cleanup)
