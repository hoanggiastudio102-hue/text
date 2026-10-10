# -*- coding: utf-8 -*-
"""
Điều khiển Gemini Web bằng Playwright: mở chat mới, CHỌN MODEL (mặc định 3.1 Pro),
gửi prompt, chờ trả lời xong, lấy văn bản.

Dùng độc lập:   python gemini_client.py --check [--profile gemini_profile]
  -> mở Gemini, liệt kê mục trong menu chọn model, thử chọn model cấu hình và báo kết quả.
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
GEMINI_URL = "https://gemini.google.com/app"
CHAT_BOX = "rich-textarea"
RESPONSE_SEL = "message-content"

DEFAULT_SETTINGS = {"model": "3.1 Pro", "thinking": "Cao"}


# ---------------------------------------------------------------------------
# CÀI ĐẶT (model đang dùng)
# ---------------------------------------------------------------------------
def load_settings():
    data = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data.update(json.load(f))
    except Exception:
        pass
    return data


def save_settings(new_values):
    data = load_settings()
    data.update({k: v for k, v in new_values.items() if k in DEFAULT_SETTINGS})
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def get_model_name():
    """Biến môi trường GEMINI_MODEL > settings.json > mặc định '3.1 Pro'."""
    return (os.environ.get("GEMINI_MODEL") or load_settings().get("model") or DEFAULT_SETTINGS["model"]).strip()


def get_thinking_level():
    """Mức suy luận trong menu Gemini (Thấp / Trung bình / Cao). Rỗng = không đổi."""
    if "GEMINI_THINKING" in os.environ:
        return os.environ["GEMINI_THINKING"].strip()
    return str(load_settings().get("thinking", DEFAULT_SETTINGS["thinking"])).strip()


# ---------------------------------------------------------------------------
# LỖI
# ---------------------------------------------------------------------------
class GeminiError(Exception):
    pass


class GeminiLimitError(GeminiError):
    """Gemini báo hết lượt / giới hạn sử dụng."""


class GeminiCancelled(GeminiError):
    pass


_LIMIT_PATTERNS = [
    r"(reached|exceeded).{0,60}limit",
    r"(đã đạt|vượt quá|hết).{0,40}(giới hạn|lượt)",
    r"try again (later|tomorrow)",
    r"something went wrong",
    r"đã xảy ra lỗi",
]


def looks_like_limit_message(text):
    t = (text or "").strip().lower()
    if not t or len(t) > 500:   # câu trả lời thật thường dài; thông báo lỗi thì ngắn
        return False
    return any(re.search(p, t) for p in _LIMIT_PATTERNS)


# ---------------------------------------------------------------------------
# SO KHỚP TÊN MODEL
# ---------------------------------------------------------------------------
def _norm(s):
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ")).strip().lower()


def model_tokens(wanted):
    return [t for t in re.split(r"[\s_\-]+", _norm(wanted)) if t and t != "gemini"]


def text_matches_model(text, wanted):
    """Mọi phần của tên model (VD '3.1' và 'pro') đều phải xuất hiện trong text."""
    t = _norm(text)
    toks = model_tokens(wanted)
    return bool(toks) and all(tok in t for tok in toks)


def pick_best_option(options, wanted):
    """options: list[str]. Trả về index mục khớp nhất (chuỗi ngắn nhất chứa đủ token) hoặc None."""
    best = None
    for i, opt in enumerate(options):
        if text_matches_model(opt, wanted):
            if best is None or len(options[i]) < len(options[best]):
                best = i
    return best


LEVEL_SYNONYMS = {
    "thấp": ["thấp", "low"], "low": ["thấp", "low"],
    "trung bình": ["trung bình", "medium"], "medium": ["trung bình", "medium"],
    "cao": ["cao", "high"], "high": ["cao", "high"],
}


def find_level_option(options, level):
    """Tìm mục mức suy luận (đầu dòng là 'Cao'/'High'...). Bỏ qua chữ 'check' của biểu tượng tick."""
    syn = LEVEL_SYNONYMS.get(_norm(level), [_norm(level)])
    for i, opt in enumerate(options):
        t = re.sub(r"^(check|done)\s*", "", _norm(opt))
        for w in syn:
            if t == w or t.startswith(w + " "):
                return i
    return None


# ---------------------------------------------------------------------------
# JS dùng trong trang Gemini
# ---------------------------------------------------------------------------
_JS_FIND_PICKER = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 8 && r.height > 8 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const clean = el => (el.innerText || el.textContent || '').replace(/(expand_more|expand_less|arrow_drop_down|arrow_drop_up|keyboard_arrow_[a-z]+|unfold_more)/g,' ').replace(/\s+/g,' ').trim();
  const box = document.querySelector('rich-textarea');
  if (!box) return null;
  const br = box.getBoundingClientRect();
  const SKIP = /(mic|micro|voice|giọng|send|gửi|upload|tải lên|add|thêm|tool|công cụ|attach|file)/i;
  const MODEL = /(flash|pro|thinking|fast|nhanh|suy nghĩ|ultra|\d\.\d|gemini)/i;
  const prefer = [
    '[data-test-id="bard-mode-menu-button"]',
    'button[aria-label*="mode" i]', 'button[aria-label*="model" i]',
    'button[aria-label*="chế độ" i]', 'button[aria-label*="mô hình" i]'
  ];
  for (const sel of prefer) {
    const el = [...document.querySelectorAll(sel)].find(vis);
    if (el) { el.setAttribute('data-ac-picker', '1'); return clean(el); }
  }
  // Dò theo vị trí: nút nằm trong/ngay quanh ô nhập, có chữ giống tên model.
  const cands = [...document.querySelectorAll('button, [role="button"]')].filter(el => {
    if (!vis(el)) return false;
    const r = el.getBoundingClientRect();
    const cy = r.top + r.height / 2;
    if (cy < br.top - 40 || cy > br.bottom + 80) return false;
    const label = (el.getAttribute('aria-label') || '') + ' ' + clean(el);
    if (SKIP.test(el.getAttribute('aria-label') || '') && !MODEL.test(clean(el))) return false;
    return MODEL.test(label);
  });
  cands.sort((a, b) => b.getBoundingClientRect().left - a.getBoundingClientRect().left);
  const el = cands[0];
  if (!el) return null;
  el.setAttribute('data-ac-picker', '1');
  return clean(el);
}
"""

