"""Per-application file operations: inputs, finals, combined PDF, thumbnails.

Everything lives inside the application folder:
  {count}_<name>.<ext>              inputs (display order == count)
  {Candidate}_{DocType}_{X}.<ext>   finals (copies of inputs, renamed)
  {Candidate}_{X}.pdf               combined PDF
  .converted/                       PDF cache for non-PDF inputs
  .thumbs/                          first-page thumbnails
The manifest is ``session.files``; this module keeps disk and manifest in sync.
"""
from __future__ import annotations

import logging
import re
import shutil
from datetime import date
from pathlib import Path

from ..config import Settings
from ..naming import DOC_TYPES, combined_file_name, final_file_name, input_file_name, x_token
from ..sessions.models import CombinedFile, FinalFile, InputFile, Session, utc_now
from ..sessions.store import POSTING_FILE, SESSION_FILE
from . import convert as cv
from .combine import merge_pdfs

log = logging.getLogger("htp.files")

CONVERTED_DIR = ".converted"
THUMBS_DIR = ".thumbs"
ANSWERS_FILE = "answers.md"
RESERVED = {SESSION_FILE, POSTING_FILE, ANSWERS_FILE}

_DOC_TYPE_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"cover[\s_-]*letter|coverletter|\bcl\b|cover", re.I), "CoverLetter"),
    (re.compile(r"resume|résumé|\bcv\b|curriculum", re.I), "Resume"),
    (re.compile(r"transcript|grades|marks", re.I), "Transcript"),
    (re.compile(r"portfolio|showcase", re.I), "Portfolio"),
    (re.compile(r"referen", re.I), "References"),
)


class FileError(ValueError):
    pass


def guess_doc_type(name: str) -> str | None:
    for pat, doc in _DOC_TYPE_HINTS:
        if pat.search(name):
            return doc
    return None


def safe_name(name: str) -> str:
    """Reject anything that is not a plain file name inside the folder."""
    if not name or name in (".", "..") or "/" in name or "\\" in name or name != Path(name).name:
        raise FileError(f"Invalid file name {name!r}")
    return name


