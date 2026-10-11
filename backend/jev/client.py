"""Minimal Jev client over plain HTTP (``POST /v1/systemone``).

Request/response shapes follow docs.typesafe.ai. Retries 429 / 529 / 5xx with
exponential backoff and honours ``retry-after``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import JevSettings, api_key

# Jev caps state + the longest question at 32k tokens; stay under with a char estimate.
CHARS_PER_TOKEN = 3.5
STATE_TOKEN_BUDGET = 30_000
RETRY_STATUSES = {429, 500, 502, 503, 504, 529}


class JevError(RuntimeError):
    pass


@dataclass
class JevResponse:
    model: str
    answers: dict[str, Any]
    usage: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def truncate_for_jev(text: str) -> tuple[str, str | None]:
    limit = int(STATE_TOKEN_BUDGET * CHARS_PER_TOKEN)
    if len(text) <= limit:
        return text, None
    return text[:limit], f"Posting truncated from {len(text)} to {limit} characters for Jev."


class JevClient:
    def __init__(self, cfg: JevSettings, key: str | None = None):
        self.cfg = cfg
        self.key = key or api_key("TYPESAFE_API_KEY")

    def ask(self, posting_text: str, questions: dict[str, dict]) -> JevResponse:
        text, warning = truncate_for_jev(posting_text)
        body = {"model": self.cfg.model, "state": {"posting": text}, "questions": questions}
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        url = f"{self.cfg.base_url.rstrip('/')}/v1/systemone"

        last_err: str | None = None
        with httpx.Client(timeout=self.cfg.timeout_s) as http:
            for attempt in range(1, self.cfg.max_attempts + 1):
                try:
                    resp = http.post(url, json=body, headers=headers)
                except httpx.HTTPError as exc:  # network / timeout
                    last_err = f"{type(exc).__name__}: {exc}"
                    resp = None
                if resp is not None and resp.status_code == 200:
                    data = resp.json()
                    out = JevResponse(
                        model=data.get("model", self.cfg.model),
                        answers=data.get("answers", {}),
                        usage=data.get("usage", {}),
                    )
                    if warning:
                        out.warnings.append(warning)
                    return out
                if resp is not None:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:500]}"
                    if resp.status_code not in RETRY_STATUSES:
                        break
                if attempt < self.cfg.max_attempts:
                    delay = 2 ** (attempt - 1)
                    if resp is not None and resp.headers.get("retry-after"):
                        try:
                            delay = max(delay, float(resp.headers["retry-after"]))
                        except ValueError:
                            pass
                    time.sleep(delay)
        raise JevError(f"Jev call failed after {self.cfg.max_attempts} attempt(s): {last_err}")
