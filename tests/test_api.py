"""API smoke tests with FastAPI's TestClient. Jev / Claude are replaced by fakes."""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import config as config_mod
from backend.api.routers import extract as extract_router
from backend.api.routers import qa as qa_router
from backend.api.routers import sessions as sessions_router
from backend.llm.client import LLMResult
from backend.main import app
from backend.pipeline import Extraction
from backend.sessions.models import JevDerived, JevRecord, LLMRecord

from .conftest import POSTING, sample_extraction
from .test_files import pdf_bytes


@pytest.fixture
def client(env):
    with TestClient(app) as c:
        yield c


def fake_extract(values_override: dict | None = None):
    def _extract(text, cfg, *, use_jev=True, use_llm=True):
        ex = sample_extraction(**(values_override or {}))
        if use_jev:
            ex.jev = JevRecord(model="jev-test", answers={}, derived=ex.derived)
        if use_llm:
            ex.llm = LLMRecord(model="claude-test", output={"organization": ex.values["Organization"]})
        return ex

    return _extract


def _payload(client, text=POSTING, **manual) -> dict:
    ex = client.post("/api/extract", json={"posting_text": text}).json()
    return {"posting_text": text, "posting_url": "https://jobs.example/1", "extraction": ex, "manual": manual}


def test_health_meta_settings(client):
    assert client.get("/api/health").json()["ok"] is True
    meta = client.get("/api/meta").json()
    assert meta["extracted_columns"][0] == "Requisition_ID" and "upload_modes" in meta
    s = client.get("/api/settings").json()
    assert s["config"]["candidate_name"] == "Test Candidate" and s["tracker_exists"] is True
    assert set(s["keys"]) == {"TYPESAFE_API_KEY", "ANTHROPIC_API_KEY"}
    assert s["paths"]["config_path"].endswith("htp.config.json")


def test_extract_rejects_empty(client):
    assert client.post("/api/extract", json={"posting_text": "  "}).status_code == 400


def test_create_duplicate_and_reextract_flow(client, env, monkeypatch):
    monkeypatch.setattr(extract_router, "extract", fake_extract())
    monkeypatch.setattr(sessions_router, "extract", fake_extract({"Compensation": "CAD 150,000 / year", "Position_Level": "Staff"}))

    ex = client.post("/api/extract", json={"posting_text": POSTING}).json()
    assert ex["values"]["Organization"] == "Acme Corp" and ex["duplicates"] == []

    r = client.post("/api/sessions", json=_payload(client, Applied_Date="2026-10-11", Applied_Through="LinkedIn"))
    assert r.status_code == 200, r.text
    body = r.json()
    folder = body["session"]["folder"]
    assert body["report"]["row"] == 2 and body["report"]["created"]
    assert body["session"]["posting"]["hash"]

    # Second extract of the same text now reports the duplicate; create refuses it.
    ex2 = client.post("/api/extract", json={"posting_text": POSTING}).json()
    assert [d["folder"] for d in ex2["duplicates"]] == [folder]
    r = client.post("/api/sessions", json=_payload(client))
    assert r.status_code == 409 and r.json()["type"] == "DuplicateError"
    assert r.json()["duplicates"][0]["folder"] == folder
    r = client.post("/api/sessions", json={**_payload(client), "allow_duplicate": True})
    assert r.status_code == 200 and r.json()["session"]["folder"] == folder + "_2"

    lst = client.get("/api/sessions").json()
    assert [s["folder"] for s in lst["sessions"]] == [folder, folder + "_2"]
    assert lst["sessions"][0]["row"]["Applied_Date"] == "2026-10-11"

    detail = client.get(f"/api/sessions/{folder}").json()
    assert detail["row"]["Organization"] == "Acme Corp" and detail["row_error"] is None
    assert client.get("/api/sessions/nope").status_code == 404

    # Re-extract: diff against the Excel row; nothing written yet.
    r = client.post(f"/api/sessions/{folder}/reextract", json={"use_jev": True, "use_llm": True})
    assert r.status_code == 200, r.text
    diff = {d["column"]: d for d in r.json()["diff"]}
    assert diff["Compensation"]["changed"] and diff["Compensation"]["proposed"] == "CAD 150,000 / year"
    assert diff["Position_Level"]["changed"] and diff["Organization"]["changed"] is False
    assert diff["Deadline"]["current"] == "2026-12-01" and not diff["Deadline"]["changed"]
    assert client.get(f"/api/sessions/{folder}").json()["row"]["Compensation"] == "CAD 140,000-160,000 / year"
    assert client.get(f"/api/sessions/{folder}").json()["session"]["llm"]["model"] == "claude-test"

    # Apply one column via force_columns.
    r = client.put(f"/api/sessions/{folder}/row", json={"values": {"Compensation": "CAD 150,000 / year"}, "force_columns": ["Compensation"]})
    assert r.status_code == 200 and r.json()["report"]["written"] == {"Compensation": "CAD 150,000 / year"}
    assert r.json()["row"]["Compensation"] == "CAD 150,000 / year"
    # Without force, a differing non-empty cell is skipped, not overwritten.
    r = client.put(f"/api/sessions/{folder}/row", json={"values": {"Compensation": "other"}})
    assert r.json()["report"]["skipped"] == {"Compensation": ["CAD 150,000 / year", "other"]}


