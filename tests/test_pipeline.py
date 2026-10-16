"""create_application + duplicate detection, against the fixture tracker."""
from datetime import date

import pytest

from backend.duplicates import DuplicateError, find_duplicates, posting_hash
from backend.excel.tracker import Tracker, TrackerLocked
from backend.pipeline import create_application
from backend.sessions.store import POSTING_FILE, SESSION_FILE, SessionStore

from .conftest import POSTING, sample_extraction


def test_create_application_writes_folder_session_and_row(env, session):
    assert session.folder == "R-12345_Acme-Corp_Senior-Backend-Engineer_2026-10-11"
    folder = env.applications_abs / session.folder
    assert (folder / SESSION_FILE).exists() and (folder / POSTING_FILE).read_text(encoding="utf-8") == POSTING
    assert session.posting.hash == posting_hash(POSTING)
    assert session.upload_mode == "separate_uploads"
    assert session.review.written_at and session.review.pending_write is None

    row = Tracker(env.tracker_abs).read_row(session.folder)
    assert row["Organization"] == "Acme Corp"
    assert row["Deadline"] == date(2026, 12, 1)
    assert row["Applied_Through"] == "LinkedIn"
    assert row["Posting_URL"] == "https://jobs.example/r-12345"
    assert row["Application_Status"] == "Not Applied"
    assert row["Folder"] == session.folder
    assert session.review.values["Organization"] == "Acme Corp"


def test_not_stated_upload_mode_is_stored_as_separate_uploads(env):
    ex = sample_extraction()
    ex.derived.upload_mode = "not_stated"
    s, _ = create_application(env, posting_text="different posting", posting_url=None, extraction=ex)
    assert s.upload_mode == "separate_uploads"


def test_folder_collision_gets_suffix(env, session):
    s2, rep = create_application(
        env, posting_text=POSTING + "\nv2", posting_url=None, extraction=sample_extraction(),
        date_created=date(2026, 10, 11), allow_duplicate=True,
    )
    assert s2.folder == session.folder + "_2" and rep.row == 3


def test_posting_hash_normalises_whitespace_and_case():
    assert posting_hash("  Hello   World\n") == posting_hash("hello world")
    assert posting_hash("a") != posting_hash("b")


def test_find_duplicates_by_text_and_requisition(env, session):
    assert find_duplicates(env, "Totally different posting", {}) == []
    hits = find_duplicates(env, POSTING.upper(), {})
    assert [h.folder for h in hits] == [session.folder] and hits[0].reason == "same posting text"
    hits = find_duplicates(env, "other text", {"Requisition_ID": "r-12345", "Organization": "ACME CORP"})
    assert hits[0].reason == "same requisition id"
    # Same requisition id but a different organization is not a duplicate.
    assert find_duplicates(env, "other text", {"Requisition_ID": "R-12345", "Organization": "Beta"}) == []
    both = find_duplicates(env, POSTING, {"Requisition_ID": "R-12345"})
    assert both[0].reason == "same posting text + same requisition id"


def test_create_refuses_duplicate_unless_allowed(env, session):
    with pytest.raises(DuplicateError) as info:
        create_application(env, posting_text=POSTING, posting_url=None, extraction=sample_extraction())
    assert info.value.hits[0].folder == session.folder
    assert len(SessionStore(env.applications_abs).list_sessions()) == 1  # no orphan folder
    s2, _ = create_application(env, posting_text=POSTING, posting_url=None, extraction=sample_extraction(), allow_duplicate=True)
    assert s2.folder != session.folder


def test_locked_tracker_leaves_no_folder(env):
    owner = env.tracker_abs.with_name(f"~${env.tracker_abs.name}")
    owner.write_text("")
    with pytest.raises(TrackerLocked):
        create_application(env, posting_text=POSTING, posting_url=None, extraction=sample_extraction())
    assert SessionStore(env.applications_abs).list_sessions() == []


def test_all_null_folder_uses_timestamp(env):
    ex = sample_extraction(Requisition_ID=None, Organization=None, Position_Title=None)
    s, _ = create_application(env, posting_text="x", posting_url=None, extraction=ex, date_created=date(2026, 1, 2))
    parts = s.folder.split("_")
    assert parts[:4] == ["null", "null", "null", "2026-01-02"] and parts[4].isdigit()
