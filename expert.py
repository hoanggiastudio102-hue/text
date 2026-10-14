# -*- coding: utf-8 -*-
"""
"VIẾT CHUYÊN GIA" — quy trình nhiều bước, ghép ý từ các repo GitHub nhiều sao:

  1. Lập kế hoạch từ dàn ý      (THUDM/LongWriter — AgentWrite: chia mục + số chữ từng mục)
  2. Viết từng mục nối tiếp     (cùng 1 chat để giữ giọng; mục thiếu chữ tự nhắn "Tiếp tục")
  3. Tự soát                    (madaan/self-refine: tự phê bình -> sửa, tối đa 2 vòng)
  4. Soát chéo bằng AI khác     (karpathy/llm-council: AI khác soát ẩn danh, AI viết làm "chủ tịch" chốt)
  5. Sửa văn AI cho giống người (blader/humanizer: các dấu hiệu "văn AI" theo hướng dẫn của Wikipedia)
  6. Máy kiểm tra cuối          (languagetool-org/languagetool + soát máy sẵn có: số liệu, chữ lẫn, đoạn lệch)

Mọi chỗ sửa / nghi lỗi được ghi theo SỐ ĐOẠN vào báo cáo <bài>_ra_soat.txt và res["review_items"] để hiện trên giao diện.
Sửa theo từng ĐOẠN (AI trả về cả đoạn đã sửa) -> không bắt viết lại cả bài, không bị cụt.
"""
import json
import re
import time

import review_check as rc

BATCH = 12
NAMES = {"gemini": "Gemini", "chatgpt": "ChatGPT", "claude": "Claude"}

DEFAULTS = {"on": False, "self": True, "cross": [], "human": True, "machine": True, "lt": "off",
            "lt_url": "http://localhost:8081/v2/check", "outline": False, "words": 0}


def options(raw):
    o = dict(DEFAULTS)
    o.update({k: v for k, v in (raw or {}).items() if k in DEFAULTS})
    o["cross"] = [x for x in (o.get("cross") or []) if x in NAMES]
    return o


# ------------------------------------------------------------------------------------------------ tiện ích
def _err_is_hard(e):
    return type(e).__name__ in ("GeminiCancelled",)


def parse_json(ans, kind="list"):
    """Lấy JSON đầu tiên (mảng hoặc object) trong câu trả lời của AI."""
    if not ans:
        return None
    s = re.sub(r"```(?:json)?", "", ans)
    o, c = ("[", "]") if kind == "list" else ("{", "}")
    a, b = s.find(o), s.rfind(c)
    if a == -1 or b <= a:
        return None
    raw = s[a:b + 1]
    for cand in (raw, re.sub(r",\s*([\]}])", r"\1", raw)):
        try:
            data = json.loads(cand)
            if (kind == "list" and isinstance(data, list)) or (kind == "dict" and isinstance(data, dict)):
                return data
        except ValueError:
            continue
    return None


def numbered(paras, i, j):
    return "\n".join(f"[{k + 1}] {paras[k]}" for k in range(i, j))


def ref_block(ref, i, j, n_out):
    """Tài liệu gốc cho lô đoạn [i, j): ngắn thì gửi cả, dài thì cắt phần tương ứng theo tỉ lệ."""
    ref = (ref or "").strip()
    if len(ref) <= 9000:
        return ref
    rp = rc.paragraphs(ref)
    a, b = rc.src_range(i, j, len(rp), n_out)
    return "\n".join(rp[a:b])


def _ok_fix(old, new):
    new = (new or "").strip()
    return bool(new) and new != old and 0.6 * len(old) <= len(new) <= 2.5 * len(old) + 60


def _flat(s):
    return re.sub(r"\s*\n\s*", " ", (s or "").strip())


class Log:
    """Gom mọi chỗ sửa/nghi lỗi để ghi báo cáo + hiện trên giao diện."""

    def __init__(self):
        self.items = []

    def add(self, step, who, p, issue, old="", new="", applied=True, kind=""):
        self.items.append({"step": step, "ai": who, "p": p, "issue": (issue or "").strip()[:300], "kind": kind,
                           "old": (old or "")[:1500], "new": (new or "")[:1500], "applied": bool(applied)})


