"""Answer application questions with one structured LLM call.

Inputs per call: ``candidate_context.txt`` (read fresh every time), the posting,
organization + title, previously answered questions (for consistency) and the
pending questions with their limits. Limits are verified in code; offenders are
re-asked once with an explicit "shorten to N" instruction.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from ..llm.client import ClaudeClient, LLMResult, OpenAIClient
from ..llm.prompts import QA_SYSTEM
from ..sessions.models import Limit, Question, Session, utc_now

log = logging.getLogger("htp.qa")

ANSWERS_FILE = "answers.md"
_DASHES = str.maketrans({"\u2014": "-", "\u2013": "-", "\u2012": "-", "\u2015": "-"})


class CandidateContextMissing(FileNotFoundError):
    pass


def load_candidate_context(cfg: Settings) -> str:
    path = cfg.candidate_context_abs
    if not path.exists():
        raise CandidateContextMissing(
            f"Candidate context not found at {path}. Create it (plain text: background, projects, skills, motivations) and retry."
        )
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise CandidateContextMissing(f"Candidate context at {path} is empty.")
    return text


# ---------------------------------------------------------------------------


def unit_word(limit: Limit) -> str:
    return "characters" if limit.unit == "chars" else "words"


def limit_text(limit: Limit | None) -> str:
    return f"max {limit.value} {unit_word(limit)}" if limit else "no limit"


def measure(answer: str, limit: Limit | None) -> int | None:
    if not limit:
        return None
    return len(answer) if limit.unit == "chars" else len(answer.split())


def over_limit(answer: str, limit: Limit | None) -> int:
    """How far over the limit (0 when fine or no limit)."""
    n = measure(answer, limit)
    return max(0, n - limit.value) if limit and n is not None else 0


def clean_answer(text: str) -> str:
    text = text.translate(_DASHES).strip()
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return text


def _schema(ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string", "enum": ids}, "answer": {"type": "string"}},
                    "required": ["id", "answer"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["answers"],
        "additionalProperties": False,
    }


def build_user_prompt(
    *,
    context: str,
    posting: str,
    organization: str | None,
    title: str | None,
    answered: list[Question],
    pending: list[Question],
    feedback: dict[str, str] | None = None,
    shorten: dict[str, int] | None = None,
) -> str:
    parts: list[str] = []
    role = " / ".join(x for x in (organization, title) if x) or "not stated"
    parts.append(f"ROLE: {role}")
    parts.append("CANDIDATE CONTEXT:\n" + context)
    parts.append("JOB POSTING:\n" + posting.strip())
    if answered:
        prev = "\n\n".join(f"Q: {q.text}\nA: {q.answer}" for q in answered if q.answer)
        parts.append("PREVIOUSLY ANSWERED (keep consistent, do not repeat):\n" + prev)
    lines = []
    for q in pending:
        block = f"- id: {q.id}\n  question: {q.text}\n  limit: {limit_text(q.limit)}"
        fb = (feedback or {}).get(q.id)
        if fb:
            block += f"\n  previous answer: {q.answer or '(none)'}\n  revision feedback from the candidate: {fb}"
        over = (shorten or {}).get(q.id)
        if over and q.limit:
            n = measure(q.answer or "", q.limit)
            block += (
                f"\n  previous answer ({n} {unit_word(q.limit)}, limit {q.limit.value}): {q.answer}"
                f"\n  instruction: rewrite so it is at most {q.limit.value} {unit_word(q.limit)}; cut content rather than squeezing words together."
            )
        lines.append(block)
    parts.append("QUESTIONS TO ANSWER:\n" + "\n".join(lines))
    return "\n\n".join(parts)


@dataclass
class AnswerRun:
    answered: list[Question]
    usage: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _call(client: ClaudeClient | OpenAIClient, cfg: Settings, system: str, user: str, ids: list[str]) -> LLMResult:
    llm = cfg.selected_llm
    return client.structured(
        model=llm.qa_model,
        system=system,
        user=user,
        schema=_schema(ids),
        max_tokens=max(llm.max_tokens, 1024 + 400 * len(ids)),
    )


def _add_usage(total: dict[str, int], usage: dict[str, Any]) -> None:
    for k in ("input_tokens", "output_tokens"):
        v = usage.get(k)
        if isinstance(v, int):
            total[k] = total.get(k, 0) + v


def answer_questions(
    session: Session,
    cfg: Settings,
    client: ClaudeClient | OpenAIClient,
    *,
    ids: list[str] | None = None,
    feedback: dict[str, str] | None = None,
    organization: str | None = None,
    title: str | None = None,
) -> AnswerRun:
    """Answer the pending questions (or the given ``ids``) in one call, verify limits,
    re-ask offenders once, and update the session in place (caller saves)."""
    context = load_candidate_context(cfg)
    questions = session.qa.questions
    targets = [q for q in questions if (q.id in ids if ids is not None else q.status == "pending")]
    if not targets:
        return AnswerRun(answered=[])
    target_ids = {q.id for q in targets}
    answered_before = [q for q in questions if q.status == "answered" and q.answer and q.id not in target_ids]

    user = build_user_prompt(
        context=context, posting=session.posting.text, organization=organization, title=title,
        answered=answered_before, pending=targets, feedback=feedback,
    )
    run = AnswerRun(answered=[])
    res = _call(client, cfg, QA_SYSTEM, user, [q.id for q in targets])
    run.warnings.extend(res.warnings)
    _add_usage(run.usage, res.usage)
    got = {a.get("id"): clean_answer(str(a.get("answer", ""))) for a in res.output.get("answers", [])}

    by_id = {q.id: q for q in targets}
    missing = [q.id for q in targets if not got.get(q.id)]
    for qid, ans in got.items():
        q = by_id.get(qid)
        if q is None or not ans:
            continue
        q.answer, q.note = ans, None

    # Verify limits; re-ask offenders once.
    offenders = {q.id: over_limit(q.answer or "", q.limit) for q in targets if q.answer and over_limit(q.answer, q.limit)}
    if offenders:
        retry_qs = [by_id[i] for i in offenders]
        user2 = build_user_prompt(
            context=context, posting=session.posting.text, organization=organization, title=title,
            answered=answered_before, pending=retry_qs, shorten=offenders,
        )
        res2 = _call(client, cfg, QA_SYSTEM, user2, list(offenders))
        _add_usage(run.usage, res2.usage)
        for a in res2.output.get("answers", []):
            q = by_id.get(a.get("id"))
            ans = clean_answer(str(a.get("answer", "")))
            if q is None or not ans:
                continue
            if over_limit(ans, q.limit) < over_limit(q.answer or "", q.limit):
                q.answer = ans
        for q in retry_qs:
            over = over_limit(q.answer or "", q.limit)
            if over:
                q.note = f"Still {over} {unit_word(q.limit) if q.limit else ''} over the limit after one re-ask; trim by hand."
                run.warnings.append(f"{q.id}: {q.note}")

    now = utc_now()
    for q in targets:
        if q.id in missing:
            run.warnings.append(f"Model returned no answer for question {q.id}.")
            continue
        q.status = "answered"
        q.answered_at = now
        q.model = res.model
        if feedback and q.id in feedback:
            q.feedback = feedback[q.id]
        run.answered.append(q)

    _add_usage(session.qa.usage, run.usage)
    session.qa.last_answered_at = now
    log.info(
        "%s: answered %d/%d question(s) reask=%d usage=%s warnings=%d",
        session.folder, len(run.answered), len(targets), len(offenders), run.usage, len(run.warnings),
    )
    return run


# ---------------------------------------------------------------------------


def render_answers_md(session: Session, organization: str | None, title: str | None) -> str:
    head = " - ".join(x for x in (organization, title) if x) or session.folder
    out = [f"# Application questions - {head}", "", f"Folder: `{session.folder}`  ", f"Updated: {utc_now()}", ""]
    if not session.qa.questions:
        out.append("_No questions yet._")
    for n, q in enumerate(session.qa.questions, start=1):
        meta = [limit_text(q.limit), q.status]
        m = measure(q.answer or "", q.limit)
        if q.answer and q.limit and m is not None:
            meta.append(f"{m} {q.limit.unit}")
        elif q.answer:
            meta.append(f"{len(q.answer)} chars, {len(q.answer.split())} words")
        out += [f"## {n}. {q.text.strip()}", "", f"_{' · '.join(meta)}_", ""]
        out.append(q.answer.strip() if q.answer else "_(pending)_")
        if q.note:
            out += ["", f"> Note: {q.note}"]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def write_answers_md(folder: Path, session: Session, organization: str | None, title: str | None) -> Path:
    path = folder / ANSWERS_FILE
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(render_answers_md(session, organization, title), encoding="utf-8")
    tmp.replace(path)
    return path
