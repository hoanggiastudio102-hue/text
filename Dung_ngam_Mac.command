#!/bin/bash
# Tắt AutoContentGemini đang chạy ngầm trên Mac.
cd "$(dirname "$0")" || exit 1
pids=$(lsof -tiTCP:5002 -sTCP:LISTEN 2>/dev/null)
if [ -z "$pids" ]; then
    echo "Tool không chạy."
else
    kill $pids 2>/dev/null; sleep 2
    pids=$(lsof -tiTCP:5002 -sTCP:LISTEN 2>/dev/null)
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null
    echo "✅ Đã tắt Tool."
fi
