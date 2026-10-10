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

    async function loadHub() {
        const { ok, status, j } = await jfetch('/api/fleet/admin/overview');
        const hub = ok && j.status === 'success';
        $('flHubDenied').style.display = hub ? 'none' : '';
        $('flCodeForm').style.display = hub ? '' : 'none';
        $('flHubData').style.display = hub ? '' : 'none';
        if (!hub) return;
        const dv = j.devices || [];
        $('flDevices').innerHTML = dv.length ? dv.map(d => {
            const st = d.state || {};
            const job = st.job ? '<br><i class="fa-solid fa-spinner fa-spin"></i> Đang chạy job' : '';
            const login = st.gemini_logged_in === false ? '<br><span style="color:#fcd34d">Chưa đăng nhập Gemini</span>' : '';
            return `<div class="fl-dev ${d.online ? '' : 'off'}">
                <div class="nm"><span class="fl-dot ${d.online ? 'on' : ''}"></span>${esc(d.name)}${d.revoked ? ' <span class="lz-muted">(đã thu hồi)</span>' : ''}</div>
                <div class="meta">${d.online ? 'Đang trực tuyến' : 'Thấy lần cuối: ' + ago(d.last_seen)}${job}${login}<br>
                ${esc(st.model || '')} ${esc(st.os || '')} ${esc(d.hostname || '')}<br>
                Đã gửi <b>${d.stats.jobs}</b> job · <b>${d.stats.units}</b> bản · ${(d.stats.chars || 0).toLocaleString('vi-VN')} ký tự</div>
                <div class="acts">${d.revoked ? '' : `<button class="btn-primary fl-danger" data-act="revoke" data-id="${d.id}">Thu hồi</button>`}
                <button class="btn-primary" data-act="forget" data-id="${d.id}">Xoá</button></div></div>`;
        }).join('') : '<div class="lz-muted">Chưa có máy nào ghép.</div>';
        const rp = j.reports || [];
        $('flReports').innerHTML = rp.length ? rp.map(r => {
            const full = r.units_total && r.units_done === r.units_total;
            return `<tr><td>${fmtT(r.received)}</td><td>${esc(r.device_name)}</td><td>${esc(r.name || (r.articles || []).join(', '))}</td>
                <td>${esc((r.countries || []).join(' '))}</td>
                <td><span class="fl-badge ${full ? '' : 'partial'}">${r.units_done}/${r.units_total}</span>${r.units_error ? ' <span class="lz-muted">' + r.units_error + ' lỗi</span>' : ''}</td>
                <td>${(r.chars || 0).toLocaleString('vi-VN')}</td>
                <td>${r.file ? `<a class="btn-primary" style="padding:4px 10px;font-size:12px;text-decoration:none" href="/api/fleet/admin/report/${r.device_id}/${r.job_id}/file"><i class="fa-solid fa-download"></i> Tải</a>` : ''}</td></tr>`;
        }).join('') : '<tr><td colspan="7" class="lz-muted">Chưa có sản phẩm nào.</td></tr>';
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
        $('flDevices').addEventListener('click', async (e) => {
            const b = e.target.closest('button[data-act]'); if (!b) return;
            const forget = b.dataset.act === 'forget';
            if (!confirm(forget ? 'Xoá máy này khỏi danh sách? (báo cáo cũ vẫn giữ)' : 'Thu hồi máy này? Máy sẽ không gửi được nữa.')) return;
            await jfetch('/api/fleet/admin/device/' + b.dataset.id + '?mode=' + (forget ? 'forget' : 'revoke'), { method: 'DELETE' });
            refresh();
        });
    }
    document.addEventListener('DOMContentLoaded', init);
})();
