# -*- coding: utf-8 -*-
"""Lấy tiêu đề + phụ đề (transcript) video YouTube để đưa vào NotebookLM."""
import re

_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/|/v/)([0-9A-Za-z_-]{11})")
_URL_RE = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/[^\s<>\"']+")


def find_links(text):
    """Tách các link YouTube (mỗi dòng/dấu cách), bỏ trùng theo mã video, giữ thứ tự."""
    out, seen = [], set()
    for m in _URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(".,;)")
        vid = video_id(url)
        if vid and vid not in seen:
            seen.add(vid)
            out.append({"url": url, "id": vid})
    return out


def video_id(url):
    m = _ID_RE.search(url or "")
    return m.group(1) if m else None


def get_title(url, timeout=10):
    try:
        import requests
        r = requests.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=timeout)
        if r.ok:
            return (r.json().get("title") or "").strip()
    except Exception:
        pass
    return ""


def get_transcript(url):
    """-> (text, language_code, error). Ưu tiên phụ đề do người đăng tạo, rồi tới phụ đề tự động (ngôn ngữ gốc)."""
    vid = video_id(url)
    if not vid:
        return "", "", "Link không phải video YouTube."
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        tl = YouTubeTranscriptApi().list(vid)
        items = list(tl)
        if not items:
            return "", "", "Video không có phụ đề."
        manual = [t for t in items if not getattr(t, "is_generated", False)]
        tr = (manual or items)[0]
        data = tr.fetch()
        parts = []
        for t in data:
            s = t.text if hasattr(t, "text") else t.get("text", "")
            s = re.sub(r"\[(?:music|âm nhạc|applause|vỗ tay|laughter|tiếng cười)[^\]]*\]", " ", s, flags=re.I)
            s = s.replace("\n", " ").strip()
            if s:
                parts.append(s)
        text = re.sub(r"\s{2,}", " ", " ".join(parts)).strip()
        return text, getattr(tr, "language_code", ""), ("" if text else "Phụ đề rỗng.")
    except Exception as e:
        return "", "", f"{type(e).__name__}: {str(e)[:200]}"


def lang_to_code(lang):
    """Mã ngôn ngữ phụ đề -> mã nước của Tool (để đo độ dài đúng kiểu chữ)."""
    lang = (lang or "").lower()
    if lang.startswith("ja"):
        return "JP"
    if lang.startswith("ko"):
        return "KR"
    if lang.startswith("zh"):
        return "TW" if ("hant" in lang or "tw" in lang or "hk" in lang) else "CN"
    return "SAME"
