"""项目配置模块。

所有路径和默认模型参数都集中在这里，避免配置散落在各个模块中。
API Key 只由 Streamlit 页面在运行时传入，不从本地文件或环境变量读取。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# 当前文件位于 src/competitor_agent/config.py，parents[2] 对应项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    """运行时配置对象。

    使用 frozen=True 是为了避免运行过程中误改配置。例如如果某个函数不小心
    修改了 `reports_dir`，后续报告可能写到错误位置；冻结后能尽早暴露问题。
    """

    project_root: Path = PROJECT_ROOT
    cache_dir: Path = PROJECT_ROOT / "data" / "cache"
    reports_dir: Path = PROJECT_ROOT / "data" / "reports"

    # Streamlit 页面会把 API Key 作为运行时参数传给工作流。
    deepseek_model: str = "deepseek-chat"
    model_provider: str = "deepseek"

    # Tavily 搜索默认参数。
    tavily_api_base_url: str = "https://api.tavily.com"
    tavily_search_depth: str = "advanced"
    tavily_max_results: int = 5

    # Ollama 本地模型配置。搜索仍然使用 Tavily。
    ollama_model: str = "llama3.2:latest"
    ollama_host: str = "http://localhost:11434"

    def ensure_directories(self) -> None:
        """确保运行时必需的目录存在。"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)




# 模块级单例：其他模块直接 `from competitor_agent.config import settings` 使用。
settings = Settings()
