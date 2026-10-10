# -*- coding: utf-8 -*-
"""Kho cấu hình module NotebookLM: Thư mục -> Dạng bài. Lưu trong notebook_store.json (chỉ cấu hình của Tool)."""
import os
import re
import threading
import uuid

from localize_bot import read_json, write_json_atomic

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(BASE_DIR, "notebook_store.json")
_LOCK = threading.Lock()

TYPE_FIELDS = {"name": "", "prompt": "", "mode": "rewrite", "length": "same", "review": False, "chunk_size": 8000,
               "fixed_text": "", "audience": "", "keywords": "", "glossary": "", "extra": ""}
MODES = ("rewrite", "localize", "analyze")
LENGTHS = ("same", "longer", "shorter")


def _load():
    if os.path.isfile(STORE):
        try:
            d = read_json(STORE)
            if isinstance(d, dict) and isinstance(d.get("folders"), list):
                return d
        except Exception:
            pass
    return {"folders": []}


def tree():
    with _LOCK:
        return _load()


def _clean_type(src, old=None):
    t = dict(TYPE_FIELDS)
    if old:
        t.update(old)
    for k in TYPE_FIELDS:
        if k in src:
            t[k] = src[k]
    t["name"] = str(t["name"]).strip()[:80]
    t["mode"] = t["mode"] if t["mode"] in MODES else "rewrite"
    t["length"] = t["length"] if t["length"] in LENGTHS else "same"
    t["review"] = bool(t["review"])
    try:
        t["chunk_size"] = max(2000, min(40000, int(t["chunk_size"])))
    except (TypeError, ValueError):
        t["chunk_size"] = 8000
    for k in ("prompt", "fixed_text", "audience", "keywords", "glossary", "extra"):
        t[k] = str(t[k] or "")
    return t


def save_folder(name, folder_id=None):
    name = (name or "").strip()[:80]
    if not name:
        raise ValueError("Tên thư mục không được để trống.")
    with _LOCK:
        d = _load()
        if folder_id:
            f = next((x for x in d["folders"] if x["id"] == folder_id), None)
            if not f:
                raise KeyError("Không thấy thư mục.")
            f["name"] = name
        else:
            f = {"id": uuid.uuid4().hex[:10], "name": name, "types": []}
            d["folders"].append(f)
        write_json_atomic(STORE, d)
        return f


def delete_folder(folder_id):
    with _LOCK:
        d = _load()
        d["folders"] = [x for x in d["folders"] if x["id"] != folder_id]
        write_json_atomic(STORE, d)


def save_type(folder_id, src, type_id=None):
    with _LOCK:
        d = _load()
        f = next((x for x in d["folders"] if x["id"] == folder_id), None)
        if not f:
            raise KeyError("Không thấy thư mục.")
        if type_id:
            t = next((x for x in f["types"] if x["id"] == type_id), None)
            if not t:
                raise KeyError("Không thấy dạng bài.")
            t.update(_clean_type(src, t))
        else:
            t = _clean_type(src)
            t["id"] = uuid.uuid4().hex[:10]
            f["types"].append(t)
        if not t["name"]:
            raise ValueError("Tên dạng bài không được để trống.")
        if not t["prompt"].strip():
            raise ValueError("Hãy nhập prompt (cách viết / phân tích) cho dạng bài.")
        write_json_atomic(STORE, d)
        return t


def delete_type(type_id):
    with _LOCK:
        d = _load()
        for f in d["folders"]:
            f["types"] = [x for x in f["types"] if x["id"] != type_id]
        write_json_atomic(STORE, d)


def find_type(type_id):
    """-> (folder, type) hoặc (None, None)."""
    for f in tree()["folders"]:
        for t in f["types"]:
            if t["id"] == type_id:
                return f, t
    return None, None


def split_fixed(text):
    """Nguồn cố định: tách thành nhiều nguồn bằng dòng chỉ có ===== (≥5 dấu =)."""
    parts = re.split(r"^\s*={5,}\s*$", text or "", flags=re.M)
    return [p.strip() for p in parts if p.strip()]