_JS_LIST_OPTIONS = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 8 && r.height > 8 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const clean = el => (el.innerText || el.textContent || '').replace(/(expand_more|expand_less|arrow_drop_down|arrow_drop_up|keyboard_arrow_[a-z]+|unfold_more)/g,' ').replace(/\s+/g,' ').trim();
  document.querySelectorAll('[data-ac-opt]').forEach(e => e.removeAttribute('data-ac-opt'));
  const sels = ['[role="menuitem"]','[role="menuitemradio"]','[role="option"]','.mat-mdc-menu-item',
                '[data-test-id*="mode-option"]','button.bard-mode-list-button'];
  let els = [];
  for (const s of sels) els.push(...document.querySelectorAll(s));
  els = [...new Set(els)].filter(vis);
  if (!els.length) {  // fallback: các nút bên trong lớp phủ (overlay) của Material
    const ov = document.querySelector('.cdk-overlay-container');
    if (ov) els = [...ov.querySelectorAll('button, [role="button"], li, a')].filter(vis);
  }
  return els.map((el, i) => { el.setAttribute('data-ac-opt', String(i)); return clean(el); });
}
"""

_JS_IS_GENERATING = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4; };
  const sels = ['button[aria-label*="Stop" i]','button[aria-label*="Dừng" i]','button[aria-label*="Ngừng" i]',
                'button.stop','[data-test-id="stop-button"]','mat-icon[fonticon="stop"]','.stop-icon'];
  for (const s of sels) { if ([...document.querySelectorAll(s)].some(vis)) return true; }
  return false;
}
"""


