"""ChatGPT (chatgpt.com) và Claude (claude.ai) chạy qua web — cùng cách làm với Gemini.

Mỗi loại AI có Chrome riêng (profiles/chatgpt_profile, profiles/claude_profile), đăng nhập riêng, dùng gói đang trả
(Plus/Pro/Max) nên không tốn tiền token. Lớp phiên có cùng giao diện với GeminiSession:
    start() / close() / new_chat() / ask(prompt) -> str

Kiểm tra / đọc tài khoản:
    python web_chat.py --provider chatgpt --whoami
    python web_chat.py --provider claude --check      (mở chat, chọn model, hỏi 1 câu ngắn)
"""
import argparse
import json
import os
import re
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import gemini_client as gc
from gemini_client import GeminiError, GeminiLimitError, GeminiCancelled, launch_browser, pick_best_option, text_matches_model

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PROVIDERS = {
    "gemini": {"name": "Gemini", "profile": "gemini_profile", "url": "https://gemini.google.com/app",
               "setting": "model"},
    "chatgpt": {"name": "ChatGPT", "profile": "chatgpt_profile", "url": "https://chatgpt.com/",
                "setting": "chatgpt_model"},
    "claude": {"name": "Claude", "profile": "claude_profile", "url": "https://claude.ai/new",
               "setting": "claude_model"},
}
MODEL_PRESETS = {
    "chatgpt": ["GPT-6", "GPT-5.6 Sol", "GPT-5.5"],
    "claude": ["Fable 5.1", "Opus 5.5", "Sonnet 5.5", "Haiku 5.5"],
}


def provider_of(name):
    name = (name or "gemini").strip().lower()
    return name if name in PROVIDERS else "gemini"


def get_model(provider):
    p = provider_of(provider)
    if p == "gemini":
        return gc.get_model_name()
    return str(gc.load_settings().get(PROVIDERS[p]["setting"], "") or "").strip()


