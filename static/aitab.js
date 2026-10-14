/* Tab riêng "ChatGPT" và "Claude": hàng đợi nhiều mục + câu lệnh mẫu + (tuỳ chọn) nhiều quốc gia. Dùng chung 1 file cho cả 2 tab. */
(function () {
    'use strict';
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const jget = async (u) => (await fetch(u)).json();
    const jpost = async (u, body) => (await fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })).json();
    let tt;
    const toast = (m, err) => { const t = document.getElementById('toast'); if (!t) return; t.textContent = m;
        t.style.background = err ? 'rgba(239,68,68,0.9)' : 'rgba(16,185,129,0.9)'; t.classList.add('show');
        clearTimeout(tt); tt = setTimeout(() => t.classList.remove('show'), 3800); };
    const fmtDuration = (sec) => { sec = Math.max(0, Math.round(sec)); const m = Math.floor(sec / 60), s = sec % 60; return m ? `${m} phút ${s} giây` : `${s} giây`; };
    const STATE_LABEL = { queued: 'Đang chờ', running: 'Đang chạy', done: 'Hoàn tất', partial: 'Xong một phần', error: 'Lỗi', cancelled: 'Đã huỷ' };
    let templates = [], countries = [];
    const instances = [];

    async function loadTemplates() {
        try { const d = await jget('/api/aichat/templates'); if (d.status === 'success') templates = d.templates; } catch (e) { /* bỏ qua */ }
        instances.forEach((x) => x.renderTemplates());
    }
    async function loadCountries() {
        try { const d = await jget('/api/locales'); if (d.status === 'success') countries = d.data.filter((c) => c.code !== 'SAME'); } catch (e) { /* bỏ qua */ }
        instances.forEach((x) => { x.renderCountries(); x.refresh(); });
    }

    function build(root) {
        const ai = root.dataset.ai, P = ai === 'chatgpt' ? 'cg' : 'cl', NAME = ai === 'chatgpt' ? 'ChatGPT' : 'Claude';
        const $ = (id) => document.getElementById(P + id);
        root.innerHTML = `
        <div class="card input-section">
            <h2><i class="${ai === 'chatgpt' ? 'fa-solid fa-comment-dots' : 'fa-solid fa-asterisk'}"></i> ${NAME} — chạy hàng loạt</h2>
            <div class="ai-topbar"><span id="${P}Acc" class="lz-muted">Đang đọc tài khoản…</span>
                <span id="${P}Model" class="lz-muted"></span>
                <a href="#" class="ai-goto" style="font-size:12px;">đăng nhập / đổi model →</a></div>
            <p class="lz-hint">Dán nhiều mục (bài gốc, chủ đề, đoạn phụ đề…) — mỗi mục ${NAME} làm trong 1 chat mới với câu lệnh mẫu bên dưới. Bài dài tự chia phần, câu trả lời bị cụt tự nhắn "Tiếp tục". Nghỉ ngẫu nhiên giữa các mục để tránh bị giới hạn. Mỗi mục ra 1 file .txt.</p>
            <form id="${P}Form">
                <div class="form-group">
                    <label><span><i class="fa-solid fa-terminal"></i> Câu lệnh mẫu</span><span class="lz-muted" style="font-size:12px;">biến: {NOI_DUNG} {TEN} {QUOC_GIA} {NGON_NGU}</span></label>
                    <div class="fl-inline"><select id="${P}Tpl" class="glass-input"></select>
                        <button type="button" class="btn-primary" id="${P}TplSave" title="Lưu câu lệnh đang gõ thành mẫu"><i class="fa-solid fa-floppy-disk"></i> Lưu mẫu</button>
                        <button type="button" class="btn-primary" id="${P}TplDel" title="Xoá mẫu đang chọn"><i class="fa-solid fa-trash"></i></button></div>
                    <textarea id="${P}Prompt" class="glass-input" rows="5" placeholder="VD: Viết lại bài dưới đây bằng {NGON_NGU} cho người đọc {QUOC_GIA}, giữ toàn bộ ý…&#10;&#10;{NOI_DUNG}"></textarea>
                </div>
                <div class="form-group">
                    <label><span><i class="fa-solid fa-list-ol"></i> Danh sách mục</span><span id="${P}Count" class="char-count">0 mục</span></label>
                    <select id="${P}Split" class="glass-input" style="margin-bottom:6px;">
                        <option value="block">Ngăn các mục bằng một dòng --- (bài dài nhiều đoạn)</option>
                        <option value="line">Mỗi dòng là 1 mục (chủ đề, tiêu đề, từ khoá…)</option>
                        <option value="all">Cả ô là 1 mục</option>
                    </select>
                    <textarea id="${P}Items" class="glass-input" rows="9" placeholder="Bài 1 …&#10;---&#10;Bài 2 …"></textarea>
                    <input type="file" id="${P}Files" multiple accept=".txt,.md,.csv,.srt" class="glass-input" style="margin-top:6px;">
                    <div class="lz-muted" style="font-size:12px;">Hoặc chọn nhiều file .txt — mỗi file là 1 mục, tên file thành tên kết quả.</div>
                </div>
                <div class="form-group">
                    <label><span><i class="fa-solid fa-earth-asia"></i> Quốc gia (tuỳ chọn — để trống = không đổi ngôn ngữ)</span><span id="${P}CCount" class="char-count">Đã chọn 0</span></label>
                    <div class="lz-actions-row"><input type="text" id="${P}CSearch" class="glass-input" placeholder="Tìm nước...">
                        <button type="button" class="btn-primary" id="${P}CNone">Bỏ chọn</button></div>
                    <div id="${P}Countries" class="country-grid ai-cgrid"><div class="lz-muted">Đang tải…</div></div>
                </div>
                <div class="lz-two-col">
                    <div class="form-group"><label><span>Cách chat</span></label>
                        <select id="${P}ChatMode" class="glass-input"><option value="new">Mỗi mục 1 chat mới (khuyên dùng)</option><option value="same">Nối tiếp trong cùng 1 chat (giữ mạch giữa các mục)</option></select></div>
                    <div class="form-group"><label><span>Bài dài chia phần</span></label>
                        <select id="${P}Chunk" class="glass-input"><option value="12000">~12.000 ký tự / phần</option><option value="25000">~25.000 ký tự / phần</option><option value="6000">~6.000 ký tự / phần (bám sát nhất)</option></select></div>
                </div>
                <div class="lz-two-col">
                    <div class="form-group"><label><span>Nghỉ giữa các mục (giây)</span></label>
                        <div class="fl-inline"><input type="number" id="${P}DMin" class="glass-input" value="5" min="0" max="600"><input type="number" id="${P}DMax" class="glass-input" value="15" min="0" max="900"></div></div>
                    <div class="form-group"><label><span>Tên file (tuỳ chọn)</span></label><input type="text" id="${P}Name" class="glass-input" placeholder="VD: Kenh09"></div>
                </div>
                <div class="form-group"><label><span>Yêu cầu thêm (tuỳ chọn)</span></label><input type="text" id="${P}Extra" class="glass-input" placeholder="VD: xưng 'bạn', giọng kể chuyện"></div>
                <div class="lz-checks">
                    <label class="lz-check"><input type="checkbox" id="${P}Cont" checked> <span>Tự nhắn "Tiếp tục" khi câu trả lời bị cụt (bài viết lại/dịch ngắn hơn hẳn bản gốc)</span></label>
                    <label class="lz-check"><input type="checkbox" id="${P}Dry"> <span>Chạy thử — không mở ${NAME}, chỉ kiểm tra luồng và file xuất</span></label>
                </div>
                <div class="action-bar lz-actions"><button type="submit" id="${P}Start" class="btn-glow"><i class="fa-solid fa-bolt"></i> Chạy bằng ${NAME}</button></div>
            </form>
        </div>
        <div class="card output-section">
            <h2><i class="fa-solid fa-list-check"></i> Tiến Độ &amp; Kết Quả</h2>
            <div id="${P}Empty" class="empty-state"><i class="fa-solid fa-robot"></i><p>Chưa có job. Nhập câu lệnh + danh sách mục rồi bấm Chạy.</p></div>
            <div id="${P}Job" style="display:none;">
                <div class="lz-jobhead"><span id="${P}State" class="lz-badge">—</span><span id="${P}Summary" class="lz-muted"></span></div>
                <div class="lz-progress"><div id="${P}Bar" class="lz-progress-bar"></div></div>
                <div id="${P}Error" class="lz-error" style="display:none;"></div>
                <div id="${P}Groups"></div>
                <div class="lz-actions-row">
                    <button type="button" id="${P}Cancel" class="btn-primary" style="display:none;"><i class="fa-solid fa-ban"></i> Huỷ</button>
                    <button type="button" id="${P}Reset" class="btn-primary" style="display:none;"><i class="fa-solid fa-rotate-right"></i> Làm mới</button>
                    <button type="button" id="${P}Resume" class="btn-primary" style="display:none;"><i class="fa-solid fa-play"></i> Tiếp tục phần còn thiếu</button>
                    <a id="${P}Zip" href="#" class="btn-primary" style="display:none;" download><i class="fa-solid fa-file-zipper"></i> Tải tất cả (ZIP)</a>
                </div>
                <div id="${P}PreviewBox" style="display:none;">
                    <label><span id="${P}PreviewTitle">Xem trước</span></label>
                    <textarea id="${P}PreviewText" class="glass-input" rows="14" readonly></textarea>
                    <div class="lz-actions-row"><a id="${P}PreviewDl" href="#" class="btn-primary" download><i class="fa-solid fa-download"></i> Tải file này</a></div>
                </div>
                <div class="log-container"><h4><i class="fa-solid fa-terminal"></i> Nhật ký job</h4><pre id="${P}Log">...</pre></div>
            </div>
        </div>`;

        const selected = new Set();
        const KEY = 'aitab_' + ai;
        // ---- nhớ lựa chọn trên máy này ----
        const FIELDS = ['Prompt', 'Split', 'ChatMode', 'Chunk', 'DMin', 'DMax', 'Extra'];
        try {
            const sv = JSON.parse(localStorage.getItem(KEY) || '{}');
            FIELDS.forEach((f) => { if (sv[f] != null) $(f).value = sv[f]; });
            (sv.countries || []).forEach((c) => selected.add(c));
            if (sv.Cont != null) $('Cont').checked = sv.Cont;
        } catch (e) { /* bỏ qua */ }
        const save = () => { try { const o = { countries: Array.from(selected), Cont: $('Cont').checked }; FIELDS.forEach((f) => o[f] = $(f).value); localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) { /* bỏ qua */ } };
        FIELDS.forEach((f) => $(f).addEventListener('change', save));
        $('Prompt').addEventListener('input', save);

        // ---- đếm mục ----
        function countItems() {
            const t = $('Items').value.replace(/\r\n/g, '\n').trim();
            let n = 0;
            if (t) n = $('Split').value === 'line' ? t.split('\n').filter((l) => l.trim()).length
                : $('Split').value === 'all' ? 1 : ('\n' + t + '\n').split(/\n\s*-{3,}\s*\n/).filter((b) => b.trim()).length;
            n += $('Files').files.length;
            $('Count').textContent = `${n} mục`;
            return n;
        }
        ['input', 'change'].forEach((ev) => { $('Items').addEventListener(ev, countItems); $('Split').addEventListener(ev, countItems); $('Files').addEventListener(ev, countItems); });

        // ---- câu lệnh mẫu ----
        function renderTemplates() {
            const sel = $('Tpl'), keep = sel.value;
            sel.innerHTML = '<option value="">— chọn câu lệnh mẫu —</option>' + templates.map((t) => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('');
            if (keep && templates.some((t) => t.id === keep)) sel.value = keep;
        }
        $('Tpl').addEventListener('change', () => {
            const t = templates.find((x) => x.id === $('Tpl').value);
            if (t) { $('Prompt').value = t.prompt; save(); }
        });
        $('TplSave').addEventListener('click', async () => {
            const prompt = $('Prompt').value.trim(); if (!prompt) return toast('Gõ câu lệnh trước đã.', true);
            const cur = templates.find((x) => x.id === $('Tpl').value);
            const name = window.prompt('Tên câu lệnh mẫu:', cur ? cur.name : ''); if (!name) return;
            const d = await jpost('/api/aichat/templates', { id: cur && cur.name === name ? cur.id : '', name, prompt });
            if (d.status === 'success') { templates = d.templates; instances.forEach((x) => x.renderTemplates()); toast('Đã lưu mẫu'); } else toast(d.message || 'Lỗi', true);
        });
        $('TplDel').addEventListener('click', async () => {
            const cur = templates.find((x) => x.id === $('Tpl').value); if (!cur) return;
            if (!confirm('Xoá câu lệnh mẫu "' + cur.name + '"?')) return;
            const d = await jpost('/api/aichat/templates', { id: cur.id, delete: true });
            if (d.status === 'success') { templates = d.templates; instances.forEach((x) => x.renderTemplates()); }
        });

        // ---- quốc gia ----
        function renderCountries() {
            const q = $('CSearch').value.trim().toLowerCase(), grid = $('Countries');
            grid.innerHTML = '';
            countries.forEach((c) => {
                if (q && !`${c.name_vi} ${c.language} ${c.code}`.toLowerCase().includes(q)) return;
                const lab = document.createElement('label');
                lab.className = 'country-chip' + (selected.has(c.code) ? ' selected' : '');
                lab.innerHTML = `<input type="checkbox" ${selected.has(c.code) ? 'checked' : ''}> <span>${esc(c.flag)} ${esc(c.name_vi)}</span><small>${esc(c.language.replace(/\s*\(.*\)/, ''))}</small>`;
                lab.querySelector('input').addEventListener('change', (e) => {
                    if (e.target.checked) selected.add(c.code); else selected.delete(c.code);
                    lab.classList.toggle('selected', e.target.checked);
                    $('CCount').textContent = `Đã chọn ${selected.size}`; save();
                });
                grid.appendChild(lab);
            });
            $('CCount').textContent = `Đã chọn ${selected.size}`;
        }
        $('CSearch').addEventListener('input', renderCountries);
        $('CNone').addEventListener('click', () => { selected.clear(); renderCountries(); save(); });

        // ---- tài khoản ----
        async function loadAccount() {
            try {
                const d = await jget('/api/ai/accounts');
                const p = (d.providers || []).find((x) => x.provider === ai) || {};
                const a = p.account || {};
                const who = [a.name, a.email ? '(' + a.email + ')' : ''].filter(Boolean).join(' ');
                $('Acc').innerHTML = who ? `<span class="ai-ok"><i class="fa-solid fa-circle-check"></i> ${esc(who)}</span>`
                    : `<span class="gm-warn">${NAME} chưa đăng nhập trên máy này</span>`;
                $('Model').textContent = '· model: ' + (p.model || 'theo web');
            } catch (e) { /* bỏ qua */ }
        }

        // ---- chạy ----
        let jobId = null, pollTimer = null, shownFile = null;
        $('Form').addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!$('Prompt').value.trim()) return toast('Hãy nhập câu lệnh hoặc chọn câu lệnh mẫu.', true);
            if (!countItems()) return toast('Chưa có mục nào.', true);
            const fd = new FormData();
            fd.append('ai', ai);
            fd.append('prompt', $('Prompt').value);
            fd.append('items', $('Items').value);
            fd.append('split', $('Split').value);
            Array.from($('Files').files).forEach((f) => fd.append('files[]', f));
            fd.append('countries', JSON.stringify(Array.from(selected)));
            fd.append('chatMode', $('ChatMode').value);
            fd.append('chunk', $('Chunk').value);
            fd.append('delayMin', $('DMin').value);
            fd.append('delayMax', $('DMax').value);
            fd.append('extra', $('Extra').value);
            fd.append('customFilename', $('Name').value.trim());
            fd.append('autoContinue', $('Cont').checked ? '1' : '');
            fd.append('dryRun', $('Dry').checked ? '1' : '');
            $('Start').disabled = true;
            try {
                const d = await (await fetch('/api/aichat/run', { method: 'POST', body: fd })).json();
                if (d.status === 'success') { toast(`Đã bắt đầu ${d.units} mục.`); attach(d.job_id); }
                else toast(d.message || 'Không bắt đầu được', true);
            } catch (err) { toast('Lỗi kết nối tới máy chủ', true); }
            $('Start').disabled = false;
        });
        function attach(id) {
            jobId = id; shownFile = null;
            $('PreviewBox').style.display = 'none'; $('Empty').style.display = 'none'; $('Job').style.display = 'block';
            poll(); clearInterval(pollTimer); pollTimer = setInterval(poll, 2000);
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
            const results = job.results || {}, keys = Object.keys(results);
            const done = keys.filter((k) => results[k].status === 'done').length;
            const errs = keys.filter((k) => results[k].status === 'error').length;
            $('Bar').style.width = `${Math.min(100, (done / (keys.length || 1)) * 100)}%`;
            $('State').className = 'lz-badge ' + job.state; $('State').textContent = STATE_LABEL[job.state] || job.state;
            const end = job.finished_at || Date.now() / 1000;
            $('Summary').textContent = `${done}/${keys.length} mục xong${errs ? ` · ${errs} lỗi` : ''}${job.dry_run ? ' · CHẠY THỬ' : ''}${job.started_at ? ' · ' + fmtDuration(end - job.started_at) : ''}`;
            if (job.error) { $('Error').style.display = 'block'; $('Error').textContent = job.error; } else $('Error').style.display = 'none';
            const box = $('Groups'); box.innerHTML = '';
            const multi = (job.countries || []).length > 1 || (job.countries || [])[0] !== 'SAME';
            const chipsWrap = document.createElement('div'); chipsWrap.className = 'lz-chips';
            (job.articles || []).forEach((a) => {
                let chips = chipsWrap;
                if (multi) {
                    const g = document.createElement('div'); g.className = 'lz-group';
                    g.innerHTML = `<div class="lz-group-title"><i class="fa-solid fa-file-lines"></i> ${esc(a.name)}</div><div class="lz-chips"></div>`;
                    box.appendChild(g); chips = g.querySelector('.lz-chips');
                }
                (job.countries || []).forEach((code) => {
                    const r = results[`${a.id}:${code}`] || { status: 'pending' };
                    const c = cmap[code] || { flag: '', name_vi: code };
                    const b = document.createElement('button'); b.type = 'button';
                    b.className = 'res-chip ' + r.status + (r.file && r.file === shownFile ? ' active' : '');
                    let tail = '⏳';
                    if (r.status === 'done') tail = '✅';
                    else if (r.status === 'running') tail = r.chunks_total > 1 ? `🔄 ${r.chunks_done || 0}/${r.chunks_total}` : '🔄';
                    else if (r.status === 'error') tail = '❌';
                    const label = multi ? `${c.flag} ${c.name_vi}` : a.name;
                    b.textContent = `${label} ${tail}`;
                    if (r.status === 'error') b.title = r.error || 'Lỗi';
                    if (r.status === 'done') { b.title = `${(r.chars || 0).toLocaleString('vi-VN')} ký tự — bấm để xem`; b.addEventListener('click', () => showResult(r.file, multi ? `${a.name} — ${c.name_vi}` : a.name)); }
                    chips.appendChild(b);
                });
            });
            if (!multi) box.appendChild(chipsWrap);
            const running = job.state === 'running' || job.state === 'queued';
            $('Cancel').style.display = running ? 'inline-flex' : 'none';
            $('Reset').style.display = running ? 'none' : 'inline-flex';
            $('Resume').style.display = !running && done < keys.length ? 'inline-flex' : 'none';
            if (job.zip) { $('Zip').style.display = 'inline-flex'; $('Zip').href = `/api/download/${encodeURIComponent(job.zip)}`; } else $('Zip').style.display = 'none';
            const log = $('Log'); const atBottom = log.scrollHeight - log.clientHeight <= log.scrollTop + 12;
            log.textContent = job.log_tail || ''; if (atBottom) log.scrollTop = log.scrollHeight;
        }
        async function showResult(file, title) {
            try {
                const d = await jget(`/api/localize/${jobId}/text?f=${encodeURIComponent(file)}`);
                if (d.status !== 'success') return toast(d.message || 'Không đọc được file', true);
                shownFile = file;
                $('PreviewBox').style.display = 'block'; $('PreviewTitle').textContent = title; $('PreviewText').value = d.text;
                $('PreviewDl').href = `/api/localize/${jobId}/file?f=${encodeURIComponent(file)}`;
                $('PreviewDl').setAttribute('download', file.split('/').pop());
                poll();
            } catch (e) { toast('Lỗi kết nối tới máy chủ', true); }
        }
        $('Cancel').addEventListener('click', async () => { if (!jobId) return; const d = await jpost(`/api/localize/${jobId}/cancel`); toast(d.message || 'Đã gửi lệnh huỷ', d.status === 'error'); });
        $('Resume').addEventListener('click', async () => {
            if (!jobId) return; const d = await jpost(`/api/localize/${jobId}/resume`);
            if (d.status === 'success') { toast('Đã chạy tiếp phần còn thiếu.'); attach(jobId); } else toast(d.message || 'Không chạy tiếp được', true);
        });
        $('Reset').addEventListener('click', () => {
            try { if (jobId) localStorage.setItem('dismissed_' + ai, jobId); } catch (e) { /* bỏ qua */ }
            clearInterval(pollTimer); pollTimer = null; jobId = null; shownFile = null;
            $('Job').style.display = 'none'; $('PreviewBox').style.display = 'none'; $('Empty').style.display = '';
            toast('Đã làm mới — có thể chạy job mới. File cũ vẫn ở tab Lịch Sử.');
        });
        root.querySelectorAll('.ai-goto').forEach((a) => a.addEventListener('click', (e) => {
            e.preventDefault(); const t = document.querySelector('.tab-btn[data-tab="tab-ai"]'); if (t) t.click();
        }));
        jget('/api/localize/latest?kind=' + ai).then((d) => {
            let dis = null; try { dis = localStorage.getItem('dismissed_' + ai); } catch (e) { /* bỏ qua */ }
            if (d && d.job_id && d.job_id !== dis && !jobId) attach(d.job_id);
        }).catch(() => {});
        const tabBtn = document.querySelector(`.tab-btn[data-tab="${root.id}"]`);
        if (tabBtn) tabBtn.addEventListener('click', () => { loadAccount(); if (!countries.length) loadCountries(); });
        loadAccount(); countItems();
        return { renderTemplates, renderCountries, refresh: () => { if (jobId) poll(); } };
    }

    document.querySelectorAll('.tab-content[data-ai]').forEach((root) => instances.push(build(root)));
    if (instances.length) { loadTemplates(); loadCountries(); }
})();
