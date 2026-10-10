/* Tab "Tái Sáng Tạo Đa Quốc Gia" + thanh chọn model Gemini.
   Tự chứa (không phụ thuộc script.js). */
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    if (!$('lzForm')) return;

    // ---------- tiện ích ----------
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
    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }
    async function jget(url) {
        const r = await fetch(url);
        return r.json();
    }
    function fmtDuration(sec) {
        sec = Math.max(0, Math.round(sec));
        const m = Math.floor(sec / 60), s = sec % 60;
        return m ? `${m} phút ${s} giây` : `${s} giây`;
    }
    function profileName() {
        const el = $('activeProfile');
        return el && el.value ? el.value : 'gemini_profile';
    }

    // ---------- trạng thái ----------
    let countries = [];            // [{code, flag, name_vi, language}]
    const selected = new Set();
    let files = [];                // File[]
    let jobId = null;
    let pollTimer = null;
    let shownFile = null;
    const countryByCode = () => Object.fromEntries(countries.map((c) => [c.code, c]));

    // ---------- model bar ----------
    async function loadLocales() {
        try {
            const d = await jget('/api/locales');
            if (d.status !== 'success') return;
            countries = d.data;
            renderCountries();
            const sel = $('lzStyle');
            const prev = sel.value;
            sel.innerHTML = '';
            d.rewrite_prompts.forEach((p) => {
                const o = document.createElement('option');
                o.value = p.id;
                o.textContent = p.name;
                o.dataset.mode = p.mode || 'rewrite';
                sel.appendChild(o);
            });
            if (prev) sel.value = prev;
            if (!sel.options.length) sel.innerHTML = '<option value="">(Chưa có mẫu — tạo ở tab Prompt › Viết Lại)</option>';
            updateStyleMode();
            if (document.activeElement !== $('gmModel')) $('gmModel').value = d.model || '';
            $('gmThinking').value = d.thinking == null ? 'Cao' : d.thinking;
        } catch (e) {
            console.error(e);
        }
    }

    function updateStyleMode() {
        const o = $('lzStyle').selectedOptions[0];
        $('lzStyleMode').textContent = o && o.dataset.mode === 'localize' ? 'Chế độ: dịch sát ý, chỉ chỉnh tự nhiên' : 'Chế độ: viết lại sáng tạo + bản địa hoá';
    }
    $('lzStyle').addEventListener('change', updateStyleMode);

    $('gmSave').addEventListener('click', async () => {
        const model = $('gmModel').value.trim();
        if (!model) return toast('Tên model không được để trống.', true);
        try {
            const r = await fetch('/api/settings', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model, thinking: $('gmThinking').value }),
            });
            const d = await r.json();
            if (d.status === 'success') toast(`Đã lưu: ${d.model}${d.thinking ? ' · suy luận ' + d.thinking : ''}`);
            else toast(d.message || 'Lưu thất bại', true);
        } catch (e) { toast('Lỗi kết nối tới máy chủ', true); }
    });

    $('gmCheck').addEventListener('click', async () => {
        const btn = $('gmCheck');
        const old = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang kiểm tra...';
        try {
            const r = await fetch('/api/gemini/check', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profileName: profileName() }),
            });
            const d = await r.json();
            openModal(d.status === 'success' ? '✅ Kiểm tra Gemini: OK' : '⚠️ Kiểm tra Gemini', (d.message ? d.message + '\n\n' : '') + (d.output || ''));
        } catch (e) {
            toast('Lỗi kết nối tới máy chủ', true);
        }
        btn.disabled = false;
        btn.innerHTML = old;
    });

    // ---------- hộp thoại ----------
    function openModal(title, text) {
        $('lzModalTitle').textContent = title;
        $('lzModalText').value = text;
        $('lzModal').style.display = 'flex';
    }
    $('lzModalClose').addEventListener('click', () => { $('lzModal').style.display = 'none'; });
    $('lzModal').addEventListener('click', (e) => { if (e.target === $('lzModal')) $('lzModal').style.display = 'none'; });

    // ---------- lưới quốc gia ----------
    function renderCountries() {
        const q = $('lzCountrySearch').value.trim().toLowerCase();
        const grid = $('lzCountries');
        grid.innerHTML = '';
        countries.forEach((c) => {
            const text = `${c.name_vi} ${c.language} ${c.code}`.toLowerCase();
            if (q && !text.includes(q)) return;
            const lab = document.createElement('label');
            lab.className = 'country-chip' + (selected.has(c.code) ? ' selected' : '');
            lab.innerHTML = `<input type="checkbox" ${selected.has(c.code) ? 'checked' : ''}> <span>${esc(c.flag)} ${esc(c.name_vi)}</span><small>${esc(c.language.replace(/\s*\(.*\)/, ''))}</small>`;
            lab.querySelector('input').addEventListener('change', (e) => {
                if (e.target.checked) selected.add(c.code); else selected.delete(c.code);
                lab.classList.toggle('selected', e.target.checked);
                updateCountryCount();
            });
            grid.appendChild(lab);
        });
        if (!grid.children.length) grid.innerHTML = '<div class="lz-muted">Không có nước nào khớp.</div>';
        updateCountryCount();
    }
    function updateCountryCount() { $('lzCountryCount').textContent = `Đã chọn ${selected.size}`; }
    $('lzCountrySearch').addEventListener('input', renderCountries);
    $('lzSelAll').addEventListener('click', () => {
        const q = $('lzCountrySearch').value.trim().toLowerCase();
        countries.forEach((c) => {
            if (c.code === 'SAME') return;
            if (!q || `${c.name_vi} ${c.language} ${c.code}`.toLowerCase().includes(q)) selected.add(c.code);
        });
        renderCountries();
    });
    $('lzSelNone').addEventListener('click', () => { selected.clear(); renderCountries(); });

    // ---------- nhập bài ----------
    $('lzRawText').addEventListener('input', () => {
        $('lzCharCount').textContent = `${$('lzRawText').value.length.toLocaleString('vi-VN')} ký tự`;
    });
    const dz = $('lzDropZone');
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); e.stopPropagation(); }));
    ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, () => dz.classList.add('dragover')));
    ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, () => dz.classList.remove('dragover')));
    dz.addEventListener('drop', (e) => addFiles(e.dataTransfer.files));
    dz.addEventListener('click', () => $('lzFileInput').click());
    $('lzFileInput').addEventListener('change', (e) => { addFiles(e.target.files); e.target.value = ''; });
    function addFiles(list) {
        Array.from(list).forEach((f) => {
            if (!/\.txt$/i.test(f.name)) return toast(`Bỏ qua ${f.name} (chỉ nhận .txt)`, true);
            if (!files.some((x) => x.name === f.name && x.size === f.size)) files.push(f);
        });
        renderFiles();
    }
    function renderFiles() {
        const box = $('lzFileList');
        box.innerHTML = '';
        files.forEach((f, i) => {
            const d = document.createElement('div');
            d.className = 'file-item';
            d.innerHTML = `<span><i class="fa-solid fa-file-lines"></i> ${esc(f.name)} <small>(${Math.round(f.size / 1024 * 10) / 10} KB)</small></span><i class="fa-solid fa-xmark remove-file" style="cursor:pointer" title="Bỏ file"></i>`;
            d.querySelector('.remove-file').addEventListener('click', () => { files.splice(i, 1); renderFiles(); });
            box.appendChild(d);
        });
    }

    // ---------- gửi form ----------
    function buildFormData() {
        const fd = new FormData();
        fd.append('rawText', $('lzRawText').value);
        fd.append('ytUrl', $('lzYt').value);
        files.forEach((f) => fd.append('files[]', f));
        fd.append('countries', JSON.stringify(Array.from(selected)));
        fd.append('promptId', $('lzStyle').value);
        fd.append('audience', $('lzAudience').value);
        fd.append('length', $('lzLength').value);
        fd.append('keywords', $('lzKeywords').value);
        fd.append('glossary', $('lzGlossary').value);
        fd.append('extra', $('lzExtra').value);
        fd.append('chunkSize', $('lzChunk').value);
        fd.append('customFilename', $('lzName').value.trim());
        fd.append('review', $('lzReview').checked ? '1' : '');
        fd.append('dryRun', $('lzDry').checked ? '1' : '');
        fd.append('profileName', profileName());
        return fd;
    }
    function validateInput() {
        if (!$('lzRawText').value.trim() && !files.length && !$('lzYt').value.trim()) { toast('Hãy dán bài, tải file .txt hoặc nhập link YouTube.', true); return false; }
        if (!selected.size) { toast('Hãy chọn ít nhất một quốc gia.', true); return false; }
        return true;
    }

    $('lzPreviewBtn').addEventListener('click', async () => {
        if (!validateInput()) return;
        try {
            const r = await fetch('/api/localize/preview', { method: 'POST', body: buildFormData() });
            const d = await r.json();
            if (d.status !== 'success') return toast(d.message || 'Không dựng được prompt', true);
            openModal(`Prompt gửi Gemini — bài "${d.article}", nước ${d.country} (đoạn 1/${d.chunks})`, d.prompt);
        } catch (e) { toast('Lỗi kết nối tới máy chủ', true); }
    });

    $('lzForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!validateInput()) return;
        const btn = $('lzStartBtn');
        btn.disabled = true;
        try {
            const r = await fetch('/api/localize', { method: 'POST', body: buildFormData() });
            const d = await r.json();
            if (r.status === 409 && d.job_id) { toast(d.message, true); attach(d.job_id); }
            else if (d.status !== 'success') toast(d.message || 'Không bắt đầu được', true);
            else { toast(`Đã bắt đầu: ${d.units} mục (bài × nước).`); attach(d.job_id); }
        } catch (err) { toast('Lỗi kết nối tới máy chủ', true); }
        btn.disabled = false;
    });

    // ---------- theo dõi job ----------
    const STATE_LABEL = { queued: 'Đang chờ', running: 'Đang chạy', done: 'Hoàn tất', partial: 'Xong một phần', error: 'Lỗi', cancelled: 'Đã huỷ' };

    function attach(id) {
        jobId = id;
        shownFile = null;
        $('lzPreviewBox').style.display = 'none';
        $('lzEmpty').style.display = 'none';
        $('lzJob').style.display = 'block';
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
        } catch (e) { /* bỏ qua lỗi mạng thoáng qua */ }
    }

    function render(job) {
        const cmap = countryByCode();
        const results = job.results || {};
        const keys = Object.keys(results);
        const total = keys.length || 1;
        const done = keys.filter((k) => results[k].status === 'done').length;
        const errs = keys.filter((k) => results[k].status === 'error').length;
        // tiến độ mượt: tính cả đoạn đang chạy dở
        let partial = 0;
        keys.forEach((k) => { const r = results[k]; if (r.status === 'running' && r.chunks_total) partial += (r.chunks_done || 0) / r.chunks_total; });
        $('lzBar').style.width = `${Math.min(100, ((done + partial) / total) * 100)}%`;

        const badge = $('lzState');
        badge.className = 'lz-badge ' + job.state;
        badge.textContent = STATE_LABEL[job.state] || job.state;
        const end = job.finished_at || Date.now() / 1000;
        const elapsed = job.started_at ? ` · ${fmtDuration(end - job.started_at)}` : '';
        $('lzSummary').textContent = `${done}/${keys.length} mục xong${errs ? ` · ${errs} lỗi` : ''}${job.dry_run ? ' · CHẠY THỬ' : ''} · ${job.model || ''}${elapsed}`;

        const eb = $('lzError');
        if (job.error) { eb.style.display = 'block'; eb.textContent = job.error; } else eb.style.display = 'none';

        // nhóm theo bài
        const groups = $('lzGroups');
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

        // nút
        const running = job.state === 'running' || job.state === 'queued';
        $('lzCancel').style.display = running ? 'inline-flex' : 'none';
        $('lzResume').style.display = !running && done < keys.length ? 'inline-flex' : 'none';
        const zip = $('lzZip');
        if (job.zip) { zip.style.display = 'inline-flex'; zip.href = `/api/download/${encodeURIComponent(job.zip)}`; }
        else zip.style.display = 'none';

        const log = $('lzLog');
        const atBottom = log.scrollHeight - log.clientHeight <= log.scrollTop + 12;
        log.textContent = job.log_tail || '';
        if (atBottom) log.scrollTop = log.scrollHeight;
    }

    async function showResult(file, title) {
        try {
            const d = await jget(`/api/localize/${jobId}/text?f=${encodeURIComponent(file)}`);
            if (d.status !== 'success') return toast(d.message || 'Không đọc được file', true);
            shownFile = file;
            $('lzPreviewBox').style.display = 'block';
            $('lzPreviewTitle').textContent = title;
            $('lzPreviewText').value = d.text;
            const dl = $('lzPreviewDl');
            dl.href = `/api/localize/${jobId}/file?f=${encodeURIComponent(file)}`;
            dl.setAttribute('download', file.split('/').pop());
            poll();
            $('lzPreviewBox').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } catch (e) { toast('Lỗi kết nối tới máy chủ', true); }
    }

    $('lzCancel').addEventListener('click', async () => {
        if (!jobId) return;
        const d = await (await fetch(`/api/localize/${jobId}/cancel`, { method: 'POST' })).json();
        toast(d.message || 'Đã gửi lệnh huỷ', d.status === 'error');
    });
    $('lzResume').addEventListener('click', async () => {
        if (!jobId) return;
        const r = await fetch(`/api/localize/${jobId}/resume`, { method: 'POST' });
        const d = await r.json();
        if (d.status === 'success') { toast('Đã chạy tiếp phần còn thiếu.'); attach(jobId); }
        else toast(d.message || 'Không chạy tiếp được', true);
    });

    // ---------- khởi động ----------
    document.querySelectorAll('.tab-btn').forEach((b) => {
        if (b.getAttribute('data-tab') === 'tab-localize') b.addEventListener('click', loadLocales);
    });
    loadLocales();
    // Nối lại job gần nhất sau khi tải lại trang
    jget('/api/localize/latest').then((d) => { if (d && d.job_id) attach(d.job_id); }).catch(() => {});
})();