def set_account(profile, info):
    data = gc.load_accounts()
    data[profile] = dict(info, at=time.time())
    with open(gc.ACCOUNT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data[profile]


def account_label(provider):
    """Chuỗi ngắn để hiện trong Đội Máy: 'Tên (email)' / 'chưa đăng nhập' / ''."""
    a = gc.load_accounts().get(PROVIDERS[provider_of(provider)]["profile"]) or {}
    if a.get("logged_in") is False:
        return "chưa đăng nhập"
    return " ".join(x for x in (a.get("name"), f"({a['email']})" if a.get("email") else "") if x)


# ---------------------------------------------------------------------------------------------- JS trong trang
_JS_COMMON = r"""
const vis = (e) => !!e && (e.checkVisibility ? e.checkVisibility() : !!e.offsetParent);
const all = (s) => Array.from(document.querySelectorAll(s));
const firstVis = (sels) => { for (const s of sels) { const e = all(s).find(vis); if (e) return e; } return null; };
"""

CHATGPT_JS = {
    "input": ["#prompt-textarea", "textarea[name='prompt']", "[contenteditable='true'][role='textbox']",
              "textarea[aria-label*='ChatGPT']", "div.ProseMirror[contenteditable='true']"],
    "assistant": "[data-message-role='assistant'], [data-message-author-role='assistant']",
    "extract": r"""(el) => {
        const md = el.querySelector('.markdown');
        if (md && !el.hasAttribute('data-message-role')) return md.innerText;
        const parts = [];
        for (const c of Array.from(el.children)) {
            if (c.matches('[data-message-attribution],[data-message-actions],h4,h5') && !c.querySelector('p,li,pre,table')) continue;
            if (c.matches('[data-message-actions]')) continue;
            const t = (c.innerText || '').trim();
            if (t) parts.push(t);
        }
        return parts.join('\n\n') || (el.innerText || '');
    }""",
    "generating": r"""() => {
        const stop = all('button').some(b => vis(b) && (/^(stop|dừng)/i.test(b.getAttribute('aria-label') || '') ||
                                                       /stop-button/.test(b.getAttribute('data-testid') || '')));
        if (stop) return true;
        const a = all("[data-message-role='assistant']").pop();
        return !!a && !a.hasAttribute('data-message-complete');
    }""",
    "done": r"""() => { const a = all("[data-message-role='assistant']").pop(); return !!a && a.hasAttribute('data-message-complete'); }""",
    "login_wall": r"""() => all('button,a').some(b => vis(b) && /^(log in|đăng nhập)$/i.test((b.innerText || '').trim()))""",
    "account": r"""async () => {
        try {
            const r = await fetch('/api/auth/session', {credentials: 'include'});
            const j = await r.json();
            if (j && j.user) return {ok: true, name: j.user.name || '', email: j.user.email || ''};
            return {ok: false};
        } catch (e) { return null; }
    }""",
    "pickers": ["[data-testid='model-switcher-dropdown-button']", "[data-octane-product-card-header-trigger]",
                "button[aria-haspopup='menu']"],
    "picker_text": r"^(chatgpt|gpt|pro|thinking|instant|auto|o\d|sol|mô hình|model)",
}

CLAUDE_JS = {
    "input": ["[data-testid='chat-input']", "div.ProseMirror[contenteditable='true']",
              "[contenteditable='true'][aria-label]"],
    "assistant": "[data-testid='assistant-message'], .font-claude-response, .font-claude-message",
    "extract": r"""(el) => {
        const blocks = Array.from(el.querySelectorAll('.standard-markdown, .progressive-markdown')).filter(vis)
            .filter(b => !b.parentElement.closest('.standard-markdown, .progressive-markdown'));
        if (blocks.length) return blocks.map(b => b.innerText.trim()).filter(Boolean).join('\n\n');
        return (el.innerText || '').replace(/^\s*(Claude đã phản hồi|Claude responded)\s*:\s*/i, '');
    }""",
    "generating": r"""() => all("[data-testid='chat-input-stop']").some(vis) || !!document.querySelector("[data-is-streaming='true']")
        || all('button').some(b => vis(b) && /^(stop response|dừng phản hồi)/i.test(b.getAttribute('aria-label') || ''))""",
    "done": r"""() => { const a = all("[data-testid='assistant-message']").pop(); const row = a && a.closest('[data-is-streaming]');
        return !!row && row.getAttribute('data-is-streaming') === 'false' && !all("[data-testid='chat-input-stop']").some(vis); }""",
    "login_wall": r"""() => /\/login|\/signin/.test(location.pathname) ||
        all('button,a').some(b => vis(b) && /^(continue with google|tiếp tục với google|log in|đăng nhập)$/i.test((b.innerText || '').trim()))""",
    "account": r"""async () => {
        try {
            const r = await fetch('/api/account', {credentials: 'include'});
            if (r.status === 401 || r.status === 403) return {ok: false};
            const j = await r.json();
            return {ok: true, name: j.full_name || j.display_name || '', email: j.email_address || ''};
        } catch (e) { return null; }
    }""",
    "pickers": ["[data-testid='model-selector-dropdown']"],
    "picker_text": r".",
}

_JS_MENU_ITEMS = r"""() => {
  const vis = (e) => !!e && (e.checkVisibility ? e.checkVisibility() : !!e.offsetParent);
  document.querySelectorAll('[data-acg-item]').forEach(e => e.removeAttribute('data-acg-item'));
  const items = Array.from(document.querySelectorAll('[role="menuitem"],[role="menuitemradio"],[role="option"],[role="menuitemcheckbox"]')).filter(vis);
  return items.map((e, i) => { e.setAttribute('data-acg-item', String(i));
      return {text: (e.innerText || '').replace(/\s+/g, ' ').trim(), checked: e.getAttribute('aria-checked') === 'true'
              || e.getAttribute('aria-selected') === 'true', sub: e.getAttribute('aria-haspopup') === 'menu'}; });
}"""


class WebChatSession:
    """Một cửa sổ Chrome riêng (profile riêng) cho ChatGPT hoặc Claude."""

    def __init__(self, provider, profile_name=None, model=None, log=print, on_tick=None, should_cancel=None,
                 headless=False, thinking=None):
        self.provider = provider_of(provider)
        info = PROVIDERS[self.provider]
        self.name = info["name"]
        self.url = info["url"]
        self.profile_name = profile_name or info["profile"]
        self.model = (get_model(self.provider) if model is None else model or "").strip()
        self.js = CHATGPT_JS if self.provider == "chatgpt" else CLAUDE_JS
        self.log = log
        self.on_tick = on_tick or (lambda: None)
        self.should_cancel = should_cancel or (lambda: False)
        self.headless = headless
        self._pw = self.ctx = self.page = None
        self._model_ok = False
        self._acct_checked = False

    # --- vòng đời ------------------------------------------------------------------------------------------
    def start(self):
        from playwright.sync_api import sync_playwright
        d = os.path.join(BASE_DIR, "profiles", self.profile_name)
        os.makedirs(d, exist_ok=True)
        self.log(f"Đang mở Chrome {self.name} ({self.profile_name})…")
        self._pw = gc.pw_acquire()
        try:
            self.ctx = launch_browser(self._pw, d, headless=self.headless, log=self.log)
        except Exception as e:
            self.close()
            raise GeminiError(f"Không mở được Chrome cho {self.name}. Hãy tắt cửa sổ 'Đăng nhập {self.name}' của Tool "
                              f"nếu đang mở rồi chạy lại. Chi tiết: {e}")
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.new_chat()
        self.record_account()

    def close(self):
        for fn in (lambda: self.ctx and self.ctx.close(), lambda: gc.pw_release(self._pw)):
            try:
                fn()
            except Exception:
                pass
        self.ctx = self._pw = self.page = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *a):
        self.close()

    def _check_cancel(self):
        if self.should_cancel():
            raise GeminiCancelled("Đã huỷ theo yêu cầu.")

    def _eval(self, body, arg=None):
        """Chạy JS có sẵn các hàm vis/all/firstVis."""
        fn = "(arg) => {" + _JS_COMMON + " return (" + body + ")(arg); }"
        return self.page.evaluate(fn, arg)

    # --- tài khoản ---------------------------------------------------------------------------------------------
    def account(self):
        try:
            return self.page.evaluate(self.js["account"])
        except Exception:
            return None

    def record_account(self):
        a = self.account()
        if a is None:
            return None
        if not a.get("ok"):
            set_account(self.profile_name, {"logged_in": False, "provider": self.provider})
            return None
        info = set_account(self.profile_name, {"name": a.get("name", ""), "email": a.get("email", ""),
                                               "provider": self.provider})
        self.log(f"Tài khoản {self.name}: {info.get('name') or ''} {info.get('email') or ''}".strip())
        return info

    # --- chat mới + model -------------------------------------------------------------------------------------
    def _input_sel(self):
        return ", ".join(self.js["input"])

    def _find_input(self):
        return self._eval("(sels) => { const e = firstVis(sels); if (!e) return false; "
                          "document.querySelectorAll('[data-acg-input]').forEach(x => x.removeAttribute('data-acg-input')); "
                          "e.setAttribute('data-acg-input', '1'); return true; }", self.js["input"])

    def new_chat(self):
        self._check_cancel()
        try:
            self.page.goto(self.url, timeout=60000)
        except Exception as e:
            raise GeminiError(f"Không mở được trang {self.name} (mạng lỗi hoặc trang chặn). Chi tiết: {str(e)[:160]}")
        t0 = time.time()
        while time.time() - t0 < 45:
            self._check_cancel()
            try:
                if self._find_input():
                    break
                if self._eval(self.js["login_wall"]):
                    a = self.account()
                    if a is not None and not a.get("ok"):
                        set_account(self.profile_name, {"logged_in": False, "provider": self.provider})
                        raise GeminiError(f"Chưa đăng nhập {self.name}. Vào tab 'Tài khoản AI' → bấm 'Đăng nhập "
                                          f"{self.name}', đăng nhập xong rồi TẮT cửa sổ đó.")
            except GeminiError:
                raise
            except Exception:
                pass          # trang đang chuyển hướng
            time.sleep(1)
        else:
            if "login" in self.page.url or "auth" in self.page.url:
                raise GeminiError(f"Chưa đăng nhập {self.name}. Vào tab 'Tài khoản AI' để đăng nhập.")
            raise GeminiError(f"Không thấy ô chat của {self.name} (mạng chậm, chưa đăng nhập hoặc trang bị chặn kiểm tra "
                              "'bạn có phải người thật'). Mở 'Đăng nhập' để xem trang.")
        time.sleep(1.2)
        if not self._acct_checked:       # ChatGPT cho chat ẩn danh khi chưa đăng nhập -> phải tự kiểm tra
            a = self.account()
            if a is not None and not a.get("ok"):
                set_account(self.profile_name, {"logged_in": False, "provider": self.provider})
                raise GeminiError(f"Chưa đăng nhập {self.name}. Vào tab 'Tài khoản AI' → bấm 'Đăng nhập {self.name}', "
                                  "đăng nhập xong rồi TẮT cửa sổ đó.")
            self._acct_checked = True
        if self.model and not self._model_ok:
            self.select_model(self.model)

    def _menu_items(self):
        return self.page.evaluate(_JS_MENU_ITEMS)

    def _picker_candidates(self):
        return self._eval(r"""(a) => {
            document.querySelectorAll('[data-acg-picker]').forEach(x => x.removeAttribute('data-acg-picker'));
            const rx = new RegExp(a.rx, 'i'); const out = []; let i = 0;
            for (const s of a.sels) for (const e of all(s)) {
                if (!vis(e) || e.hasAttribute('data-acg-picker')) continue;
                const t = (e.innerText || e.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
                if (!rx.test(t) && !/model|mô hình/i.test(e.getAttribute('aria-label') || '')) continue;
                e.setAttribute('data-acg-picker', String(i)); out.push(t); i++;
            }
            return out; }""", {"sels": self.js["pickers"], "rx": self.js["picker_text"]})

    def select_model(self, wanted):
        """Chọn model trong menu của trang. Không thấy thì giữ model đang chọn (ghi cảnh báo, không dừng job)."""
        wanted = (wanted or "").strip()
        if not wanted:
            return True
        page = self.page
        try:
            labels = self._picker_candidates()
        except Exception:
            labels = []
        if any(text_matches_model(l, wanted) for l in labels):
            self._model_ok = True
            self.log(f"Model {self.name}: {wanted} (đang chọn sẵn)")
            return True
        for i, lab in enumerate(labels[:4]):
            try:
                page.click(f'[data-acg-picker="{i}"]', timeout=5000)
                time.sleep(0.8)
                items = self._menu_items()
                idx = pick_best_option([x["text"] for x in items], wanted)
                if idx is None:      # thử mở menu con "Mô hình khác / More models"
                    sub = next((k for k, x in enumerate(items) if x["sub"] or re.search(
                        r"khác|more|other|legacy|cũ", x["text"], re.I)), None)
                    if sub is not None:
                        page.hover(f'[data-acg-item="{sub}"]')
                        page.click(f'[data-acg-item="{sub}"]', timeout=3000)
                        time.sleep(0.8)
                        items = self._menu_items()
                        idx = pick_best_option([x["text"] for x in items], wanted)
                if idx is not None:
                    page.click(f'[data-acg-item="{idx}"]', timeout=5000)
                    time.sleep(0.8)
                    page.keyboard.press("Escape")
                    self._model_ok = True
                    self.log(f"Đã chọn model {self.name}: {items[idx]['text'][:60]}")
                    return True
                page.keyboard.press("Escape")
                time.sleep(0.4)
            except Exception:
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
        self._model_ok = True          # không thử lại ở mỗi chat mới
        self.log(f"⚠️ Không tìm thấy model '{wanted}' trong menu {self.name} — dùng model đang chọn trên web.")
        return False

    def list_model_options(self):
        labels = self._picker_candidates()
        if not labels:
            return "", []
        self.page.click('[data-acg-picker="0"]', timeout=5000)
        time.sleep(0.8)
        items = [x["text"] for x in self._menu_items()]
        self.page.keyboard.press("Escape")
        return labels[0], items

    # --- hỏi ------------------------------------------------------------------------------------------------
    def _count(self):
        return self.page.evaluate("(s) => document.querySelectorAll(s).length", self.js["assistant"])

    def _last_text(self):
        return self.page.evaluate("(a) => { const vis = (e) => !!e && (e.checkVisibility ? e.checkVisibility() : !!e.offsetParent);"
                                  " const els = document.querySelectorAll(a.sel); const el = els[els.length - 1];"
                                  " if (!el) return ''; return (" + self.js["extract"] + ")(el); }",
                                  {"sel": self.js["assistant"]})

    def _is_generating(self):
        try:
            return bool(self._eval(self.js["generating"]))
        except Exception:
            return False

    def _typed(self):
        try:
            return self.page.evaluate("() => { const e = document.querySelector('[data-acg-input]');"
                                      " return e ? (e.value !== undefined ? e.value : e.innerText).trim().length : 0; }")
        except Exception:
            return 0

    def _click_send(self):
        return self._eval(r"""() => {
            const b = all('button').find(x => vis(x) && !x.disabled && (/^(send|gửi)/i.test(x.getAttribute('aria-label') || '')
                       || /send-button|chat-input-send/.test(x.getAttribute('data-testid') || '')));
            if (b) { b.click(); return true; } return false; }""")

    def ask(self, prompt, timeout=1800, first_token_timeout=240):
        self._check_cancel()
        page = self.page
        if not self._find_input():
            raise GeminiError(f"Không thấy ô chat của {self.name}.")
        before = self._count()
        page.click("[data-acg-input]")
        time.sleep(0.3)
        page.keyboard.insert_text(prompt)
        time.sleep(1.5 if len(prompt) > 20000 else 0.8)
        page.keyboard.press("Enter")
        time.sleep(2.5)
        if self._typed() > 0 and self._count() <= before and not self._is_generating():
            self._click_send()        # Enter không gửi (VD đang xuống dòng) -> bấm nút Gửi

        t0 = time.time()
        last_len, changed_at, saw_gen, text = -1, time.time(), False, ""
        while True:
            time.sleep(2)
            self.on_tick()
            self._check_cancel()
            now = time.time()
            if self._count() <= before:
                if now - t0 > first_token_timeout:
                    raise GeminiError(f"{self.name} không tạo câu trả lời mới (quá thời gian chờ).")
                continue
            try:
                text = self._last_text() or ""
            except Exception:
                continue
            gen = self._is_generating()
            saw_gen = saw_gen or gen
            try:
                done = (not gen) and bool(self._eval(self.js["done"]))
            except Exception:
                done = False
            if len(text) != last_len:
                last_len, changed_at = len(text), now
            idle = now - changed_at
            if text.strip():
                if done and idle >= 3:          # trang đánh dấu đã trả lời xong
                    break
                if saw_gen:
                    if not gen and idle >= 4:
                        break
                elif idle >= 25:
                    break
            if now - t0 > timeout:
                if text.strip():
                    self.log("⚠️ Quá thời gian chờ tối đa, lấy phần đã có.")
                    break
                raise GeminiError(f"Quá thời gian chờ, {self.name} không trả về nội dung.")
        text = re.sub(r"^\s*(ChatGPT said|ChatGPT đã nói|Claude đã phản hồi|Claude responded)\s*:\s*", "", text)
        text = re.sub(r"^\s*(Thought for|Đã suy nghĩ( trong)?|Reasoned for)[^\n]{0,40}\n+", "", text)
        if gc.looks_like_limit_message(text):
            raise GeminiLimitError(f"{self.name} báo hết lượt/giới hạn: {text[:200]}")
        return text.strip()


