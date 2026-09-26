"""Write one session JSON locally, and optionally to BigQuery and Cloudflare.

Local files are the record a laptop run can open. BigQuery holds the same
JSON, one row per session, so a Cloud Run task with an empty disk can still
rebuild the page. Cloudflare stores the rendered HTML and serves it. Both
remote writes stay off unless their environment is set, so a local proof
does not touch either account.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from tradingagents.daily.page import render_page

# Under the same home directory the framework already uses for logs.
ARCHIVE = Path.home() / ".tradingagents" / "sp500"


def save_local(document: dict, archive: Path = ARCHIVE) -> Path:
    """Replace that session's JSON file. Returns the path."""
    archive.mkdir(parents=True, exist_ok=True)
    path = archive / f"{document['trade_date']}.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_local(archive: Path = ARCHIVE) -> list[dict]:
    """Every saved session JSON, oldest first."""
    if not archive.is_dir():
        return []
    days = []
    for path in sorted(archive.glob("*.json")):
        days.append(json.loads(path.read_text(encoding="utf-8")))
    return days


def write_page(days: list[dict], archive: Path = ARCHIVE) -> Path:
    """Render the static page beside the JSON archive."""
    archive.mkdir(parents=True, exist_ok=True)
    path = archive / "index.html"
    path.write_text(render_page(days), encoding="utf-8")
    return path


def upsert_bigquery(document: dict, project: str, dataset: str = "sp500_daily", table: str = "decisions") -> None:
    """Insert or replace this session's single JSON row.

    Uses a query job, which draws on BigQuery's free query allowance.
    Streaming inserts are a separate charge, so this path does not use them.
    The dataset must live in the US multi-region, which is where the free
    storage tier applies.
    """
    _query(
        project,
        f"CREATE SCHEMA IF NOT EXISTS `{project}.{dataset}` OPTIONS(location='US')",
    )
    _query(
        project,
        f"""
        CREATE TABLE IF NOT EXISTS `{project}.{dataset}.{table}` (
          trade_date DATE NOT NULL,
          ticker STRING NOT NULL,
          payload JSON NOT NULL
        )
        """,
    )
    _query(
        project,
        f"""
        MERGE `{project}.{dataset}.{table}` T
        USING (
          SELECT @trade_date AS trade_date, @ticker AS ticker, @payload AS payload
        ) S
        ON T.trade_date = S.trade_date AND T.ticker = S.ticker
        WHEN MATCHED THEN UPDATE SET payload = S.payload
        WHEN NOT MATCHED THEN
          INSERT (trade_date, ticker, payload)
          VALUES (S.trade_date, S.ticker, S.payload)
        """,
        parameters=[
            _param("trade_date", "DATE", document["trade_date"]),
            _param("ticker", "STRING", document["ticker"]),
            _param("payload", "JSON", json.dumps(document, ensure_ascii=False)),
        ],
    )


def load_bigquery(project: str, dataset: str = "sp500_daily", table: str = "decisions") -> list[dict]:
    """Every stored session, oldest first."""
    rows = _query(
        project,
        f"""
        SELECT payload
        FROM `{project}.{dataset}.{table}`
        WHERE ticker = 'SPY'
        ORDER BY trade_date
        """,
    )
    days = []
    for row in rows:
        raw = row["f"][0]["v"]
        days.append(json.loads(raw) if isinstance(raw, str) else raw)
    return days


def put_cloudflare_page(html: str) -> str:
    """Store the page in Cloudflare KV. The Worker serves that one key.

    Requires ``CLOUDFLARE_API_TOKEN``, ``CLOUDFLARE_ACCOUNT_ID``, and
    ``CLOUDFLARE_KV_NAMESPACE_ID``. The token needs Workers KV Storage write
    on this account and nothing else.
    """
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    namespace = os.environ["CLOUDFLARE_KV_NAMESPACE_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{account}/storage/kv/namespaces/{namespace}/values/index.html"
    )
    response = requests.put(
        url,
        data=html.encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "text/html; charset=utf-8",
        },
        timeout=60,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("success") is not True:
        raise RuntimeError(f"Cloudflare KV write failed: {body.get('errors')}")
    return url


def _param(name: str, kind: str, value: str) -> dict:
    return {
        "name": name,
        "parameterType": {"type": kind},
        "parameterValue": {"value": value},
    }


def _query(project: str, sql: str, parameters: list | None = None) -> list:
    import google.auth
    from google.auth.transport.requests import Request as GoogleAuthRequest

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/bigquery"])
    credentials.refresh(GoogleAuthRequest())
    payload: dict = {"query": sql, "useLegacySql": False, "timeoutMs": 60000}
    if parameters:
        payload["parameterMode"] = "NAMED"
        payload["queryParameters"] = parameters
    response = requests.post(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}/queries",
        headers={"Authorization": f"Bearer {credentials.token}"},
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("jobComplete") is False:
        raise RuntimeError("BigQuery job did not finish within the request")
    if "error" in body.get("status", {}):
        raise RuntimeError(body["status"]["error"])
    return (body.get("rows") or [])
