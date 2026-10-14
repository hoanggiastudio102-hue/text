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
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
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


# ---------------------------------------------------------------- TÀI KHOẢN NHÂN VIÊN
# Mỗi tài khoản = 1 máy nhân viên. Sếp cấp tài khoản + mật khẩu; máy nhân viên đăng nhập 1 lần để nhận token
# (máy không lưu mật khẩu). Đăng nhập lại ở máy khác thì token cũ của tài khoản đó bị thay.
import re as _re
_USER_RE = _re.compile(r"^[a-z0-9][a-z0-9_.@+-]{2,63}$")   # cho phép dùng email làm tên đăng nhập
_PBKDF_ROUNDS = 200_000
_FAILS = {}            # key -> [thời điểm sai]  (chống dò mật khẩu)
MAX_FAILS_USER, MAX_FAILS_IP, FAIL_WINDOW = 8, 40, 10 * 60


def _pw_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF_ROUNDS).hex()
    return salt, h


def _pw_ok(acc, password):
    _, h = _pw_hash(password, acc.get("salt"))
    return hmac.compare_digest(h, acc.get("pw_hash", ""))


def gen_password(n=10):
    return "".join(secrets.choice("abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(n))


def _public(a, devices=None, stats=None):
    d = (devices or {}).get(a.get("device_id") or "", {})
    now = time.time()
    online = bool(d) and not d.get("revoked") and (now - d.get("last_seen", 0)) < ONLINE_SECONDS
    return {
        "username": a["username"], "display_name": a.get("display_name") or a["username"],
        "role": a.get("role", "staff"), "locked": bool(a.get("locked")),
        "created": a.get("created", 0), "last_login": a.get("last_login", 0), "last_ip": a.get("last_ip", ""),
        "device_id": a.get("device_id", ""), "online": online, "last_seen": d.get("last_seen", 0),
        "state": d.get("state", {}), "hostname": d.get("hostname", ""),
        "stats": (stats or {}).get(a.get("device_id") or "", {"jobs": 0, "units": 0, "chars": 0, "last": 0}),
    }


def list_accounts():
    accs = _read(ACCOUNTS_FILE, {})
    devices = _read(DEVICES_FILE, {})
    stats = {d["id"]: d["stats"] for d in list_devices()}
    out = [_public(a, devices, stats) for a in accs.values()]
    out.sort(key=lambda x: (x["locked"], x["username"]))
    return out


def create_account(username, display_name="", password="", role="staff"):
    u = (username or "").strip().lower()
    role = role if role in ("staff", "admin") else "staff"
    if not _USER_RE.match(u):
        raise ValueError("Tên đăng nhập 3-64 ký tự: chữ thường, số, dấu . _ - @ + (VD: mac02 hoặc email).")
    password = password or gen_password()
    if len(password) < 6:
        raise ValueError("Mật khẩu tối thiểu 6 ký tự.")
    with _LOCK:
        accs = _read(ACCOUNTS_FILE, {})
        if u in accs:
            raise ValueError("Tài khoản này đã tồn tại.")
        salt, h = _pw_hash(password)
        accs[u] = {"username": u, "display_name": (display_name or u).strip()[:60], "role": role,
                   "salt": salt, "pw_hash": h, "created": time.time(), "last_login": 0, "last_ip": "",
                   "locked": False, "device_id": ""}
        _write(ACCOUNTS_FILE, accs)
    return _public(accs[u]), password


def update_account(username, display_name=None, password=None, locked=None):
    u = (username or "").strip().lower()
    new_pw = None
    with _LOCK:
        accs = _read(ACCOUNTS_FILE, {})
        a = accs.get(u)
        if not a:
            return None
        if display_name is not None and str(display_name).strip():
            a["display_name"] = str(display_name).strip()[:60]
        if password is not None:
            new_pw = password or gen_password()
            if len(new_pw) < 6:
                raise ValueError("Mật khẩu tối thiểu 6 ký tự.")
            a["salt"], a["pw_hash"] = _pw_hash(new_pw)
        if locked is not None:
            a["locked"] = bool(locked)
        _write(ACCOUNTS_FILE, accs)
        devices = _read(DEVICES_FILE, {})
        d = devices.get(a.get("device_id") or "")
        if d:
            d["name"] = a["display_name"]
            if locked is not None:
                d["revoked"] = bool(locked)         # khoá tài khoản = máy ngừng gửi
            _write(DEVICES_FILE, devices)
    return _public(a), new_pw


def delete_account(username):
    u = (username or "").strip().lower()
    with _LOCK:
        accs = _read(ACCOUNTS_FILE, {})
        a = accs.pop(u, None)
        if not a:
            return False
        _write(ACCOUNTS_FILE, accs)
        devices = _read(DEVICES_FILE, {})
        if a.get("device_id") in devices:
            devices[a["device_id"]]["revoked"] = True   # báo cáo cũ vẫn giữ
            _write(DEVICES_FILE, devices)
    return True


def _throttled(keys):
    now = time.time()
    for k, limit in keys:
        arr = [t for t in _FAILS.get(k, []) if now - t < FAIL_WINDOW]
        _FAILS[k] = arr
        if len(arr) >= limit:
            return True
    return False


def login_account(username, password, hostname="", ip=""):
    """Máy nhân viên đăng nhập. Trả (device_id, token, display_name). Ném PermissionError/ValueError."""
    u = (username or "").strip().lower()
    ip = str(ip or "")[:64]
    keys = [("u:" + u, MAX_FAILS_USER), ("i:" + ip, MAX_FAILS_IP)]
    if _throttled(keys):
        raise PermissionError("Sai quá nhiều lần. Thử lại sau 10 phút.")
    password = password or ""
    with _LOCK:
        accs = _read(ACCOUNTS_FILE, {})
        a = accs.get(u)
        ok = False
        if a:
            ok = _pw_ok(a, password)
        else:
            _pw_hash(password or "x")   # giữ thời gian xử lý gần như nhau
        if not ok:
            now = time.time()
            for k, _ in keys:
                _FAILS.setdefault(k, []).append(now)
            raise PermissionError("Sai tài khoản hoặc mật khẩu.")
        if a.get("locked"):
            raise PermissionError("Tài khoản đã bị khoá. Liên hệ sếp.")
        devices = _read(DEVICES_FILE, {})
        token = secrets.token_urlsafe(32)
        dev_id = a.get("device_id")
        if dev_id and dev_id in devices:
            d = devices[dev_id]
            d.update(token_hash=_hash(token), revoked=False, hostname=str(hostname)[:60], name=a["display_name"])
        else:
            dev_id = "d" + secrets.token_hex(4)
            devices[dev_id] = {"id": dev_id, "name": a["display_name"], "hostname": str(hostname)[:60],
                               "token_hash": _hash(token), "created": time.time(), "last_seen": 0,
                               "revoked": False, "state": {}, "account": u}
            a["device_id"] = dev_id
        a["last_login"] = time.time()
        a["last_ip"] = ip
        for k, _ in keys:
            _FAILS.pop(k, None)
        _write(DEVICES_FILE, devices)
        _write(ACCOUNTS_FILE, accs)
    return dev_id, token, a["display_name"]


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
        "account": str(meta.get("account") or "")[:120],
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


def summary(days=7):
    """Số liệu cho bảng điều khiển: tổng quan, năng suất từng máy, sản lượng theo ngày."""
    import datetime
    now = time.time()
    since = now - days * 86400 if days else 0
    reports = [r for r in list_reports(limit=5000) if r.get("received", 0) >= since]
    devices = list_devices()
    per = {}
    for d in devices:
        per[d["id"]] = {"id": d["id"], "name": d["name"], "online": d["online"], "revoked": d["revoked"],
                        "jobs": 0, "units": 0, "errors": 0, "chars": 0, "seconds": 0, "last": 0}
    total = {"jobs": 0, "units": 0, "errors": 0, "chars": 0, "seconds": 0}
    daily = {}
    for r in reports:
        p = per.setdefault(r["device_id"], {"id": r["device_id"], "name": r.get("device_name", "?"), "online": r["device_id"] == HUB_ID,
                                            "revoked": r["device_id"] != HUB_ID, "jobs": 0, "units": 0, "errors": 0,
                                            "chars": 0, "seconds": 0, "last": 0})
        for t in (p, total):
            t["jobs"] += 1
            t["units"] += r.get("units_done", 0)
            t["errors"] += r.get("units_error", 0)
            t["chars"] += r.get("chars", 0)
            t["seconds"] += r.get("seconds", 0)
        p["last"] = max(p["last"], r.get("received", 0))
        day = datetime.datetime.fromtimestamp(r.get("received", 0)).strftime("%d/%m/%Y")
        daily[day] = daily.get(day, 0) + r.get("units_done", 0)
    n = days if days else 14
    day_list = []
    for i in range(min(n, 14)):
        day = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%d/%m/%Y")
        day_list.append({"day": day, "units": daily.get(day, 0)})
    return {
        "days": days, "total": total,
        "online": sum(1 for d in devices if d["online"]),
        "devices_total": sum(1 for d in devices if not d["revoked"]),
        "waiting_login": sum(1 for d in devices if d["online"] and d["state"].get("gemini_logged_in") is False),
        "running": sum(1 for d in devices if d["online"] and d["state"].get("job")),
        "per_device": sorted(per.values(), key=lambda x: -x["units"]),
        "daily": day_list,
    }


HUB_ID = "hub"
HUB_NAME = "Máy sếp (máy chủ)"


class _LocalFile:
    """Giả lập file upload để máy chủ tự lưu báo cáo cho chính nó."""
    def __init__(self, path):
        self.path = path
        self.filename = os.path.basename(path)

    def save(self, dest):
        shutil.copyfile(self.path, dest)


def save_local_report(job_dir):
    """Máy chủ (chưa ghép cặp với máy nào) tự ghi báo cáo cho các job của chính nó -> hiện trong tab Đội Máy."""
    meta, zpath = job_report(job_dir)
    try:
        save_report({"id": HUB_ID, "name": HUB_NAME}, meta, _LocalFile(zpath) if zpath else None)
    finally:
        if zpath:
            try:
                os.remove(zpath)
            except OSError:
                pass
    return True


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


# ---------------------------------------------------------------- QUẢN TRỊ QUA WEB (Cloudflare Access)
# Đường /api/fleet-admin/* nằm SAU đăng nhập Cloudflare Access của sếp. Cloudflare gắn vào mỗi yêu cầu một thẻ JWT
# ký bằng khoá của Cloudflare; tool kiểm tra chữ ký + đúng ứng dụng (AUD) + còn hạn rồi mới cho quản trị.
# Không tin header tự khai: thẻ giả sẽ sai chữ ký.
ACCESS_TEAM = os.environ.get("ACCESS_TEAM_DOMAIN", "broken-sunset-7301.cloudflareaccess.com")
ACCESS_AUD = os.environ.get("ACCESS_AUD", "529cdc9f0d84e539eff114c0f975241d5322bf9e0ccc360c2c6622511c12e359")
ADMIN_EMAILS_FILE = os.path.join(DATA_DIR, "admin_emails.txt")   # (tuỳ chọn) mỗi dòng 1 email được quản trị
_CERTS = {"at": 0, "keys": {}}


def _b64u(s):
    import base64
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _access_keys(force=False):
    import requests
    if not force and _CERTS["keys"] and time.time() - _CERTS["at"] < 3600:
        return _CERTS["keys"]
    r = requests.get(f"https://{ACCESS_TEAM}/cdn-cgi/access/certs", timeout=10)
    r.raise_for_status()
    keys = {k["kid"]: k for k in r.json().get("keys", []) if k.get("kty") == "RSA"}
    _CERTS.update(at=time.time(), keys=keys)
    return keys


def verify_access_jwt(token, keys=None):
    """Trả payload nếu thẻ hợp lệ, ngược lại None."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    try:
        h64, p64, s64 = token.split(".")
        header = json.loads(_b64u(h64))
        payload = json.loads(_b64u(p64))
        if header.get("alg") != "RS256":
            return None
        ks = keys if keys is not None else _access_keys()
        jwk = ks.get(header.get("kid"))
        if jwk is None and keys is None:
            jwk = _access_keys(force=True).get(header.get("kid"))
        if jwk is None:
            return None
        pub = rsa.RSAPublicNumbers(int.from_bytes(_b64u(jwk["e"]), "big"),
                                   int.from_bytes(_b64u(jwk["n"]), "big")).public_key()
        pub.verify(_b64u(s64), (h64 + "." + p64).encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
        now = time.time()
        aud = payload.get("aud")
        aud = aud if isinstance(aud, list) else [aud]
        if ACCESS_AUD not in aud:
            return None
        if payload.get("iss") != f"https://{ACCESS_TEAM}":
            return None
        if float(payload.get("exp", 0)) < now or float(payload.get("nbf", 0)) > now + 60:
            return None
        return payload
    except Exception:
        return None


def _allowed_emails():
    try:
        with open(ADMIN_EMAILS_FILE, "r", encoding="utf-8") as f:
            return {l.strip().lower() for l in f if l.strip() and not l.startswith("#")}
    except OSError:
        return set()


def admin_identity(request, keys=None):
    """Trả 'local' nếu gọi trực tiếp trên máy chủ, email nếu qua Cloudflare Access hợp lệ, hoặc None."""
    if is_local_request(request):
        return "local"
    tok = request.headers.get("Cf-Access-Jwt-Assertion") or request.cookies.get("CF_Authorization") or ""
    if not tok:
        return None
    payload = verify_access_jwt(tok, keys)
    if not payload:
        return None
    email = str(payload.get("email") or "").lower()
    allowed = _allowed_emails()
    if allowed and email not in allowed:
        return None
    # thao tác ghi qua web cần header riêng (chống CSRF: header tuỳ biến buộc trình duyệt kiểm tra CORS trước)
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-Fleet") != "1":
        return None
    return email or "access"


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


def agent_login(hub_url, username, password, cf_id="", cf_secret="", hostname=""):
    """Máy nhân viên đăng nhập bằng tài khoản sếp cấp. Không lưu mật khẩu, chỉ lưu token."""
    import requests
    hub_url = (hub_url or "").strip().rstrip("/")
    if not hub_url.startswith(("http://", "https://")):
        hub_url = "https://" + hub_url
    h = {}
    if cf_id and cf_secret:
        h = {"CF-Access-Client-Id": cf_id, "CF-Access-Client-Secret": cf_secret}
    r = requests.post(hub_url + "/api/fleet/login", json={"username": username, "password": password,
                                                          "hostname": hostname}, headers=h, timeout=20)
    try:
        j = r.json()
    except ValueError:
        raise RuntimeError("Máy chủ không trả lời đúng định dạng (kiểm tra lại địa chỉ máy chủ / Cloudflare Access).")
    if r.status_code != 200 or j.get("status") != "success":
        raise RuntimeError(j.get("message") or f"Đăng nhập thất bại (HTTP {r.status_code}).")
    cfg = {"hub_url": hub_url, "device_id": j["device_id"], "token": j["token"], "name": j.get("name") or username,
           "account": username.strip().lower(), "cf_id": cf_id, "cf_secret": cf_secret, "paired_at": time.time()}
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
        "model": job.get("model"), "dry_run": job.get("dry_run"), "account": job.get("account") or "",
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
