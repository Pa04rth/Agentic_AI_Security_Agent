"""
email_manager.py
----------------
The Master Output. This replaces Notion's "Morning Digest" database. It:
  1) appends every selected item to a local JSONL archive (dedup + history), and
  2) renders a clean HTML digest and emails it via Gmail SMTP.

Each digest "row" mirrors the PRD's Morning Digest schema:
  title, content_type, feed_type, url, cto_takeaway,
  matched_explainer_video, date_added, read_status(False)
"""

import os
import json
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ARCHIVE_DIR = os.path.join(_ROOT, "archive")
_ARCHIVE_FILE = os.path.join(_ARCHIVE_DIR, "digest_archive.jsonl")
_SEEN_FILE = os.path.join(_ARCHIVE_DIR, "seen_urls.txt")


# ----------------------------------------------------------------------
#  Dedup + archive
# ----------------------------------------------------------------------
def _load_seen():
    if not os.path.exists(_SEEN_FILE):
        return set()
    with open(_SEEN_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def _append_seen(urls):
    os.makedirs(_ARCHIVE_DIR, exist_ok=True)
    with open(_SEEN_FILE, "a", encoding="utf-8") as f:
        for u in urls:
            f.write(u + "\n")


def dedupe(rows):
    """Drop rows whose URL was already archived in a previous run."""
    seen = _load_seen()
    fresh = []
    for r in rows:
        url = (r.get("url") or "").strip()
        if url and url in seen:
            continue
        fresh.append(r)
    return fresh


def archive(rows):
    os.makedirs(_ARCHIVE_DIR, exist_ok=True)
    with open(_ARCHIVE_FILE, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    _append_seen([r.get("url", "") for r in rows if r.get("url")])


# ----------------------------------------------------------------------
#  HTML rendering
# ----------------------------------------------------------------------
def _section_html(title, rows):
    if not rows:
        return ""
    parts = [f'<h2 style="color:#1a1a2e;border-bottom:2px solid #16213e;'
             f'padding-bottom:6px;margin-top:28px;">{title} '
             f'<span style="color:#888;font-weight:normal;">({len(rows)})</span></h2>']
    for r in rows:
        link = r.get("url") or "#"
        name = r.get("title", "(untitled)")
        ct = r.get("content_type", "")
        meta_bits = [b for b in [
            ct,
            r.get("topic"),
            r.get("source"),
            (f"{r.get('citationCount')} citations"
             if r.get("citationCount") is not None and ct == "Paper" else None),
            r.get("publicationDate") or r.get("published"),
        ] if b]
        meta = " &middot; ".join(str(b) for b in meta_bits)
        takeaway = r.get("cto_takeaway", "")
        video = r.get("matched_explainer_video")
        block = [
            '<div style="margin:14px 0;padding:12px 14px;background:#f7f7fb;'
            'border-left:3px solid #16213e;border-radius:4px;">',
            f'<a href="{link}" style="font-size:15px;font-weight:600;'
            f'color:#0f3460;text-decoration:none;">{name}</a>',
        ]
        if meta:
            block.append(f'<div style="font-size:12px;color:#777;margin-top:3px;">{meta}</div>')
        if takeaway:
            block.append(f'<div style="font-size:13px;color:#333;margin-top:8px;'
                         f'line-height:1.5;">{takeaway}</div>')
        if video:
            block.append(f'<div style="margin-top:6px;font-size:13px;">'
                         f'&#127909; <a href="{video}" style="color:#c0392b;">'
                         f'Explainer video</a></div>')
        block.append("</div>")
        parts.append("".join(block))
    return "".join(parts)


def render_digest_html(sections, date_str):
    """sections: ordered list of (title, rows)."""
    total = sum(len(rows) for _, rows in sections)
    body = [
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;'
        'max-width:760px;margin:auto;color:#1a1a2e;">',
        f'<h1 style="margin-bottom:2px;">&#129504; CTO Executive Intelligence Digest</h1>',
        f'<div style="color:#888;font-size:13px;margin-bottom:4px;">{date_str} '
        f'&middot; {total} items</div>',
    ]
    for title, rows in sections:
        body.append(_section_html(title, rows))
    if total == 0:
        body.append('<p style="color:#888;">No new items today. The cursor will '
                     'advance and try fresh windows on the next run.</p>')
    body.append('<hr style="margin-top:32px;border:none;border-top:1px solid #ddd;">')
    body.append('<div style="font-size:11px;color:#aaa;">Generated automatically by '
                'The CTO Executive Intelligence Engine.</div>')
    body.append("</div>")
    return "".join(body)


# ----------------------------------------------------------------------
#  Sending
# ----------------------------------------------------------------------
def send_email(html, subject):
    addr = os.getenv("EMAIL_ADDRESS")
    pw = os.getenv("EMAIL_APP_PASSWORD")
    to = os.getenv("EMAIL_TO", addr)
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))

    if not addr or not pw:
        print("  [email] EMAIL_ADDRESS / EMAIL_APP_PASSWORD not set — skipping send.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = addr
    msg["To"] = to
    msg.attach(MIMEText(html, "html", "utf-8"))

    context = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context) as server:
                server.login(addr, pw)
                server.sendmail(addr, [t.strip() for t in to.split(",")], msg.as_string())
        else:
            with smtplib.SMTP(host, port) as server:
                server.starttls(context=context)
                server.login(addr, pw)
                server.sendmail(addr, [t.strip() for t in to.split(",")], msg.as_string())
        print(f"  [email] Digest sent to {to}")
        return True
    except Exception as e:
        print(f"  [email] Send failed: {e}")
        return False


def utc_date_str():
    return datetime.now(timezone.utc).strftime("%A, %d %B %Y")