# ------------------------------------------------------------------------------------------------ hội đồng soát
class Panel:
    """Các AI soát chéo (mỗi AI 1 cửa sổ Chrome riêng). Mở khi cần, AI nào lỗi 2 lần thì tạm bỏ cho cả job."""

    def __init__(self, job, names, dry=False):
        self.job, self.names, self.dry = job, list(names), dry
        self.sessions, self.dead, self.fails = {}, set(), {}

    def alive(self):
        return [n for n in self.names if n not in self.dead]

    def get(self, name):
        if name in self.dead:
            return None
        if name in self.sessions:
            return self.sessions[name]
        job = self.job
        try:
            if self.dry:
                s = DryReviewer(name)
            else:
                import web_chat
                s = web_chat.make_session(name, log=job.log, on_tick=job.beat, should_cancel=job.cancelled)
            s.start()
            self.sessions[name] = s
            return s
        except Exception as e:
            if _err_is_hard(e):
                raise
            job.log(f"   ⚠️ Không mở được {NAMES[name]} để soát chéo: {str(e)[:160]} — bỏ {NAMES[name]} cho job này.")
            self.dead.add(name)
            return None

    def ask(self, name, prompt):
        s = self.get(name)
        if s is None:
            return None
        for attempt in (1, 2):
            try:
                s.new_chat()
                return s.ask(prompt)
            except Exception as e:
                if _err_is_hard(e):
                    raise
                limit = type(e).__name__ == "GeminiLimitError"
                self.job.log(f"   ({NAMES[name]} lỗi: {str(e)[:120]}{'' if limit or attempt == 2 else ' — thử lại'})")
                if limit:
                    break
        self.fails[name] = self.fails.get(name, 0) + 1
        if self.fails[name] >= 2:
            self.job.log(f"   ⚠️ {NAMES[name]} lỗi liên tiếp — bỏ {NAMES[name]} khỏi hội đồng soát cho job này.")
            self.dead.add(name)
        return None

    def close(self):
        for s in self.sessions.values():
            try:
                s.close()
            except Exception:
                pass
        self.sessions = {}


class DryReviewer:
    def __init__(self, name):
        self.name = NAMES.get(name, name)

    def start(self):
        pass

    def close(self):
        pass

    def new_chat(self):
        pass

    def ask(self, prompt, **k):
        time.sleep(0.2)
        return "[]"


# ------------------------------------------------------------------------------------------------ bước 1-2
def plan_and_write(job, session, base_prompt, code, lang, words=0):
    """Dàn ý -> kế hoạch (mục + số chữ + ý bắt buộc) -> viết từng mục. Trả (text, plan) hoặc (None, None)."""
    import locales
    job.log("   🧭 Bước 1: lập kế hoạch viết từ dàn ý…")
    want = f"Tổng độ dài khoảng {words:,} từ." if words else "Tự chọn độ dài hợp lý cho từng mục để bài đầy đủ, sâu."
    ans = session.ask(
        base_prompt + "\n\n---\nĐây là BƯỚC LẬP KẾ HOẠCH, CHƯA viết bài. Bám đúng thứ tự dàn ý, không bỏ mục nào. " + want +
        "\nTrả về DUY NHẤT một mảng JSON, mỗi phần tử: {\"muc\": \"tên mục\", \"so_tu\": số từ cần viết, "
        "\"y_chinh\": [\"ý bắt buộc 1\", \"ý bắt buộc 2\", ...]}. Không giải thích.")
    plan = parse_json(ans, "list")
    plan = [p for p in (plan or []) if isinstance(p, dict) and str(p.get("muc") or "").strip()]
    if not plan:
        job.log("   (không đọc được kế hoạch — viết theo cách thường)")
        return None, None
    plan = plan[:30]
    job.log(f"   Kế hoạch: {len(plan)} mục — " + "; ".join(f"{p['muc'][:40]} (~{p.get('so_tu', '?')} từ)" for p in plan[:8])
            + (" …" if len(plan) > 8 else ""))
    outs = []
    for i, p in enumerate(plan, start=1):
        try:
            n = int(re.sub(r"\D", "", str(p.get("so_tu") or "")) or 0)
        except ValueError:
            n = 0
        ys = [str(y) for y in (p.get("y_chinh") or []) if str(y).strip()][:12]
        pos = ("Đây là mục ĐẦU: có câu mở bài cuốn hút." if i == 1 else
               "Đây là mục CUỐI: kết bài tự nhiên, không sáo rỗng." if i == len(plan) else
               "Nối mạch với mục trước; không mở bài hay kết luận riêng cho mục này.")
        job.log(f"   ✍️ Bước 2: viết mục {i}/{len(plan)}: {p['muc'][:60]}…")
        t = session.ask(
            f"Viết MỤC {i}/{len(plan)}: \"{p['muc']}\" bằng {lang}" + (f", khoảng {n} từ" if n else "") + ".\n"
            + ("Phải có đủ các ý: " + "; ".join(ys) + ".\n" if ys else "") + pos +
            " Viết như chuyên gia thật sự am hiểu: cụ thể, có chi tiết/ví dụ, câu dài ngắn đan xen. Chỉ trả về nội dung "
            "mục này (được ghi tiêu đề mục nếu bài cần tiêu đề), không lời dẫn.")
        if n and len(t) > 200:
            for rnd in (1, 2):
                if locales.measure(t, code) >= 0.75 * n:
                    break
                job.log(f"   ↪ mục {i} mới {locales.measure(t, code)}/{n} từ — nhắn 'Tiếp tục'…")
                more = session.ask("Tiếp tục viết mục này từ đúng chỗ vừa dừng, không lặp lại, không lời dẫn. "
                                   "Nếu mục đã đủ ý thì chỉ trả lời: HẾT")
                if re.fullmatch(r"\W*(HẾT|HET|END|DONE)\W*", more.strip(), re.I) or len(more.strip()) < 40:
                    break
                t = t.rstrip() + "\n\n" + more.strip()
        outs.append(t.strip())
    return "\n\n".join(outs), plan