# ---------------------------------------------------------------------------
# PHIÊN LÀM VIỆC VỚI GEMINI
# ---------------------------------------------------------------------------
class GeminiSession:
    def __init__(self, profile_name="gemini_profile", model=None, log=print,
                 on_tick=None, should_cancel=None, headless=False, thinking=None):
        self.profile_name = profile_name or "gemini_profile"
        self.model = (get_model_name() if model is None else model).strip()
        self.thinking = (get_thinking_level() if thinking is None else thinking).strip()
        self.log = log
        self.on_tick = on_tick or (lambda: None)
        self.should_cancel = should_cancel or (lambda: False)
        self.headless = headless
        self._pw = None
        self.ctx = None
        self.page = None

    # --- vòng đời -----------------------------------------------------------
    def start(self):
        from playwright.sync_api import sync_playwright
        user_data_dir = os.path.join(BASE_DIR, "profiles", self.profile_name)
        os.makedirs(user_data_dir, exist_ok=True)
        self.log(f"Đang mở trình duyệt với tài khoản: {self.profile_name}")
        self._pw = sync_playwright().start()
        try:
            self.ctx = self._pw.chromium.launch_persistent_context(
                user_data_dir, channel="chrome", headless=self.headless, accept_downloads=True,
                args=["--disable-blink-features=AutomationControlled"])
        except Exception as e:
            self.close()
            raise GeminiError(
                "Không mở được Chrome cho Tool. Hãy đóng mọi cửa sổ Chrome 'Đăng nhập' đang mở của Tool "
                f"rồi chạy lại. Chi tiết: {e}")
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.new_chat()

    def close(self):
        try:
            if self.ctx:
                self.ctx.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self.ctx = self._pw = self.page = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *a):
        self.close()

    # --- chat mới + chọn model ---------------------------------------------
    def new_chat(self):
        self._check_cancel()
        page = self.page
        page.goto(GEMINI_URL, timeout=60000)
        try:
            page.wait_for_selector(CHAT_BOX, timeout=40000)
        except Exception:
            if "accounts.google.com" in page.url or "signin" in page.url.lower():
                raise GeminiError("Chưa đăng nhập Gemini. Bấm nút 'Đăng nhập' ở góc phải trên của Tool, "
                                  "đăng nhập rồi TẮT cửa sổ đó.")
            raise GeminiError("Không thấy khung chat của Gemini (có thể chưa đăng nhập hoặc mạng chậm).")
        time.sleep(1.5)
        if self.model:
            self.select_model(self.model)

    def _open_picker(self):
        label = self.page.evaluate(_JS_FIND_PICKER)
        if label is None:
            return None
        self.page.click('[data-ac-picker="1"]')
        time.sleep(1.0)
        return label

    def picker_label(self):
        try:
            return self.page.evaluate(_JS_FIND_PICKER)
        except Exception:
            return None

    def list_model_options(self):
        """Mở menu model, trả (nhãn_hiện_tại, [các mục]) rồi đóng menu."""
        label = self._open_picker()
        if label is None:
            return None, []
        options = self.page.evaluate(_JS_LIST_OPTIONS)
        return label, options

    def select_model(self, wanted):
        """Chọn model theo tên (VD '3.1 Pro'). Ném GeminiError nếu không chọn được."""
        page = self.page
        current = self.picker_label()
        if current and text_matches_model(current, wanted):
            self.log(f"Model đang dùng: {current}")
            return current

        label = self._open_picker()
        if label is None:
            raise GeminiError("Không tìm thấy nút chọn model của Gemini trên trang. "
                              "Giao diện Gemini có thể đã đổi — hãy bấm 'Kiểm tra Gemini' để xem chi tiết.")
        options = page.evaluate(_JS_LIST_OPTIONS)
        idx = pick_best_option(options, wanted)
        if idx is None:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            shown = " | ".join(options) if options else "(không đọc được mục nào)"
            raise GeminiError(f"Không thấy model '{wanted}' trong menu Gemini. Các mục đang có: {shown}. "
                              "Hãy sửa ô 'Model Gemini' cho khớp với tên trong menu rồi chạy lại.")
        page.click(f'[data-ac-opt="{idx}"]')
        time.sleep(1.5)
        after = self.picker_label() or ""
        # Nhãn nút chỉ cần chứa phần chữ của tên model (VD 'pro'); phần số phiên bản có thể nằm ở mục menu.
        letters = [t for t in model_tokens(wanted) if not re.search(r"\d", t)]
        ok = text_matches_model(after, wanted) or (letters and all(t in _norm(after) for t in letters))
        if not ok:
            raise GeminiError(f"Đã bấm '{options[idx]}' nhưng nút model vẫn hiện '{after}'. Không chắc đã đổi model.")
        self.log(f"Đã chọn model: {options[idx]}  (nút hiện: {after})")
        self.select_level(self.thinking)
        return self.picker_label() or after

    def select_level(self, level):
        """Chọn mức suy luận (Thấp/Trung bình/Cao). Lỗi ở bước này chỉ cảnh báo, không dừng job."""
        if not level:
            return
        page = self.page
        try:
            options = page.evaluate(_JS_LIST_OPTIONS)      # menu có thể còn đang mở sau khi chọn model
            idx = find_level_option(options, level)
            if idx is None:
                if self._open_picker() is None:
                    self.log(f"⚠️ Không mở lại được menu để chọn mức '{level}'.")
                    return
                options = page.evaluate(_JS_LIST_OPTIONS)
                idx = find_level_option(options, level)
            if idx is None:
                self.log(f"⚠️ Không thấy mức suy luận '{level}' trong menu — giữ mức hiện tại.")
                page.keyboard.press("Escape")
                return
            page.click(f'[data-ac-opt="{idx}"]')
            time.sleep(1.0)
            self.log(f"Mức suy luận: {level}  (nút hiện: {self.picker_label()})")
        except Exception as e:
            self.log(f"⚠️ Bỏ qua bước chọn mức suy luận: {e}")

    # --- gửi / nhận --------------------------------------------------------
    def _check_cancel(self):
        if self.should_cancel():
            raise GeminiCancelled("Đã huỷ theo yêu cầu.")

    def _is_generating(self):
        try:
            return bool(self.page.evaluate(_JS_IS_GENERATING))
        except Exception:
            return False

    def ask(self, prompt, timeout=1500, first_token_timeout=180):
        """Gửi prompt vào chat hiện tại, chờ trả lời xong, trả về văn bản."""
        self._check_cancel()
        page = self.page
        before = len(page.query_selector_all(RESPONSE_SEL))

        page.click(CHAT_BOX)
        time.sleep(0.4)
        page.keyboard.insert_text(prompt)
        time.sleep(1.2)
        page.keyboard.press("Enter")

        t0 = time.time()
        last_len, changed_at, saw_generating = -1, time.time(), False
        text = ""
        while True:
            time.sleep(2)
            self.on_tick()
            self._check_cancel()
            now = time.time()
            elems = page.query_selector_all(RESPONSE_SEL)
            if len(elems) <= before:
                if now - t0 > first_token_timeout:
                    raise GeminiError("Gemini không tạo câu trả lời mới (quá thời gian chờ).")
                continue
            text = elems[-1].inner_text()
            generating = self._is_generating()
            saw_generating = saw_generating or generating
            if len(text) != last_len:
                last_len, changed_at = len(text), now
            idle = now - changed_at

            if text.strip():
                if saw_generating:
                    if not generating and idle >= 4:
                        break
                elif idle >= 25:      # không thấy nút Stop bao giờ -> dựa vào độ ổn định lâu hơn
                    break
            if now - t0 > timeout:
                if text.strip():
                    self.log("⚠️ Quá thời gian chờ tối đa, lấy phần đã có.")
                    break
                raise GeminiError("Quá thời gian chờ, Gemini không trả về nội dung.")

        text = text.strip()
        if looks_like_limit_message(text):
            raise GeminiLimitError(f"Gemini báo lỗi/hết lượt: {text[:200]}")
        return text


