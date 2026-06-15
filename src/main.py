"""
main.py  —  The Orchestration Brain
===================================
Config and storage both live in Notion now (notion_manager). Routes by day
of week (UTC):

  Mon–Sat  -> Module 1 (Historical Pincer)  + Module 2 (Daily Social)
  Sunday   -> Module 3 (Unfiltered Firehose) + Module 2 (Daily Social)
  Every day-> Module 4 (write to Notion Morning Digest + WhatsApp ping)

Run locally:
    python src/main.py                # auto-detect today's mode
    python src/main.py --mode weekday # force historical+social
    python src/main.py --mode sunday  # force firehose
    python src/main.py --dry-run      # build digest, DON'T write Notion / WhatsApp
"""

import os
import argparse
from datetime import datetime, timezone, timedelta

# All day-of-week routing is done in IST so "Sunday" means Sunday in India,
# matching the 05:00 IST schedule (see .github/workflows/daily.yml).
IST = timezone(timedelta(hours=5, minutes=30))

# Load .env for local runs (GitHub Actions injects env directly).
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except Exception:
    pass

import notion_manager as db
from claude_agent import ClaudeAgent
from fetchers import semantic_scholar, youtube, rss
import email_manager as archive  # dedup ledger, HTML render, and the email digest


# ======================================================================
#  MODULE 1 — Monday–Saturday Historical Engine (Pincer + Rollover)
# ======================================================================
def run_historical(controls, claude):
    print("[Module 1] Historical pincer engine")
    topics = db.get_active_topics()
    channels = [c["id"] for c in db.get_active_youtube_channels()]
    print(f"  active sources: {len(topics)} topics, {len(channels)} youtube channels")
    if not topics:
        print("  WARNING: no active Topics in 'The Source Directory' "
              "(add rows with Type=Topic and Status=checked) — 0 papers will be found.")
    yt_key = os.getenv("YOUTUBE_API_KEY")
    ss_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    tracker = db.get_time_tracker()

    rows = []
    for era_key, target_key in (
        ("old_era", "old_era_daily_target"),
        ("new_era", "new_era_daily_target"),
    ):
        target = controls[target_key]
        era = tracker[era_key]
        collected = _collect_era_papers(topics, era, target, ss_key, max_rollovers=12)
        print(f"  {era_key}: {len(collected)} papers "
              f"(cursor now {era['year']}-{era['month']:02d})")

        for p in collected:
            p["content_type"] = "Paper"
            p["feed_type"] = "Mon-Sat Historical"
            p["era"] = era_key
            p["matched_explainer_video"] = youtube.find_explainer(
                p["title"], channels, yt_key
            )
        claude.summarize_batch(collected)
        rows.extend(collected)

        # Persist the advanced cursor straight back to its Notion page.
        db.update_time_tracker_era(era)

    return rows


