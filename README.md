# 🧠 The CTO Executive Intelligence Engine

An automated, self-correcting personal intelligence pipeline for an AI Security founder / future CTO. It sources, ranks, summarizes, and delivers cutting-edge developments in AI Security, LLMs, Agentic AI, and MCP — on a **dual track**:

- **Old Era** — marches forward month-by-month from the birth of Transformers (Jan 2017), surfacing the *most-cited* foundational papers.
- **New Era** — does the same from Jan 2025 forward, for state-of-the-art shifts.

Plus a **Daily Social** industry feed and a **Sunday Firehose** data dump for self-paced study.

> **Notion is the control + storage layer.** You manage every topic, source, target, and the timeline from Notion — zero code changes. The pipeline reads its config from Notion, writes the curated digest into a Notion database, and fires a WhatsApp "it's ready" ping that deep-links straight to it.

---

## What changed vs. the original PRD (and why)

| PRD spec | This build | Why |
|---|---|---|
| Notion as DB + dashboard | **Notion (4 databases)** ✅ as specced | You control everything from Notion |
| Hand-build Notion schema | **`setup_notion.py` auto-creates + seeds all 4 DBs** | No manual database building |
| LinkedIn scraper (Apify/PhantomBuster, paid) | **RSS feeds** (free) | No paid scraper, no ToS/ban risk. Mint a feed for any LinkedIn/X person at rss.app or openrss.org and add it as an `RSS Feed` row |
| Telegram/Slack/Email alert | **WhatsApp via CallMeBot** (free) | You asked for WhatsApp; no business account or Twilio needed |
| Gemini AI core | **Claude API (Anthropic)** | Swapped per request; same CTO prompt |

Everything else follows the PRD: Semantic Scholar objective (citation-sorted) filter, month rollover logic written back to Notion, YouTube channel-restricted video matchmaker, the exact CTO summary prompt, token-minimal design, modular file structure, and `os.getenv` secret management.

---

## Repository layout

```
Agentic_AI_Security_Agent/
├── config/
│   └── notion_ids.json          # the 4 database IDs (created by setup_notion.py — COMMIT this)
├── src/
│   ├── setup_notion.py          # ONE-TIME: auto-creates + seeds the 4 Notion databases
│   ├── main.py                  # orchestration brain (day-of-week routing)
│   ├── notion_manager.py        # all Notion reads/writes (the 4 databases)
│   ├── claude_agent.py          # CTO 3-sentence summaries
│   ├── email_manager.py         # dedup ledger + HTML render + email digest (Gmail SMTP)
│   └── fetchers/
│       ├── semantic_scholar.py  # citation-sorted month search
│       ├── youtube.py           # channel-restricted matchmaker
│       └── rss.py               # 24h / 7d windowing
├── archive/                     # local dedup ledger (so items aren't re-posted)
├── .github/workflows/daily.yml  # free serverless cron, 05:00 IST (23:30 UTC)
├── requirements.txt
├── .env.example                 # copy to .env
└── README.md
```

The 4 Notion databases (created for you by the setup script):

| Database | Role | Key properties |
|---|---|---|
| **The Control Variables** | numeric targets | `Variable Name` (title), `Value` (number) |
| **The Source Directory** | topics / channels / feeds | `Source Name`, `Type` (select), `URL / ID`, `Status` (checkbox) |
| **The Time Tracker** | month cursors (auto-advanced) | `Era Name`, `Current Year`, `Current Month` |
| **The Morning Digest** | output | `Title`, `Content Type`, `Feed Type`, `URL`, `CTO Takeaway`, `Matched Explainer Video`, `Date Added`, `Read Status` |

---

## Notion setup (one time, ~5 min)

