from collections.abc import Iterable
from dataclasses import dataclass

from tradingagents.agents.analysts import fundamentals_analyst, market_analyst, news_analyst


@dataclass(frozen=True)
class AnalystNodeSpec:
    key: str
    agent_node: str
    clear_node: str
    report_key: str
    tools: tuple = ()

    @property
    def tool_node(self) -> str | None:
        """The node that runs this analyst's tool calls; None when it has no tools."""
        return f"tools_{self.key}" if self.tools else None


@dataclass(frozen=True)
class AnalystExecutionPlan:
    specs: list[AnalystNodeSpec]
    concurrency: int = 2


ANALYST_NODE_SPECS: dict[str, AnalystNodeSpec] = {
    "market": AnalystNodeSpec(
        key="market",
        agent_node="Market Analyst",
        clear_node="Msg Clear Market",
        report_key="market_report",
        tools=market_analyst.TOOLS,
    ),
    "social": AnalystNodeSpec(
        # Saved configs select this analyst as "social". It fetches its
        # sources before calling the model, so it has no tools.
        key="social",
        agent_node="Sentiment Analyst",
        clear_node="Msg Clear Sentiment",
        report_key="sentiment_report",
    ),
    "news": AnalystNodeSpec(
        key="news",
        agent_node="News Analyst",
        clear_node="Msg Clear News",
        report_key="news_report",
        tools=news_analyst.TOOLS,
    ),
    "fundamentals": AnalystNodeSpec(
        key="fundamentals",
        agent_node="Fundamentals Analyst",
        clear_node="Msg Clear Fundamentals",
        report_key="fundamentals_report",
        tools=fundamentals_analyst.TOOLS,
    ),
}


def build_analyst_execution_plan(
    selected_analysts: Iterable[str],
    concurrency: int = 2,
) -> AnalystExecutionPlan:
    specs: list[AnalystNodeSpec] = []
    for analyst_key in selected_analysts:
        spec = ANALYST_NODE_SPECS.get(analyst_key)
        if spec is None:
            raise ValueError(f"unknown analyst key: {analyst_key}")
        specs.append(spec)

    if not specs:
        raise ValueError("at least one analyst must be selected")

    width = max(1, int(concurrency))
    return AnalystExecutionPlan(specs=specs, concurrency=width)


def current_wave(specs: list[AnalystNodeSpec], concurrency: int, done: set[str]) -> list[AnalystNodeSpec]:
    """The wave that is running: the first one that still has an analyst to file."""
    for wave in analyst_waves(specs, concurrency):
        if any(spec.key not in done for spec in wave):
            return wave
    return []


def analyst_waves(specs: list[AnalystNodeSpec], concurrency: int) -> list[list[AnalystNodeSpec]]:
    """Split analysts into waves of ``concurrency``.

    A wave runs together. The next wave starts when that wave has filed.
    Width 1 is the serial layout. The daily jobs use 2.
    """
    width = max(1, int(concurrency))
    return [specs[i:i + width] for i in range(0, len(specs), width)]


