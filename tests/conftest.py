"""Shared fixtures: every test runs against a throw-away Applications dir,
a synthetic tracker workbook and a config file under pytest's tmp_path.

``HTP_CONFIG`` is pointed at a scratch config *before* ``backend`` is imported
so the module-level ``CONFIG_PATH`` already refers to it. The ``env`` fixture
rewrites that file per test and clears the ``settings()`` cache.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path

import pytest

_SCRATCH = Path(tempfile.mkdtemp(prefix="htp_tests_"))
os.environ["HTP_CONFIG"] = str(_SCRATCH / "htp.config.json")
atexit.register(shutil.rmtree, _SCRATCH, True)

from openpyxl import Workbook  # noqa: E402
from openpyxl.worksheet.table import Table, TableStyleInfo  # noqa: E402

from backend import config as config_mod  # noqa: E402
from backend.config import Settings  # noqa: E402
from backend.excel.tracker import FORMULA_COLS  # noqa: E402
from backend.pipeline import Extraction, create_application  # noqa: E402
from backend.sessions.models import JevDerived  # noqa: E402

HEADERS = [
    "Requisition_ID", "Organization", "Position_Title", "Compensation", "Work_Mode", "Employment_Type",
    "Deadline", "Applied_Date", "Posting_URL", "Application_Status", "Recruiter_Name", "Recruiter_Contact",
    "Outcome", "Role_Categories", "Position_Level", "Days_Since_Applied", "Applied_Through", "Confirmation_#",
    "Folder",
]
POSTING = """Senior Backend Engineer - Acme Corp
Req ID: R-12345
Acme Corp is hiring a Senior Backend Engineer (remote, full-time).
Salary CAD 140,000-160,000 per year. Apply by 2026-12-01.
Contact: Jane Doe, jane.doe@acme.example
Please upload a resume and a cover letter as separate files.
"""


def make_tracker(path: Path) -> Path:
    """Minimal clone of the real tracker: 19 headers, table ``Applications`` over A1:S2,
    one empty seed row carrying the Days_Since_Applied formula."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(HEADERS)
    ws.cell(2, HEADERS.index("Days_Since_Applied") + 1).value = FORMULA_COLS["Days_Since_Applied"]
    table = Table(displayName="Applications", ref="A1:S2")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(table)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def write_config(path: Path, root: Path, **extra) -> dict:
    data = {
        "applications_dir": (root / "Applications").as_posix(),
        "tracker_path": (root / "Applications" / "tracker.xlsx").as_posix(),
        "candidate_name": "Test Candidate",
        "candidate_context_path": (root / "candidate_context.txt").as_posix(),
        "backups_keep": 3,
        **extra,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


@pytest.fixture
def env(tmp_path: Path) -> Settings:
    """Fresh Applications dir + tracker + config; returns the active ``Settings``."""
    make_tracker(tmp_path / "Applications" / "tracker.xlsx")
    (tmp_path / "candidate_context.txt").write_text(
        "Software developer with 4 years of Python and FastAPI experience. Built a job tracker.\n", encoding="utf-8"
    )
    write_config(config_mod.CONFIG_PATH, tmp_path)
    config_mod.settings.cache_clear()
    cfg = config_mod.settings()
    yield cfg
    config_mod.settings.cache_clear()


def sample_extraction(**overrides) -> Extraction:
    values = {
        "Requisition_ID": "R-12345",
        "Organization": "Acme Corp",
        "Position_Title": "Senior Backend Engineer",
        "Compensation": "CAD 140,000-160,000 / year",
        "Work_Mode": "Remote",
        "Employment_Type": "Full-time",
        "Deadline": date(2026, 12, 1),
        "Recruiter_Name": "Jane Doe",
        "Recruiter_Contact": "jane.doe@acme.example",
        "Role_Categories": "Backend, Cloud",
        "Position_Level": "Senior",
    }
    values.update(overrides)
    return Extraction(derived=JevDerived(upload_mode="separate_uploads", required_docs=["CoverLetter"]), values=values)


@pytest.fixture
def session(env: Settings):
    """One created application (folder + session.json + Excel row 2)."""
    s, report = create_application(
        env, posting_text=POSTING, posting_url="https://jobs.example/r-12345", extraction=sample_extraction(),
        manual={"Applied_Through": "LinkedIn"}, date_created=date(2026, 10, 11),
    )
    return s
