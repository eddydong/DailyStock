"""Hong Kong market data: Tencent quotes, East Money statements, HKEXnews filings.

US names stay on Yahoo, SEC EDGAR, StockTwits, and Reddit. An HKEX code
(``0700.HK``) is served from the sources that actually publish Hong Kong
prices, interim and quarterly statements, and exchange announcements.

Prices are the forward-adjusted daily bars from Tencent's quote service, in
HKD, with share volume. Statements come from East Money's HK filing tables,
in the currency that feed reports (CNY for the large China issuers). Company
news and director dealings are the English HKEXnews announcements, not a
Yahoo ticker search.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta

import pandas as pd
import requests
from stockstats import wrap

from tradingagents.dataflows.date_window import in_window
from tradingagents.dataflows.errors import NoMarketDataError, VendorRateLimitError
from tradingagents.dataflows.symbols import normalize_symbol

_KLINE = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
_EM = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
_STOCKS = "https://www1.hkexnews.hk/ncms/script/eds/activestock_sehk_e.json"
_SEARCH = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
_HKEX = "https://www1.hkexnews.hk"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

_STATEMENTS = {
    "income": "RPT_HKF10_FN_INCOME_PC",
    "balance": "RPT_HKF10_FN_BALANCE_PC",
    "cashflow": "RPT_HKF10_FN_CASHFLOW_PC",
}
_ANNUAL = "001"
_INSIDER_WORDS = ("disclosure of interest", "director", "substantial shareholder", "buyback")
_stock_ids: dict[str, tuple[str, str]] | None = None


def _code(symbol: str) -> tuple[str, str]:
    """``(00700, 0700.HK)`` or an error when the symbol is not an HKEX code."""
    canonical = normalize_symbol(symbol)
    if not isinstance(canonical, str) or not canonical.endswith(".HK"):
        raise NoMarketDataError(symbol, canonical, "not an HKEX code")
    digits = canonical[:-3]
    if not digits.isdigit():
        raise NoMarketDataError(symbol, canonical, "not an HKEX code")
    return f"{int(digits):05d}", canonical


def _get_json(url: str, params: dict | None = None, headers: dict | None = None) -> dict:
    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": _UA, **(headers or {})},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise VendorRateLimitError(f"HK data request failed: {exc}") from exc
    except ValueError as exc:
        raise VendorRateLimitError("HK data source returned an unreadable response") from exc


def _bars(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Forward-adjusted daily bars. Volume is shares, not board lots."""
    digits, canonical = _code(symbol)
    tencent = f"hk{digits}"
    payload = _get_json(_KLINE, {"param": f"{tencent},day,{start_date},{end_date},800,qfq"})
    item = (payload.get("data") or {}).get(tencent) or {}
    rows = item.get("qfqday") or item.get("day") or []
    parsed = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        parsed.append(
            {
                "Date": str(row[0]),
                "Open": float(row[1]),
                "Close": float(row[2]),
                "High": float(row[3]),
                "Low": float(row[4]),
                "Volume": float(row[5]),
            }
        )
    if not parsed:
        raise NoMarketDataError(symbol, canonical, f"no daily bars between {start_date} and {end_date}")
    frame = pd.DataFrame(parsed)
    frame["Date"] = pd.to_datetime(frame["Date"])
    frame = frame[(frame["Date"] >= start_date) & (frame["Date"] <= end_date)]
    frame = frame.sort_values("Date")
    if frame.empty:
        raise NoMarketDataError(symbol, canonical, f"no daily bars between {start_date} and {end_date}")
    return frame


