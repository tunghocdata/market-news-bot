from __future__ import annotations
"""
report_builder.py – Build HTML report (BSC-style) và Telegram message (mobile-friendly)
cho bản tin sáng tunglaiapchung.
"""

import os
import logging
import requests
from datetime import datetime, timezone, timedelta

from marketreview import (
    BROKER_NAME, BROKER_TITLE, BROKER_TELEGRAM, BROKER_PHONE,
    BROKER_LOGO, DISCLAIMER_VN,
    TELEGRAM_TOKEN, CHAT_ID, REPORT_URL,
)

log = logging.getLogger(__name__)

_VN_TZ = timezone(timedelta(hours=7))
_WEEKDAY_VN = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_vn() -> datetime:
    return datetime.now(_VN_TZ)


def _is_trading_day(dt: datetime) -> bool:
    """Trả về False nếu là thứ Bảy hoặc Chủ Nhật."""
    return dt.weekday() < 5  # 0=Thứ Hai … 4=Thứ Sáu


def _fmt_change(chg, decimals=2) -> str:
    """Format % thay đổi với dấu + / -"""
    if chg is None:
        return "—"
    sign = "+" if chg > 0 else ""
    return f"{sign}{chg:.{decimals}f}%"


def _change_class(chg) -> str:
    """CSS class cho giá tăng/giảm"""
    if chg is None:
        return "neutral"
    return "up" if chg > 0 else ("down" if chg < 0 else "neutral")


def _fmt_number(val, decimals=2) -> str:
    """Format số theo chuẩn VN: dấu chấm ngăn nghìn, dấu phẩy thập phân.
    Ví dụ: 1750.25 → '1.750,25' | 73540 (decimals=0) → '73.540'
    """
    if val is None:
        return "\u2014"
    try:
        f = float(val)
        import math
        if math.isnan(f) or math.isinf(f):
            return "\u2014"
        if f >= 1000:
            if decimals == 0:
                return f"{f:,.0f}".replace(",", ".")
            formatted = f"{f:,.{decimals}f}"
            dot_pos   = formatted.rfind(".")
            int_str   = formatted[:dot_pos].replace(",", ".")
            dec_str   = formatted[dot_pos + 1:]
            return f"{int_str},{dec_str}"
        if decimals == 0:
            return str(int(round(f)))
        return f"{f:.{decimals}f}".replace(".", ",")
    except (ValueError, TypeError):
        return str(val)


def _arrow(chg) -> str:
    if chg is None:
        return "─"
    return "▲" if chg > 0 else ("▼" if chg < 0 else "─")


# ─────────────────────────────────────────────────────────────────────────────
# Build HTML Report (BSC-style, 2-column)
# ─────────────────────────────────────────────────────────────────────────────

