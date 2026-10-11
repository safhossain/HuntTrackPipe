"""Turn raw Jev answers into decisions: which LLM fields to ask for, which
Excel columns are already settled, upload hints."""
from __future__ import annotations

from typing import Any

from ..config import JevSettings
from ..sessions.models import JevDerived
from .questions import CHOICE_COLUMNS, DOC_NOULS, EXISTENCE, UPLOAD_MODES


def _noul(answers: dict[str, Any], key: str) -> float | None:
    a = answers.get(key)
    if not a or a.get("type") != "noul":
        return None
    try:
        return float(a["noul"])
    except (KeyError, TypeError, ValueError):
        return None


def _choice(answers: dict[str, Any], key: str) -> tuple[str | None, float | None]:
    a = answers.get(key)
    if not a or a.get("type") != "choice":
        return None, None
    conf = a.get("confidence")
    return a.get("choice"), (float(conf) if conf is not None else None)


def derive(answers: dict[str, Any], cfg: JevSettings) -> JevDerived:
    d = JevDerived()

    # Gate
    d.is_job_posting = _noul(answers, "is_job_posting")
    if d.is_job_posting is not None and d.is_job_posting < cfg.job_posting_warn_below:
        d.warnings.append(f"Jev thinks this may not be a job posting (p={d.is_job_posting:.2f}).")

    # Existence nouls -> LLM schema fields (bias toward inclusion)
    for key, fld in EXISTENCE.items():
        p = _noul(answers, key)
        if p is None:
            d.warnings.append(f"Jev returned no answer for {key}; including {fld} in the LLM schema.")
            d.schema_fields.append(fld)
        elif p >= cfg.noul_include_threshold:
            d.schema_fields.append(fld)

    # Choices -> direct value or LLM enum field
    for key, (column, fld, mapping) in CHOICE_COLUMNS.items():
        choice, conf = _choice(answers, key)
        if choice in mapping and conf is not None and conf >= cfg.choice_direct_confidence:
            d.direct_values[column] = mapping[choice]
        else:
            d.low_confidence_choices.append(fld)

    # Upload hints
    mode, conf = _choice(answers, "upload_mode")
    d.upload_mode = mode if mode in UPLOAD_MODES else "not_stated"
    d.upload_mode_confidence = conf
    for key, doc in DOC_NOULS.items():
        p = _noul(answers, key)
        if p is not None and p >= cfg.doc_noul_threshold:
            d.required_docs.append(doc)

    return d
