"""File manager + PDF/image conversions (PyMuPDF only; LibreOffice is not required)."""
from pathlib import Path

import pymupdf
import pytest

from backend.files import convert as cv
from backend.files.manager import FileError, FileManager, guess_doc_type, safe_name, x_for
from backend.sessions.store import SessionStore


def pdf_bytes(pages: int, label: str) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{label} page {i + 1}")
    return doc.tobytes()


def png_bytes() -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 30), False)
    pix.clear_with(200)
    return pix.tobytes("png")


@pytest.fixture
def fm(env) -> FileManager:
    return FileManager(env)


def test_guess_doc_type_and_safe_name():
    assert guess_doc_type("Jane_Resume_2026.pdf") == "Resume"
    assert guess_doc_type("cover letter.docx") == "CoverLetter"
    assert guess_doc_type("unofficial-transcript.pdf") == "Transcript"
    assert guess_doc_type("notes.txt") is None
    assert safe_name("a.pdf") == "a.pdf"
    for bad in ("../a.pdf", "x/y.pdf", "..", ""):
        with pytest.raises(FileError):
            safe_name(bad)


def test_add_final_reorder_remove(env, session, fm):
    store = SessionStore(env.applications_abs)
    a = fm.add_input_bytes(session, "My Resume.pdf", pdf_bytes(2, "resume"))
    b = fm.add_input_bytes(session, "Cover Letter.PDF", pdf_bytes(1, "letter"))
    assert (a.index, a.file, a.doc_type, a.pages) == (0, "0_My-Resume.pdf", "Resume", 2)
    assert (b.index, b.file, b.doc_type, b.pages) == (1, "1_Cover-Letter.pdf", "CoverLetter", 1)
    folder = fm.folder(session)

    x = x_for(session, None)
    assert x == "R-12345"
    final = fm.make_final(session, 0, x)
    assert final.file == "Test-Candidate_Resume_R-12345.pdf" and final.from_index == 0
    assert (folder / final.file).exists()
    # Making a final again from the same input replaces it instead of piling up.
    fm.make_final(session, 0, x)
    assert len(session.files.finals) == 1

    fm.reorder(session, [1, 0])
    names = [i.file for i in session.files.inputs]
    assert names == ["0_Cover-Letter.pdf", "1_My-Resume.pdf"]
    assert all((folder / n).exists() for n in names)
    assert session.files.finals[0].from_index == 1  # remapped
    with pytest.raises(FileError):
        fm.reorder(session, [0, 0])

    with pytest.raises(FileError):
        fm.set_doc_type(session, 0, "Letter")
    fm.set_doc_type(session, 0, None)
    with pytest.raises(FileError):
        fm.make_final(session, 0, x)  # no doc type

    fm.remove_input(session, 0)
    assert [i.file for i in session.files.inputs] == ["0_My-Resume.pdf"]
    assert not (folder / "1_My-Resume.pdf").exists()
    assert session.files.finals[0].from_index == 0
    store.save(session)
    assert store.load(session.folder).files.inputs[0].file == "0_My-Resume.pdf"


def test_combine_and_outputs(env, session, fm):
    fm.add_input_bytes(session, "resume.pdf", pdf_bytes(2, "resume"))
    fm.add_input_bytes(session, "cover.png", png_bytes())
    fm.add_input_bytes(session, "letter.pdf", pdf_bytes(1, "letter"))
    combined = fm.combine(session, [2, 0], "R-12345")
    assert combined.file == "Test-Candidate_R-12345.pdf" and combined.pages == 3
    out = fm.folder(session) / combined.file
    assert pymupdf.open(out)[0].get_text().startswith("letter page 1")  # order honoured

    combined_all = fm.combine(session, None, "R-12345")
    assert combined_all.pages == 4  # png -> one PDF page
    assert fm.untracked(session) == []
    assert fm.missing(session) == []

    fm.delete_output(session, combined_all.file)
    assert session.files.combined is None and not out.exists()
    with pytest.raises(FileError):
        fm.delete_output(session, "nope.pdf")


def test_untracked_adopt_and_thumbnail(env, session, fm):
    folder = fm.folder(session)
    (folder / "dropped.pdf").write_bytes(pdf_bytes(1, "dropped"))
    assert fm.untracked(session) == ["dropped.pdf"]
    item = fm.adopt(session, "dropped.pdf")
    assert item.file == "0_dropped.pdf" and fm.untracked(session) == []
    with pytest.raises(FileError):
        fm.adopt(session, "session.json")

    thumb = fm.thumbnail(session, item.file, width=120)
    assert thumb.exists() and pymupdf.Pixmap(thumb).width == 120
    assert fm.thumbnail(session, item.file, width=120) == thumb  # cached


def test_convert_pdf_to_images_and_back(tmp_path: Path, env):
    src = tmp_path / "doc.pdf"
    src.write_bytes(pdf_bytes(2, "doc"))
    outs = cv.convert(src, "png", tmp_path / "out", env.files)
    assert [p.name for p in outs] == ["doc_p1.png", "doc_p2.png"]
    pdf = cv.convert(outs[0], "pdf", tmp_path / "out2", env.files)
    assert len(pdf) == 1 and cv.page_count(pdf[0]) == 1
    with pytest.raises(cv.ConversionError):
        cv.convert(src, "xyz", tmp_path / "out3", env.files)


def test_convert_input_appends_new_inputs(env, session, fm):
    fm.add_input_bytes(session, "resume.pdf", pdf_bytes(2, "resume"))
    added = fm.convert_input(session, 0, "png")
    assert [a.file for a in added] == ["1_resume_p1.png", "2_resume_p2.png"]
    assert all(a.doc_type == "Resume" for a in added)
