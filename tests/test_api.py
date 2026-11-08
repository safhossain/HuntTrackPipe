"""API smoke tests with FastAPI's TestClient and fake provider responses."""
import json
import subprocess
import sys
from datetime import date
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import config as config_mod
from backend.api.routers import extract as extract_router
from backend.api.routers import qa as qa_router
from backend.api.routers import sessions as sessions_router
from backend.duplicates import posting_hash
from backend.llm.client import LLMResult
from backend.main import app
from backend.pipeline import Extraction
from backend.sessions import store as session_store
from backend.sessions.models import JevDerived, JevRecord, LLMRecord

from .conftest import POSTING, sample_extraction
from .test_files import pdf_bytes, png_bytes


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


def _credit_after_restart(provider):
    code = (
        "from backend.config import settings\n"
        f"from backend.llm.client import {provider}_credit_low\n"
        f"print({provider}_credit_low(settings()))"
    )
    return subprocess.check_output(
        [sys.executable, "-c", code],
        cwd=config_mod.REPO_ROOT,
        text=True,
        timeout=10,
    ).strip()


def _openai_rate_limit(code):
    from openai import RateLimitError

    response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    return RateLimitError(code, response=response, body={"code": code, "type": "insufficient_quota"})


def test_health_meta_settings(client):
    assert client.get("/api/health").json()["ok"] is True
    meta = client.get("/api/meta").json()
    assert meta["extracted_columns"][0] == "Requisition_ID" and "upload_modes" in meta
    assert set(meta["editable_option_columns"]) == {"Application_Status", "Applied_Through", "Found_From"}
    assert "LinkedIn" in meta["options"]["Applied_Through"]
    s = client.get("/api/settings").json()
    assert s["config"]["candidate_name"] == "Test Candidate" and s["tracker_exists"] is True
    assert set(s["keys"]) == {"TYPESAFE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"}
    assert s["config"]["llm"]["extract_provider"] == "anthropic"
    assert s["config"]["openai"]["qa_model"] == "gpt-6-luna"
    assert s["paths"]["config_path"].endswith("htp.config.json")


def test_extract_rejects_empty(client):
    assert client.post("/api/extract", json={"posting_text": "  "}).status_code == 400


def test_claude_credit_status_survives_restart_and_recovery(client, env, session, monkeypatch):
    import anthropic

    key_name = "ANTHROPIC_API_KEY"
    key = "test-claude-key-with-low-credit"
    low_credit_message = "Your credit balance is too low to access the Anthropic API."
    monkeypatch.setenv(key_name, key)
    fingerprint = sha256(key.encode("utf-8")).hexdigest()
    marker = env.applications_abs / ".htp_state" / f"claude-low-credit-{fingerprint}"
    calls = []
    failure = None

    def provider_error(status, message):
        response = httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
        return anthropic.APIStatusError(message, response=response, body={"error": {"message": message}})

    def create(**kwargs):
        calls.append(kwargs["model"])
        if failure is not None:
            raise failure
        ids = kwargs["output_config"]["format"]["schema"]["properties"]["answers"]["items"]["properties"]["id"]["enum"]
        text = json.dumps({"answers": [{"id": qid, "answer": "I built a job tracker."} for qid in ids]})
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])

    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: SimpleNamespace(messages=SimpleNamespace(create=create)))

    def credit_low():
        return client.get("/api/tracker/status").json()["claude_credit_low"]

    def extract():
        return client.post("/api/extract", json={"posting_text": POSTING, "use_jev": False})

    assert credit_low() is False and calls == []
    for status, message in [(400, "Invalid structured output schema."), (429, low_credit_message)]:
        failure = provider_error(status, message)
        assert extract().status_code == 502
        assert credit_low() is False

    failure = provider_error(400, low_credit_message)
    response = extract()
    assert response.status_code == 502 and low_credit_message in response.json()["detail"]
    assert credit_low() is True
    assert client.get("/api/settings").json()["tracker_status"]["claude_credit_low"] is True
    assert marker.read_bytes() == b""
    assert _credit_after_restart("claude") == "True"
    assert len(calls) == 6  # each failure gets the existing retry; status reads make no calls

    failure = provider_error(429, "Rate limit reached.")
    assert extract().status_code == 502 and credit_low() is True
    with monkeypatch.context() as patch:
        patch.setenv(key_name, "test-other-claude-key")
        assert credit_low() is False
        patch.delenv(key_name)
        assert credit_low() is False
    assert credit_low() is True

    failure = None
    qa_url = f"/api/sessions/{session.folder}/qa"
    assert client.post(f"{qa_url}/questions", json={"questions": [{"text": "What did you build?"}]}).status_code == 200
    assert client.post(f"{qa_url}/answer", json={}).status_code == 200
    assert credit_low() is False
    assert not marker.exists()
    assert _credit_after_restart("claude") == "False"