def build_html_report(
    market_data: dict,
    summaries: dict,
    corp_news_html: str = "",
    macro_bullets: list[str] | None = None,
    run_date: str | None = None,
    articles: list[dict] | None = None,  # kept for API compatibility, unused
) -> str:
    """
    Trả về chuỗi HTML đầy đủ theo layout BSC Morning Brief.
    market_data: output từ morning_brief.py (vn, world, commodities, crypto, forex, foreign)
    summaries: dict {group: text} từ summarizer.py
    corp_news_html: HTML fragment từ ticker_classifier.format_corporate_for_telegram
    macro_bullets: list string cho tin vĩ mô nổi bật
    """
    now = _now_vn()
    if not run_date:
        run_date = now.strftime("%d/%m/%Y")

    weekday = _WEEKDAY_VN[now.weekday()]
    date_str = f"{weekday}, ngày {run_date}"

    # ── Logo ──────────────────────────────────────────────────────────────────
    logo_path = os.path.join(BASE_DIR, BROKER_LOGO)
    if os.path.exists(logo_path):
        logo_html = f'<img src="{BROKER_LOGO}" alt="{BROKER_NAME}" class="logo">'
    else:
        logo_html = f'<div class="logo-placeholder">{BROKER_NAME.upper()}</div>'

    # ── VN Market table ───────────────────────────────────────────────────────
    vn_data   = market_data.get("vn", {})
    foreign   = market_data.get("foreign", {})
    vn_rows   = _build_index_table_rows(vn_data)

    foreign_html = ""
    if foreign.get("net") is not None and foreign["net"] != 0:
        net       = foreign["net"]
        net_cls   = "up" if net > 0 else "down"
        net_label = "MUA R\u00d2NG" if net > 0 else "B\xc1N R\u00d2NG"
        net_abs   = f"{abs(net):,.1f} t\u1ef7"
        upd_note  = f' <span class="note">({foreign["updated_at"]})</span>' if foreign.get("updated_at") else ""
        stale_warn = ' <span class="warn">\u26a0\ufe0f Stale</span>' if not foreign.get("is_today") else ""
        foreign_html = (
            f'<tr class="foreign-row">'
            f'<td>KN n\u01b0\u1edbc ngo\u00e0i</td>'
            f'<td class="{net_cls}">{net_label} {net_abs}</td>'
            f'<td class="note">{upd_note}{stale_warn}</td>'
            f'</tr>'
        )

    # ── World markets table ───────────────────────────────────────────────────
    world_rows = _build_world_table_rows(market_data.get("world", []))

    # ── Commodities table ─────────────────────────────────────────────────────
    commo_rows = _build_commodity_table_rows(market_data.get("commodities", []))

    # ── Forex + Crypto ────────────────────────────────────────────────────────
    forex_html  = _build_forex_html(market_data.get("forex", {}))
    crypto_rows = _build_crypto_table_rows(market_data.get("crypto", []))

    # ── Macro bullets ─────────────────────────────────────────────────────────
    macro_html = _build_macro_html(summaries, macro_bullets)

    # ── Corp news ──────────────────────────────────────────────────────────────
    corp_html_section = ""
    if corp_news_html:
        corp_html_section = f"""
        <div class="section-gap corporate-section">
          <div class="section-title">Tin th&#7883; tr&#432;&#7901;ng</div>
          <div class="corp-list">{corp_news_html}</div>
        </div>"""

    # ── AI Section ────────────────────────────────────────────────────────────
    ai_html      = _build_ai_html(summaries)
    outlook_html = _build_outlook_html(summaries)

    # ── Updated time ──────────────────────────────────────────────────────────
    updated_time = _now_vn().strftime("%H:%M")

    # ── Read template ─────────────────────────────────────────────────────────
    with open(os.path.join(BASE_DIR, "template_morning.html"), encoding="utf-8") as f:
        template = f.read()

    return template.format(
        broker_name       = BROKER_NAME,
        broker_title      = BROKER_TITLE,
        broker_tel        = BROKER_PHONE,
        broker_tg         = BROKER_TELEGRAM,
        logo_html         = logo_html,
        date_str          = date_str,
        run_date          = run_date,
        updated_time      = updated_time,
        vn_rows           = vn_rows,
        foreign_row       = foreign_html,
        world_rows        = world_rows,
        commo_rows        = commo_rows,
        forex_html        = forex_html,
        crypto_rows       = crypto_rows,
        macro_html        = macro_html,
        corp_section      = corp_html_section,
        outlook_html      = outlook_html,
        ai_html           = ai_html,
        disclaimer        = DISCLAIMER_VN,
    )


# ─────────────────────────────────────────────────────────────────────────────
# HTML fragment builders
# ─────────────────────────────────────────────────────────────────────────────

_CAT_LABEL = {
    "chung_khoan":  "Chứng khoán",  "tai_chinh":   "Tài chính",
    "doanh_nghiep": "Doanh nghiệp", "bat_dong_san": "BĐS",
    "hang_hoa":     "Hàng hóa",    "vi_mo":        "Vĩ mô",
    "thi_truong":   "Thị trường",  "the_gioi":     "Thế giới",
    "phan_tich":    "Phân tích",   "markets":      "Markets",
}


