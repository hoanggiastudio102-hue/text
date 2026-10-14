# -*- coding: utf-8 -*-
"""
Điều khiển NotebookLM ("Gemini Notebook", https://notebook.google.com) bằng Playwright, cùng hồ sơ Chrome
với Gemini. Có cùng giao diện với GeminiSession (start / new_chat / ask / close) nên localize_bot.py dùng
được cho cả hai.

Nguyên tắc: KHÔNG xoá gì trong NotebookLM. Mỗi "chat mới" = tạo một sổ ghi chú mới (nạp lại các nguồn cố
định của dạng bài), nên mỗi bài × quốc gia nằm trong một sổ riêng, không lẫn nhau.
"""
import os
import re
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from gemini_client import (BASE_DIR, GeminiError, GeminiLimitError, GeminiCancelled,
                           looks_like_limit_message, save_account, strip_restart, _JS_ACCOUNT)

NB_HOME = "https://notebook.google.com/"

# Nhãn có cả tiếng Việt lẫn tiếng Anh để đổi ngôn ngữ giao diện vẫn chạy.
RX_NEW = re.compile(r"Sổ ghi chú mới|New notebook|Create new", re.I)
RX_ADD = re.compile(r"Thêm nguồn|Add source", re.I)
RX_PASTE = re.compile(r"Văn bản đã sao chép|Copied text|Paste text", re.I)
RX_INSERT = re.compile(r"^\s*(Chèn|Insert)\s*$", re.I)
RX_PASTE_BOX = re.compile(r"Dán văn bản|Paste (your )?text", re.I)
RX_WEB = re.compile(r"Trang web|Website", re.I)
RX_URL_BOX = re.compile(r"Dán liên kết|Paste (any )?link|URL", re.I)
RX_UPLOAD = re.compile(r"Tải tệp lên|Upload files?", re.I)
RX_NB_MENU = re.compile(r"Cấu hình sổ ghi chú|Notebook (settings|configuration)|Configure notebook|More options", re.I)
RX_CHAT_CFG = re.compile(r"Định cấu hình cuộc trò chuyện|Configure chat", re.I)
QUERY_BOX = '[aria-label="Hộp truy vấn"], [aria-label="Query box"]'
CHAT_MAX = 7000      # lệnh dài hơn thì đưa vào nguồn (ô chat NotebookLM khoá nút Gửi khi quá dài)

# Quy tắc chung đặt vào "Định cấu hình cuộc trò chuyện > Tuỳ chỉnh" của mỗi sổ (giới hạn 10.000 ký tự).
BASE_CHAT_RULES = (
    "Bạn là biên dịch viên kiêm biên tập viên bản ngữ chuyên nghiệp. Khi được yêu cầu chuyển ngữ hoặc viết lại "
    "một nguồn: chỉ trả về đúng văn bản kết quả; không lời dẫn, không tóm tắt, không ghi chú, không số trích dẫn "
    "nguồn, không câu hỏi hay gợi ý ở cuối. Giữ nguyên bố cục, tiêu đề, xuống dòng, gạch đầu dòng như bản gốc. "
    "Tuyệt đối không rút gọn, không bỏ đoạn. Nếu một lần trả lời không đủ chỗ thì dừng ở cuối một đoạn trọn vẹn; "
    "khi được nhắn 'Tiếp tục' thì viết tiếp đúng từ chỗ dừng, không lặp lại phần đã viết.")
ANSWER_SEL = ".to-user-message-inner-content"

# Gắn vào đầu mọi câu hỏi để NotebookLM trả về đúng bản viết, không kèm lời dẫn/gợi ý.
PROMPT_RULES = (
    "[NOTEBOOK RULES] Reply with ONLY the finished text that is requested. No preface (no \"here is...\"), "
    "no list of sources, no closing question or suggestion, no emoji call-to-action at the end. Never shorten "
    "or summarise unless asked. If this notebook contains reference/style/rule sources, treat them as "
    "authoritative for voice, structure and facts, together with the instructions below. Ignore any earlier "
    "question or answer in this conversation that is not part of the current job.\n\n")

_JS_TEXT = """el => {
  const ms = Array.from(el.querySelectorAll('.citation-marker'));
  ms.forEach(m => { m.dataset._d = m.style.display; m.style.display = 'none'; });
  const box = el.querySelector('.message-text-content') || el;
  const t = box.innerText;
  ms.forEach(m => { m.style.display = m.dataset._d || ''; });
  return t;
}"""

