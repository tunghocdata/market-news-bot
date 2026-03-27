"""
MARKET MORNING BRIEF v8 — Optimized
- VN indices + khối ngoại : 24hmoney API
- Tỷ giá USD/VND          : Yahoo Finance
- Dữ liệu quốc tế         : Yahoo Finance (concurrent)
- AI nhận xét             : Groq (free)

pip install requests
Run:  python b.py           → gửi Telegram
      python b.py --test    → in ra màn hình, KHÔNG gửi
"""

import os
import sys
import logging
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ── Cấu hình (ưu tiên env var, fallback hardcode) ───────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8783760409:AAG2bkbwTAIwC2dels2EJuJ6vsTYaOeR_Bo")
CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID", "8150478108")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "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")

TEST_MODE = "--test" in sys.argv  # python b.py --test → chỉ in, không gửi

# ── HTTP Session với retry ───────────────────────────────────────
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _make_session() -> requests.Session:
    s   = requests.Session()
    ret = Retry(total=2, backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=ret))
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept":     "application/json",
        "Referer":    "https://24hmoney.vn/",
    })
    return s

SESSION = _make_session()

# ── Danh sách tài sản quốc tế ────────────────────────────────────
ASSETS = {
    "🛢 Năng lượng": [
        {"symbol": "CL=F",      "name": "Dầu WTI"     },
        {"symbol": "BZ=F",      "name": "Dầu Brent"   },
        {"symbol": "NG=F",      "name": "Khí tự nhiên"},
    ],
    "🥇 Kim loại & Thép": [
        {"symbol": "GC=F",      "name": "Vàng"        },
        {"symbol": "SI=F",      "name": "Bạc"         },
        {"symbol": "HG=F",      "name": "Đồng"        },
        {"symbol": "HRC=F",     "name": "Thép HRC"    },
    ],
    "🌾 Nông sản": [
        {"symbol": "ZW=F",      "name": "Lúa mì"      },
        {"symbol": "ZC=F",      "name": "Ngô"         },
        {"symbol": "ZS=F",      "name": "Đậu nành"    },
    ],
    "🇺🇸 Mỹ": [
        {"symbol": "^GSPC",     "name": "S&P 500"     },
        {"symbol": "^DJI",      "name": "Dow Jones"   },
        {"symbol": "^IXIC",     "name": "Nasdaq"      },
    ],
    "🇨🇳 Trung Quốc & HK": [
        {"symbol": "000001.SS", "name": "Shanghai"    },
        {"symbol": "^HSI",      "name": "Hang Seng"   },
    ],
    "🌏 Châu Á": [
        {"symbol": "^N225",     "name": "Nikkei 225"  },
        {"symbol": "^KS11",     "name": "KOSPI"       },
    ],
}

# Tổng hợp tất cả symbol quốc tế + tỉ giá (để fetch song song)
ALL_SYMBOLS: list[str] = ["USDVND=X"]
for assets in ASSETS.values():
    for a in assets:
        ALL_SYMBOLS.append(a["symbol"])

# ── 24hmoney: VN indices + khối ngoại ────────────────────────────
def fetch_24hmoney():
    url = (
        "https://api-finance-t19.24hmoney.vn/v1/ios/indices"
        "?device_id=web000000000000000000000000000000"
        "&device_name=INVALID&device_model=macOS"
        "&network_carrier=INVALID&connection_type=INVALID"
        "&os=Chrome&os_version=120.0.0.0"
        "&access_token=INVALID&push_token=INVALID&locale=vi"
        "&browser_id=web000000000000000000000000000000"
    )
    SYMBOL_MAP = {
        "VN-INDEX":   ("VNINDEX", "VN-Index" ),
        "VN30-INDEX": ("VN30",    "VN30"     ),
        "HNX-INDEX":  ("HNX",     "HNX-Index"),
        "UPCOM":      ("UPCOM",   "UPCOM"    ),
    }

    indices: dict = {}
    foreign = None
    buy_total = sell_total = 0.0

    try:
        data  = SESSION.get(url, timeout=12).json()
        items = data["data"]["floor"]

        for item in items:
            sym = item.get("symbol", "").upper()
            if sym not in SYMBOL_MAP:
                continue
            code, _ = SYMBOL_MAP[sym]
            price  = float(item["price"])
            change = float(item["change"])
            prev   = price - change
            pct    = (change / prev * 100) if prev else 0
            indices[code] = {"price": price, "change": change, "pct": pct}

            buy_total  += float(item.get("foreign_today_buy_value",  0))
            sell_total += float(item.get("foreign_today_sell_value", 0))

        if buy_total or sell_total:
            net     = buy_total - sell_total
            foreign = {"buy": buy_total, "sell": sell_total, "net": net}

        log.info("24hmoney OK — %s | KN ròng: %s",
                 list(indices.keys()),
                 f"{foreign['net']:.0f} tỷ" if foreign else "–")
    except Exception as e:
        log.error("24hmoney lỗi: %s", e)

    return indices, foreign

