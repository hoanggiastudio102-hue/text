/* Tab "YouTube → Text": dán link YouTube, NotebookLM biên tập thành văn bản chuẩn. Tự chứa. */
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    if (!$('ytForm')) return;

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
    const jpost = async (u) => (await fetch(u, { method: 'POST' })).json();
    const profileName = () => { const el = $('activeProfile'); return el && el.value ? el.value : 'gemini_profile'; };
    function fmtDuration(sec) {
        sec = Math.max(0, Math.round(sec));
        const m = Math.floor(sec / 60), s = sec % 60;
        return m ? `${m} phút ${s} giây` : `${s} giây`;
    }
    const YT_RE = /https?:\/\/(?:www\.|m\.)?(?:youtube\.com|youtu\.be)\/[^\s<>"']+/g;
    function countLinks() {
        const ids = new Set();
        ($('ytLinks').value.match(YT_RE) || []).forEach((u) => {
            const m = /(?:v=|youtu\.be\/|\/shorts\/|\/embed\/|\/live\/|\/v\/)([0-9A-Za-z_-]{11})/.exec(u);
            if (m) ids.add(m[1]);
        });
        $('ytCount').textContent = `${ids.size} link`;
        return ids.size;
    }
    $('ytLinks').addEventListener('input', countLinks);

    async function loadLangs() {
        try {
            const d = await jget('/api/locales');
            if (d.status !== 'success') return;
            const sel = $('ytLang');
            const keep = sel.value;
            sel.innerHTML = '<option value="SAME">Giữ nguyên ngôn ngữ của video</option>';
            d.data.forEach((c) => {
                if (c.code === 'SAME') return;
                const o = document.createElement('option');
                o.value = c.code;
                o.textContent = `Viết bằng ngôn ngữ ${c.flag} ${c.name_vi} (${c.language})`;
                sel.appendChild(o);
            });
            sel.value = keep || 'SAME';
        } catch (e) { /* bỏ qua */ }
    }

    // ---------- chạy ----------
    let jobId = null, pollTimer = null, shownFile = null;
    $('ytForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!countLinks()) return toast('Hãy dán ít nhất một link YouTube.', true);
        const fd = new FormData();
        fd.append('links', $('ytLinks').value);
        fd.append('style', $('ytStyle').value);
        fd.append('lang', $('ytLang').value);
        fd.append('extra', $('ytExtra').value);
        fd.append('customFilename', $('ytName').value);
        fd.append('review', $('ytReview').checked ? '1' : '');
        fd.append('header', $('ytHeader').checked ? '1' : '');
        fd.append('dryRun', $('ytDry').checked ? '1' : '');
        fd.append('profileName', profileName());
        const btn = $('ytStart');
        btn.disabled = true;
        try {
            const d = await (await fetch('/api/yt/run', { method: 'POST', body: fd })).json();
            if (d.status === 'success') { toast(`Đã bắt đầu ${d.units} video.`); attach(d.job_id); }
            else { toast(d.message || 'Không bắt đầu được', true); if (d.job_id) attach(d.job_id); }
        } catch (err) { toast('Lỗi kết nối tới máy chủ', true); }
        btn.disabled = false;
    });

    // ---------- tiến độ ----------
    const STATE_LABEL = { queued: 'Đang chờ', running: 'Đang chạy', done: 'Hoàn tất', partial: 'Xong một phần', error: 'Lỗi', cancelled: 'Đã huỷ' };
    function attach(id) {
        jobId = id; shownFile = null;
        $('ytPreviewBox').style.display = 'none';
        $('ytEmpty').style.display = 'none';
        $('ytJob').style.display = 'block';
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
        const results = job.results || {};
        const keys = Object.keys(results);
        const done = keys.filter((k) => results[k].status === 'done').length;
        const errs = keys.filter((k) => results[k].status === 'error').length;
        $('ytBar').style.width = `${Math.min(100, (done / (keys.length || 1)) * 100)}%`;
        const badge = $('ytState');
        badge.className = 'lz-badge ' + job.state;
        badge.textContent = STATE_LABEL[job.state] || job.state;
        const end = job.finished_at || Date.now() / 1000;
        $('ytSummary').textContent = `${done}/${keys.length} video xong${errs ? ` · ${errs} lỗi` : ''}${job.dry_run ? ' · CHẠY THỬ' : ''}${job.started_at ? ' · ' + fmtDuration(end - job.started_at) : ''}`;
        const eb = $('ytError');
        if (job.error) { eb.style.display = 'block'; eb.textContent = job.error; } else eb.style.display = 'none';
        const box = $('ytGroups');
        box.innerHTML = '';
        const code = (job.countries || ['SAME'])[0];
        (job.articles || []).forEach((a) => {
            const r = results[`${a.id}:${code}`] || { status: 'pending' };
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'res-chip ' + r.status + (r.file && r.file === shownFile ? ' active' : '');
            let tail = '⏳';
            if (r.status === 'done') tail = '✅';
            else if (r.status === 'running') tail = r.chunks_total > 1 ? `🔄 ${r.chunks_done || 0}/${r.chunks_total}` : '🔄';
            else if (r.status === 'error') tail = '❌';
            b.innerHTML = `${esc(a.name)} ${tail}`;
            b.title = r.status === 'error' ? (r.error || 'Lỗi') : (a.url || '');
            if (r.status === 'done') {
                b.title = `${(r.chars || 0).toLocaleString('vi-VN')} ký tự — bấm để xem`;
                b.addEventListener('click', () => showResult(r.file, a.name));
            }
            box.appendChild(b);
        });
        const running = job.state === 'running' || job.state === 'queued';
        $('ytCancel').style.display = running ? 'inline-flex' : 'none';
        $('ytResume').style.display = !running && done < keys.length ? 'inline-flex' : 'none';
        const zip = $('ytZip');
        if (job.zip) { zip.style.display = 'inline-flex'; zip.href = `/api/download/${encodeURIComponent(job.zip)}`; } else zip.style.display = 'none';
        const log = $('ytLog');
        const atBottom = log.scrollHeight - log.clientHeight <= log.scrollTop + 12;
        log.textContent = job.log_tail || '';
        if (atBottom) log.scrollTop = log.scrollHeight;
    }
    async function showResult(file, title) {
        try {
            const d = await jget(`/api/localize/${jobId}/text?f=${encodeURIComponent(file)}`);
            if (d.status !== 'success') return toast(d.message || 'Không đọc được file', true);
            shownFile = file;
            $('ytPreviewBox').style.display = 'block';
            $('ytPreviewTitle').textContent = title;
            $('ytPreviewText').value = d.text;
            const dl = $('ytPreviewDl');
            dl.href = `/api/localize/${jobId}/file?f=${encodeURIComponent(file)}`;
            dl.setAttribute('download', file.split('/').pop());
            poll();
            $('ytPreviewBox').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } catch (e) { toast('Lỗi kết nối tới máy chủ', true); }
    }
    $('ytCancel').addEventListener('click', async () => {
        if (!jobId) return;
        const d = await jpost(`/api/localize/${jobId}/cancel`);
        toast(d.message || 'Đã gửi lệnh huỷ', d.status === 'error');
    });
    $('ytResume').addEventListener('click', async () => {
        if (!jobId) return;
        const d = await jpost(`/api/localize/${jobId}/resume`);
        if (d.status === 'success') { toast('Đã chạy tiếp phần còn thiếu.'); attach(jobId); } else toast(d.message || 'Không chạy tiếp được', true);
    });

    document.querySelectorAll('.tab-btn').forEach((b) => {
        if (b.getAttribute('data-tab') === 'tab-yt') b.addEventListener('click', () => { if ($('ytLang').options.length < 2) loadLangs(); });
    });
    loadLangs();
})();
