"""Create / load / save ``session.json`` inside each application folder."""
from __future__ import annotations

import os
from pathlib import Path

from .models import Session

SESSION_FILE = "session.json"
POSTING_FILE = "posting.txt"


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
        path = self.folder_path(session.folder) / SESSION_FILE
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(session.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
        os.replace(tmp, path)

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
