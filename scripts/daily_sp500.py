"""Run the daily SPY session and refresh the static page.

Local use writes JSON and HTML under ~/.tradingagents/sp500/.
Pass --publish to also upsert BigQuery and push the page to Cloudflare KV.
Those steps run only when their environment is present:

- GCP_PROJECT (BigQuery dataset sp500_daily, table decisions, location US)
- CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_KV_NAMESPACE_ID
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# The script lives outside the package. The repo root is the import path
# when Cloud Run starts it as `python scripts/daily_sp500.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tradingagents.daily.page import render_page
from tradingagents.daily.publish import (
    load_bigquery,
    load_local,
    put_cloudflare_page,
    save_local,
    upsert_bigquery,
    write_page,
)
from tradingagents.daily.sp500 import TICKER, coming_session, run_session


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
    args = parser.parse_args()

    if args.date:
        trade_date = args.date
    else:
        trade_date = coming_session()
        if trade_date is None:
            print("NYSE is closed today. Skipping.", flush=True)
            return
    print(f"Starting {TICKER} session for {trade_date}", flush=True)
    document = run_session(trade_date)
    path = save_local(document)
    print(f"Saved {path}", flush=True)
    print(f"Rating {document['rating']} on {document['trade_date']}", flush=True)

    project = os.environ.get("GCP_PROJECT", "")
    if args.publish and project:
        upsert_bigquery(document, project)
        days = load_bigquery(project)
        print(f"BigQuery rows {len(days)}", flush=True)
    else:
        days = load_local()

    page = write_page(days)
    print(f"Page {page}", flush=True)

    if args.publish and os.environ.get("CLOUDFLARE_API_TOKEN"):
        put_cloudflare_page(render_page(days))
        print("Cloudflare page updated", flush=True)


if __name__ == "__main__":
    main()
