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
                if fixed.strip() and len(fixed) >= 0.4 * len(text):
                    text = fixed
                else:
                    job.log("   (bản soát lại quá ngắn/rỗng — giữ bản đầu)")
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
            for h in cfg["history_files"]:
                meta[h] = {"processing_time": secs}
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

    if session_factory is None:
        if cfg.get("dry_run"):
            session_factory = lambda: DryRunSession(log=job.log, on_tick=job.beat, should_cancel=job.cancelled)
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
                    if article["id"] not in chunk_cache:
                        with open(os.path.join(job.dir, "sources", article["file"]), "r", encoding="utf-8") as f:
                            chunk_cache[article["id"]] = locales.split_text(f.read(), max(int(cfg.get("chunk_size") or 12000), 60000) if (cfg.get("mode") == "analyze" or article.get("outline_file")) else int(cfg.get("chunk_size") or 12000))
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
