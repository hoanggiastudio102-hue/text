# -*- coding: utf-8 -*-
"""
Rà soát bản dịch/bản viết lại theo từng đoạn (dùng cho module NotebookLM).

Lớp 1 (máy, không tốn lượt AI): ghép đoạn gốc <-> đoạn dịch, đánh dấu đoạn nghi thiếu/thừa ý (độ dài lệch),
        thiếu số liệu, lẫn chữ ngôn ngữ khác.
Lớp 3 (Gemini soát chéo): gửi từng lô đoạn gốc + đoạn dịch, Gemini chỉ trả về ĐOẠN cần sửa kèm bản sửa hoàn chỉnh
        của đoạn đó -> Tool thay đúng đoạn, không viết lại cả bài (không bị cụt, không làm hỏng đoạn tốt).
Mọi chỗ sửa được ghi vào báo cáo <bài>_<nước>_ra_soat.txt.
"""
import json
import re

BATCH = 12          # số đoạn dịch mỗi lô gửi Gemini


def paragraphs(text):
    return [p.strip() for p in (text or "").replace("\r\n", "\n").split("\n") if p.strip()]


def _digits(s):
    """Các con số trong đoạn (bỏ dấu phân cách): '130.000' -> '130000'."""
    return [re.sub(r"[.,\s]", "", n) for n in re.findall(r"\d[\d.,]*\d|\d", s)]


def leaks_in(text, code):
    pats = []
    if code not in ("KR", "SAME"):
        pats.append(r"[가-힣ᄀ-ᇿ]+")
    if code not in ("CN", "TW", "HK", "JP", "KR", "SAME"):
        pats.append(r"[぀-ヿ㐀-鿿]+")
    if code in ("CN", "TW", "HK", "JP"):
        pats.append(r"(?<![A-Za-z])[a-z][A-Za-z]{2,}(?![A-Za-z])")
    out = []
    for pat in pats:
        for m in re.finditer(pat, text):
            snip = text[max(0, m.start() - 4):m.end() + 4].replace("\n", " ").strip()
            if snip not in out:
                out.append(snip)
    return out


def src_range(i, j, n_src, n_out):
    """Đoạn gốc tương ứng với các đoạn dịch [i, j): khớp số đoạn thì 1-1, lệch thì ước theo tỉ lệ (+1 đoạn mỗi bên)."""
    if n_src == n_out:
        return i, j
    a = max(0, int(i * n_src / n_out) - 1)
    b = min(n_src, int(round(j * n_src / n_out)) + 1)
    return a, b


def machine_flags(src_paras, out_paras, code):
    """Lớp 1 -> {chỉ số đoạn dịch: [lý do, ...]}."""
    flags = {}
    exact = len(src_paras) == len(out_paras)
    tot_s = sum(len(p) for p in src_paras) or 1
    tot_o = sum(len(p) for p in out_paras) or 1
    ratio = tot_o / tot_s
    for k, op in enumerate(out_paras):
        why = []
        if exact:
            sp = src_paras[k]
            if len(sp) >= 80:
                r = len(op) / len(sp)
                if r < 0.6 * ratio:
                    why.append(f"ngắn bất thường so với đoạn gốc ({len(op)}/{len(sp)} ký tự) — nghi thiếu ý")
                elif r > 1.7 * ratio:
                    why.append(f"dài bất thường so với đoạn gốc ({len(op)}/{len(sp)} ký tự) — nghi thêm ý")
            od = "".join(_digits(op))
            miss = [d for d in _digits(sp) if d not in od]
            if miss:
                why.append("thiếu số liệu: " + ", ".join(miss[:5]))
        lk = leaks_in(op, code)
        if lk:
            why.append("lẫn chữ ngôn ngữ khác: " + ", ".join(lk[:5]))
        if why:
            flags[k] = why
    return flags


def build_batch_prompt(src_paras, out_paras, i, j, n_src, language, audience, flags):
    a, b = src_range(i, j, n_src, len(out_paras))
    src_block = "\n".join(f"[S{x + 1}] {src_paras[x]}" for x in range(a, b))
    out_block = "\n".join(f"[T{x + 1}] {out_paras[x]}" for x in range(i, j))
    sus = [f"T{k + 1}: {'; '.join(v)}" for k, v in sorted(flags.items()) if i <= k < j]
    return (
        "You are a senior bilingual editor and native writer of " + language + ". Compare each TRANSLATION paragraph "
        "[T#] with the SOURCE paragraphs [S#] (same order" + (", numbered 1-to-1" if n_src == len(out_paras) else "") + ").\n"
        "Find REAL problems only: wrong meaning, missing ideas or details, content added that is not in the source, "
        "wrong numbers/names/dates, words or characters from another language mixed in, typos, wrong word choice, "
        "phrasing a native " + language + " reader (" + (audience or "general readers") + ") would find unnatural.\n"
        + ("Automatic checks flagged these paragraphs — check them carefully:\n" + "\n".join(sus) + "\n" if sus else "")
        + "Return ONLY a JSON array, no other text: "
        "[{\"p\": <T number>, \"issue\": \"<short reason in Vietnamese>\", \"fixed\": \"<the COMPLETE corrected paragraph in "
        + language + ">\"}]. Include only paragraphs that need changes. In \"fixed\" keep the full content and length of the "
        "paragraph — never shorten or summarise, keep the style. If nothing needs fixing, return [].\n\n"
        "SOURCE:\n" + src_block + "\n\nTRANSLATION:\n" + out_block)


