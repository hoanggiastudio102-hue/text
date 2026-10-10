# AutoContentGemini (Vinh Global Premium Translator)

Hệ thống Tự động hoá Sáng tạo Nội dung và Dịch thuật Đa ngôn ngữ, sử dụng công nghệ Google Gemini Advanced (Playwright Automation). Cho phép bạn tận dụng sức mạnh của tài khoản Gemini Web để xử lý tác vụ hàng loạt mà không tốn chi phí API.

## Tính năng nổi bật
- **Dịch Thuật Chuyên Nghiệp:** Dịch thuật đơn lẻ hoặc hàng loạt (Batch Translation) qua file `.txt`.
- **Sáng Tạo Nội Dung:** Viết bài chuẩn SEO, kịch bản YouTube, bài đăng MXH.
- **Sáng Tạo Ảnh Tự Động (Image Generation):** Tự động gửi lệnh tạo ảnh cho Gemini, hỗ trợ đồng bộ nhân vật (Character Consistency) và lưu trữ ảnh SLL.
- **Quản Lý Đa Tài Khoản (Multi-Account Farm):** Cho phép đăng nhập luân phiên nhiều tài khoản Google khác nhau để tránh giới hạn (Rate Limit) của Google.
- **Quản Lý Prompt:** Lưu trữ, chỉnh sửa và phân loại các mẫu Prompt Dịch Thuật/Tạo Ảnh chuyên nghiệp.

## Yêu cầu hệ thống
- Python 3.9+
- Trình duyệt Google Chrome đã cài đặt trên máy.

## Hướng dẫn Cài đặt & Chạy

1. **Clone repository:**
   ```bash
   git clone <your-repo-url>
   cd AutoContentGemini
   ```

2. **Cài đặt môi trường:**
   ```bash
   # Tạo môi trường ảo (Tuỳ chọn nhưng khuyên dùng)
   python3 -m venv venv
   source venv/bin/activate
   
   # Cài đặt thư viện
   pip install -r requirements.txt
   
   # Cài đặt Playwright Browser
   playwright install chromium
   ```

3. **Cấu hình (Không bắt buộc):**
   Copy file `.env.example` thành `.env` nếu bạn muốn tuỳ chỉnh các thông số.
   ```bash
   cp .env.example .env
   ```

4. **Khởi động Ứng dụng:**
   ```bash
   python app.py
   ```
   Sau đó truy cập: `http://localhost:5002`

## Lưu ý Quan trọng
- Lần đầu tiên chạy hoặc thêm tài khoản mới, bạn cần bấm **[+ Thêm tài khoản mới]** trên giao diện, chờ cửa sổ Chrome bật lên, tiến hành Đăng nhập vào Google (Gemini), sau đó **TẮT cửa sổ đó đi** để hệ thống lưu trữ Cookie.
- Không để lộ thư mục `chrome_profile_...` vì nó chứa session đăng nhập của bạn. (Thư mục này đã được đưa vào `.gitignore`).

## Giấy phép
Thuộc bản quyền sử dụng nội bộ của Vinh Global.

## Viết Lại & Bản Địa Hoá (tab mới)
- Dán/tải nhiều bài (.txt, YouTube) → chọn kiểu viết lại + nhiều quốc gia → mỗi bài × mỗi nước chạy 1 chat Gemini mới, viết thẳng bằng ngôn ngữ bản địa.
- Model mặc định: Gemini 3.1 Pro, mức suy luận Cao (đổi ở thanh "Model Gemini", lưu vào settings.json).
- "Kiểm tra Gemini": mở Gemini, chọn model, chụp menu vào outputs/_diag/ để dò lỗi.
- "Chạy thử": không dùng Gemini, chỉ kiểm tra luồng + file xuất.
- Job chạy nền (localize_bot.py), có huỷ/tiếp tục; kết quả zip trong outputs/.
- Lần đầu: bấm "Đăng nhập" của tool để đăng nhập Gemini trong profile của tool.