def apply_model_to_page(page, log=print):
    """Dùng cho các tab cũ (browser_bot.py): chọn model đã cấu hình trên trang Gemini đang mở."""
    s = GeminiSession(log=log)
    s.page = page
    if s.model:
        s.select_model(s.model)


# ---------------------------------------------------------------------------
# PHIÊN GIẢ LẬP (chạy thử toàn bộ Tool mà không cần Gemini/đăng nhập)
# ---------------------------------------------------------------------------
class DryRunSession:
    model = "dry-run"

    def __init__(self, *a, log=print, on_tick=None, should_cancel=None, **k):
        self.log = log
        self.on_tick = on_tick or (lambda: None)
        self.should_cancel = should_cancel or (lambda: False)
        self.calls = 0

    def start(self):
        self.log("[CHẠY THỬ] Không mở Gemini — dùng văn bản giả lập.")

    def close(self):
        pass

    def new_chat(self):
        pass

    def ask(self, prompt, **k):
        if self.should_cancel():
            raise GeminiCancelled("Đã huỷ theo yêu cầu.")
        self.calls += 1
        time.sleep(0.6)
        self.on_tick()
        m = re.search(r"SOURCE ARTICLE:\n<<<\n(.*?)\n>>>", prompt, re.S)
        src = (m.group(1) if m else prompt)[:160].replace("\n", " ")
        who = re.search(r"writer for (.+?) \(", prompt)
        if prompt.startswith("Now act as a strict second editor"):
            return "[CHẠY THỬ] (đã soát lại) văn bản hoàn chỉnh."
        return f"[CHẠY THỬ — {who.group(1) if who else '?'}] {src}"