def parse_fixes(answer):
    a, b = answer.find("["), answer.rfind("]")
    if a == -1 or b <= a:
        return None
    raw = answer[a:b + 1]
    for cand in (raw, re.sub(r",\s*([\]}])", r"\1", raw)):
        try:
            data = json.loads(cand)
            return data if isinstance(data, list) else None
        except ValueError:
            continue
    return None


def apply_fixes(out_paras, items, i, j):
    """Thay đoạn được sửa (chỉ trong lô [i, j)); bỏ qua bản sửa rút gọn quá mức hoặc phình bất thường."""
    log = []
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            k = int(str(it.get("p")).lstrip("Tt")) - 1
        except (TypeError, ValueError):
            continue
        fixed = str(it.get("fixed") or "").strip()
        if not (i <= k < j) or not fixed:
            continue
        old = out_paras[k]
        if fixed == old or len(fixed) < 0.6 * len(old) or len(fixed) > 2.5 * len(old) + 50:
            continue
        out_paras[k] = re.sub(r"\s*\n\s*", " ", fixed)
        log.append((k, str(it.get("issue") or "").strip(), old, out_paras[k]))
    return log


def cross_check(gemini, src, text, code, language, audience, log=print, should_stop=lambda: False):
    """Lớp 3: Gemini soát chéo theo lô. Trả (text_mới, danh_sách_sửa, cờ_lớp_1)."""
    src_paras, out_paras = paragraphs(src), paragraphs(text)
    flags = machine_flags(src_paras, out_paras, code)
    changes = []
    if gemini is None or not out_paras:
        return "\n".join(out_paras), changes, flags
    n = len(out_paras)
    fails = 0
    for i in range(0, n, BATCH):
        if should_stop():
            break
        j = min(n, i + BATCH)
        log(f"   🧐 Gemini soát chéo đoạn {i + 1}–{j}/{n}…")
        prompt = build_batch_prompt(src_paras, out_paras, i, j, len(src_paras), language, audience, flags)
        ans = None
        for attempt in (1, 2):
            try:
                gemini.new_chat()
                ans = gemini.ask(prompt)
                break
            except Exception as e:  # lỗi một lô không làm hỏng cả bài
                if type(e).__name__ in ("GeminiLimitError", "GeminiCancelled"):
                    raise
                log(f"   (lô {i + 1}–{j} lỗi: {str(e)[:100]}{' — thử lại' if attempt == 1 else ' — bỏ qua lô này'})")
        if ans is None:
            fails += 1
            if fails >= 2:
                log("   ⚠️ Gemini lỗi liên tiếp — bỏ bước soát chéo cho bài này (kiểm tra đăng nhập Gemini).")
                break
            continue
        fails = 0
        items = parse_fixes(ans or "")
        if items is None:
            if ans:
                log(f"   (lô {i + 1}–{j}: không đọc được kết quả soát)")
            continue
        changes += apply_fixes(out_paras, items, i, j)
    return "\n".join(out_paras), changes, flags


def report(article, country_name, changes, flags, out_paras_final, code, proof_count=0):
    lines = [f"BÁO CÁO RÀ SOÁT — {article} — {country_name}", "=" * 60,
             f"NotebookLM tự soát: sửa {proof_count} chỗ nhỏ (chính tả, chữ lẫn).",
             f"Gemini soát chéo: sửa {len(changes)} đoạn.", ""]
    for k, issue, old, new in changes:
        lines += [f"■ Đoạn {k + 1}: {issue or 'sửa diễn đạt'}", f"  TRƯỚC: {old}", f"  SAU  : {new}", ""]
    remain = {}
    for k, op in enumerate(out_paras_final):
        lk = leaks_in(op, code)
        if lk:
            remain[k] = ["còn lẫn chữ: " + ", ".join(lk[:5])]
    fixed_idx = {c[0] for c in changes}
    for k, v in flags.items():
        if k not in fixed_idx and k < len(out_paras_final):
            remain.setdefault(k, []).extend(x for x in v if not x.startswith("lẫn chữ"))
    remain = {k: v for k, v in remain.items() if v}
    lines.append("ĐOẠN CÒN NGHI NGỜ (sếp nên xem lại):" if remain else "Không còn đoạn nào bị máy đánh dấu nghi ngờ.")
    for k, v in sorted(remain.items()):
        lines.append(f"  - Đoạn {k + 1}: {'; '.join(v)}")
    return "\n".join(lines) + "\n", len(remain)
