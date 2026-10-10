/* Tab "NotebookLM": Thư mục -> Dạng bài -> dán bài, chạy nhiều nước. Tự chứa. */
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    if (!$('nbForm')) return;

    let toastTimer;
    function toast(msg, isError) {
        const t = $('toast');
        if (!t) return;
        t.textContent = msg;
        t.style.background = isError ? 'rgba(239, 68, 68, 0.9)' : 'rgba(16, 185, 129, 0.9)';
        t.classList.add('show');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => t.classList.remove('show'), 3500);
    }
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const jget = async (u) => (await fetch(u)).json();
    async function jpost(u, body) {
        const r = await fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
        return r.json();
    }
    function fmtDuration(sec) {
        sec = Math.max(0, Math.round(sec));
        const m = Math.floor(sec / 60), s = sec % 60;
        return m ? `${m} phút ${s} giây` : `${s} giây`;
    }
    const profileName = () => { const el = $('activeProfile'); return el && el.value ? el.value : 'gemini_profile'; };

    let folders = [];
    let countries = [];
    const selected = new Set();
    let jobId = null, pollTimer = null, shownFile = null;
    let editTypeId = null;

    // ---------- thư mục / dạng bài ----------
    const curFolder = () => folders.find((f) => f.id === $('nbFolder').value) || null;
    const curType = () => { const f = curFolder(); return f ? f.types.find((t) => t.id === $('nbType').value) || null : null; };

    async function loadTree(keepFolder, keepType) {
        const d = await jget('/api/nb/tree');
        folders = (d.data && d.data.folders) || [];
        const fsel = $('nbFolder');
        fsel.innerHTML = folders.length ? '' : '<option value="">(Chưa có thư mục — bấm "Thư mục mới")</option>';
        folders.forEach((f) => { const o = document.createElement('option'); o.value = f.id; o.textContent = `${f.name} (${f.types.length})`; fsel.appendChild(o); });
        if (keepFolder && folders.some((f) => f.id === keepFolder)) fsel.value = keepFolder;
        renderTypes(keepType);
    }
    function renderTypes(keepType) {
        const tsel = $('nbType');
        const f = curFolder();
        tsel.innerHTML = '';
        if (!f) tsel.innerHTML = '<option value="">—</option>';
        else if (!f.types.length) tsel.innerHTML = '<option value="">(Chưa có dạng bài — bấm "Dạng bài mới")</option>';
        else f.types.forEach((t) => { const o = document.createElement('option'); o.value = t.id; o.textContent = t.name; tsel.appendChild(o); });
        if (keepType && f && f.types.some((t) => t.id === keepType)) tsel.value = keepType;
        updateTypeInfo();
    }
    function updateTypeInfo() {
        const t = curType();
        if (!t) { $('nbTypeInfo').textContent = ''; return; }
        const nsrc = (t.fixed_text || '').split(/^\s*={5,}\s*$/m).filter((x) => x.trim()).length;
        const md = t.mode === 'localize' ? 'giữ sát ý gốc' : t.mode === 'analyze' ? 'phân tích' : 'sáng tạo';
        $('nbTypeInfo').textContent = `${md} · ${nsrc} nguồn cố định${t.review ? ' · tự soát' : ''}`;
    }
    $('nbFolder').addEventListener('change', () => renderTypes());
    $('nbType').addEventListener('change', updateTypeInfo);

    $('nbFolderNew').addEventListener('click', async () => {
        const name = (prompt('Tên thư mục mới:') || '').trim();
        if (!name) return;
        const d = await jpost('/api/nb/folder', { name });
        if (d.status !== 'success') return toast(d.message || 'Lỗi', true);
        loadTree(d.folder.id);
    });
    $('nbFolderRename').addEventListener('click', async () => {
        const f = curFolder();
        if (!f) return;
        const name = (prompt('Tên mới của thư mục:', f.name) || '').trim();
        if (!name) return;
        const d = await jpost('/api/nb/folder', { id: f.id, name });
        if (d.status !== 'success') return toast(d.message || 'Lỗi', true);
        loadTree(f.id, $('nbType').value);
    });
    $('nbFolderDel').addEventListener('click', async () => {
        const f = curFolder();
        if (!f || !confirm(`Xoá thư mục "${f.name}" và các dạng bài trong đó khỏi Tool?\n(Không xoá gì trong NotebookLM.)`)) return;
        await jpost(`/api/nb/folder/${f.id}/delete`);
        loadTree();
    });

    function openTypeModal(t) {
        editTypeId = t ? t.id : null;
        $('nbTypeModalTitle').textContent = t ? 'Sửa dạng bài' : 'Dạng bài mới';
        $('nbTName').value = t ? t.name : '';
        $('nbTMode').value = t ? t.mode : 'rewrite';
        $('nbTPrompt').value = t ? t.prompt : '';
        $('nbTFixed').value = t ? t.fixed_text : '';
        $('nbTLength').value = t ? t.length : 'same';
        $('nbTChunk').value = t ? t.chunk_size : 8000;
        $('nbTAudience').value = t ? t.audience : '';
        $('nbTKeywords').value = t ? t.keywords : '';
        $('nbTGlossary').value = t ? t.glossary : '';
        $('nbTExtra').value = t ? t.extra : '';
        $('nbTReview').checked = !!(t && t.review);
        $('nbTypeModal').style.display = 'flex';
    }
    $('nbTypeNew').addEventListener('click', () => { if (!curFolder()) return toast('Hãy tạo thư mục trước.', true); openTypeModal(null); });
    $('nbTypeEdit').addEventListener('click', () => { const t = curType(); if (t) openTypeModal(t); else toast('Chưa chọn dạng bài.', true); });
    $('nbTypeModalClose').addEventListener('click', () => { $('nbTypeModal').style.display = 'none'; });
    $('nbTypeDel').addEventListener('click', async () => {
        const t = curType();
        if (!t || !confirm(`Xoá dạng bài "${t.name}" khỏi Tool?\n(Không xoá gì trong NotebookLM.)`)) return;
        await jpost(`/api/nb/type/${t.id}/delete`);
        loadTree($('nbFolder').value);
    });
    $('nbTSave').addEventListener('click', async () => {
        const f = curFolder();
        if (!f) return;
        const d = await jpost('/api/nb/type', {
            folder_id: f.id, id: editTypeId, name: $('nbTName').value, mode: $('nbTMode').value, prompt: $('nbTPrompt').value,
            fixed_text: $('nbTFixed').value, length: $('nbTLength').value, chunk_size: $('nbTChunk').value,
            audience: $('nbTAudience').value, keywords: $('nbTKeywords').value, glossary: $('nbTGlossary').value,
            extra: $('nbTExtra').value, review: $('nbTReview').checked,
        });
        if (d.status !== 'success') return toast(d.message || 'Không lưu được', true);
        $('nbTypeModal').style.display = 'none';
        toast('Đã lưu dạng bài.');
        loadTree(f.id, d.type.id);
    });

    // ---------- quốc gia ----------
    async function loadCountries() {
        try {
            const d = await jget('/api/locales');
            if (d.status === 'success') { countries = d.data; renderCountries(); }
        } catch (e) { console.error(e); }
    }
    function renderCountries() {
        const q = $('nbCountrySearch').value.trim().toLowerCase();
        const grid = $('nbCountries');
        grid.innerHTML = '';
        countries.forEach((c) => {
            if (q && !`${c.name_vi} ${c.language} ${c.code}`.toLowerCase().includes(q)) return;
            const lab = document.createElement('label');
            lab.className = 'country-chip' + (selected.has(c.code) ? ' selected' : '');
            lab.innerHTML = `<input type="checkbox" ${selected.has(c.code) ? 'checked' : ''}> <span>${esc(c.flag)} ${esc(c.name_vi)}</span><small>${esc(c.language.replace(/\s*\(.*\)/, ''))}</small>`;
            lab.querySelector('input').addEventListener('change', (e) => {
                if (e.target.checked) selected.add(c.code); else selected.delete(c.code);
                lab.classList.toggle('selected', e.target.checked);
                $('nbCountryCount').textContent = `Đã chọn ${selected.size}`;
            });
            grid.appendChild(lab);
        });
        if (!grid.children.length) grid.innerHTML = '<div class="lz-muted">Không có nước nào khớp.</div>';
        $('nbCountryCount').textContent = `Đã chọn ${selected.size}`;
    }
    $('nbCountrySearch').addEventListener('input', renderCountries);
    $('nbSelAll').addEventListener('click', () => {
        const q = $('nbCountrySearch').value.trim().toLowerCase();
        countries.forEach((c) => { if (c.code !== 'SAME' && (!q || `${c.name_vi} ${c.language} ${c.code}`.toLowerCase().includes(q))) selected.add(c.code); });
        renderCountries();
    });
    $('nbSelNone').addEventListener('click', () => { selected.clear(); renderCountries(); });
    $('nbRaw').addEventListener('input', () => { $('nbCount').textContent = `${$('nbRaw').value.length.toLocaleString('vi-VN')} ký tự`; });

    // ---------- chạy ----------
    $('nbForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const t = curType();
        if (!t) return toast('Hãy chọn một dạng bài.', true);
        const files = Array.from($('nbFiles').files);
        if (!$('nbRaw').value.trim() && !files.length) return toast('Hãy dán bài hoặc chọn file .txt.', true);
        if (!selected.size) return toast('Hãy chọn ít nhất một quốc gia.', true);
        const fd = new FormData();
        fd.append('typeId', t.id);
        fd.append('rawText', $('nbRaw').value);
        fd.append('countries', JSON.stringify(Array.from(selected)));
        fd.append('customFilename', $('nbName').value);
        fd.append('perLine', $('nbPerLine').checked ? '1' : '');
        fd.append('dryRun', $('nbDry').checked ? '1' : '');
        fd.append('profileName', profileName());
        files.forEach((f) => fd.append('files[]', f));
        const btn = $('nbStart');
        btn.disabled = true;
        try {
            const d = await (await fetch('/api/nb/run', { method: 'POST', body: fd })).json();
            if (d.status === 'success') { toast(`Đã bắt đầu ${d.units} mục.`); attach(d.job_id); }
            else { toast(d.message || 'Không bắt đầu được', true); if (d.job_id) attach(d.job_id); }
        } catch (err) { toast('Lỗi kết nối tới máy chủ', true); }
        btn.disabled = false;
    });

    // ---------- theo dõi job (dùng API /api/localize/<id> chung) ----------
    const STATE_LABEL = { queued: 'Đang chờ', running: 'Đang chạy', done: 'Hoàn tất', partial: 'Xong một phần', error: 'Lỗi', cancelled: 'Đã huỷ' };
    function attach(id) {
        jobId = id; shownFile = null;
        $('nbPreviewBox').style.display = 'none';
        $('nbEmpty').style.display = 'none';
        $('nbJob').style.display = 'block';
        poll();
        clearInterval(pollTimer);
        pollTimer = setInterval(poll, 2000);
    }
    async function poll() {
        if (!jobId) return;
        try {
            const d = await jget(`/api/localize/${jobId}`);
            if (d.status !== 'success') return;
            render(d.job);
            if (d.job.state !== 'running' && d.job.state !== 'queued') { clearInterval(pollTimer); pollTimer = null; }
        } catch (e) { /* lỗi mạng thoáng qua */ }
    }
    function render(job) {
        const cmap = Object.fromEntries(countries.map((c) => [c.code, c]));
        const results = job.results || {};
        const keys = Object.keys(results);
        const total = keys.length || 1;
        const done = keys.filter((k) => results[k].status === 'done').length;
        const errs = keys.filter((k) => results[k].status === 'error').length;
        let partial = 0;
        keys.forEach((k) => { const r = results[k]; if (r.status === 'running' && r.chunks_total) partial += (r.chunks_done || 0) / r.chunks_total; });
        $('nbBar').style.width = `${Math.min(100, ((done + partial) / total) * 100)}%`;
        const badge = $('nbState');
        badge.className = 'lz-badge ' + job.state;
        badge.textContent = STATE_LABEL[job.state] || job.state;
        const end = job.finished_at || Date.now() / 1000;
        const elapsed = job.started_at ? ` · ${fmtDuration(end - job.started_at)}` : '';
        $('nbSummary').textContent = `${done}/${keys.length} mục xong${errs ? ` · ${errs} lỗi` : ''}${job.dry_run ? ' · CHẠY THỬ' : ''}${elapsed}`;
        const eb = $('nbError');
        if (job.error) { eb.style.display = 'block'; eb.textContent = job.error; } else eb.style.display = 'none';

        const groups = $('nbGroups');
        groups.innerHTML = '';
        (job.articles || []).forEach((a) => {
            const g = document.createElement('div');
            g.className = 'lz-group';
            g.innerHTML = `<div class="lz-group-title"><i class="fa-solid fa-file-lines"></i> ${esc(a.name)}</div><div class="lz-chips"></div>`;
            const chips = g.querySelector('.lz-chips');
            (job.countries || []).forEach((code) => {
                const r = results[`${a.id}:${code}`] || { status: 'pending' };
                const c = cmap[code] || { flag: '', name_vi: code };
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'res-chip ' + r.status + (r.file && r.file === shownFile ? ' active' : '');
                let tail = '⏳';
                if (r.status === 'done') tail = '✅';
                else if (r.status === 'running') tail = `🔄 ${r.chunks_done || 0}/${r.chunks_total || '?'}`;
                else if (r.status === 'error') tail = '❌';
                b.textContent = `${c.flag} ${c.name_vi} ${tail}`;
                if (r.status === 'error') b.title = r.error || 'Lỗi';
                if (r.status === 'done') {
                    b.title = `${(r.chars || 0).toLocaleString('vi-VN')} ký tự — bấm để xem`;
                    b.addEventListener('click', () => showResult(r.file, `${a.name} — ${c.name_vi}`));
                }
                chips.appendChild(b);
            });
            groups.appendChild(g);
        });
        const running = job.state === 'running' || job.state === 'queued';
        $('nbCancel').style.display = running ? 'inline-flex' : 'none';
        $('nbResume').style.display = !running && done < keys.length ? 'inline-flex' : 'none';
        const zip = $('nbZip');
        if (job.zip) { zip.style.display = 'inline-flex'; zip.href = `/api/download/${encodeURIComponent(job.zip)}`; } else zip.style.display = 'none';
        const log = $('nbLog');
        const atBottom = log.scrollHeight - log.clientHeight <= log.scrollTop + 12;
        log.textContent = job.log_tail || '';
        if (atBottom) log.scrollTop = log.scrollHeight;
    }
    async function showResult(file, title) {
        try {
            const d = await jget(`/api/localize/${jobId}/text?f=${encodeURIComponent(file)}`);
            if (d.status !== 'success') return toast(d.message || 'Không đọc được file', true);
            shownFile = file;
            $('nbPreviewBox').style.display = 'block';
            $('nbPreviewTitle').textContent = title;
            $('nbPreviewText').value = d.text;
            const dl = $('nbPreviewDl');
            dl.href = `/api/localize/${jobId}/file?f=${encodeURIComponent(file)}`;
            dl.setAttribute('download', file.split('/').pop());
            poll();
            $('nbPreviewBox').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } catch (e) { toast('Lỗi kết nối tới máy chủ', true); }
    }
    $('nbCancel').addEventListener('click', async () => {
        if (!jobId) return;
        const d = await jpost(`/api/localize/${jobId}/cancel`);
        toast(d.message || 'Đã gửi lệnh huỷ', d.status === 'error');
    });
    $('nbResume').addEventListener('click', async () => {
        if (!jobId) return;
        const d = await jpost(`/api/localize/${jobId}/resume`);
        if (d.status === 'success') { toast('Đã chạy tiếp phần còn thiếu.'); attach(jobId); } else toast(d.message || 'Không chạy tiếp được', true);
    });

    document.querySelectorAll('.tab-btn').forEach((b) => {
        if (b.getAttribute('data-tab') === 'tab-notebook') b.addEventListener('click', () => { loadTree($('nbFolder').value, $('nbType').value); if (!countries.length) loadCountries(); });
    });
    loadTree();
    loadCountries();
})();
