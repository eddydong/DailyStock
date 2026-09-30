"""The daily SPY record and the static page, without calling a model."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from tradingagents.daily.hkex import is_hkex_session
from tradingagents.daily.nyse import is_nyse_session
from tradingagents.daily.page import render_page
from tradingagents.daily.publish import load_local, put_cloudflare_page, save_local, write_page
from tradingagents.daily.sp500 import (
    TICKERS,
    US_TICKERS,
    choose_session,
    coming_hk_session,
    coming_session,
    executive_summary,
    result_document,
)

_NY = ZoneInfo("America/New_York")
_HK = ZoneInfo("Asia/Hong_Kong")


def test_session_before_the_close_uses_the_previous_day():
    sessions = [date(2026, 9, 24), date(2026, 9, 25)]
    morning = datetime(2026, 9, 25, 10, 0, tzinfo=_NY)
    assert choose_session(sessions, morning) == "2026-09-24"


def test_session_after_the_close_uses_that_day():
    sessions = [date(2026, 9, 24), date(2026, 9, 25)]
    evening = datetime(2026, 9, 25, 16, 10, tzinfo=_NY)
    assert choose_session(sessions, evening) == "2026-09-25"


def test_weekend_morning_keeps_friday():
    sessions = [date(2026, 9, 25)]
    saturday = datetime(2026, 9, 26, 9, 30, tzinfo=_NY)
    assert choose_session(sessions, saturday) == "2026-09-25"


def test_preopen_uses_the_session_about_to_open():
    morning = datetime(2026, 9, 25, 9, 0, tzinfo=_NY)
    assert coming_session(morning) == "2026-09-25"


def test_saturday_is_not_a_session():
    saturday = datetime(2026, 9, 26, 9, 0, tzinfo=_NY)
    assert coming_session(saturday) is None


def test_hk_preopen_uses_the_session_about_to_open():
    morning = datetime(2026, 9, 29, 9, 0, tzinfo=_HK)
    assert coming_hk_session(morning) == "2026-09-29"


def test_hk_holiday_and_weekend_are_not_sessions():
    lunar_new_year = datetime(2026, 2, 17, 9, 0, tzinfo=_HK)
    assert coming_hk_session(lunar_new_year) is None
    assert is_hkex_session(date(2026, 2, 16)) is True  # half day, still opens
    assert is_hkex_session(date(2026, 7, 1)) is False
    saturday = datetime(2026, 9, 26, 9, 0, tzinfo=_HK)
    assert coming_hk_session(saturday) is None


def test_known_2026_holidays_are_closed_and_a_normal_friday_is_open():
    assert is_nyse_session(date(2026, 9, 25)) is True
    for closed in (
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),
        date(2026, 9, 7),
        date(2026, 11, 26),
        date(2026, 12, 25),
    ):
        assert is_nyse_session(closed) is False


def test_summary_is_the_executive_paragraph_only():
    decision = (
        "**Rating**: Hold\n\n"
        "**Executive Summary**: Wait for a close back above the week high.\n\n"
        "**Investment Thesis**: The debate was split.\n"
    )
    assert executive_summary(decision) == "Wait for a close back above the week high."


def test_result_document_keeps_every_report():
    state = {
        "company_of_interest": "SPY",
        "trade_date": "2026-09-25",
        "final_trade_decision": "**Rating**: Hold\n\n**Executive Summary**: Sit tight.\n\n",
        "market_report": "prices",
        "sentiment_report": "mood",
        "news_report": "headlines",
        "fundamentals_report": "filings",
        "investment_plan": "plan",
        "trader_investment_plan": "trade",
        "investment_debate_state": {"bull_history": "up", "bear_history": "down", "judge_decision": "mixed"},
        "risk_debate_state": {
            "aggressive_history": "a",
            "conservative_history": "c",
            "neutral_history": "n",
            "judge_decision": "risk",
        },
    }
    doc = result_document(state, "Hold", "2026-09-26T09:00:00-04:00")
    assert doc["market_report"] == "prices"
    assert doc["bull"] == "up"
    assert doc["summary"] == "Sit tight."
    assert doc["rating"] == "Hold"


def test_page_shows_the_latest_report_and_only_a_line_for_earlier_days():
    older = {
        "trade_date": "2026-09-24",
        "rating": "Sell",
        "summary": "Take the position down.",
        "final_decision": "full older decision",
        "market_report": "OLDER MARKET REPORT",
    }
    newer = {
        "trade_date": "2026-09-25",
        "rating": "Hold",
        "summary": "Sit tight.",
        "final_decision": "full newer decision",
        "market_report": "NEWER MARKET REPORT",
        "generated_at": "2026-09-26T09:00:00-04:00",
        "run_settings": {
            "version": "0.5.1",
            "llm_provider": "deepseek",
            "deep_think_llm": "deepseek-flash",
            "quick_think_llm": "deepseek-flash",
            "analysts": ["market", "news"],
            "data_vendors": {"core_stock_apis": "yfinance"},
            "tool_vendors": {},
        },
    }
    html = render_page([older, newer])
    assert "NEWER MARKET REPORT" in html
    assert "TradingAgents 0.5.1" in html
    assert "deepseek-flash" in html
    assert "OLDER MARKET REPORT" not in html
    assert "full older decision" not in html
    assert "Take the position down." in html
    assert ">Hold<" in html
    assert 'href="#market"' in html
    assert 'id="market"' in html
    assert "is-active" in html
    assert 'addEventListener("scroll"' in html
    assert "getBoundingClientRect" in html
    assert 'behavior: reduce ? "auto" : "smooth"' in html


def test_archive_round_trip(tmp_path):
    doc = {"trade_date": "2026-09-25", "ticker": "SPY", "rating": "Hold", "summary": "Sit tight."}
    save_local(doc, tmp_path)
    assert load_local(tmp_path) == [doc]
    page = write_page(load_local(tmp_path), tmp_path)
    assert "Sit tight." in page.read_text(encoding="utf-8")


def test_markdown_marks_are_not_left_as_text():
    page = render_page([{
        "trade_date": "2026-09-25",
        "rating": "Hold",
        "summary": "Sit tight.",
        "market_report": "# Title\n**Date:** today\n\n`close`\n\n- one\n- two",
    }])
    assert "# Title" not in page
    assert "**Date:**" not in page
    assert "<code>close</code>" in page
    wrapped = render_page([{
        "trade_date": "2026-09-25",
        "rating": "Hold",
        "summary": "Sit tight.",
        "market_report": "See **the `close` price** today.",
    }])
    assert "<strong>the <code>close</code> price</strong>" in wrapped
    assert "<li>one</li>" in page


def test_markdown_table_is_a_table():
    html = render_page([{
        "trade_date": "2026-09-25",
        "rating": "Hold",
        "summary": "Sit tight.",
        "market_report": "| Metric | Value |\n| --- | --- |\n| Close | 771.35 |",
    }])
    assert "<table>" in html and "<td>771.35</td>" in html


def test_empty_archive_page_says_nothing_is_recorded():
    assert "No session has been recorded." in render_page([])


def test_universe_stays_the_frozen_ten():
    """These ten names stay until the user asks for a different list."""
    from tradingagents.daily.sp500 import HK_TICKERS, US_TICKERS, job_config

    assert TICKERS == HK_TICKERS + US_TICKERS
    assert HK_TICKERS == ("0700.HK", "9988.HK", "6869.HK", "1810.HK", "9926.HK")
    assert US_TICKERS == ("NVDA", "MU", "META", "TSLA", "AMD")
    hk = job_config("0700.HK")
    us = job_config("NVDA")
    assert hk["data_vendors"]["fundamental_data"] == "hk"
    assert hk["tool_vendors"]["get_news"] == "hk"
    assert us["data_vendors"]["fundamental_data"] == "yfinance"
    assert "get_news" not in us["tool_vendors"]
    assert hk["analyst_concurrency"] == us["analyst_concurrency"] == 2


def test_same_day_tickers_keep_separate_files(tmp_path):
    save_local({"trade_date": "2026-09-28", "ticker": "AAPL", "rating": "Hold", "summary": "Apple."}, tmp_path)
    save_local({"trade_date": "2026-09-28", "ticker": "NVDA", "rating": "Buy", "summary": "Nvidia."}, tmp_path)
    loaded = {(row["ticker"], row["summary"]) for row in load_local(tmp_path)}
    assert loaded == {("AAPL", "Apple."), ("NVDA", "Nvidia.")}


def test_board_lists_every_name_and_keeps_each_report():
    html = render_page([
        {
            "trade_date": "2026-09-25",
            "ticker": "AAPL",
            "rating": "Sell",
            "summary": "Old apple.",
            "market_report": "OLD AAPL MARKET",
        },
        {
            "trade_date": "2026-09-28",
            "ticker": "AAPL",
            "rating": "Hold",
            "summary": "Apple now.",
            "market_report": "AAPL MARKET",
        },
        {
            "trade_date": "2026-09-28",
            "ticker": "NVDA",
            "rating": "Buy",
            "summary": "Nvidia now.",
            "market_report": "NVDA MARKET",
        },
    ], tickers=("NVDA", "AAPL", "MU"))
    assert "AAPL MARKET" in html
    assert "NVDA MARKET" in html
    assert "OLD AAPL MARKET" not in html
    assert "Old apple." in html
    assert "No session has been recorded for MU." in html
    assert 'data-ticker="AAPL" hidden' in html
    assert '<span class="rank">01</span><span class="sym">NVDA</span>' in html
    assert '<span class="rank">02</span><span class="sym">AAPL</span>' in html
    assert 'aria-pressed="true"' in html
    assert 'id="aapl-market"' in html
    assert 'id="nvda-market"' in html


def test_board_groups_markets_and_uses_hong_kong_names():
    html = render_page([
        {
            "trade_date": "2026-09-30",
            "ticker": "0700.HK",
            "rating": "Underweight",
            "summary": "Tencent note.",
            "market_report": "TENCENT MARKET",
        },
        {
            "trade_date": "2026-09-29",
            "ticker": "NVDA",
            "rating": "Hold",
            "summary": "Nvidia note.",
            "market_report": "NVDA MARKET",
        },
    ], tickers=("0700.HK", "9988.HK", "NVDA"))
    assert '<span class="mkt">HK</span>' in html
    assert '<span class="mkt">US</span>' in html
    assert html.index("HK") < html.index(">Tencent<") < html.index(">US<") < html.index(">NVDA<")
    assert '<span class="sym">Tencent</span>' in html
    assert '<span class="sym">Alibaba</span>' in html
    assert "Tencent Holdings Limited (0700.HK)" in html
    assert "Alibaba Group Holding Limited (9988.HK)" in html
    assert "TENCENT MARKET" in html


def test_publish_url_puts_the_page_with_its_bearer(monkeypatch):
    captured = {}

    class Response:
        text = "ok"

        def raise_for_status(self):
            return None

    def fake_put(url, data, headers, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("PAGE_PUBLISH_URL", "https://stock.example/publish")
    monkeypatch.setenv("PAGE_PUBLISH_TOKEN", "secret-token")
    monkeypatch.setattr("tradingagents.daily.publish.requests.put", fake_put)

    assert put_cloudflare_page("<!DOCTYPE html><html></html>") == "https://stock.example/publish"
    assert captured["url"] == "https://stock.example/publish"
    assert captured["data"] == b"<!DOCTYPE html><html></html>"
    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert captured["timeout"] == 60


def test_batch_reads_storage_once_and_spaces_the_names(monkeypatch):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "daily_sp500.py"
    spec = importlib.util.spec_from_file_location("daily_sp500_script", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    stored = [{"trade_date": "2026-09-29", "ticker": "MU", "rating": "Hold", "summary": "done"}]
    reads = {"n": 0}
    gaps = []
    published = []

    def stored_days(_publish):
        reads["n"] += 1
        return list(stored)

    def run(_date, ticker):
        if ticker == "NVDA":
            raise RuntimeError("vendor down")
        return {"trade_date": "2026-09-29", "ticker": ticker, "rating": "Hold", "summary": ticker}

    def save(document):
        stored.append(document)
        return Path("saved")

    def write(days, _publish):
        published.append([row["ticker"] for row in days])

    monkeypatch.setattr(script, "_stored_days", stored_days)
    monkeypatch.setattr(script, "run_session", run)
    monkeypatch.setattr(script, "save_local", save)
    monkeypatch.setattr(script, "_write_published_page", write)
    monkeypatch.setattr(script.time, "sleep", lambda seconds: gaps.append(seconds))

    failures = script._run_universe("2026-09-29", False, US_TICKERS)

    finished = [row["ticker"] for row in stored]
    assert failures == ["NVDA"]
    assert reads["n"] == 1
    assert finished == ["MU", *[name for name in US_TICKERS if name not in ("MU", "NVDA")]]
    assert gaps == [script._GAP_SECONDS] * (len(US_TICKERS) - 2)
    assert published[-1] == finished
