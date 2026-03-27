"""
morning_run.py – Orchestrator Morning Brief
Chạy: python3 morning_run.py          → scrape + AI + Sheets + Telegram
      python3 morning_run.py --test   → chỉ in ra màn hình, không ghi/gửi
"""

import sys
import json
import logging
from datetime import datetime

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

TEST_MODE = "--test" in sys.argv

from scraper      import fetch_all, deduplicate
from classifier   import classify_morning
from summarizer   import summarize_all
from sheets       import write_to_sheets, get_sheet_url
from telegram_send import send_morning_brief


def run():
    today = datetime.now().strftime("%Y-%m-%d")
    log.info("=" * 60)
    log.info("📰 MORNING BRIEF – %s  [%s]", today, "TEST" if TEST_MODE else "LIVE")
    log.info("=" * 60)

    # ── Bước 1: Thu thập tin ──────────────────────────────────────
    log.info("⏳ Bước 1/4 – Thu thập tin tức (24h)...")
    articles = fetch_all(hours_ago_intl=24, hours_ago_vn=24)
    articles = deduplicate(articles)

    # ── Bước 2: Phân loại ─────────────────────────────────────────
    log.info("🗂 Bước 2/4 – Phân loại %d bài...", len(articles))
    buckets = classify_morning(articles)

    # ── Bước 3: Tóm tắt AI ───────────────────────────────────────
    log.info("🤖 Bước 3/4 – Tóm tắt AI theo nhóm...")
    summaries = summarize_all(buckets, mode="morning")

    # ── Hiển thị preview ─────────────────────────────────────────
    log.info("\n%s", "=" * 60)
    log.info("PREVIEW:")
    for grp, text in summaries.items():
        print(f"\n{text}")
    log.info("=" * 60)

    if TEST_MODE:
        log.info("✅ Test xong — không ghi Sheets / không gửi Telegram.")
        return

    # ── Bước 4: Ghi Sheets + Gửi Telegram ─────────────────────────
    log.info("📊 Bước 4/4 – Ghi Google Sheets + Gửi Telegram...")
    write_to_sheets(articles, buckets, summaries=summaries, session="morning")

    sheet_url = get_sheet_url()
    send_morning_brief(summaries, run_date=today, sheet_url=sheet_url)

    log.info("✅ Morning Brief hoàn tất!")


if __name__ == "__main__":
    run()
