"""Shared LLM defaults for sketch / polish / auto-refine.

Local demo and CLI default to Grok on the a0 OpenAI-compatible proxy.
Override with env:

    LLM_API_KEY / VENICE_API_KEY
    LLM_API_BASE / VENICE_API_BASE
    TEXT_MODEL / VISION_MODEL
"""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Load KEY=VALUE from nearby .env files without clobbering process env."""
    here = Path(__file__).resolve()
    candidates = (
        here.parents[2] / ".env",  # techfig repo root
        Path.home() / ".hermes" / "profiles" / "scientist" / "projects" / "techfig-web" / ".env",
        Path.home() / ".techfig" / ".env",
    )
    for path in candidates:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


_load_dotenv()

DEFAULT_TEXT_MODEL = os.getenv("TEXT_MODEL") or os.getenv("VISION_MODEL") or "openai/grok-4-6"
DEFAULT_API_BASE = (
    os.getenv("LLM_API_BASE")
    or os.getenv("VENICE_API_BASE")
    or "https://llm.agent-zero.ai/v1"
)


def _api_key() -> str:
    return os.getenv("LLM_API_KEY") or os.getenv("VENICE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""


def completion_kwargs(**overrides) -> dict:
    """litellm.completion kwargs for the configured OpenAI-compatible endpoint."""
    kwargs = {
        "api_key": _api_key(),
        "api_base": DEFAULT_API_BASE,
        "temperature": 0.2,
    }
    kwargs.update(overrides)
    return kwargs
