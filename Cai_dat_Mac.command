#!/bin/bash
# Cài đặt AutoContentGemini trên Mac (chạy 1 lần). Tự cài uv + Python 3.12 + thư viện, rồi chạy ngầm Tool.
cd "$(dirname "$0")" || exit 1
xattr -dr com.apple.quarantine . 2>/dev/null
chmod +x ./*.command 2>/dev/null

pause_exit() { echo; read -r -n 1 -p "Bấm phím bất kỳ để đóng..."; exit "${1:-1}"; }

echo "==================================================="
echo " CÀI ĐẶT AUTO CONTENT GEMINI TRÊN MAC (lần đầu)"
echo "==================================================="
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

echo; echo "[1/4] Kiểm tra uv..."
if ! command -v uv >/dev/null 2>&1; then
    echo "Chưa có uv — đang tải từ https://astral.sh/uv ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || { echo "[LỖI] Không cài được uv. Kiểm tra mạng rồi chạy lại."; pause_exit 1; }

echo; echo "[2/4] Tạo môi trường .venv với Python 3.12..."
if [ ! -x .venv/bin/python ]; then
    uv venv --python 3.12 .venv || { echo "[LỖI] Không tạo được .venv."; pause_exit 1; }
fi

echo; echo "[3/4] Cài thư viện (1-3 phút)..."
uv pip install --python .venv/bin/python -r requirements.txt || { echo "[LỖI] Cài thư viện thất bại (xem thông báo phía trên)."; pause_exit 1; }

echo; echo "[4/4] Kiểm tra trình duyệt..."
if [ -d "/Applications/Google Chrome.app" ] || [ -d "$HOME/Applications/Google Chrome.app" ]; then
    echo "Đã có Google Chrome — OK."
else
    echo "Máy chưa có Google Chrome. Đang tải Chromium dự phòng..."
    echo "(Nên cài Google Chrome từ https://www.google.com/chrome/ để đăng nhập Google ổn định.)"
    .venv/bin/python -m playwright install chromium
fi

mkdir -p logs outputs
echo; echo "==================================================="
echo " CÀI ĐẶT XONG — đang chạy ngầm Tool..."
echo "==================================================="
./Chay_ngam_Mac.command
