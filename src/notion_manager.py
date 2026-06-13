"""
notion_manager.py
-----------------
The Database Layer. All Notion reads/writes live here (separation of concerns).
Maps the 4 PRD databases:

  DB1 "The Control Variables"  -> numeric targets
  DB2 "The Source Directory"   -> topics / youtube channels / rss feeds
  DB3 "The Time Tracker"       -> month/year cursors (read + write)
  DB4 "The Morning Digest"     -> output rows

Database IDs are read from config/notion_ids.json, which is produced by
setup_notion.py. The Notion integration token comes from NOTION_API_KEY.
"""

import os
import json
import time

try:
    from notion_client import Client
except ImportError:  # pragma: no cover
    Client = None

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IDS_FILE = os.path.join(_ROOT, "config", "notion_ids.json")

_client = None
_ids = None


# ----------------------------------------------------------------------
#  Bootstrap
# ----------------------------------------------------------------------
def client():
    global _client
    if _client is None:
        if Client is None:
            raise RuntimeError("notion-client not installed. pip install notion-client")
        token = os.getenv("NOTION_API_KEY")
        if not token:
            raise RuntimeError("NOTION_API_KEY is not set.")
        # Pin to the 2022-06-28 API. notion-client >=3 defaults to "2025-09-03"
        # (the "data source" model), which breaks the database_id-based
        # databases.query / pages.create calls this module relies on.
        _client = Client(auth=token, notion_version="2022-06-28")
    return _client


def ids():
    global _ids
    if _ids is None:
        if not os.path.exists(_IDS_FILE):
            raise RuntimeError(
                f"{_IDS_FILE} not found. Run: python src/setup_notion.py first."
            )
        with open(_IDS_FILE, "r", encoding="utf-8") as f:
            _ids = json.load(f)
    return _ids


# ----------------------------------------------------------------------
#  Small property helpers
# ----------------------------------------------------------------------
def _title(prop):
    arr = prop.get("title", [])
    return arr[0]["plain_text"].strip() if arr else ""


def _rich(prop):
    arr = prop.get("rich_text", [])
    return arr[0]["plain_text"].strip() if arr else ""


def _select(prop):
    sel = prop.get("select")
    return sel["name"] if sel else ""


def _number(prop):
    return prop.get("number")


def _checkbox(prop):
    return bool(prop.get("checkbox"))


