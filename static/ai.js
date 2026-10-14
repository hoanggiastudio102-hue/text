/* Tab "Tài Khoản AI": đăng nhập riêng Gemini / ChatGPT / Claude trên máy này + chọn model; ô "Chạy bằng" ở các module. */
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    if (!$('aiCards')) return;
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    let tt;
    const toast = (m, err) => { const t = $('toast'); if (!t) return; t.textContent = m;
        t.style.background = err ? 'rgba(239,68,68,0.9)' : 'rgba(16,185,129,0.9)'; t.classList.add('show');
        clearTimeout(tt); tt = setTimeout(() => t.classList.remove('show'), 4000); };
    const ICON = { gemini: 'fa-brands fa-google', chatgpt: 'fa-solid fa-comment-dots', claude: 'fa-solid fa-asterisk' };
    const HINT = {
        gemini: 'Dùng cho Tái Sáng Tạo, NotebookLM, YouTube → Text. Model đặt ở thanh "Model Gemini" phía trên.',
        chatgpt: 'chatgpt.com — dùng gói Plus/Pro đang trả.',
        claude: 'claude.ai — dùng gói Pro/Max đang trả.',
    };
    let providers = [];

    function who(a) {
        if (!a) return '';
        return [a.name, a.email ? '(' + a.email + ')' : ''].filter(Boolean).join(' ');
    }
    function statusHtml(p) {
        const a = p.account || {};
        if (who(a)) return `<span class="ai-ok"><i class="fa-solid fa-circle-check"></i> ${esc(who(a))}</span>`;
        if (a.logged_in === false) return '<span class="gm-warn">Chưa đăng nhập — bấm Đăng nhập</span>';
        if (p.has_profile) return '<span class="lz-muted">Đã mở đăng nhập — bấm "Đọc lại tài khoản" để xem email</span>';
        return '<span class="gm-warn">Chưa đăng nhập</span>';
    }
    function shortLabel(p) {
        const a = p.account || {};
        if (a.email) return a.email;
        if (a.name) return a.name;
        if (a.logged_in === false || !p.has_profile) return 'chưa đăng nhập';
        return '';
    }
    function modelHtml(p) {
        if (p.provider === 'gemini') return `<div class="lz-muted">Model: <b>${esc(p.model)}</b> (đổi ở thanh Model Gemini phía trên)</div>`;
        const isPreset = !p.model || p.presets.some((x) => x.toLowerCase() === p.model.toLowerCase());
        const opts = ['<option value="">Giữ model đang chọn trên web</option>']
            .concat(p.presets.map((x) => `<option value="${esc(x)}" ${x.toLowerCase() === (p.model || '').toLowerCase() ? 'selected' : ''}>${esc(x)}</option>`))
            .concat([`<option value="__custom__" ${isPreset ? '' : 'selected'}>Khác… (tự gõ tên)</option>`]).join('');
        return `<label class="ai-lab">Model</label>
            <div class="fl-inline"><select class="glass-input ai-model" data-p="${p.provider}">${opts}</select>
            <input type="text" class="glass-input ai-model-custom" data-p="${p.provider}" value="${isPreset ? '' : esc(p.model)}" placeholder="Gõ đúng tên trong menu, VD: GPT-6" style="${isPreset ? 'display:none' : ''}"></div>`;
    }
    function render() {
        $('aiCards').innerHTML = providers.map((p) => `
            <div class="ai-card" data-p="${p.provider}">
                <div class="ai-card-head"><i class="${ICON[p.provider]}"></i> <b>${esc(p.name)}</b></div>
                <div class="ai-status">${statusHtml(p)}</div>
                <div class="lz-muted ai-hint">${esc(HINT[p.provider])}</div>
                ${modelHtml(p)}
                <div class="ai-btns">
                    <button type="button" class="btn-glow fl-mini" data-act="login"><i class="fa-solid fa-right-to-bracket"></i> Đăng nhập</button>
                    <button type="button" class="btn-primary fl-mini" data-act="whoami"><i class="fa-solid fa-rotate"></i> Đọc lại tài khoản</button>
                    <button type="button" class="btn-primary fl-mini" data-act="check"><i class="fa-solid fa-stethoscope"></i> Kiểm tra</button>
                </div>
            </div>`).join('');
        // nhãn trong các ô "Chạy bằng"
        document.querySelectorAll('select.ai-select').forEach((sel) => {
            Array.from(sel.options).forEach((o) => {
                const p = providers.find((x) => x.provider === o.value);
                if (!p) return;
                const lab = shortLabel(p);
                o.textContent = p.name + (lab ? ' — ' + lab : '');
            });
        });
    }
    async function load() {
        try {
            const d = await (await fetch('/api/ai/accounts')).json();
            if (d.status === 'success') { providers = d.providers; render(); }
        } catch (e) { /* bỏ qua */ }
    }
    function showOut(title, text) {
        $('aiOutTitle').textContent = title;
        $('aiOut').textContent = text || '';
        $('aiOutBox').style.display = '';
        $('aiOutBox').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    $('aiOutClose').addEventListener('click', () => { $('aiOutBox').style.display = 'none'; });

    async function saveModel(provider, value) {
        const body = {}; body[provider + '_model'] = value;
        const d = await (await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json();
        if (d.status === 'success') { toast('Đã lưu model ' + provider + ': ' + (value || 'giữ theo web')); load(); } else toast(d.message || 'Lưu thất bại', true);
    }

    $('aiCards').addEventListener('change', (e) => {
        const sel = e.target.closest('select.ai-model'); if (!sel) return;
        const inp = sel.parentElement.querySelector('.ai-model-custom');
        if (sel.value === '__custom__') { inp.style.display = ''; inp.focus(); return; }
        inp.style.display = 'none';
        saveModel(sel.dataset.p, sel.value);
    });
    $('aiCards').addEventListener('keydown', (e) => {
        const inp = e.target.closest('.ai-model-custom'); if (!inp || e.key !== 'Enter') return;
        e.preventDefault(); saveModel(inp.dataset.p, inp.value.trim());
    });
    $('aiCards').addEventListener('focusout', (e) => {
        const inp = e.target.closest('.ai-model-custom'); if (!inp || !inp.value.trim()) return;
        const p = providers.find((x) => x.provider === inp.dataset.p);
        if (p && p.model !== inp.value.trim()) saveModel(inp.dataset.p, inp.value.trim());
    });

    $('aiCards').addEventListener('click', async (e) => {
        const b = e.target.closest('button[data-act]'); if (!b) return;
        const card = b.closest('.ai-card'); const prov = card.dataset.p;
        const p = providers.find((x) => x.provider === prov) || { name: prov };
        const old = b.innerHTML; b.disabled = true;
        try {
            if (b.dataset.act === 'login') {
                b.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang mở Chrome… (đăng nhập xong thì TẮT cửa sổ)';
                toast(`Cửa sổ Chrome ${p.name} đang mở. Đăng nhập xong thì TẮT HẲN cửa sổ đó.`);
                const d = await (await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ provider: prov, profileName: 'gemini_profile' }) })).json();
                toast(d.message || (d.status === 'success' ? 'Đã lưu' : 'Lỗi'), d.status !== 'success');
                if (prov === 'gemini') { await fetch('/api/gemini/account', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profileName: 'gemini_profile' }) }); }
            } else if (b.dataset.act === 'whoami') {
                b.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang đọc…';
                if (prov === 'gemini') {
                    await fetch('/api/gemini/account', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profileName: 'gemini_profile' }) });
                } else {
                    const d = await (await fetch(`/api/ai/${prov}/whoami`, { method: 'POST' })).json();
                    if (d.status !== 'success' && d.message) toast(d.message, true);
                }
            } else if (b.dataset.act === 'check') {
                b.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang kiểm tra (1-2 phút)…';
                const url = prov === 'gemini' ? '/api/gemini/check' : `/api/ai/${prov}/check`;
                const d = await (await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profileName: 'gemini_profile' }) })).json();
                showOut((d.status === 'success' ? '✅ ' : '⚠️ ') + 'Kiểm tra ' + p.name, (d.message ? d.message + '\n\n' : '') + (d.output || ''));
            }
        } catch (err) { toast('Lỗi kết nối tới máy chủ', true); }
        b.disabled = false; b.innerHTML = old;
        load();
    });

    // ô "Chạy bằng": nhớ lựa chọn trên máy này
    document.querySelectorAll('select.ai-select').forEach((sel) => {
        const key = 'ai_choice_' + sel.id;
        try { const v = localStorage.getItem(key); if (v && Array.from(sel.options).some((o) => o.value === v)) sel.value = v; } catch (e) { /* bỏ qua */ }
        sel.addEventListener('change', () => { try { localStorage.setItem(key, sel.value); } catch (e) { /* bỏ qua */ } });
    });
    document.querySelectorAll('.ai-goto').forEach((a) => a.addEventListener('click', (e) => {
        e.preventDefault();
        const t = document.querySelector('.tab-btn[data-tab="tab-ai"]'); if (t) t.click();
    }));
    const tab = document.querySelector('.tab-btn[data-tab="tab-ai"]');
    if (tab) tab.addEventListener('click', load);
    load();
})();
