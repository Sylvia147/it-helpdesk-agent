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


# Runtime knobs live in env vars so demos can switch model/proxy without code edits.
# 模型名、最大 token、中间商 base URL 都从环境变量读，演示时不用改代码。
#
# Override via env: ITAGENT_MODEL=claude-haiku-4-5-20251001 ./run.sh
# 例如可以在 .env 里写 ITAGENT_MODEL=... 来切换模型。
DEFAULT_MODEL = os.getenv("ITAGENT_MODEL", "claude-sonnet-4-6")
DEFAULT_MAX_TOKENS = int(os.getenv("ITAGENT_MAX_TOKENS", "2048"))
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL")


@lru_cache(maxsize=1)
def get_client() -> Anthropic:
    """Return a process-wide Anthropic client (lazy).

    客户端懒加载并缓存，避免每轮对话都重新创建 SDK client。
    如果设置 ANTHROPIC_BASE_URL，就走兼容 Anthropic API 的代理/中间商。
    """
    return Anthropic(base_url=ANTHROPIC_BASE_URL)
