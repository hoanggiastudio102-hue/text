"""Đội máy: MÁY CHỦ (máy sếp) nhận báo cáo + sản phẩm từ MÁY NHÂN VIÊN.

Mỗi máy nhân viên chạy tool riêng, đăng nhập Gemini riêng (profile riêng trên máy đó),
xong job thì tự gửi báo cáo + file về máy chủ. Máy chủ chỉ giữ token đã băm.

Dữ liệu máy chủ : fleet_data/devices.json, pairing.json, reports/<device_id>/<job_id>/
Cấu hình máy NV : fleet_agent.json  (hub_url, device_id, token, name, cf_id, cf_secret)
"""
import hashlib
import hmac
import json
import os
import secrets
import shutil
import threading
import time
import zipfile

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "fleet_data")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")
PAIRING_FILE = os.path.join(DATA_DIR, "pairing.json")
AGENT_FILE = os.path.join(APP_DIR, "fleet_agent.json")
OUTBOX_FILE = os.path.join(APP_DIR, "fleet_outbox.json")   # job đã gửi / chờ gửi (máy NV)

PAIR_TTL = 15 * 60          # mã ghép máy sống 15 phút, dùng 1 lần
ONLINE_SECONDS = 90         # quá ngần này giây không heartbeat -> ngoại tuyến
MAX_UPLOAD = 300 * 1024 * 1024
_LOCK = threading.RLock()
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


# ---------------------------------------------------------------- tiện ích
def _read(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _safe(s, fallback="x", n=60):
    s = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(s or ""))[:n].strip("._")
    return s or fallback


# ================================================================ MÁY CHỦ
def create_pair_code(device_name):
    """Sếp cấp mã ghép cho 1 máy nhân viên."""
    name = (device_name or "").strip()[:40] or "May-NV"
    with _LOCK:
        pairing = _read(PAIRING_FILE, {})
        now = time.time()
        pairing = {c: v for c, v in pairing.items() if v.get("expires", 0) > now}
        code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        pairing[code] = {"name": name, "expires": now + PAIR_TTL}
        _write(PAIRING_FILE, pairing)
    return {"code": code, "name": name, "expires_in": PAIR_TTL}


def redeem_pair_code(code, hostname=""):
    """Máy nhân viên đổi mã lấy token. Trả (device_id, token) hoặc None."""
    code = (code or "").strip().upper().replace("-", "").replace(" ", "")
    with _LOCK:
        pairing = _read(PAIRING_FILE, {})
        entry = pairing.get(code)
        if not entry or entry.get("expires", 0) < time.time():
            return None
        del pairing[code]
        _write(PAIRING_FILE, pairing)
        devices = _read(DEVICES_FILE, {})
        dev_id = "d" + secrets.token_hex(4)
        token = secrets.token_urlsafe(32)
        devices[dev_id] = {
            "id": dev_id, "name": entry["name"], "hostname": str(hostname)[:60],
            "token_hash": _hash(token), "created": time.time(), "last_seen": 0,
            "revoked": False, "state": {},
        }
        _write(DEVICES_FILE, devices)
    return dev_id, token


def auth_device(token):
    if not token:
        return None
    h = _hash(token)
    devices = _read(DEVICES_FILE, {})
    for d in devices.values():
        if not d.get("revoked") and hmac.compare_digest(d.get("token_hash", ""), h):
            return d
    return None


def heartbeat(dev_id, state):
    with _LOCK:
        devices = _read(DEVICES_FILE, {})
        d = devices.get(dev_id)
        if not d or d.get("revoked"):
            return False
        d["last_seen"] = time.time()
        d["state"] = {k: state.get(k) for k in ("gemini_logged_in", "model", "job", "version", "os") if k in state}
        _write(DEVICES_FILE, devices)
    return True


def revoke_device(dev_id):
    with _LOCK:
        devices = _read(DEVICES_FILE, {})
        if dev_id not in devices:
            return False
        devices[dev_id]["revoked"] = True
        _write(DEVICES_FILE, devices)
    return True


def forget_device(dev_id):
    """Xoá hẳn khỏi danh sách (báo cáo cũ vẫn giữ)."""
    with _LOCK:
        devices = _read(DEVICES_FILE, {})
        ok = devices.pop(dev_id, None) is not None
        _write(DEVICES_FILE, devices)
    return ok