def make_session(provider, **kw):
    """Tạo phiên đúng loại AI. provider: gemini / chatgpt / claude."""
    p = provider_of(provider)
    if p == "gemini":
        return gc.GeminiSession(**kw)
    kw.pop("thinking", None)
    return WebChatSession(p, **kw)


def check(provider, model=None):
    lines = []

    def log(m):
        print(m, flush=True)
        lines.append(m)

    s = WebChatSession(provider, model=model, log=log)
    try:
        s.start()
        try:
            label, opts = s.list_model_options()
            log(f"Nút model: {label!r}")
            for o in opts:
                log(f"   - {o}")
        except Exception as e:
            log(f"(không đọc được menu model: {e})")
        ans = s.ask("Trả lời đúng một câu ngắn bằng tiếng Việt: bạn là mô hình nào?", timeout=240)
        log(f"Trả lời thử: {ans[:300]}")
        ok = bool(ans.strip())
        log("✅ Chạy được." if ok else "❌ Không đọc được câu trả lời.")
        return ok, "\n".join(lines)
    except GeminiError as e:
        log(f"❌ {e}")
        return False, "\n".join(lines)
    finally:
        try:
            diag = os.path.join(BASE_DIR, "outputs", "_diag")
            os.makedirs(diag, exist_ok=True)
            if s.page:
                s.page.screenshot(path=os.path.join(diag, f"{s.provider}_check.png"))
        except Exception:
            pass
        s.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=["chatgpt", "claude"])
    ap.add_argument("--whoami", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    if a.whoami:
        s = WebChatSession(a.provider, model="", log=print, headless=False)
        try:
            from playwright.sync_api import sync_playwright
            d = os.path.join(BASE_DIR, "profiles", s.profile_name)
            os.makedirs(d, exist_ok=True)
            s._pw = gc.pw_acquire()
            s.ctx = launch_browser(s._pw, d, headless=False, log=print)
            s.page = s.ctx.pages[0] if s.ctx.pages else s.ctx.new_page()
            try:
                s.page.set_viewport_size({"width": 900, "height": 700})
            except Exception:
                pass
            s.page.goto(s.url, timeout=60000)
            time.sleep(4)
            info = s.record_account()
            print(json.dumps(info or gc.load_accounts().get(s.profile_name, {}), ensure_ascii=False))
        except Exception as e:
            print("ERR", e)
            sys.exit(1)
        finally:
            s.close()
        sys.exit(0)
    if a.check:
        ok, _ = check(a.provider, a.model)
        sys.exit(0 if ok else 1)
    print(__doc__)
