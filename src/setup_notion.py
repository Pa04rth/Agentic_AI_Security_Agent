"""
setup_notion.py  —  ONE-TIME SETUP
==================================
Auto-creates the 4 Notion databases with the exact PRD schema, seeds sensible
defaults, and writes their IDs to config/notion_ids.json so the pipeline can
find them.

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


# ---- Default seed content (you can edit all of this later inside Notion) ----
DEFAULT_TOPICS = [
    "Transformer architecture",
    "Large language model security",
    "LLM prompt injection",
    "Agentic AI systems",
    "Retrieval augmented generation",
    "AI red teaming",
    "Model alignment safety",
    "Adversarial machine learning",
]

DEFAULT_YOUTUBE = [
    ("Yannic Kilcher", "UCZHmQk67mSJgfCCTn7xBfew"),
    ("Two Minute Papers", "UCbfYPyITQ-7l4upoX8nvctg"),
    ("3Blue1Brown", "UCYO_jab_esuFRV4b17AJtAw"),
    ("AI Explained", "UCNJ1Ymd5yFuUPtn21xtRbbw"),
]

DEFAULT_RSS = [
    ("OpenAI Blog", "https://openai.com/blog/rss.xml"),
    ("Google DeepMind Blog", "https://deepmind.google/blog/rss.xml"),
    ("Anthropic News", "https://www.anthropic.com/news/rss.xml"),
    ("Simon Willison (LLM/AI)", "https://simonwillison.net/atom/everything/"),
    ("BAIR Blog (Berkeley AI)", "https://bair.berkeley.edu/blog/feed.xml"),
    ("arXiv cs.CR (Security)", "http://export.arxiv.org/rss/cs.CR"),
    ("arXiv cs.CL (NLP)", "http://export.arxiv.org/rss/cs.CL"),
    ("The Gradient", "https://thegradient.pub/rss/"),
]


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
    print("Seeding default records...")

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

    # DB2: Source Directory
    def add_source(name, type_name, value):
        props = {
            "Source Name": {"title": [{"text": {"content": name}}]},
            "Type": {"select": {"name": type_name}},
            "Status": {"checkbox": True},
        }
        if value:
            props["URL / ID"] = {"rich_text": [{"text": {"content": value}}]}
        notion.pages.create(parent={"database_id": ids["source_directory"]}, properties=props)

    for t in DEFAULT_TOPICS:
        add_source(t, "Topic", "")
    for name, cid in DEFAULT_YOUTUBE:
        add_source(name, "YouTube Channel ID", cid)
    for name, url in DEFAULT_RSS:
        add_source(name, "RSS Feed", url)


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
    print("Open your parent Notion page — you'll see all 4 databases, pre-populated.")
    for k, v in ids.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