# ── Yahoo Finance (single symbol) ────────────────────────────────
def fetch_quote(symbol: str):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{requests.utils.quote(symbol)}?interval=1d&range=2d"
    )
    try:
        meta   = SESSION.get(url, timeout=12).json()["chart"]["result"][0]["meta"]
        price  = meta["regularMarketPrice"]
        prev   = meta.get("chartPreviousClose") or meta.get("previousClose")
        if not prev:
            return None
        change = price - prev
        pct    = (change / prev) * 100
        return {"price": price, "change": change, "pct": pct}
    except Exception as e:
        log.warning("Yahoo [%s] lỗi: %s", symbol, e)
        return None

# ── Fetch tất cả Yahoo symbols song song ─────────────────────────
def fetch_all_quotes(symbols: list[str], max_workers: int = 8) -> dict:
    """Trả về dict {symbol: quote_or_None}"""
    results: dict = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_quote, s): s for s in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                results[sym] = fut.result()
            except Exception as e:
                log.warning("Yahoo future [%s]: %s", sym, e)
                results[sym] = None
    return results

# ── Format helpers ────────────────────────────────────────────────
def fmt_price(p: float) -> str:
    if p >= 1000: return f"{p:,.2f}"
    if p >= 10:   return f"{p:.2f}"
    return f"{p:.3f}"

def fmt_pct(pct: float) -> str:
    return f"{'+'if pct>=0 else ''}{pct:.2f}%"

def fmt_b(v: float) -> str:
    return f"{'+'if v>=0 else ''}{v:.0f} tỷ"

def badge(pct: float) -> str:
    if pct >= 1:  return "🟢"
    if pct > 0:   return "🔵"
    if pct > -1:  return "🟡"
    return "🔴"

def mood(pct) -> str:
    if pct is None: return "–"
    if pct >= 1:    return "🟢 Tích cực"
    if pct > 0:     return "🔵 Nhích nhẹ"
    if pct > -1:    return "🟡 Rung nhẹ"
    return "🔴 Tiêu cực"

