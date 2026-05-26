"""缓存工具。

竞品画像的抽取会消耗搜索 API 和模型调用。缓存工具把已经抽取好的画像保存
为 JSON 文件，后续分析同一产品时可以直接复用。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from competitor_agent.config import settings


def slugify(value: str) -> str:
    """把产品名转换成适合文件名的短字符串。

    英文、数字和中文会保留；空格、斜杠、标点等统一替换成连字符。
    """

    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip().lower())
    return slug.strip("-") or "untitled"


def cache_path(product_name: str, cache_dir: Path | None = None) -> Path:
    """根据产品名计算缓存文件路径。"""

    base = cache_dir or settings.cache_dir
    return base / f"{slugify(product_name)}.json"


def read_cache(product_name: str, cache_dir: Path | None = None) -> dict[str, Any] | None:
    """读取单个产品的 JSON 缓存。

    缓存不存在时返回 None，让调用方决定是否重新搜索和抽取。
    """

    path = cache_path(product_name, cache_dir)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_cache(product_name: str, data: dict[str, Any], cache_dir: Path | None = None) -> Path:
    """写入单个产品的 JSON 缓存，并返回写入路径。"""

    path = cache_path(product_name, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return path
