# -*- coding: utf-8 -*-
"""Viết lại một số ĐOẠN của 1 file kết quả bằng AI được chọn (Gemini / ChatGPT / Claude) — chạy nền, tool gọi:

    python para_fix.py <task.json>

task.json: {"job_dir", "file", "idxs": [chỉ số đoạn, từ 0], "ai", "note", "paras": [...]}
Kết quả ghi vào cùng thư mục: <task>.out.json = {"state": running|done|error, "results": {idx: đoạn mới}, "log": [...]}
Không sửa file — sếp duyệt trên giao diện rồi mới bấm Lưu.
"""
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import expert


def write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def source_text(job_dir, file):
    """Bài gốc/dàn ý của kết quả này (để AI viết lại đúng ý)."""
    try:
        with open(os.path.join(job_dir, "job.json"), "r", encoding="utf-8") as f:
            job = json.load(f)
        aid = file.split("/", 1)[0]
        art = next((a for a in job.get("articles", []) if a["id"] == aid), None)
        if not art:
            return ""
        out = ""
        if art.get("outline_file"):
            with open(os.path.join(job_dir, "sources", art["outline_file"]), "r", encoding="utf-8") as f:
                out = "DÀN Ý:\n" + f.read().strip() + "\n\n"
        with open(os.path.join(job_dir, "sources", art["file"]), "r", encoding="utf-8") as f:
            return out + f.read().strip()
    except Exception:
        return ""


def build_prompt(paras, idxs, note, ref):
    blocks = []
    for k in idxs:
        prev = paras[k - 1] if k > 0 else "(đầu bài)"
        nxt = paras[k + 1] if k + 1 < len(paras) else "(cuối bài)"
        blocks.append(f"[{k + 1}]\n  Đoạn TRƯỚC (chỉ để nối mạch): {prev[:600]}\n  ĐOẠN CẦN VIẾT LẠI: {paras[k]}\n"
                      f"  Đoạn SAU (chỉ để nối mạch): {nxt[:600]}")
    return (
        "Bạn là biên tập viên chuyên nghiệp, viết như người bản xứ am hiểu chủ đề. Viết lại TỪNG đoạn được đánh số dưới đây "
        "cho hay hơn, tự nhiên như người thật viết: giữ nguyên ngôn ngữ của đoạn, giữ đủ ý, dữ kiện, tên riêng, số liệu; "
        "độ dài tương đương; nối mạch với đoạn trước và sau; bỏ câu sáo, từ phóng đại, giọng máy móc."
        + (f"\nYÊU CẦU CỦA SẾP: {note}" if note else "")
        + "\nTrả về DUY NHẤT mảng JSON: [{\"p\": số đoạn, \"fixed\": \"đoạn đã viết lại hoàn chỉnh\"}]."
        + ("\n\nTÀI LIỆU GỐC (để đối chiếu ý):\n" + expert.ref_block(ref, min(idxs), max(idxs) + 1, len(paras)) if ref else "")
        + "\n\nCÁC ĐOẠN:\n" + "\n\n".join(blocks))


def main(task_path):
    with open(task_path, "r", encoding="utf-8") as f:
        task = json.load(f)
    out_path = task_path[:-5] + ".out.json"
    state = {"state": "running", "results": {}, "log": [], "started": time.time()}

    def log(m):
        state["log"].append(str(m))
        state["log"] = state["log"][-40:]
        write(out_path, state)

    write(out_path, state)
    paras = task["paras"]
    idxs = sorted({int(i) for i in task["idxs"] if 0 <= int(i) < len(paras)})
    ref = source_text(task["job_dir"], task["file"])
    session = None
    try:
        import web_chat
        session = web_chat.make_session(task["ai"], log=log)
        session.start()
        for x in range(0, len(idxs), 8):
            part = idxs[x:x + 8]
            log(f"Đang nhờ {expert.NAMES.get(task['ai'], task['ai'])} viết lại đoạn {', '.join(str(i + 1) for i in part)}…")
            ans = session.ask(build_prompt(paras, part, (task.get("note") or "").strip(), ref))
            items = expert.parse_json(ans, "list") or []
            got = 0
            for it in items:
                try:
                    k = int(str(it.get("p")).strip("[] ")) - 1
                except (TypeError, ValueError, AttributeError):
                    continue
                txt = expert._flat(it.get("fixed") or "")
                if k in part and txt and txt != paras[k]:
                    state["results"][str(k)] = txt
                    got += 1
            if not got and len(part) == 1 and ans and len(ans.strip()) > 20 and "[" not in ans[:5]:
                state["results"][str(part[0])] = expert._flat(ans)     # AI trả thẳng đoạn văn, không JSON
            write(out_path, state)
            if x + 8 < len(idxs):
                session.new_chat()
        state["state"] = "done"
        log(f"Xong: có bản mới cho {len(state['results'])}/{len(idxs)} đoạn.")
    except Exception as e:
        state["state"] = "error"
        state["error"] = str(e)[:400]
        log(f"Lỗi: {str(e)[:300]}")
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        state["finished"] = time.time()
        write(out_path, state)


if __name__ == "__main__":
    main(sys.argv[1])
