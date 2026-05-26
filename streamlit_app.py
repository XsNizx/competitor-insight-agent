"""CompetitorInsightAgent 的 Streamlit 前端页面。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from competitor_agent.agno_workflow import AgnoCompetitorWorkflow
from competitor_agent.config import settings
from competitor_agent.tools.cache_tools import slugify


st.set_page_config(
    page_title="竞品洞察智能体",
    page_icon="CI",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _inject_style() -> None:
    """注入页面样式，让 Streamlit 默认控件看起来更像一个完整工具。"""

    st.markdown(
        """
        <style>
        .block-container { padding-top: 2rem; max-width: 1220px; }
        .ci-hero {
            border: 1px solid #d9e2ec;
            border-radius: 8px;
            padding: 22px 24px;
            background: linear-gradient(135deg, #f8fbff 0%, #f7f7f2 100%);
            margin-bottom: 18px;
        }
        .ci-hero h1 { margin: 0 0 8px 0; font-size: 2.1rem; letter-spacing: 0; }
        .ci-hero p { margin: 0; color: #52606d; font-size: 1rem; line-height: 1.7; }
        .ci-pill {
            display: inline-block;
            border: 1px solid #bcccdc;
            border-radius: 999px;
            padding: 4px 10px;
            margin-right: 8px;
            color: #334e68;
            background: #ffffff;
            font-size: .86rem;
        }
        .stDownloadButton button, .stButton button { border-radius: 6px; font-weight: 600; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _init_state() -> None:
    """初始化页面状态，保存上一次报告和进度事件。"""

    st.session_state.setdefault("markdown", "")
    st.session_state.setdefault("report_topic", "")
    st.session_state.setdefault("events", [])


def _append_event(title: str, detail: str, status_box: Any) -> None:
    """接收工作流进度回调，并刷新页面中的状态显示。"""

    st.session_state.events.append((title, detail))
    status_box.info(f"**{title}**：{detail}")


def _build_sidebar() -> dict[str, Any]:
    """渲染侧栏配置，并返回工作流初始化所需参数。"""

    with st.sidebar:
        st.header("运行配置")
        model_label = st.radio(
            "模型选择",
            ["外部模型：DeepSeek", "本地模型：Ollama llama3.2"],
            index=0,
            help="两种模型都会使用 Tavily 在线搜索；区别只在 LLM 来自 DeepSeek 还是本地 Ollama。",
        )
        model_provider = "ollama" if model_label.startswith("本地") else "deepseek"

        st.caption("搜索固定使用 Tavily，因此无论选择哪种模型都需要 Tavily API Key。")
        tavily_api_key = st.text_input("Tavily API Key", type="password", placeholder="请输入 Tavily API Key")

        if model_provider == "deepseek":
            st.caption("外部模型需要 DeepSeek API Key。")
            deepseek_api_key = st.text_input("DeepSeek API Key", type="password", placeholder="请输入 DeepSeek API Key")
            model_id = st.text_input("DeepSeek 模型", value=settings.deepseek_model)
            ollama_host = None
            ready = bool(tavily_api_key.strip() and deepseek_api_key.strip() and model_id.strip())
            if not ready:
                st.warning("请先填写 Tavily API Key、DeepSeek API Key 和模型名。")
        else:
            st.caption("本地模型不需要模型 API Key，但需要本机 Ollama 服务已启动，并已拉取 llama3.2:latest。")
            deepseek_api_key = ""
            model_id = st.text_input("Ollama 模型", value=settings.ollama_model or "llama3.2:latest")
            ollama_host = st.text_input("Ollama 地址", value=settings.ollama_host)
            ready = bool(tavily_api_key.strip() and model_id.strip() and ollama_host.strip())
            if not ready:
                st.warning("请先填写 Tavily API Key，并确认 Ollama 模型名和地址。")

        use_cache = st.toggle(
            "使用竞品画像缓存",
            value=False,
            help="开启后，重复分析同名竞品时会优先读取 data/cache/agno 中的历史画像。",
        )
        if ready:
            st.success("配置已完成，可以开始分析。")
        st.divider()
        st.caption("报告生成后会在主区域展示 Markdown，并提供下载按钮。")

    return {
        "model_provider": model_provider,
        "deepseek_api_key": deepseek_api_key.strip(),
        "tavily_api_key": tavily_api_key.strip(),
        "model_id": model_id.strip(),
        "ollama_host": ollama_host.strip() if ollama_host else None,
        "use_cache": use_cache,
        "ready": ready,
    }


def main() -> None:
    """渲染 Streamlit 页面，并在用户提交后运行多智能体工作流。"""

    _inject_style()
    _init_state()

    config = _build_sidebar()
    ready = config["ready"]
    mode_label = "Ollama 本地模型 llama3.2 + Tavily 在线搜索" if config["model_provider"] == "ollama" else "DeepSeek 外部模型 + Tavily 在线搜索"

    st.markdown(
        f"""
        <div class="ci-hero">
          <span class="ci-pill">Agno 多智能体</span>
          <span class="ci-pill">{mode_label}</span>
          <span class="ci-pill">Markdown 报告</span>
          <h1>竞品洞察智能体</h1>
          <p>输入一个产品时，系统会自动发现两个直接竞品；无论产品来自用户输入还是系统补充，报告都会把三者作为并列对象进行横向对比。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([0.95, 1.25], gap="large")

    with left:
        st.subheader("发送请求")
        request = st.text_area(
            "分析需求",
            value="对 chatgpt 和它的竞品做市场分析",
            height=140,
            placeholder="例如：分析 Figma；或：分析 Figma、Canva、Miro 这三个协作设计产品",
            disabled=not ready,
        )
        submitted = st.button("开始分析", type="primary", disabled=not ready or not request.strip(), use_container_width=True)
        if not ready:
            st.info("请先在侧栏完成当前模型所需配置。")

        st.subheader("处理状态")
        status_box = st.empty()
        status_box.info("等待开始...")

    with right:
        st.subheader("Markdown 报告")
        report_box = st.empty()
        if st.session_state.markdown:
            report_box.markdown(st.session_state.markdown)
            filename = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slugify(st.session_state.report_topic or 'competitor-report')}.md"
            st.download_button(
                "下载 Markdown 报告",
                data=st.session_state.markdown.encode("utf-8"),
                file_name=filename,
                mime="text/markdown",
                use_container_width=True,
            )
        else:
            report_box.info("报告会在分析完成后显示在这里。")

    if submitted:
        st.session_state.events = []
        st.session_state.markdown = ""
        st.session_state.report_topic = ""
        status_box.info("**准备启动**：正在初始化多智能体工作流...")

        def progress_callback(title: str, detail: str, percent: int) -> None:
            _append_event(title, detail, status_box)

        try:
            workflow = AgnoCompetitorWorkflow(
                use_cache=config["use_cache"],
                model_id=config["model_id"] if config["model_provider"] == "deepseek" else None,
                deepseek_api_key=config["deepseek_api_key"],
                tavily_api_key=config["tavily_api_key"],
                model_provider=config["model_provider"],
                ollama_model=config["model_id"] if config["model_provider"] == "ollama" else None,
                ollama_host=config["ollama_host"],
                progress_callback=progress_callback,
            )
            report, markdown = workflow.run(request.strip())
        except Exception as exc:
            status_box.error(f"**运行失败**：{exc}")
            st.error(f"分析失败：{exc}")
            return

        st.session_state.markdown = markdown
        st.session_state.report_topic = report.topic
        status_box.success("**分析完成**")
        report_box.markdown(markdown)
        filename = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slugify(report.topic)}.md"
        st.download_button(
            "下载 Markdown 报告",
            data=markdown.encode("utf-8"),
            file_name=filename,
            mime="text/markdown",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
