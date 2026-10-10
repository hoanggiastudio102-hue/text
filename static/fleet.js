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
        const { ok, j } = await jfetch('/api/fleet/admin/overview?days=' + days);
        const hub = ok && j.status === 'success';
        $('flHubDenied').style.display = hub ? 'none' : '';
        $('flHubBox').querySelectorAll('.fl-acc-head,.fl-acc-tools,.fl-tablewrap,.lz-muted:not(#flHubDenied)').forEach(el => el.style.display = hub ? '' : 'none');
        $('flHubData').style.display = hub ? '' : 'none';
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
        const rp = j.reports || [];
        $('flReports').innerHTML = rp.length ? rp.map(r => {
            const full = r.units_total && r.units_done === r.units_total;
            return `<tr><td>${fmtT(r.received)}</td><td>${esc(r.device_name)}</td><td>${esc(r.name || (r.articles || []).join(', '))}</td>
                <td>${esc((r.countries || []).join(' '))}</td>
                <td><span class="fl-badge ${full ? '' : 'partial'}">${r.units_done}/${r.units_total}</span>${r.units_error ? ' <span class="lz-muted">' + r.units_error + ' lỗi</span>' : ''}</td>
                <td>${num(r.chars)}</td>
                <td>${r.file ? `<a class="btn-primary fl-mini" style="text-decoration:none" href="/api/fleet/admin/report/${r.device_id}/${r.job_id}/file"><i class="fa-solid fa-download"></i> Tải</a>` : ''}</td></tr>`;
        }).join('') : '<tr><td colspan="7" class="lz-muted">Chưa có sản phẩm nào trong kỳ này.</td></tr>';
    }


    // ---------- tài khoản nhân viên ----------
    let accounts = [], accFilter = 'all';
    async function loadAccounts() {
        const { ok, j } = await jfetch('/api/fleet/admin/accounts');
        if (!ok || j.status !== 'success') return;
        accounts = j.accounts || [];
        renderAccounts();
    }
    function renderAccounts() {
        const q = ($('flAccSearch').value || '').trim().toLowerCase();
        const rows = accounts.filter(a => (accFilter === 'all' || (accFilter === 'locked') === a.locked)
            && (!q || (a.username + ' ' + a.display_name).toLowerCase().includes(q)));
        $('flAccounts').innerHTML = rows.length ? rows.map(a => {
            const st = a.locked ? '<span class="fl-pill off">Đã khoá</span>'
                : a.online ? (a.state && a.state.job ? '<span class="fl-pill run">Đang chạy</span>' : '<span class="fl-pill on">Đang kết nối</span>')
                : a.last_login ? '<span class="fl-pill off">Ngoại tuyến · ' + ago(a.last_seen || a.last_login) + '</span>' : '<span class="fl-pill warn">Chưa đăng nhập máy</span>';
            const gem = a.online && a.state && a.state.gemini_logged_in === false ? '<div class="lz-muted" style="color:#fcd34d">Chưa đăng nhập Gemini</div>' : '';
            return `<tr><td><div class="fl-user"><span class="fl-av">${esc((a.display_name || a.username).charAt(0).toUpperCase())}</span>
                <div><b>${esc(a.display_name)}</b> <button class="fl-link" data-act="rename" data-u="${esc(a.username)}" title="Đổi tên hiển thị"><i class="fa-solid fa-pen"></i></button>
                <div class="lz-muted">@${esc(a.username)} · tạo ${fmtT(a.created)}</div></div></div></td>
                <td>${st}${gem}</td><td>${a.last_login ? ago(a.last_login) : '—'}</td><td>${esc(a.last_ip || '—')}</td>
                <td>${num(a.stats.units)} bản<div class="lz-muted">${num(a.stats.jobs)} job</div></td>
                <td class="fl-acts"><button class="btn-primary fl-mini" data-act="pass" data-u="${esc(a.username)}">Đặt mật khẩu</button>
                <button class="btn-primary fl-mini" data-act="${a.locked ? 'unlock' : 'lock'}" data-u="${esc(a.username)}">${a.locked ? 'Mở khoá' : 'Khoá'}</button>
                <button class="btn-primary fl-danger fl-mini" data-act="del" data-u="${esc(a.username)}">Xoá</button></td></tr>`;
        }).join('') : '<tr><td colspan="6" class="lz-muted">Không có tài khoản nào khớp.</td></tr>';
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
            const { j } = await jfetch('/api/fleet/admin/accounts', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: $('flAccUser').value, display_name: $('flAccName').value, password: $('flAccPass').value }) });
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
            const patch = async (body) => (await jfetch('/api/fleet/admin/accounts/' + encodeURIComponent(u), { method: 'PATCH',
                headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).j;
            if (b.dataset.act === 'pass') {
                if (!confirm('Tạo mật khẩu mới cho ' + a.display_name + '? Máy đang dùng vẫn chạy, mật khẩu mới dùng cho lần đăng nhập sau.')) return;
                const j = await patch({ reset_password: true }); if (j.status === 'success') showCred('Mật khẩu mới', a, j.password); else toast(j.message || 'Lỗi', true);
            } else if (b.dataset.act === 'lock' || b.dataset.act === 'unlock') {
                const lock = b.dataset.act === 'lock';
                if (lock && !confirm('Khoá ' + a.display_name + '? Máy này sẽ ngừng gửi báo cáo (giữ lịch sử, mở khoá lại được).')) return;
                await patch({ locked: lock }); toast(lock ? 'Đã khoá' : 'Đã mở khoá');
            } else if (b.dataset.act === 'rename') {
                const n = prompt('Tên hiển thị mới:', a.display_name); if (n && n.trim()) await patch({ display_name: n.trim() });
            } else if (b.dataset.act === 'del') {
                if (!confirm('XOÁ tài khoản ' + a.display_name + '? Máy bị thu hồi, báo cáo cũ vẫn giữ. Nếu chỉ tạm nghỉ, nên dùng Khoá.')) return;
                await jfetch('/api/fleet/admin/accounts/' + encodeURIComponent(u), { method: 'DELETE' }); toast('Đã xoá');
            }
            refresh();
        });
    }

    function refresh() { loadAgent().catch(() => { }); loadHub().catch(() => { }); }

    function init() {
        if (!$('tab-fleet')) return;
        initAccounts();
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
            await jfetch('/api/fleet/admin/device/' + b.dataset.id + '?mode=' + (forget ? 'forget' : 'revoke'), { method: 'DELETE' });
            refresh();
        });
    }
    document.addEventListener('DOMContentLoaded', init);
})();