def _build_top_articles_html(articles: list[dict], vn_count: int = 6, intl_count: int = 4) -> str:
    """Top bài đọc hôm nay — VN trước, INTL sau, có link về nguồn gốc."""
    if not articles:
        return ""

    def _pub_dt(a: dict):
        pub = a.get("published") or a.get("datetime") or ""
        try:
            from datetime import datetime, timezone, timedelta
            dt = datetime.fromisoformat(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone(timedelta(hours=7)))
            return dt
        except Exception:
            return None

    def _fmt_time(a: dict) -> str:
        dt = _pub_dt(a)
        if dt:
            return dt.astimezone(_VN_TZ).strftime("%H:%M")
        return ""

    sorted_arts = sorted(
        [a for a in articles if a.get("url")],
        key=lambda a: _pub_dt(a) or _now_vn().replace(hour=0),
        reverse=True,
    )
    vn   = [a for a in sorted_arts if a.get("region") == "vn"][:vn_count]
    intl = [a for a in sorted_arts if a.get("region") != "vn"][:intl_count]
    top  = vn + intl

    if not top:
        return ""

    rows = []
    for a in top:
        t     = _fmt_time(a)
        cat   = _CAT_LABEL.get(a.get("category", ""), a.get("category", ""))
        title = (a.get("title") or "").strip()[:90]
        url   = a.get("url", "")
        src   = a.get("source", "")
        rows.append(
            f'<div class="top-article-row">'
            f'<span class="art-time">{t}</span>'
            f'<span class="art-cat">{cat}</span>'
            f'<span class="art-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></span>'
            f'<span class="art-src">— {src}</span>'
            f'</div>'
        )

    return (
        '<div class="section-gap">'
        '<div class="section-title">Top bài đọc hôm nay</div>'
        + "".join(rows)
        + "</div>"
    )


def _build_index_table_rows(vn_data: dict) -> str:
    ORDER = ["VN-Index", "VN30", "HNX-Index", "UPCOM"]
    rows = []
    for name in ORDER:
        item = vn_data.get(name)
        if not item:
            continue
        val = _fmt_number(item.get("value"))
        chg = item.get("change")
        cls = _change_class(chg)
        chg_str = _fmt_change(chg)
        rows.append(
            f'<tr>'
            f'<td>{name}</td>'
            f'<td class="val">{val}</td>'
            f'<td class="{cls}">{chg_str}</td>'
            f'</tr>'
        )
    return "\n".join(rows) if rows else "<tr><td colspan='3'>Kh&#244;ng c&#243; d&#7919; li&#7879;u</td></tr>"


def _build_world_table_rows(world: list) -> str:
    rows = []
    for item in world:
        flag = item.get("flag", "")
        name = item.get("name", "")
        val  = item.get("value")
        chg  = item.get("change")
        # Bỏ qua dòng không có data hoặc nan
        if val is None:
            continue
        try:
            if str(float(val)) == 'nan':
                continue
        except (ValueError, TypeError):
            pass
        cls  = _change_class(chg)
        chg_str = _fmt_change(chg)
        rows.append(
            f'<tr>'
            f'<td>{flag} {name}</td>'
            f'<td class="val">{_fmt_number(val)}</td>'
            f'<td class="{cls}">{chg_str}</td>'
            f'</tr>'
        )
    return "\n".join(rows) if rows else "<tr><td colspan='3'>Kh&#244;ng c&#243; d&#7919; li&#7879;u</td></tr>"


def _build_commodity_table_rows(commodities: list) -> str:
    rows = []
    for item in commodities:
        icon = item.get("icon", "")
        name = item.get("name", "")
        val  = _fmt_number(item.get("value"), decimals=1)
        chg  = item.get("change")
        cls  = _change_class(chg)
        chg_str = _fmt_change(chg)
        rows.append(
            f'<tr>'
            f'<td>{icon} {name}</td>'
            f'<td class="val">{val}</td>'
            f'<td class="{cls}">{chg_str}</td>'
            f'</tr>'
        )
    return "\n".join(rows) if rows else "<tr><td colspan='3'>Kh&#244;ng c&#243; d&#7919; li&#7879;u</td></tr>"


def _build_crypto_table_rows(crypto: list) -> str:
    rows = []
    for item in crypto:
        icon   = item.get("icon", "")
        name   = item.get("name", "")
        symbol = item.get("symbol", "")
        val    = f"${_fmt_number(item.get('value'), decimals=0)}"
        chg    = item.get("change")
        cls    = _change_class(chg)
        chg_str = _fmt_change(chg)
        rows.append(
            f'<tr>'
            f'<td>{icon} {name} <span class="sym">({symbol})</span></td>'
            f'<td class="val">{val}</td>'
            f'<td class="{cls}">{chg_str}</td>'
            f'</tr>'
        )
    return "\n".join(rows) if rows else ""


