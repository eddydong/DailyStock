"""Static page: the latest SPY session in full, older sessions as one line each.

The HTML is self-contained so Cloudflare can store and serve a single document.
No script fetches data. A later brevity change belongs in the agent prompts,
not in this layout.
"""

from __future__ import annotations

import html
import re

# Cool exchange-floor paper, not cream. The stamp is condensed board type.
# Rating colors are the only signal color; everything else stays quiet.
_CSS = """
:root {
  --paper: #dfe7ee;
  --card: #f6f8fa;
  --ink: #142033;
  --muted: #5c6b7c;
  --rule: #8a6a2f;
  --line: #c5d0da;
}
* { box-sizing: border-box; }
html { background: var(--paper); }
body {
  margin: 0;
  color: var(--ink);
  font-family: "Source Sans 3", "Source Sans Pro", sans-serif;
  font-size: 1.05rem;
  line-height: 1.5;
}
.wrap { max-width: 46rem; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
.ticket {
  background: var(--card);
  border: 1px solid var(--line);
  border-left: 0.55rem solid var(--rule);
  padding: 1.5rem 1.4rem 1.6rem 1.5rem;
  position: relative;
}
.ticket::before {
  content: "";
  position: absolute;
  left: 0.35rem;
  top: 0.8rem;
  bottom: 0.8rem;
  width: 0.45rem;
  background: radial-gradient(circle, var(--paper) 0.11rem, transparent 0.13rem);
  background-size: 0.45rem 0.7rem;
  background-repeat: repeat-y;
}
.kicker {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0;
}
h1 {
  font-family: "Barlow Condensed", "Arial Narrow", sans-serif;
  font-weight: 600;
  font-size: 2.4rem;
  letter-spacing: 0.01em;
  margin: 0.2rem 0 0.6rem;
}
.stamp {
  font-family: "Barlow Condensed", "Arial Narrow", sans-serif;
  font-weight: 700;
  font-size: 4.2rem;
  line-height: 0.9;
  letter-spacing: 0.02em;
  margin: 0.4rem 0 0.8rem;
}
.summary { font-size: 1.15rem; margin: 0 0 0.4rem; }
.meta {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.78rem;
  color: var(--muted);
}
section { margin-top: 2rem; }
h2 {
  font-family: "Barlow Condensed", "Arial Narrow", sans-serif;
  font-size: 1.6rem;
  font-weight: 600;
  margin: 0 0 0.6rem;
  border-bottom: 1px solid var(--line);
}
h3 { font-size: 1.05rem; margin: 1.1rem 0 0.3rem; }
p { margin: 0.4rem 0; }
ul { margin: 0.4rem 0; padding-left: 1.2rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.92rem; margin: 0.6rem 0 1rem; }
th, td { text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 0.78rem; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); font-weight: 600; }
.tape { list-style: none; margin: 0; padding: 0; }
.tape li {
  display: grid;
  grid-template-columns: 7.2rem 7.5rem 1fr;
  gap: 0.6rem;
  padding: 0.55rem 0;
  border-bottom: 1px solid var(--line);
  align-items: baseline;
}
.tape time, .tape .rate {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.82rem;
}
.tape .rate { font-weight: 700; }
.note {
  margin-top: 2.5rem;
  color: var(--muted);
  font-size: 0.85rem;
}
a { color: inherit; }
@media (max-width: 40rem) {
  .tape li { grid-template-columns: 1fr; gap: 0.1rem; }
  .stamp { font-size: 3.2rem; }
}
"""

_RATING_COLOR = {
    "Buy": "#1C6B45",
    "Overweight": "#2E7D4F",
    "Hold": "#8A5A12",
    "Underweight": "#8E4B2A",
    "Sell": "#8E2E2E",
    "REVIEW": "#5C6B7A",
}

_SECTIONS = (
    ("Decision", "final_decision"),
    ("Market", "market_report"),
    ("Sentiment", "sentiment_report"),
    ("News", "news_report"),
    ("Fundamentals", "fundamentals_report"),
    ("Research manager", "research_manager"),
    ("Bull case", "bull"),
    ("Bear case", "bear"),
    ("Trader", "trader_plan"),
    ("Risk", "risk_decision"),
)