def bars_for_snapshot(symbol: str, curr_date: str) -> pd.DataFrame:
    """OHLCV on or before ``curr_date``, in the shape the verification snapshot reads."""
    start = (pd.Timestamp(curr_date) - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
    frame = _bars(symbol, start, curr_date)
    frame = frame[frame["Date"] <= pd.Timestamp(curr_date)]
    if frame.empty:
        raise NoMarketDataError(symbol, normalize_symbol(symbol), f"no bars on or before {curr_date}")
    return frame


def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    """Daily OHLCV for an HKEX code, forward-adjusted, quoted in HKD."""
    _, canonical = _code(symbol)
    frame = _bars(symbol, start_date, end_date)
    latest = frame["Date"].max()
    if (pd.Timestamp(end_date) - latest).days > 10:
        raise NoMarketDataError(symbol, canonical, f"latest bar {latest.date()} is stale for {end_date}")
    shown = frame.copy()
    shown["Date"] = shown["Date"].dt.strftime("%Y-%m-%d")
    for column in ("Open", "High", "Low", "Close"):
        shown[column] = shown[column].round(3)
    header = (
        f"# Stock data for {canonical} from {start_date} to {end_date}\n"
        f"# Source: Tencent quote, forward-adjusted, HKD. Volume is shares.\n"
        f"# Total records: {len(shown)}\n\n"
    )
    return header + shown.to_csv(index=False)


def get_indicator(symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    """One stockstats indicator on the Hong Kong daily bars."""
    start = (pd.Timestamp(curr_date) - pd.Timedelta(days=max(look_back_days, 30) + 400)).strftime("%Y-%m-%d")
    frame = _bars(symbol, start, curr_date)
    wrapped = wrap(frame.copy())
    try:
        wrapped[indicator]
    except Exception as exc:
        raise NoMarketDataError(symbol, normalize_symbol(symbol), f"{indicator} unavailable: {exc}") from exc
    wrapped["Date"] = pd.to_datetime(wrapped["Date"]).dt.strftime("%Y-%m-%d")
    by_date = {
        row["Date"]: ("N/A" if pd.isna(row[indicator]) else str(row[indicator]))
        for _, row in wrapped.iterrows()
    }
    end = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end - timedelta(days=look_back_days)
    lines = []
    cursor = end
    while cursor >= start_dt:
        key = cursor.strftime("%Y-%m-%d")
        lines.append(f"{key}: {by_date.get(key, 'N/A: Not a trading day (weekend or holiday)')}")
        cursor -= timedelta(days=1)
    return (
        f"## {indicator} values from {start_dt.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(lines)
        + "\n\nComputed from Tencent forward-adjusted HKEX daily bars.\n"
    )


def _em_rows(report: str, code: str, report_date: str | None = None) -> list[dict]:
    filt = f'(SECUCODE="{code}.HK")'
    if report_date:
        filt += f"(REPORT_DATE='{report_date}')"
    # ``ALL`` is rejected on the summary report. Ask only for the columns each
    # report actually returns.
    if report_date:
        columns = "SECUCODE,REPORT_DATE,STD_ITEM_CODE,STD_ITEM_NAME,AMOUNT"
    else:
        columns = "SECUCODE,REPORT_DATE,DATE_TYPE_CODE,REPORT_TYPE,CURRENCY,FISCAL_YEAR"
    payload = _get_json(
        _EM,
        {
            "reportName": report,
            "columns": columns,
            "filter": filt,
            "pageNumber": 1,
            "pageSize": 200,
            "sortTypes": "-1",
            "sortColumns": "REPORT_DATE",
            "source": "F10",
            "client": "PC",
        },
        headers={"Referer": "https://emweb.securities.eastmoney.com/"},
    )
    result = payload.get("result") or {}
    data = result.get("data") or []
    return data if isinstance(data, list) else []


def _periods(code: str, curr_date: str | None, freq: str) -> list[dict]:
    rows = _em_rows("RPT_CUSTOM_HKSK_APPFN_CASHFLOW_SUMMARY", code)
    reports = (rows[0].get("REPORT_LIST") or []) if rows else []
    cutoff = curr_date or "9999-12-31"
    kept = []
    for row in reports:
        day = str(row.get("REPORT_DATE") or "")[:10]
        if not day or day > cutoff:
            continue
        if str(freq).lower() == "annual" and str(row.get("DATE_TYPE_CODE")) != _ANNUAL:
            continue
        kept.append(row)
    kept.sort(key=lambda row: str(row.get("REPORT_DATE")), reverse=True)
    return kept[:4]


def _statement(symbol: str, kind: str, freq: str, curr_date: str | None, title: str) -> str:
    code, canonical = _code(symbol)
    periods = _periods(code, curr_date, freq)
    if not periods:
        raise NoMarketDataError(symbol, canonical, f"no {freq} {title} on or before {curr_date}")
    columns: dict[str, dict[str, float]] = {}
    currency = None
    for period in periods:
        day = str(period.get("REPORT_DATE"))[:10]
        label = f"{day} {period.get('REPORT_TYPE') or ''}".strip()
        currency = currency or period.get("CURRENCY")
        lines = _em_rows(_STATEMENTS[kind], code, day)
        values = {}
        for line in lines:
            name = line.get("STD_ITEM_NAME") or line.get("ORIG_ITEM_NAME")
            amount = line.get("AMOUNT")
            if name and amount is not None:
                values[str(name)] = amount
        if values:
            columns[label] = values
    if not columns:
        raise NoMarketDataError(symbol, canonical, f"no {title} lines on or before {curr_date}")
    frame = pd.DataFrame(columns)
    header = (
        f"# {title} for {canonical} ({freq})\n"
        f"# Source: East Money HK filings. Currency: {currency or 'as reported'}.\n"
        "# A period is included only when the company published it. "
        "Hong Kong does not require a US-style quarterly report.\n\n"
    )
    return header + frame.to_csv()


def get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
    """Latest reported income lines for an HKEX code, with the filing currency."""
    code, canonical = _code(ticker)
    periods = _periods(code, curr_date, "quarterly")
    if not periods:
        raise NoMarketDataError(ticker, canonical, "no reported periods")
    latest = periods[0]
    day = str(latest.get("REPORT_DATE"))[:10]
    lines = _em_rows(_STATEMENTS["income"], code, day)
    wanted = ("营业额", "营运收入", "毛利", "经营溢利", "股东应占溢利", "每股摊薄盈利", "每股基本盈利")
    picked = []
    for line in lines:
        name = str(line.get("STD_ITEM_NAME") or "")
        if name in wanted and line.get("AMOUNT") is not None:
            picked.append(f"{name}: {line['AMOUNT']}")
    if not picked:
        raise NoMarketDataError(ticker, canonical, f"no income lines for {day}")
    name = _company_name(code) or canonical
    return (
        f"# Company fundamentals for {canonical}\n\n"
        f"Name: {name}\n"
        f"Report date: {day} ({latest.get('REPORT_TYPE') or 'reported'})\n"
        f"Currency: {latest.get('CURRENCY') or 'as reported'}\n"
        "Quote currency: HKD\n"
        + "\n".join(picked)
        + "\n"
    )


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    return _statement(ticker, "balance", freq, curr_date, "Balance sheet")


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    return _statement(ticker, "cashflow", freq, curr_date, "Cash flow")


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    return _statement(ticker, "income", freq, curr_date, "Income statement")


def _companies() -> dict[str, tuple[str, str]]:
    global _stock_ids
    if _stock_ids is None:
        payload = _get_json(_STOCKS)
        found: dict[str, tuple[str, str]] = {}
        stack = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                code = str(node.get("c") or "")
                stock_id = node.get("i")
                if code.isdigit() and stock_id is not None:
                    found[f"{int(code):05d}"] = (str(stock_id), str(node.get("n") or ""))
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        _stock_ids = found
    return _stock_ids


def _company_name(code: str) -> str:
    try:
        return _companies().get(code, ("", ""))[1]
    except VendorRateLimitError:
        return ""


def _announcements(symbol: str, start_date: str, end_date: str) -> list[dict]:
    code, canonical = _code(symbol)
    listing = _companies().get(code)
    if not listing:
        raise NoMarketDataError(symbol, canonical, "not in the HKEXnews active list")
    stock_id, _name = listing
    payload = _get_json(
        _SEARCH,
        {
            "sortDir": "0",
            "sortByOptions": "DateTime",
            "category": "0",
            "market": "SEHK",
            "stockId": stock_id,
            "documentType": "-1",
            "fromDate": start_date.replace("-", ""),
            "toDate": end_date.replace("-", ""),
            "title": "",
            "searchType": "0",
            "t1code": "-2",
            "t2Gcode": "-2",
            "t2code": "-2",
            "rowRange": "20",
            "lang": "E",
        },
        headers={"Referer": "https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en"},
    )
    raw = payload.get("result") or "[]"
    try:
        rows = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError as exc:
        raise VendorRateLimitError("HKEXnews returned an unreadable announcement list") from exc
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    kept = []
    for row in rows if isinstance(rows, list) else []:
        published = _published(row.get("DATE_TIME"))
        if published is None or not in_window(published, start_dt, end_dt):
            continue
        title = _clean(row.get("TITLE") or row.get("LONG_TEXT") or "")
        link = str(row.get("FILE_LINK") or "")
        if link.startswith("/"):
            link = _HKEX + link
        kept.append({"title": title, "published": published, "link": link})
    return kept


def _published(value) -> datetime | None:
    text = _clean(value or "")
    if not text:
        return None
    for pattern in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:16] if pattern.endswith("%M") else text[:10], pattern)
        except ValueError:
            continue
    return None


