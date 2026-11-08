"""Structured output clients for posting extraction and application Q&A.

Haiku 5.5: adaptive thinking is on by default, so ``output_config.effort`` is
set low; ``temperature`` / ``top_p`` / ``top_k`` must not be sent.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any

from ..config import Settings, api_key

CHARS_PER_TOKEN = 3.5
log = logging.getLogger("htp.llm")
_CLAUDE_KEY = "ANTHROPIC_API_KEY"
_OPENAI_KEY = "OPENAI_API_KEY"
_CREDIT_PREFIX = {_CLAUDE_KEY: "claude", _OPENAI_KEY: "openai"}
_credit_lock = Lock()
_unsaved_credit: dict[Path, bool] = {}


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


def _credit_marker(cfg: Settings, key_name: str, key: str) -> Path:
    fingerprint = sha256(key.encode("utf-8")).hexdigest()
    return cfg.applications_abs / ".htp_state" / f"{_CREDIT_PREFIX[key_name]}-low-credit-{fingerprint}"


def claude_credit_low(cfg: Settings) -> bool:
    return _credit_low(cfg, _CLAUDE_KEY)


def openai_credit_low(cfg: Settings) -> bool:
    return _credit_low(cfg, _OPENAI_KEY)


def _credit_low(cfg: Settings, key_name: str) -> bool:
    """Return the last observed low-credit state for the active API key."""
    key = os.environ.get(key_name)
    if not key:
        return False
    marker = _credit_marker(cfg, key_name, key)
    with _credit_lock:
        if marker in _unsaved_credit:
            return _unsaved_credit[marker]
        try:
            return marker.is_file()
        except OSError:
            return False


def _record_credit(marker: Path, *, low: bool) -> None:
    # Exclusive creation and removal avoid read/modify/write races with the CLI.
    with _credit_lock:
        try:
            if low:
                marker.parent.mkdir(parents=True, exist_ok=True)
                try:
                    marker.touch(exist_ok=False)
                except FileExistsError:
                    if marker.is_dir():
                        raise
            else:
                marker.unlink(missing_ok=True)
        except OSError as exc:
            _unsaved_credit[marker] = low
            log.warning("Could not persist provider credit status: %s", exc.strerror or type(exc).__name__)
        else:
            _unsaved_credit.pop(marker, None)


def _is_claude_low_credit_error(exc: Exception) -> bool:
    if getattr(exc, "status_code", None) != 400:
        return False
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        body = body.get("error", body)
        if isinstance(body, dict):
            body = body.get("message")
    return isinstance(body, str) and "credit balance is too low" in body.casefold()


class ClaudeClient:
    def __init__(self, cfg: Settings, key: str | None = None):
        import anthropic  # lazy: keeps CLI start-up fast when --no-llm

        self.cfg = cfg.llm
        key = key or api_key(_CLAUDE_KEY)
        self._credit_marker = _credit_marker(cfg, _CLAUDE_KEY, key)
        self._client = anthropic.Anthropic(api_key=key)

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
        t0 = time.perf_counter()
        for attempt in range(2):
            try:
                msg = self._client.messages.create(**kwargs)
            except Exception as exc:  # transport / API error -> one retry
                if _is_claude_low_credit_error(exc):
                    _record_credit(self._credit_marker, low=True)
                last_err = f"{type(exc).__name__}: {exc}"
                log.warning("llm attempt %d failed: %s", attempt + 1, last_err)
                continue
            _record_credit(self._credit_marker, low=False)
            text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
            if not text:
                last_err = f"No text block (stop_reason={getattr(msg, 'stop_reason', None)})"
                log.warning("llm attempt %d: %s", attempt + 1, last_err)
                continue
            try:
                output = json.loads(text)
            except json.JSONDecodeError as exc:
                last_err = f"Invalid JSON from model: {exc}"
                log.warning("llm attempt %d: %s", attempt + 1, last_err)
                continue
            usage = getattr(msg, "usage", None)
            result = LLMResult(
                model=getattr(msg, "model", model),
                output=output,
                usage={
                    "input_tokens": getattr(usage, "input_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None),
                },
                warnings=warnings,
            )
            log.info(
                "llm ok model=%s est_in=%d in=%s out=%s attempt=%d %.1fs",
                result.model, est, result.usage["input_tokens"], result.usage["output_tokens"], attempt + 1, time.perf_counter() - t0,
            )
            return result
        raise LLMError(f"LLM call failed: {last_err}")


class OpenAIClient:
    def __init__(self, cfg: Settings, key: str | None = None):
        import openai

        self.cfg = cfg.openai
        key = key or api_key(_OPENAI_KEY)
        self._credit_marker = _credit_marker(cfg, _OPENAI_KEY, key)
        self._client = openai.OpenAI(api_key=key, max_retries=0)

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

        last_err: str | None = None
        t0 = time.perf_counter()
        for attempt in range(2):
            try:
                response = self._client.responses.create(
                    model=model,
                    instructions=system,
                    input=user,
                    reasoning={"effort": self.cfg.effort},
                    max_output_tokens=max_tokens or self.cfg.max_tokens,
                    text={"format": {"type": "json_schema", "name": "structured_output", "schema": schema, "strict": True}},
                    store=False,
                )
            except Exception as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                if getattr(exc, "status_code", None) == 429 and getattr(exc, "code", None) == "credit_balance_exhausted":
                    _record_credit(self._credit_marker, low=True)
                    raise LLMError(f"OpenAI call failed: {last_err}") from exc
                log.warning("OpenAI attempt %d failed: %s", attempt + 1, last_err)
                continue

            _record_credit(self._credit_marker, low=False)
            text = response.output_text
            if response.status not in (None, "completed") or not text:
                last_err = f"No complete structured output (status={response.status})"
                log.warning("OpenAI attempt %d: %s", attempt + 1, last_err)
                continue
            try:
                output = json.loads(text)
                if not isinstance(output, dict):
                    raise ValueError("expected a JSON object")
            except ValueError as exc:
                last_err = f"Invalid JSON from model: {exc}"
                log.warning("OpenAI attempt %d: %s", attempt + 1, last_err)
                continue

            usage = response.usage
            result = LLMResult(
                model=response.model,
                output=output,
                usage={
                    "input_tokens": getattr(usage, "input_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None),
                },
                warnings=warnings,
            )
            log.info(
                "OpenAI ok model=%s est_in=%d in=%s out=%s attempt=%d %.1fs",
                result.model, est, result.usage["input_tokens"], result.usage["output_tokens"], attempt + 1, time.perf_counter() - t0,
            )
            return result
        raise LLMError(f"OpenAI call failed: {last_err}")


def selected_client(cfg: Settings) -> ClaudeClient | OpenAIClient:
    return OpenAIClient(cfg) if cfg.llm.extract_provider == "openai" else ClaudeClient(cfg)
