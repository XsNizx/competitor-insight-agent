"""报告保存工具。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from competitor_agent.config import settings
from competitor_agent.tools.cache_tools import slugify


def save_report(markdown: str, topic: str, reports_dir: Path | None = None) -> Path:
    """把 Markdown 报告保存到磁盘。

    文件名由时间戳和主题组成：时间戳方便排序，主题方便人工识别内容。
    """

    base = reports_dir or settings.reports_dir
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = base / f"{stamp}-{slugify(topic)}.md"
    with path.open("w", encoding="utf-8") as file:
        file.write(markdown)
        # 文本文件以换行结尾更符合常见工具和 Git diff 的习惯。
        if not markdown.endswith("\n"):
            file.write("\n")
    return path