def _build_forex_html(forex: dict) -> str:
    usd = forex.get("usd_vnd", {})
    if not usd or not usd.get("value"):
        return ""
    val = _fmt_number(usd["value"], decimals=0)
    src = usd.get("source", "")
    return (f'<tr><td>&#x1F1FB;&#x1F1F3; USD/VND</td>'
            f'<td class="val">{val}</td>'
            f'<td class="neutral"><small>({src})</small></td></tr>')


def _build_macro_html(summaries: dict, bullets: list | None) -> str:
    """Build phần tin vĩ mô: ưu tiên bullets rõ ràng, fallback sang summaries."""
    html_parts = []

    if bullets:
        html_parts.append('<ul class="macro-list">')
        for b in bullets:
            tag  = '<span class="tag-qt">QT</span>' if b.startswith("[QT]") else '<span class="tag-vn">VN</span>'
            text = b.replace("[QT]", "").replace("[VN]", "").strip()
            # Rút ngắn nếu quá dài (tránh wrap nhiều dòng)
            if len(text) > 110:
                text = text[:107] + "…"
            html_parts.append(
                f'<li><span class="bullet">&bull;</span>{tag} {text}</li>'
            )
        html_parts.append("</ul>")
        return "\n".join(html_parts)

    # Fallback: lấy từ summaries nếu không có bullets
    MACRO_GROUPS = ["intl_war", "intl_energy", "intl_fed", "intl_global_fin",
                    "vn_rates", "vn_infra", "vn_domestic_fin", "vn_corporate"]
    for grp in MACRO_GROUPS:
        if grp in summaries:
            text = summaries[grp].strip()
            if text and "Kh&#244;ng c&#243; tin m&#7899;i" not in text and "Không có tin mới" not in text:
                html_parts.append(f'<div class="macro-group">{_escape_html(text)}</div>')
    return "\n".join(html_parts) if html_parts else "<p>&#272;ang c&#7853;p nh&#7853;t...</p>"


def _build_ai_html(summaries: dict) -> str:
    """Tạo phần nhận định AI từ summaries groq — clean markdown symbols."""
    import re
    lines_out = []

    # 1. Market view narrative — render trước, bỏ dòng tiêu đề thừa
    ai_text = (summaries.get("ai_insights") or "").strip()
    if ai_text:
        filtered = [l for l in ai_text.split("\n") if "NHẬN ĐỊNH AI" not in l and l.strip()]
        if filtered:
            cleaned = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', "\n".join(filtered))
            lines_out.append(
                f'<div class="ai-block" style="border-left-color:#80cbc4;background:rgba(255,255,255,.12)">'
                f'{_escape_html_clean(cleaned)}</div>'
            )

    # 2. Per-group AI sentiment — bỏ qua error và nhóm không có tin
    GROUP_ORDER = [
        "intl_war", "intl_energy", "intl_fed", "intl_global_fin",
        "vn_rates", "vn_infra", "vn_domestic_fin", "vn_corporate",
    ]
    for grp in GROUP_ORDER:
        text = (summaries.get(grp) or "").strip()
        if not text or "Không có tin mới" in text or "\u26a0\ufe0f" in text:
            continue
        cleaned = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        cleaned = re.sub(r'\*(.+?)\*',     r'<i>\1</i>', cleaned)
        lines_out.append(f'<div class="ai-block">{_escape_html_clean(cleaned)}</div>')

    if not lines_out:
        return "<p style='color:#e0f2f1'>AI &#273;ang ph&#226;n t&#237;ch...</p>"
    return "\n".join(lines_out)


