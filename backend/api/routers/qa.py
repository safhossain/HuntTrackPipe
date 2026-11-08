"""Application questions (DESIGN.md section 11)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...excel.tracker import TrackerError
from ...llm.client import selected_client
from ...qa.answer import ANSWERS_FILE, answer_questions, write_answers_md
from ...sessions.models import Question, Session, utc_now
from ..deps import get_settings, get_store, get_tracker
from ..models import (
    AnswerRequest,
    QAView,
    QuestionOrderRequest,
    QuestionsCreate,
    QuestionUpdate,
    RegenerateRequest,
)

router = APIRouter(prefix="/sessions/{folder}/qa", tags=["qa"])


def _load(folder: str) -> Session:
    try:
        return get_store().load(folder)
    except FileNotFoundError:
        raise HTTPException(404, f"No session for folder {folder!r}")


def _org_title(session: Session) -> tuple[str | None, str | None]:
    src = None
    try:
        src = get_tracker().read_row(session.folder)
    except (TrackerError, OSError):
        pass
    src = src or session.review.values
    org, title = src.get("Organization"), src.get("Position_Title")
    return (str(org).strip() or None) if org else None, (str(title).strip() or None) if title else None


def _view(session: Session, warnings: list[str] | None = None) -> QAView:
    cfg = get_settings()
    org, title = _org_title(session)
    folder = get_store().folder_path(session.folder)
    return QAView(
        qa=session.qa,
        candidate_context_exists=cfg.candidate_context_abs.exists(),
        candidate_context_path=str(cfg.candidate_context_abs),
        answers_md=ANSWERS_FILE if (folder / ANSWERS_FILE).exists() else None,
        organization=org,
        title=title,
        warnings=warnings or [],
    )


def _save(session: Session, warnings: list[str] | None = None) -> QAView:
    store = get_store()
    store.save(session)
    org, title = _org_title(session)
    write_answers_md(store.folder_path(session.folder), session, org, title)
    return _view(session, warnings)


def _question(session: Session, qid: str) -> Question:
    for q in session.qa.questions:
        if q.id == qid:
            return q
    raise HTTPException(404, f"No question {qid!r}")


@router.get("", response_model=QAView)
def get_qa(folder: str) -> QAView:
    return _view(_load(folder))


@router.post("/questions", response_model=QAView)
def add_questions(folder: str, req: QuestionsCreate) -> QAView:
    session = _load(folder)
    added = 0
    for item in req.questions:
        text = " ".join(item.text.split())
        if not text:
            continue
        session.qa.questions.append(Question(text=text, limit=item.limit))
        added += 1
    if not added:
        raise HTTPException(400, "No question text given.")
    return _save(session)


@router.put("/questions/order", response_model=QAView)
def reorder_questions(folder: str, req: QuestionOrderRequest) -> QAView:
    session = _load(folder)
    by_id = {q.id: q for q in session.qa.questions}
    if sorted(req.order) != sorted(by_id):
        raise HTTPException(400, "order must list every question id exactly once.")
    session.qa.questions = [by_id[i] for i in req.order]
    return _save(session)


@router.put("/questions/{qid}", response_model=QAView)
def update_question(folder: str, qid: str, req: QuestionUpdate) -> QAView:
    session = _load(folder)
    q = _question(session, qid)
    if req.text is not None:
        text = " ".join(req.text.split())
        if not text:
            raise HTTPException(400, "Question text cannot be empty.")
        if text != q.text:
            q.text = text
            if q.answer:
                q.note = "Question changed after it was answered; regenerate if needed."
    if req.clear_limit:
        q.limit = None
    elif req.limit is not None:
        q.limit = req.limit
    if req.answer is not None:
        ans = req.answer.strip()
        if ans:
            q.answer, q.status, q.model, q.answered_at, q.note = ans, "answered", "manual", utc_now(), None
        else:
            q.answer, q.status, q.model, q.answered_at, q.note = None, "pending", None, None, None
    return _save(session)


@router.delete("/questions/{qid}", response_model=QAView)
def delete_question(folder: str, qid: str) -> QAView:
    session = _load(folder)
    q = _question(session, qid)
    session.qa.questions.remove(q)
    return _save(session)


@router.post("/answer", response_model=QAView)
def answer_pending(folder: str, req: AnswerRequest) -> QAView:
    session = _load(folder)
    cfg = get_settings()
    org, title = _org_title(session)
    run = answer_questions(session, cfg, selected_client(cfg), ids=req.ids, organization=org, title=title)
    if not run.answered and not run.warnings:
        raise HTTPException(400, "No pending questions.")
    return _save(session, run.warnings)


@router.post("/regenerate/{qid}", response_model=QAView)
def regenerate(folder: str, qid: str, req: RegenerateRequest) -> QAView:
    session = _load(folder)
    q = _question(session, qid)
    cfg = get_settings()
    org, title = _org_title(session)
    fb = (req.feedback or "").strip() or None
    run = answer_questions(
        session, cfg, selected_client(cfg), ids=[q.id], feedback={q.id: fb} if fb else None, organization=org, title=title
    )
    return _save(session, run.warnings)
