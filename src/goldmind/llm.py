"""Thin LLM access layer over LangChain.

Goals
-----
* **Provider-agnostic.** Reasoning agents default to Claude; the Vision agent
  defaults to a GPT-4o-class multimodal model. Either can be swapped via config.
* **Structured by default.** Agents request a Pydantic schema and get a validated
  object back (``with_structured_output``), so an LLM can never inject an
  out-of-range confidence or an unknown enum into the pipeline.
* **Degrade, don't crash.** If no API key is configured (CI, offline research,
  the analysis VPS), :func:`get_chat_model` returns ``None`` and each LLM agent
  falls back to a deterministic heuristic. The system stays runnable everywhere.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from goldmind.config import Settings, get_settings
from goldmind.logging import get_logger

log = get_logger("llm")
T = TypeVar("T", bound=BaseModel)

Role = str  # "reasoning" | "vision" | "fast"


def get_chat_model(role: Role = "reasoning", settings: Settings | None = None) -> Any | None:
    """Return a configured LangChain chat model for ``role`` or ``None`` if the
    required provider key is missing."""
    s = settings or get_settings()
    model_name = {"reasoning": s.reasoning_model, "vision": s.vision_model, "fast": s.fast_model}.get(
        role, s.reasoning_model
    )
    is_anthropic = model_name.startswith("claude")

    try:
        if is_anthropic:
            if not s.anthropic_api_key:
                return None
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=model_name,
                temperature=s.llm_temperature,
                timeout=s.llm_timeout_s,
                api_key=s.anthropic_api_key,
                max_tokens=2048,
            )
        if not s.openai_api_key:
            return None
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            temperature=s.llm_temperature,
            timeout=s.llm_timeout_s,
            api_key=s.openai_api_key,
        )
    except Exception as exc:  # pragma: no cover - import/config guard
        log.warning("llm_init_failed", role=role, model=model_name, error=str(exc))
        return None


def encode_image(path: str | Path) -> tuple[str, str]:
    """Return (mime_type, base64_data) for a local image."""
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return mime, base64.b64encode(p.read_bytes()).decode("utf-8")


def _image_block(path: str | Path) -> dict[str, Any]:
    mime, data = encode_image(path)
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
def complete_structured(
    model: Any,
    schema: type[T],
    system: str,
    human: str,
    *,
    image_path: str | Path | None = None,
) -> T:
    """Call ``model`` and coerce the reply into ``schema`` (validated).

    Retries with exponential backoff on transient provider errors. The caller is
    responsible for handling the *final* failure (agents convert it into a
    low-confidence, flagged output).
    """
    structured = model.with_structured_output(schema)
    if image_path is not None:
        human_content: Any = [{"type": "text", "text": human}, _image_block(image_path)]
    else:
        human_content = human
    messages = [("system", system), ("human", human_content)]
    return structured.invoke(messages)  # type: ignore[return-value]