# ------------------------------------------------------------------------------------------------ bước 3
def self_refine(job, session, ref, paras, lang, who, log):
    """Chính AI viết tự soát (ở cùng chat), sửa theo đoạn + bổ sung ý thiếu. Tối đa 2 vòng."""
    for rnd in (1, 2):
        n = len(paras)
        changed = 0
        whole = sum(len(p) for p in paras) <= 20000
        step = n if whole else BATCH
        adds = []
        for i in range(0, n, step):
            j = min(n, i + step)
            job.log(f"   🔁 Bước 3: tự soát vòng {rnd} — đoạn {i + 1}–{j}/{n}…")
            ask_missing = whole
            ans = session.ask(
                "Hãy đóng vai biên tập viên khó tính, TỰ SOÁT bản bạn vừa viết (đánh số đoạn bên dưới), đối chiếu với "
                "TÀI LIỆU GỐC/DÀN Ý. Tìm lỗi thật: sai nghĩa/sai dữ kiện, ý bịa, lặp ý, lỗi chính tả - ngữ pháp, câu "
                f"lủng củng hoặc không tự nhiên với người bản xứ {lang}.\n"
                "Trả về DUY NHẤT một object JSON: {\"sua\": [{\"p\": số đoạn, \"issue\": \"lý do ngắn bằng tiếng Việt\", "
                f"\"fixed\": \"TOÀN BỘ đoạn đã sửa bằng {lang}\"}}]"
                + (", \"thieu_y\": [{\"y\": \"ý trong dàn ý/bản gốc còn thiếu\", \"sau_doan\": số đoạn để chèn sau, "
                   f"\"noi_dung\": \"đoạn văn bổ sung hoàn chỉnh bằng {lang}\"}}]" if ask_missing else "")
                + "}. Không rút gọn đoạn. Không có lỗi thì trả về {\"sua\": []" + (", \"thieu_y\": []" if ask_missing else "")
                + "}.\n\nTÀI LIỆU GỐC/DÀN Ý:\n" + ref_block(ref, i, j, n) + "\n\nBẢN VIẾT:\n" + numbered(paras, i, j))
            data = parse_json(ans, "dict")
            if data is None:
                lst = parse_json(ans, "list")
                data = {"sua": lst or []}
            for it in data.get("sua") or []:
                if not isinstance(it, dict):
                    continue
                try:
                    k = int(str(it.get("p")).strip("[] ")) - 1
                except (TypeError, ValueError):
                    continue
                if not (i <= k < j) or not _ok_fix(paras[k], it.get("fixed")):
                    continue
                old = paras[k]
                paras[k] = _flat(it["fixed"])
                changed += 1
                log.add("Tự soát", who, k + 1, it.get("issue") or "sửa diễn đạt", old, paras[k])
            for it in data.get("thieu_y") or []:
                if isinstance(it, dict) and len(str(it.get("noi_dung") or "").strip()) > 40:
                    try:
                        after = int(str(it.get("sau_doan")).strip("[] "))
                    except (TypeError, ValueError):
                        after = len(paras)
                    adds.append((max(0, min(len(paras), after)), _flat(it["noi_dung"]), str(it.get("y") or "")))
        for after, txt, y in sorted(adds, key=lambda x: -x[0]):
            paras.insert(after, txt)
            changed += 1
            log.add("Tự soát", who, after + 1, "bổ sung ý còn thiếu: " + y, "", txt, kind="them")
        job.log(f"   tự soát vòng {rnd}: sửa {changed} chỗ")
        if not changed:
            break
    return paras


