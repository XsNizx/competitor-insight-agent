"""Agno + DeepSeek + Tavily 驱动的多智能体竞品分析工作流。

这个模块是项目的核心编排层。它负责创建五个 Agno Agent，并按固定顺序
执行：规划、检索、抽取、分析、报告。每个 Agent 都被要求输出 Pydantic
schema 约束的结构化结果，从而降低大模型自由发挥导致的格式错误。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from competitor_agent.config import settings
from competitor_agent.models import (
    AnalysisPlan,
    ComparisonReport,
    CompetitorProfile,
    Pricing,
    Source,
    profile_from_dict,
    to_dict,
)
from competitor_agent.tools.cache_tools import read_cache, write_cache
from competitor_agent.tools.real_search_tools import make_tavily_search_tool


class SourceOutput(BaseModel):
    """LLM 输出中的资料来源 schema。"""

    title: str = Field(default="unknown")
    source_url: str = Field(default="unknown")
    summary: str = Field(default="")
    relevance: str = Field(default="unknown")
    source_type: str = Field(default="web")


class PricingOutput(BaseModel):
    """LLM 输出中的定价信息 schema。"""

    free: bool | None = None
    paid_plans: list[str] = Field(default_factory=list)
    note: str = Field(default="unknown")


class CompetitorProfileOutput(BaseModel):
    """LLM 输出中的单个竞品画像 schema。"""

    name: str
    website: str = Field(default="unknown")
    positioning: str = Field(default="unknown")
    target_users: list[str] = Field(default_factory=list)
    core_features: list[str] = Field(default_factory=list)
    pricing: PricingOutput = Field(default_factory=PricingOutput)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    user_feedback: list[str] = Field(default_factory=list)
    sources: list[SourceOutput] = Field(default_factory=list)


class AnalysisPlanOutput(BaseModel):
    """PlannerAgent 的输出 schema。"""

    model_config = ConfigDict(extra="forbid")

    topic: str
    competitor_names: list[str] = Field(min_length=3, max_length=3)
    analysis_dimensions: list[str] = Field(default_factory=list)
    required_sources: list[str] = Field(default_factory=list)


class SearchEvidenceOutput(BaseModel):
    """SearchAgent 的输出 schema。"""

    product_name: str
    evidence_summary: list[str] = Field(default_factory=list)
    sources: list[SourceOutput] = Field(default_factory=list)


class ComparisonReportOutput(BaseModel):
    """AnalystAgent 的输出 schema。"""

    topic: str
    competitors: list[CompetitorProfileOutput]
    feature_matrix: list[dict[str, Any]] = Field(default_factory=list)
    pricing_matrix: list[dict[str, Any]] = Field(default_factory=list)
    swot: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    opportunities: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    source_summary: list[SourceOutput] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class MarkdownReportOutput(BaseModel):
    """ReportAgent 的输出 schema。"""

    markdown: str = Field(description="最终中文 Markdown 竞品分析报告")


class AgnoCompetitorWorkflow:
    """协调五个 LLM 智能体完成完整竞品分析。

    这个类是 CLI 真正调用的业务入口。它不直接做具体分析，而是负责：
    1. 校验 API Key；
    2. 创建 DeepSeek 模型和 Agno Agent；
    3. 在 Agent 之间传递结构化结果；
    4. 读写竞品画像缓存；
    5. 在结果明显跑偏时及时报错。
    """

    def __init__(
        self,
        use_cache: bool = True,
        model_id: str | None = None,
        deepseek_api_key: str | None = None,
        tavily_api_key: str | None = None,
        model_provider: str | None = None,
        ollama_model: str | None = None,
        ollama_host: str | None = None,
        progress_callback: Callable[[str, str, int], None] | None = None,
    ) -> None:
        """初始化工作流并创建五个 Agent。

        Args:
            use_cache: 是否读取和写入 `data/cache/agno` 下的竞品画像缓存。
            model_id: 可选模型名；不传时使用默认 DeepSeek 模型。
        """

        resolved_model_provider = (model_provider or settings.model_provider).lower()
        if resolved_model_provider not in {"deepseek", "ollama"}:
            raise RuntimeError("model_provider must be either 'deepseek' or 'ollama'.")

        try:
            from agno.agent import Agent
        except Exception as exc:  # pragma: no cover - 依赖缺失时才触发
            raise RuntimeError("Agno is not installed. Run `pip install -e .` first.") from exc

        resolved_tavily_api_key = tavily_api_key
        if not resolved_tavily_api_key:
            raise RuntimeError("Tavily API Key is required because all model providers use Tavily online search.")

        search_tool = make_tavily_search_tool(
            api_key=resolved_tavily_api_key,
            base_url=settings.tavily_api_base_url,
            search_depth=settings.tavily_search_depth,
            max_results=settings.tavily_max_results,
            time_range=settings.tavily_time_range,
            news_days=settings.tavily_news_days,
        )
        search_tool_name = "tavily_search"
        evidence_provider = "Tavily 搜索"

        if resolved_model_provider == "ollama":
            try:
                from agno.models.ollama import Ollama
            except Exception as exc:  # pragma: no cover - 依赖缺失时才触发
                raise RuntimeError(
                    "Ollama model support is not available. Run `pip install -e .`, install `ollama`, "
                    "and make sure the Ollama service is running."
                ) from exc
            model_name = ollama_model or model_id or settings.ollama_model
            model = Ollama(id=model_name, host=ollama_host or settings.ollama_host)
        else:
            resolved_deepseek_api_key = deepseek_api_key
            if not resolved_deepseek_api_key:
                raise RuntimeError("DeepSeek API Key is required for DeepSeek LLM agents.")
            try:
                from agno.models.deepseek import DeepSeek
            except Exception as exc:  # pragma: no cover - 依赖缺失时才触发
                raise RuntimeError("DeepSeek model support is not available. Run `pip install -e .` first.") from exc
            model_name = model_id or settings.deepseek_model
            model = DeepSeek(id=model_name, api_key=resolved_deepseek_api_key)
        self.cache_dir = settings.cache_dir / "agno"
        self.use_cache = use_cache
        self.progress_callback = progress_callback
        self.model_provider = resolved_model_provider
        self.search_tool_name = search_tool_name
        self.evidence_provider = evidence_provider

        self.planner = Agent(
            name="PlannerAgent",
            model=model,
            tools=[search_tool],
            tool_call_limit=3,
            output_schema=AnalysisPlanOutput,
            use_json_mode=True,
            instructions=[
                "你是竞品分析系统中的规划智能体 PlannerAgent。",
                "把中文用户需求拆解成结构化分析计划，只提取真实产品、公司或服务名称。",
                f"如果用户只输入 1 个产品，必须调用 {search_tool_name} 搜索并补充恰好 2 个直接竞品，补齐后恰好 3 个产品是并列分析对象。禁止多补，也不许少补。",
                f"如果用户输入 2 个产品，必须调用 {search_tool_name} 再补充恰好 1 个同领域直接竞品，总共恰好 3 个产品。",
                "如果用户已经输入 3 个产品，直接使用用户给出的 3 个产品，不要再搜索补充或替换任何产品。",
                "competitor_names 必须恰好包含 3 个互不重复的真实产品名称，不要输出泛称、品类词或任务词。无论什么情况，总数就是 3 个，不能是 2 个、4 个或更多。",
                "不要把“分析”“竞品”“报告”“对比”等任务词当成竞品。",
                "分析维度至少覆盖产品定位、目标用户、核心功能、定价、商业模式、生态/渠道、用户反馈、SWOT、差异化机会。",
                "输出必须严格符合 AnalysisPlanOutput schema，只包含 topic、competitor_names、analysis_dimensions、required_sources，不要输出 Markdown 或解释文字。",
            ],
        )
        self.searcher = Agent(
            name="SearchAgent",
            model=model,
            tools=[search_tool],
            tool_call_limit=8,
            output_schema=SearchEvidenceOutput,
            use_json_mode=True,
            instructions=[
                "你是竞品分析系统中的资料检索智能体 SearchAgent。",
                f"必须调用 {search_tool_name} 获取 {evidence_provider} 证据，不能凭记忆生成来源。",
                f"优先检索最近 {settings.tavily_news_days} 天到 1 个月内发布或更新的资料；调用工具时通用搜索使用 time_range='month'，新闻、官方博客、更新公告使用 topic='news' 和 days={settings.tavily_news_days}。",
                "围绕官网、定价页、产品文档、官方博客/新闻、更新日志、第三方评测、用户社区或评论分别检索；所有模型供应商都必须使用 Tavily 在线搜索结果作为证据。",
                "如果最新资料不足，可以补充最近 1 年内的高可信来源，但必须在 summary 或 relevance 中说明资料时效性限制。",
                "输出来源时保留 title、source_url、summary、relevance、source_type。",
                "每个 summary 不超过 80 个汉字，sources 最多返回 6 条；不要把网页全文或工具原始 JSON 整段复制到输出。",
                "输出必须严格符合 SearchEvidenceOutput schema，不要输出 Markdown 或解释文字。",
            ],
        )
        self.extractor = Agent(
            name="ExtractorAgent",
            model=model,
            output_schema=CompetitorProfileOutput,
            use_json_mode=True,
            instructions=[
                "你是竞品分析系统中的结构化抽取智能体 ExtractorAgent。",
                "基于搜索证据抽取单个竞品画像，包括官网、定位、用户、功能、定价、优劣势、用户反馈和来源。",
                "证据不足时写 unknown、null 或空列表，不要编造。",
                "sources 必须来自输入证据，关键结论要能被 sources 支撑。",
                "输出必须严格符合 CompetitorProfileOutput schema，不要输出 Markdown 或解释文字。",
            ],
        )
        self.analyst = Agent(
            name="AnalystAgent",
            model=model,
            output_schema=ComparisonReportOutput,
            use_json_mode=True,
            instructions=[
                "你是竞品分析系统中的策略分析智能体 AnalystAgent。",
                "基于多个结构化竞品画像做横向比较，生成 feature_matrix、pricing_matrix、SWOT、机会点、建议、来源汇总和风险。",
                "所有输入产品都是并列分析对象，即使其中一两个是系统搜索补充的，也必须与用户输入的产品同等对待。",
                "opportunities、recommendations 和 risks 必须面向全部产品的整体横向对比，覆盖三者各自的机会、建议和风险；不要默认偏向第一个产品，也不要偏向用户最先输入的产品。",
                "功能对比要体现差异、成熟度或证据不足，不要只机械写有/无。",
                "所有判断必须基于输入来源；不确定信息必须进入 risks。",
                "输出必须严格符合 ComparisonReportOutput schema，不要输出 Markdown 或解释文字。",
            ],
        )
        self.reporter = Agent(
            name="ReportAgent",
            model=model,
            output_schema=MarkdownReportOutput,
            use_json_mode=True,
            markdown=True,
            instructions=[
                "你是竞品分析系统中的中文报告撰写智能体 ReportAgent。",
                "把结构化 ComparisonReport 写成专业、清晰、适合中文用户阅读的 Markdown 报告。",
                "报告必须包含：结论摘要、产品概览、核心功能对比、定价策略对比、SWOT 分析、差异化机会、产品策略建议、风险提示、来源列表。",
                "“差异化机会”“产品策略建议”和“风险提示”必须面向所有并列产品的整体横向对比，并尽量覆盖每个产品；不要因为用户只输入了一个产品就把报告写成单一产品建议。",
                "来源列表必须保留 URL；没有来源支撑的判断不要写成确定事实。",
                "输出必须严格符合 MarkdownReportOutput schema，不要输出额外解释。",
            ],
        )

    def run(self, user_request: str) -> tuple[ComparisonReport, str]:
        """执行完整竞品分析流程。

        Args:
            user_request: 用户在命令行输入的自然语言需求。

        Returns:
            二元组：结构化 `ComparisonReport` 和最终 Markdown 文本。
        """

        settings.ensure_directories()
        self._emit_progress("正在规划与发现竞品", f"PlannerAgent 正在解析请求；如果只给出一个产品，会先通过{self.evidence_provider}寻找两个直接竞品。", 8)

        plan_output = self._run_structured(self.planner, user_request, AnalysisPlanOutput)
        plan = self._plan_from_output(plan_output)
        if not plan.competitor_names:
            raise RuntimeError("PlannerAgent did not return any competitors.")
        if len(plan.competitor_names) != 3:
            raise RuntimeError(f"PlannerAgent 必须返回恰好 3 个产品（用户提供的 + 补充的竞品），实际返回了 {len(plan.competitor_names)} 个：{'、'.join(plan.competitor_names)}")

        self._emit_progress("规划完成", f"识别到竞品：{'、'.join(plan.competitor_names)}。", 18)
        competitors = [self._get_profile(name, plan) for name in plan.competitor_names]

        self._emit_progress("正在分析", "AnalystAgent 正在进行横向对比、SWOT 和策略建议生成。", 78)
        report_output = self._run_structured(
            self.analyst,
            {
                "topic": plan.topic,
                "analysis_dimensions": plan.analysis_dimensions,
                "competitors": [to_dict(profile) for profile in competitors],
            },
            ComparisonReportOutput,
        )
        report = self._report_from_output(report_output)

        # 防止模型跑偏：分析阶段必须围绕 Planner 给出的竞品继续分析。
        expected_names = {name.lower() for name in plan.competitor_names}
        actual_names = {item.name.lower() for item in report.competitors}
        if not expected_names.issubset(actual_names):
            missing = ", ".join(plan.competitor_names)
            actual = ", ".join(item.name for item in report.competitors)
            raise RuntimeError(f"AnalystAgent returned competitors inconsistent with the plan. expected={missing}; actual={actual}")

        self._emit_progress("正在撰写报告", "ReportAgent 正在把结构化分析结果写成 Markdown 报告。", 90)
        markdown_output = self._run_structured(
            self.reporter,
            {"plan": to_dict(plan), "report": to_dict(report)},
            MarkdownReportOutput,
        )
        self._emit_progress("报告完成", "Markdown 报告已经生成，可以在页面查看或下载。", 100)
        return report, markdown_output.markdown.strip() + "\n"

    def _get_profile(self, product_name: str, plan: AnalysisPlan) -> CompetitorProfile:
        """获取单个竞品画像。

        如果缓存开启且命中，就直接从 JSON 缓存恢复画像；否则调用 SearchAgent
        和 ExtractorAgent 重新搜索、抽取，并把结果写入缓存。
        """

        if self.use_cache:
            self._emit_progress("正在检查缓存", f"检查 {product_name} 是否已有历史竞品画像。", 20)
            cached = read_cache(product_name, self.cache_dir)
            if cached:
                self._emit_progress("缓存命中", f"{product_name} 使用缓存画像，跳过搜索和抽取。", 32)
                return profile_from_dict(cached)

        self._emit_progress("正在搜索网页", f"SearchAgent 正在为 {product_name} 调用 {self.search_tool_name} 获取资料。", 35)
        today = date.today().isoformat()
        current_year = date.today().year
        evidence = self._run_structured(
            self.searcher,
            {
                "product_name": product_name,
                "topic": plan.topic,
                "freshness_requirement": f"当前日期是 {today}。优先使用最近 30 天或 1 个月内发布/更新的资料；不足时再使用 {current_year} 年内资料。",
                "required_sources": plan.required_sources,
                "search_queries": [
                    f"{product_name} 最新 产品定位 主要功能 {current_year}",
                    f"{product_name} 最新定价 价格变动 pricing update {current_year}",
                    f"{product_name} release notes changelog product updates {current_year}",
                    f"{product_name} 最新 用户评价 优点 缺点 reviews {current_year}",
                ],
            },
            SearchEvidenceOutput,
        )
        self._emit_progress("正在抽取信息", f"ExtractorAgent 正在把 {product_name} 的搜索资料整理成结构化画像。", 55)
        profile_output = self._run_structured(
            self.extractor,
            {"product_name": product_name, "evidence": evidence.model_dump()},
            CompetitorProfileOutput,
        )
        profile = self._profile_from_output(profile_output)
        if self.use_cache:
            write_cache(product_name, to_dict(profile), self.cache_dir)
        return profile

    def _emit_progress(self, title: str, detail: str, percent: int) -> None:
        """把工作流进度发送给前端或其他调用方。"""

        if self.progress_callback:
            self.progress_callback(title, detail, percent)

    def _run_structured(self, agent: Any, input_value: Any, schema: type[BaseModel]) -> BaseModel:
        """运行单个 Agno Agent，并把返回结果解析为指定 schema。

        注意：这里不会把 dict 直接传给 `agent.run()`，而是先转成 JSON 文本。
        这样可以避免 Agno 把普通业务 dict 误判成缺少 `role` 字段的 Message。
        """

        formatted_input = self._format_agent_input(input_value)

        response = agent.run(
            formatted_input,
            output_schema=schema,
            session_id=f"competitor-insight-{agent.name}",
            add_history_to_context=False,
        )
        content = getattr(response, "content", response)
        if isinstance(content, schema):
            return content
        if isinstance(content, dict):
            return schema.model_validate(content)
        if isinstance(content, str):
            cleaned = self._strip_json_fence(content)
            try:
                return schema.model_validate_json(cleaned)
            except ValidationError as exc:
                raise RuntimeError(
                    f"{agent.name} returned invalid JSON for {schema.__name__}. "
                    f"content_tail={cleaned[-1000:]}"
                ) from exc
        raise TypeError(f"{agent.name} returned unsupported content type: {type(content)!r}")

    def _format_agent_input(self, input_value: Any) -> str:
        """把 Agent 输入统一格式化成文本。

        Agno 的 `run()` 可以接收多种输入类型，但普通 dict 在某些路径下会被
        当成 Message 校验。这里统一转成“说明文字 + JSON”的字符串，既清晰，
        也能让模型知道后面是结构化任务输入。
        """

        if isinstance(input_value, str):
            return input_value
        if isinstance(input_value, BaseModel):
            input_value = input_value.model_dump()
        return "请基于以下 JSON 输入完成任务：\n" + json.dumps(input_value, ensure_ascii=False, indent=2)

    def _strip_json_fence(self, value: str) -> str:
        """去掉模型可能包裹在 JSON 外层的 Markdown 代码块。"""

        text = value.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        return text.strip()

    def _plan_from_output(self, output: AnalysisPlanOutput) -> AnalysisPlan:
        """把 PlannerAgent 的 Pydantic 输出转换成项目 dataclass。"""

        competitor_names = self._dedupe_names(output.competitor_names)

        return AnalysisPlan(
            topic=output.topic,
            competitor_names=competitor_names,
            analysis_dimensions=output.analysis_dimensions,
            required_sources=output.required_sources,
        )

    def _dedupe_names(self, names: list[str]) -> list[str]:
        """去掉空名称和重复名称，同时保留 PlannerAgent 给出的顺序。"""

        result: list[str] = []
        seen: set[str] = set()
        for name in names:
            normalized = name.strip()
            key = normalized.casefold()
            if normalized and key not in seen:
                result.append(normalized)
                seen.add(key)
        return result

    def _profile_from_output(self, output: CompetitorProfileOutput) -> CompetitorProfile:
        """把竞品画像 schema 转换成 `CompetitorProfile`。"""

        return CompetitorProfile(
            name=output.name,
            website=output.website,
            positioning=output.positioning,
            target_users=output.target_users,
            core_features=output.core_features,
            pricing=Pricing(
                free=output.pricing.free,
                paid_plans=output.pricing.paid_plans,
                note=output.pricing.note,
            ),
            strengths=output.strengths,
            weaknesses=output.weaknesses,
            user_feedback=output.user_feedback,
            sources=[self._source_from_output(source) for source in output.sources],
        )

    def _report_from_output(self, output: ComparisonReportOutput) -> ComparisonReport:
        """把 AnalystAgent 输出转换成最终结构化报告对象。"""

        return ComparisonReport(
            topic=output.topic,
            competitors=[self._profile_from_output(item) for item in output.competitors],
            feature_matrix=output.feature_matrix,
            pricing_matrix=output.pricing_matrix,
            swot=output.swot,
            opportunities=output.opportunities,
            recommendations=output.recommendations,
            source_summary=[self._source_from_output(source) for source in output.source_summary],
            risks=output.risks,
        )

    def _source_from_output(self, output: SourceOutput) -> Source:
        """把来源 schema 转换成 `Source` dataclass。"""

        return Source(
            title=output.title,
            source_url=output.source_url,
            summary=output.summary,
            relevance=output.relevance,
            source_type=output.source_type,
        )
