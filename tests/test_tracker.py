from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook

from backend.excel.tracker import BACKUP_DIR, Tracker, TrackerError, TrackerLocked

from .conftest import HEADERS, make_tracker


@pytest.fixture
def tracker(tmp_path: Path) -> Tracker:
    return Tracker(make_tracker(tmp_path / "t.xlsx"), backups_keep=2)


def _table_ref(path: Path) -> str:
    ws = load_workbook(path)["Sheet1"]
    return ws.tables["Applications"].ref


def test_headers_and_seed_row(tracker: Tracker):
    assert tracker.headers() == HEADERS
    assert tracker.read_all() == []  # seed row is empty -> not listed


def test_first_write_uses_seed_row_and_defaults(tracker: Tracker):
    rep = tracker.write_row("F1", {"Organization": "Acme", "Deadline": date(2026, 12, 1), "Position_Title": None})
    assert rep.row == 2 and rep.created
    row = tracker.read_row("F1")
    assert row["Organization"] == "Acme" and row["Deadline"] == date(2026, 12, 1)
    assert row["Application_Status"] == "Not Applied" and row["Outcome"] == "Pending"
    assert str(row["Days_Since_Applied"]).startswith("=IF(")
    assert row["Position_Title"] is None
    assert _table_ref(tracker.path) == "A1:T2"
    assert "Position_Title" not in rep.written


def test_second_folder_appends_and_extends_table(tracker: Tracker):
    tracker.write_row("F1", {"Organization": "Acme"})
    rep = tracker.write_row("F2", {"Organization": "Beta"})
    assert rep.row == 3 and rep.created
    assert _table_ref(tracker.path) == "A1:T3"
    assert [r["Folder"] for r in tracker.read_all()] == ["F1", "F2"]
    assert str(tracker.read_row("F2")["Days_Since_Applied"]).startswith("=IF(")


def test_fill_only_empty_then_force(tracker: Tracker):
    tracker.write_row("F1", {"Organization": "Acme", "Compensation": None})
    rep = tracker.write_row("F1", {"Organization": "ACME Inc", "Compensation": "$1"})
    assert not rep.created and rep.row == 2
    assert rep.written == {"Compensation": "$1"}
    assert rep.skipped == {"Organization": ("Acme", "ACME Inc")}
    assert tracker.read_row("F1")["Organization"] == "Acme"

    rep = tracker.write_row("F1", {"Organization": "ACME Inc"}, force_columns={"Organization"})
    assert rep.written == {"Organization": "ACME Inc"} and not rep.skipped
    assert tracker.read_row("F1")["Organization"] == "ACME Inc"

    # Writing the same value again is neither written nor skipped.
    rep = tracker.write_row("F1", {"Organization": "ACME Inc"})
    assert not rep.written and not rep.skipped


def test_unknown_column_is_an_error(tracker: Tracker):
    with pytest.raises(TrackerError):
        tracker.write_row("F1", {"Nope": 1})


def test_backups_are_rotated(tracker: Tracker):
    for i in range(4):
        tracker.write_row(f"F{i}", {"Organization": f"O{i}"})
    backups = list((tracker.path.parent / BACKUP_DIR).glob("t.*.xlsx"))
    assert len(backups) == 2


def test_lock_detection(tracker: Tracker):
    owner = tracker.path.with_name("~$t.xlsx")
    owner.write_text("")
    with pytest.raises(TrackerLocked):
        tracker.check_writable()
    with pytest.raises(TrackerLocked):
        tracker.write_row("F1", {"Organization": "Acme"})
    owner.unlink()
    tracker.check_writable()


def test_missing_table(tmp_path: Path):
    from openpyxl import Workbook

    p = tmp_path / "plain.xlsx"
    Workbook().save(p)
    with pytest.raises(TrackerError):
        Tracker(p).headers()
