from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...pipeline import extract
from ..deps import get_settings
from ..models import ExtractRequest, ExtractResponse

router = APIRouter(prefix="/extract", tags=["extract"])


@router.post("", response_model=ExtractResponse)
def run_extract(req: ExtractRequest) -> ExtractResponse:
    text = req.posting_text.strip()
    if not text:
        raise HTTPException(400, "Posting text is empty.")
    ex = extract(text, get_settings(), use_jev=req.use_jev, use_llm=req.use_llm)
    return ExtractResponse(jev=ex.jev, llm=ex.llm, derived=ex.derived, values=ex.values, warnings=ex.warnings)