# ---------------------------------------------------------------------------
# KIỂM TRA NHANH: python gemini_client.py --check
# ---------------------------------------------------------------------------
def check(profile="gemini_profile", model=None):
    model = model or get_model_name()
    lines = []

    def log(msg):
        print(msg, flush=True)
        lines.append(msg)

    s = GeminiSession(profile_name=profile, model="", log=log)   # model="" -> chưa chọn, để ta tự dò
    try:
        s.start()
        label, options = s.list_model_options()
        log(f"Nút chọn model hiện đang ghi: {label!r}")
        log("Các mục trong menu model:")
        for o in options:
            log(f"   - {o}")
        if not options:
            log("   (không đọc được mục nào)")
        diag_dir = os.path.join(BASE_DIR, "outputs", "_diag")
        os.makedirs(diag_dir, exist_ok=True)
        try:
            s.page.screenshot(path=os.path.join(diag_dir, "gemini_menu.png"))
            log(f"Đã chụp màn hình menu: outputs/_diag/gemini_menu.png")
        except Exception:
            pass
        try:
            s.page.keyboard.press("Escape")
        except Exception:
            pass
        idx = pick_best_option(options, model)
        if idx is None:
            log(f"❌ KHÔNG thấy mục nào khớp với model '{model}'.")
            return False, "\n".join(lines)
        s.select_model(model)
        log(f"✅ Chọn được model '{model}'.")
        return True, "\n".join(lines)
    except GeminiError as e:
        log(f"❌ {e}")
        return False, "\n".join(lines)
    finally:
        s.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--profile", default="gemini_profile")
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    if a.check:
        ok, _ = check(a.profile, a.model)
        sys.exit(0 if ok else 1)
    print(__doc__)
