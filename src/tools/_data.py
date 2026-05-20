"""Shared data loading helpers for tool functions.

JSON and markdown files are loaded once and cached via @lru_cache, so reading
data/*.json on every tool call is free after the first call. Internal fields
(starting with `_`, e.g. `_meta`, `_demo_hook`, `_dependencies`) are stripped
from the returned views except where the field is genuinely meaningful to the
agent (handled by the caller).

Failure injection:
    Set the env var SIMULATE_FAILURE=<tool_name> to make that tool return a
    structured error (success=False) without invoking its real logic. Used by
    the eval suite's tool_failure case to exercise the agent's degradation
    path. The check is NOT cached because the env var is intended to vary
    between calls in test runs.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
KB_DIR = DATA_DIR / "kb"


# --- JSON loaders ---------------------------------------------------------


@lru_cache(maxsize=1)
def load_users() -> dict:
    """Returns {user_id: record} with `_meta` stripped at the top level."""
    raw = json.loads((DATA_DIR / "users.json").read_text())
    return {k: v for k, v in raw.items() if not k.startswith("_")}


@lru_cache(maxsize=1)
def load_status() -> tuple[dict, dict]:
    """Returns (services, dependency_graph). Both have `_*` keys stripped."""
    raw = json.loads((DATA_DIR / "system_status.json").read_text())
    deps_raw = raw.get("_dependencies", {})
    deps = {k: v for k, v in deps_raw.items() if not k.startswith("_")}
    services = {k: v for k, v in raw.items() if not k.startswith("_")}
    return services, deps


@lru_cache(maxsize=1)
def load_history() -> list[dict]:
    """Returns the list of historical case records."""
    raw = json.loads((DATA_DIR / "resolution_history.json").read_text())
    return raw["history"]


@lru_cache(maxsize=1)
def load_policies() -> dict:
    """Returns {action: policy_record}."""
    raw = json.loads((DATA_DIR / "policies.json").read_text())
    return {k: v for k, v in raw.items() if not k.startswith("_")}


# --- KB markdown loader ---------------------------------------------------


_ARTICLE_ID_RE = re.compile(r"\*\*Article ID:\*\*\s*(\S+)")
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@lru_cache(maxsize=1)
def load_kb() -> list[dict]:
    """Load every kb/*.md article. Each entry has article_id, title, path, content."""
    articles = []
    for path in sorted(KB_DIR.glob("*.md")):
        content = path.read_text()
        article_id_match = _ARTICLE_ID_RE.search(content)
        title_match = _TITLE_RE.search(content)
        articles.append(
            {
                "article_id": article_id_match.group(1) if article_id_match else path.stem,
                "title": title_match.group(1).strip() if title_match else path.stem,
                "path": f"kb/{path.name}",
                "content": content,
            }
        )
    return articles


# --- BM25 tokenizer -------------------------------------------------------


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens. Drops markdown punctuation, suitable for BM25."""
    return _TOKEN_RE.findall(text.lower())


# --- Failure injection ----------------------------------------------------


def simulated_failure(tool_name: str) -> str | None:
    """Return an error string if SIMULATE_FAILURE matches `tool_name`, else None.

    The env var is read fresh each call (no caching) so eval cases can flip the
    flag between runs in the same process.
    """
    target = os.environ.get("SIMULATE_FAILURE", "").strip()
    if target and target == tool_name:
        return (
            f"Simulated failure for {tool_name} "
            "(SIMULATE_FAILURE env var set; this is a deliberate fault for testing)."
        )
    return None