def _clean(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(str(value)))
    return " ".join(text.split())


def _format_announcements(symbol: str, start_date: str, end_date: str, rows: list[dict], heading: str) -> str:
    if not rows:
        return f"No {heading} for {normalize_symbol(symbol)} between {start_date} and {end_date}"
    body = ""
    for row in rows:
        stamp = row["published"].strftime("%Y-%m-%d %H:%M")
        body += f"### {row['title']} (source: HKEXnews, {stamp})\n"
        if row["link"]:
            body += f"Link: {row['link']}\n"
        body += "\n"
    return f"## {normalize_symbol(symbol)} {heading}, from {start_date} to {end_date}:\n\n{body}"


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """English HKEXnews announcements for one HKEX code inside the date window."""
    rows = _announcements(ticker, start_date, end_date)
    return _format_announcements(ticker, start_date, end_date, rows, "exchange announcements")


def get_insider_transactions(symbol: str, curr_date: str | None = None) -> str:
    """Director dealings and buybacks, taken from HKEXnews headlines in the last 90 days."""
    end = curr_date or datetime.now().strftime("%Y-%m-%d")
    start = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=90)).strftime("%Y-%m-%d")
    rows = [
        row for row in _announcements(symbol, start, end)
        if any(word in row["title"].lower() for word in _INSIDER_WORDS)
    ]
    if not rows:
        return f"No director-dealing or buyback filings for {normalize_symbol(symbol)} between {start} and {end}"
    return _format_announcements(symbol, start, end, rows, "director dealings and buybacks")


def get_global_news(curr_date: str, look_back_days: int | None = None, limit: int | None = None) -> str:
    """HKEXnews is company-specific. Market-wide macro stays on the shared news vendor.

    This exists so a run that pins every news tool to ``hk`` still gets a
    dated answer instead of a missing-method error.
    """
    window = look_back_days if look_back_days is not None else 7
    start = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=window)).strftime("%Y-%m-%d")
    return (
        f"## Hong Kong market news, from {start} to {curr_date}:\n\n"
        "Company filings are retrieved per ticker from HKEXnews. "
        "This feed does not replace a macro search.\n"
    )
