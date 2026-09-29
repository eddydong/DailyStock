"""One session for each name in the daily universe: all four analysts, then debate.

The universe is the five most-traded HKEX names and the five most-traded US
names. Each market has its own pre-open job, at 09:00 local time, and its
own data vendors. The analysts and the models are the same.

Verbosity is the framework default: full analyst narratives, one bull/bear
round, and one risk round. Nothing here shortens those prompts. To tighten
later without editing this file's flow:

- ``TRADINGAGENTS_MAX_TOKENS`` caps every reply. On DeepSeek Flash the cap
  includes hidden reasoning, so a low value can cut a rating off.
- ``TRADINGAGENTS_MAX_DEBATE_ROUNDS`` and ``TRADINGAGENTS_MAX_RISK_ROUNDS``
  repeat the debate. Leaving both at 1 is already the short setting.
- A brevity sentence would go in each agent's prompt, not in this job.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import yfinance as yf

from tradingagents.agents.rating import parse_rating
from tradingagents.daily.hkex import is_hkex_session
from tradingagents.daily.nyse import is_nyse_session
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

# All four desks. Order matches the CLI. Do not drop one to save tokens
# unless that choice is made on purpose.
ANALYSTS = ("market", "social", "news", "fundamentals")

# Five names from each market, ranked by session turnover on 2026-09-29.
# Hong Kong is that day's cash session. The US names are the last completed
# US session, 2026-09-28, because the US open was still ahead. ETFs are out.
HK_TICKERS = (
    "0700.HK",   # Tencent
    "9988.HK",   # Alibaba
    "6869.HK",   # Yangtze Optical Fibre
    "1810.HK",   # Xiaomi
    "9926.HK",   # Akeso
)
US_TICKERS = (
    "NVDA",
    "MU",
    "META",
    "TSLA",
    "AMD",
)
TICKERS = HK_TICKERS + US_TICKERS
TICKER = "NVDA"
_NY = ZoneInfo("America/New_York")
_HK = ZoneInfo("Asia/Hong_Kong")
# Each cash session opens at 09:30 local time. That market's job is 09:00,
# thirty minutes before. A US cash session is treated as complete a few
# minutes after the 16:00 close.
_CLOSE = time(16, 5)


def _is_hk(ticker: str) -> bool:
    canonical = normalize_symbol(ticker)
    return isinstance(canonical, str) and canonical.endswith(".HK")


def job_config(ticker: str = TICKER) -> dict:
    """Framework defaults, with the provider pinned to whatever ``.env`` set.

    ``DEFAULT_CONFIG`` already applies ``TRADINGAGENTS_*`` overrides, including
    the DeepSeek Flash pair when those variables are present. Debate depth
    stays at the default of one round unless the env overrides say otherwise.

    A US ticker keeps Yahoo, SEC, StockTwits, and Reddit. An HKEX ticker uses
    the Hong Kong quote, statement, and filing vendors. The graph, the
    analysts, and the models are the same either way. Shared macro tools
    (FRED, the global-news search) stay on the default vendors.
    """
    config = DEFAULT_CONFIG.copy()
    config["data_vendors"] = dict(config["data_vendors"])
    config["tool_vendors"] = dict(config.get("tool_vendors") or {})
    # Checkpointing lets a crashed local run resume. A Cloud Run task has an
    # ephemeral disk, so a retry there starts clean.
    config["checkpoint_enabled"] = True
    if _is_hk(ticker):
        config["data_vendors"].update({
            "core_stock_apis": "hk",
            "technical_indicators": "hk",
            "fundamental_data": "hk",
        })
        config["tool_vendors"].update({
            "get_news": "hk",
            "get_insider_transactions": "hk",
        })
    return config


def choose_session(session_dates: list[date], now: datetime) -> str:
    """Pick the latest session date that has already closed in New York."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=_NY)
    else:
        now = now.astimezone(_NY)
    today = now.date()
    if now.time() < _CLOSE:
        usable = [day for day in session_dates if day < today]
    else:
        usable = [day for day in session_dates if day <= today]
    if not usable:
        raise RuntimeError("no completed US session")
    return max(usable).isoformat()


def tickers_for(market: str) -> tuple[str, ...]:
    """The names one pre-open job analyzes."""
    if market == "hk":
        return HK_TICKERS
    if market == "us":
        return US_TICKERS
    raise ValueError(f"market must be 'hk' or 'us', got {market!r}")