class FileManager:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.root = cfg.applications_abs

    # -- paths ---------------------------------------------------------------
    def folder(self, session: Session) -> Path:
        return self.root / session.folder

    def converted_dir(self, session: Session) -> Path:
        return self.folder(session) / CONVERTED_DIR

    def thumbs_dir(self, session: Session) -> Path:
        return self.folder(session) / THUMBS_DIR

    def path_of(self, session: Session, name: str) -> Path:
        p = self.folder(session) / safe_name(name)
        if not p.is_file():
            raise FileNotFoundError(f"{name} is not in {session.folder}")
        return p

    def _input(self, session: Session, index: int) -> InputFile:
        inputs = session.files.inputs
        if index < 0 or index >= len(inputs):
            raise FileError(f"No input with index {index}")
        return inputs[index]

    # -- inputs ---------------------------------------------------------------
    def add_input_bytes(self, session: Session, original_name: str, data: bytes) -> InputFile:
        folder = self.folder(session)
        idx = len(session.files.inputs)
        original = Path(original_name).name or "file"
        name = self._unique(folder, input_file_name(idx, original))
        (folder / name).write_bytes(data)
        return self._register(session, idx, name, original)

    def add_input_path(self, session: Session, src: Path, original_name: str | None = None) -> InputFile:
        """Copy an existing file into the folder as the next input."""
        folder = self.folder(session)
        idx = len(session.files.inputs)
        original = original_name or src.name
        name = self._unique(folder, input_file_name(idx, original))
        shutil.copy2(src, folder / name)
        return self._register(session, idx, name, original)

    def adopt(self, session: Session, name: str) -> InputFile:
        """Turn a file the user dropped into the folder into a tracked input (renamed in place)."""
        folder = self.folder(session)
        src = folder / safe_name(name)
        if not src.is_file() or name not in self.untracked(session):
            raise FileError(f"{name} is not an untracked file in this folder")
        idx = len(session.files.inputs)
        target = self._unique(folder, input_file_name(idx, name))
        src.rename(folder / target)
        return self._register(session, idx, target, name)

    def _register(self, session: Session, idx: int, name: str, original: str) -> InputFile:
        p = self.folder(session) / name
        item = InputFile(
            index=idx,
            file=name,
            original=original,
            doc_type=guess_doc_type(original),
            size=p.stat().st_size,
            pages=cv.page_count(p),
        )
        session.files.inputs.append(item)
        log.info("%s: input %d %s (%d bytes, %s pages)", session.folder, idx, name, item.size, item.pages)
        return item

    def set_doc_type(self, session: Session, index: int, doc_type: str | None) -> None:
        if doc_type is not None and doc_type not in DOC_TYPES:
            raise FileError(f"doc_type must be one of {DOC_TYPES}")
        self._input(session, index).doc_type = doc_type

    def remove_input(self, session: Session, index: int) -> None:
        item = self._input(session, index)
        p = self.folder(session) / item.file
        if p.exists():
            p.unlink()
        order = [i for i in range(len(session.files.inputs)) if i != index]
        self._apply_order(session, order)

    def reorder(self, session: Session, order: list[int]) -> None:
        n = len(session.files.inputs)
        if sorted(order) != list(range(n)):
            raise FileError(f"order must be a permutation of 0..{n - 1}")
        self._apply_order(session, order)

    def _apply_order(self, session: Session, order: list[int]) -> None:
        """``order[new_index] = old_index``. Renames files on disk, remaps finals/combined."""
        folder = self.folder(session)
        old = session.files.inputs
        remap = {old_i: new_i for new_i, old_i in enumerate(order)}
        # Two-phase rename to avoid clobbering (e.g. swapping 0 and 1).
        tmp_names: dict[int, Path] = {}
        for old_i in order:
            src = folder / old[old_i].file
            tmp = folder / f".__reorder_{old_i}_{old[old_i].file}"
            if src.exists():
                src.rename(tmp)
                tmp_names[old_i] = tmp
        new_inputs: list[InputFile] = []
        for new_i, old_i in enumerate(order):
            item = old[old_i]
            name = input_file_name(new_i, item.original)
            if old_i in tmp_names:
                tmp_names[old_i].rename(folder / name)
            new_inputs.append(item.model_copy(update={"index": new_i, "file": name}))
        session.files.inputs = new_inputs
        for f in session.files.finals:
            f.from_index = remap.get(f.from_index) if f.from_index is not None else None
        if session.files.combined:
            session.files.combined.from_indices = [remap[i] for i in session.files.combined.from_indices if i in remap]
        self._prune_cache(session)

    # -- conversions ------------------------------------------------------------
    def convert_input(self, session: Session, index: int, target: str) -> list[InputFile]:
        """Convert one input and append the result(s) as new inputs."""
        item = self._input(session, index)
        src = self.folder(session) / item.file
        with_tmp = self.converted_dir(session) / "standalone"
        if with_tmp.exists():
            shutil.rmtree(with_tmp, ignore_errors=True)
        outs = cv.convert(src, target, with_tmp, self.cfg.files)
        added: list[InputFile] = []
        stem = Path(item.original).stem
        for out in outs:
            suffix = out.name[len(src.stem):] if out.name.startswith(src.stem) else out.suffix
            new = self.add_input_path(session, out, f"{stem}{suffix}")
            new.doc_type = item.doc_type
            added.append(new)
        shutil.rmtree(with_tmp, ignore_errors=True)
        return added

    # -- finals -------------------------------------------------------------------
    def make_final(self, session: Session, index: int, x: str) -> FinalFile:
        item = self._input(session, index)
        if not item.doc_type:
            raise FileError(f"Set a document type for {item.file} first")
        folder = self.folder(session)
        src = folder / item.file
        if not src.exists():
            raise FileNotFoundError(f"{item.file} is missing on disk")
        # Replace an earlier final made from the same input.
        for old in [f for f in session.files.finals if f.from_index == index]:
            self._delete_file(folder / old.file)
            session.files.finals.remove(old)
        name = final_file_name(self.cfg.candidate_name, item.doc_type, x, cv.ext_of(src))
        taken = {f.file.lower() for f in session.files.finals}
        name = self._unique(folder, name, taken)
        shutil.copy2(src, folder / name)
        final = FinalFile(file=name, doc_type=item.doc_type, from_index=index)
        session.files.finals.append(final)
        log.info("%s: final %s from input %d", session.folder, name, index)
        return final

    # -- combine -------------------------------------------------------------------
    def combine(self, session: Session, indices: list[int] | None, x: str) -> CombinedFile:
        inputs = session.files.inputs
        if indices is None:
            indices = list(range(len(inputs)))
        if not indices:
            raise FileError("No inputs to combine")
        folder = self.folder(session)
        pdfs = [cv.to_pdf(folder / self._input(session, i).file, self.converted_dir(session), self.cfg.files) for i in indices]
        name = combined_file_name(self.cfg.candidate_name, x)
        if session.files.combined and session.files.combined.file != name:
            self._delete_file(folder / session.files.combined.file)
        out = merge_pdfs(pdfs, folder / name)
        combined = CombinedFile(file=name, from_indices=list(indices), pages=cv.page_count(out), at=utc_now())
        session.files.combined = combined
        log.info("%s: combined %s from %s (%s pages)", session.folder, name, indices, combined.pages)
        return combined

    # -- outputs -------------------------------------------------------------------
    def delete_output(self, session: Session, name: str) -> None:
        name = safe_name(name)
        folder = self.folder(session)
        if session.files.combined and session.files.combined.file == name:
            session.files.combined = None
        else:
            match = [f for f in session.files.finals if f.file == name]
            if not match:
                raise FileError(f"{name} is not a final or combined file")
            session.files.finals.remove(match[0])
        self._delete_file(folder / name)

    # -- listing / previews --------------------------------------------------------
    def untracked(self, session: Session) -> list[str]:
        folder = self.folder(session)
        known = {i.file for i in session.files.inputs} | {f.file for f in session.files.finals} | RESERVED
        if session.files.combined:
            known.add(session.files.combined.file)
        out = []
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.name not in known and not p.name.startswith(".") and not p.name.endswith(".tmp"):
                out.append(p.name)
        return out

    def missing(self, session: Session) -> list[str]:
        folder = self.folder(session)
        names = [i.file for i in session.files.inputs] + [f.file for f in session.files.finals]
        if session.files.combined:
            names.append(session.files.combined.file)
        return [n for n in names if not (folder / n).exists()]

    def thumbnail(self, session: Session, name: str, width: int = 240) -> Path:
        src = self.path_of(session, name)
        tdir = self.thumbs_dir(session)
        key = f"{src.stem}.{src.stat().st_mtime_ns}.w{width}.png"
        dst = tdir / key
        if dst.exists():
            return dst
        tdir.mkdir(exist_ok=True)
        for stale in tdir.glob(f"{src.stem}.*.w{width}.png"):
            stale.unlink(missing_ok=True)
        return cv.thumbnail(src, dst, width, self.cfg.files, work_dir=self.converted_dir(session))

    # -- helpers ---------------------------------------------------------------------
    @staticmethod
    def _unique(folder: Path, name: str, taken: set[str] = frozenset()) -> str:
        if not (folder / name).exists() and name.lower() not in taken:
            return name
        stem, dot, ext = name.rpartition(".")
        if not dot:
            stem, ext = name, ""
        n = 2
        while True:
            cand = f"{stem}-{n}" + (f".{ext}" if ext else "")
            if not (folder / cand).exists() and cand.lower() not in taken:
                return cand
            n += 1

    @staticmethod
    def _delete_file(p: Path) -> None:
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    def _prune_cache(self, session: Session) -> None:
        cdir = self.converted_dir(session)
        if not cdir.exists():
            return
        stems = {Path(i.file).stem for i in session.files.inputs}
        for p in cdir.glob("*.pdf"):
            if p.stem not in stems:
                p.unlink(missing_ok=True)


def x_for(session: Session, row: dict | None) -> str:
    """{X} token from Excel's row when readable, else from the engine's last written values."""
    src = row or session.review.values
    created = date.fromisoformat(session.created_at[:10])
    return x_token(
        _s(src.get("Requisition_ID")),
        _s(src.get("Organization")),
        _s(src.get("Position_Title")),
        created,
    )


def _s(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None