_JS_SOURCE_COUNT = r"""() => {
  let n = -1;
  for (const e of document.querySelectorAll('span, div, button')) {
    if (e.children.length) continue;
    const m = /^\s*(\d+)\s*(nguồn|sources?)\s*$/i.exec(e.innerText || '');
    if (m) n = Math.max(n, +m[1]);
  }
  return n;
}"""

_JS_CLOSE_INTRO ="""() => {
  const d = Array.from(document.querySelectorAll('[role=dialog], mat-dialog-container, .mat-mdc-dialog-container'))
    .find(x => /Hạn mức|hạn mức|Gemini Notebook linh hoạt|usage limits/i.test(x.innerText || ''));
  if (!d) return false;
  const b = Array.from(d.querySelectorAll('button')).find(x => /đóng|close|got it|đã hiểu/i.test(
    (x.getAttribute('aria-label') || '') + ' ' + (x.innerText || ''))) || d.querySelector('button');
  if (b) { b.click(); return true; }
  return false;
}"""


def clean_answer(text):
    """Bỏ lời dẫn đầu ("Dưới đây là...:") và câu gợi ý cuối ("💡 Bạn có muốn...") mà NotebookLM hay thêm."""
    t = (text or "").replace("\r\n", "\n").strip()
    # nhãn nút "Thoughts / expand_more" của khung suy nghĩ bị dính vào đầu câu trả lời
    t = re.sub(r"^\s*(?:(?:Thoughts|Thinking|Suy nghĩ|Show thinking|Hiện suy nghĩ|expand_more|expand_less|"
               r"chevron_right|keyboard_arrow_down)\s*(?:\n|$))+", "", t, flags=re.I).strip()
    paras = [p for p in re.split(r"\n{2,}", t)]
    if len(paras) > 1 and re.match(r"^\s*(dưới đây|đây là|sau đây|here is|here's|below is)\b", paras[0], re.I) \
            and paras[0].rstrip().endswith(":") and len(paras[0]) < 300:
        paras = paras[1:]
    while len(paras) > 1 and re.match(r"^\s*(💡|✨|🔎|👉)", paras[-1]):
        paras = paras[:-1]
    out = "\n\n".join(paras).strip()
    out = re.sub(r"^\s*[-*_]{3,}\s*$", "", out, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


class _GeminiTab:
    """Bọc GeminiSession chạy trên tab mới của NotebookSession."""

    def __init__(self, nb):
        from gemini_client import GeminiSession
        g = GeminiSession(profile_name=nb.profile_name, log=nb.log, on_tick=nb.on_tick, should_cancel=nb.should_cancel)
        g.ctx = nb.ctx
        g.page = nb.ctx.new_page()
        self.g = g

    def new_chat(self):
        self.g.page.bring_to_front()
        self.g.new_chat()

    def ask(self, prompt):
        self.g.page.bring_to_front()
        return self.g.ask(prompt)


class NotebookSession:
    model = "NotebookLM"

    def __init__(self, profile_name="gemini_profile", fixed_sources=None, label="", log=print,
                 on_tick=None, should_cancel=None, headless=False, **_ignored):
        self.profile_name = profile_name or "gemini_profile"
        self.fixed_sources = [s for s in (fixed_sources or []) if (s or "").strip()]
        self.label = label
        self.log = log
        self.on_tick = on_tick or (lambda: None)
        self.should_cancel = should_cancel or (lambda: False)
        self.headless = headless
        self._pw = None
        self.ctx = None
        self.page = None
        self._need_new = True
        self._cmd = 0
        self.url = ""
        self.custom_ok = False
        self.article_id = None
        self._gem = None

    # --- vòng đời ------------------------------------------------------------------------------
    def start(self):
        from playwright.sync_api import sync_playwright
        user_data_dir = os.path.join(BASE_DIR, "profiles", self.profile_name)
        os.makedirs(user_data_dir, exist_ok=True)
        self.log(f"Đang mở trình duyệt (NotebookLM) với tài khoản: {self.profile_name}")
        self._pw = sync_playwright().start()
        try:
            from gemini_client import launch_browser
            self.ctx = launch_browser(self._pw, user_data_dir, headless=self.headless, log=self.log)
        except Exception as e:
            self.close()
            raise GeminiError(
                "Không mở được Chrome cho Tool. Hãy đóng mọi cửa sổ Chrome 'Đăng nhập' đang mở của Tool "
                f"rồi chạy lại. Chi tiết: {e}")
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self._open_home()
        self._record_account()

    def gemini(self):
        """Gemini trong một TAB MỚI của cùng trình duyệt (cùng hồ sơ, không mở Chrome thứ hai) để soát chéo."""
        if self._gem is None:
            self._gem = _GeminiTab(self)
        return self._gem

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

    def _check_cancel(self):
        if self.should_cancel():
            raise GeminiCancelled("Đã huỷ theo yêu cầu.")

    def _debug(self, why):
        try:
            self.page.screenshot(path=os.path.join(BASE_DIR, "notebook_debug.png"))
            self.log(f"(đã lưu ảnh màn hình notebook_debug.png — {why})")
        except Exception:
            pass

    def _record_account(self):
        try:
            label = self.page.evaluate(_JS_ACCOUNT)
            if label:
                info = save_account(self.profile_name, label)
                if info:
                    self.log(f"Tài khoản NotebookLM: {info.get('name') or ''} {info.get('email') or ''}".strip())
        except Exception:
            pass

    # --- trang chủ / sổ mới ----------------------------------------------------------------------
    def _open_home(self):
        self._check_cancel()
        page = self.page
        page.goto(NB_HOME, timeout=60000)
        try:
            page.get_by_role("button", name=RX_NEW).first.wait_for(timeout=40000)
        except Exception:
            self._debug("không thấy nút tạo sổ")
            if "accounts.google.com" in page.url or "signin" in page.url.lower():
                raise GeminiError("Chưa đăng nhập Google/NotebookLM. Bấm nút 'Đăng nhập' ở góc phải trên của Tool, "
                                  "đăng nhập rồi TẮT cửa sổ đó.")
            raise GeminiError("Không thấy nút tạo sổ ghi chú của NotebookLM (có thể chưa đăng nhập, mạng chậm "
                              "hoặc Google đổi giao diện). Xem ảnh notebook_debug.png.")

    def new_chat(self):
        """Đánh dấu: lần hỏi kế tiếp sẽ mở một sổ ghi chú MỚI (không xoá/không dùng lại sổ cũ)."""
        self._check_cancel()
        self._need_new = True
        self.article_id = None

    def _dismiss_intro(self):
        for _ in range(3):
            try:
                if not self.page.evaluate(_JS_CLOSE_INTRO):
                    return
            except Exception:
                return
            time.sleep(0.8)

    def _create_notebook(self, add_fixed=True):
        page = self.page
        self._open_home()
        page.get_by_role("button", name=RX_NEW).first.click()
        try:
            page.wait_for_url(re.compile(r"/notebook/[0-9a-f-]{8,}"), timeout=40000)
        except Exception:
            self._debug("không vào được sổ mới")
            raise GeminiError("Không tạo được sổ ghi chú mới trên NotebookLM.")
        self.url = page.url
        time.sleep(2)
        self._dismiss_intro()
        self.log(f"   📓 Sổ mới: {self.url.split('?')[0]}" + (f" — {self.label}" if self.label else ""))
        self.custom_ok = False
        if not add_fixed:
            return
        for i, src in enumerate(self.fixed_sources, start=1):
            self._add_source(src)
            self.log(f"   + nguồn cố định {i}/{len(self.fixed_sources)} ({len(src):,} ký tự)")
        self._wait_chat_ready()
        self._need_new = False

    def _add_source(self, text):
        page = self.page
        box = page.get_by_placeholder(RX_PASTE_BOX).first
        try:
            visible = box.is_visible()
        except Exception:
            visible = False
        if not visible:
            opt = page.get_by_text(RX_PASTE).first
            try:
                opt_visible = opt.is_visible()
            except Exception:
                opt_visible = False
            if not opt_visible:
                page.get_by_role("button", name=RX_ADD).first.click()
                time.sleep(1)
            page.get_by_text(RX_PASTE).first.click()
        try:
            box.wait_for(timeout=15000)
        except Exception:
            self._debug("không mở được ô dán nguồn")
            raise GeminiError("Không mở được hộp 'Văn bản đã sao chép' của NotebookLM.")
        box.fill(text)
        time.sleep(0.8)
        btn = page.get_by_role("button", name=RX_INSERT).first
        btn.click()
        try:
            box.wait_for(state="hidden", timeout=90000)
        except Exception:
            self._debug("nguồn chưa chèn xong")
            raise GeminiError("NotebookLM không chèn được nguồn (quá thời gian chờ).")
        time.sleep(4)
        self._dismiss_intro()
        self.on_tick()

    # --- luồng "như sếp làm tay": 1 bài = 1 sổ, bài gốc tải lên dạng tệp -------------------------------
    def _visible(self, loc):
        try:
            return loc.is_visible()
        except Exception:
            return False

    def _source_count(self):
        try:
            return int(self.page.evaluate(_JS_SOURCE_COUNT))
        except Exception:
            return -1

    def _wait_sources(self, n, timeout=180):
        t0 = time.time()
        while time.time() - t0 < timeout:
            self._check_cancel()
            self.on_tick()
            if self._source_count() >= n:
                time.sleep(3)
                return True
            time.sleep(2)
        return False

    def _upload_file(self, path):
        """Thêm nguồn > Tải tệp lên > chọn file (đúng như sếp làm tay)."""
        page = self.page
        before = max(0, self._source_count())
        up = page.get_by_role("button", name=RX_UPLOAD).first
        if not self._visible(up):
            up = page.get_by_text(RX_UPLOAD).first
        if not self._visible(up):
            page.get_by_role("button", name=RX_ADD).first.click()
            time.sleep(1.2)
            up = page.get_by_role("button", name=RX_UPLOAD).first
            if not self._visible(up):
                up = page.get_by_text(RX_UPLOAD).first
        with page.expect_file_chooser(timeout=15000) as fc:
            up.click()
        fc.value.set_files(path)
        if not self._wait_sources(before + 1):
            self._debug("tệp tải lên chưa thành nguồn")
            raise GeminiError("NotebookLM chưa nhận tệp bài gốc (quá thời gian chờ).")
        self._dismiss_intro()

    def _add_url(self, url):
        """Thêm nguồn > Trang web (YouTube) > dán link > Chèn. NotebookLM tự lấy bản chép lời của video."""
        page = self.page
        before = max(0, self._source_count())
        box = page.get_by_placeholder(RX_URL_BOX).first
        if not self._visible(box):
            web = page.get_by_role("button", name=RX_WEB).first
            if not self._visible(web):
                page.get_by_role("button", name=RX_ADD).first.click()
                time.sleep(1.2)
                web = page.get_by_role("button", name=RX_WEB).first
            web.click()
        try:
            box.wait_for(timeout=15000)
        except Exception:
            self._debug("không mở được ô dán link")
            raise GeminiError("Không mở được hộp 'URL trang web và YouTube' của NotebookLM.")
        box.fill(url)
        time.sleep(0.8)
        page.get_by_role("button", name=RX_INSERT).first.click()
        try:
            box.wait_for(state="hidden", timeout=90000)
        except Exception:
            self._debug("link chưa chèn xong")
            raise GeminiError("NotebookLM không nhận link YouTube (quá thời gian chờ).")
        if not self._wait_sources(before + 1, timeout=240):
            self._debug("video chưa thành nguồn")
            raise GeminiError("NotebookLM chưa lấy được bản chép lời của video (video riêng tư/không có phụ đề?).")
        self._dismiss_intro()

    def configure_chat(self, rules="", longer=True):
        """⋮ > Định cấu hình cuộc trò chuyện: Tuỳ chỉnh (≤10.000 ký tự) + độ dài 'Dài hơn'. Lỗi thì bỏ qua."""
        page = self.page
        try:
            opened = False
            for _ in range(3):
                page.get_by_role("button", name=RX_NB_MENU).first.click()
                item = page.get_by_text(RX_CHAT_CFG).first
                try:
                    item.wait_for(timeout=4000)
                    item.click()
                    opened = True
                    break
                except Exception:
                    page.keyboard.press("Escape")
                    time.sleep(0.8)
            if not opened:
                raise GeminiError("không mở được menu cấu hình")
            dlg = page.locator("[role=dialog], mat-dialog-container").last
            dlg.wait_for(timeout=8000)
            if rules.strip():
                dlg.get_by_role("radio", name=re.compile(r"chỉnh|custom", re.I)).first.click()
                time.sleep(0.6)
                dlg.get_by_role("textbox").first.fill(rules.strip()[:10000])
            if longer:
                dlg.get_by_role("radio", name=re.compile(r"chi tiết|longer|detailed", re.I)).first.click()
            time.sleep(0.5)
            dlg.locator("button[type=submit]").first.click()
            dlg.wait_for(state="hidden", timeout=10000)
            self.log("   ⚙️ Đã cấu hình chat: " + ("Tuỳ chỉnh" if rules.strip() else "Mặc định")
                     + (" + Dài hơn" if longer else ""))
            return True
        except Exception as e:
            self.log(f"   (bỏ qua bước cấu hình chat: {str(e)[:120]})")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False

    def rename(self, title):
        """Đặt tên sổ (ô tiêu đề ở góc trái trên). Lỗi thì bỏ qua."""
        if not title:
            return
        try:
            for inp in self.page.locator("input").all()[:12]:
                box = inp.bounding_box()
                ph = inp.get_attribute("placeholder") or ""
                if box and box["y"] < 110 and inp.is_visible() and not re.search(r"tìm|search", ph, re.I):
                    inp.click()
                    inp.fill(title[:120])
                    inp.press("Enter")
                    time.sleep(1)
                    return
        except Exception:
            pass

    def open_article(self, file_path=None, title="", chat_rules="", longer=True, url=None):
        """Tạo sổ MỚI cho 1 bài: tải bài lên (tệp) hoặc thêm link YouTube + nguồn cố định + cấu hình chat + đặt tên."""
        self._check_cancel()
        self._create_notebook(add_fixed=False)
        if file_path:
            try:
                self._upload_file(file_path)
                self.log(f"   + tải lên: {os.path.basename(file_path)}")
            except Exception as e:
                self.log(f"   ⚠️ Không tải lên được tệp ({str(e)[:120]}) — dán văn bản thay thế.")
                with open(file_path, "r", encoding="utf-8") as f:
                    self._add_source(f.read())
        elif url:
            self._add_url(url)
            self.log(f"   + thêm video YouTube làm nguồn: {url}")
        for i, src in enumerate(self.fixed_sources, start=1):
            self._add_source(src)
            self.log(f"   + nguồn cố định {i}/{len(self.fixed_sources)} ({len(src):,} ký tự)")
        self.custom_ok = self.configure_chat(chat_rules, longer)
        self.rename(title)
        self._wait_chat_ready()
        self._need_new = False

    def _wait_chat_ready(self, timeout=90):
        t0 = time.time()
        while time.time() - t0 < timeout:
            self._check_cancel()
            self.on_tick()
            try:
                el = self.page.locator(QUERY_BOX).first
                if el.is_visible() and el.is_enabled():
                    return
            except Exception:
                pass
            time.sleep(1.5)
        self._debug("ô chat chưa sẵn sàng")
        raise GeminiError("Ô chat của NotebookLM chưa sẵn sàng (quá thời gian chờ).")

    # --- gửi / nhận ---------------------------------------------------------------------------------
    def _is_generating(self, box):
        try:
            ph = (box.get_attribute("placeholder") or "") + " " + (box.get_attribute("aria-label") or "")
            return bool(re.search(r"đang trả lời|generating|responding", ph, re.I))
        except Exception:
            return False

    @staticmethod
    def _typed_len(box):
        try:
            return len(box.evaluate("e => (e.value !== undefined ? e.value : e.innerText) || ''"))
        except Exception:
            return -1

    def _send_disabled(self):
        """Nút Gửi của ô chat bị khoá (thường do lệnh quá dài)."""
        try:
            return bool(self.page.locator(QUERY_BOX).first.evaluate("""e => {
                let p = e;
                for (let i = 0; i < 6 && p; i++, p = p.parentElement) {
                    const b = Array.from(p.querySelectorAll('button')).find(x =>
                        /^(Gửi|Submit|Send)$/i.test((x.getAttribute('aria-label') || '').trim()));
                    if (b) return b.disabled || b.getAttribute('aria-disabled') === 'true';
                }
                return false;
            }"""))
        except Exception:
            return False

    def _send_via_source(self, full):
        """Lệnh dài: đưa nguyên lệnh vào 1 nguồn rồi gửi chỉ dẫn ngắn trong chat."""
        page = self.page
        self._cmd += 1
        tag = f"[LỆNH #{self._cmd}]"
        self.log(f"   (lệnh dài {len(full):,} ký tự — đưa vào nguồn {tag})")
        try:
            page.locator(QUERY_BOX).first.fill("")
        except Exception:
            pass
        self._add_source(tag + "\n" + full)
        self._wait_chat_ready()
        short = (("" if self.custom_ok else PROMPT_RULES) +
                 f"Thực hiện đầy đủ, chính xác chỉ dẫn trong nguồn có dòng đầu là {tag} (nguồn mới nhất). "
                 f"Chỉ trả về kết quả hoàn chỉnh.")
        box = page.locator(QUERY_BOX).first
        box.click()
        box.fill(short)
        time.sleep(0.5)
        page.keyboard.press("Enter")

    def ask(self, prompt, timeout=1500, first_token_timeout=240):
        self._check_cancel()
        page = self.page
        try:
            page.bring_to_front()
        except Exception:
            pass
        if self._need_new:
            self._create_notebook()
        box = page.locator(QUERY_BOX).first
        full = prompt if self.custom_ok else PROMPT_RULES + prompt
        before = len(page.query_selector_all(ANSWER_SEL))

        box.click()
        too_long = len(full) > CHAT_MAX
        if not too_long:
            box.fill(full)
            time.sleep(0.8)
            too_long = self._typed_len(box) < len(full) * 0.98 or self._send_disabled()
        via_source = False
        if too_long:
            self._send_via_source(full)
            via_source = True
        else:
            page.keyboard.press("Enter")

        t0 = time.time()
        last_len, changed_at, saw_generating = -1, time.time(), False
        text = ""
        while True:
            time.sleep(2)
            self.on_tick()
            self._check_cancel()
            now = time.time()
            elems = page.query_selector_all(ANSWER_SEL)
            if len(elems) <= before:
                # Ô chat vẫn còn nguyên lệnh (không gửi được, VD vượt giới hạn ký tự) -> chuyển sang cách đưa vào nguồn
                if not via_source and now - t0 > 25 and self._typed_len(page.locator(QUERY_BOX).first) > 100:
                    self.log("   (ô chat không gửi được lệnh — chuyển sang đưa lệnh vào nguồn)")
                    self._send_via_source(full)
                    via_source, t0 = True, time.time()
                    continue
                if now - t0 > first_token_timeout:
                    self._debug("không có câu trả lời mới")
                    raise GeminiError("NotebookLM không tạo câu trả lời mới (quá thời gian chờ).")
                continue
            try:
                text = elems[-1].evaluate(_JS_TEXT)
            except Exception:
                continue
            generating = self._is_generating(page.locator(QUERY_BOX).first)
            saw_generating = saw_generating or generating
            if len(text) != last_len:
                last_len, changed_at = len(text), now
            idle = now - changed_at
            if text.strip():
                if saw_generating:
                    if not generating and idle >= 5:
                        break
                elif idle >= 25:
                    break
            if now - t0 > timeout:
                if text.strip():
                    self.log("⚠️ Quá thời gian chờ tối đa, lấy phần đã có.")
                    break
                raise GeminiError("Quá thời gian chờ, NotebookLM không trả về nội dung.")

        text = clean_answer(strip_restart(text, self.log))
        if looks_like_limit_message(text) or (
                len(text) < 600 and re.search(r"đã đạt (đến )?hạn mức|reached (your|the) (usage )?limit", text, re.I)):
            raise GeminiLimitError(f"NotebookLM báo hết lượt/hạn mức: {text[:200]}")
        return text


if __name__ == "__main__":
    # Kiểm tra nhanh: python notebook_client.py --profile gemini_profile  (tạo 1 sổ thử, hỏi 1 câu, KHÔNG xoá gì)
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="gemini_profile")
    a = ap.parse_args()
    with NotebookSession(profile_name=a.profile, fixed_sources=["Kem ABC dưỡng ẩm cho da khô, giá 350.000đ."],
                         label="TEST-AutoContent") as s:
        print(s.ask("Viết đoạn quảng cáo khoảng 80 từ bằng tiếng Việt từ nguồn."))