def test_openai_extraction_and_credit_status(client, session, monkeypatch):
    import anthropic
    import openai

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    openai_calls, claude_calls = [], []
    failure = None

    def openai_create(**kwargs):
        openai_calls.append(kwargs)
        if failure is not None:
            raise failure
        fields = kwargs["text"]["format"]["schema"]["required"]
        output = {**dict.fromkeys(fields), "organization": "OpenAI extracted", "subrole_categories": ["FastAPI"]}
        usage = SimpleNamespace(input_tokens=120, output_tokens=28)
        return SimpleNamespace(model="gpt-6-luna-snapshot", status="completed", output_text=json.dumps(output), usage=usage)

    def claude_create(**kwargs):
        claude_calls.append(kwargs["model"])
        pytest.fail("OpenAI was selected for extraction")

    monkeypatch.setattr(openai, "OpenAI", lambda **_: SimpleNamespace(responses=SimpleNamespace(create=openai_create)))
    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: SimpleNamespace(messages=SimpleNamespace(create=claude_create)))

    def extract():
        return client.post("/api/extract", json={"posting_text": POSTING, "use_jev": False})

    settings = client.put("/api/settings", json={"config": {"llm": {"extract_provider": "openai"}}})
    assert settings.status_code == 200, settings.text
    assert settings.json()["keys"]["OPENAI_API_KEY"] is True
    assert settings.json()["tracker_status"]["openai_credit_low"] is False

    response = extract()
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["values"]["Organization"] == "OpenAI extracted"
    assert result["values"]["Subrole_Categories"] == "FastAPI"
    assert result["llm"]["model"] == "gpt-6-luna-snapshot"
    assert result["llm"]["usage"] == {"input_tokens": 120, "output_tokens": 28}
    request, = openai_calls
    assert request["model"] == "gpt-6-luna" and request["reasoning"] == {"effort": "none"}
    assert request["max_output_tokens"] == 2048 and request["store"] is False
    assert request["text"]["format"] == {
        "type": "json_schema", "name": "structured_output", "schema": result["llm"]["schema"], "strict": True,
    }
    assert POSTING.strip() in request["input"] and claude_calls == []

    failure = _openai_rate_limit("insufficient_quota")
    assert extract().status_code == 502
    assert client.get("/api/tracker/status").json()["openai_credit_low"] is False

    failure = _openai_rate_limit("credit_balance_exhausted")
    assert extract().status_code == 502
    status = client.get("/api/tracker/status").json()
    assert status["openai_credit_low"] is True and status["claude_credit_low"] is False
    assert len(openai_calls) == 4  # ordinary failure retries; credit depletion does not
    assert _credit_after_restart("openai") == "True"

    failure = None
    reextract = client.post(f"/api/sessions/{session.folder}/reextract", json={"use_jev": False})
    assert reextract.status_code == 200, reextract.text
    assert reextract.json()["extraction"]["values"]["Organization"] == "OpenAI extracted"
    assert client.get("/api/tracker/status").json()["openai_credit_low"] is False
    assert _credit_after_restart("openai") == "False"