# ── Groq AI ──────────────────────────────────────────────────────
def get_ai_comment(intl: str, vn: str) -> str:
    if not GROQ_API_KEY or GROQ_API_KEY == "PASTE_GROQ_API_KEY_HERE":
        return "_⚠️ Chưa điền GROQ\\_API\\_KEY_"

    prompt = f"""Bạn là chuyên gia phân tích thị trường tài chính với 15 năm kinh nghiệm đầu tư tại Việt Nam.

DỮ LIỆU QUỐC TẾ:
{intl}

DỮ LIỆU VIỆT NAM:
{vn}

Nhận xét tổng quan 4-6 câu theo góc nhìn nhà đầu tư VN:
1. Tâm lý thị trường quốc tế ảnh hưởng thế nào tới VN hôm nay
2. Tín hiệu khối ngoại — cơ hội hay rủi ro?
3. Gợi ý quan sát phiên HOSE hôm nay

Viết tiếng Việt, súc tích, không bullet point, không markdown."""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model":       "llama-3.3-70b-versatile",
                "messages":    [{"role": "user", "content": prompt}],
                "max_tokens":  400,
                "temperature": 0.7,
            },
            timeout=25,
        )
        body = r.json()
        if "error" in body:
            return f"_⚠️ Groq: {body['error'].get('message','')}_"
        return body["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"_AI lỗi: {e}_"

# ── Build message ─────────────────────────────────────────────────
def build_message() -> str:
    now   = datetime.now().strftime("%d/%m/%Y %H:%M")
    lines = ["📊 *MARKET MORNING BRIEF*", f"_{now} · GMT+7_", ""]
    ai_intl, ai_vn = [], []

    # ── Song song: 24hmoney + toàn bộ Yahoo ──────────────────────
    log.info("⏳ Bắt đầu fetch dữ liệu...")
    with ThreadPoolExecutor(max_workers=2) as top:
        fut_vn    = top.submit(fetch_24hmoney)
        fut_intl  = top.submit(fetch_all_quotes, ALL_SYMBOLS)

        vn_indices, foreign = fut_vn.result()
        quotes              = fut_intl.result()   # {symbol: quote}

    log.info("✅ Fetch xong")

    # ── Việt Nam ─────────────────────────────────────────────────
    lines.append("*🇻🇳 Việt Nam*")

    for code, name in [("VNINDEX","VN-Index"),("VN30","VN30"),
                       ("HNX","HNX-Index"),("UPCOM","UPCOM")]:
        q = vn_indices.get(code)
        if not q:
            lines.append(f"⬜ *{name}*   `–`")
            continue
        b   = badge(q["pct"])
        p   = fmt_price(q["price"])
        pct = fmt_pct(q["pct"])
        lines.append(f"{b} *{name}*   `{p}`  `{pct}`")
        ai_vn.append(f"{name}: {p} ({pct})")

    # Tỷ giá
    usd = quotes.get("USDVND=X")
    if usd:
        b   = badge(usd["pct"])
        p   = f"{usd['price']:,.0f}"
        pct = fmt_pct(usd["pct"])
        lines.append(f"{b} *USD/VND*   `{p}`  `{pct}`")
        ai_vn.append(f"USD/VND: {p} ({pct})")
    else:
        lines.append("⬜ *USD/VND*   `–`")

    # Khối ngoại
    if foreign:
        icon = "🟢" if foreign["net"] >= 0 else "🔴"
        lines.append(
            f"{icon} *Khối ngoại*   "
            f"Mua `{foreign['buy']:.0f}B` · Bán `{foreign['sell']:.0f}B` · "
            f"Ròng `{fmt_b(foreign['net'])}`"
        )
        ai_vn.append(
            f"Khối ngoại: Mua {foreign['buy']:.0f}B, "
            f"Bán {foreign['sell']:.0f}B, Ròng {fmt_b(foreign['net'])}"
        )
    else:
        lines.append("⬜ *Khối ngoại*   `–`")

    lines.append("")

    # ── Quốc tế ──────────────────────────────────────────────────
    for group, assets in ASSETS.items():
        lines.append(f"*{group}*")
        for a in assets:
            q = quotes.get(a["symbol"])
            if not q:
                lines.append(f"⬜ *{a['name']}*   `–`")
                continue
            b   = badge(q["pct"])
            p   = fmt_price(q["price"])
            pct = fmt_pct(q["pct"])
            lines.append(f"{b} *{a['name']}*   `{p}`  `{pct}`")
            ai_intl.append(f"{a['name']}: {p} ({pct})")
        lines.append("")

    # ── Nhận định nhanh (tái dùng cache, không fetch lại) ────────
    sp   = quotes.get("^GSPC")
    gold = quotes.get("GC=F")
    oil  = quotes.get("CL=F")
    vni_pct = vn_indices.get("VNINDEX", {}).get("pct")

    lines += [
        "━━━━━━━━━━━━━━━━",
        "*📝 Nhận định nhanh*",
        f"VN-Index · {mood(vni_pct)}",
        f"S&P 500  · {mood(sp['pct']   if sp   else None)}",
        f"Vàng     · {mood(gold['pct'] if gold else None)}",
        f"Dầu WTI  · {mood(oil['pct']  if oil  else None)}",
        "",
    ]

    # ── AI View ──────────────────────────────────────────────────
    log.info("🤖 Đang hỏi Groq AI...")
    ai_comment = get_ai_comment("\n".join(ai_intl), "\n".join(ai_vn))
    lines += [
        "━━━━━━━━━━━━━━━━",
        "*View Chung*",
        ai_comment,
        "",
        "━━━━━━━━━━━━━━━━",
        "🟢 ≥+1%  🔵 0↔+1%  🟡 0↔-1%  🔴 ≤-1%",
        "_Nguồn: Tung Lai Ap Chung suutam - 24hmoney - Yahoo Finance_",
    ]

    return "\n".join(lines)

# ── Send Telegram ─────────────────────────────────────────────────
def send_telegram(text: str):
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    r    = requests.post(url, json=data, timeout=12)
    if r.status_code == 200:
        log.info("✅ Gửi Telegram thành công")
    else:
        log.error("❌ Telegram lỗi %s: %s", r.status_code, r.text)

# ── Main ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    msg = build_message()
    if TEST_MODE:
        print("\n" + "="*50)
        print(msg)
        print("="*50)
        log.info("✅ Test xong — chưa gửi Telegram (dùng --test)")
    else:
        send_telegram(msg)