# ------------------------------------------------------------------------------------------------ bước 4
def _review_prompt(ref, paras, i, j, lang, audience):
    return (
        f"Bạn là tổng biên tập, người bản xứ {lang}, am hiểu sâu chủ đề của bài. Soát BẢN VIẾT (đoạn đánh số [n]) đối "
        "chiếu với TÀI LIỆU GỐC/DÀN Ý. Chỉ nêu LỖI THẬT: sai nghĩa hoặc sai dữ kiện so với tài liệu gốc, thiếu ý quan trọng, "
        "ý bịa không có căn cứ, sai số liệu/tên/ngày, lỗi chính tả, ngữ pháp, dùng từ sai, câu không tự nhiên với người "
        f"đọc {audience or 'bản xứ'}, lặp ý, giọng văn máy móc kiểu AI.\n"
        "Trả về DUY NHẤT một mảng JSON: [{\"p\": số đoạn, \"loai\": \"sai dữ kiện|thiếu ý|chính tả|ngữ pháp|dùng từ|"
        "diễn đạt|lặp|văn AI\", \"muc_do\": 1-3 (3 = nghiêm trọng), \"issue\": \"lý do ngắn bằng tiếng Việt\", "
        f"\"fixed\": \"TOÀN BỘ đoạn đã sửa bằng {lang}\"}}]. Chỉ đưa đoạn cần sửa; không rút gọn đoạn, giữ phong cách. "
        "Không có lỗi thì trả về [].\n\nTÀI LIỆU GỐC/DÀN Ý:\n" + ref_block(ref, i, j, len(paras)) +
        "\n\nBẢN VIẾT:\n" + numbered(paras, i, j))


def _sev(it):
    m = re.search(r"\d", str(it.get("muc_do") or ""))
    return int(m.group()) if m else 1


