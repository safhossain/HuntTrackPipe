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
    assert _table_ref(tracker.path) == "A1:V2"
    assert "Position_Title" not in rep.written


def test_second_folder_appends_and_extends_table(tracker: Tracker):
    tracker.write_row("F1", {"Organization": "Acme"})
    rep = tracker.write_row("F2", {"Organization": "Beta"})
    assert rep.row == 3 and rep.created
    assert _table_ref(tracker.path) == "A1:V3"
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


def test_ensure_columns_appends_headers(tmp_path: Path):
    from openpyxl import Workbook
    from openpyxl.worksheet.table import Table, TableStyleInfo

    path = tmp_path / "slim.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    slim = ["Organization", "Folder", "Found_From"]
    ws.append(slim)
    ws.append(["Acme", "F1", None])
    table = Table(displayName="Applications", ref="A1:C2")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(table)
    wb.save(path)

    t = Tracker(path, backups_keep=1)
    assert t.ensure_columns(["Location_Country", "Location_City"]) == ["Location_Country", "Location_City"]
    assert t.headers() == slim + ["Location_Country", "Location_City"]
    assert _table_ref(path) == "A1:E2"
    assert t.ensure_columns(["Location_Country", "Location_City"]) == []  # idempotent
    t.write_row("F1", {"Location_Country": "Canada", "Location_City": "Toronto"})
    row = t.read_row("F1")
    assert row["Location_Country"] == "Canada" and row["Location_City"] == "Toronto"


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


def test_sync_list_validations_by_header(tracker: Tracker):
    touched = tracker.sync_list_validations({
        "Applied_Through": ["Org-Portal", "Lever"],
        "Found_From": ["HiringCafe", "Referral"],
        "Missing_Col": ["Nope"],  # ignored
    })
    assert set(touched) == {"Applied_Through", "Found_From"}
    wb = load_workbook(tracker.path)
    dvs = {str(dv.sqref): dv.formula1 for dv in wb.active.data_validations.dataValidation}
    assert any("Lever" in f for f in dvs.values())
    assert any("Referral" in f for f in dvs.values())
    # Table body only (seed data row 2) — not whole-column to 1048576.
    assert all("1048576" not in str(ref) for ref in dvs)
    assert any(str(ref).endswith("2") for ref in dvs)

    # Reinforced on write_row in the same save.
    tracker.write_row("F1", {"Organization": "Acme"}, list_options={"Application_Status": ["Not Applied", "Offer-Stage"]})
    wb = load_workbook(tracker.path)
    formulas = [dv.formula1 for dv in wb.active.data_validations.dataValidation]
    assert any("Offer-Stage" in f for f in formulas)


def test_clear_column_body(tracker: Tracker):
    tracker.write_row("F1", {"Employment_Type": "Permanent Full-time"})
    assert tracker.read_row("F1").get("Employment_Type") == "Permanent Full-time"
    cleared = tracker.clear_column_body("Employment_Type")
    assert cleared >= 1
    assert tracker.read_row("F1").get("Employment_Type") in (None, "")


def test_list_validation_rejects_comma_and_overlong(tracker: Tracker):
    with pytest.raises(TrackerError, match="commas"):
        tracker.sync_list_validations({"Applied_Through": ["A,B"]})
    with pytest.raises(TrackerError, match="too long"):
        tracker.sync_list_validations({"Applied_Through": ["x" * 256]})


def test_read_list_options_roundtrip(tracker: Tracker):
    tracker.sync_list_validations({"Found_From": ["HiringCafe", "Referral"]})
    got = tracker.read_list_options(["Found_From", "Applied_Through"])
    assert got["Found_From"] == ["HiringCafe", "Referral"]
    assert got["Applied_Through"] is None  # no DV on that column yet


def test_parse_list_formula_strips_excel_spaces():
    from backend.excel.tracker import parse_list_formula

    # Excel UI often writes "a, b, c"; HTP writes "a,b,c". Both must compare equal.
    spaced = parse_list_formula('"Not Applied, Applied, Recruiter-Screening"')
    tight = parse_list_formula('"Not Applied,Applied,Recruiter-Screening"')
    assert spaced == ["Not Applied", "Applied", "Recruiter-Screening"]
    assert spaced == tight


def test_dropdown_compare_and_cache(env):
    from backend.columns import DEFAULT_OPTIONS, editable_list_options
    from backend.excel.dropdown_sync import compare_dropdowns, dropdown_cache

    dropdown_cache.clear()
    opts = {k: list(DEFAULT_OPTIONS[k]) for k in ("Application_Status", "Applied_Through", "Found_From")}
    Tracker(env.tracker_abs, backups_keep=2).sync_list_validations(opts)

    a = compare_dropdowns(env, locked=False, force=True)
    assert a.status == "in_sync"
    b = compare_dropdowns(env, locked=False, force=False)
    assert b.status == "in_sync" and b.checked_at == a.checked_at  # cache hit

    locked = compare_dropdowns(env, locked=True)
    assert locked.status == "locked"

    Tracker(env.tracker_abs, backups_keep=2).sync_list_validations({"Found_From": ["X"]})
    dropdown_cache.clear()
    c = compare_dropdowns(env, locked=False, force=True)
    assert c.status == "mismatched"
    assert any(d.column == "Found_From" and d.changed for d in c.columns)
    assert editable_list_options(env)["Found_From"] != ["X"]
