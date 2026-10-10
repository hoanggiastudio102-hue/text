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
        $('flCodeForm').style.display = hub ? '' : 'none';
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
        }).join('') : '<tr><td colspan="9" class="lz-muted">Chưa có máy nào ghép. Cấp mã ở ô bên dưới.</td></tr>';
        const max = Math.max(1, ...sm.daily.map(x => x.units));
        $('flDaily').innerHTML = sm.daily.map(x => `<div class="fl-drow"><span>${x.day}</span>
            <div class="fl-bar"><i style="width:${Math.round(x.units / max * 100)}%"></i></div><b>${x.units} bản</b></div>`).join('');
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

    function refresh() { loadAgent().catch(() => { }); loadHub().catch(() => { }); }

    function init() {
        if (!$('tab-fleet')) return;
        document.querySelector('[data-tab="tab-fleet"]').addEventListener('click', () => {
            refresh(); clearInterval(timer); timer = setInterval(() => {
                if ($('tab-fleet').classList.contains('active')) refresh(); else { clearInterval(timer); }
            }, 8000);
        });
        $('flAgentForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const err = $('flAgentErr'); err.style.display = 'none';
            $('flPairBtn').disabled = true;
            const { j } = await jfetch('/api/fleet/agent/pair', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hub_url: $('flHubUrl').value, code: $('flCode').value, cf_id: $('flCfId').value, cf_secret: $('flCfSecret').value })
            });
            $('flPairBtn').disabled = false;
            if (j.status === 'success') { toast('Đã ghép máy với máy chủ'); $('flCode').value = ''; setTimeout(refresh, 1500); }
            else { err.textContent = j.message || 'Ghép máy thất bại'; err.style.display = ''; }
        });
        $('flAgentUnpair').addEventListener('click', async () => {
            if (!confirm('Ngắt kết nối với máy chủ? Máy này sẽ ngừng gửi sản phẩm.')) return;
            await jfetch('/api/fleet/agent/unpair', { method: 'POST' }); refresh();
        });
        $('flAgentSync').addEventListener('click', async () => {
            await jfetch('/api/fleet/agent/sync', { method: 'POST' }); toast('Đang gửi lại…'); setTimeout(refresh, 2500);
        });
        $('flCodeForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const { j } = await jfetch('/api/fleet/admin/pair-code', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: $('flDevName').value })
            });
            if (j.status === 'success') {
                const o = $('flCodeOut'); o.style.display = '';
                o.innerHTML = `<div class="lz-muted">Mã ghép cho máy <b>${esc(j.name)}</b> (15 phút, dùng 1 lần)</div><b>${esc(j.code)}</b>`;
            } else toast(j.message || 'Không cấp được mã', true);
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
