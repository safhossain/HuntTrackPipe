"""Create / load / save ``session.json`` inside each application folder."""
from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from .models import Posting, Session

SESSION_FILE = "session.json"
POSTING_FILE = "posting.txt"
_WRITE_LOCK = Lock()


def _replace_file(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class SessionStore:
    def __init__(self, applications_dir: Path):
        self.root = applications_dir

    # -- paths -------------------------------------------------------------
    def folder_path(self, folder: str) -> Path:
        return self.root / folder

    def existing_folder_names(self) -> list[str]:
        if not self.root.exists():
            return []
        return [p.name for p in self.root.iterdir() if p.is_dir() and not p.name.startswith(".")]

    # -- CRUD --------------------------------------------------------------
    def create(self, session: Session) -> Path:
        path = self.folder_path(session.folder)
        if path.exists():
            raise FileExistsError(f"Application folder already exists: {path}")
        path.mkdir(parents=True)
        (path / POSTING_FILE).write_text(session.posting.text, encoding="utf-8")
        self.save(session)
        return path

    def save(self, session: Session) -> None:
        with _WRITE_LOCK:
            path = self.folder_path(session.folder) / SESSION_FILE
            if path.exists():
                # A save for notes, files, or Q&A may have loaded before a posting edit.
                posting = self.load(session.folder).posting
                session.posting.text = posting.text
                session.posting.hash = posting.hash
            self._save_session(path, session)

    def update_posting(self, folder: str, text: str, text_hash: str) -> Posting:
        folder_path = self.folder_path(folder)
        if folder_path.name != folder or folder_path.resolve().parent != self.root.resolve():
            raise FileNotFoundError(f"No session for folder {folder!r}")
        with _WRITE_LOCK:
            session = self.load(folder)
            posting_path = folder_path / POSTING_FILE
            try:
                original = posting_path.read_bytes()
            except FileNotFoundError:
                original = None

            session.posting.text = text
            session.posting.hash = text_hash
            _replace_file(posting_path, text.encode("utf-8"))
            try:
                self._save_session(folder_path / SESSION_FILE, session)
            except Exception:
                if original is None:
                    posting_path.unlink()
                else:
                    _replace_file(posting_path, original)
                raise
            return session.posting

    @staticmethod
    def _save_session(path: Path, session: Session) -> None:
        _replace_file(path, session.model_dump_json(indent=2, by_alias=True).encode("utf-8"))

    def load(self, folder: str) -> Session:
        path = self.folder_path(folder) / SESSION_FILE
        return Session.model_validate_json(path.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[Session]:
        out: list[Session] = []
        for name in self.existing_folder_names():
            if (self.folder_path(name) / SESSION_FILE).exists():
                try:
                    out.append(self.load(name))
                except Exception:  # corrupt file: skip, UI can show it as unmanaged
                    continue
        out.sort(key=lambda s: s.created_at, reverse=True)
        return out

    def unmanaged_folders(self) -> list[str]:
        return [n for n in self.existing_folder_names() if not (self.folder_path(n) / SESSION_FILE).exists()]
