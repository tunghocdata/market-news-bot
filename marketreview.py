"""
marketreview.py – Config tập trung cho Morning Brief News + Evening Recap
Chỉnh sửa các giá trị bên dưới theo thông tin của bạn.
"""

import os

# ── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8783760409:AAG2bkbwTAIwC2dels2EJuJ6vsTYaOeR_Bo")
CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID", "8150478108")

# ── Groq AI ───────────────────────────────────────────────────────────────────
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "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")
GROQ_MODEL     = "llama-3.3-70b-versatile"

# ── Google Sheets ─────────────────────────────────────────────────────────────
# Tạo Google Sheet, share cho email của Service Account, lấy ID từ URL
GOOGLE_SHEETS_ID          = os.getenv("GOOGLE_SHEETS_ID", "1z07pF8EDv6Q5vN5QvdNz7NhZxTRSfjxd1QKyFuzTts8")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    "/Users/chinh/Downloads/Code/Antigravity/Tintuc/service_account.json"   # <-- đặt file JSON ở đây
)

# ── Nguồn tin quốc tế (RSS) ───────────────────────────────────────────────────
INTL_RSS_SOURCES = [
    # ✅ Reuters + Bloomberg qua Google News RSS (bypass anti-bot/paywall)
    {"name": "Reuters – World",    "url": "https://news.google.com/rss/search?q=site:reuters.com+world+OR+economy&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Reuters – Markets",  "url": "https://news.google.com/rss/search?q=site:reuters.com+markets+OR+finance&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Bloomberg – Asia",   "url": "https://news.google.com/rss/search?q=site:bloomberg.com+asia+OR+markets&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Bloomberg – World",  "url": "https://news.google.com/rss/search?q=site:bloomberg.com+economy+OR+finance&hl=en-US&gl=US&ceid=US:en"},
    # ✅ Trực tiếp
    {"name": "NYT – World",        "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
    {"name": "NYT – Business",     "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"},
    {"name": "Guardian – World",   "url": "https://www.theguardian.com/world/rss"},
    {"name": "Guardian – Business","url": "https://www.theguardian.com/business/rss"},
    {"name": "BBC – Business",     "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},
    {"name": "WSJ – World News",   "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml"},
]

# ── Nguồn tin trong nước (HTML scrape) ───────────────────────────────────────
VN_SCRAPE_SOURCES = [
    {
        "name": "CafeF",
        "url":  "https://cafef.vn/",
        "selectors": ["h3 a", "h2 a", ".tlitem h3 a", ".list-feed a.title"],
        "base_url": "https://cafef.vn",
    },
    {
        "name": "VnEconomy",
        "url":  "https://vneconomy.vn/",
        "selectors": ["h3.story__heading a", "h2.story__heading a", "h3 a", ".story-title a"],
        "base_url": "https://vneconomy.vn",
    },
    {
        "name": "VietnamBiz",
        "url":  "https://vietnambiz.vn/",
        "selectors": ["p.story__title a", "h3 a", "h2 a"],
        "base_url": "https://vietnambiz.vn",
    },
    {
        "name": "Vietstock",
        "url":  "https://vietstock.vn/",
        "selectors": ["a.title", "h3 a", "h2 a"],
        "base_url": "https://vietstock.vn",
    },
    {
        "name": "Người Quan Sát",
        "url":  "https://nguoiquansat.vn/",
        "selectors": ["h3 a", "h2 a", ".post-title a", ".entry-title a"],
        "base_url": "https://nguoiquansat.vn",
    },
]

# ── Keyword phân loại QUỐC TẾ ─────────────────────────────────────────────────
INTL_KEYWORDS = {
    "intl_war": [
        "war", "conflict", "ukraine", "russia", "middle east", "iran",
        "sanctions", "geopolitical", "military", "troops", "ceasefire",
        "gaza", "israel", "nato", "attack", "missile",
    ],
    "intl_energy": [
        "oil", "crude", "brent", "wti", "gas", "energy prices", "opec",
        "natural gas", "lng", "petroleum", "barrel", "fuel", "refinery",
    ],
    "intl_fed": [
        "fed", "federal reserve", "interest rate", "rate hike", "rate cut",
        "central bank", "ecb", "boj", "monetary policy", "inflation target",
        "fomc", "jerome powell", "quantitative",
    ],
    "intl_global_fin": [
        "stocks", "bonds", "global markets", "equities", "inflation",
        "gdp", "recession", "wall street", "s&p", "nasdaq", "dow",
        "yield", "treasury", "dollar", "trade deficit", "tariff",
    ],
}

# ── Keyword phân loại TRONG NƯỚC ──────────────────────────────────────────────
VN_KEYWORDS = {
    "vn_rates": [
        "lãi suất", "ngân hàng nhà nước", "hạn mức tín dụng", "thanh khoản",
        "tái cấp vốn", "nhnn", "tín dụng", "room tín dụng", "lãi suất huy động",
        "lãi suất cho vay", "chính sách tiền tệ",
    ],
    "vn_infra": [
        "cao tốc", "đường sắt", "sân bay", "cảng biển", "cầu", "đầu tư công",
        "tháo gỡ vướng mắc", "giải ngân", "khu công nghiệp", "nhà máy",
        "dự án", "khởi công", "phê duyệt", "hạ tầng",
    ],
    "vn_domestic_fin": [
        "vn-index", "trái phiếu doanh nghiệp", "gdp", "lạm phát",
        "tài khóa", "ngân sách", "thâm hụt", "xuất khẩu", "nhập khẩu",
        "tăng trưởng", "vĩ mô", "tỷ giá", "hnx", "upcom",
    ],
    "vn_corporate": [
        "doanh nghiệp", "ctcp", "lợi nhuận", "doanh thu", "phát hành",
        "niêm yết", "m&a", "sáp nhập", "cổ phiếu", "kết quả kinh doanh",
        "đại hội", "đhcđ", "cổ tức", "ipo",
    ],
}

# ── Evening extra groups ────────────────────────────────────────────────────
VN_MARKET_EVENING_KEYWORDS = [
    "vn-index", "vnindex", "thanh khoản", "phiên giao dịch", "điểm số",
    "khối ngoại", "dòng tiền", "ngành", "bluechip", "kết thúc phiên",
    "đóng cửa", "tăng điểm", "giảm điểm", "thị trường chứng khoán",
]

INTL_ENERGY_RATES_EVENING_KEYWORDS = (
    INTL_KEYWORDS["intl_energy"] + INTL_KEYWORDS["intl_fed"] +
    ["euro", "sterling", "pound", "ftse", "dax", "cac", "european markets"]
)
