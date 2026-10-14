/* Tab "Đội Máy": máy nhân viên ghép với máy chủ + máy chủ xem máy/sản phẩm gửi về. */
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    let tt;
    const toast = (m, err) => { const t = $('toast'); if (!t) return; t.textContent = m;
        t.style.background = err ? 'rgba(239,68,68,0.9)' : 'rgba(16,185,129,0.9)'; t.classList.add('show');
        clearTimeout(tt); tt = setTimeout(() => t.classList.remove('show'), 3500); };
    const fmtT = (t) => t ? new Date(t * 1000).toLocaleString('vi-VN') : '—';
    const ago = (t) => { if (!t) return 'chưa kết nối'; const s = Math.max(0, Date.now() / 1000 - t);
        return s < 90 ? 'vừa xong' : s < 3600 ? Math.round(s / 60) + ' phút trước' : s < 86400 ? Math.round(s / 3600) + ' giờ trước' : Math.round(s / 86400) + ' ngày trước'; };
    async function jfetch(url, opt) {
        opt = Object.assign({}, opt); opt.headers = Object.assign({ 'X-Fleet': '1' }, opt.headers || {});
        const r = await fetch(url, opt); let j = {};
        try { j = await r.json(); } catch (e) { }
        return { ok: r.ok, status: r.status, j };
    }
    let timer = null;

    async function loadAgent() {
        const { j } = await jfetch('/api/fleet/agent');
        const paired = !!j.paired;
        $('flAgentPaired').style.display = paired ? '' : 'none';
        $('flAgentForm').style.display = paired ? 'none' : '';
        if (!paired) return;
        const recent = j.last_ping && (Date.now() / 1000 - j.last_ping) < 90;
        $('flAgentDot').className = 'fl-dot ' + (recent && !j.last_error ? 'on' : 'warn');
        $('flAgentName').textContent = (j.name || 'Máy này') + ' → ' + j.hub_url;
        $('flAgentInfo').innerHTML = (recent ? 'Đã kết nối, báo cáo lần cuối ' + ago(j.last_ping) : 'Chưa thông với máy chủ')
            + ' · Đã gửi ' + j.sent + ' job' + (j.failed ? ' · <span style="color:#fcd34d">' + j.failed + ' job chờ gửi lại</span>' : '')
            + (j.last_error ? '<br><span style="color:#fca5a5">' + esc(j.last_error) + '</span>' : '');
    }

    const fmtDur = (s) => { s = Math.max(0, Math.round(s || 0)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
        return h + ':' + String(m).padStart(2, '0') + ':' + String(x).padStart(2, '0'); };
    const num = (n) => (n || 0).toLocaleString('vi-VN');

    async function loadHub() {
        const days = $('flRange') ? $('flRange').value : 7;
        const { ok, j } = await jfetch('/api/fleet-admin/overview?days=' + days);
        const hub = ok && j.status === 'success';
        $('flHubDenied').style.display = hub ? 'none' : '';
        $('flHubBox').querySelectorAll('.fl-acc-head,.fl-acc-tools,.fl-tablewrap,.lz-muted:not(#flHubDenied)').forEach(el => el.style.display = hub ? '' : 'none');
        $('flHubData').style.display = hub ? '' : 'none';
        $('flIpBox').style.display = hub ? '' : 'none';
        if (!hub) return;
        const sm = j.summary, t = sm.total;
        $('kJobs').textContent = num(t.jobs);
        $('kJobsSub').textContent = num(t.units + t.errors) + ' bản trong kỳ';
        $('kUnits').textContent = num(t.units);
        $('kUnitsSub').textContent = t.errors ? num(t.errors) + ' bản lỗi' : 'không có bản lỗi';
        $('kChars').textContent = num(t.chars);
        $('kTime').textContent = fmtDur(t.seconds);
        $('flStatusLine').innerHTML = `<span class="fl-dot ${sm.online ? 'on' : ''}"></span> <b>${sm.online}</b>/${sm.devices_total} máy đang kết nối`
            + (sm.running ? ` · <span style="color:#93c5fd">${sm.running} máy đang chạy job</span>` : '')
            + (sm.waiting_login ? ` · <span style="color:#fcd34d">${sm.waiting_login} máy chưa đăng nhập Gemini</span>` : '')
            + (t.errors ? ` · <span style="color:#fca5a5">${t.errors} bản lỗi</span>` : '');
        const devById = {}; (j.devices || []).forEach(d => devById[d.id] = d);
        $('flPerDevice').innerHTML = sm.per_device.length ? sm.per_device.map(p => {
            const d = devById[p.id] || {}; const st = d.state || {};
            let stat = p.revoked ? '<span class="fl-pill off">Đã thu hồi</span>' : !p.online ? '<span class="fl-pill off">Ngoại tuyến · ' + ago(d.last_seen) + '</span>'
                : st.job ? '<span class="fl-pill run"><i class="fa-solid fa-spinner fa-spin"></i> Đang chạy</span>'
                : st.gemini_logged_in === false ? '<span class="fl-pill warn">Chưa đăng nhập Gemini</span>' : '<span class="fl-pill on">Sẵn sàng</span>';
            return `<tr><td><b>${esc(p.name)}</b><div class="lz-muted">${esc(d.hostname || '')} ${esc(st.model || '')}</div></td><td>${stat}</td>
                <td>${num(p.jobs)}</td><td>${num(p.units)}</td><td>${p.errors ? '<span style="color:#fca5a5">' + p.errors + '</span>' : 0}</td>
                <td>${num(p.chars)}</td><td>${fmtDur(p.seconds)}</td><td>${p.last ? fmtT(p.last) : '—'}</td>
                <td>${p.revoked ? '' : `<button class="btn-primary fl-danger fl-mini" data-act="revoke" data-id="${p.id}">Thu hồi</button>`}
                <button class="btn-primary fl-mini" data-act="forget" data-id="${p.id}">Xoá</button></td></tr>`;
        }).join('') : '<tr><td colspan="9" class="lz-muted">Chưa có máy nào. Cấp tài khoản ở ô bên dưới.</td></tr>';
        const max = Math.max(1, ...sm.daily.map(x => x.units));
        $('flDaily').innerHTML = sm.daily.map(x => `<div class="fl-drow"><span>${x.day}</span>
            <div class="fl-bar"><i style="width:${Math.round(x.units / max * 100)}%"></i></div><b>${x.units} bản</b></div>`).join('');
        loadAccounts().catch(() => { });
        loadIp().catch(() => { });
        const rp = j.reports || [];
        $('flReports').innerHTML = rp.length ? rp.map(r => {
            const full = r.units_total && r.units_done === r.units_total;
            return `<tr><td>${fmtT(r.received)}</td><td>${esc(r.device_name)}</td><td>${esc(r.name || (r.articles || []).join(', '))}</td>
                <td>${esc((r.countries || []).join(' '))}</td>
                <td><span class="fl-badge ${full ? '' : 'partial'}">${r.units_done}/${r.units_total}</span>${r.units_error ? ' <span class="lz-muted">' + r.units_error + ' lỗi</span>' : ''}</td>
                <td style="font-size:12px">${esc(r.account || '—')}</td>
                <td>${num(r.chars)}</td>
                <td>${r.file ? `<a class="btn-primary fl-mini" style="text-decoration:none" href="/api/fleet-admin/report/${r.device_id}/${r.job_id}/file"><i class="fa-solid fa-download"></i> Tải</a>` : ''}</td></tr>`;
        }).join('') : '<tr><td colspan="8" class="lz-muted">Chưa có sản phẩm nào trong kỳ này.</td></tr>';
    }


    // ---------- tài khoản nhân viên ----------
    let accounts = [], accFilter = 'all';
    async function loadAccounts() {
        const { ok, j } = await jfetch('/api/fleet-admin/accounts');
        if (!ok || j.status !== 'success') return;
        accounts = j.accounts || [];
        renderAccounts();
    }
    function renderAccounts() {
        const q = ($('flAccSearch').value || '').trim().toLowerCase();
        const rows = accounts.filter(a => (accFilter === 'all' || (accFilter === 'locked') === a.locked)
            && (!q || (a.username + ' ' + a.display_name).toLowerCase().includes(q)));
        $('flAccounts').innerHTML = rows.length ? rows.map(a => {
            const st = a.locked ? '<span class="fl-pill off">Đã khoá</span>' : '<span class="fl-pill on">Hoạt động</span>';
            const conn = a.locked ? '' : a.online ? (a.state && a.state.job ? 'đang chạy job' : 'máy đang kết nối')
                : a.last_login ? 'ngoại tuyến · ' + ago(a.last_seen || a.last_login) : 'chưa đăng nhập máy';
            const gem = a.online && a.state && a.state.gemini_logged_in === false ? ' · <span style="color:#fcd34d">chưa đăng nhập Gemini</span>' : '';
            const role = a.role === 'admin' ? 'Quản trị' : 'Nhân viên';
            const day = a.created ? new Date(a.created * 1000).toLocaleString('vi-VN', { hour12: false }) : '—';
            return `<tr><td><b>${esc(a.username)}</b></td>
                <td>${esc(a.display_name)} <button class="fl-link" data-act="rename" data-u="${esc(a.username)}" title="Đổi tên hiển thị"><i class="fa-solid fa-pen"></i></button></td>
                <td>${a.state && a.state.google ? esc(a.state.google) : (a.last_login ? '<span class="lz-muted">chưa báo</span>' : '—')}</td>
                <td>${ipCell(a)}</td>
                <td>${role}</td>
                <td>${st}<div class="lz-muted">${conn}${gem}</div></td>
                <td>${day}</td>
                <td class="fl-acts"><button class="btn-primary fl-mini" data-act="${a.locked ? 'unlock' : 'lock'}" data-u="${esc(a.username)}"><i class="fa-solid fa-lock${a.locked ? '-open' : ''}"></i> ${a.locked ? 'Mở khoá' : 'Khoá'}</button>
                <button class="btn-primary fl-mini" data-act="ip" data-u="${esc(a.username)}" title="Lịch sử IP, khoá IP"><i class="fa-solid fa-network-wired"></i> IP</button>
                <button class="btn-primary fl-mini" data-act="pass" data-u="${esc(a.username)}"><i class="fa-solid fa-key"></i> Đổi mật khẩu</button>
                <button class="btn-primary fl-danger fl-mini" data-act="del" data-u="${esc(a.username)}" title="Xoá tài khoản"><i class="fa-solid fa-trash"></i></button></td></tr>`;
        }).join('') : '<tr><td colspan="8" class="lz-muted">Không có tài khoản nào khớp.</td></tr>';
    }
    function ipCell(a) {
        if (!a.ip) return '<span class="lz-muted">—</span>';
        const n = (a.ip_history || []).length;
        const lock = a.ip_lock ? ' <i class="fa-solid fa-shield-halved" style="color:#6ee7b7" title="Đã khoá IP: chỉ cho dùng từ IP được phép"></i>' : '';
        const alert = a.ip_alert ? ` <button class="fl-pill warn fl-ipwarn" data-act="ipseen" data-u="${esc(a.username)}" title="Xuất hiện IP mới ${esc(a.ip_alert.ip)} lúc ${fmtT(a.ip_alert.at)} (trước đó ${esc(a.ip_alert.prev || '—')}). Bấm = đã xem">⚠ IP mới</button>` : '';
        return `<span class="fl-ip">${esc(a.ip)}</span>${lock}${alert}<div class="lz-muted">${n > 1 ? n + ' IP đã dùng · ' : ''}${a.last_ip_at ? ago(a.last_ip_at) : ''}</div>`;
    }

    // ---------- quản lý IP ----------
    const EV = { fail: ['Sai mật khẩu', 'warn'], denied: ['Bị chặn', 'off'], new_ip: ['IP mới', 'run'] };
    let myIp = '';
    async function loadIp() {
        const { ok, j } = await jfetch('/api/fleet-admin/ip');
        if (!ok || j.status !== 'success') return;
        myIp = j.my_ip || '';
        $('flMyIp').textContent = myIp ? '— IP sếp đang dùng: ' + myIp : '';
        $('flIpBlocked').innerHTML = (j.blocked || []).length ? j.blocked.map(b => `<div class="fl-iprow"><span><span class="fl-ip">${esc(b.ip)}</span>
            <span class="lz-muted">${esc(b.note || '')} · ${fmtT(b.at)}</span></span>
            <button class="btn-primary fl-mini" data-ipact="unblock" data-ip="${esc(b.ip)}">Bỏ chặn</button></div>`).join('')
            : '<span class="lz-muted">Chưa chặn IP nào.</span>';
        $('flIpThrottled').innerHTML = (j.throttled || []).length ? j.throttled.map(t => `<div class="fl-iprow"><span><span class="fl-ip">${esc(t.ip)}</span>
            <span class="lz-muted">${t.fails} lần sai${t.locked ? ' · khoá đến ' + new Date(t.until * 1000).toLocaleTimeString('vi-VN') : ''}</span></span>
            <span><button class="btn-primary fl-mini" data-ipact="unblock" data-ip="${esc(t.ip)}">Gỡ</button>
            <button class="btn-primary fl-danger fl-mini" data-ipact="block" data-ip="${esc(t.ip)}">Chặn hẳn</button></span></div>`).join('')
            : '<span class="lz-muted">Không có.</span>';
        const blocked = new Set((j.blocked || []).map(b => b.ip));
        $('flIpEvents').innerHTML = (j.events || []).length ? j.events.map(e => {
            const k = EV[e.kind] || [e.kind, ''];
            return `<tr><td style="white-space:nowrap">${fmtT(e.at)}</td><td><span class="fl-ip">${esc(e.ip || '—')}</span></td><td>${esc(e.user || '')}</td>
                <td><span class="fl-pill ${k[1]}">${k[0]}</span> <span class="lz-muted">${esc(e.msg || '')}</span></td>
                <td>${e.ip && !blocked.has(e.ip) && e.ip !== myIp ? `<button class="btn-primary fl-danger fl-mini" data-ipact="block" data-ip="${esc(e.ip)}">Chặn</button>` : ''}</td></tr>`;
        }).join('') : '<tr><td colspan="5" class="lz-muted">Chưa có sự kiện nào.</td></tr>';
    }
    async function ipAction(action, ip, note) {
        const { j } = await jfetch('/api/fleet-admin/ip', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, ip, note: note || '' }) });
        if (j.status !== 'success') { toast(j.message || 'Lỗi', true); return false; }
        toast(action === 'block' ? 'Đã chặn ' + ip : 'Đã bỏ chặn ' + ip); loadIp().catch(() => { }); return true;
    }
    let ipUser = null;
    function openIpModal(a) {
        ipUser = a.username;
        $('flIpModalTitle').textContent = 'IP — ' + a.display_name + ' (' + a.username + ')';
        $('flIpErr').style.display = 'none';
        $('flIpLock').checked = !!a.ip_lock;
        $('flIpAllowed').value = (a.allowed_ips || []).join('\n');
        const hist = a.ip_history || [];
        $('flIpHist').innerHTML = hist.length ? hist.map(h => `<tr><td><span class="fl-ip">${esc(h.ip)}</span>${h.ip === a.ip ? ' <span class="fl-pill on">hiện tại</span>' : ''}</td>
            <td>${fmtT(h.first)}</td><td>${fmtT(h.last)}</td>
            <td class="fl-acts"><button class="btn-primary fl-mini" data-hact="allow" data-ip="${esc(h.ip)}">Cho phép</button>
            <button class="btn-primary fl-danger fl-mini" data-hact="block" data-ip="${esc(h.ip)}">Chặn</button></td></tr>`).join('')
            : '<tr><td colspan="4" class="lz-muted">Máy chưa kết nối lần nào.</td></tr>';
        $('flIpModal').style.display = 'flex';
    }
    function addAllowed(ip) {
        if (!ip) return;
        const cur = $('flIpAllowed').value.split(/[\s,;]+/).filter(Boolean);
        if (!cur.includes(ip)) cur.push(ip);
        $('flIpAllowed').value = cur.join('\n');
    }
    function initIp() {
        $('flIpBlock').addEventListener('click', async () => {
            const ip = $('flIpNew').value.trim(); if (!ip) return toast('Nhập IP cần chặn', true);
            if (await ipAction('block', ip, $('flIpNote').value.trim())) { $('flIpNew').value = ''; $('flIpNote').value = ''; }
        });
        $('flIpBox').addEventListener('click', async (e) => {
            const b = e.target.closest('[data-ipact]'); if (!b) return;
            const ip = b.dataset.ip;
            if (b.dataset.ipact === 'block' && !confirm('Chặn IP ' + ip + '? Mọi máy dùng IP này sẽ không đăng nhập / gửi sản phẩm được (máy cùng văn phòng thường chung IP).')) return;
            await ipAction(b.dataset.ipact, ip);
        });
        $('flIpModalClose').addEventListener('click', () => { $('flIpModal').style.display = 'none'; });
        $('flIpAddCur').addEventListener('click', () => { const a = accounts.find(x => x.username === ipUser); addAllowed(a && a.ip); });
        $('flIpHist').addEventListener('click', async (e) => {
            const b = e.target.closest('[data-hact]'); if (!b) return;
            if (b.dataset.hact === 'allow') addAllowed(b.dataset.ip);
            else if (confirm('Chặn IP ' + b.dataset.ip + ' cho TẤT CẢ tài khoản?')) await ipAction('block', b.dataset.ip, 'chặn từ ' + ipUser);
        });
        $('flIpSave').addEventListener('click', async () => {
            const lock = $('flIpLock').checked, list = $('flIpAllowed').value;
            const a = accounts.find(x => x.username === ipUser);
            if (lock && a && a.ip && !list.includes(a.ip) && !confirm('IP hiện tại của máy (' + a.ip + ') KHÔNG có trong danh sách → máy sẽ bị ngắt ngay. Vẫn lưu?')) return;
            const { j } = await jfetch('/api/fleet-admin/accounts/' + encodeURIComponent(ipUser), { method: 'PATCH',
                headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ allowed_ips: list, ip_lock: lock }) });
            if (j.status !== 'success') { $('flIpErr').textContent = j.message || 'Lỗi'; $('flIpErr').style.display = ''; return; }
            $('flIpModal').style.display = 'none'; toast(lock ? 'Đã khoá IP cho tài khoản này' : 'Đã lưu (không khoá IP)'); loadAccounts();
        });
    }

    function showCred(title, acc, pw) {
        $('flAccModalTitle').textContent = title;
        $('flAccForm').style.display = 'none'; $('flAccDone').style.display = '';
        const hub = location.origin.includes('localhost') ? 'https://text.vinhglobal.vn' : location.origin;
        $('flAccCred').textContent = `Tool: Tái Sáng Tạo (Vinh Global)\nMáy chủ: ${hub}\nTài khoản: ${acc.username}\nMật khẩu: ${pw}\n\nCách dùng: mở tab "Đội Máy" → ô "Máy này → kết nối máy chủ" → nhập tài khoản và mật khẩu → Đăng nhập máy chủ.`;
        $('flAccModal').style.display = 'flex';
    }
    function initAccounts() {
        $('flAccNew').addEventListener('click', () => {
            $('flAccModalTitle').textContent = 'Cấp tài khoản';
            $('flAccForm').reset(); $('flAccErr').style.display = 'none';
            $('flAccForm').style.display = ''; $('flAccDone').style.display = 'none';
            $('flAccModal').style.display = 'flex'; $('flAccUser').focus();
        });
        $('flAccModalClose').addEventListener('click', () => { $('flAccModal').style.display = 'none'; });
        $('flAccGen').addEventListener('click', () => {
            const c = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'; let p = '';
            const buf = new Uint32Array(10); crypto.getRandomValues(buf); buf.forEach(n => p += c[n % c.length]);
            $('flAccPass').value = p;
        });
        $('flAccForm').addEventListener('submit', async (e) => {
            e.preventDefault(); $('flAccErr').style.display = 'none';
            const { j } = await jfetch('/api/fleet-admin/accounts', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: $('flAccUser').value, display_name: $('flAccName').value, password: $('flAccPass').value, role: $('flAccRole').value }) });
            if (j.status !== 'success') { $('flAccErr').textContent = j.message || 'Không tạo được tài khoản'; $('flAccErr').style.display = ''; return; }
            showCred('Đã tạo tài khoản', j.account, j.password); loadAccounts();
        });
        $('flAccCopy').addEventListener('click', async () => {
            try { await navigator.clipboard.writeText($('flAccCred').textContent); toast('Đã sao chép'); } catch (e) { toast('Hãy bôi đen và copy tay', true); }
        });
        $('flAccSearch').addEventListener('input', renderAccounts);
        $('flAccChips').addEventListener('click', (e) => {
            const b = e.target.closest('button[data-f]'); if (!b) return;
            accFilter = b.dataset.f;
            $('flAccChips').querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b)); renderAccounts();
        });
        $('flAccounts').addEventListener('click', async (e) => {
            const b = e.target.closest('[data-act]'); if (!b) return;
            const u = b.dataset.u, a = accounts.find(x => x.username === u); if (!a) return;
            const patch = async (body) => (await jfetch('/api/fleet-admin/accounts/' + encodeURIComponent(u), { method: 'PATCH',
                headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).j;
            if (b.dataset.act === 'ip') { openIpModal(a); return; }
            if (b.dataset.act === 'ipseen') { await patch({ clear_ip_alert: true }); loadAccounts(); return; }
            if (b.dataset.act === 'pass') {
                const np = prompt('Mật khẩu mới cho ' + a.display_name + ' (tối thiểu 6 ký tự).\nĐể trống = Tool tạo ngẫu nhiên. Máy đang dùng vẫn chạy, mật khẩu mới dùng cho lần đăng nhập sau.', '');
                if (np === null) return;
                const j = await patch({ reset_password: true, password: np.trim() }); if (j.status === 'success') showCred('Mật khẩu mới', a, j.password); else toast(j.message || 'Lỗi', true);
            } else if (b.dataset.act === 'lock' || b.dataset.act === 'unlock') {
                const lock = b.dataset.act === 'lock';
                if (lock && !confirm('Khoá ' + a.display_name + '? Máy này sẽ ngừng gửi báo cáo (giữ lịch sử, mở khoá lại được).')) return;
                await patch({ locked: lock }); toast(lock ? 'Đã khoá' : 'Đã mở khoá');
            } else if (b.dataset.act === 'rename') {
                const n = prompt('Tên hiển thị mới:', a.display_name); if (n && n.trim()) await patch({ display_name: n.trim() });
            } else if (b.dataset.act === 'del') {
                if (!confirm('XOÁ tài khoản ' + a.display_name + '? Máy bị thu hồi, báo cáo cũ vẫn giữ. Nếu chỉ tạm nghỉ, nên dùng Khoá.')) return;
                await jfetch('/api/fleet-admin/accounts/' + encodeURIComponent(u), { method: 'DELETE' }); toast('Đã xoá');
            }
            refresh();
        });
    }

    function refresh() { loadAgent().catch(() => { }); loadHub().catch(() => { }); }

    function init() {
        if (!$('tab-fleet')) return;
        initAccounts();
        initIp();
        document.querySelector('[data-tab="tab-fleet"]').addEventListener('click', () => {
            refresh(); clearInterval(timer); timer = setInterval(() => {
                if ($('tab-fleet').classList.contains('active')) refresh(); else { clearInterval(timer); }
            }, 8000);
        });
        $('flAgentForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const err = $('flAgentErr'); err.style.display = 'none';
            $('flPairBtn').disabled = true;
            const { j } = await jfetch('/api/fleet/agent/login', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hub_url: $('flHubUrl').value, username: $('flUser').value, password: $('flPass').value, cf_id: $('flCfId').value, cf_secret: $('flCfSecret').value })
            });
            $('flPairBtn').disabled = false;
            if (j.status === 'success') { toast('Đã đăng nhập máy chủ'); $('flPass').value = ''; setTimeout(refresh, 1500); }
            else { err.textContent = j.message || 'Đăng nhập thất bại'; err.style.display = ''; }
        });
        $('flAgentUnpair').addEventListener('click', async () => {
            if (!confirm('Ngắt kết nối với máy chủ? Máy này sẽ ngừng gửi sản phẩm.')) return;
            await jfetch('/api/fleet/agent/unpair', { method: 'POST' }); refresh();
        });
        $('flAgentSync').addEventListener('click', async () => {
            await jfetch('/api/fleet/agent/sync', { method: 'POST' }); toast('Đang gửi lại…'); setTimeout(refresh, 2500);
        });
        $('flRange').addEventListener('change', refresh);
        $('flRefresh').addEventListener('click', refresh);
        $('flPerDevice').addEventListener('click', async (e) => {
            const b = e.target.closest('button[data-act]'); if (!b) return;
            const forget = b.dataset.act === 'forget';
            if (!confirm(forget ? 'Xoá máy này khỏi danh sách? (báo cáo cũ vẫn giữ)' : 'Thu hồi máy này? Máy sẽ không gửi được nữa.')) return;
            await jfetch('/api/fleet-admin/device/' + b.dataset.id + '?mode=' + (forget ? 'forget' : 'revoke'), { method: 'DELETE' });
            refresh();
        });
    }
    document.addEventListener('DOMContentLoaded', init);
})();
