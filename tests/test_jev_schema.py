"""Jev answers -> derive -> schema -> row values (no network)."""
from datetime import date

import pytest

from backend.config import JevSettings
from backend.jev.derive import derive
from backend.jev.questions import EXISTENCE, QUESTIONS
from backend.llm.postprocess import row_values
from backend.llm.schema_builder import FIELD_TO_COLUMN, build_schema
from backend.pipeline import derived_without_jev


def noul(p: float) -> dict:
    return {"type": "noul", "noul": p}


def choice(c: str, conf: float) -> dict:
    return {"type": "choice", "choice": c, "confidence": conf}


def answers(**over) -> dict:
    base = {k: noul(0.9) for k in EXISTENCE}
    base.update(
        is_job_posting=noul(0.97),
        work_mode=choice("remote", 0.95),
        employment_type=choice("full_time", 0.4),
        upload_mode=choice("separate_uploads", 0.8),
        requires_cover_letter=noul(0.9),
        requires_transcript=noul(0.1),
        requires_portfolio=noul(0.2),
        requires_references=noul(0.05),
    )
    base.update(over)
    return base


def test_question_set_shape():
    assert set(QUESTIONS) >= set(EXISTENCE) | {"work_mode", "employment_type", "upload_mode", "is_job_posting"}
    for q in QUESTIONS.values():
        assert q["type"] in ("noul", "choice") and q["instructions"] and q["criteria"]


def test_derive_gates_fields_and_choices():
    cfg = JevSettings()
    d = derive(answers(has_compensation=noul(0.2), has_deadline=noul(0.35)), cfg)
    assert "compensation" not in d.schema_fields  # below 0.35
    assert "deadline" in d.schema_fields  # boundary is inclusive
    assert d.direct_values == {"Work_Mode": "Remote"}  # conf 0.95 >= 0.7
    assert d.low_confidence_choices == ["employment_type"]  # conf 0.4 -> LLM enum
    assert d.upload_mode == "separate_uploads" and d.upload_mode_confidence == 0.8
    assert d.required_docs == ["CoverLetter"]
    assert not d.warnings


def test_derive_warns_on_missing_answers_and_non_posting():
    d = derive(answers(is_job_posting=noul(0.1), has_recruiter_name=None), JevSettings())
    assert any("may not be a job posting" in w for w in d.warnings)
    assert "recruiter_name" in d.schema_fields  # missing answer -> include
    assert any("no answer for has_recruiter_name" in w for w in d.warnings)


def test_schema_is_strict_and_ordered():
    d = derive(answers(has_requisition_id=noul(0.1)), JevSettings())
    schema = build_schema(d)
    fields = list(schema["properties"])
    assert fields == schema["required"]
    assert schema["additionalProperties"] is False
    assert "requisition_id" not in fields and "work_mode" not in fields
    assert fields.index("organization") < fields.index("employment_type") < fields.index("position_level")
    assert schema["properties"]["employment_type"]["anyOf"][0]["enum"][0] == "Full-time"
    for spec in schema["properties"].values():
        assert "maxItems" not in spec


def test_schema_without_jev_asks_everything():
    d = derived_without_jev()
    assert list(build_schema(d)["properties"]) == list(FIELD_TO_COLUMN)


def test_schema_with_nothing_selected_raises():
    d = derive({k: noul(0.0) for k in EXISTENCE} | {"work_mode": choice("remote", 0.9), "employment_type": choice("full_time", 0.9)}, JevSettings())
    with pytest.raises(ValueError):
        build_schema(d)


def test_row_values_merge_direct_and_llm():
    d = derive(answers(), JevSettings())
    out = row_values(d, {
        "requisition_id": " R-1 ",
        "organization": "Acme",
        "position_title": "Dev",
        "compensation": None,
        "employment_type": "Full-time",
        "deadline": "2026-12-01",
        "recruiter_name": "",
        "recruiter_contact": "x@y.z",
        "role_categories": ["Backend", " Cloud ", "Data", "ML", ""],
        "position_level": "Senior",
        "work_mode": "Hybrid",  # ignored: Jev decided Remote directly
    })
    assert out["Work_Mode"] == "Remote"
    assert out["Requisition_ID"] == "R-1"
    assert out["Compensation"] is None and out["Recruiter_Name"] is None
    assert out["Deadline"] == date(2026, 12, 1)
    assert out["Role_Categories"] == "Backend, Cloud, Data"
    assert list(out) == list(FIELD_TO_COLUMN.values())


def test_row_values_keeps_deadline_phrase():
    assert row_values(derived_without_jev(), {"deadline": "Open until filled"})["Deadline"] == "Open until filled"
