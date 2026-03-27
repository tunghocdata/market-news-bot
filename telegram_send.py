"""
telegram_send.py – Gửi message lên Telegram bot
"""

import logging
import requests
from marketreview import TELEGRAM_TOKEN, CHAT_ID

log = logging.getLogger(__name__)

MAX_MSG_LEN = 4096   # giới hạn Telegram


def _post(text: str):
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown",
            "disable_web_page_preview": True}
    r = requests.post(url, json=data, timeout=12)
    if r.status_code != 200:
        log.error("❌ Telegram %s: %s", r.status_code, r.text[:200])
    return r.status_code == 200


def send(text: str) -> bool:
    """Gửi text, tự cắt nếu quá dài."""
    if len(text) <= MAX_MSG_LEN:
        return _post(text)
    # Cắt thành nhiều phần
    ok = True
    for i in range(0, len(text), MAX_MSG_LEN):
        chunk = text[i:i + MAX_MSG_LEN]
        if not _post(chunk):
            ok = False
    return ok


def send_morning_brief(summaries: dict[str, str], run_date: str,
                       sheet_url: str | None = None):
    """Gửi Morning Brief lên Telegram."""
    lines = [
        f"📰 *MARKET MORNING BRIEF*",
        f"_{run_date} · GMT+7_",
        "",
    ]

    # Quốc tế trước
    intl_order = ["intl_war", "intl_energy", "intl_fed", "intl_global_fin"]
    for grp in intl_order:
        if grp in summaries:
            lines.append(summaries[grp])

    # Trong nước sau
    vn_order = ["vn_rates", "vn_infra", "vn_domestic_fin", "vn_corporate"]
    for grp in vn_order:
        if grp in summaries:
            lines.append(summaries[grp])

    if sheet_url:
        lines += ["━━━━━━━━━━━━━━━━",
                  f"📊 [Xem chi tiết Google Sheets]({sheet_url})"]

    lines.append("_Nguồn: Reuters, FT, Guardian, NYT, CafeF, VnEconomy, VietnamBiz, Vietstock_")
    msg = "\n".join(lines)
    ok  = send(msg)
    if ok:
        log.info("✅ Gửi Morning Brief Telegram thành công")
    return ok


def send_evening_recap(summaries: dict[str, str], run_date: str,
                       sheet_url: str | None = None):
    """Gửi Evening Recap lên Telegram."""
    lines = [
        f"🌇 *MARKET EVENING RECAP*",
        f"_{run_date} · GMT+7_",
        "",
    ]

    order = ["vn_market", "vn_rates", "vn_infra", "vn_corporate",
             "intl_war", "intl_energy_rates"]
    for grp in order:
        if grp in summaries:
            lines.append(summaries[grp])

    if sheet_url:
        lines += ["━━━━━━━━━━━━━━━━",
                  f"📊 [Xem chi tiết Google Sheets]({sheet_url})"]

    lines.append("_Nguồn: CafeF, VnEconomy, VietnamBiz, Vietstock, Reuters, FT_")
    msg = "\n".join(lines)
    ok  = send(msg)
    if ok:
        log.info("✅ Gửi Evening Recap Telegram thành công")
    return ok
