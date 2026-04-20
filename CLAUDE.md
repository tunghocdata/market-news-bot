# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
# Install dependencies
pip install -r requirements.txt
pip install yfinance vnstock   # optional market data libs

# Run 1 — 06:00: scrape 8h overnight, Sheets draft, Telegram preview, save cache
python3 morning_run.py --run1

# Run 2 — 09:15: merge cache, full Sheets, HTML report, Telegram full report, git push
python3 morning_run.py

# Test mode: builds HTML + writes Sheets + sends Telegram full report + saves DB
# (same as run2 but without git push — despite the docstring saying "preview only")
python3 morning_run.py --test

# Debug v2marketnews scraper standalone
python3 v2marketnews.py --rss-only --no-enrich   # ~15s, RSS headlines only
python3 v2marketnews.py --no-enrich               # ~30s, RSS + scrape
python3 v2marketnews.py --hours 3                 # full pipeline, last 3h

# Interactive Telegram bot (run separately, long-polling)
python3 bot_server.py
```

Scheduling on macOS is via **launchd** (not crontab):
```bash
launchctl start com.tintuc.run1         # trigger run1 manually
launchctl start com.tintuc.run2         # trigger run2 manually
launchctl list | grep tintuc            # check status
tail -f ~/Library/Logs/tintuc_run1.log  # live log
```
Plist files: `~/Library/LaunchAgents/com.tintuc.run{1,2}.plist`. Logs: `~/Library/Logs/tintuc_run{1,2}.log`.

GitHub Actions (`marketbrief.yml`): `workflow_dispatch` only — manually deploys `morning-brief.html`.

## Architecture

`morning_run.py` is the sole orchestrator. The pipeline runs twice daily:

**Run1 (06:00):** `--run1` flag
1. **`morning_brief.py`** — Fetch market prices → save `market_data.json` + `market_data.js`.
2. **`v2marketnews.py`** `fetch_articles(hours=8)` — Async RSS + scrape + enrich pipeline.
3. **`classifier.py`** — Group by `category` field (set by `v2marketnews`, zero-cost).
4. **`ticker_classifier.py`** + **`summarizer.summarize_all()`** + **`generate_market_view()`** — AI.
5. **`sheets.py`** — Write Google Sheets draft tab.
6. **Cache** — Save `.marketbot/run1_cache.json`.
7. **`report_builder.send_run1_preview()`** — Send short Telegram preview.

**Run2 (09:15):** default (no flag)
1. **`morning_brief.py`** — Fetch latest prices → overwrite `market_data.json` / `market_data.js`.
2. **`v2marketnews.fetch_articles(hours=3)`** — Morning articles.
3. **Merge** — Load `run1_cache.json` + merge + dedup by URL.
4. **`classifier.py`** → **`summarizer`** → `_build_macro_bullets_ai()`.
5. **`report_builder.build_html_report()`** — Build `morning-brief.html`.
6. **`sheets.py`** — Overwrite day tab.
7. **`report_builder.send_morning_brief()`** — Send full Telegram (HTML parse_mode, auto-split at 4096 chars).
8. **`database.save_articles()` + `save_market_snapshot()`** — Persist to SQLite.
9. **git commit + push** — Push `morning-brief.html` to GitHub.

Central config in **`marketreview.py`**: broker info, API keys via env, source URLs.

### v2marketnews Pipeline (`v2marketnews.py`)

Replaces the old `scraper.py` + `enrich_content.py`. Single async module that handles:
- RSS fetch (parallel, 12 workers) from ~30 international + ~20 Vietnamese sources
- HTML scraping (6 workers) for sources without RSS
- Content enrichment (20 async workers): `trafilatura` → Jina AI (`r.jina.ai`) → RSS summary fallback
- Paywall domains (`bloomberg.com`, `wsj.com`, `ft.com`...) skip to RSS summary directly
- Guardian API (`GUARDIAN_API_KEY`) as direct source
- Categories are assigned per-source in the source config (not keyword-matched at runtime)

Article shape after `v2marketnews`:
```python
{
  "source": str, "title": str, "url": str,
  "summary": str, "content": str,
  "datetime": str,          # ISO 8601, VN tz
  "category": str,          # one of 10 CATEGORIES keys
  "region": "intl"|"vn",
  "lang": "vi"|"en",
  "full_text": str,         # enriched body text
  "source_quality": str,
}
```

### Market Data Sources (`morning_brief.py`)

| Data | Source | Notes |
|---|---|---|
| VN indices (VN-Index, VN30, HNX, UPCOM) | 24hMoney API | `is_today` flag check |
| World indices, commodities | `yfinance` | `history(period="5d")` |
| USD/VND | VCB XML → ER-API fallback | |
| Crypto (BTC, ETH, BNB) | CoinGecko (no key) | |
| Foreign trading (khối ngoại) | 24hMoney API (VN-INDEX row) | Stale check vs VN timezone |

### Classifier Categories (10 groups)

`classifier.py` now just reads the `category` field set by `v2marketnews` — no keyword matching. Categories:

`chung_khoan`, `tai_chinh`, `doanh_nghiep`, `bat_dong_san`, `hang_hoa`, `vi_mo`, `thi_truong`, `the_gioi`, `phan_tich`, `markets`

Articles without a matching category go to `unclassified` (skipped by AI summarizer).

### Database (`database.py`)

SQLite at `.marketbot/marketbot.db`. Two tables: `articles` (indexed by date, category, source) and `market_snapshots` (one row per date). Called at end of every run via `save_articles()` and `save_market_snapshot()`. Used by `bot_server.py` for interactive queries.

### Interactive Bot (`bot_server.py`)

Long-polling Telegram bot, runs independently from the daily pipeline. Commands:

| Command | Action |
|---|---|
| `/today` | Resend today's full report |
| `/gia` | Today's market snapshot |
| `/tin [category]` | 5 latest articles in category |
| `/cp [TICKER]` | Articles mentioning ticker |
| `/tim [keyword]` | Full-text search, last 7 days |
| `/help` | List all commands |

Run standalone: `python3 bot_server.py`. Suggested crontab: restart at 05:00 daily.

### Google Sheets Layout

One tab per day (`YYYY-MM-DD`). Two regions: world articles (cols A–H) and VN articles (cols J–Q), sorted oldest → newest within each region.

## Key Rules

**Number formatting (Vietnamese standard):** Always use `_fmt_number()` in `report_builder.py`. Dot = thousands separator, comma = decimal. `1750.25` → `1.750,25`. Apply to every number in output.

**All AI output must be in Vietnamese**, including summaries of English articles. The Groq system prompt enforces this. Do not change this behavior.

**Ticker blacklist:** ~50 international abbreviations (USD, GDP, NATO, IMF, WEF, APEC, SWIFT, QE, QT, OMO…) in `ticker_classifier.py:TICKER_BLACKLIST` prevent false ticker detection. Add new ones when false positives appear.

**HTML template:** `template_morning.html` uses `str.format()`. All CSS `{}` must be escaped as `{{}}`. Missing any required key causes a `KeyError` and no HTML is written. Current keys:
```
broker_name, broker_title, broker_tel, broker_tg, logo_html,
date_str, run_date, updated_time, vn_rows, foreign_row, world_rows, commo_rows,
forex_html, crypto_rows, macro_html, corp_section,
outlook_html, ai_html, disclaimer
```

**`_build_macro_bullets_ai` fallback:** Only call `_build_macro_bullets_fallback()` when AI fails entirely — it produces lower-quality keyword-only bullets without Vietnamese translation.

**Stale foreign trading data:** `fetch_foreign_trading()` checks `is_today` against VN timezone. If stale, output must include `⚠️ (dữ liệu chưa cập nhật hôm nay)`.

**SSL verify=False:** Intentional workaround for Python 3.14 Mac cert issues in `v2marketnews.py`. Do not remove.

**launchd constraints (macOS Ventura):** Log files must NOT be in `~/Downloads` (sandbox blocks `xpcproxy`). Python binary must be the real path (e.g. `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14`), not a symlink. Do not set `WorkingDirectory` to `~/Downloads`.

## Credentials & Environment

All secrets in `.env`. Required:
- `GROQ_API_KEY` — Groq AI
- `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` — Telegram channel
- `GOOGLE_SHEETS_ID` / `GOOGLE_SERVICE_ACCOUNT_FILE` — Google Sheets (default: `service_account.json`)

Optional (enhance content enrichment):
- `JINA_API_KEY` — Jina AI reader fallback for paywalled articles
- `GUARDIAN_API_KEY` — The Guardian direct API source

`yfinance` and `vnstock` are not in `requirements.txt` — install separately if needed.

In GitHub Actions, secrets are injected as env vars and `service_account.json` is written from `GCP_SERVICE_ACCOUNT` secret at runtime.

## Groq AI Configuration

- Model: `llama-3.3-70b-versatile`
- Temperature: 0.4 for `generate_market_view`, 0.2 for `summarize_group`
- Response format: `{"type": "json_object"}` for both
- `summarize_all` runs with `max_workers=4`; accepts `mode="morning"|"evening"`
- Retry: 3 attempts, 15s backoff on rate-limit, 5s on other errors
