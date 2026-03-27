"""
scraper.py – Thu thập tin tức từ RSS feeds + HTML scraping
"""

import logging
import ssl
import urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import feedparser
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from marketreview import INTL_RSS_SOURCES, VN_SCRAPE_SOURCES

log = logging.getLogger(__name__)

_VN_TZ = timezone(timedelta(hours=7))

# ── HTTP Session (SSL verify=False để bypass Python 3.14 Mac cert issue) ──
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _make_session() -> requests.Session:
    s = requests.Session()
    ret = Retry(total=1, backoff_factor=0, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=ret))
    s.mount("http://",  HTTPAdapter(max_retries=ret))
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    return s

SESSION = _make_session()

# ── SSL context không verify (fix cho Python 3.14 trên Mac) ───────────────
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode    = ssl.CERT_NONE

def _feedparser_parse(url: str):
    """Parse RSS với SSL bypass, timeout cứng 8s (không retry)."""
    try:
        req  = urllib.request.Request(url, headers={"User-Agent": "feedparser/6.0"})
        resp = urllib.request.urlopen(req, context=_SSL_CTX, timeout=8)
        content = resp.read()
        return feedparser.parse(content)
    except Exception as e:
        log.warning("RSS timeout/lỗi [%s]: %s", url, type(e).__name__)
        return feedparser.parse("")  # trả về feed rỗng, không retry


# ── Helpers ────────────────────────────────────────────────────────────────
def _now_vn() -> datetime:
    return datetime.now(_VN_TZ)

def _parse_rss_dt(entry) -> datetime | None:
    """Parse RSS entry datetime, return timezone-aware datetime or None."""
    for attr in ("published", "updated", "created"):
        raw = entry.get(attr)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(_VN_TZ)
            except Exception:
                pass
    return None

def _is_within(dt: datetime | None, hours: int) -> bool:
    if dt is None:
        return True  # nếu không có datetime → giữ lại (không lọc bỏ)
    cutoff = _now_vn() - timedelta(hours=hours)
    return dt >= cutoff

def _clean(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.split())


# ── RSS scraper (quốc tế) ──────────────────────────────────────────────────
def scrape_rss(source: dict, hours_ago: int = 24) -> list[dict]:
    """Lấy bài từ 1 RSS feed (SSL bypass enabled)."""
    articles = []
    try:
        feed = _feedparser_parse(source["url"])
        if not feed.entries:
            log.warning("RSS [%s]: 0 entries – bozo=%s", source["name"], feed.bozo)
        for entry in feed.entries:
            dt = _parse_rss_dt(entry)
            if not _is_within(dt, hours_ago):
                continue
            title   = _clean(entry.get("title", ""))
            summary = _clean(entry.get("summary") or entry.get("description", ""))
            url     = entry.get("link", "")
            if not title or not url:
                continue
            articles.append({
                "source":   source["name"],
                "title":    title,
                "url":      url,
                "summary":  summary[:500],
                "datetime": dt.isoformat() if dt else "",
                "section":  source.get("section", "general"),
                "lang":     "en",
            })
        log.info("RSS [%s]: %d bài trong %dh", source["name"], len(articles), hours_ago)
    except Exception as e:
        log.warning("RSS [%s] lỗi: %s", source["name"], e)
    return articles


# ── HTML scraper (trong nước) ──────────────────────────────────────────────
def scrape_html(source: dict, hours_ago: int = 24) -> list[dict]:
    """
    Scrape trang chủ báo trong nước.
    Chỉ lấy title + url (không có datetime/summary thường).
    Timestamp mặc định = now (bài trên trang chủ = bài mới nhất).
    """
    articles = []
    try:
        resp = SESSION.get(source["url"], timeout=8, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        seen_urls = set()
        for selector in source["selectors"]:
            links = soup.select(selector)
            for a in links:
                title = _clean(a.get_text())
                href  = a.get("href", "")
                if not href.startswith("http"):
                    href = source["base_url"].rstrip("/") + "/" + href.lstrip("/")
                if not title or len(title) < 15 or href in seen_urls:
                    continue
                seen_urls.add(href)
                articles.append({
                    "source":   source["name"],
                    "title":    title,
                    "url":      href,
                    "summary":  "",
                    "datetime": _now_vn().isoformat(),
                    "section":  "general",
                    "lang":     "vi",
                })
            if articles:
                break  # dùng selector đầu tiên có kết quả

        log.info("HTML [%s]: %d bài", source["name"], len(articles))
    except Exception as e:
        log.warning("HTML [%s] lỗi: %s", source["name"], e)
    return articles


# ── Public API ─────────────────────────────────────────────────────────────
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_all(hours_ago_intl: int = 24, hours_ago_vn: int = 24,
              max_workers: int = 8) -> list[dict]:
    """
    Thu thập tất cả tin tức song song.
    Trả về list dict đã hợp nhất.
    """
    tasks = []
    for src in INTL_RSS_SOURCES:
        tasks.append(("rss", src, hours_ago_intl))
    for src in VN_SCRAPE_SOURCES:
        tasks.append(("html", src, hours_ago_vn))

    all_articles: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for kind, src, hrs in tasks:
            fn  = scrape_rss if kind == "rss" else scrape_html
            fut = pool.submit(fn, src, hrs)
            futures[fut] = src["name"]

        for fut in as_completed(futures):
            try:
                all_articles.extend(fut.result())
            except Exception as e:
                log.warning("Lỗi fetch [%s]: %s", futures[fut], e)

    # Sắp xếp theo thời gian đăng (cũ → mới), bài không có datetime lên cuối
    all_articles.sort(key=lambda a: a.get("datetime", "") or "9999")
    log.info("Tổng bài thu thập: %d", len(all_articles))
    return all_articles


def deduplicate(articles: list[dict]) -> list[dict]:
    """Loại bỏ bài trùng URL hoặc tiêu đề giống nhau."""
    seen_urls   = set()
    seen_titles = set()
    result = []
    for a in articles:
        url_key   = a["url"].split("?")[0].rstrip("/")
        title_key = a["title"].lower()[:80]
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        result.append(a)
    log.info("Sau dedup: %d bài", len(result))
    return result