def save_report(device, meta, file_storage):
    """Nhận báo cáo + file sản phẩm từ máy nhân viên (idempotent theo job_id)."""
    job_id = _safe(meta.get("job_id"), "job", 40)
    d = os.path.join(REPORTS_DIR, device["id"], job_id)
    os.makedirs(d, exist_ok=True)
    fname = None
    if file_storage is not None and file_storage.filename:
        fname = _safe(os.path.basename(file_storage.filename), "san_pham.zip", 120)
        file_storage.save(os.path.join(d, fname))
    report = {
        "device_id": device["id"], "device_name": device["name"], "job_id": job_id,
        "received": time.time(), "file": fname,
        "name": str(meta.get("name") or "")[:120],
        "state": str(meta.get("state") or "")[:20],
        "countries": [str(c)[:8] for c in (meta.get("countries") or [])][:60],
        "articles": [str(a)[:120] for a in (meta.get("articles") or [])][:200],
        "units_total": int(meta.get("units_total") or 0),
        "units_done": int(meta.get("units_done") or 0),
        "units_error": int(meta.get("units_error") or 0),
        "chars": int(meta.get("chars") or 0),
        "seconds": int(meta.get("seconds") or 0),
        "model": str(meta.get("model") or "")[:40],
        "dry_run": bool(meta.get("dry_run")),
        "started_at": meta.get("started_at"), "finished_at": meta.get("finished_at"),
    }
    _write(os.path.join(d, "report.json"), report)
    return report


def list_devices():
    now = time.time()
    devices = _read(DEVICES_FILE, {})
    reports = list_reports()
    stats = {}
    for r in reports:
        s = stats.setdefault(r["device_id"], {"jobs": 0, "units": 0, "chars": 0, "last": 0})
        s["jobs"] += 1
        s["units"] += r.get("units_done", 0)
        s["chars"] += r.get("chars", 0)
        s["last"] = max(s["last"], r.get("received", 0))
    out = []
    for d in devices.values():
        online = (now - d.get("last_seen", 0)) < ONLINE_SECONDS and not d.get("revoked")
        out.append({
            "id": d["id"], "name": d["name"], "hostname": d.get("hostname", ""),
            "online": online, "revoked": bool(d.get("revoked")),
            "last_seen": d.get("last_seen", 0), "created": d.get("created", 0),
            "state": d.get("state", {}), "stats": stats.get(d["id"], {"jobs": 0, "units": 0, "chars": 0, "last": 0}),
        })
    out.sort(key=lambda x: (not x["online"], x["name"].lower()))
    return out


def list_reports(device_id=None, limit=300):
    out = []
    if not os.path.isdir(REPORTS_DIR):
        return out
    for dev in os.listdir(REPORTS_DIR):
        if device_id and dev != device_id:
            continue
        dp = os.path.join(REPORTS_DIR, dev)
        if not os.path.isdir(dp):
            continue
        for job in os.listdir(dp):
            r = _read(os.path.join(dp, job, "report.json"), None)
            if r:
                out.append(r)
    out.sort(key=lambda r: r.get("received", 0), reverse=True)
    return out[:limit]


def report_file_path(device_id, job_id):
    base = os.path.realpath(REPORTS_DIR)
    d = os.path.realpath(os.path.join(REPORTS_DIR, _safe(device_id, "d", 20), _safe(job_id, "j", 40)))
    if not d.startswith(base + os.sep):
        return None
    r = _read(os.path.join(d, "report.json"), None)
    if not r or not r.get("file"):
        return None
    p = os.path.join(d, r["file"])
    return p if os.path.isfile(p) else None


def is_local_request(request):
    """Chỉ cho quản trị khi gọi trực tiếp từ chính máy chủ (không qua tunnel/proxy)."""
    if request.headers.get("Cf-Connecting-Ip") or request.headers.get("X-Forwarded-For") \
            or request.headers.get("Cf-Ray") or request.headers.get("X-Real-Ip"):
        return False
    return request.remote_addr in ("127.0.0.1", "::1", "::ffff:127.0.0.1")


# ================================================================ MÁY NHÂN VIÊN
def agent_config():
    return _read(AGENT_FILE, {})


def agent_save(cfg):
    _write(AGENT_FILE, cfg)


def agent_unpair():
    try:
        os.remove(AGENT_FILE)
    except OSError:
        pass


def _headers(cfg):
    h = {"Authorization": "Bearer " + cfg.get("token", "")}
    if cfg.get("cf_id") and cfg.get("cf_secret"):   # Cloudflare Access service token (nếu sếp bật)
        h["CF-Access-Client-Id"] = cfg["cf_id"]
        h["CF-Access-Client-Secret"] = cfg["cf_secret"]
    return h


def _url(cfg, path):
    return cfg["hub_url"].rstrip("/") + path


