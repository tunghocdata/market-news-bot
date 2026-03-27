---
name: Market Review Automation (News & Stocks Brief)
description: Quy trình tự động thu thập, phân loại, dùng AI tóm tắt và gửi bản tin (Morning Brief & Evening Recap) cho thị trường chứng khoán trong/ngoài nước.
---

# Kỹ năng (Skill): Automated Market News Briefing

Hệ thống Market Review Automation là một Pipeline gồm 4 bước chạy liên hoàn để cung cấp nội dung điểm tin chất lượng cao vào các khung giờ cố định (Sáng trước khi mở cửa, Chiều sau khi đóng cửa). Kỹ năng này đóng vai trò quan trọng trong việc tiết kiệm thời gian đọc tin tức tài chính mỗi ngày.

## 1. Cấu trúc Hệ Thống
Hệ thống được module hóa thành các tệp độc lập dễ dàng nâng cấp:
- **`marketreview.py`**: Trái tim cấu hình (API Keys, URLs báo chí, Tần suất quét, Keywords Regex phân nhóm).
- **`scraper.py`**: Thu thập dữ liệu đa nguồn (RSS parsing, HTML Scraping qua `requests` & `BeautifulSoup`). Tích hợp sẵn cơ chế bypass lỗi SSL chứng chỉ và Timeout.
- **`browser_scraper.py`**: Web Scraping nâng cao qua Playwright (Headless Chrome) để vượt qua các trang chống bot mạnh như Bloomberg trực tiếp. Đặc biệt dùng RSS của Google News là cách luân phiên vượt qua "Paywall" của Reuters / Bloomberg.
- **`classifier.py`**: Dùng biểu thức chính quy (Regex Regex Keywords) để phân luồng tin về các cụm riêng (Ví dụ: Lãi suất, Bất động sản, Chiến tranh...). Dùng Keyword matching giúp tiết kiệm đáng kể token AI so với đẩy tất cả qua LLM.
- **`summarizer.py`**: Sử dụng Groq API (`llama-3.3-70b-versatile`) để gộp hàng chục bài viết cùng chủ đề thành 3-5 gạch đầu dòng ngắn gọn báo cáo theo văn phong phân tích tài chính. Sử dụng Multi-threading (`ThreadPoolExecutor`) để tăng tốc gọi API AI.
- **`sheets.py`**: Ghi log vào Google Sheets thông qua tài khoản Service Account (`gspread`), tự tạo Sheet theo từng ngày (YYYY-MM-DD), bài viết được chia 2 cột "Trong Nước" và "Quốc Tế".
- **`telegram_send.py`**: Gửi Broadcast Message tới Telegram thông qua Bot API, tự động cắt chuỗi nếu thông điệp quá dài (>4000 chars).
- **`morning_run.py` & `evening_run.py`**: Orchestrator ghép tất cả các mắt xích lại để thực hiện trong duy nhất 1 luồng.

## 2. Các Bước Tiến Hành Vận Hành (Flow)

**Bước 1: Quét Tin Tức (Scraping)**
- Quét các nguồn báo chí (Cafef, VnEconomy, NYT, Guardian...).
- Thực hiện loại bỏ bài trùng lặp (Dedup) dựa theo `URL` hoặc chuỗi `Title` giống nhau một cách triệt để.
- Tự động lấy tối đa các bài trong vòng `24 giờ` đổ lại với Morning và `8 giờ` đổ lại với Evening.

**Bước 2: Phân Loại Phễu (Classification)**
- Duyệt qua từng bản tin đã thu thập.
- Đưa qua bộ điểm số từ Keyword (vd: "Fed", "lãi suất", "lạm phát" -> `intl_fed`). Nếu điểm rơi vào nhóm nào cao nhất thì đánh tag vào cấu trúc Dictionary.

**Bước 3: Tóm Tắt (AI Summarization)**
- Thay vì gửi hàng trăm link rác, hệ thống đẩy từng Group (Nhóm Đề Tài) kèm mảng Title + Summary cho Groq API.
- Prompt kỹ thuật Prompting: Yêu cầu AI đóng vai siêu chuyên gia phân tích tài chính, gom ý trùng từ nhiều đầu báo và rút ra "thông tin nào là keypoint ảnh hưởng hành động giá cổ phiếu ngày hôm đó".

**Bước 4: Xuất Bản (Export & Notification)**
- Đẩy dữ liệu thô + bản chốt AI tổng hợp xuống Google Sheets của ngày hôm đó để làm Archive tham khảo sau này.
- Gửi tin nhắn Markdown định dạng rõ ràng về Telegram kèm Emoji cảnh báo sớm.

## 3. Tự Động Hoá Lịch Trình (macOS LaunchAgents)
Sử dụng công cụ `launchd` sẵn có trên Mac để tạo một tệp `.plist` báo thức tự động.
Mã XML sẽ tự động đánh thức file `python3 morning_run.py` vào lúc *07:00 AM* và *16:30 PM* hằng ngày (từ Thứ 2 đến Thứ 6), không yêu cầu can thiệp bằng tay.

### Các tình huống Troubleshooting (Xử lý lỗi) thường gặp:
- Lỗi kết nối / **Timeout** khi cào báo: Giảm lượt truy cập (`requests` Retry = 0, Timeout = 8s) để không bị kẹt toàn bộ Pipeline. Tận dụng Google News RSS cho các trang quốc tế có Paywall dày tốn kém băng thông.
- AI báo lỗi **Rate Limit** (Giới hạn tải): Bắt `try except` trong việc Summary. Nếu nhóm nào bị từ chối kết nối Groq Server thì giữ tên gốc thay vì làm sập toàn bộ bản tin.

## 4. Cách nâng cấp trong tương lai
- Thêm Prompt AI phụ chuyên quét "Sentiment Analysis" của các nhóm ngành.
- Có thể đẩy lên các dịch vụ đám mây (AWS Lambda, GitHub Actions) để đỡ phải phụ thuộc máy Mac phải bật ở nhà.
