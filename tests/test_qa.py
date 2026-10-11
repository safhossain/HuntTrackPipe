"""Q&A engine with a scripted fake Claude client."""
import pytest

from backend.llm.client import LLMResult
from backend.qa.answer import (
    CandidateContextMissing,
    answer_questions,
    build_user_prompt,
    clean_answer,
    load_candidate_context,
    over_limit,
    render_answers_md,
    write_answers_md,
)
from backend.sessions.models import Limit, Question


class FakeClient:
    """Returns the queued outputs in order and records every prompt."""

    def __init__(self, *outputs: dict):
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    def structured(self, *, model, system, user, schema, max_tokens=None):
        self.calls.append({"model": model, "user": user, "schema": schema})
        return LLMResult(model=model, output=self.outputs.pop(0), usage={"input_tokens": 100, "output_tokens": 20})


def q(text: str, limit: Limit | None = None, qid: str | None = None) -> Question:
    return Question(id=qid or text[:4].lower(), text=text, limit=limit)


def test_helpers():
    assert clean_answer('"Hello \u2014 world"') == "Hello - world"
    assert over_limit("a b c d", Limit(unit="words", value=3)) == 1
    assert over_limit("abcd", Limit(unit="chars", value=10)) == 0
    assert over_limit("abcd", None) == 0


def test_candidate_context_required(env):
    assert load_candidate_context(env).startswith("Software developer")
    env.candidate_context_abs.unlink()
    with pytest.raises(CandidateContextMissing):
        load_candidate_context(env)


def test_prompt_includes_limits_and_previous_answers():
    prev = q("Why us?", qid="prev")
    prev.status, prev.answer = "answered", "Because."
    pend = q("Why you?", Limit(unit="words", value=50), qid="pend")
    text = build_user_prompt(
        context="CTX", posting="POST", organization="Acme", title="Dev", answered=[prev], pending=[pend],
        feedback={"pend": "more concrete"},
    )
    assert "ROLE: Acme / Dev" in text and "Q: Why us?\nA: Because." in text
    assert "limit: max 50 words" in text and "revision feedback from the candidate: more concrete" in text


def test_answer_within_limit_single_call(env, session):
    session.qa.questions = [q("Why this role?", Limit(unit="chars", value=200), "q1"), q("Start date?", None, "q2")]
    client = FakeClient({"answers": [{"id": "q1", "answer": "Because it fits."}, {"id": "q2", "answer": "Immediately."}]})
    run = answer_questions(session, env, client, organization="Acme", title="Dev")
    assert [a.id for a in run.answered] == ["q1", "q2"]
    assert len(client.calls) == 1
    assert client.calls[0]["schema"]["properties"]["answers"]["items"]["properties"]["id"]["enum"] == ["q1", "q2"]
    assert all(x.status == "answered" and x.model == env.llm.qa_model for x in session.qa.questions)
    assert session.qa.usage == {"input_tokens": 100, "output_tokens": 20}


def test_over_limit_is_reasked_once_then_noted(env, session):
    session.qa.questions = [q("Short one", Limit(unit="words", value=3), "q1")]
    client = FakeClient(
        {"answers": [{"id": "q1", "answer": "one two three four five"}]},
        {"answers": [{"id": "q1", "answer": "one two three four"}]},  # better, still over
    )
    run = answer_questions(session, env, client)
    assert len(client.calls) == 2 and "rewrite so it is at most 3 words" in client.calls[1]["user"]
    qq = session.qa.questions[0]
    assert qq.answer == "one two three four" and qq.status == "answered"
    assert qq.note and "1 words over" in qq.note and run.warnings


def test_reask_keeps_better_answer(env, session):
    session.qa.questions = [q("Short one", Limit(unit="words", value=3), "q1")]
    client = FakeClient(
        {"answers": [{"id": "q1", "answer": "one two three four"}]},
        {"answers": [{"id": "q1", "answer": "one two"}]},
    )
    answer_questions(session, env, client)
    assert session.qa.questions[0].answer == "one two" and session.qa.questions[0].note is None


def test_missing_answer_is_warned_and_stays_pending(env, session):
    session.qa.questions = [q("A", None, "q1"), q("B", None, "q2")]
    run = answer_questions(session, env, FakeClient({"answers": [{"id": "q1", "answer": "ok"}]}))
    assert [a.id for a in run.answered] == ["q1"]
    assert session.qa.questions[1].status == "pending" and any("q2" in w for w in run.warnings)


def test_regenerate_with_feedback_targets_only_that_id(env, session):
    a, b = q("A", None, "q1"), q("B", None, "q2")
    a.status, a.answer, b.status, b.answer = "answered", "old A", "answered", "old B"
    session.qa.questions = [a, b]
    client = FakeClient({"answers": [{"id": "q2", "answer": "new B"}]})
    answer_questions(session, env, client, ids=["q2"], feedback={"q2": "shorter"})
    assert "Q: A\nA: old A" in client.calls[0]["user"] and "previous answer: old B" in client.calls[0]["user"]
    assert b.answer == "new B" and b.feedback == "shorter" and a.answer == "old A"


def test_answers_md(env, session):
    qq = q("Why?", Limit(unit="chars", value=10), "q1")
    qq.status, qq.answer = "answered", "Because"
    session.qa.questions = [qq]
    md = render_answers_md(session, "Acme", "Dev")
    assert md.startswith("# Application questions - Acme - Dev") and "Because" in md
    path = write_answers_md(env.applications_abs / session.folder, session, None, None)
    assert path.exists() and session.folder in path.read_text(encoding="utf-8")
