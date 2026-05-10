"""Lightweight logging for OpenAI chat completions (latency cost observability)."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger("ai.openai")

T = TypeVar("T")


def log_chat_completion(response: Any, operation: str, latency_s: float | None = None) -> None:
    usage = getattr(response, "usage", None)
    model = getattr(response, "model", None)
    pt = getattr(usage, "prompt_tokens", None) if usage else None
    ct = getattr(usage, "completion_tokens", None) if usage else None
    tt = getattr(usage, "total_tokens", None) if usage else None
    lat = f"{latency_s:.3f}s" if latency_s is not None else "n/a"
    logger.info(
        "openai_chat op=%s model=%s latency=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s",
        operation,
        model,
        lat,
        pt,
        ct,
        tt,
    )


def timed_completion(operation: str, fn: Callable[[], T]) -> T:
    """Run ``fn`` (usually ``lambda: client.chat.completions.create(...)``) and log usage."""
    t0 = time.perf_counter()
    response = fn()
    log_chat_completion(response, operation, time.perf_counter() - t0)
    return response
