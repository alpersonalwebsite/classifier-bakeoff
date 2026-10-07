"""Written conclusions for one run (spec 002).

Conclusions live in `reports/conclusions/<run_id>.md` and are shown only in that
run's report (B1). Every figure they quote must appear, exactly as printed, in the
run's public edition built without them (B3), and they render as escaped text with
paragraphs, lists and emphasis only (B4).
"""

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONCLUSIONS_DIR = ROOT / "reports" / "conclusions"


class ConclusionsError(ValueError):
    """Conclusions quote figures their run's public report does not support."""


def load(run_id: str, directory: Path | None = None) -> str | None:
    path = (directory or CONCLUSIONS_DIR) / f"{run_id}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


# A figure is a number the report prints with a unit or a sign (spec 002 Assumptions).
# Each pattern refuses to start inside a word or a longer number, so a date such as
# 2026-10-07 never yields "-10".
_FIGURE = re.compile(
    r"(?P<lb>(?:≥|at least)\s*)?"
    r"(?<![\w.$])(?P<fig>"
    r"\$\d[\d,]*(?:\.\d+)?"  # dollars
    r"|[+-]\d+\.\d+"  # signed point differences, as the report prints them
    r"|\d+(?:\.\d+)?%"  # percentages
    r"|\d+(?:\.\d+)? s\b"  # durations
    r")"
)


def figures(text: str) -> list[tuple[str, bool]]:
    """Every figure quoted in the text, and whether it carries a lower-bound marker."""
    return [(m.group("fig"), bool(m.group("lb"))) for m in _FIGURE.finditer(text)]


def page_text(page_html: str) -> str:
    """The visible text of a rendered report, whitespace collapsed."""
    text = re.sub(r"<style.*?</style>", " ", page_html, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text)


def check(conclusions: str, public_without_conclusions: str) -> list[str]:
    """Problems with the quoted figures; an empty list means every figure is supported.

    The report's figures are extracted with the same pattern and compared as whole
    tokens. A substring test let "4.0%" pass because the report prints "94.0%", and
    "$0.00006" pass inside "$0.000062" (review of PR #5)."""
    printed = figures(page_text(public_without_conclusions))
    plain = {fig for fig, marked in printed if not marked}
    bounded = {fig for fig, marked in printed if marked}
    problems = []
    for fig, marked in figures(conclusions):
        if fig not in plain and fig not in bounded:
            problems.append(f"{fig}: not printed in the public report")
        elif fig in bounded and fig not in plain and not marked:
            problems.append(f"{fig}: the report shows it only as a lower bound, so quote it as '≥ {fig}' or 'at least {fig}'")
    return sorted(set(problems))


def _inline(text: str) -> str:
    out = html.escape(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    return re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<em>\1</em>", out)


def to_html(text: str) -> str:
    """Paragraphs, `- ` and `1. ` lists, and **bold** / *italic* only; everything else is escaped text."""
    blocks = [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    out = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        if all(line.lstrip().startswith("- ") for line in lines):
            items = "".join(f"<li>{_inline(line.lstrip()[2:])}</li>" for line in lines)
            out.append(f"<ul>{items}</ul>")
        elif all(re.match(r"\s*\d+\. ", line) for line in lines):
            items = "".join(f"<li>{_inline(re.sub(r'^\s*\d+\. ', '', line))}</li>" for line in lines)
            out.append(f"<ol>{items}</ol>")
        else:
            out.append(f"<p>{_inline(' '.join(line.strip() for line in lines))}</p>")
    return "".join(out)