def _escape_html_clean(text: str) -> str:
    """Escape HTML nhưng giữ lại <b> và <i> tags đã được xử lý sẵn."""
    # Tạm thời thay các tag HTML đã có
    text = text.replace("<b>", "\x00B\x00").replace("</b>", "\x00/B\x00")
    text = text.replace("<i>", "\x00I\x00").replace("</i>", "\x00/I\x00")
    # Escape phần còn lại
    text = (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>"))
    # Phục hồi tags
    text = text.replace("\x00B\x00", "<b>").replace("\x00/B\x00", "</b>")
    text = text.replace("\x00I\x00", "<i>").replace("\x00/I\x00", "</i>")
    return text


def _escape_html(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>"))


def _build_outlook_html(summaries: dict) -> str:
    """
    Build outlook cards từ ai_insights (bias, vn_outlook, risk).
    Điền vào {outlook_html} trong template — hiển thị dưới cột tin tức.
    """
    ai_text = (summaries.get("ai_insights") or "").strip()
    if not ai_text:
        return ""

    bias_line = vn_line = risk_line = ""
    for line in ai_text.split("\n"):
        if "▸ Bias:" in line:
            bias_line = line.replace("▸ Bias:", "").strip()
        elif "▸ VN hôm nay:" in line:
            vn_line = line.replace("▸ VN hôm nay:", "").strip()
        elif "▸ Rủi ro:" in line:
            risk_line = line.replace("▸ Rủi ro:", "").strip()

    if not (bias_line or vn_line or risk_line):
        return ""

    bu = bias_line.upper()
    sent_cls = "oc-pos" if "TÍCH CỰC" in bu else ("oc-neg" if "THẬN TRỌNG" in bu else "oc-neu")

    cards = []
    if bias_line:
        cards.append(
            f'<div class="outlook-card">'
            f'<div class="oc-label">Bias hôm nay</div>'
            f'<div class="oc-sentiment {sent_cls}">{_escape_html(bias_line)}</div>'
            f'</div>'
        )
    if vn_line:
        cards.append(
            f'<div class="outlook-card">'
            f'<div class="oc-label">VN-Index outlook</div>'
            f'<div class="oc-note">{_escape_html(vn_line)}</div>'
            f'</div>'
        )
    if risk_line:
        cards.append(
            f'<div class="outlook-card">'
            f'<div class="oc-label">&#9888;&#65039; Rủi ro cần theo dõi</div>'
            f'<div class="oc-note">{_escape_html(risk_line)}</div>'
            f'</div>'
        )

    if not cards:
        return ""
    return (
        '<div class="section-gap">'
        '<div class="section-title">Nhận định nhanh</div>'
        f'<div class="outlook-grid">{"".join(cards)}</div>'
        '</div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Build Telegram Message (Mobile-Friendly)
# ─────────────────────────────────────────────────────────────────────────────

def build_telegram_msg(
    market_data: dict,
    summaries: dict,
    corp_news_text: str = "",
    macro_bullets: list[str] | None = None,
    run_date: str | None = None,
) -> str:
    """
    Tạo tin nhắn Telegram HTML parse_mode, mobile-friendly.
    Dùng HTML tags: <b>, <i>, <code> (KHÔNG dùng Markdown dễ lỗi trên mobile).
    """
    now = _now_vn()
    if not run_date:
        run_date = now.strftime("%d/%m/%Y")
    weekday = _WEEKDAY_VN[now.weekday()]

    parts = []

    # ── Header ────────────────────────────────────────────────────────────────
    parts.append(
        f"📰 <b>BẢN TIN SÁNG</b> | <b>{BROKER_NAME}</b>\n"
        f"📅 {weekday}, {run_date} — {now.strftime('%H:%M')}\n"
        f"{'━' * 22}"
    )

    # ── Disclaimer ngày nghỉ ──────────────────────────────────────────────────
    if not _is_trading_day(now):
        parts.append(
            f"⚠️ <i>Hôm nay {weekday} — HOSE/HNX nghỉ giao dịch.</i>\n"
            f"<i>Số liệu chứng khoán VN từ phiên gần nhất (thứ Sáu).</i>"
        )

    # ── VN Market ─────────────────────────────────────────────────────────────
    vn = market_data.get("vn", {})
    foreign = market_data.get("foreign", {})
    if vn:
        parts.append("\n🇻🇳 <b>CHỨNG KHOÁN VIỆT NAM</b>")
        for name in ["VN-Index", "VN30", "HNX-Index", "UPCOM"]:
            item = vn.get(name)
            if not item:
                continue
            val  = _fmt_number(item.get("value"))
            chg  = item.get("change")
            icon = "🟢" if (chg or 0) > 0 else ("🔴" if (chg or 0) < 0 else "⚪")
            parts.append(f"{icon} {name}: <b>{val}</b> ({_fmt_change(chg)})")

        # Khối ngoại
        if foreign.get("net") is not None and foreign["net"] != 0:
            net = foreign["net"]
            net_icon  = "🟢" if net > 0 else "🔴"
            net_label = "Mua ròng" if net > 0 else "Bán ròng"
            upd = f" <i>({foreign['updated_at']})</i>" if foreign.get("updated_at") else ""
            stale = " ⚠️ <i>(dữ liệu chưa cập nhật hôm nay)</i>" if not foreign.get("is_today") else ""
            net_fmt = f"{abs(net):,.1f}".replace(",", ".")
            parts.append(f"🌍 Khối ngoại: {net_icon} {net_label} {net_fmt} tỷ{upd}{stale}")

    # ── World Markets ─────────────────────────────────────────────────────────
    world = market_data.get("world", [])
    if world:
        parts.append(f"\n{'━' * 22}\n🌐 <b>CHỨNG KHOÁN THẾ GIỚI</b>")
        for item in world:
            flag = item.get("flag", "")
            name = item.get("name", "")
            val  = _fmt_number(item.get("value"))
            chg  = item.get("change")
            icon = "🟢" if (chg or 0) > 0 else ("🔴" if (chg or 0) < 0 else "⚪")
            parts.append(f"{icon} {flag} {name}: <b>{val}</b> ({_fmt_change(chg)})")

    # ── Commodities + Forex ────────────────────────────────────────────────────
    commo  = market_data.get("commodities", [])
    forex  = market_data.get("forex", {})
    crypto = market_data.get("crypto", [])

    if commo or forex or crypto:
        parts.append(f"\n{'━' * 22}\n🛢️ <b>HÀNG HÓA &amp; TỶ GIÁ</b>")

        # USD/VND
        usd = forex.get("usd_vnd", {})
        if usd and usd.get("value"):
            parts.append(f"💵 USD/VND: <b>{_fmt_number(usd['value'], decimals=0)}</b> ({usd.get('source','')})")

        # Hàng hóa chọn lọc
        PRIORITY = ["Vàng", "Dầu Brent", "Dầu WTI", "Thép HRC", "Khí tự nhiên"]
        shown = set()
        for name in PRIORITY:
            for item in commo:
                if item["name"] == name and name not in shown:
                    icon = item.get("icon", "")
                    val  = _fmt_number(item.get("value"), decimals=1)
                    chg  = item.get("change")
                    tick = "🟢" if (chg or 0) > 0 else ("🔴" if (chg or 0) < 0 else "⚪")
                    parts.append(f"{tick} {icon} {name}: <b>{val}</b> ({_fmt_change(chg)})")
                    shown.add(name)

        # Crypto
        for item in crypto:
            icon   = item.get("icon", "")
            name   = item.get("name", "")
            symbol = item.get("symbol", "")
            val    = f"${_fmt_number(item.get('value'), decimals=0)}"
            chg    = item.get("change")
            tick   = "🟢" if (chg or 0) > 0 else ("🔴" if (chg or 0) < 0 else "⚪")
            parts.append(f"{tick} {icon} {name} ({symbol}): <b>{val}</b> ({_fmt_change(chg)})")

    # ── Vĩ mô ─────────────────────────────────────────────────────────────────
    if macro_bullets:
        parts.append(f"\n{'━' * 22}\n📌 <b>TIN VĨ MÔ QUAN TRỌNG</b>")
        for b in macro_bullets[:8]:
            parts.append(f"• {b}")

    # ── Tin doanh nghiệp ───────────────────────────────────────────────────────
    if corp_news_text.strip():
        parts.append(f"\n{'━' * 22}\n🏢 <b>TIN DOANH NGHIỆP</b>")
        parts.append(corp_news_text)

    # ── AI nhận định ──────────────────────────────────────────────────────────
    ai_blocks = _extract_ai_insights(summaries)
    if ai_blocks:
        parts.append(f"\n{'━' * 22}\n🤖 <b>NHẬN ĐỊNH AI</b>")
        for block in ai_blocks:
            parts.append(block)

    # ── Footer ────────────────────────────────────────────────────────────────
    parts.append(
        f"\n{'━' * 22}\n"
        f"<i>{DISCLAIMER_VN}</i>\n"
        f"📲 {BROKER_TELEGRAM}"
    )

    return "\n".join(parts)


def _extract_ai_insights(summaries: dict) -> list[str]:
    """
    Hiển thị phần nhận định AI trong Telegram:
    1. Groq market view (ai_insights key) — narrative tổng thể
    2. Divider
    3. Per-group AI sentiment analysis (tất cả các nhóm)
    """
    import re
    blocks = []

    # 1. Groq market view narrative
    ai_text = (summaries.get("ai_insights") or "").strip()
    if ai_text and "error" not in ai_text.lower():
        lines = [l for l in ai_text.split("\n") if l.strip() and "NHẬN ĐỊNH AI" not in l]
        if lines:
            blocks.append("\n".join(lines))

    # 2. Per-group AI sentiment — tất cả nhóm theo thứ tự
    GROUP_ORDER = [
        "intl_war", "intl_energy", "intl_fed", "intl_global_fin",
        "vn_rates", "vn_infra", "vn_domestic_fin", "vn_corporate",
    ]
    group_blocks = []
    for grp in GROUP_ORDER:
        text = (summaries.get(grp) or "").strip()
        if not text or "Không có tin mới" in text or "⚠️" in text:
            continue
        # Convert **bold** → <b>bold</b> cho Telegram HTML mode
        rendered = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        group_blocks.append(rendered)

    if group_blocks:
        blocks.append("<i>── Phân tích chi tiết theo nhóm ──</i>")
        blocks.extend(group_blocks)

    return blocks


# ─────────────────────────────────────────────────────────────────────────────
# Save Report
# ─────────────────────────────────────────────────────────────────────────────

def save_html_report(html_content: str, filename: str | None = None) -> str:
    """Lưu HTML report ra file (không lưu theo ngày, chỉ ghi đè morning-brief.html)."""
    if not filename:
        filename = os.path.join(BASE_DIR, "morning-brief.html")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    log.info("✅ Đã lưu HTML report: %s", filename)
    return filename


# ─────────────────────────────────────────────────────────────────────────────
# Telegram Send
# ─────────────────────────────────────────────────────────────────────────────

_MAX_MSG_LEN = 4096


def _tg_post(text: str, parse_mode: str = "HTML") -> bool:
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id":                  CHAT_ID,
        "text":                     text,
        "parse_mode":               parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=data, timeout=15)
        if r.status_code != 200:
            log.error("❌ Telegram %s: %s", r.status_code, r.text[:300])
            return False
        return True
    except Exception as e:
        log.error("❌ Telegram exception: %s", e)
        return False


def send(text: str, parse_mode: str = "HTML") -> bool:
    """Gửi text lên Telegram, tự cắt nếu quá 4096 ký tự."""
    if len(text) <= _MAX_MSG_LEN:
        return _tg_post(text, parse_mode)

    ok, current, chunks = True, "", []
    for line in text.split("\n"):
        candidate = current + ("\n" if current else "") + line
        if len(candidate) > _MAX_MSG_LEN - 100:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)

    for chunk in chunks:
        if not _tg_post(chunk, parse_mode):
            ok = False
    return ok


def generate_report_screenshot(html_path: str) -> str | None:
    """Render morning-brief.html → PNG full-page. Trả về path ảnh hoặc None nếu lỗi."""
    try:
        from playwright.sync_api import sync_playwright
        img_path = html_path.replace(".html", ".png")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page    = browser.new_page(viewport={"width": 794, "height": 1123})
            page.goto(f"file://{html_path}")
            page.wait_for_load_state("networkidle", timeout=10_000)
            page.screenshot(path=img_path, full_page=True)
            browser.close()
        log.info("📸 Screenshot: %s", img_path)
        return img_path
    except Exception as e:
        log.warning("⚠️ Screenshot lỗi: %s", e)
        return None


def send_report_image(img_path: str, caption: str) -> bool:
    """Gửi ảnh PNG báo cáo qua Telegram sendPhoto."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with open(img_path, "rb") as f:
            r = requests.post(
                url,
                data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                files={"photo": f},
                timeout=60,
            )
        if r.status_code != 200:
            log.error("❌ sendPhoto %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:
        log.error("❌ sendPhoto exception: %s", e)
        return False


def send_morning_brief(
    market_data: dict,
    summaries: dict,
    corp_news_text: str = "",
    macro_bullets: list | None = None,
    run_date: str | None = None,
    sheet_url: str | None = None,
    html_path: str | None = None,
) -> bool:
    """Gửi Morning Brief lên Telegram.
    Nếu html_path được truyền: gửi ảnh PNG (screenshot) + caption ngắn.
    Fallback: gửi text đầy đủ như cũ.
    """
    date_str = run_date or _now_vn().strftime("%d/%m/%Y")
    caption_parts = [f"📰 <b>Bản tin sáng {date_str}</b> — {BROKER_NAME}"]
    if sheet_url:
        caption_parts.append(f'📊 <a href="{sheet_url}">Google Sheets</a>')
    if REPORT_URL:
        caption_parts.append(f'🌐 <a href="{REPORT_URL}">Xem online</a>')
    caption = "\n".join(caption_parts)

    # Thử gửi ảnh trước
    if html_path and os.path.exists(html_path):
        img_path = generate_report_screenshot(html_path)
        if img_path and os.path.exists(img_path):
            ok = send_report_image(img_path, caption)
            if ok:
                log.info("✅ Gửi Morning Brief (ảnh) Telegram thành công")
                return True
            log.warning("⚠️ Gửi ảnh thất bại — fallback sang text")

    # Fallback: text đầy đủ
    msg = build_telegram_msg(
        market_data    = market_data,
        summaries      = summaries,
        corp_news_text = corp_news_text,
        macro_bullets  = macro_bullets,
        run_date       = run_date,
    )
    if sheet_url:
        msg += f'\n\n📊 <a href="{sheet_url}">Xem chi tiết Google Sheets</a>'
    if REPORT_URL:
        msg += f'\n🌐 <a href="{REPORT_URL}">Xem báo cáo đầy đủ</a>'

    ok = send(msg, parse_mode="HTML")
    if ok:
        log.info("✅ Gửi Morning Brief (text) Telegram thành công")
    else:
        log.error("❌ Gửi Telegram thất bại")
    return ok


def send_run1_preview(
    article_count: int,
    buckets: dict,
    market_data: dict,
    run_date: str,
    sheet_url: str | None = None,
) -> bool:
    """Gửi preview ngắn sau Run1 (06:00) để xác nhận pipeline không lỗi."""
    BUCKET_LABELS = {
        "intl_war":        "🌍 Địa chính trị",
        "intl_energy":     "⚡ Năng lượng",
        "intl_fed":        "🏦 FED/NHTW",
        "intl_global_fin": "📈 Thị trường QT",
        "vn_rates":        "🏛 Lãi suất VN",
        "vn_infra":        "🏗 Hạ tầng VN",
        "vn_domestic_fin": "📊 Vĩ mô VN",
        "vn_corporate":    "🏢 Doanh nghiệp",
    }
    bucket_lines = []
    total_classified = 0
    for key, label in BUCKET_LABELS.items():
        count = len(buckets.get(key, []))
        if count > 0:
            total_classified += count
            bucket_lines.append(f"  {label}: <b>{count}</b> bài")

    vn_line = ""
    try:
        vn    = market_data.get("vn", {})
        vnidx = vn.get("VN-Index") or vn.get("VNINDEX") or {}
        price = vnidx.get("price") or vnidx.get("close", 0)
        chg   = vnidx.get("change_pct") or vnidx.get("pct_change", 0)
        if price:
            arrow = "🟢" if float(chg or 0) >= 0 else "🔴"
            sign  = "+" if float(chg or 0) >= 0 else ""
            vn_line = f"\n🇻🇳 VN-Index: <b>{price:,.2f}</b> {arrow} {sign}{chg}%"
    except Exception:
        pass

    lines = [
        f"⏱ <b>RUN1 HOÀN TẤT</b> — {run_date} · 06:00",
        "",
        f"📰 Thu thập: <b>{article_count}</b> bài (8h qua đêm)",
        f"🗂 Phân loại: <b>{total_classified}</b> bài vào {len(bucket_lines)} nhóm",
    ]
    if bucket_lines:
        lines += bucket_lines
    if vn_line:
        lines.append(vn_line)
    lines += [
        "",
        "⏳ Báo cáo đầy đủ sẽ gửi lúc <b>09:15</b> (merge + AI + Telegram).",
    ]
    if sheet_url:
        lines.append(f'📊 <a href="{sheet_url}">Xem Sheets bản nháp</a>')
    if REPORT_URL:
        lines.append(f'🌐 <a href="{REPORT_URL}">Xem báo cáo đầy đủ</a>')

    ok = send("\n".join(lines), parse_mode="HTML")
    if ok:
        log.info("✅ Gửi Run1 preview Telegram thành công")
    else:
        log.error("❌ Gửi Run1 preview thất bại")
    return ok
