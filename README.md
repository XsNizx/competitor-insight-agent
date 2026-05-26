# Competitor Insight Agent

基于 Agno 多智能体框架的智能竞品分析工具。用户在 Streamlit 网页中输入产品或分析需求后，系统会自动规划竞品、调用 Tavily 搜索公开资料、抽取结构化竞品画像，并生成中文 Markdown 竞品分析报告。

> API Key 只在网页侧栏中填写，项目不需要 `.env` 文件，也不会把密钥写入仓库文件。

## Highlights

- **多智能体分析流程**：Planner、Search、Extractor、Analyst、Reporter 分工协作
- **真实网页证据**：使用 Tavily 搜索公开信息，降低纯模型幻觉风险
- **结构化输出**：用 Pydantic schema 约束中间结果，便于校验和复用
- **双模型模式**：支持 DeepSeek 在线模型，也支持本地 Ollama 模型
- **网页交互**：基于 Streamlit 提供可视化输入、运行状态和 Markdown 下载
- **可选缓存**：可复用已生成的竞品画像，减少重复搜索和模型调用

## Workflow

```text
用户输入分析需求
        │
        ▼
PlannerAgent 识别分析主题并补齐 3 个并列产品
        │
        ▼
SearchAgent 调用 Tavily 搜索公开网页资料
        │
        ▼
ExtractorAgent 抽取单个产品的结构化竞品画像
        │
        ▼
AnalystAgent 横向对比功能、定价、SWOT、机会与风险
        │
        ▼
ReportAgent 生成中文 Markdown 报告
```

## Tech Stack

- Python 3.10+
- [Agno](https://github.com/agno-agi/agno): 多智能体编排
- [Streamlit](https://streamlit.io/): Web UI
- Tavily Search API: 在线检索
- DeepSeek 或 Ollama: LLM 推理
- Pydantic: 结构化输出校验

## Quick Start

克隆项目后，建议创建虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

启动网页：

```bash
streamlit run streamlit_app.py
```

打开 Streamlit 页面后：

1. 在侧栏选择模型：DeepSeek 或 Ollama
2. 填写 Tavily API Key
3. 如果选择 DeepSeek，再填写 DeepSeek API Key 和模型名
4. 如果选择 Ollama，确认本地 Ollama 服务已启动，并填写模型名和服务地址
5. 输入分析需求，例如：`分析 Figma 和它的竞品`
6. 点击“开始分析”，等待报告生成后下载 Markdown

## Project Structure

```text
.
├── README.md
├── pyproject.toml
├── streamlit_app.py
├── data/
│   ├── cache/
│   │   └── .gitkeep
│   └── reports/
│       └── .gitkeep
└── src/
    └── competitor_agent/
        ├── agno_workflow.py        # Agno 多智能体主流程
        ├── config.py               # 路径和默认模型参数
        ├── models.py               # 业务数据结构
        └── tools/
            ├── cache_tools.py      # 竞品画像缓存
            ├── real_search_tools.py # Tavily 搜索工具
            └── report_tools.py     # Markdown 报告保存工具
```

## Runtime Files

运行过程中可能生成：

- `data/cache/**/*.json`: 竞品画像缓存
- `data/reports/**/*.md`: 本地保存的 Markdown 报告

这些文件已被 `.gitignore` 忽略，仓库只保留 `.gitkeep` 来维持目录结构。

## Security Notes

- 不要把真实 API Key 写入源码、README 或任何将要提交的文件。
- 本项目不依赖 `.env`，API Key 在网页运行时输入。
- 如果曾经误提交过真实密钥，请立即吊销旧 Key，并清理 Git 历史后再公开仓库。

## License

本项目用于学习和课程实践。如需公开复用，可根据自己的发布需求补充许可证文件。
