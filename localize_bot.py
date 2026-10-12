# -*- coding: utf-8 -*-
"""
Chạy 1 "job" Sáng tạo & Bản địa hoá: với mỗi (bài × quốc gia) -> chat mới trên Gemini (model đã cấu hình),
viết lại/bản địa hoá từng đoạn của bài, (tuỳ chọn) tự soát lại lần 2, lưu 1 file .txt,
cuối cùng nén ZIP.

Cách chạy:  python localize_bot.py --job-dir outputs/jobs/<id>
Trạng thái được ghi liên tục vào <job-dir>/job.json để giao diện đọc tiến độ.
Chạy lại cùng job-dir sẽ BỎ QUA các mục đã xong (tiếp tục sau khi bị ngắt/hết lượt).

Cấu trúc job.json (rút gọn):
  articles: [{id, name, file}]      file nằm trong <job-dir>/sources/
  countries: ["BR", "JP", ...]
  results:  {"<article_id>:<CODE>": {status: pending|running|done|error, file, chars, error, ...}}
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import locales
from gemini_client import (GeminiSession, DryRunSession, GeminiError, GeminiLimitError,
                           GeminiCancelled)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")


def rkey(article_id, code):
    return f"{article_id}:{code}"


# ---------------------------------------------------------------------------
# JSON an toàn (ghi nguyên tử, đọc có thử lại — Windows hay khoá file khi đang đọc)
# ---------------------------------------------------------------------------
def read_json(path, retries=6):
    last = None
    for _ in range(retries):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError) as e:
            last = e
            time.sleep(0.05)
    raise last


def write_json_atomic(path, data, retries=8):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    for i in range(retries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    shutil.copyfile(tmp, path)  # phương án cuối


class Job:
    def __init__(self, job_dir):
        self.dir = job_dir
        self.path = os.path.join(job_dir, "job.json")
        self.log_path = os.path.join(job_dir, "run.log")
        self.cancel_path = os.path.join(job_dir, "cancel.flag")
        self.files_dir = os.path.join(job_dir, "files")
        self.data = read_json(self.path)
        self._last_beat = 0

    def save(self):
        self.data["heartbeat"] = time.time()
        write_json_atomic(self.path, self.data)

    def beat(self):
        now = time.time()
        if now - self._last_beat >= 4:
            self._last_beat = now
            self.save()

    def log(self, msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def cancelled(self):
        return os.path.exists(self.cancel_path)


# ---------------------------------------------------------------------------
# XỬ LÝ 1 MỤC (bài × quốc gia)
# ---------------------------------------------------------------------------
def _chunk_len(cfg, article):
    """Cỡ đoạn: bài thường theo cài đặt; có dàn ý/phân tích thì gửi cả bài một lần nếu <= 28.000 ký tự,
    dài hơn thì cắt ~18.000 ký tự/đoạn (các đoạn gửi tiếp nối trong cùng một cuộc chat)."""
    base = int(cfg.get("chunk_size") or 12000)
    if cfg.get("mode") == "analyze" or article.get("outline_file"):
        total = int(article.get("chars") or 0)
        return 60000 if total <= 28000 else max(base, 18000)
    return base


def process_unit(job, session, article, code, chunks):
    cfg = job.data
    outline = ""
    if article.get("outline_file"):
        try:
            with open(os.path.join(job.dir, "sources", article["outline_file"]), "r", encoding="utf-8") as f:
                outline = f.read().strip()
        except OSError:
            outline = ""
    country = locales.get_country(code)
    res = cfg["results"][rkey(article["id"], code)]
    res.update(status="running", started_at=time.time(), chunks_total=len(chunks), chunks_done=0, error="")
    cfg["current"] = {"article": article["id"], "code": code}
    job.save()
    job.log(f"▶ [{article['name']}] {country['flag']} {country['name_vi']} "
            f"({country['language']}) — {len(chunks)} phần"
            + (f" — theo dàn ý: {article.get('outline_name') or 'có'}" if outline else ""))

    outputs = []
    for i, chunk in enumerate(chunks, start=1):
        prompt = locales.build_prompt(
            chunk, country, cfg.get("style_text", ""), mode=cfg.get("mode", "rewrite"),
            audience=cfg.get("audience", ""), length=cfg.get("length", "same"),
            keywords=cfg.get("keywords", ""), glossary=cfg.get("glossary", ""),
            extra=cfg.get("extra", ""), part=i, parts=len(chunks),
            outline=outline, outline_use=cfg.get("outline_use", "strict"), source_use=cfg.get("source_use", "fresh"))

        last_err = None
        text = ""
        for attempt in (1, 2):
            try:
                job.log(f"   phần {i}/{len(chunks)}: gửi Gemini{' (thử lại)' if attempt > 1 else ''}…")
                text = session.ask(prompt)
                if not text.strip():
                    raise GeminiError("Gemini trả về nội dung rỗng.")
                last_err = None
                break
            except (GeminiLimitError, GeminiCancelled):
                raise
            except GeminiError as e:
                last_err = e
                job.log(f"   ⚠️ {e}")
                if attempt == 1:
                    time.sleep(5)
                    session.new_chat()   # chat mới + chọn lại model rồi thử lại
        if last_err is not None:
            raise last_err

        # --- chốt độ dài: bản ra quá ngắn so với bài gốc thì bắt Gemini viết đầy đủ lại (tối đa 2 lần) ---
        if cfg.get("mode") != "analyze" and cfg.get("length", "same") != "shorter" and len(chunk) > 1500:
            factor = 1.4 if cfg.get("length") == "longer" else 1.0
            want, unit = locales.target_units(chunk, code, factor)
            for rnd in (1, 2):
                have = locales.measure(text, code)
                if have >= 0.8 * want:
                    break
                job.log(f"   ⚠️ bản ra ngắn ({have:,}/{want:,} {unit}) — yêu cầu Gemini viết đầy đủ lại ({rnd}/2)…")
                try:
                    longer = session.ask(locales.build_expand_prompt(country, have, want, unit))
                except (GeminiLimitError, GeminiCancelled):
                    raise
                except GeminiError as e:
                    job.log(f"   (bỏ qua bước nới độ dài: {e})")
                    break
                if locales.measure(longer, code) > have * 1.1:
                    text = longer
                else:
                    break

        if cfg.get("review"):
            job.log(f"   phần {i}/{len(chunks)}: tự soát lại lần 2…")
            try:
                fixed = session.ask(locales.build_review_prompt(
                    country, mode=cfg.get("mode", "rewrite"), part=i, parts=len(chunks), has_outline=bool(outline)))
                if fixed.strip() and len(fixed) >= 0.85 * len(text):
                    text = fixed
                else:
                    job.log("   (bản soát lại ngắn hơn 85% bản đầu — nghi bị rút gọn, giữ bản đầu)")
            except (GeminiLimitError, GeminiCancelled):
                raise
            except GeminiError as e:
                job.log(f"   (bỏ qua bước soát lại: {e})")

        outputs.append(text.strip())
        res["chunks_done"] = i
        job.save()
        time.sleep(2)

    final = "\n\n".join(outputs).strip()
    fname = f"{article['name']}_{code}.txt"
    art_dir = os.path.join(job.files_dir, article["id"])
    os.makedirs(art_dir, exist_ok=True)
    with open(os.path.join(art_dir, fname), "w", encoding="utf-8") as f:
        f.write(final + "\n")
    res.update(status="done", file=f"{article['id']}/{fname}", chars=len(final), finished_at=time.time())
    job.save()
    job.log(f"✅ Xong [{article['name']}] {country['name_vi']}: {len(final)} ký tự -> {fname}")


# ---------------------------------------------------------------------------
# NOTEBOOKLM: 1 bài = 1 sổ (bài gốc là nguồn tệp), mỗi nước = 1 câu lệnh ngắn + tên nước ở cuối,
# tự nhắn "Tiếp tục" khi câu trả lời bị cụt.
# ---------------------------------------------------------------------------
VI_LANG = {
    "US": "tiếng Anh (Mỹ)", "GB": "tiếng Anh (Anh)", "AU": "tiếng Anh (Úc)", "VN": "tiếng Việt",
    "JP": "tiếng Nhật", "KR": "tiếng Hàn", "CN": "tiếng Trung giản thể (đại lục)", "TW": "tiếng Trung phồn thể (Đài Loan)",
    "HK": "tiếng Trung phồn thể (Hồng Kông)", "TH": "tiếng Thái", "ID": "tiếng Indonesia", "MY": "tiếng Mã Lai (Malaysia)",
    "PH": "tiếng Filipino", "IN": "tiếng Hindi", "DE": "tiếng Đức", "FR": "tiếng Pháp", "ES": "tiếng Tây Ban Nha (Tây Ban Nha)",
    "IT": "tiếng Ý", "PT": "tiếng Bồ Đào Nha (Bồ Đào Nha)", "NL": "tiếng Hà Lan", "PL": "tiếng Ba Lan", "SE": "tiếng Thụy Điển",
    "CZ": "tiếng Séc", "RO": "tiếng Romania", "GR": "tiếng Hy Lạp", "RU": "tiếng Nga", "UA": "tiếng Ukraina",
    "TR": "tiếng Thổ Nhĩ Kỳ", "MX": "tiếng Tây Ban Nha (Mexico)", "AR": "tiếng Tây Ban Nha (Argentina)",
    "BR": "tiếng Bồ Đào Nha (Brazil)", "SA": "tiếng Ả Rập (Ả Rập Xê Út)", "EG": "tiếng Ả Rập (Ai Cập)",
    "SAME": "ngôn ngữ gốc của bài",
}

NB_DEFAULT_PROMPT = (
    "Chuyển đổi TOÀN BỘ văn bản trong nguồn \"{TEN_BAI}\" sang {NGON_NGU}.\n"
    "- GIỮ NGUYÊN nội dung, ý, số liệu, tên riêng, thứ tự và độ dài như bản gốc; tuyệt đối không tự ý thêm bớt, không tóm tắt.\n"
    "- Trình bày và định dạng (tiêu đề, đoạn, xuống dòng, gạch đầu dòng) y như bản gốc.\n"
    "- Văn phong tự nhiên như người bản xứ viết, phù hợp với khán giả là {DOI_TUONG}; không dịch word-by-word.\n"
    "- Chỉ trả về bản đã chuyển ngữ, không lời dẫn, không ghi chú.\n"
    "Quốc gia: {QUOC_GIA}")


def nb_prompt(cfg, article, code):
    country = locales.get_country(code)
    lang = VI_LANG.get(code, country["language"])
    vals = {"QUOC_GIA": country["name_vi"], "NGON_NGU": lang, "TEN_BAI": article["name"],
            "DOI_TUONG": (cfg.get("audience") or "").strip() or f"người {country['name_vi']}"}
    tpl = (cfg.get("style_text") or "").strip() or NB_DEFAULT_PROMPT
    has_var = any("{" + k + "}" in tpl for k in vals)
    p = tpl
    for k, v in vals.items():
        p = p.replace("{" + k + "}", v)
    if not has_var:                       # mẫu không có biến: gõ tên nước ở cuối như sếp làm tay
        p += f"\n\nQuốc gia: {country['name_vi']} — viết bằng {lang}."
    if (cfg.get("keywords") or "").strip():
        p += "\nTừ khoá cần giữ/đưa vào: " + ", ".join(x.strip() for x in cfg["keywords"].splitlines() if x.strip())
    if (cfg.get("glossary") or "").strip():
        p += "\nBảng thuật ngữ bắt buộc:\n" + cfg["glossary"].strip()
    if (cfg.get("extra") or "").strip():
        p += "\nYêu cầu thêm: " + cfg["extra"].strip()
    return p


def merge_continuation(prev, new):
    """Nối phần 'Tiếp tục' vào bản trước, bỏ đoạn bị lặp lại ở đầu phần mới."""
    new = (new or "").strip()
    tail = prev[-400:]
    for k in range(min(len(tail), 300), 29, -10):
        seg = tail[-k:]
        i = new.find(seg, 0, k + 600)
        if i != -1:
            new = new[i + len(seg):].lstrip()
            break
    return (prev.rstrip() + "\n\n" + new).strip() if new else prev


def restore_breaks(src, out):
    """Giữ đúng bố cục bài gốc: nếu số đoạn khớp, chèn lại các dòng trống ngăn phần như bản gốc."""
    gaps, gap = [], 0
    for line in (src or "").replace("\r\n", "\n").split("\n"):
        if line.strip():
            gaps.append(gap)
            gap = 0
        else:
            gap += 1
    paras = [p.strip() for p in out.replace("\r\n", "\n").split("\n") if p.strip()]
    if not paras or len(paras) != len(gaps):
        return out.strip()
    s = paras[0]
    for g, p in zip(gaps[1:], paras[1:]):
        s += "\n" * (g + 1) + p
    return s




def find_leaks(text, code):
    """Chữ của ngôn ngữ khác lẫn vào bản dịch (VD: 'dã蠻', 'conveyed' trong bản Trung, '帝국의')."""
    pats = []
    if code not in ("KR", "SAME"):
        pats.append(r"[\uac00-\ud7a3\u1100-\u11ff]+")
    if code not in ("CN", "TW", "HK", "JP", "KR", "SAME"):
        pats.append(r"[\u3040-\u30ff\u3400-\u9fff]+")
    if code in ("CN", "TW", "HK", "JP"):
        pats.append(r"(?<![A-Za-z])[a-z][A-Za-z]{2,}(?![A-Za-z])")   # từ tiếng Anh viết thường (bỏ qua AI, USB...)
    leaks = []
    for pat in pats:
        for m in re.finditer(pat, text):
            snip = text[max(0, m.start() - 4):m.end() + 4].replace("\n", " ").strip()
            if snip not in leaks:
                leaks.append(snip)
    return leaks[:30]


def nb_proofread(job, session, text, code):
    """Hỏi NotebookLM liệt kê lỗi dạng 'sai -> đúng' (không bắt viết lại toàn văn, nên không bị cụt), rồi Tool tự thay."""
    country = locales.get_country(code)
    lang = VI_LANG.get(code, country["language"])
    leaks = find_leaks(text, code)
    if leaks:
        job.log(f"   ⚠️ nghi lẫn chữ ngôn ngữ khác: {', '.join(leaks[:8])}")
    prompt = (
        f"Soát lỗi bản {lang} bạn vừa viết, đối chiếu với nguồn gốc. Chỉ liệt kê LỖI THẬT: sai chính tả, gõ nhầm, từ dùng sai "
        f"nghĩa hoặc không tự nhiên với người bản xứ, chữ/từ của ngôn ngữ khác lẫn vào, câu thêm ý không có trong gốc, "
        f"sai nghĩa so với gốc.\n"
        + (f"Bắt buộc sửa các chỗ lẫn chữ này: {', '.join(leaks)}\n" if leaks else "")
        + "Trả về DUY NHẤT một mảng JSON, mỗi phần tử dạng {\"sai\": \"đoạn NGUYÊN VĂN đang có trong bản viết (3-15 từ)\", "
        "\"dung\": \"đoạn thay thế\"}. Không có lỗi thì trả về []. Không giải thích.")
    ans = session.ask(prompt)
    i, j = ans.find("["), ans.rfind("]")
    if i == -1 or j <= i:
        job.log("   (soát lỗi: không đọc được danh sách lỗi)")
        return text
    try:
        items = json.loads(ans[i:j + 1])
    except ValueError:
        job.log("   (soát lỗi: danh sách lỗi sai định dạng)")
        return text
    fixed = 0
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        bad, good = str(it.get("sai") or ""), str(it.get("dung") or "")
        if bad and good and bad != good and len(bad) <= 300 and bad in text:
            text = text.replace(bad, good, 1)
            fixed += 1
    job.log(f"   🔍 soát lỗi: sửa {fixed}/{len(items) if isinstance(items, list) else 0} chỗ")
    rest = find_leaks(text, code)
    if rest:
        job.log(f"   ⚠️ còn chữ lạ chưa sửa được: {', '.join(rest[:8])} — sếp xem lại.")
    return text


def process_unit_nb(job, session, article, code):
    cfg = job.data
    country = locales.get_country(code)
    with open(os.path.join(job.dir, "sources", article["file"]), "r", encoding="utf-8") as f:
        src = f.read()
    res = cfg["results"][rkey(article["id"], code)]
    res.update(status="running", started_at=time.time(), chunks_total=1, chunks_done=0, error="")
    cfg["current"] = {"article": article["id"], "code": code}
    job.save()
    job.log(f"▶ [{article['name']}] {country['flag']} {country['name_vi']} — NotebookLM")

    text = ""
    for attempt in (1, 2):
        try:
            text = session.ask(nb_prompt(cfg, article, code))
            if not text.strip():
                raise GeminiError("NotebookLM trả về nội dung rỗng.")
            break
        except (GeminiLimitError, GeminiCancelled):
            raise
        except GeminiError as e:
            job.log(f"   ⚠️ {e}")
            if attempt == 2:
                raise
            time.sleep(5)

    # Bị cụt (giới hạn độ dài 1 câu trả lời) -> nhắn "Tiếp tục" và nối lại, tối đa 8 lượt.
    if cfg.get("mode") != "analyze" and cfg.get("length", "same") != "shorter" and len(src) > 1500:
        factor = 1.4 if cfg.get("length") == "longer" else 1.0
        want, unit = locales.target_units(src, code, factor)
        for rnd in range(1, 9):
            have = locales.measure(text, code)
            if have >= 0.9 * want:
                break
            job.log(f"   ↪ mới {have:,}/{want:,} {unit} — nhắn 'Tiếp tục' ({rnd}/8)…")
            res["chunks_total"] = rnd + 1
            job.save()
            last = text.strip()[-160:].replace("\n", " ")
            try:
                more = session.ask(
                    f"Tiếp tục bản {VI_LANG.get(code, country['language'])} từ ĐÚNG chỗ vừa dừng (ngay sau đoạn: "
                    f"\"…{last}\"). Không lặp lại phần đã viết, không lời dẫn. Nếu đã chuyển hết bài thì chỉ trả lời "
                    f"đúng một từ: HẾT")
            except (GeminiLimitError, GeminiCancelled):
                raise
            except GeminiError as e:
                job.log(f"   (dừng bước tiếp tục: {e})")
                break
            if re.fullmatch(r"\W*(HẾT|HET|END|DONE)\W*", more.strip(), re.I) or len(more.strip()) < 40:
                break
            merged = merge_continuation(text, more)
            if len(merged) <= len(text) + 40:
                break
            text = merged
        have = locales.measure(text, code)
        if have < 0.8 * want:
            job.log(f"   ⚠️ bản ra vẫn ngắn ({have:,}/{want:,} {unit}) — sếp kiểm tra lại bản này.")

    text = re.sub(r"\n?\s*\bHẾT\W*$", "", text.strip()).strip()
    try:
        text = nb_proofread(job, session, text, code)
    except (GeminiLimitError, GeminiCancelled):
        raise
    except Exception as e:
        job.log(f"   (bỏ qua bước soát lỗi: {str(e)[:120]})")
    final = restore_breaks(src, text)
    fname = f"{article['name']}_{code}.txt"
    art_dir = os.path.join(job.files_dir, article["id"])
    os.makedirs(art_dir, exist_ok=True)
    with open(os.path.join(art_dir, fname), "w", encoding="utf-8") as f:
        f.write(final + "\n")
    res.update(status="done", file=f"{article['id']}/{fname}", chars=len(final), chunks_done=res.get("chunks_total", 1),
               finished_at=time.time())
    job.save()
    job.log(f"✅ Xong [{article['name']}] {country['name_vi']}: {len(final):,} ký tự (gốc {len(src):,}) -> {fname}")


def nb_open_article(job, session, article):
    """Sổ mới cho bài: tải bài gốc lên dạng tệp mang đúng tên bài (giống thao tác tay của sếp)."""
    cfg = job.data
    nb = cfg.get("nb") or {}
    up_dir = os.path.join(job.dir, "upload")
    os.makedirs(up_dir, exist_ok=True)
    path = os.path.join(up_dir, f"{article['name']}.txt")
    shutil.copyfile(os.path.join(job.dir, "sources", article["file"]), path)
    from notebook_client import BASE_CHAT_RULES
    rules = (BASE_CHAT_RULES + "\n\n" + (nb.get("chat_rules") or "")).strip()
    title = " | ".join(x for x in (article["name"], nb.get("type")) if x)
    session.open_article(path, title=title, chat_rules=rules, longer=nb.get("longer", True))
    session.article_id = article["id"]


class DryNotebook(DryRunSession):
    article_id = None

    def open_article(self, path, **k):
        self.log(f"[CHẠY THỬ] sổ mới + tải lên {os.path.basename(path)}")

    def ask(self, prompt, **k):
        if prompt.startswith("Tiếp tục"):
            return "HẾT"
        if prompt.startswith("Soát lỗi"):
            return "[]"
        return f"[CHẠY THỬ NotebookLM] {prompt[:200]}"


# ---------------------------------------------------------------------------
# ĐÓNG GÓI
# ---------------------------------------------------------------------------
def finalize(job):
    cfg = job.data
    done = [(k, r) for k, r in cfg["results"].items() if r.get("status") == "done" and r.get("file")]
    arts = {a["id"]: a for a in cfg["articles"]}
    cfg["zip"] = None
    cfg["history_files"] = []
    if done:
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        if len(done) == 1:
            k, r = done[0]
            name = os.path.basename(r["file"])
            shutil.copyfile(os.path.join(job.files_dir, r["file"]), os.path.join(OUTPUT_FOLDER, name))
            cfg["history_files"] = [name]
        else:
            multi = len(cfg["articles"]) > 1
            zip_name = f"{cfg['base_name']}_BanDia_{cfg['id'][:6]}.zip"
            with zipfile.ZipFile(os.path.join(OUTPUT_FOLDER, zip_name), "w", zipfile.ZIP_DEFLATED) as z:
                for k, r in done:
                    aid = k.split(":", 1)[0]
                    arcname = (f"{arts[aid]['name']}/{os.path.basename(r['file'])}" if multi
                               else os.path.basename(r["file"]))
                    z.write(os.path.join(job.files_dir, r["file"]), arcname)
            cfg["zip"] = zip_name
            cfg["history_files"] = [zip_name]
        try:  # thời gian xử lý hiện trong tab Lịch Sử
            meta_path = os.path.join(OUTPUT_FOLDER, "metadata.json")
            meta = read_json(meta_path) if os.path.exists(meta_path) else {}
            secs = int(time.time() - cfg.get("started_at", time.time()))
            try:
                import gemini_client
                a = gemini_client.load_accounts().get(cfg.get("profile") or "gemini_profile") or {}
                acct = " ".join(x for x in (a.get("name"), "(" + a["email"] + ")" if a.get("email") else "") if x)
            except Exception:
                acct = ""
            cfg["account"] = acct
            for h in cfg["history_files"]:
                meta[h] = {"processing_time": secs, "count": len(done), "account": acct,
                           "countries": list(cfg.get("countries") or [])}
            write_json_atomic(meta_path, meta)
        except Exception:
            pass

    n_err = sum(1 for r in cfg["results"].values() if r.get("status") == "error")
    n_wait = sum(1 for r in cfg["results"].values() if r.get("status") in ("pending", "running"))
    if job.cancelled():
        cfg["state"] = "cancelled"
    elif not done:
        cfg["state"] = "error"
    elif n_err or n_wait:
        cfg["state"] = "partial"
    else:
        cfg["state"] = "done"
    cfg["current"] = None
    cfg["finished_at"] = time.time()
    job.save()


# ---------------------------------------------------------------------------
# CHẠY JOB
# ---------------------------------------------------------------------------
def run_job(job_dir, session_factory=None):
    job = Job(job_dir)
    cfg = job.data
    if os.path.exists(job.cancel_path):
        os.remove(job.cancel_path)          # chạy lại/tiếp tục thì bỏ cờ huỷ cũ
    cfg["state"] = "running"
    cfg.setdefault("started_at", time.time())
    cfg["error"] = ""
    cfg["finished_at"] = None
    for a in cfg["articles"]:
        for code in cfg["countries"]:
            r = cfg["results"].setdefault(rkey(a["id"], code), {"status": "pending"})
            if r.get("status") in ("error", "running"):
                r["status"] = "pending"      # chạy lại các mục từng lỗi/bị ngắt
    job.save()

    # Mục cần làm theo thứ tự: xong trọn từng bài (mọi quốc gia) rồi mới sang bài kế.
    todo = []
    for a in cfg["articles"]:
        for code in cfg["countries"]:
            r = cfg["results"][rkey(a["id"], code)]
            f = r.get("file")
            if r.get("status") == "done" and f and os.path.exists(os.path.join(job.files_dir, f)):
                job.log(f"⏭️  [{a['name']}] {code}: đã xong từ trước, bỏ qua.")
            else:
                r["status"] = "pending"
                todo.append((a, code))

    is_nb = cfg.get("engine") == "notebook"
    if session_factory is None:
        if is_nb and cfg.get("dry_run"):
            session_factory = lambda: DryNotebook(log=job.log, on_tick=job.beat, should_cancel=job.cancelled)
        elif cfg.get("dry_run"):
            session_factory = lambda: DryRunSession(log=job.log, on_tick=job.beat, should_cancel=job.cancelled)
        elif cfg.get("engine") == "notebook":
            from notebook_client import NotebookSession
            nb = cfg.get("nb") or {}
            session_factory = lambda: NotebookSession(
                profile_name=cfg.get("profile") or "gemini_profile", fixed_sources=nb.get("fixed_sources") or [],
                label=" / ".join(x for x in (nb.get("folder"), nb.get("type")) if x),
                log=job.log, on_tick=job.beat, should_cancel=job.cancelled)
        else:
            session_factory = lambda: GeminiSession(
                profile_name=cfg.get("profile") or "gemini_profile", model=cfg.get("model"),
                thinking=cfg.get("thinking"), log=job.log, on_tick=job.beat, should_cancel=job.cancelled)

    session = None
    chunk_cache = {}
    try:
        if todo:
            job.log(f"Bắt đầu job {cfg['id'][:8]}: {len(todo)} mục (bài × quốc gia), model: "
                    f"{'(chạy thử)' if cfg.get('dry_run') else cfg.get('model')}")
            session = session_factory()
            session.start()
            first = True
            for article, code in todo:
                if job.cancelled():
                    job.log("⛔ Đã huỷ.")
                    break
                key = rkey(article["id"], code)
                try:
                    if is_nb:
                        if getattr(session, "article_id", None) != article["id"]:
                            nb_open_article(job, session, article)
                        process_unit_nb(job, session, article, code)
                        job.save()
                        continue
                    if article["id"] not in chunk_cache:
                        with open(os.path.join(job.dir, "sources", article["file"]), "r", encoding="utf-8") as f:
                            chunk_cache[article["id"]] = locales.split_text(f.read(), _chunk_len(cfg, article))
                    chunks = chunk_cache[article["id"]]
                    if not chunks:
                        raise GeminiError("Bài gốc trống.")
                    if not first:
                        session.new_chat()
                    first = False
                    process_unit(job, session, article, code, chunks)
                except GeminiCancelled:
                    cfg["results"][key]["status"] = "pending"
                    job.log("⛔ Đã huỷ.")
                    break
                except GeminiLimitError as e:
                    cfg["results"][key].update(status="error", error=str(e))
                    cfg["error"] = ("Gemini báo hết lượt/giới hạn. Phần đã xong vẫn được giữ — "
                                    "bấm 'Tiếp tục' khi lượt được làm mới.")
                    job.log(f"⛔ {e}")
                    break
                except GeminiError as e:
                    cfg["results"][key].update(status="error", error=str(e))
                    job.log(f"❌ [{article['name']}] {code}: {e}")
                    # lỗi cấu hình toàn cục (chưa đăng nhập, không chọn được model) -> dừng cả job
                    if any(k in str(e) for k in ("đăng nhập", "model", "Chrome")):
                        cfg["error"] = str(e)
                        break
                    job.save()
                    try:
                        session.new_chat()
                        first = True
                    except GeminiError:
                        pass
                except Exception as e:  # lỗi bất ngờ của 1 mục không được làm hỏng cả job
                    cfg["results"][key].update(status="error", error=f"{type(e).__name__}: {e}")
                    job.log(f"❌ [{article['name']}] {code}: {type(e).__name__}: {e}")
                job.save()
    except GeminiError as e:
        cfg["error"] = str(e)
        job.log(f"❌ {e}")
    except Exception as e:
        cfg["error"] = f"{type(e).__name__}: {e}"
        job.log(f"❌ Lỗi bất ngờ: {type(e).__name__}: {e}")
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        for article, code in todo:         # mục chưa chạy tới do job dừng sớm -> đánh dấu rõ nguyên nhân
            r = cfg["results"][rkey(article["id"], code)]
            if r.get("status") == "pending" and cfg.get("error") and not job.cancelled():
                r.update(status="error", error=cfg["error"])
        finalize(job)
        job.log(f"Kết thúc job: {cfg['state']}")
    return cfg


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-dir", required=True)
    a = ap.parse_args()
    run_job(a.job_dir)
