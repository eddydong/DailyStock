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
  font-size: 1.2rem;
  line-height: 1.55;
}
.mast {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 1.25rem;
  background: var(--ink);
  color: var(--card);
}
.kicker {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #b7c3cf;
  margin: 0;
}
.stamp {
  font-family: "Barlow Condensed", "Arial Narrow", sans-serif;
  font-weight: 700;
  font-size: 2.4rem;
  line-height: 1;
  letter-spacing: 0.02em;
  margin: 0;
}
.layout {
  display: grid;
  grid-template-columns: 13rem minmax(0, 1fr);
  gap: 2.5rem;
  align-items: start;
  padding: 1.75rem 2.5rem 4rem;
}
.toc {
  position: sticky;
  top: 4.2rem;
  align-self: start;
  max-height: calc(100vh - 5rem);
  overflow: auto;
  padding-right: 0.4rem;
}
.toc p {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 0.4rem;
}
.toc ol { list-style: none; margin: 0; padding: 0; }
.toc li { margin: 0.15rem 0; }
.toc a {
  display: block;
  text-decoration: none;
  padding: 0.15rem 0;
  border-bottom: 1px solid transparent;
}
.toc a:hover, .toc a:focus-visible { border-bottom-color: var(--rule); }
.toc .sub { padding-left: 0.75rem; }
.toc .sub a { font-size: 0.92rem; color: var(--muted); }
.reading { min-width: 0; }
.summary { font-size: 1.35rem; margin: 0 0 0.4rem; max-width: none; }
.meta {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.78rem;
  color: var(--muted);
}
section { scroll-margin-top: 4.6rem; }
section { margin-top: 2rem; }
h2 {
  font-family: "Barlow Condensed", "Arial Narrow", sans-serif;
  font-size: 1.6rem;
  font-weight: 600;
  margin: 0 0 0.6rem;
  border-bottom: 1px solid var(--line);
  scroll-margin-top: 4.6rem;
}
h3 { font-size: 1.2rem; margin: 1.1rem 0 0.3rem; scroll-margin-top: 4.6rem; }
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
@media (max-width: 52rem) {
  .layout { grid-template-columns: 1fr; padding-top: 0.75rem; }
  .toc {
    position: sticky;
    top: 3.6rem;
    max-height: none;
    background: var(--paper);
    padding: 0.4rem 0 0.6rem;
  }
  .toc ol { display: flex; gap: 0.8rem; overflow-x: auto; }
  .toc .sub { display: none; }
  .tape li { grid-template-columns: 1fr; gap: 0.1rem; }
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
# The header is dark, so the rating word uses a lighter ink than the body.
_RATING_ON_DARK = {
    "Buy": "#8fd6b0",
    "Overweight": "#9dceae",
    "Hold": "#e4c27a",
    "Underweight": "#e2b09a",
    "Sell": "#e7a3a3",
    "REVIEW": "#c5d0da",
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
        ticker = latest.get("ticker") or ""
        title = f"{ticker} · {latest.get('trade_date') or ''}"
        body = _layout(latest, prior)
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
{body}
</body>
</html>
"""


def _layout(day: dict, prior: list[dict]) -> str:
    rating = day.get("rating") or "REVIEW"
    color = _RATING_ON_DARK.get(rating, _RATING_ON_DARK["REVIEW"])
    blocks = []
    toc = []
    used = set()
    for label, key in _SECTIONS:
        text = day.get(key) or ""
        if not text.strip():
            continue
        sid = _unique(_slug(label), used)
        inner, _subs = _markdown(text, sid, used)
        blocks.append(f'<section id="{sid}"><h2>{html.escape(label)}</h2>{inner}</section>')
        toc.append((sid, label, []))
    prior_html = _prior(prior)
    if prior_html:
        sid = _unique("earlier", used)
        blocks.append(prior_html.replace("<section>", f'<section id="{sid}">', 1))
        toc.append((sid, "Earlier sessions", []))
    return f"""
<header class="mast">
  <p class="kicker">{html.escape(day.get("ticker") or "")} · session {html.escape(day.get("trade_date") or "")}</p>
  <p class="stamp" style="color:{color}">{html.escape(rating)}</p>
</header>
<div class="layout">
  <nav class="toc" aria-label="Contents">
    <p>Contents</p>
    {_toc(toc)}
  </nav>
  <main class="reading">
    <p class="summary">{_inline(day.get("summary") or "")}</p>
    <p class="meta">Written {html.escape(day.get("generated_at") or "")}</p>
    {"".join(blocks)}
    {_note()}
  </main>
</div>
"""


def _toc(items: list[tuple[str, str, list[tuple[str, str]]]]) -> str:
    rows = []
    for sid, label, subs in items:
        sub = ""
        if subs:
            links = "".join(
                f'<li><a href="#{html.escape(hid)}">{html.escape(text)}</a></li>'
                for hid, text in subs
            )
            sub = f'<ol class="sub">{links}</ol>'
        rows.append(f'<li><a href="#{html.escape(sid)}">{html.escape(label)}</a>{sub}</li>')
    return "<ol>" + "".join(rows) + "</ol>"


def _unique(base: str, used: set[str]) -> str:
    candidate = base or "section"
    n = 2
    while candidate in used:
        candidate = f"{base}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "section"


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


def _markdown(text: str, prefix: str, used: set[str]) -> tuple[str, list[tuple[str, str]]]:
    blocks = re.split(r"\n\s*\n", text.strip())
    parts = []
    subs: list[tuple[str, str]] = []
    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.lstrip().startswith("#") for line in lines):
            for line in lines:
                marks = len(line) - len(line.lstrip("#"))
                # Section titles are already h2. Report headings sit under them.
                level = min(max(marks + 1, 3), 4)
                plain = line.lstrip("#").strip()
                hid = _unique(f"{prefix}-{_slug(plain)}", used)
                if level == 3:
                    subs.append((hid, plain))
                parts.append(f'<h{level} id="{hid}">{_inline(plain)}</h{level}>')
            continue
        if all(line.strip()[:2] in ("- ", "* ") for line in lines):
            items = "".join(f"<li>{_inline(line.strip()[2:])}</li>" for line in lines)
            parts.append(f"<ul>{items}</ul>")
            continue
        if _is_table(lines):
            parts.append(_table(lines))
            continue
        parts.append("<p>" + _inline(block).replace("\n", "<br>") + "</p>")
    return "\n".join(parts), subs


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
