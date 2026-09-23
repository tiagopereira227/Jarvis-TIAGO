# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""News headlines from an RSS/Atom feed.

Cross-platform: this is pure HTTP + XML parsing, so it behaves identically on
macOS, Windows, and Linux.

Security note: the feed is untrusted remote XML. Per OWASP XXE guidance we never
parse it with default settings — we reject any document containing a DOCTYPE
declaration (which legitimate RSS/Atom feeds never need). That closes external-
entity (XXE) and entity-expansion ("billion laughs") attacks at the door before
the parser sees the content.
"""

from __future__ import annotations

import re
import urllib.request
from typing import Any
from xml.etree import ElementTree as ET

from .base import Skill

_HTTP_TIMEOUT = 10
# Portuguese news feeds by default (key-free public RSS from RTP, the national
# broadcaster — verified working). Users can pass any feed URL as the source.
_DEFAULT_FEEDS = {
    "top": "https://www.rtp.pt/noticias/rss",
    "world": "https://www.rtp.pt/noticias/rss/mundo",
    "country": "https://www.rtp.pt/noticias/rss/pais",
    "economy": "https://www.rtp.pt/noticias/rss/economia",
    "sport": "https://www.record.pt/rss",
}
# Detect a DOCTYPE anywhere in the prolog. If present, we refuse to parse.
_DOCTYPE_RE = re.compile(rb"<!DOCTYPE", re.IGNORECASE)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/0.1"})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:  # noqa: S310
        return resp.read()


def _strip_ns(tag: str) -> str:
    """'{http://www.w3.org/2005/Atom}entry' -> 'entry'."""
    return tag.rsplit("}", 1)[-1].lower()


def _clean_title(text: str) -> str:
    """Tidy a raw feed title: drop CDATA wrappers and stray HTML tags/entities.

    Some feeds (e.g. Record) wrap titles in <![CDATA[...]]>, and a few embed
    HTML. ElementTree already unwraps CDATA into .text, but we defensively strip
    any leftover markers and tags so headlines read as clean plain text.
    """
    import html as _html

    t = text.strip()
    # Remove leftover CDATA markers if a feed double-wrapped them.
    t = t.replace("<![CDATA[", "").replace("]]>", "")
    # Strip any HTML tags, then unescape entities (&amp; -> &).
    t = re.sub(r"<[^>]+>", "", t)
    t = _html.unescape(t)
    return t.strip()


def _extract_titles(raw: bytes, limit: int) -> list[str]:
    """Parse RSS (<item><title>) or Atom (<entry><title>) titles."""
    if _DOCTYPE_RE.search(raw):
        raise ValueError("feed contains a DOCTYPE; refusing to parse untrusted XML")
    root = ET.fromstring(raw)  # noqa: S314 - DOCTYPE rejected above; no ext entities
    titles: list[str] = []
    for elem in root.iter():
        if _strip_ns(elem.tag) in ("item", "entry"):
            for child in elem:
                if _strip_ns(child.tag) == "title" and child.text:
                    cleaned = _clean_title(child.text)
                    if cleaned:
                        titles.append(cleaned)
                    break
        if len(titles) >= limit:
            break
    return titles


class NewsSkill(Skill):
    name = "get_news"
    description = (
        "Get the latest news headlines. Optionally pass a topic ('world', "
        "'tech', 'top') or a full RSS/Atom feed URL, and how many headlines."
    )
    parameters: dict[str, Any] = {
        "source": {
            "type": "string",
            "description": "Topic ('world', 'tech', 'top') or a feed URL. Default 'top'.",
        },
        "count": {
            "type": "integer",
            "description": "How many headlines to return (1-10). Default 5.",
        },
    }
    required: list[str] = []

    def run(self, source: str = "top", count: int = 5, **kwargs: Any) -> str:
        source = (source or "top").strip()
        try:
            count = max(1, min(10, int(count)))
        except (ValueError, TypeError):
            count = 5

        # Resolve a topic keyword to a feed, else treat it as a URL.
        url = _DEFAULT_FEEDS.get(source.lower())
        label = source.lower() if url else source
        if url is None:
            if not source.lower().startswith(("http://", "https://")):
                return (
                    f"[error] Unknown topic {source!r}. Use one of "
                    f"{', '.join(sorted(_DEFAULT_FEEDS))}, or pass a feed URL."
                )
            url = source

        try:
            raw = _fetch(url)
        except Exception as exc:  # noqa: BLE001
            return f"[error] Could not fetch the feed: {exc}"

        try:
            titles = _extract_titles(raw, count)
        except ET.ParseError:
            return "[error] The feed wasn't valid XML I could read."
        except ValueError as exc:
            return f"[error] {exc}"

        if not titles:
            return f"I found no headlines in {label!r}."
        lines = "\n".join(f"{i}. {t}" for i, t in enumerate(titles, 1))
        return f"Top {len(titles)} headlines ({label}):\n{lines}"