def test_openai_qa_batches_checks_limits_and_regenerates(client, session, monkeypatch):
    import anthropic
    import openai

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-qa-key")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: pytest.fail("OpenAI was selected for Q&A"))
    calls = []
    failure = _openai_rate_limit("credit_balance_exhausted")

    def create(**kwargs):
        if failure is not None:
            raise failure
        output_format = kwargs["text"]["format"]
        ids = output_format["schema"]["properties"]["answers"]["items"]["properties"]["id"]["enum"]
        calls.append((kwargs, ids))
        if len(ids) == 2:
            answers = ["I built the tracker.", "Immediately."]
        elif "revision feedback" in kwargs["input"]:
            answers = ["I tested it."]
        else:
            answers = ["I built it."]
        output = {"answers": [{"id": qid, "answer": answer} for qid, answer in zip(ids, answers)]}
        usage = SimpleNamespace(input_tokens=30, output_tokens=10)
        return SimpleNamespace(model=kwargs["model"], status="completed", output_text=json.dumps(output), usage=usage)

    monkeypatch.setattr(openai, "OpenAI", lambda **_: SimpleNamespace(responses=SimpleNamespace(create=create)))
    response = client.put("/api/settings", json={"config": {
        "llm": {"extract_provider": "openai"}, "openai": {"qa_model": "test-qa-model", "max_tokens": 512},
    }})
    assert response.status_code == 200, response.text

    qa_url = f"/api/sessions/{session.folder}/qa"
    response = client.post(f"{qa_url}/questions", json={"questions": [
        {"text": "What did you build?", "limit": {"unit": "words", "value": 3}}, {"text": "When can you start?"},
    ]})
    ids = [q["id"] for q in response.json()["qa"]["questions"]]
    failed = client.post(f"{qa_url}/answer", json={})
    assert failed.status_code == 502 and failed.json()["detail"].startswith("OpenAI call failed")
    assert client.get("/api/tracker/status").json()["openai_credit_low"] is True

    failure = None
    answered = client.post(f"{qa_url}/answer", json={})
    assert answered.status_code == 200, answered.text
    qa = answered.json()["qa"]
    assert [q["answer"] for q in qa["questions"]] == ["I built it.", "Immediately."]
    assert all(q["model"] == "test-qa-model" and q["status"] == "answered" for q in qa["questions"])
    assert qa["usage"] == {"input_tokens": 60, "output_tokens": 20}
    assert [target_ids for _, target_ids in calls] == [ids, ids[:1]]
    assert [request["max_output_tokens"] for request, _ in calls] == [1824, 1424]
    assert calls[0][0]["text"]["format"]["strict"] is True
    assert "rewrite so it is at most 3 words" in calls[1][0]["input"]
    assert client.get("/api/tracker/status").json()["openai_credit_low"] is False

    revised = client.post(f"{qa_url}/regenerate/{ids[0]}", json={"feedback": "Mention testing."})
    assert revised.status_code == 200, revised.text
    qa = revised.json()["qa"]
    assert [q["answer"] for q in qa["questions"]] == ["I tested it.", "Immediately."]
    assert qa["usage"] == {"input_tokens": 90, "output_tokens": 30}
    assert calls[2][1] == ids[:1] and "revision feedback from the candidate: Mention testing." in calls[2][0]["input"]


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

    # Explicit duplicate endpoint: new req id + today's date in the folder name.
    r = client.post(
        f"/api/sessions/{folder}/duplicate",
        json={"values": {"Requisition_ID": "JR-99999", "Applied_Date": "2026-11-02", "Application_Status": "Not Applied", "Outcome": "Pending"}},
    )
    assert r.status_code == 200, r.text
    dup_folder = r.json()["session"]["folder"]
    assert dup_folder.startswith("JR-99999_Acme-Corp_") and dup_folder != folder
    assert r.json()["session"]["posting"]["hash"] == body["session"]["posting"]["hash"]
    assert r.json()["session"]["files"]["inputs"] == []
    assert r.json()["report"]["created"] is True

    lst = client.get("/api/sessions").json()
    folders = [s["folder"] for s in lst["sessions"]]
    assert folder in folders and folder + "_2" in folders and dup_folder in folders
    assert next(s["row"]["Applied_Date"] for s in lst["sessions"] if s["folder"] == folder) == "2026-10-11"

    detail = client.get(f"/api/sessions/{folder}").json()
    assert detail["row"]["Organization"] == "Acme Corp" and detail["row_error"] is None
    assert detail["session"]["review"]["compensation_estimated"] is False
    fr = client.put(f"/api/sessions/{folder}/flags", json={"compensation_estimated": True})
    assert fr.status_code == 200 and fr.json()["compensation_estimated"] is True
    assert client.get(f"/api/sessions/{folder}").json()["session"]["review"]["compensation_estimated"] is True
    nr = client.put(f"/api/sessions/{folder}/notes", json={"notes": "follow up Tuesday"})
    assert nr.status_code == 200 and nr.json()["notes"] == "follow up Tuesday"
    assert client.get(f"/api/sessions/{folder}").json()["session"]["notes"] == "follow up Tuesday"
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


