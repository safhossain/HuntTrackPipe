"""Single-file conversions.

docx/office -> pdf   LibreOffice headless (``soffice``)
pdf -> docx          pdf2docx (lossy)
pdf -> png/jpg       PyMuPDF, one image per page
png/jpg -> pdf       img2pdf (alpha channels flattened with Pillow first)
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf

from ..config import FileSettings

OFFICE_EXTS = {"doc", "docx", "odt", "rtf", "txt", "md", "xls", "xlsx", "ods", "ppt", "pptx", "odp"}
IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "gif"}
PDF_EXT = "pdf"
CONVERT_TARGETS = ("pdf", "docx", "png", "jpg")

_SOFFICE_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)


class ConversionError(RuntimeError):
    pass


def ext_of(path: str | Path) -> str:
    return Path(path).suffix.lstrip(".").lower()


def kind_of(path: str | Path) -> str:
    """'pdf' | 'image' | 'office' | 'other'"""
    e = ext_of(path)
    if e == PDF_EXT:
        return "pdf"
    if e in IMAGE_EXTS:
        return "image"
    if e in OFFICE_EXTS:
        return "office"
    return "other"


def find_soffice(cfg: FileSettings | None = None) -> str | None:
    if cfg and cfg.soffice_path and Path(cfg.soffice_path).exists():
        return cfg.soffice_path
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return found
    for c in _SOFFICE_CANDIDATES:
        if Path(c).exists():
            return c
    return None


def pdf2docx_available() -> bool:
    try:
        import pdf2docx  # noqa: F401
    except Exception:
        return False
    return True


def tool_status(cfg: FileSettings | None = None) -> dict[str, bool | str | None]:
    return {"soffice": find_soffice(cfg), "pdf2docx": pdf2docx_available()}


# ---------------------------------------------------------------------------


def office_to_pdf(src: Path, out_dir: Path, cfg: FileSettings | None = None, timeout_s: float = 120) -> Path:
    soffice = find_soffice(cfg)
    if not soffice:
        raise ConversionError("LibreOffice (soffice) not found. Install it or set files.soffice_path in htp.config.json.")
    out_dir.mkdir(parents=True, exist_ok=True)
    # Own (persistent) profile dir: a running LibreOffice GUI cannot swallow the call,
    # and reusing it avoids the ~15 s first-run profile creation on every conversion.
    profile = Path(tempfile.gettempdir()) / "htp_lo_profile"
    profile.mkdir(exist_ok=True)
    cmd = [
        soffice,
        "--headless",
        "--norestore",
        f"-env:UserInstallation={profile.as_uri()}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(src),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(f"LibreOffice timed out converting {src.name}") from exc
    out = out_dir / (src.stem + ".pdf")
    if proc.returncode != 0 or not out.exists():
        msg = (proc.stderr or proc.stdout or "").strip()
        raise ConversionError(f"LibreOffice failed on {src.name}: {msg or 'no output produced'}")
    return out


def pdf_to_docx(src: Path, dst: Path) -> Path:
    try:
        from pdf2docx import Converter
    except Exception as exc:  # pragma: no cover - import guard
        raise ConversionError("pdf2docx is not installed.") from exc
    logging.getLogger("pdf2docx").setLevel(logging.WARNING)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cv = Converter(str(src))
    try:
        cv.convert(str(dst))
    except Exception as exc:
        raise ConversionError(f"pdf2docx failed on {src.name}: {exc}") from exc
    finally:
        cv.close()
    return dst


def pdf_to_images(src: Path, out_dir: Path, fmt: str = "png", dpi: int = 150) -> list[Path]:
    fmt = fmt.lower()
    if fmt not in ("png", "jpg"):
        raise ConversionError(f"Unsupported image format {fmt!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    outs: list[Path] = []
    with pymupdf.open(src) as doc:
        if doc.page_count == 0:
            raise ConversionError(f"{src.name} has no pages")
        width = len(str(doc.page_count))
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            out = out_dir / f"{src.stem}_p{i:0{width}d}.{fmt}"
            pix.save(out, output="png" if fmt == "png" else "jpeg", jpg_quality=90)
            outs.append(out)
    return outs


def images_to_pdf(srcs: list[Path], dst: Path) -> Path:
    import img2pdf
    from PIL import Image

    dst.parent.mkdir(parents=True, exist_ok=True)
    payloads: list[bytes] = []
    for s in srcs:
        with Image.open(s) as im:
            needs_flatten = im.mode not in ("RGB", "L", "1") or ext_of(s) not in ("jpg", "jpeg", "png")
            if needs_flatten:
                import io

                rgb = im.convert("RGBA") if "A" in im.getbands() else im.convert("RGB")
                if rgb.mode == "RGBA":
                    bg = Image.new("RGB", rgb.size, (255, 255, 255))
                    bg.paste(rgb, mask=rgb.split()[3])
                    rgb = bg
                buf = io.BytesIO()
                rgb.save(buf, format="JPEG", quality=92)
                payloads.append(buf.getvalue())
            else:
                payloads.append(s.read_bytes())
    try:
        pdf_bytes = img2pdf.convert(payloads)
    except Exception as exc:
        raise ConversionError(f"img2pdf failed: {exc}") from exc
    dst.write_bytes(pdf_bytes)
    return dst


def to_pdf(src: Path, work_dir: Path, cfg: FileSettings | None = None) -> Path:
    """Return a PDF for ``src``: itself if already a PDF, otherwise a converted copy in ``work_dir``.
    The converted copy is reused when it is newer than the source."""
    kind = kind_of(src)
    if kind == "pdf":
        return src
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / (src.stem + ".pdf")
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return out
    if kind == "image":
        return images_to_pdf([src], out)
    if kind == "office":
        return office_to_pdf(src, work_dir, cfg)
    raise ConversionError(f"Cannot convert .{ext_of(src)} files to PDF")


def convert(src: Path, target: str, out_dir: Path, cfg: FileSettings | None = None) -> list[Path]:
    """Standalone conversion: returns one or more output files in ``out_dir``."""
    target = target.lower().lstrip(".")
    if target not in CONVERT_TARGETS:
        raise ConversionError(f"target must be one of {CONVERT_TARGETS}")
    kind = kind_of(src)
    dpi = cfg.image_dpi if cfg else 150
    if target == "pdf":
        if kind == "pdf":
            raise ConversionError("Already a PDF.")
        return [to_pdf(src, out_dir, cfg)]
    if target == "docx":
        if kind != "pdf":
            raise ConversionError("Only PDF -> DOCX is supported.")
        return [pdf_to_docx(src, out_dir / (src.stem + ".docx"))]
    # png / jpg
    if kind == "pdf":
        return pdf_to_images(src, out_dir, target, dpi)
    if kind in ("image", "office"):
        pdf = to_pdf(src, out_dir / ".tmp", cfg)
        return pdf_to_images(pdf, out_dir, target, dpi)
    raise ConversionError(f"Cannot convert .{ext_of(src)} to {target}")


def page_count(path: Path) -> int | None:
    try:
        if kind_of(path) in ("pdf", "image"):
            with pymupdf.open(path) as doc:
                return doc.page_count
    except Exception:
        return None
    return None


def thumbnail(src: Path, dst: Path, width: int = 240, cfg: FileSettings | None = None, work_dir: Path | None = None) -> Path:
    """First-page PNG thumbnail. Office documents are converted to PDF first (cached in ``work_dir``)."""
    kind = kind_of(src)
    target = src
    if kind == "office":
        target = to_pdf(src, work_dir or dst.parent, cfg)
    elif kind == "other":
        raise ConversionError(f"No preview for .{ext_of(src)} files")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(target) as doc:
        page = doc[0]
        zoom = width / max(page.rect.width, 1)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        pix.save(dst, output="png")
    return dst
