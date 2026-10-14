#!/bin/bash
# Chạy AutoContentGemini ngầm trên Mac (đóng cửa sổ Terminal này vẫn chạy). Log: logs/server.log
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo "Chưa cài đặt. Hãy chạy Cai_dat_Mac.command trước."
    read -r -n 1 -p "Bấm phím bất kỳ để đóng..."; exit 1
fi
running() { lsof -nP -iTCP:5002 -sTCP:LISTEN >/dev/null 2>&1; }
if running; then
    echo "Tool đang chạy rồi."
else
    mkdir -p logs
    PYTHONUTF8=1 AUTOGEMINI_DEBUG=0 nohup .venv/bin/python app.py >> logs/server.log 2>&1 < /dev/null &
    disown
    echo -n "Đang khởi động Tool"
    for _ in $(seq 1 40); do running && break; echo -n "."; sleep 1; done
    echo
    if ! running; then
        echo "[LỖI] Tool chưa chạy được. 30 dòng cuối của logs/server.log:"
        tail -n 30 logs/server.log
        read -r -n 1 -p "Bấm phím bất kỳ để đóng..."; exit 1
    fi
fi
open "http://localhost:5002"
echo "✅ Tool đang chạy ngầm tại http://localhost:5002 — có thể đóng cửa sổ này."
echo "   Muốn tắt: chạy Dung_ngam_Mac.command"
