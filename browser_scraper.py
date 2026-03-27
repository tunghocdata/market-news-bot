"""
browser_scraper.py – Scrape Bloomberg và Reuters bằng Playwright (headless Chrome)
Chạy riêng hoặc được gọi từ morning_run.py
"""

import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

_VN_TZ = timezone(timedelta(hours=7))

BROWSER_SOURCES = [
    {
        "name":     "Reuters",
        "url":      "https://www.reuters.com/",
        "lang":     "en",
        "selectors": [
            "a[data-testid='Heading']",
            "[class*='story-title'] a",
            "h3 a[href*='/world/'], h3 a[href*='/business/'], h3 a[href*='/markets/']",
        ],
        "base_url": "https://www.reuters.com",
        "link_filter": lambda href: (
            href.startswith("https://www.reuters.com/") and
            any(s in href for s in ["/world/", "/business/", "/markets/", "/economy/"])
        ),
    },
    {
        "name":     "Bloomberg",
        "url":      "https://www.bloomberg.com/asia",
        "lang":     "en",
        "selectors": [
            "a[class*='story-package-module__headline']",
            "a[class*='headline']",
            "h1 a, h2 a, h3 a",
        ],
        "base_url": "https://www.bloomberg.com",
        "link_filter": lambda href: (
            href.startswith("https://www.bloomberg.com/") and
            any(s in href for s in ["/news/", "/markets/", "/economics/", "/asia/"])
        ),
    },
]


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.split())


def scrape_with_browser(sources: list[dict] | None = None, timeout: int = 20000) -> list[dict]:
    """
    Scrape Bloomberg + Reuters bằng Playwright headless.
    Trả về list dict cùng cấu trúc với scraper.py.
    """
    if sources is None:
        sources = BROWSER_SOURCES

    articles = []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("Playwright chưa cài. Chạy: pip3 install playwright && python3 -m playwright install chromium")
        return []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            viewport={"width": 1280, "height": 800},
        )
        # Chặn ảnh/media để tăng tốc
        context.route("**/*.{png,jpg,jpeg,gif,webp,mp4,woff2,woff}", lambda r: r.abort())

        now_vn = datetime.now(_VN_TZ)

        for src in sources:
            try:
                page = context.new_page()
                log.info("Browser scraping [%s] ...", src["name"])
                page.goto(src["url"], wait_until="domcontentloaded", timeout=timeout)
                page.wait_for_timeout(2000)  # đợi JS render thêm 2s

                seen_urls  = set()
                src_articles = []

                for selector in src["selectors"]:
                    try:
                        links = page.query_selector_all(selector)
                        for a in links:
                            title = _clean(a.inner_text())
                            href  = a.get_attribute("href") or ""
                            if not href.startswith("http"):
                                href = src["base_url"].rstrip("/") + "/" + href.lstrip("/")

                            link_filter = src.get("link_filter")
                            if link_filter and not link_filter(href):
                                continue

                            if not title or len(title) < 15 or href in seen_urls:
                                continue

                            seen_urls.add(href)
                            src_articles.append({
                                "source":   src["name"],
                                "title":    title,
                                "url":      href,
                                "summary":  "",
                                "datetime": now_vn.isoformat(),
                                "section":  "world",
                                "lang":     src.get("lang", "en"),
                            })

                        if src_articles:
                            break  # dùng selector đầu tiên có kết quả
                    except Exception as e:
                        log.debug("Selector [%s] on [%s]: %s", selector, src["name"], e)
                        continue

                log.info("Browser [%s]: %d bài", src["name"], len(src_articles))
                articles.extend(src_articles)
                page.close()

            except Exception as e:
                log.warning("Browser [%s] lỗi: %s", src["name"], e)
                try:
                    page.close()
                except Exception:
                    pass

        context.close()
        browser.close()

    return articles
