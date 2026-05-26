"""Tavily 真实搜索工具。

Agno 的 SearchAgent 会把本模块中的 `tavily_search` 当成工具函数调用。
这里刻意只返回短摘要、标题和 URL，不返回网页全文。原因是网页全文会让
LLM 上下文迅速变大，进而导致模型输出的 JSON 被截断，出现
“Unterminated string / EOF while parsing a string” 这类错误。
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from competitor_agent.config import settings

MAX_ANSWER_CHARS = 800
MAX_CONTENT_CHARS = 700
MAX_RESULTS_PER_QUERY = 3


def _shorten(text: Any, max_chars: int) -> str:
    """把搜索返回的长文本压缩到固定长度。"""

    value = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    value = " ".join(value.split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"


def _normalize_tavily_payload(parsed: dict[str, Any], query: str, limit: int) -> dict[str, Any]:
    """把 Tavily 原始响应压缩成 Agent 易处理的小 JSON。"""

    results = []
    for item in parsed.get("results", [])[:limit]:
        results.append(
            {
                "title": _shorten(item.get("title", ""), 120),
                "url": item.get("url", ""),
                "content": _shorten(item.get("content", ""), MAX_CONTENT_CHARS),
                "score": item.get("score"),
            }
        )

    return {
        "query": parsed.get("query", query),
        "answer": _shorten(parsed.get("answer", ""), MAX_ANSWER_CHARS),
        "results": results,
    }


def _run_tavily_search(
    query: str,
    max_results: int | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    search_depth: str | None = None,
    default_max_results: int | None = None,
) -> str:
    """执行 Tavily HTTP 请求，并返回紧凑 JSON 证据。"""

    resolved_api_key = api_key
    if not resolved_api_key:
        raise RuntimeError("Tavily API Key is required for real search.")

    requested_limit = max_results or default_max_results or settings.tavily_max_results
    limit = max(1, min(requested_limit, MAX_RESULTS_PER_QUERY))
    payload: dict[str, Any] = {
        "query": query,
        "topic": "general",
        "search_depth": search_depth or settings.tavily_search_depth,
        "include_answer": True,
        "include_raw_content": False,
        "max_results": limit,
    }
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{(base_url or settings.tavily_api_base_url).rstrip('/')}/search",
        data=data,
        headers={
            "Authorization": f"Bearer {resolved_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "CompetitorInsightAgent/0.2",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Tavily search failed with HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise RuntimeError(f"Tavily search failed: {exc.reason}") from exc

    parsed = json.loads(raw)
    normalized = _normalize_tavily_payload(parsed, query, limit)
    return json.dumps(normalized, ensure_ascii=False)


def tavily_search(query: str, api_key: str, max_results: int | None = None) -> str:
    """使用显式传入的 Tavily API Key 搜索实时网页。"""

    return _run_tavily_search(query=query, max_results=max_results, api_key=api_key)


def make_tavily_search_tool(
    api_key: str,
    base_url: str | None = None,
    search_depth: str | None = None,
    max_results: int | None = None,
):
    """创建一个绑定了运行时 API Key 的 Agno 工具函数。

    Streamlit 页面中的 API Key 来自侧栏输入框。使用闭包后，
    Agno 调用工具时仍然只需要传 `query` 和可选的 `max_results`。
    """

    configured_max_results = max_results

    def tavily_search_for_run(query: str, max_results: int | None = None) -> str:
        """使用 Tavily 搜索实时网页，并返回紧凑 JSON 证据。"""

        return _run_tavily_search(
            query=query,
            max_results=max_results,
            api_key=api_key,
            base_url=base_url,
            search_depth=search_depth,
            default_max_results=configured_max_results,
        )

    tavily_search_for_run.__name__ = "tavily_search"
    tavily_search_for_run.__qualname__ = "tavily_search"
    return tavily_search_for_run
