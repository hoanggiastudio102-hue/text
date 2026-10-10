# -*- coding: utf-8 -*-
"""Thăm dò NotebookLM bằng tài khoản Google đã đăng nhập của Tool (chỉ XEM, không tạo/sửa gì).
Ghi notebook_debug.json + notebook_debug.png để biết giao diện thật trước khi viết module."""
import argparse, json, os, sys, time
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
JS = """() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 4 && r.height > 4; };
  const pick = sel => Array.from(document.querySelectorAll(sel)).filter(vis).slice(0, 80)
      .map(e => ({tag: e.tagName.toLowerCase(), aria: e.getAttribute('aria-label') || '', text: (e.innerText || '').trim().slice(0, 60),
                  href: (e.getAttribute('href') || '').slice(0, 80)}));
  return {url: location.href, title: document.title,
          buttons: pick('button, [role=button]'), links: pick('a[href]').slice(0, 30),
          text: (document.body.innerText || '').slice(0, 800)};
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="gemini_profile")
    a = ap.parse_args()
    udir = os.path.join(BASE, "profiles", a.profile)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(udir, channel="chrome", headless=False,
                                                   args=["--disable-blink-features=AutomationControlled"])
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://notebooklm.google.com/", timeout=60000)
            time.sleep(8)
            info = page.evaluate(JS)
            with open(os.path.join(BASE, "notebook_debug.json"), "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False, indent=1)
            page.screenshot(path=os.path.join(BASE, "notebook_debug.png"))
            print("URL:", info["url"])
            print("Tiêu đề:", info["title"])
            print("Số nút:", len(info["buttons"]))
            logged = "accounts.google.com" not in info["url"]
            print("Đã đăng nhập Google:", "có" if logged else "KHÔNG (đang ở trang đăng nhập)")
        finally:
            ctx.close()


if __name__ == "__main__":
    main()
