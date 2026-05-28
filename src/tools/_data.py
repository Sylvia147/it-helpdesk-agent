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
# These loaders are cached because the mock data files are static during a run.
# 这些 loader 都做缓存，因为 demo 数据在一次运行中不会变；第一次读文件后，
#     后续工具调用直接走内存。


@lru_cache(maxsize=1)
def load_users() -> dict:
    """Returns {user_id: record} with `_meta` stripped at the top level.

    读取员工目录。顶层 `_meta` 是数据说明，不是用户记录，所以过滤掉。
    """
    raw = json.loads((DATA_DIR / "users.json").read_text())
    return {k: v for k, v in raw.items() if not k.startswith("_")}


@lru_cache(maxsize=1)
def load_status() -> tuple[dict, dict]:
    """Returns (services, dependency_graph). Both have `_*` keys stripped.

    返回两个结构：服务状态表和依赖图。依赖图用于“Tableau 受 Jenkins
    上游影响”这类多系统场景。
    """
    raw = json.loads((DATA_DIR / "system_status.json").read_text())
    deps_raw = raw.get("_dependencies", {})
    deps = {k: v for k, v in deps_raw.items() if not k.startswith("_")}
    services = {k: v for k, v in raw.items() if not k.startswith("_")}
    return services, deps


@lru_cache(maxsize=1)
def load_history() -> list[dict]:
    """Returns the list of historical case records.

    历史工单用于 search_history，让 agent 能参考过去类似案例。
    """
    raw = json.loads((DATA_DIR / "resolution_history.json").read_text())
    return raw["history"]


@lru_cache(maxsize=1)
def load_policies() -> dict:
    """Returns {action: policy_record}.

    策略表用于判断 agent 是否有权限处理某类动作，或必须升级人工。
    """
    raw = json.loads((DATA_DIR / "policies.json").read_text())
    return {k: v for k, v in raw.items() if not k.startswith("_")}


# --- KB markdown loader ---------------------------------------------------


_ARTICLE_ID_RE = re.compile(r"\*\*Article ID:\*\*\s*(\S+)")
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@lru_cache(maxsize=1)
def load_kb() -> list[dict]:
    """Load every kb/*.md article. Each entry has article_id, title, path, content.

    把 markdown KB 文章读成结构化记录，方便 BM25 建索引。
    """
    articles = []
    for path in sorted(KB_DIR.glob("*.md")):
        content = path.read_text()
        article_id_match = _ARTICLE_ID_RE.search(content)
        title_match = _TITLE_RE.search(content)
        # Article IDs/titles are parsed from markdown, with filename fallback.
        # 优先从 markdown 正文里解析 Article ID 和标题；解析不到就用文件名兜底。
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
    """Lowercase word tokens. Drops markdown punctuation, suitable for BM25.

    简单分词器：转小写，只保留字母数字 token。小语料下 BM25 足够好用。
    """
    return _TOKEN_RE.findall(text.lower())


# --- Failure injection ----------------------------------------------------


def simulated_failure(tool_name: str) -> str | None:
    """Return an error string if SIMULATE_FAILURE matches `tool_name`, else None.

    The env var is read fresh each call (no caching) so eval cases can flip the
    flag between runs in the same process.

    故障注入用于测试可靠性。比如 SIMULATE_FAILURE=search_kb 时，
    search_kb 会返回 success=False，验证 agent 不会引用不存在的 KB 内容。
    """
    target = os.environ.get("SIMULATE_FAILURE", "").strip()
    if target and target == tool_name:
        return (
            f"Simulated failure for {tool_name} "
            "(SIMULATE_FAILURE env var set; this is a deliberate fault for testing)."
        )
    return None