def cross_review(job, panel, chair, ref, paras, lang, audience, log, writer_name):
    """Các AI khác soát ẩn danh. 1 AI soát -> áp thẳng; >=2 AI -> AI viết làm chủ tịch chốt từng đoạn."""
    reviewers = panel.alive()
    if not reviewers:
        return paras
    n = len(paras)
    sugg = {}      # k -> [(name, item)]
    for i in range(0, n, BATCH):
        j = min(n, i + BATCH)
        for name in panel.alive():
            job.log(f"   🧐 Bước 4: {NAMES[name]} soát chéo đoạn {i + 1}–{j}/{n}…")
            ans = panel.ask(name, _review_prompt(ref, paras, i, j, lang, audience))
            items = parse_json(ans or "", "list")
            if items is None:
                if ans:
                    job.log(f"   ({NAMES[name]}: không đọc được kết quả soát lô này)")
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                try:
                    k = int(str(it.get("p")).strip("[] Tt")) - 1
                except (TypeError, ValueError):
                    continue
                if i <= k < j and _ok_fix(paras[k], it.get("fixed")):
                    sugg.setdefault(k, []).append((name, it))
    if not sugg:
        job.log("   soát chéo: không thấy lỗi cần sửa")
        return paras
    if len(reviewers) == 1 or chair is None:
        for k, lst in sorted(sugg.items()):
            name, it = lst[0]
            old = paras[k]
            paras[k] = _flat(it["fixed"])
            log.add("Soát chéo", NAMES[name], k + 1, f"[{it.get('loai') or 'lỗi'}] {it.get('issue') or ''}", old, paras[k],
                    kind=str(it.get("loai") or ""))
        job.log(f"   soát chéo: sửa {len(sugg)} đoạn")
        return paras
    # Chủ tịch (AI viết) chốt từng đoạn, góp ý ẩn tên A/B/C
    keys = sorted(sugg)
    decided = 0
    for x in range(0, len(keys), 8):
        part = keys[x:x + 8]
        blocks = []
        for k in part:
            opts = "\n".join(f"  Góp ý {chr(65 + m)} ({it.get('loai') or 'lỗi'}, mức {it.get('muc_do') or '?'}): "
                             f"{it.get('issue') or ''}\n  Bản sửa {chr(65 + m)}: {_flat(it['fixed'])}"
                             for m, (_, it) in enumerate(sugg[k]))
            blocks.append(f"[{k + 1}] HIỆN TẠI: {paras[k]}\n{opts}")
        job.log(f"   ⚖️ Bước 4: {writer_name} làm chủ tịch hội đồng, chốt {len(part)} đoạn có góp ý…")
        try:
            ans = chair.ask(
                "Hội đồng biên tập (các AI khác, đã ẩn tên) góp ý cho bài bạn vừa viết. Với MỖI đoạn dưới đây, hãy quyết "
                "định bản cuối cùng: giữ nguyên nếu góp ý sai, chọn một bản sửa, hoặc tự viết bản kết hợp tốt nhất. "
                "Ưu tiên đúng dữ kiện, đủ ý, tự nhiên như người bản xứ viết.\n"
                "Trả về DUY NHẤT mảng JSON: [{\"p\": số đoạn, \"quyet_dinh\": \"giu|A|B|C|ket_hop\", \"ly_do\": \"ngắn, "
                f"tiếng Việt\", \"fixed\": \"đoạn cuối cùng hoàn chỉnh bằng {lang}\"}}].\n\n" + "\n\n".join(blocks))
        except Exception as e:
            if _err_is_hard(e) or type(e).__name__ == "GeminiLimitError":
                raise
            ans = None
            job.log(f"   (chủ tịch lỗi: {str(e)[:100]} — áp góp ý được nhiều AI đồng ý)")
        dec = {}
        for it in parse_json(ans or "", "list") or []:
            try:
                dec[int(str(it.get("p")).strip("[] ")) - 1] = it
            except (TypeError, ValueError, AttributeError):
                continue
        for k in part:
            lst = sugg[k]
            names = ", ".join(NAMES[nm] for nm, _ in lst)
            issue = "; ".join(f"[{it.get('loai') or 'lỗi'}] {it.get('issue') or ''}" for _, it in lst)
            d = dec.get(k)
            if d is not None:
                q = str(d.get("quyet_dinh") or "").strip().lower()
                if q.startswith("giu") or q.startswith("giữ"):
                    log.add("Soát chéo", names, k + 1, issue + f" → chủ tịch giữ nguyên: {d.get('ly_do') or ''}",
                            paras[k], "", applied=False)
                    continue
                new = d.get("fixed")
                if not _ok_fix(paras[k], new) and len(q) == 1 and "a" <= q <= chr(96 + len(lst)):
                    new = lst[ord(q) - 97][1].get("fixed")
                if _ok_fix(paras[k], new):
                    old = paras[k]
                    paras[k] = _flat(new)
                    decided += 1
                    log.add("Soát chéo", names, k + 1, issue + f" → chủ tịch: {d.get('ly_do') or q}", old, paras[k])
                    continue
            # không có quyết định: >=2 AI cùng chỉ ra hoặc lỗi nghiêm trọng thì áp, còn lại để sếp xem
            best = max(lst, key=lambda t: _sev(t[1]))
            if len(lst) >= 2 or _sev(best[1]) >= 3:
                old = paras[k]
                paras[k] = _flat(best[1]["fixed"])
                decided += 1
                log.add("Soát chéo", names, k + 1, issue, old, paras[k])
            else:
                log.add("Soát chéo", names, k + 1, issue + " (chưa áp — sếp xem)", paras[k], _flat(best[1]["fixed"]),
                        applied=False)
    job.log(f"   soát chéo: {len(sugg)} đoạn có góp ý, đã sửa {decided}")
    return paras


