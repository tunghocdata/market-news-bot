"""
sheets.py – Ghi dữ liệu vào Google Sheets
Thiết kế mới: 1 sheet duy nhất mỗi ngày, chia 2 cột khu vực (Thế giới | Trong nước)
              bài sắp xếp theo thời gian đăng từ cũ → mới trong mỗi khu vực.
"""

import logging
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from marketreview import GOOGLE_SHEETS_ID, GOOGLE_SERVICE_ACCOUNT_FILE

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Header cho mỗi khu vực (8 cột × 2 khu vực = 16 cột)
AREA_HEADERS = ["#", "Nguồn", "Tiêu đề", "URL", "Tóm tắt", "Thời gian", "Nhóm", ""]
# Cột bắt đầu: Thế giới = A, Trong nước = I (cách nhau 8 cột, có 1 cột trống giữa)
WORLD_COL   = 0   # 0-indexed = cột A
VN_COL      = 9   # 0-indexed = cột J (có 1 cột trống ở giữa)


def _get_client() -> gspread.Client:
    creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_or_create_sheet(wb: gspread.Spreadsheet, name: str) -> gspread.Worksheet:
    try:
        return wb.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        log.info("Tạo sheet mới: %s", name)
        ws = wb.add_worksheet(title=name, rows=2000, cols=20)
        return ws


def _format_dt(dt_str: str) -> str:
    """Chuyển ISO datetime → HH:MM DD/MM."""
    if not dt_str:
        return ""
    try:
        from datetime import timezone, timedelta
        dt = datetime.fromisoformat(dt_str)
        vn_tz = timezone(timedelta(hours=7))
        dt    = dt.astimezone(vn_tz)
        return dt.strftime("%H:%M %d/%m")
    except Exception:
        return dt_str[:16]


def _split_by_region(articles: list[dict]) -> tuple[list[dict], list[dict]]:
    """Chia bài theo khu vực: quốc tế (en) và trong nước (vi), giữ thứ tự đã sort."""
    world = [a for a in articles if a.get("lang", "vi") == "en"]
    vn    = [a for a in articles if a.get("lang", "vi") == "vi"]
    return world, vn


def _articles_to_rows(articles: list[dict], url_to_group: dict) -> list[list]:
    """Chuyển list bài → list rows (mỗi row = 7 cột)."""
    rows = []
    for i, a in enumerate(articles, 1):
        rows.append([
            i,
            a.get("source", ""),
            a.get("title", "")[:150],
            a.get("url", ""),
            a.get("summary", "")[:200],
            _format_dt(a.get("datetime", "")),
            url_to_group.get(a.get("url", ""), ""),
        ])
    return rows


def write_to_sheets(articles: list[dict], buckets: dict[str, list[dict]],
                    summaries: dict[str, str] | None = None,
                    session: str = "morning"):
    """
    Ghi tất cả vào Google Sheets theo thiết kế mới:
    - 1 tab mỗi ngày (ví dụ: 2026-03-27) – không tạo nhiều tab
    - Trong tab: Thế giới bên trái | Trong nước bên phải
    - Bài sắp xếp theo thời gian từ cũ → mới
    - Phần tóm tắt AI ở phía dưới (nếu có)
    """
    if GOOGLE_SHEETS_ID == "YOUR_GOOGLE_SHEET_ID_HERE":
        log.warning("Chưa cấu hình GOOGLE_SHEETS_ID – bỏ qua")
        return

    today      = datetime.now().strftime("%Y-%m-%d")
    sheet_name = today  # 1 tab duy nhất mỗi ngày

    # Tạo lookup: url → group
    url_to_group: dict[str, str] = {}
    for group, arts in buckets.items():
        for a in arts:
            url_to_group[a["url"]] = group

    world_arts, vn_arts = _split_by_region(articles)
    world_rows = _articles_to_rows(world_arts, url_to_group)
    vn_rows    = _articles_to_rows(vn_arts,    url_to_group)

    try:
        client = _get_client()
        wb     = client.open_by_key(GOOGLE_SHEETS_ID)
        ws     = _get_or_create_sheet(wb, sheet_name)
        ws.clear()  # xóa nội dung cũ (nếu chạy lại trong ngày)

        batch = []

        # ── Tiêu đề khu vực ──────────────────────────────────────────────
        # Hàng 1: tiêu đề lớn (merge thủ công sau nếu muốn)
        title_row = [""] * 20
        title_row[WORLD_COL] = (
            f"🌍 THẾ GIỚI – {today} "
            f"{'Morning Brief' if session=='morning' else 'Evening Recap'}"
        )
        title_row[VN_COL] = (
            f"🇻🇳 TRONG NƯỚC – {today} "
            f"{'Morning Brief' if session=='morning' else 'Evening Recap'}"
        )
        batch.append(title_row)

        # Hàng 2: headers cột
        header_row = [""] * 20
        for i, h in enumerate(AREA_HEADERS):
            header_row[WORLD_COL + i] = h
            header_row[VN_COL   + i] = h
        header_row[WORLD_COL] = "#"
        header_row[VN_COL]    = "#"
        batch.append(header_row)

        # ── Rows bài viết (song song theo chiều ngang) ────────────────────
        max_len = max(len(world_rows), len(vn_rows), 1)
        for i in range(max_len):
            row = [""] * 20
            if i < len(world_rows):
                for j, v in enumerate(world_rows[i]):
                    row[WORLD_COL + j] = v
            if i < len(vn_rows):
                for j, v in enumerate(vn_rows[i]):
                    row[VN_COL + j] = v
            batch.append(row)

        # ── Tóm tắt AI (nếu có) ──────────────────────────────────────────
        if summaries:
            batch.append([""] * 20)
            sep_row = [""] * 20
            sep_row[WORLD_COL] = "─" * 30 + " NHẬN XÉT AI " + "─" * 30
            batch.append(sep_row)
            for group, text in summaries.items():
                for line in text.split("\n"):
                    if line.strip():
                        txt_row = [""] * 20
                        txt_row[WORLD_COL] = line
                        batch.append(txt_row)
                batch.append([""] * 20)

        ws.update("A1", batch, value_input_option="RAW")

        log.info(
            "✅ Sheets [%s]: %d thế giới + %d trong nước",
            sheet_name, len(world_rows), len(vn_rows)
        )
    except Exception as e:
        log.error("❌ Sheets lỗi: %s", e)


def get_sheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEETS_ID}"