def test_edit_posting_preserves_raw_text_and_reextracts_from_it(client, env, monkeypatch):
    monkeypatch.setattr(extract_router, "extract", fake_extract())
    extract_calls = []

    def record_extract(text, cfg, **kwargs):
        extract_calls.append(text)
        return fake_extract()(text, cfg, **kwargs)

    monkeypatch.setattr(sessions_router, "extract", record_extract)
    folder = client.post("/api/sessions", json=_payload(client)).json()["session"]["folder"]
    base = f"/api/sessions/{folder}"
    original = client.get(base).json()
    store = session_store.SessionStore(env.applications_abs)
    stale = store.load(folder)
    posting_file = env.applications_abs / folder / session_store.POSTING_FILE
    new_text = "  Updated posting — junior engineer\n\n  Keep this indentation.\n  "

    response = client.put(f"{base}/posting", json={"text": new_text})
    assert response.status_code == 200, response.text
    posting = {**original["session"]["posting"], "text": new_text, "hash": posting_hash(new_text)}
    assert response.json() == posting
    expected = {**original, "session": {**original["session"], "posting": posting}}
    assert client.get(base).json() == expected
    assert posting_file.read_bytes() == new_text.encode("utf-8")
    assert extract_calls == []

    assert client.put(f"{base}/posting", json={"text": " \n\t "}).status_code == 400
    assert client.get(base).json() == expected
    assert posting_file.read_bytes() == new_text.encode("utf-8")

    outside = session_store.SessionStore(env.applications_abs.parent)
    outside.create(stale.model_copy(update={"folder": "outside"}))
    assert client.put("/api/sessions/..%5Coutside/posting", json={"text": new_text}).status_code == 404
    assert outside.load("outside").posting.text == original["session"]["posting"]["text"]

    stale.notes = "Saved after the posting edit."
    store.save(stale)
    assert client.get(base).json()["session"]["posting"] == posting
    assert client.get(base).json()["session"]["notes"] == stale.notes
    assert client.post(f"{base}/reextract", json={}).status_code == 200
    assert extract_calls == [new_text]


def test_edit_posting_restores_file_if_session_save_fails(client, env, monkeypatch):
    monkeypatch.setattr(extract_router, "extract", fake_extract())
    folder = client.post("/api/sessions", json=_payload(client)).json()["session"]["folder"]
    base = f"/api/sessions/{folder}"
    original = client.get(base).json()
    posting_file = env.applications_abs / folder / session_store.POSTING_FILE
    original_bytes = posting_file.read_bytes()
    replace = session_store.os.replace

    def fail_session_replace(src, dst):
        if dst.name == session_store.SESSION_FILE:
            raise PermissionError("Session file is locked.")
        return replace(src, dst)

    with monkeypatch.context() as patch:
        patch.setattr(session_store.os, "replace", fail_session_replace)
        with pytest.raises(PermissionError, match="Session file is locked"):
            client.put(f"{base}/posting", json={"text": "Updated posting"})

    assert posting_file.read_bytes() == original_bytes
    assert client.get(base).json() == original


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
    # convert-all-pdf: only PDFs left -> 400; with a PNG it appends a new PDF
    assert client.post(f"{base}/convert-all-pdf").status_code == 400
    assert client.post(base, files=[("files", ("shot.png", png_bytes(), "image/png"))]).status_code == 200
    r = client.post(f"{base}/convert-all-pdf")
    assert r.status_code == 200, r.text
    names = [i["file"] for i in r.json()["files"]["inputs"]]
    assert any(n.endswith(".pdf") and "shot" in n.lower() for n in names)
    assert client.get("/api/files/tools").status_code == 200
    # standalone multi → PDF
    r = client.post(
        "/api/files/convert-all-pdf",
        files=[
            ("files", ("a.png", png_bytes(), "image/png")),
            ("files", ("b.pdf", pdf_bytes(1, "b"), "application/pdf")),
        ],
    )
    assert r.status_code == 200 and "zip" in (r.headers.get("content-type") or "")


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

    monkeypatch.setattr(qa_router, "selected_client", FakeClaude)

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