def test_locked_tracker_sets_pending_write_and_retry(client, env, monkeypatch):
    monkeypatch.setattr(extract_router, "extract", fake_extract())
    folder = client.post("/api/sessions", json=_payload(client)).json()["session"]["folder"]
    owner = env.tracker_abs.with_name(f"~${env.tracker_abs.name}")
    owner.write_text("")
    r = client.put(f"/api/sessions/{folder}/row", json={"values": {"Recruiter_Name": "Someone"}, "force_columns": ["Recruiter_Name"]})
    assert r.status_code == 423
    pend = client.get(f"/api/sessions/{folder}").json()["session"]["review"]["pending_write"]
    assert pend == {"values": {"Recruiter_Name": "Someone"}, "force_columns": ["Recruiter_Name"]}
    assert client.get("/api/sessions").json()["sessions"][0]["pending_write"] is True
    assert client.post(f"/api/sessions/{folder}/row/retry").status_code == 423
    owner.unlink()
    r = client.post(f"/api/sessions/{folder}/row/retry")
    assert r.status_code == 200 and r.json()["row"]["Recruiter_Name"] == "Someone"
    assert client.get(f"/api/sessions/{folder}").json()["session"]["review"]["pending_write"] is None
    assert client.post(f"/api/sessions/{folder}/row/retry").status_code == 400


def test_files_endpoints(client, env, monkeypatch):
    monkeypatch.setattr(extract_router, "extract", fake_extract())
    folder = client.post("/api/sessions", json=_payload(client)).json()["session"]["folder"]
    base = f"/api/sessions/{folder}/files"
    r = client.post(base, files=[("files", ("Resume.pdf", pdf_bytes(2, "r"), "application/pdf")),
                                 ("files", ("cover letter.pdf", pdf_bytes(1, "c"), "application/pdf"))])
    assert r.status_code == 200, r.text
    view = r.json()
    assert [i["file"] for i in view["files"]["inputs"]] == ["0_Resume.pdf", "1_cover-letter.pdf"]
    assert view["x"] == "R-12345" and view["required_docs"] == ["CoverLetter"] and view["upload_mode"] == "separate_uploads"

    assert client.put(f"{base}/order", json={"order": [1, 0]}).json()["files"]["inputs"][0]["file"] == "0_cover-letter.pdf"
    r = client.post(f"{base}/final", json={"indices": [0, 1]})
    assert sorted(f["file"] for f in r.json()["files"]["finals"]) == ["Test-Candidate_CoverLetter_R-12345.pdf", "Test-Candidate_Resume_R-12345.pdf"]
    r = client.post(f"{base}/combine", json={"indices": None})
    assert r.json()["files"]["combined"]["pages"] == 3
    assert client.get(f"{base}/thumb/0_cover-letter.pdf?width=100").headers["content-type"] == "image/png"
    assert client.get(f"{base}/download/Test-Candidate_R-12345.pdf").status_code == 200
    assert client.get(f"{base}/download/..%5Csession.json").status_code in (400, 404)
    assert client.put(f"{base}/upload-mode", json={"upload_mode": "single_combined_file"}).json()["upload_mode_source"] == "user"
    assert client.delete(f"{base}/1").json()["files"]["inputs"].__len__() == 1
    assert client.get("/api/files/tools").status_code == 200


