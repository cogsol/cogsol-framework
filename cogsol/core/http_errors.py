"""Helpers to render HTTP error bodies as terminal-friendly one-liners.

Remote services answer failures with whatever their stack produces: Cloudflare
HTML pages, Django debug pages (hundreds of KB), proxy notices.  Printing those
verbatim buries the actual error, so every error body goes through
``summarize_http_error`` before reaching the user.
"""

from __future__ import annotations

import html
import re

MAX_DETAIL_LENGTH = 240


def _clean_text(raw: str) -> str:
    """Unescape entities and collapse whitespace into a single line."""
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _truncate(text: str) -> str:
    if len(text) <= MAX_DETAIL_LENGTH:
        return text
    return f"{text[: MAX_DETAIL_LENGTH - 3]}..."


def _django_debug_summary(body: str) -> str | None:
    """Extract ``<exception type> at <path>: <message>`` from a Django debug page."""
    value_match = re.search(
        r'<pre class="exception_value">(.*?)</pre>', body, re.IGNORECASE | re.DOTALL
    )
    if not value_match:
        return None

    message = _clean_text(value_match.group(1))
    title_match = re.search(r"<title>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
    where = _clean_text(title_match.group(1)) if title_match else ""

    if where and message:
        return f"{where}: {message}"
    return message or where or None


def summarize_http_error(detail: str) -> str:
    """Return a concise, single-line description of an HTTP error body."""
    clean = (detail or "").strip()
    if not clean:
        return ""

    lowered = clean.lower()
    if "<html" in lowered or "<!doctype html" in lowered:
        django_summary = _django_debug_summary(clean)
        if django_summary:
            return _truncate(django_summary)

        title_match = re.search(r"<title>(.*?)</title>", clean, re.IGNORECASE | re.DOTALL)
        if title_match:
            return f"HTML error page returned ({_clean_text(title_match.group(1))})"
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", clean, re.IGNORECASE | re.DOTALL)
        if h1_match:
            return f"HTML error page returned ({_clean_text(h1_match.group(1))})"
        return "HTML error page returned by remote server"

    return _truncate(re.sub(r"\s+", " ", clean))
