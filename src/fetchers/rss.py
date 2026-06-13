"""
fetchers/rss.py
---------------
Parses RSS/Atom feeds with feedparser and returns entries published inside a
rolling time window. Powers BOTH:
  - Module 2 (Daily Social): window_hours = 24
  - Module 3 (Sunday Firehose): window_hours = 168 (7 days)

This is also the free, ToS-safe replacement for LinkedIn scraping: point it at
Substack/blog feeds, or at an rss.app/openrss.org feed minted from a specific
LinkedIn or X profile.
"""

import time
from datetime import datetime, timezone, timedelta
import feedparser


def _entry_datetime(entry):
    """Best-effort published/updated datetime (UTC). None if unavailable."""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    return None


def fetch_recent(feed, window_hours):
    """
    feed: {"name": ..., "url": ...}
    Returns a list of dicts: {title, url, summary, published, source}.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    out = []
    try:
        parsed = feedparser.parse(feed["url"])
    except Exception as e:  # feedparser rarely raises, but be safe
        print(f"  [rss] {feed['name']} failed: {e}")
        return out

    for entry in parsed.entries:
        dt = _entry_datetime(entry)
        # If a feed omits dates, keep the item (better to over-include than drop).
        if dt is not None and dt < cutoff:
            continue
        summary = entry.get("summary", "") or ""
        out.append({
            "title": entry.get("title", "(untitled)"),
            "url": entry.get("link", ""),
            "summary": summary,
            "published": dt.isoformat() if dt else None,
            "source": feed["name"],
        })
    return out


def fetch_all_recent(feeds, window_hours, cap=None):
    """Aggregate across many feeds. Optionally cap total items (newest first)."""
    items = []
    for feed in feeds:
        items.extend(fetch_recent(feed, window_hours))

    # Sort newest first; undated items sink to the bottom.
    items.sort(key=lambda x: x["published"] or "", reverse=True)
    if cap is not None:
        items = items[:cap]
    return items
