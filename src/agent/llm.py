"""Thin wrapper around the Anthropic SDK.

Centralizes the model name and default parameters so changing them is a
one-line edit. Loads ANTHROPIC_API_KEY from .env via python-dotenv at import
time.
"""

from __future__ import annotations

import os
from functools import lru_cache

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


# Override via env: ITAGENT_MODEL=claude-haiku-4-5-20251001 ./run.sh
DEFAULT_MODEL = os.getenv("ITAGENT_MODEL", "claude-sonnet-4-6")
DEFAULT_MAX_TOKENS = int(os.getenv("ITAGENT_MAX_TOKENS", "2048"))


@lru_cache(maxsize=1)
def get_client() -> Anthropic:
    """Return a process-wide Anthropic client (lazy)."""
    return Anthropic()
