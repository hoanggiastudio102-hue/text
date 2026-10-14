#!/bin/bash
# Giữ lại cho tương thích: chưa cài thì cài, đã cài thì chạy ngầm.
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then exec ./Chay_ngam_Mac.command; else exec ./Cai_dat_Mac.command; fi
