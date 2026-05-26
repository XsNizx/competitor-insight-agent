"""项目核心数据模型。

本模块定义 Agent 之间传递的结构化对象。相比直接传递大段自然语言，
结构化对象更容易缓存、验证、导出为 JSON，也方便后续扩展到 Web API
或可视化界面。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Source:
    """一条资料来源。

    SearchAgent 和 ExtractorAgent 会用它记录官网、定价页、文档、新闻、
    用户社区等来源。最终报告中的关键判断应该能追溯到这些来源。
    """

    title: str
    source_url: str
    summary: str
    relevance: str
    source_type: str = "web"


@dataclass
class Pricing:
    """产品定价信息。

    `free` 使用三态值：True 表示确认有免费版，False 表示确认没有免费版，
    None 表示资料不足，暂时无法判断。
    """

    free: bool | None = None
    paid_plans: list[str] = field(default_factory=list)
    note: str = "unknown"


@dataclass
class CompetitorProfile:
    """单个竞品的结构化画像。

    这个对象是“资料检索”和“信息抽取”之后的核心产物。后续 AnalystAgent
    会基于多个 `CompetitorProfile` 做横向比较。
    """

    name: str
    website: str = "unknown"
    positioning: str = "unknown"
    target_users: list[str] = field(default_factory=list)
    core_features: list[str] = field(default_factory=list)
    pricing: Pricing = field(default_factory=Pricing)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    user_feedback: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)


@dataclass
class AnalysisPlan:
    """一次竞品分析的执行计划。

    PlannerAgent 从用户输入中生成该对象，用来告诉后续流程：分析主题是什么、
    要分析哪些竞品、需要覆盖哪些维度、需要哪些资料来源。
    """

    topic: str
    competitor_names: list[str]
    analysis_dimensions: list[str]
    required_sources: list[str]


@dataclass
class ComparisonReport:
    """最终报告的结构化中间结果。

    ReporterAgent 会把这个对象渲染成 Markdown。保留结构化形态的好处是：
    同一份分析结果既能写 Markdown，也能输出 JSON，未来还可以导出为 PPT、
    PDF 或前端页面。
    """

    topic: str
    competitors: list[CompetitorProfile]
    feature_matrix: list[dict[str, Any]]
    pricing_matrix: list[dict[str, Any]]
    swot: dict[str, dict[str, list[str]]]
    opportunities: list[str]
    recommendations: list[str]
    source_summary: list[Source]
    risks: list[str] = field(default_factory=list)


def to_dict(value: Any) -> Any:
    """把 dataclass/list/dict 递归转换成普通 Python 数据。

    这个函数主要服务两个场景：
    1. 写入 JSON 缓存；
    2. 在命令行使用 `--json` 输出结构化结果。
    """

    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    return value


def source_from_dict(data: dict[str, Any]) -> Source:
    """从缓存字典恢复 `Source` 对象。

    缓存文件可能来自历史运行结果或人工编辑，因此这里用 `dict.get()` 给每个字段
    提供默认值，避免缺字段时直接崩溃。
    """

    return Source(
        title=data.get("title", "unknown"),
        source_url=data.get("source_url", "unknown"),
        summary=data.get("summary", ""),
        relevance=data.get("relevance", "unknown"),
        source_type=data.get("source_type", "web"),
    )


def profile_from_dict(data: dict[str, Any]) -> CompetitorProfile:
    """从缓存字典恢复 `CompetitorProfile` 对象。

    JSON 只保存普通字典和列表，不保留 Python 类型信息。因此读取缓存后，
    需要显式把嵌套的 pricing 和 sources 字段恢复成 `Pricing`、`Source`
    这类项目内部对象。
    """

    pricing_data = data.get("pricing") or {}
    return CompetitorProfile(
        name=data.get("name", "unknown"),
        website=data.get("website", "unknown"),
        positioning=data.get("positioning", "unknown"),
        target_users=list(data.get("target_users") or []),
        core_features=list(data.get("core_features") or []),
        pricing=Pricing(
            free=pricing_data.get("free"),
            paid_plans=list(pricing_data.get("paid_plans") or []),
            note=pricing_data.get("note", "unknown"),
        ),
        strengths=list(data.get("strengths") or []),
        weaknesses=list(data.get("weaknesses") or []),
        user_feedback=list(data.get("user_feedback") or []),
        sources=[source_from_dict(item) for item in data.get("sources", [])],
    )
