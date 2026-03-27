"""
summarizer.py – Tóm tắt từng nhóm bài bằng Groq AI
"""

import logging
import requests
from marketreview import GROQ_API_KEY, GROQ_MODEL

log = logging.getLogger(__name__)

# ── Label hiển thị cho từng group ─────────────────────────────────────────────
GROUP_LABELS = {
    # Morning
    "intl_war":         "🌍 [QUỐC TẾ] Chiến tranh – Địa chính trị",
    "intl_energy":      "🛢 [QUỐC TẾ] Nhiên liệu – Hàng hóa",
    "intl_fed":         "🏦 [QUỐC TẾ] FED – Lãi suất toàn cầu",
    "intl_global_fin":  "📊 [QUỐC TẾ] Tài chính thế giới",
    "vn_rates":         "🏦 [TRONG NƯỚC] Lãi suất – Chính sách tiền tệ",
    "vn_infra":         "🏗 [TRONG NƯỚC] Dự án hạ tầng",
    "vn_domestic_fin":  "📈 [TRONG NƯỚC] Tài chính vĩ mô & Thị trường",
    "vn_corporate":     "🏢 [TRONG NƯỚC] Tin doanh nghiệp",
    # Evening
    "vn_market":        "📊 [TRONG NƯỚC] Kết quả thị trường hôm nay",
    "intl_energy_rates":"🌐 [QUỐC TẾ] Giá dầu – Lãi suất – Thị trường châu Âu",
}

# ── Prompt templates ───────────────────────────────────────────────────────────
PROMPT_TEMPLATE = """Bạn là một chuyên gia phân tích tài chính 15 năm kinh nghiệm, chuyên đọc tin tức để đánh giá tâm lý thị trường theo ngành.

Nhiệm vụ:
- Đọc toàn bộ danh sách tin tức sau về cùng một nhóm ngành.
- Đánh giá "sentiment" tổng thể của thị trường với ngành này trong {time_context}.
- Chỉ xét trên nội dung tin, không dự đoán tương lai.

Yêu cầu đầu ra:
1) Gán nhãn sentiment: "TÍCH CỰC", "TIÊU CỰC" hoặc "TRUNG TÍNH".
2) Cho điểm sentiment từ -2 đến +2 (-2=rất tiêu cực, -1=tiêu cực nhẹ, 0=trung tính, +1=tích cực, +2=rất tích cực).
3) Liệt kê 3-5 luận điểm chính giải thích lý do (dẫn chiếu ngắn gọn tới tin cụ thể). Nếu có tin trái chiều, hãy đề cập.

BẮT BUỘC TRẢ VỀ DƯỚI DẠNG JSON hợp lệ theo định dạng sau (không chứa markdown markdown backticks ở ngoài):
{{
  "sentiment_label": "...",
  "sentiment_score": 0,
  "reasons": [
    "...", "..."
  ]
}}

Nhóm: {group_label}
Bài viết:
{articles_text}"""


def _articles_to_text(articles: list[dict], max_articles: int = 15) -> str:
    """Chuyển list bài → chuỗi text cho prompt."""
    lines = []
    for a in articles[:max_articles]:
        title   = a.get("title", "")
        summary = a.get("summary", "")
        source  = a.get("source", "")
        line    = f"[{source}] {title}"
        if summary:
            line += f" — {summary[:200]}"
        lines.append(line)
    return "\n".join(lines)

def _sources_used(articles: list[dict]) -> list[str]:
    seen = []
    for a in articles:
        s = a.get("source", "")
        if s and s not in seen:
            seen.append(s)
    return seen


# ── Gọi Groq ──────────────────────────────────────────────────────────────────
import json
import time

def _call_groq_json(prompt: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "model":       GROQ_MODEL,
                    "messages":    [{"role": "user", "content": prompt}],
                    "max_tokens":  800,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"}
                },
                timeout=40,
            )
            body = r.json()
            if "error" in body:
                error_msg = body['error'].get('message', '')
                if "Rate limit" in error_msg and attempt < retries - 1:
                    log.warning("Groq Rate Limit. Đợi %ds rồi thử lại...", 10 * (attempt + 1))
                    time.sleep(10 * (attempt + 1))
                    continue
                return {"error": f"Groq: {error_msg}"}
                
            content = body["choices"][0]["message"]["content"].strip()
            return json.loads(content)
        except json.JSONDecodeError:
            log.warning("Groq trả về không phải JSON hợp lệ: %s", content)
            return {"error": "Lỗi định dạng JSON từ AI."}
        except Exception as e:
            if attempt < retries - 1:
                log.warning("Groq error (%s), thử lại...", e)
                time.sleep(5)
                continue
            log.warning("Groq error: %s", e)
            return {"error": f"Không lấy được nhận xét AI: {e}"}
            
    return {"error": "Vượt quá số lần thử lại API."}


# ── Public API ─────────────────────────────────────────────────────────────────
def summarize_group(group: str, articles: list[dict], mode: str = "morning") -> str:
    """
    Tóm tắt 1 nhóm bài và nhận diện sentiment.
    Trả về text hiển thị format sẵn cho Markdown.
    """
    label = GROUP_LABELS.get(group, group)

    if not articles:
        return f"{label}\n- Không có tin mới.\n"

    time_context = "SÁNG NAY" if mode == "morning" else "CHIỀU NAY"
    articles_text = _articles_to_text(articles)
    prompt = PROMPT_TEMPLATE.format(
        time_context=time_context,
        group_label=label,
        articles_text=articles_text
    )

    log.info("AI Sentiment [%s] – %d bài...", group, len(articles))
    resp = _call_groq_json(prompt)
    
    if "error" in resp:
        return f"{label}\n_⚠️ {resp['error']}_\n"

    # Lấy dữ liệu từ JSON
    sent_label = resp.get("sentiment_label", "TRUNG TÍNH").upper()
    sent_score = resp.get("sentiment_score", 0)
    reasons = resp.get("reasons", [])

    # Map Emoji
    emoji = "🟡"
    if "TÍCH CỰC" in sent_label or sent_score > 0:
        emoji = "🟢"
    elif "TIÊU CỰC" in sent_label or sent_score < 0:
        emoji = "🔴"

    score_str = f"+{sent_score}" if sent_score > 0 else str(sent_score)
    
    # Định dạng Markdown output
    lines = [f"{label}"]
    lines.append(f"{emoji} **[{sent_label}]** (Score: {score_str})")
    for r in reasons:
        lines.append(f"- {r}")
        
    # Nguồn
    sources = _sources_used(articles)
    lines.append(f"Nguồn: {', '.join(sources)}")
    
    return "\n".join(lines) + "\n"


def summarize_all(buckets: dict[str, list[dict]], mode: str = "morning",
                  skip_groups: list[str] | None = None) -> dict[str, str]:
    """
    Tóm tắt tất cả nhóm — chạy SONG SONG để tiết kiệm thời gian.
    Trả về dict {group: summary_text}.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    skip  = set(skip_groups or ["unclassified"])
    tasks = {g: arts for g, arts in buckets.items() if g not in skip}

    result = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(summarize_group, g, arts, mode): g
            for g, arts in tasks.items()
        }
        for fut in as_completed(futures):
            g = futures[fut]
            try:
                result[g] = fut.result()
            except Exception as e:
                log.warning("summarize [%s] lỗi: %s", g, e)
                result[g] = f"{g}\n- ⚠️ Lỗi tóm tắt: {e}\n"

    # Giữ đúng thứ tự hiển thị
    ordered = {}
    for g in tasks:
        if g in result:
            ordered[g] = result[g]
    return ordered