1. **Create an integration** → https://www.notion.so/my-integrations → *New integration* (internal) → copy the **Internal Integration Secret** into `.env` as `NOTION_API_KEY`.
2. **Create a parent page** in Notion (e.g. "CTO Engine"). Open its **`...` menu → Connections → Connect to → your integration**. This grants access.
3. **Get the page ID** — open the page, copy the 32-character hex string from its URL (the part after the title, before any `?`). Put it in `.env` as `NOTION_PARENT_PAGE_ID`.
4. **Run the setup script:**
   ```bash
   pip install -r requirements.txt
   cp .env.example .env        # fill in NOTION_API_KEY + NOTION_PARENT_PAGE_ID
   python src/setup_notion.py
   ```
   This creates all 4 databases on your page, seeds the operational defaults (targets + 2017/2025 cursors), and writes `config/notion_ids.json`. **The Source Directory is created empty on purpose** — you add your own Topics, YouTube Channel IDs, and RSS Feeds in Notion (set each row's `Status` checkbox to activate it). The pipeline only ever *reads* the Source Directory.

> **Commit `config/notion_ids.json`** to your repo so GitHub Actions can find the databases. It contains IDs, not secrets.

---

## Run it

```bash
python src/main.py --dry-run   # builds digest, writes NOTHING to Notion (safe test)
python src/main.py             # real run: writes to Morning Digest + emails the digest
```

Force a mode regardless of the day:

```bash
python src/main.py --mode weekday   # historical pincer + daily social
python src/main.py --mode sunday    # firehose + daily social
```

---

## Getting the keys (all free tiers)

1. **Notion** — integration secret from https://www.notion.so/my-integrations → `NOTION_API_KEY` (see Notion setup above).
2. **Claude (Anthropic)** — https://console.anthropic.com/settings/keys → `ANTHROPIC_API_KEY`. Default model `claude-haiku-4-5-20251001` keeps cost well under **$3/month**.
3. **YouTube Data API v3** — Google Cloud Console → enable "YouTube Data API v3" → create API key → `YOUTUBE_API_KEY`.
4. **Email (Gmail App Password)** — on a Gmail account with 2-Step Verification on, create a 16-char App Password at https://myaccount.google.com/apppasswords → put it in `EMAIL_APP_PASSWORD`, your address in `EMAIL_ADDRESS`, and the recipient in `EMAIL_TO`.
5. **Semantic Scholar** — optional; works keyless. A free key just raises rate limits.

---

## Deploy free on GitHub Actions

1. Push this folder to a GitHub repo (including `config/notion_ids.json`).
2. Repo → **Settings → Secrets and variables → Actions** → add as **Secrets**: `GEMINI_API_KEY`, `GEMINI_MODEL` (optional), `YOUTUBE_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY` (optional), `NOTION_API_KEY`, `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD`, `EMAIL_TO`.
3. The workflow runs daily at **05:00 IST** (cron `30 23 * * *`, i.e. 23:30 UTC) and auto-detects Sunday vs. weekday in IST. The month cursors live in Notion now; only the small local dedup ledger is committed back.
4. Trigger a test run anytime: repo → **Actions → CTO Executive Intelligence Engine → Run workflow**.

> Adjust the time by editing the `cron` line in `.github/workflows/daily.yml` (it's in UTC).

---

## How the engine works

**Mon–Sat — Historical Pincer.** Reads targets + cursors from Notion, queries Semantic Scholar's *bulk* endpoint per active topic for the exact month window, sorted `citationCount:desc` (objective, not LLM-picked). If a month is thin, the **rollover logic** advances the cursor a month at a time until the target is filled, then writes the new cursor straight back into the Time Tracker. Each paper gets a channel-restricted YouTube explainer match and a 3-sentence Claude CTO takeaway. 10 Old + 10 New land in the Morning Digest.

**Daily — Social feed.** Pulls active RSS feeds from the last 24h, capped at `Daily Social Target`.

**Sunday — Firehose.** Everything from the trailing 7 days across all feeds, no LLM, no filters — raw material for self-paced breakdown.

**Every day — Output.** Dedupes against the local ledger, writes rows into the Morning Digest database, and fires a WhatsApp ping deep-linking to it.

---

## Customizing — all inside Notion, no code

- **More/less per day** → edit the `Value` numbers in **The Control Variables**.
- **Add a topic / channel / feed** → add a row in **The Source Directory**, pick the `Type`, fill `URL / ID`, tick `Status`. Untick `Status` to pause a source.
- **Add a specific LinkedIn/X person** → mint an RSS feed at rss.app or openrss.org, then add it as an `RSS Feed` row. (Raw `LinkedIn URL` rows are intentionally skipped — no scraping.)
- **Jump the timeline** → edit `Current Year` / `Current Month` in **The Time Tracker**.

---

## Cost & token hygiene

Only the abstracts of *currently selected* papers are ever sent to Claude — historical records are never replayed — so the context window never bloats. With `claude-haiku-4-5` and ~20 short summaries/day, monthly spend stays under **$3**. Notion, Semantic Scholar, YouTube (within quota), feedparser, CallMeBot, and GitHub Actions are all free.