def test_add_option_persists_and_syncs_excel(client, env):
    from backend.excel.tracker import Tracker

    r = client.post("/api/meta/options/Applied_Through", json={"value": "Lever"})
    assert r.status_code == 200, r.text
    body = r.json()
    expected = ["AshbyHQ", "Email", "Greenhouse", "Indeed", "Lever", "LinkedIn", "Org-Portal", "UltiPro", "Workday", "Other"]
    assert body["value"] == "Lever" and body["excel_synced"] is True
    assert body["options"]["Applied_Through"] == expected
    # First add seeds all three editable lists into config.
    on_disk = json.loads(config_mod.CONFIG_PATH.read_text(encoding="utf-8"))
    assert on_disk["options"]["Applied_Through"][-1] == "Lever"
    assert "Application_Status" in on_disk["options"] and "Found_From" in on_disk["options"]
    assert client.get("/api/meta").json()["options"]["Applied_Through"] == expected
    assert Tracker(env.tracker_abs).read_list_options(["Applied_Through"])["Applied_Through"] == expected

    assert client.post("/api/meta/options/Applied_Through", json={"value": "Lever"}).status_code == 409
    assert client.post("/api/meta/options/Outcome", json={"value": "Maybe"}).status_code == 400
    assert client.post("/api/meta/options/Applied_Through", json={"value": "A,B"}).status_code == 400


def test_add_option_defers_excel_when_locked(client, env):
    owner = env.tracker_abs.with_name(f"~${env.tracker_abs.name}")
    owner.write_text("")
    try:
        r = client.post("/api/meta/options/Found_From", json={"value": "Referral"})
        assert r.status_code == 200, r.text
        assert r.json()["excel_synced"] is False and r.json()["excel_error"]
        assert "Referral" in r.json()["options"]["Found_From"]
        assert "Referral" in json.loads(config_mod.CONFIG_PATH.read_text(encoding="utf-8"))["options"]["Found_From"]
    finally:
        owner.unlink(missing_ok=True)


def test_tracker_status_lock_and_dropdown_sync(client, env):
    from backend.columns import editable_list_options
    from backend.excel.tracker import Tracker

    # Seed Excel DVs to match HTP defaults so unlocked status is in_sync.
    tracker = Tracker(env.tracker_abs, backups_keep=2)
    options = editable_list_options(env)
    tracker.sync_list_validations(options)
    r = client.get("/api/tracker/status?force=true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["locked"] is False
    assert body["dropdown_sync"]["status"] == "in_sync"
    assert body["suggest_sync"] is False

    # Drift: reorder Excel's existing options.
    tracker.sync_list_validations({"Applied_Through": options["Applied_Through"][::-1]})
    r = client.get("/api/tracker/status?force=true")
    assert r.json()["dropdown_sync"]["status"] == "mismatched"
    assert r.json()["suggest_sync"] is True
    assert any(c["column"] == "Applied_Through" and c["changed"] for c in r.json()["dropdown_sync"]["columns"])

    # Lock via ~$ owner file (probe path; watcher may also see it).
    owner = env.tracker_abs.with_name(f"~${env.tracker_abs.name}")
    owner.write_text("")
    try:
        r = client.get("/api/tracker/status")
        assert r.json()["locked"] is True
        assert r.json()["dropdown_sync"]["status"] == "locked"
        assert r.json()["suggest_sync"] is False
        assert client.post("/api/meta/options/sync").status_code == 423
    finally:
        owner.unlink(missing_ok=True)

    r = client.post("/api/meta/options/sync")
    assert r.status_code == 200, r.text
    assert r.json()["locked"] is False
    assert r.json()["dropdown_sync"]["status"] == "in_sync"
    assert r.json()["suggest_sync"] is False
    assert tracker.read_list_options(["Applied_Through"])["Applied_Through"] == options["Applied_Through"]