# ------------------------------------------------------------------------------------------------ bước 5
HUMAN_GUIDE = (
    "Các dấu hiệu 'văn AI' cần sửa (theo hướng dẫn 'Signs of AI writing' của Wikipedia, như repo blader/humanizer):\n"
    "1) Dàn dựng thay vì nói thẳng: 'không phải X mà là Y', 'không chỉ… mà còn…', câu kết đoạn kịch tính/khẩu hiệu, "
    "câu hỏi tu từ sáo rỗng, câu dẫn dắt rườm rà.\n"
    "2) Nhịp theo khuôn: liệt kê đúng ba ý cho đều, nhiều câu mở đầu giống nhau, câu dài bằng nhau, lạm dụng gạch ngang.\n"
    "3) Thổi phồng: 'đóng vai trò then chốt', 'minh chứng cho', 'bức tranh', 'hành trình', 'không thể phủ nhận', "
    "từ vựng AI hay dùng (delve, tapestry, testament, pivotal, crucial, realm, landscape, vibrant, seamless, "
    "underscore, showcase), dẫn nguồn mơ hồ ('các chuyên gia cho rằng', 'nhiều người tin').\n"
    "4) Định dạng theo thói quen: in đậm, tiêu đề, emoji, gạch đầu dòng không cần thiết.\n"
    "5) Lời thừa của chatbot: 'Dưới đây là', 'Hy vọng', 'Tóm lại', 'Nhìn chung', 'Điều quan trọng cần lưu ý', "
    "câu tự nhắc giới hạn kiến thức.\n"
    "6) Viết cho sai người đọc: giải thích lại điều người đọc đã biết, kể lể chung chung thay vì chi tiết cụ thể.\n"
    "Cách sửa: nói thẳng, cụ thể, câu dài ngắn đan xen, giọng người thật am hiểu. GIỮ NGUYÊN mọi dữ kiện, tên, số liệu "
    "và ý; độ dài đoạn tương đương (±15%); không bịa thêm.")

_AI_PATTERNS = [
    (r"không (chỉ|những)\b.{1,90}?\bmà còn\b", "không chỉ… mà còn…"),
    (r"không phải (là )?.{1,70}?,? mà (là|chính là)\b", "không phải X mà là Y"),
    (r"(^|\n)\s*(Tóm lại|Nhìn chung|Tổng kết lại|Có thể nói|Nói tóm lại|Cuối cùng thì)\b", "câu tổng kết sáo"),
    (r"đóng vai trò (quan trọng|then chốt|chủ chốt)|minh chứng (sống động )?cho|không thể phủ nhận|"
     r"trong thế giới (hiện đại|ngày nay)|Hãy cùng|Điều quan trọng (cần|là)", "cụm từ AI hay dùng"),
    (r"\bnot (just|only)\b.{1,90}?\bbut( also)?\b", "not only… but…"),
    (r"\b(delve|delves|tapestry|testament|pivotal|crucial|realm|landscape|vibrant|seamless|underscores?|showcases?|"
     r"navigat(e|ing) the|in today's (fast-paced|digital)|it'?s (important|worth) (to note|noting))\b", "từ vựng AI"),
    (r"(^|\n)\s*(In conclusion|Overall|Ultimately|In summary|In essence)\b", "câu tổng kết sáo"),
    (r"\bno (solo|sólo)\b.{1,90}?\bsino\b|(^|\n)\s*(En conclusión|En resumen|Cabe destacar)", "cụm từ AI (ES)"),
    (r"\bnão (só|apenas)\b.{1,90}?\bmas\b|(^|\n)\s*(Em conclusão|Em resumo)", "cụm từ AI (PT)"),
    (r"\bnicht nur\b.{1,90}?\bsondern\b|(^|\n)\s*(Zusammenfassend|Abschließend)", "cụm từ AI (DE)"),
    (r"\bnon seulement\b.{1,90}?\bmais\b|(^|\n)\s*(En conclusion|En résumé)", "cụm từ AI (FR)"),
]


def ai_signs(paras):
    """Máy dò dấu hiệu văn AI -> {chỉ số đoạn: [lý do]}."""
    out = {}
    for k, p in enumerate(paras):
        why = []
        for pat, name in _AI_PATTERNS:
            if re.search(pat, p, re.I):
                why.append(name)
        if p.count("—") >= 2:
            why.append("lạm dụng gạch ngang")
        sents = [s.strip() for s in re.split(r"(?<=[.!?。！？])\s+", p) if s.strip()]
        heads = [s.split()[0].lower() for s in sents if s.split()]
        if any(heads[x] == heads[x + 1] == heads[x + 2] for x in range(len(heads) - 2)):
            why.append("3 câu liền mở đầu giống nhau")
        if re.search(r"\*\*|[\U0001F300-\U0001FAFF]", p):
            why.append("in đậm/emoji")
        if why:
            out[k] = why
    return out


