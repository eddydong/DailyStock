"""Hong Kong vendor parsing, without the network."""

import pandas as pd
import pytest

from tradingagents.agents.analysts import sentiment_analyst
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors import hk


@pytest.mark.unit
def test_a_us_ticker_is_not_queried_as_hong_kong():
    with pytest.raises(NoMarketDataError, match="not an HKEX"):
        hk.get_stock("NVDA", "2026-09-01", "2026-09-28")


@pytest.mark.unit
def test_tencent_daily_bars_keep_share_volume(monkeypatch):
    payload = {
        "data": {
            "hk00700": {
                "day": [["2026-09-29", "430", "432", "433", "429", "18015236"]],
            }
        }
    }
    monkeypatch.setattr(hk, "_get_json", lambda *args, **kwargs: payload)
    text = hk.get_stock("700.HK", "2026-09-01", "2026-09-29")
    assert "0700.HK" in text
    assert "HKD" in text
    assert "432" in text
    assert "18015236" in text


@pytest.mark.unit
def test_income_statement_labels_currency_and_period(monkeypatch):
    def fake_json(url, params=None, headers=None):
        report = (params or {}).get("reportName")
        if report == "RPT_CUSTOM_HKSK_APPFN_CASHFLOW_SUMMARY":
            return {
                "result": {
                    "data": [{
                        "REPORT_LIST": [{
                            "REPORT_DATE": "2026-03-31 00:00:00",
                            "DATE_TYPE_CODE": "003",
                            "REPORT_TYPE": "一季报",
                            "CURRENCY": "人民币",
                        }],
                    }]
                }
            }
        return {
            "result": {
                "data": [
                    {"STD_ITEM_NAME": "营业额", "AMOUNT": 194166000000},
                    {"STD_ITEM_NAME": "股东应占溢利", "AMOUNT": 58093000000},
                ]
            }
        }

    monkeypatch.setattr(hk, "_get_json", fake_json)
    text = hk.get_income_statement("0700.HK", "quarterly", "2026-09-29")
    assert "人民币" in text
    assert "2026-03-31" in text
    assert "194166000000" in text


@pytest.mark.unit
def test_announcements_keep_only_the_requested_window(monkeypatch):
    monkeypatch.setattr(hk, "_companies", lambda: {"00700": ("7609", "TENCENT")})
    monkeypatch.setattr(hk, "_get_json", lambda *args, **kwargs: {
        "result": (
            '[{"TITLE":"Share Buyback","DATE_TIME":"29/09/2026 17:31",'
            '"FILE_LINK":"/listedco/a.pdf"},'
            '{"TITLE":"Old notice","DATE_TIME":"01/01/2020 09:00","FILE_LINK":"/old.pdf"}]'
        )
    })
    text = hk.get_news("0700.HK", "2026-09-22", "2026-09-29")
    assert "Share Buyback" in text
    assert "Old notice" not in text
    assert "https://www1.hkexnews.hk/listedco/a.pdf" in text


@pytest.mark.unit
def test_hk_sentiment_does_not_call_us_social_feeds(monkeypatch):
    called = []
    monkeypatch.setattr(
        sentiment_analyst,
        "fetch_stocktwits_messages",
        lambda *args, **kwargs: called.append("stocktwits"),
    )
    monkeypatch.setattr(
        sentiment_analyst,
        "fetch_reddit_posts",
        lambda *args, **kwargs: called.append("reddit"),
    )
    stocktwits, reddit = sentiment_analyst._social_blocks("0700.HK", "2026-09-22", "2026-09-29")
    assert called == []
    assert "StockTwits" in stocktwits
    assert "subreddit" in reddit.lower() or "cashtag" in reddit.lower()


@pytest.mark.unit
def test_indicator_uses_the_hong_kong_bars(monkeypatch):
    dates = pd.bdate_range("2026-06-01", periods=40)
    frame = pd.DataFrame({
        "Date": dates,
        "Open": range(100, 140),
        "Close": range(101, 141),
        "High": range(102, 142),
        "Low": range(99, 139),
        "Volume": [1_000_000] * 40,
    })
    monkeypatch.setattr(hk, "_bars", lambda *args, **kwargs: frame)
    as_of = dates[-1].strftime("%Y-%m-%d")
    text = hk.get_indicator("0700.HK", "rsi", as_of, 3)
    assert "rsi values" in text
    assert f"{as_of}:" in text
    assert "N/A" not in text.split(f"{as_of}:", 1)[1].splitlines()[0]
