"""
setup_notion.py  —  ONE-TIME SETUP
==================================
Auto-creates the 4 Notion databases with the exact PRD schema, seeds operational
defaults (Control Variables + Time Tracker only), and writes their IDs to
config/notion_ids.json so the pipeline can find them.

NOTE: The Source Directory (DB2) is created EMPTY on purpose. You decide its
contents — topics, YouTube channel IDs, and RSS feeds — directly in Notion. The
pipeline only ever READS the Source Directory; it never writes to it.

Prereqs (see README "Notion setup"):
  1) Create an internal integration at https://www.notion.so/my-integrations
     and copy its secret  ->  NOTION_API_KEY in .env
  2) Create (or pick) a Notion PAGE to hold these databases, then "Connect" your
     integration to it (page ... menu -> Connections -> your integration).
  3) Copy that page's ID (the 32-char hex in its URL) -> NOTION_PARENT_PAGE_ID in .env

Then run:
    python src/setup_notion.py

Safe to re-run only if you delete config/notion_ids.json first (otherwise it
refuses, to avoid creating duplicate databases).
"""

import os
import json
import sys

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except Exception:
    pass

from notion_client import Client

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IDS_FILE = os.path.join(_ROOT, "config", "notion_ids.json")


def _parent(page_id):
    return {"type": "page_id", "page_id": page_id}


def _db_title(text):
    return [{"type": "text", "text": {"content": text}}]


def create_databases(notion, parent_page):
    print("Creating databases...")

    control = notion.databases.create(
        parent=_parent(parent_page),
        title=_db_title("The Control Variables"),
        properties={
            "Variable Name": {"title": {}},
            "Value": {"number": {}},
        },
    )

    sources = notion.databases.create(
        parent=_parent(parent_page),
        title=_db_title("The Source Directory"),
        properties={
            "Source Name": {"title": {}},
            "Type": {"select": {"options": [
                {"name": "Topic", "color": "blue"},
                {"name": "YouTube Channel ID", "color": "red"},
                {"name": "RSS Feed", "color": "green"},
                {"name": "LinkedIn URL", "color": "purple"},
            ]}},
            "URL / ID": {"rich_text": {}},
            "Status": {"checkbox": {}},
        },
    )

    tracker = notion.databases.create(
        parent=_parent(parent_page),
        title=_db_title("The Time Tracker"),
        properties={
            "Era Name": {"title": {}},
            "Current Year": {"number": {}},
            "Current Month": {"number": {}},
        },
    )

    digest = notion.databases.create(
        parent=_parent(parent_page),
        title=_db_title("The Morning Digest"),
        properties={
            "Title": {"title": {}},
            "Content Type": {"select": {"options": [
                {"name": "Paper", "color": "blue"},
                {"name": "Video", "color": "red"},
                {"name": "Article", "color": "green"},
                {"name": "Social", "color": "orange"},
            ]}},
            "Feed Type": {"select": {"options": [
                {"name": "Mon-Sat Historical", "color": "blue"},
                {"name": "Daily Social", "color": "green"},
                {"name": "Sunday Firehose", "color": "red"},
            ]}},
            "URL": {"url": {}},
            "CTO Takeaway": {"rich_text": {}},
            "Matched Explainer Video": {"url": {}},
            "Date Added": {"date": {}},
            "Read Status": {"checkbox": {}},
        },
    )

    return {
        "control_variables": control["id"],
        "source_directory": sources["id"],
        "time_tracker": tracker["id"],
        "morning_digest": digest["id"],
    }


def seed(notion, ids):
    """Seed ONLY the operational databases the pipeline must mutate at runtime
    (Control Variables + Time Tracker). The Source Directory (DB2) is left empty
    on purpose — you own its contents and edit them directly in Notion."""
    print("Seeding operational defaults (Control Variables + Time Tracker)...")

    # DB1: Control Variables
    for name, val in [
        ("Old Era Daily Target", 10),
        ("New Era Daily Target", 10),
        ("Daily Social Target", 10),
        ("Sunday Firehose Cap", 400),
    ]:
        notion.pages.create(parent={"database_id": ids["control_variables"]}, properties={
            "Variable Name": {"title": [{"text": {"content": name}}]},
            "Value": {"number": val},
        })

    # DB3: Time Tracker
    for era, year in [("Old Era", 2017), ("New Era", 2025)]:
        notion.pages.create(parent={"database_id": ids["time_tracker"]}, properties={
            "Era Name": {"title": [{"text": {"content": era}}]},
            "Current Year": {"number": year},
            "Current Month": {"number": 1},
        })

    # DB2: Source Directory — intentionally NOT seeded. You decide every Topic,
    # YouTube Channel ID, and RSS Feed by adding rows in Notion (set Status =
    # checked to activate). The pipeline reads this DB but must never write it.
    print("Source Directory left EMPTY — populate it yourself in Notion "
          "(Type = Topic / YouTube Channel ID / RSS Feed, Status = checked).")


def main():
    token = os.getenv("NOTION_API_KEY")
    parent = os.getenv("NOTION_PARENT_PAGE_ID")
    if not token or not parent:
        sys.exit("Set NOTION_API_KEY and NOTION_PARENT_PAGE_ID in .env first.")

    if os.path.exists(_IDS_FILE):
        sys.exit(f"{_IDS_FILE} already exists. Delete it first to re-create databases.")

    # Pin to the 2022-06-28 API. notion-client >=3 defaults to "2025-09-03",
    # which moves schema/properties onto "data sources" and silently ignores
    # the top-level `properties` passed to databases.create — leaving a DB with
    # only a default "Name" column, which then breaks seeding.
    notion = Client(auth=token, notion_version="2022-06-28")
    ids = create_databases(notion, parent)
    seed(notion, ids)

    os.makedirs(os.path.dirname(_IDS_FILE), exist_ok=True)
    with open(_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2)

    print("\nDone! Database IDs written to config/notion_ids.json")
    print("Open your parent Notion page — you'll see all 4 databases.")
    print("Next step: open 'The Source Directory' and add your own Topics, "
          "YouTube Channel IDs, and RSS Feeds (Status = checked to activate).")
    for k, v in ids.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
