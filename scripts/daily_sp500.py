"""Run the daily sessions and refresh the static page.

Local use writes JSON and HTML under ~/.tradingagents/sp500/.
Pass --publish to also upsert BigQuery and push the page to Cloudflare KV.
Those steps run only when their environment is present:

- GCP_PROJECT (BigQuery dataset sp500_daily, table decisions, location US)
- PAGE_PUBLISH_URL and PAGE_PUBLISH_TOKEN (the Worker bearer for PUT /publish)
- or CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_KV_NAMESPACE_ID
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from pathlib import Path

# The script lives outside the package. The repo root is the import path
# when Cloud Run starts it as `python scripts/daily_sp500.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tradingagents.daily.publish import (
    load_bigquery,
    load_local,
    put_cloudflare_page,
    save_local,
    upsert_bigquery,
    write_page,
)
from tradingagents.daily.sp500 import TICKERS, coming_session, run_session

# Five HKEX names, then five US names, one after another. Hong Kong names
# call Tencent, East Money, and HKEXnews. US names call Yahoo, Reddit, and
# SEC. The gap keeps a name that fails in a few seconds from starting the
# next burst immediately.
_GAP_SECONDS = 8


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily SPY session")
    parser.add_argument(
        "--date",
        help="Session date YYYY-MM-DD. Default: today's NYSE session, which is the day about to open.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also write BigQuery and Cloudflare when those environments are set.",
    )
    parser.add_argument(
        "--publish-only",
        action="store_true",
        help="Push the sessions already saved. Does not call the model.",
    )
    args = parser.parse_args()

    if args.publish_only:
        project = os.environ.get("GCP_PROJECT", "")
        if args.publish and project:
            days = load_bigquery(project)
            print(f"BigQuery rows {len(days)}", flush=True)
        else:
            days = load_local()
        if not days:
            print("No saved sessions to publish.", flush=True)
            return
        _write_published_page(days, args.publish)
        return

    if args.date:
        trade_date = args.date
    else:
        trade_date = coming_session()
        if trade_date is None:
            print("NYSE is closed today. Skipping.", flush=True)
            return
    failures = _run_universe(trade_date, args.publish)
    if failures:
        raise SystemExit(f"Failed: {', '.join(failures)}")


def _run_universe(trade_date: str, publish: bool) -> list[str]:
    """Run each missing ticker. Storage is read once; the page is updated from memory.

    Names stay in series. A parallel burst is what gets Yahoo and Reddit to
    answer 429, and the analysts already retry when that happens.
    """
    days = _stored_days(publish)
    failures = []
    published = False
    started = False
    for ticker in TICKERS:
        if any(row.get("trade_date") == trade_date and row.get("ticker") == ticker for row in days):
            print(f"Already saved {ticker} {trade_date}", flush=True)
            continue
        if started:
            _pace()
        started = True
        print(f"Starting {ticker} session for {trade_date}", flush=True)
        try:
            document = run_session(trade_date, ticker)
        except Exception:
            traceback.print_exc()
            failures.append(ticker)
            continue
        path = save_local(document)
        print(f"Saved {path}", flush=True)
        print(f"Rating {document['rating']} on {document['trade_date']} {ticker}", flush=True)
        days.append(document)
        project = os.environ.get("GCP_PROJECT", "")
        if publish and project:
            upsert_bigquery(document, project)
            print(f"BigQuery saved {ticker}", flush=True)
        _write_published_page(days, publish)
        published = True
    if not published:
        _write_published_page(days, publish)
    return failures


def _pace() -> None:
    time.sleep(_GAP_SECONDS)


def _stored_days(publish: bool) -> list:
    project = os.environ.get("GCP_PROJECT", "")
    if publish and project:
        return load_bigquery(project)
    return load_local()


def _write_published_page(days: list, publish: bool) -> None:
    page = write_page(days, tickers=TICKERS)
    print(f"Page {page}", flush=True)
    if not publish:
        return
    if os.environ.get("PAGE_PUBLISH_URL"):
        if not os.environ.get("PAGE_PUBLISH_TOKEN"):
            return
    elif not os.environ.get("CLOUDFLARE_API_TOKEN"):
        return
    put_cloudflare_page(page.read_text(encoding="utf-8"))
    print("Cloudflare page updated", flush=True)


if __name__ == "__main__":
    main()