def _collect_era_papers(topics, era, target, ss_key, max_rollovers):
    """Fill `target` papers for one era; roll the month cursor forward when a
    month is too thin. `era` (year/month) is mutated in place."""
    collected = []
    seen_urls = set()
    rollovers = 0
    while len(collected) < target and rollovers <= max_rollovers:
        per_topic = max(1, (target - len(collected)) // max(1, len(topics)) + 1)
        for topic in topics:
            if len(collected) >= target:
                break
            papers = semantic_scholar.fetch_top_papers(
                topic, era["year"], era["month"], per_topic, api_key=ss_key
            )
            for p in papers:
                key = p.get("url") or p.get("title")
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                collected.append(p)
                if len(collected) >= target:
                    break
        if len(collected) < target:
            db.advance_month(era)
            rollovers += 1
    return collected[:target]


# ======================================================================
#  MODULE 2 — Daily Social & Industry Feed (RSS; runs every day)
# ======================================================================
def run_daily_social(controls):
    print("[Module 2] Daily social / industry feed")
    feeds = db.get_active_rss_feeds()
    print(f"  active sources: {len(feeds)} RSS feeds")
    if not feeds:
        print("  WARNING: no active RSS Feeds in 'The Source Directory' "
              "(add rows with Type=RSS Feed and Status=checked) — 0 items will be found.")
    items = rss.fetch_all_recent(feeds, window_hours=24,
                                 cap=controls["daily_social_target"])
    for it in items:
        it["content_type"] = "Article"
        it["feed_type"] = "Daily Social"
    print(f"  {len(items)} items in last 24h")
    return items


# ======================================================================
#  MODULE 3 — Sunday Unfiltered Firehose (no LLM, no filters)
# ======================================================================
def run_sunday_firehose(controls):
    print("[Module 3] Sunday firehose")
    feeds = db.get_active_rss_feeds()
    items = rss.fetch_all_recent(feeds, window_hours=168,
                                 cap=controls["sunday_firehose_cap"])
    for it in items:
        it["content_type"] = "Article"
        it["feed_type"] = "Sunday Firehose"
    print(f"  {len(items)} items in trailing 7 days")
    return items


# ======================================================================
#  MODULE 4 — Output: dedupe -> write to Notion -> email the digest
# ======================================================================
def finalize(sections, dry_run):
    now_iso = datetime.now(timezone.utc).isoformat()
    flat = []
    for _, rows in sections:
        for r in rows:
            r.setdefault("date_added", now_iso)
            r.setdefault("read_status", False)
            flat.append(r)

    collected = len(flat)
    flat = archive.dedupe(flat)  # skip anything already pushed in a prior run
    total = len(flat)
    print(f"  [finalize] {collected} collected -> {total} new after dedup "
          f"({collected - total} already seen)")
    if collected == 0:
        print("  [finalize] WARNING: pipeline collected 0 items. Check that "
              "'The Source Directory' has rows with Status = checked "
              "(Topics / RSS Feeds / YouTube Channel IDs).")
    date_str = archive.utc_date_str()

    if dry_run:
        deduped_sections = [(title, [r for r in rows if r in flat])
                            for title, rows in sections]
        html = archive.render_digest_html(deduped_sections, date_str)
        out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "archive", "last_digest_preview.html")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[dry-run] {total} new items. Notion NOT written. Preview: {out}")
        return

    written_rows = db.add_digest_rows(flat, pause=0.15)
    # Only mark rows that were actually written as "seen", so a failed Notion
    # write is retried next run instead of being silently dropped forever.
    archive.archive(written_rows)
    written = len(written_rows)
    print(f"  [notion] wrote {written}/{total} rows to Morning Digest")
    if total and written == 0:
        print("  [notion] WARNING: had new items but wrote 0 rows — every "
              "Notion write failed (check NOTION_API_KEY and that the "
              "integration is connected to the Morning Digest database).")

    # Completion notification by email (replaces the old WhatsApp ping). The
    # email carries the full rendered digest, so you get the content even if a
    # Notion write failed above.
    link = db.digest_deeplink()
    deduped_sections = [(title, [r for r in rows if r in flat])
                        for title, rows in sections]
    html = archive.render_digest_html(deduped_sections, date_str)
    if link:
        html += (f'<p style="font-size:13px;margin-top:8px;">'
                 f'Open in Notion: <a href="{link}">{link}</a></p>')
    subject = f"🧠 CTO Intelligence Digest — {written} new items ({date_str})"
    archive.send_email(html, subject)


# ======================================================================
#  Entry point
# ======================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["auto", "weekday", "sunday"], default="auto")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    controls = db.get_control_variables()
    claude = ClaudeAgent()

    weekday = datetime.now(IST).weekday()  # Mon=0 ... Sun=6 (in IST)
    mode = args.mode
    if mode == "auto":
        mode = "sunday" if weekday == 6 else "weekday"

    print(f"=== CTO Engine run | mode={mode} | claude={'on' if claude.enabled else 'off'} ===")

    sections = []
    if mode == "sunday":
        sections.append(("Sunday Firehose (trailing 7 days)", run_sunday_firehose(controls)))
        sections.append(("Daily Social", run_daily_social(controls)))
    else:
        hist = run_historical(controls, claude)
        sections.append(("Old Era — Foundations",
                         [r for r in hist if r.get("era") == "old_era"]))
        sections.append(("New Era — State of the Art",
                         [r for r in hist if r.get("era") == "new_era"]))
        sections.append(("Daily Social", run_daily_social(controls)))

    finalize(sections, args.dry_run)
    print("=== Run complete ===")


if __name__ == "__main__":
    main()