def test_qa_endpoints(client, env, monkeypatch):
    monkeypatch.setattr(extract_router, "extract", fake_extract())
    folder = client.post("/api/sessions", json=_payload(client)).json()["session"]["folder"]
    base = f"/api/sessions/{folder}/qa"

    class FakeClaude:
        def __init__(self, cfg):
            pass

        def structured(self, *, model, system, user, schema, max_tokens=None):
            ids = schema["properties"]["answers"]["items"]["properties"]["id"]["enum"]
            return LLMResult(model=model, output={"answers": [{"id": i, "answer": "I am a good fit."} for i in ids]}, usage={"input_tokens": 1, "output_tokens": 1})

    monkeypatch.setattr(qa_router, "ClaudeClient", FakeClaude)

    view = client.get(base).json()
    assert view["candidate_context_exists"] and view["organization"] == "Acme Corp" and view["qa"]["questions"] == []
    r = client.post(f"{base}/questions", json={"questions": [{"text": "Why us?", "limit": {"unit": "words", "value": 50}}, {"text": "Why you?"}]})
    ids = [q["id"] for q in r.json()["qa"]["questions"]]
    assert len(ids) == 2
    r = client.post(f"{base}/answer", json={"ids": None})
    assert r.status_code == 200, r.text
    assert all(q["status"] == "answered" and q["answer"] == "I am a good fit." for q in r.json()["qa"]["questions"])
    assert r.json()["answers_md"] == "answers.md"
    r = client.put(f"{base}/questions/{ids[0]}", json={"answer": "Typed by hand."})
    assert r.json()["qa"]["questions"][0]["model"] == "manual"
    r = client.put(f"{base}/questions/order", json={"order": [ids[1], ids[0]]})
    assert [q["id"] for q in r.json()["qa"]["questions"]] == [ids[1], ids[0]]
    assert client.delete(f"{base}/questions/{ids[1]}").json()["qa"]["questions"].__len__() == 1

    env.candidate_context_abs.unlink()
    assert client.post(f"{base}/answer", json={"ids": None}).status_code == 412


def test_settings_update_and_logs(client, env):
    r = client.put("/api/settings", json={"config": {"candidate_name": "New Name", "jev": {"noul_include_threshold": 0.5}}})
    assert r.status_code == 200, r.text
    assert r.json()["config"]["candidate_name"] == "New Name"
    assert r.json()["config"]["jev"]["noul_include_threshold"] == 0.5
    assert r.json()["config"]["jev"]["model"] == "jev-1.13.0"  # untouched keys survive the merge
    on_disk = json.loads(config_mod.CONFIG_PATH.read_text(encoding="utf-8"))
    assert on_disk["candidate_name"] == "New Name" and "\\" not in on_disk["applications_dir"]
    assert config_mod.settings().candidate_name == "New Name"  # cache cleared

    r = client.put("/api/settings", json={"config": {"backups_keep": "lots"}})
    assert r.status_code == 400 and "backups_keep" in r.json()["detail"]

    logs = client.get("/api/logs?lines=50").json()
    assert logs["path"].endswith("htp.log")
    assert any("settings updated" in ln for ln in logs["lines"])
