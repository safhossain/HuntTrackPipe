"""Claude structured-output call for field extraction (and reusable for Q&A).

Haiku 5.5: adaptive thinking is on by default, so ``output_config.effort`` is
set low; ``temperature`` / ``top_p`` / ``top_k`` must not be sent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..config import LLMSettings, api_key

CHARS_PER_TOKEN = 3.5


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    model: str
    output: dict[str, Any]
    usage: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def estimate_tokens(*texts: str) -> int:
    return int(sum(len(t) for t in texts) / CHARS_PER_TOKEN)


class ClaudeClient:
    def __init__(self, cfg: LLMSettings, key: str | None = None):
        import anthropic  # lazy: keeps CLI start-up fast when --no-llm

        self.cfg = cfg
        self._client = anthropic.Anthropic(api_key=key or api_key("ANTHROPIC_API_KEY"))

    def structured(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int | None = None,
    ) -> LLMResult:
        warnings: list[str] = []
        est = estimate_tokens(system, user, json.dumps(schema))
        if est > self.cfg.token_warn:
            warnings.append(f"Estimated {est} input tokens exceeds warn threshold {self.cfg.token_warn}.")

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or self.cfg.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {
                "format": {"type": "json_schema", "schema": schema},
                "effort": self.cfg.effort,
            },
        }

        last_err: str | None = None
        for attempt in range(2):
            try:
                msg = self._client.messages.create(**kwargs)
            except Exception as exc:  # transport / API error -> one retry
                last_err = f"{type(exc).__name__}: {exc}"
                continue
            text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
            if not text:
                last_err = f"No text block (stop_reason={getattr(msg, 'stop_reason', None)})"
                continue
            try:
                output = json.loads(text)
            except json.JSONDecodeError as exc:
                last_err = f"Invalid JSON from model: {exc}"
                continue
            usage = getattr(msg, "usage", None)
            return LLMResult(
                model=getattr(msg, "model", model),
                output=output,
                usage={
                    "input_tokens": getattr(usage, "input_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None),
                },
                warnings=warnings,
            )
        raise LLMError(f"LLM call failed: {last_err}")
