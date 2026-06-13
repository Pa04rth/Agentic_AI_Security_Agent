"""
fetchers/semantic_scholar.py
----------------------------
The Objective Filter. Pulls the most-cited papers for a topic within a
specific year+month window, sorted by citationCount descending. Sorting by
citations (not relevance) is a deliberate constraint to remove popularity /
LLM selection bias.

We use the BULK search endpoint because it supports:
  - sort=citationCount:desc
  - publicationDateOrYear date RANGES  -> lets us pin a single month
which the basic /paper/search endpoint does not.
"""

import calendar
import time
import requests

BULK_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
FIELDS = "title,url,abstract,publicationDate,citationCount"


def _month_range(year, month):
    """Return ('YYYY-MM-DD:YYYY-MM-DD') spanning the full calendar month."""
    last_day = calendar.monthrange(year, month)[1]
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year:04d}-{month:02d}-{last_day:02d}"
    return f"{start}:{end}"


def fetch_top_papers(topic, year, month, limit, api_key=None, _retries=3):
    """
    Returns up to `limit` papers for `topic` published in year/month,
    most-cited first. Each item: {title, url, abstract, publicationDate,
    citationCount, topic}.
    """
    params = {
        "query": topic,
        "publicationDateOrYear": _month_range(year, month),
        "fields": FIELDS,
        "sort": "citationCount:desc",
    }
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    for attempt in range(_retries):
        try:
            resp = requests.get(BULK_URL, params=params, headers=headers, timeout=30)
            if resp.status_code == 429:
                # Rate limited — back off and retry
                time.sleep(3 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            papers = data.get("data") or []
            cleaned = []
            for p in papers:
                if not p.get("title"):
                    continue
                cleaned.append({
                    "title": p.get("title"),
                    "url": p.get("url"),
                    "abstract": p.get("abstract") or "",
                    "publicationDate": p.get("publicationDate"),
                    "citationCount": p.get("citationCount") or 0,
                    "topic": topic,
                })
            # Bulk endpoint already sorts, but enforce it client-side too.
            cleaned.sort(key=lambda x: x["citationCount"], reverse=True)
            return cleaned[:limit]
        except requests.RequestException as e:
            if attempt == _retries - 1:
                print(f"  [semantic_scholar] '{topic}' {year}-{month:02d} failed: {e}")
                return []
            time.sleep(2 * (attempt + 1))
    return []