def coming_hk_session(now: datetime | None = None) -> str | None:
    """The HKEX session about to open, or None when the exchange is closed.

    The date is today in Hong Kong, including a run at 09:00 before the 09:30
    open. A half day still opens at 09:30, so it is a session.
    """
    now = now or datetime.now(_HK)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_HK)
    else:
        now = now.astimezone(_HK)
    if not is_hkex_session(now.date()):
        return None
    return now.date().isoformat()


def coming_session_for(market: str, now: datetime | None = None) -> str | None:
    """The session the named market's pre-open job should analyze."""
    if market == "hk":
        return coming_hk_session(now)
    if market == "us":
        return coming_session(now)
    raise ValueError(f"market must be 'hk' or 'us', got {market!r}")


def coming_session(now: datetime | None = None) -> str | None:
    """The NYSE session about to open, or None when the exchange is closed.

    The date is today in New York, including a run at 09:00 before the 09:30
    open. Prices for that morning still end at the previous close, because
    today's cash bar does not exist yet. News, retail posts, live valuation
    fields, and prediction-market odds are current as of the run.
    """
    now = now or datetime.now(_NY)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_NY)
    else:
        now = now.astimezone(_NY)
    if not is_nyse_session(now.date()):
        return None
    return now.date().isoformat()


def last_completed_session(now: datetime | None = None) -> str:
    """The latest US session whose cash close is in the past, as YYYY-MM-DD."""
    now = now or datetime.now(_NY)
    hist = yf.Ticker(TICKER).history(period="15d", auto_adjust=True)
    if hist.empty:
        raise RuntimeError(f"{TICKER} returned no recent sessions")
    dates = []
    for stamp in hist.index:
        dates.append(stamp.date() if hasattr(stamp, "date") else stamp)
    return choose_session(dates, now)


def result_document(final_state: dict, rating: str, generated_at: str) -> dict:
    """The one JSON object stored for a session. Reports are kept in full."""
    debate = final_state.get("investment_debate_state") or {}
    risk = final_state.get("risk_debate_state") or {}
    decision = final_state.get("final_trade_decision") or ""
    return {
        "ticker": final_state.get("company_of_interest") or TICKER,
        "trade_date": final_state.get("trade_date"),
        "rating": rating,
        "summary": executive_summary(decision),
        "final_decision": decision,
        "market_report": final_state.get("market_report") or "",
        "sentiment_report": final_state.get("sentiment_report") or "",
        "news_report": final_state.get("news_report") or "",
        "fundamentals_report": final_state.get("fundamentals_report") or "",
        "investment_plan": final_state.get("investment_plan") or "",
        "trader_plan": final_state.get("trader_investment_plan") or "",
        "bull": debate.get("bull_history") or "",
        "bear": debate.get("bear_history") or "",
        "research_manager": debate.get("judge_decision") or "",
        "aggressive": risk.get("aggressive_history") or "",
        "conservative": risk.get("conservative_history") or "",
        "neutral": risk.get("neutral_history") or "",
        "risk_decision": risk.get("judge_decision") or "",
        "generated_at": generated_at,
    }


def executive_summary(decision: str) -> str:
    """The Portfolio Manager's short paragraph, for the prior-day tape.

    The full decision stays in ``final_decision``. This slice is only the
    line the older sessions show. It does not ask the model to write less.
    """
    text = decision or ""
    marker = "**Executive Summary**:"
    if marker in text:
        body = text.split(marker, 1)[1]
        stop = body.find("**Investment Thesis**:")
        if stop != -1:
            body = body[:stop]
        body = " ".join(body.split())
        if body:
            return body
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("**Rating**"):
            return " ".join(stripped.split())
    return ""


def run_session(trade_date: str | None = None, ticker: str = TICKER) -> dict:
    """Run one ticker for ``trade_date`` (default: the session opening this morning)."""
    if trade_date is None:
        trade_date = coming_hk_session() if _is_hk(ticker) else coming_session()
        if trade_date is None:
            closed = "HKEX" if _is_hk(ticker) else "NYSE"
            raise RuntimeError(f"{closed} is closed today")
    graph = TradingAgentsGraph(
        selected_analysts=list(ANALYSTS),
        debug=False,
        config=job_config(ticker),
    )
    final_state, signal = graph.propagate(ticker, trade_date)
    rating = signal if signal else parse_rating(final_state.get("final_trade_decision") or "")
    if not rating:
        rating = "REVIEW"
    zone = _HK if _is_hk(ticker) else _NY
    generated_at = datetime.now(zone).isoformat(timespec="seconds")
    document = result_document(final_state, rating, generated_at)
    document["ticker"] = ticker
    document["trade_date"] = trade_date
    return document