def _query_all(database_id, filter_=None):
    """Paginate through an entire database, honoring an optional filter."""
    results = []
    cursor = None
    while True:
        kwargs = {"database_id": database_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        if filter_:
            kwargs["filter"] = filter_
        resp = client().databases.query(**kwargs)
        results.extend(resp["results"])
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return results


# ----------------------------------------------------------------------
#  DB1 — Control Variables
# ----------------------------------------------------------------------
def get_control_variables():
    rows = _query_all(ids()["control_variables"])
    table = {}
    for r in rows:
        p = r["properties"]
        name = _title(p.get("Variable Name", {}))
        val = _number(p.get("Value", {}))
        if name:
            table[name] = val
    return {
        "old_era_daily_target": int(table.get("Old Era Daily Target", 10) or 10),
        "new_era_daily_target": int(table.get("New Era Daily Target", 10) or 10),
        "daily_social_target": int(table.get("Daily Social Target", 10) or 10),
        "sunday_firehose_cap": int(table.get("Sunday Firehose Cap", 400) or 400),
    }


# ----------------------------------------------------------------------
#  DB2 — Source Directory  (only Status == checked rows)
# ----------------------------------------------------------------------
def _active_sources_of_type(type_name):
    flt = {
        "and": [
            {"property": "Status", "checkbox": {"equals": True}},
            {"property": "Type", "select": {"equals": type_name}},
        ]
    }
    rows = _query_all(ids()["source_directory"], filter_=flt)
    out = []
    for r in rows:
        p = r["properties"]
        out.append({
            "name": _title(p.get("Source Name", {})),
            "value": _rich(p.get("URL / ID", {})),
        })
    return out


def get_active_topics():
    return [s["name"] for s in _active_sources_of_type("Topic") if s["name"]]


def get_active_youtube_channels():
    return [
        {"name": s["name"], "id": s["value"]}
        for s in _active_sources_of_type("YouTube Channel ID")
        if s["value"]
    ]


def get_active_rss_feeds():
    return [
        {"name": s["name"], "url": s["value"]}
        for s in _active_sources_of_type("RSS Feed")
        if s["value"]
    ]


# ----------------------------------------------------------------------
#  DB3 — Time Tracker  (read + update)
# ----------------------------------------------------------------------
def get_time_tracker():
    """Return {'old_era': {...}, 'new_era': {...}} each with year, month, page_id."""
    rows = _query_all(ids()["time_tracker"])
    tracker = {}
    for r in rows:
        p = r["properties"]
        era_name = _title(p.get("Era Name", {}))
        year = _number(p.get("Current Year", {}))
        month = _number(p.get("Current Month", {}))
        key = era_name.strip().lower().replace(" ", "_")  # "Old Era" -> "old_era"
        if key in ("old_era", "new_era"):
            tracker[key] = {
                "year": int(year) if year is not None else (2017 if key == "old_era" else 2025),
                "month": int(month) if month is not None else 1,
                "page_id": r["id"],
            }
    tracker.setdefault("old_era", {"year": 2017, "month": 1, "page_id": None})
    tracker.setdefault("new_era", {"year": 2025, "month": 1, "page_id": None})
    return tracker


def update_time_tracker_era(era):
    """Write a single era's advanced cursor back to its Notion page."""
    if not era.get("page_id"):
        return
    client().pages.update(
        page_id=era["page_id"],
        properties={
            "Current Year": {"number": int(era["year"])},
            "Current Month": {"number": int(era["month"])},
        },
    )


def advance_month(era):
    """Pure cursor math; mutates and returns era. (Mirrors the PRD rollover.)"""
    era["month"] += 1
    if era["month"] > 12:
        era["month"] = 1
        era["year"] += 1
    return era


# ----------------------------------------------------------------------
#  DB4 — Morning Digest  (write output rows)
# ----------------------------------------------------------------------
def _clip(text, limit=1900):
    text = (text or "").strip()
    return text[:limit]


def _row_to_properties(row):
    title = row.get("title", "(untitled)")
    url = (row.get("url") or "").strip() or None
    takeaway = row.get("cto_takeaway") or row.get("summary") or ""
    video = (row.get("matched_explainer_video") or "").strip() or None
    date_added = row.get("date_added")

    props = {
        "Title": {"title": [{"text": {"content": _clip(title, 200)}}]},
        "Content Type": {"select": {"name": row.get("content_type", "Article")}},
        "Feed Type": {"select": {"name": row.get("feed_type", "Daily Social")}},
        "CTO Takeaway": {"rich_text": [{"text": {"content": _clip(takeaway)}}]},
        "Read Status": {"checkbox": False},
    }
    if url:
        props["URL"] = {"url": url}
    if video:
        props["Matched Explainer Video"] = {"url": video}
    if date_added:
        props["Date Added"] = {"date": {"start": date_added}}
    return props


def add_digest_rows(rows, pause=0.0):
    """Create one Notion page per row in the Morning Digest DB."""
    db = ids()["morning_digest"]
    created = 0
    for row in rows:
        try:
            client().pages.create(
                parent={"database_id": db},
                properties=_row_to_properties(row),
            )
            created += 1
            if pause:
                time.sleep(pause)
        except Exception as e:
            print(f"  [notion] failed to write '{row.get('title','?')[:50]}': {e}")
    return created


def digest_deeplink():
    """A direct https link to the Morning Digest database view."""
    db = ids().get("morning_digest", "")
    return f"https://www.notion.so/{db.replace('-', '')}" if db else ""