def humanize(job, session, paras, lang, who, log):
    signs = ai_signs(paras)
    n = len(paras)
    fixed = 0
    for i in range(0, n, 15):
        j = min(n, i + 15)
        hint = [f"[{k + 1}] {', '.join(v)}" for k, v in sorted(signs.items()) if i <= k < j]
        job.log(f"   🧑 Bước 5: sửa văn AI cho giống người viết — đoạn {i + 1}–{j}/{n}"
                + (f" (máy thấy {len(hint)} đoạn nghi)" if hint else "") + "…")
        ans = session.ask(
            HUMAN_GUIDE + "\n\n" + ("Máy đã đánh dấu các đoạn nghi: " + "; ".join(hint) + "\n" if hint else "") +
            "Rà các đoạn dưới đây, CHỈ sửa đoạn có dấu hiệu văn AI. Trả về DUY NHẤT mảng JSON: [{\"p\": số đoạn, "
            f"\"issue\": \"dấu hiệu đã sửa, tiếng Việt\", \"fixed\": \"TOÀN BỘ đoạn đã sửa bằng {lang}\"}}]. "
            "Không có gì cần sửa thì trả về [].\n\n" + numbered(paras, i, j))
        for it in parse_json(ans, "list") or []:
            if not isinstance(it, dict):
                continue
            try:
                k = int(str(it.get("p")).strip("[] ")) - 1
            except (TypeError, ValueError):
                continue
            new = it.get("fixed")
            if i <= k < j and _ok_fix(paras[k], new) and 0.75 * len(paras[k]) <= len(new.strip()) <= 1.35 * len(paras[k]) + 40:
                old = paras[k]
                paras[k] = _flat(new)
                fixed += 1
                log.add("Văn AI → người", who, k + 1, it.get("issue") or ", ".join(signs.get(k, [])) or "giọng máy",
                        old, paras[k])
    job.log(f"   sửa văn AI: {fixed} đoạn")
    return paras


# ------------------------------------------------------------------------------------------------ bước 6
def languagetool(text, code, mode, url, log=print):
    """Gọi LanguageTool (máy local hoặc bản online miễn phí). Trả list (offset, length, message, gợi ý) hoặc None."""
    if mode not in ("local", "online"):
        return None
    try:
        import requests
        import locales
        loc = locales.get_country(code).get("locale") if code != "SAME" else "auto"
    except Exception:
        return None
    endpoint = url if mode == "local" else "https://api.languagetool.org/v2/check"
    limit = 18000 if mode == "online" else 60000
    out, pos = [], 0
    chunks = []
    while pos < len(text) and len(chunks) < (4 if mode == "online" else 10):
        end = min(len(text), pos + limit)
        if end < len(text):
            cut = text.rfind("\n", pos, end)
            end = cut if cut > pos else end
        chunks.append((pos, text[pos:end]))
        pos = end
    for n, (off, chunk) in enumerate(chunks):
        langs = [loc or "auto", (loc or "auto").split("-")[0], "auto"]
        data = None
        for lg in dict.fromkeys(langs):
            try:
                r = requests.post(endpoint, data={"text": chunk, "language": lg}, timeout=60)
            except Exception as e:
                log(f"   (LanguageTool không kết nối được: {str(e)[:80]})")
                return None
            if r.status_code == 200:
                data = r.json()
                break
        if data is None:
            log("   (LanguageTool không hỗ trợ ngôn ngữ này — bỏ qua)")
            return None
        for m in data.get("matches", []):
            out.append((off + m.get("offset", 0), m.get("length", 0), m.get("message", ""),
                        [x.get("value") for x in (m.get("replacements") or [])[:3]],
                        ((m.get("rule") or {}).get("issueType") or "")))
        if mode == "online" and n < len(chunks) - 1:
            time.sleep(3.5)
    return out


def machine_check(job, src, paras, code, opts, log):
    rc_flags = rc.machine_flags(rc.paragraphs(src), paras, code)
    for k, v in sorted(rc_flags.items()):
        log.add("Máy kiểm tra", "Máy", k + 1, "; ".join(v), paras[k], "", applied=False)
    left = ai_signs(paras)
    for k, v in sorted(left.items()):
        log.add("Máy kiểm tra", "Máy", k + 1, "còn dấu hiệu văn AI: " + ", ".join(v), paras[k], "", applied=False)
    n_lt = 0
    if opts.get("lt") in ("local", "online"):
        job.log(f"   🔎 Bước 6: LanguageTool ({'máy này' if opts['lt'] == 'local' else 'online'}) soát chính tả/ngữ pháp…")
        text = "\n".join(paras)
        starts, acc = [], 0
        for p in paras:
            starts.append(acc)
            acc += len(p) + 1
        res = languagetool(text, code, opts["lt"], opts.get("lt_url") or DEFAULTS["lt_url"], job.log)
        for off, ln, msg, reps, typ in (res or [])[:150]:
            k = max(x for x in range(len(starts)) if starts[x] <= off) if starts else 0
            word = text[off:off + ln]
            if typ in ("whitespace",):
                continue
            log.add("Máy kiểm tra", "LanguageTool", k + 1, f"{msg} — '{word}'" + (f" → gợi ý: {', '.join(r for r in reps if r)}"
                                                                                  if reps else ""), word, "", applied=False,
                    kind=typ)
            n_lt += 1
    job.log(f"   máy kiểm tra: {len(rc_flags)} đoạn nghi lệch/thiếu số liệu/chữ lẫn, {len(left)} đoạn còn dấu hiệu văn AI"
            + (f", LanguageTool báo {n_lt} chỗ" if opts.get("lt") in ("local", "online") else ""))


