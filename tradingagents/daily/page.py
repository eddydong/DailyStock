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
  --ink: #121a16;
  --sheet: #f7f6f1;
  --rail: #1c2822;
  --text: #1a2420;
  --muted: #5d6b64;
  --line: #d9d4c8;
  --mark: #c4a15a;
}
* { box-sizing: border-box; }
html, body { background: var(--sheet); }
body {
  margin: 0;
  color: var(--text);
  font-family: "Figtree", "Source Sans 3", sans-serif;
  font-size: 1.125rem;
  line-height: 1.6;
}
.mast {
  position: sticky;
  top: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
  padding: 0.85rem 1.75rem;
  background: var(--ink);
  color: var(--sheet);
}
.ticker {
  font-family: "Syne", "Figtree", sans-serif;
  font-weight: 700;
  font-size: 1.85rem;
  letter-spacing: -0.03em;
  line-height: 1;
  margin: 0;
}
.kicker {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.78rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #b7c4bb;
  margin: 0.2rem 0 0;
}
.stamp {
  font-family: "Syne", "Figtree", sans-serif;
  font-weight: 700;
  font-size: 1.35rem;
  letter-spacing: 0.04em;
  line-height: 1;
  margin: 0;
  padding: 0.45rem 0.85rem;
  color: var(--ink);
}
.layout {
  display: grid;
  grid-template-columns: 15.5rem minmax(0, 1fr);
  align-items: start;
  min-height: calc(100vh - 4.2rem);
  background: var(--rail);
}
.toc {
  position: sticky;
  top: 4.4rem;
  align-self: start;
  padding: 1.4rem 1.1rem 2rem 1.5rem;
  color: var(--sheet);
}
.toc p {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.68rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #8ea096;
  margin: 0 0 0.7rem;
}
.toc ol { list-style: none; margin: 0; padding: 0; }
.toc li { margin: 0; }
.toc a {
  display: block;
  text-decoration: none;
  font-weight: 600;
  font-size: 1.02rem;
  margin: 0.12rem 0;
  padding: 0.38rem 0.65rem;
  border-radius: 6px;
  color: #d5ddd8;
}
.toc a:hover, .toc a:focus-visible { color: var(--sheet); }
.toc a.is-active {
  color: var(--sheet);
  background: rgba(196, 161, 90, 0.22);
}
.reading {
  min-width: 0;
  background: var(--sheet);
  padding: 1.6rem 2.4rem 4rem;
  min-height: calc(100vh - 4.4rem);
}
.summary { font-size: 1.28rem; line-height: 1.45; margin: 0 0 0.35rem; }
.meta {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.78rem;
  color: var(--muted);
}
section { scroll-margin-top: 4.6rem; }
section { margin-top: 2rem; }
h2 {
  font-family: "Syne", "Figtree", sans-serif;
  font-size: 1.7rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  margin: 0 0 0.7rem;
  padding-top: 0.2rem;
  border-top: 3px solid var(--mark);
  scroll-margin-top: 5rem;
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
code {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.92em;
  background: #ece8df;
  padding: 0.05rem 0.28rem;
  border-radius: 3px;
}
hr { border: 0; border-top: 1px solid var(--line); margin: 1.1rem 0; }
blockquote {
  margin: 0.6rem 0;
  padding-left: 0.9rem;
  border-left: 3px solid var(--mark);
  color: var(--muted);
}
a { color: inherit; }
@media (max-width: 52rem) {
  .layout { grid-template-columns: 1fr; }
  .toc {
    position: sticky;
    top: 4.2rem;
    max-height: none;
    padding: 0.6rem 1rem;
  }
  .toc ol { display: flex; gap: 1rem; overflow-x: auto; }
  .toc a { white-space: nowrap; }
  .reading { padding: 1.2rem 1rem 3rem; }
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
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;600&family=IBM+Plex+Mono:wght@400;600&family=Syne:wght@700&display=swap">
<style>{_CSS}</style>
</head>
<body>
{body}
<script>
(() => {{
  const links = [...document.querySelectorAll(".toc a[href^='#']")];
  const sections = links.map((a) => document.getElementById(a.getAttribute("href").slice(1))).filter(Boolean);
  if (!sections.length) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const mast = document.querySelector(".mast");
  let shown = "";
  let locked = null;
  let frame = 0;
  const mark = (id) => {{
    if (!id || id === shown) return;
    shown = id;
    for (const a of links) a.classList.toggle("is-active", a.getAttribute("href") === "#" + id);
  }};
  const currentId = () => {{
    const doc = document.documentElement;
    if (window.innerHeight + window.scrollY >= doc.scrollHeight - 2) return sections[sections.length - 1].id;
    const line = (mast ? mast.getBoundingClientRect().height : 0) + 48;
    let active = sections[0].id;
    for (const section of sections) {{
      if (section.getBoundingClientRect().top <= line) active = section.id;
    }}
    return active;
  }};
  const sync = () => mark(locked || currentId());
  window.addEventListener("scroll", () => {{
    if (frame) return;
    frame = requestAnimationFrame(() => {{
      frame = 0;
      sync();
    }});
  }}, {{ passive: true }});
  window.addEventListener("scrollend", () => {{
    locked = null;
    sync();
  }});
  window.addEventListener("wheel", () => {{ locked = null; }}, {{ passive: true }});
  window.addEventListener("touchstart", () => {{ locked = null; }}, {{ passive: true }});
  links.forEach((a) => a.addEventListener("click", (event) => {{
    event.preventDefault();
    const id = a.getAttribute("href").slice(1);
    const section = document.getElementById(id);
    if (!section) return;
    locked = id;
    mark(id);
    section.scrollIntoView({{ behavior: reduce ? "auto" : "smooth", block: "start" }});
  }}));
  mark(currentId());
}})();
</script>
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
  <div>
    <p class="ticker">{html.escape(day.get("ticker") or "")}</p>
    <p class="kicker">Session {html.escape(day.get("trade_date") or "")}</p>
  </div>
  <p class="stamp" style="background:{color}">{html.escape(rating)}</p>
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


_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_BULLET = re.compile(r"^[-*+]\s+(.*\S)\s*$")
_NUMBER = re.compile(r"^\d+[.)]\s+(.*\S)\s*$")
_RULE = re.compile(r"^([-*_])\1{2,}\s*$")


def _markdown(text: str, prefix: str, used: set[str]) -> tuple[str, list[tuple[str, str]]]:
    """Render the agents' Markdown. A line is classified on its own, so a
    heading does not have to sit in a paragraph by itself."""
    lines = text.replace("\r\n", "\n").split("\n")
    parts: list[str] = []
    subs: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue
        heading = _HEADING.match(stripped)
        if heading:
            marks = len(heading.group(1))
            level = min(max(marks + 1, 3), 4)
            plain = heading.group(2)
            hid = _unique(f"{prefix}-{_slug(plain)}", used)
            if level == 3:
                subs.append((hid, plain))
            parts.append(f'<h{level} id="{hid}">{_inline(plain)}</h{level}>')
            i += 1
            continue
        if _RULE.match(stripped):
            parts.append("<hr>")
            i += 1
            continue
        if stripped.startswith("|"):
            table: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table.append(lines[i])
                i += 1
            parts.append(_table(table))
            continue
        bullet = _BULLET.match(stripped)
        number = _NUMBER.match(stripped)
        if bullet or number:
            items: list[str] = []
            ordered = bool(number) and not bullet
            while i < len(lines):
                item = lines[i].strip()
                if not item:
                    i += 1
                    break
                matched = (_NUMBER if ordered else _BULLET).match(item)
                if not matched:
                    break
                items.append(f"<li>{_inline(matched.group(1))}</li>")
                i += 1
            tag = "ol" if ordered else "ul"
            parts.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue
        if stripped.startswith(">"):
            quotes: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quotes.append(lines[i].strip().lstrip(">").strip())
                i += 1
            parts.append("<blockquote><p>" + "<br>".join(_inline(q) for q in quotes) + "</p></blockquote>")
            continue
        para: list[str] = []
        while i < len(lines) and lines[i].strip() and not _starts_block(lines[i]):
            para.append(lines[i].strip())
            i += 1
        parts.append("<p>" + _inline("\n".join(para)).replace("\n", "<br>") + "</p>")
    return "\n".join(parts), subs


def _starts_block(line: str) -> bool:
    stripped = line.strip()
    return bool(
        _HEADING.match(stripped)
        or _RULE.match(stripped)
        or stripped.startswith("|")
        or _BULLET.match(stripped)
        or _NUMBER.match(stripped)
        or stripped.startswith(">")
    )


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
    """Bold, italics, and code spans. Code is set aside first so a bold
    phrase can wrap a code span, and marks inside code stay literal."""
    if not text:
        return ""
    codes: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        codes.append(match.group(1))
        return f"\x00{len(codes) - 1}\x00"

    protected = re.sub(r"`([^`]+)`", _stash, text)
    escaped = html.escape(protected)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped, flags=re.S)
    escaped = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", escaped)

    def _restore(match: re.Match[str]) -> str:
        return "<code>" + html.escape(codes[int(match.group(1))]) + "</code>"

    return re.sub(r"\x00(\d+)\x00", _restore, escaped)