def agent_pair(hub_url, code, name="", cf_id="", cf_secret="", hostname=""):
    import requests
    hub_url = (hub_url or "").strip().rstrip("/")
    if not hub_url.startswith(("http://", "https://")):
        hub_url = "https://" + hub_url
    h = {}
    if cf_id and cf_secret:
        h = {"CF-Access-Client-Id": cf_id, "CF-Access-Client-Secret": cf_secret}
    r = requests.post(hub_url + "/api/fleet/pair", json={"code": code, "hostname": hostname or name}, headers=h, timeout=20)
    try:
        j = r.json()
    except ValueError:
        raise RuntimeError("Máy chủ không trả lời đúng định dạng (kiểm tra lại địa chỉ máy chủ / Cloudflare Access).")
    if r.status_code != 200 or j.get("status") != "success":
        raise RuntimeError(j.get("message") or f"Ghép máy thất bại (HTTP {r.status_code}).")
    cfg = {"hub_url": hub_url, "device_id": j["device_id"], "token": j["token"],
           "name": j.get("name") or name, "cf_id": cf_id, "cf_secret": cf_secret, "paired_at": time.time()}
    agent_save(cfg)
    return cfg


def agent_ping(state):
    import requests
    cfg = agent_config()
    if not cfg.get("token"):
        return None
    r = requests.post(_url(cfg, "/api/fleet/heartbeat"), json=state, headers=_headers(cfg), timeout=15)
    if r.status_code == 401:
        raise PermissionError("Máy chủ đã thu hồi hoặc từ chối máy này.")
    return r.status_code == 200


def job_report(job_dir):
    """Gom báo cáo + tạo file zip sản phẩm từ 1 job đã xong. Trả (meta, zip_path|None)."""
    job = _read(os.path.join(job_dir, "job.json"), {})
    results = job.get("results", {})
    done = [r for r in results.values() if r.get("status") == "done"]
    err = [r for r in results.values() if r.get("status") == "error"]
    meta = {
        "job_id": job.get("id"), "name": job.get("base_name") or (job.get("articles") or [{}])[0].get("name", ""),
        "state": job.get("state"), "countries": job.get("countries") or [],
        "articles": [a.get("name", "") for a in job.get("articles", [])],
        "units_total": len(results), "units_done": len(done), "units_error": len(err),
        "chars": sum(int(r.get("chars") or 0) for r in done),
        "seconds": int((job.get("finished_at") or time.time()) - (job.get("started_at") or time.time())),
        "model": job.get("model"), "dry_run": job.get("dry_run"),
        "started_at": job.get("started_at"), "finished_at": job.get("finished_at"),
    }
    files_dir = os.path.join(job_dir, "files")
    zpath = None
    if done and os.path.isdir(files_dir):
        zpath = os.path.join(job_dir, f"san_pham_{_safe(job.get('id'), 'job', 12)}.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(files_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    z.write(full, os.path.relpath(full, files_dir))
    return meta, zpath


def agent_upload_job(job_dir):
    import requests
    cfg = agent_config()
    if not cfg.get("token"):
        return False
    meta, zpath = job_report(job_dir)
    files = {}
    fh = None
    try:
        if zpath:
            fh = open(zpath, "rb")
            files["file"] = (os.path.basename(zpath), fh, "application/zip")
        r = requests.post(_url(cfg, "/api/fleet/report"), data={"meta": json.dumps(meta, ensure_ascii=False)},
                          files=files or None, headers=_headers(cfg), timeout=300)
    finally:
        if fh:
            fh.close()
        if zpath:
            try:
                os.remove(zpath)
            except OSError:
                pass
    if r.status_code == 401:
        raise PermissionError("Máy chủ từ chối máy này.")
    return r.status_code == 200


def outbox():
    return _read(OUTBOX_FILE, {})


def outbox_mark(job_id, ok, err=""):
    with _LOCK:
        o = outbox()
        o[job_id] = {"sent": bool(ok), "at": time.time(), "error": err[:200]}
        _write(OUTBOX_FILE, o)


def pending_jobs(jobs_dir):
    """Job đã kết thúc (done/partial) trên máy này mà chưa gửi về máy chủ."""
    out = []
    o = outbox()
    if not os.path.isdir(jobs_dir):
        return out
    for jid in os.listdir(jobs_dir):
        jd = os.path.join(jobs_dir, jid)
        job = _read(os.path.join(jd, "job.json"), None)
        if not job or job.get("state") not in ("done", "partial") or job.get("dry_run"):
            continue
        if o.get(jid, {}).get("sent"):
            continue
        if time.time() - o.get(jid, {}).get("at", 0) < 60 and jid in o:
            continue   # vừa thử lỗi, chờ chút
        out.append(jd)
    return out