# ------------------------------------------------------------------------------------------------ tổng hợp
def polish(job, session, panel, ref, text, code, lang, audience, opts, writer_name, plan=None):
    """Bước 3 → 6 trên bản nháp. Trả (text_mới, báo_cáo_txt, items)."""
    log = Log()
    paras = rc.paragraphs(text)
    if not paras:
        return text, "", []
    if opts.get("self"):
        try:
            paras = self_refine(job, session, ref, paras, lang, writer_name, log)
        except Exception as e:
            if _err_is_hard(e) or type(e).__name__ == "GeminiLimitError":
                raise
            job.log(f"   (bỏ qua bước tự soát: {str(e)[:120]})")
    if panel is not None and panel.alive():
        try:
            paras = cross_review(job, panel, session, ref, paras, lang, audience, log, writer_name)
        except Exception as e:
            if _err_is_hard(e) or type(e).__name__ == "GeminiLimitError":
                raise
            job.log(f"   (bỏ qua bước soát chéo: {str(e)[:120]})")
    if opts.get("human"):
        try:
            paras = humanize(job, session, paras, lang, writer_name, log)
        except Exception as e:
            if _err_is_hard(e) or type(e).__name__ == "GeminiLimitError":
                raise
            job.log(f"   (bỏ qua bước sửa văn AI: {str(e)[:120]})")
    if opts.get("machine", True):
        try:
            machine_check(job, ref, paras, code, opts, log)
        except Exception as e:
            job.log(f"   (bỏ qua máy kiểm tra: {str(e)[:120]})")
    # số đoạn theo bản CUỐI để sếp dò đúng chỗ
    for it in log.items:
        if it["applied"] and it["new"]:
            for k, p in enumerate(paras):
                if p[:1500] == it["new"]:
                    it["p"] = k + 1
                    break
    final = "\n\n".join(paras)
    return final, build_report(log.items, plan, writer_name, panel), log.items


def build_report(items, plan, writer_name, panel):
    applied = [x for x in items if x["applied"]]
    pending = [x for x in items if not x["applied"]]
    by = {}
    for x in applied:
        by[x["step"]] = by.get(x["step"], 0) + 1
    lines = ["BÁO CÁO VIẾT CHUYÊN GIA", "=" * 60, f"AI viết: {writer_name}"
             + (f" · Hội đồng soát chéo: {', '.join(NAMES[n] for n in panel.names)}" if panel and panel.names else ""), ""]
    if plan:
        lines.append("KẾ HOẠCH TỪ DÀN Ý:")
        lines += [f"  {i}. {p.get('muc')} (~{p.get('so_tu', '?')} từ)" for i, p in enumerate(plan, start=1)]
        lines.append("")
    lines.append("ĐÃ SỬA: " + (", ".join(f"{k} {v}" for k, v in by.items()) or "không có"))
    lines.append("")
    for x in applied:
        lines += [f"■ Đoạn {x['p']} — {x['step']} ({x['ai']}): {x['issue']}"]
        if x["old"]:
            lines.append(f"  TRƯỚC: {x['old']}")
        lines += [f"  SAU  : {x['new']}", ""]
    lines.append("CẦN SẾP XEM LẠI (" + str(len(pending)) + " chỗ):" if pending else "Không còn chỗ nào cần xem lại.")
    for x in pending:
        lines.append(f"  - Đoạn {x['p']} — {x['step']} ({x['ai']}): {x['issue']}")
        if x["new"]:
            lines.append(f"      đề xuất: {x['new']}")
    return "\n".join(lines) + "\n"
