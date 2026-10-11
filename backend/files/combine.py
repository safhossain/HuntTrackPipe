"""Merge PDFs in display order (pypdf)."""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from .convert import ConversionError


def merge_pdfs(sources: list[Path], dst: Path) -> Path:
    if not sources:
        raise ConversionError("Nothing to combine.")
    writer = PdfWriter()
    for src in sources:
        try:
            reader = PdfReader(str(src))
            if reader.is_encrypted:
                reader.decrypt("")
            for page in reader.pages:
                writer.add_page(page)
        except Exception as exc:
            raise ConversionError(f"Could not read {src.name}: {exc}") from exc
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".pdf.tmp")
    with open(tmp, "wb") as fh:
        writer.write(fh)
    tmp.replace(dst)
    return dst
