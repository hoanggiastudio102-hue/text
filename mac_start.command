#!/bin/bash
# Di chuyển vào thư mục chứa file script này
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "==================================================="
echo "🚀 ĐANG KHỞI ĐỘNG AUTO CONTENT GEMINI TRÊN MAC..."
echo "==================================================="

# Cập nhật code mới nhất từ Github (nếu có)
echo "🔄 Đang kiểm tra cập nhật..."
git pull origin main

# Kiểm tra và tạo môi trường ảo nếu chưa có
if [ ! -d ".venv" ]; then
    echo "⚙️ Lần đầu chạy trên Mac, hệ thống đang tự động cài đặt..."
    echo "Vui lòng đợi khoảng 1-2 phút nhé sếp!"
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    playwright install chromium
else
    source .venv/bin/activate
fi

echo "🌐 Đang mở giao diện trên trình duyệt..."
# Mở sẵn trình duyệt Safari/Chrome mặc định của Mac
open "http://127.0.0.1:5002"

echo "✅ Hệ thống đã sẵn sàng!"
echo "⚠️ LƯU Ý: Không được đóng cửa sổ Terminal màu đen này khi đang dùng Tool!"
echo "==================================================="

# Chạy server Flask
python app.py