def render_page(days: list[dict]) -> str:
    """Latest session in full. Each earlier session is one tape line."""
    ordered = sorted(days, key=lambda row: row.get("trade_date") or "")
    if not ordered:
        body = "<p>No session has been recorded.</p>"
        title = "Daily session"
    else:
        latest = ordered[-1]
        prior = list(reversed(ordered[:-1]))
        title = f"S&P 500 · {latest.get('trade_date') or ''}"
        body = _ticket(latest) + _prior(prior) + _note()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=IBM+Plex+Mono:wght@400;700&family=Source+Sans+3:wght@400;600&display=swap">
<style>{_CSS}</style>
</head>
<body>
<main class="wrap">
{body}
</main>
</body>
</html>
"""


def _ticket(day: dict) -> str:
    rating = day.get("rating") or "REVIEW"
    color = _RATING_COLOR.get(rating, _RATING_COLOR["REVIEW"])
    sections = []
    for label, key in _SECTIONS:
        text = day.get(key) or ""
        if not text.strip():
            continue
        sections.append(f"<section><h2>{html.escape(label)}</h2>{_markdown(text)}</section>")
    return f"""
<article class="ticket">
<p class="kicker">{html.escape(day.get("ticker") or "")} · session {html.escape(day.get("trade_date") or "")}</p>
<h1>Session ticket</h1>
<p class="stamp" style="color:{color}">{html.escape(rating)}</p>
<p class="summary">{_inline(day.get("summary") or "")}</p>
<p class="meta">Written {html.escape(day.get("generated_at") or "")}</p>
</article>
{"".join(sections)}
"""


def _prior(days: list[dict]) -> str:
    if not days:
        return "<section><h2>Earlier sessions</h2><p>They will line up here after the next run.</p></section>"
    items = []
    for day in days:
        rating = day.get("rating") or "REVIEW"
        color = _RATING_COLOR.get(rating, _RATING_COLOR["REVIEW"])
        items.append(
            "<li>"
            f"<time>{html.escape(day.get('trade_date') or '')}</time>"
            f"<span class=\"rate\" style=\"color:{color}\">{html.escape(rating)}</span>"
            f"<span>{_inline(day.get('summary') or '')}</span>"
            "</li>"
        )
    return "<section><h2>Earlier sessions</h2><ul class=\"tape\">" + "".join(items) + "</ul></section>"


def _note() -> str:
    return (
        "<p class=\"note\">Research record of one multi-agent reading. "
        "It is not a recommendation to buy or sell.</p>"
    )


def _markdown(text: str) -> str:
    blocks = re.split(r"\n\s*\n", text.strip())
    parts = []
    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.lstrip().startswith("#") for line in lines):
            for line in lines:
                marks = len(line) - len(line.lstrip("#"))
                # Section titles are already h2. Report headings sit under them.
                level = min(max(marks + 1, 3), 4)
                parts.append(f"<h{level}>{_inline(line.lstrip('#').strip())}</h{level}>")
            continue
        if all(line.strip()[:2] in ("- ", "* ") for line in lines):
            items = "".join(f"<li>{_inline(line.strip()[2:])}</li>" for line in lines)
            parts.append(f"<ul>{items}</ul>")
            continue
        if _is_table(lines):
            parts.append(_table(lines))
            continue
        parts.append("<p>" + _inline(block).replace("\n", "<br>") + "</p>")
    return "\n".join(parts)


def _is_table(lines: list[str]) -> bool:
    return len(lines) >= 2 and all(line.strip().startswith("|") for line in lines)


def _table(lines: list[str]) -> str:
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and all(set(cell) <= set("-: ") for cell in cells):
            continue
        rows.append(cells)
    if not rows:
        return ""
    head = "".join(f"<th>{_inline(cell)}</th>" for cell in rows[0])
    body = ""
    for row in rows[1:]:
        body += "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _inline(text: str) -> str:
    escaped = html.escape(text or "")
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
