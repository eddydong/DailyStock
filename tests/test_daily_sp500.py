"""The daily SPY record and the static page, without calling a model."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from tradingagents.daily.nyse import is_nyse_session
from tradingagents.daily.page import render_page
from tradingagents.daily.publish import load_local, put_cloudflare_page, save_local, write_page
from tradingagents.daily.sp500 import choose_session, coming_session, executive_summary, result_document

_NY = ZoneInfo("America/New_York")


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
    }
    html = render_page([older, newer])
    assert "NEWER MARKET REPORT" in html
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
