/* Cửa sổ "Sửa từng đoạn": đánh dấu đoạn cần viết lại; mỗi đoạn có thể nhờ AI khác viết lại, copy câu lệnh ra ngoài,
   hoặc dán đoạn tự viết; bấm Lưu -> Tool ghép thành file hoàn thiện (giữ bản đầu). Dùng chung cho mọi tab kết quả. */
(function () {
    'use strict';
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    let tt;
    const toast = (m, err) => { const t = document.getElementById('toast'); if (!t) return; t.textContent = m;
        t.style.background = err ? 'rgba(239,68,68,0.9)' : 'rgba(16,185,129,0.9)'; t.classList.add('show');
        clearTimeout(tt); tt = setTimeout(() => t.classList.remove('show'), 4000); };
    const AIS = [['chatgpt', 'ChatGPT'], ['claude', 'Claude'], ['gemini', 'Gemini']];
    const AINAME = Object.fromEntries(AIS);

    const modal = document.createElement('div');
    modal.id = 'peModal';
    modal.className = 'lz-modal';
    modal.style.display = 'none';
    modal.innerHTML = `
      <div class="lz-modal-box pe-box">
        <div class="lz-modal-head"><b id="peTitle">Sửa từng đoạn</b>
          <div class="pe-headbtns"><button type="button" class="btn-glow" id="peSave"><i class="fa-solid fa-floppy-disk"></i> Lưu &amp; ghép file hoàn thiện</button>
          <button type="button" class="btn-primary" id="peClose">Đóng</button></div></div>
        <div class="pe-tools">
          <div class="fl-chips pe-filter"><button type="button" class="active" data-f="flag">Đoạn cần sửa <span id="peNFlag">0</span></button><button type="button" data-f="all">Tất cả <span id="peNAll">0</span></button><button type="button" data-f="edited">Đã thay <span id="peNEd">0</span></button></div>
          <span class="lz-muted" id="peStat"></span>
        </div>
        <div class="pe-tools pe-ai">
          <label class="pe-selall"><input type="checkbox" id="peSelAll"> chọn hết đoạn đang hiện</label>
          <select id="peAi" class="glass-input">${AIS.map(([k, n]) => `<option value="${k}">${n}</option>`).join('')}</select>
          <input type="text" id="peNote" class="glass-input" placeholder="Yêu cầu khi viết lại (tuỳ chọn) — VD: kể chuyện hơn, thêm ví dụ, ngắn gọn hơn">
          <button type="button" class="btn-primary" id="peRunAi"><i class="fa-solid fa-robot"></i> AI viết lại đoạn đã chọn</button>
        </div>
        <div id="peTask" class="pe-task" style="display:none;"></div>
        <div id="peList" class="pe-list"></div>
        <div class="lz-muted pe-foot">Bản gốc lúc đầu được giữ lại (đuôi .ban_dau). Mỗi lần lưu, Tool ghi lại đoạn nào đã thay vào báo cáo _ra_soat.txt và ghép lại file tải về / ZIP.</div>
      </div>`;
    document.addEventListener('DOMContentLoaded', () => document.body.appendChild(modal));
    if (document.readyState !== 'loading') document.body.appendChild(modal);
    const $ = (id) => document.getElementById(id);

    let S = null;   // trạng thái đang sửa
    function counts() {
        const ed = Object.keys(S.edits).filter((k) => S.edits[k].accepted).length;
        $('peNFlag').textContent = Object.keys(S.flags).length;
        $('peNAll').textContent = S.paras.length;
        $('peNEd').textContent = ed;
        const pend = Object.keys(S.edits).filter((k) => !S.edits[k].accepted).length;
        $('peStat').textContent = `${ed} đoạn sẽ được thay khi Lưu` + (pend ? ` · ${pend} bản AI đang chờ sếp duyệt` : '');
    }
    function visible() {
        return S.paras.map((_, i) => i).filter((i) => S.filter === 'all' || (S.filter === 'flag' ? S.flags[i] || S.edits[i] : S.edits[i] && S.edits[i].accepted));
    }
    function promptFor(i) {
        const prev = S.paras[i - 1] || '(đầu bài)', next = S.paras[i + 1] || '(cuối bài)';
        const why = (S.flags[i] || []).join('; ');
        return `Viết lại ĐOẠN dưới đây cho hay hơn, tự nhiên như người bản xứ am hiểu chủ đề viết. Giữ nguyên ngôn ngữ của đoạn, giữ đủ ý, dữ kiện, tên riêng, số liệu; độ dài tương đương; nối mạch với đoạn trước và sau; bỏ câu sáo, từ phóng đại, giọng máy móc.`
            + (why ? `\nĐiểm cần sửa: ${why}` : '') + ($('peNote').value.trim() ? `\nYêu cầu thêm: ${$('peNote').value.trim()}` : '')
            + `\nChỉ trả về đoạn đã viết lại, không giải thích.\n\nĐoạn TRƯỚC (để nối mạch): ${prev}\n\nĐOẠN CẦN VIẾT LẠI:\n${S.paras[i]}\n\nĐoạn SAU (để nối mạch): ${next}`;
    }
    function row(i) {
        const e = S.edits[i], f = S.flags[i] || [];
        const cur = e && e.accepted ? e.text : S.paras[i];
        return `<div class="pe-row ${f.length ? 'flag' : ''} ${e && e.accepted ? 'done' : ''}" data-i="${i}">
          <div class="pe-rowhead"><label><input type="checkbox" class="pe-cb" data-i="${i}" ${S.sel.has(i) ? 'checked' : ''}> <b>Đoạn ${i + 1}</b></label>
            ${f.map((x) => `<span class="pe-flag">${esc(x)}</span>`).join('')}
            ${e && e.accepted ? `<span class="rv-badge ok">đã thay · ${esc(e.by)}</span>` : ''}</div>
          <div class="pe-text ${e && e.accepted ? 'pe-old' : ''}">${esc(S.paras[i])}</div>
          ${e && e.accepted ? `<div class="pe-text pe-newtxt">${esc(e.text)}</div>` : ''}
          ${e && !e.accepted ? `<div class="pe-cand"><div class="lz-muted">Bản ${esc(e.by)} đề xuất:</div><div class="pe-text pe-newtxt">${esc(e.text)}</div>
             <button type="button" class="btn-glow fl-mini" data-a="accept" data-i="${i}">✓ Dùng bản này</button>
             <button type="button" class="btn-primary fl-mini" data-a="reject" data-i="${i}">Bỏ</button></div>` : ''}
          <div class="pe-manual" id="peM${i}" style="display:none;"><textarea class="glass-input" rows="4" placeholder="Dán đoạn đã viết lại (từ ChatGPT/Claude/Gemini bên ngoài hoặc tự viết)…">${esc(cur)}</textarea>
             <button type="button" class="btn-glow fl-mini" data-a="useManual" data-i="${i}">✓ Thay đoạn này</button></div>
          <div class="pe-acts">
            <button type="button" class="btn-primary fl-mini" data-a="manual" data-i="${i}"><i class="fa-solid fa-paste"></i> Dán / sửa tay</button>
            <button type="button" class="btn-primary fl-mini" data-a="ai1" data-i="${i}"><i class="fa-solid fa-robot"></i> AI viết lại</button>
            <button type="button" class="btn-primary fl-mini" data-a="copy" data-i="${i}"><i class="fa-solid fa-copy"></i> Copy câu lệnh</button>
            ${e ? `<button type="button" class="btn-primary fl-mini" data-a="undo" data-i="${i}"><i class="fa-solid fa-rotate-left"></i> Về bản cũ</button>` : ''}
          </div></div>`;
    }
    function render() {
        const v = visible();
        $('peList').innerHTML = v.length ? v.map(row).join('')
            : `<div class="lz-muted" style="padding:20px;">${S.filter === 'flag' ? 'Máy không thấy đoạn nào cần sửa — bấm "Tất cả" để tự chọn đoạn.' : 'Chưa có đoạn nào.'}</div>`;
        $('peSelAll').checked = v.length > 0 && v.every((i) => S.sel.has(i));
        counts();
    }

    window.openParaEditor = async function (jobId, file, title, onSaved) {
        try {
            const d = await (await fetch(`/api/para/${jobId}?f=${encodeURIComponent(file)}`)).json();
            if (d.status !== 'success') return toast(d.message || 'Không mở được file', true);
            S = { jobId, file, onSaved, paras: d.paras, flags: {}, edits: {}, sel: new Set(), filter: 'flag', task: null };
            Object.entries(d.flags || {}).forEach(([k, v]) => S.flags[+k] = v);
            if (!Object.keys(S.flags).length) S.filter = 'all';
            modal.querySelectorAll('.pe-filter button').forEach((b) => b.classList.toggle('active', b.dataset.f === S.filter));
            $('peTitle').textContent = 'Sửa từng đoạn — ' + (title || file.split('/').pop());
            $('peTask').style.display = 'none';
            try { const a = localStorage.getItem('pe_ai'); if (a) $('peAi').value = a; } catch (e) { /* bỏ qua */ }
            render();
            modal.style.display = 'flex';
        } catch (e) { toast('Lỗi kết nối tới máy chủ', true); }
    };

    async function runAi(idxs) {
        if (!idxs.length) return toast('Chọn ít nhất 1 đoạn (tích ô vuông).', true);
        const ai = $('peAi').value;
        try { localStorage.setItem('pe_ai', ai); } catch (e) { /* bỏ qua */ }
        const paras = S.paras.map((p, i) => (S.edits[i] && S.edits[i].accepted ? S.edits[i].text : p));
        const d = await (await fetch(`/api/para/${S.jobId}/rewrite`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ f: S.file, idxs, ai, note: $('peNote').value.trim(), paras }) })).json();
        if (d.status !== 'success') return toast(d.message || 'Không chạy được', true);
        S.task = d.task;
        $('peTask').style.display = '';
        $('peTask').innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${AINAME[ai]} đang viết lại ${idxs.length} đoạn (cửa sổ Chrome sẽ mở)…`;
        const jid = S.jobId, tid = d.task;
        const tick = async () => {
            if (!S || S.task !== tid) return;
            try {
                const t = await (await fetch(`/api/para/${jid}/task/${tid}`)).json();
                const last = (t.log || []).slice(-1)[0] || '';
                if (t.state === 'done' || t.state === 'error') {
                    Object.entries(t.results || {}).forEach(([k, txt]) => { S.edits[+k] = { text: txt, by: AINAME[ai], accepted: false }; });
                    $('peTask').innerHTML = t.state === 'done'
                        ? `✅ ${AINAME[ai]} đã viết lại ${Object.keys(t.results || {}).length}/${idxs.length} đoạn — duyệt từng đoạn bên dưới (✓ Dùng bản này / Bỏ).`
                        : `❌ ${esc(t.error || last || 'Lỗi')}`;
                    S.task = null; S.filter = S.filter === 'edited' ? 'flag' : S.filter;
                    idxs.forEach((i) => { if (!S.flags[i] && S.filter === 'flag' && S.edits[i]) S.filter = 'all'; });
                    modal.querySelectorAll('.pe-filter button').forEach((b) => b.classList.toggle('active', b.dataset.f === S.filter));
                    render();
                    return;
                }
                $('peTask').innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${esc(last || 'Đang mở trình duyệt…')}`;
            } catch (e) { /* lỗi mạng thoáng qua */ }
            setTimeout(tick, 2000);
        };
        setTimeout(tick, 1500);
    }

    modal.addEventListener('click', async (ev) => {
        const fb = ev.target.closest('.pe-filter button');
        if (fb) { S.filter = fb.dataset.f; modal.querySelectorAll('.pe-filter button').forEach((b) => b.classList.toggle('active', b === fb)); return render(); }
        const b = ev.target.closest('button[data-a]');
        if (!b || !S) return;
        const i = +b.dataset.i, a = b.dataset.a;
        if (a === 'manual') { const m = $('peM' + i); m.style.display = m.style.display === 'none' ? '' : 'none'; if (m.style.display === '') m.querySelector('textarea').focus(); return; }
        if (a === 'useManual') {
            const t = $('peM' + i).querySelector('textarea').value.trim();
            if (!t) return toast('Đoạn trống.', true);
            if (t === S.paras[i]) { delete S.edits[i]; } else S.edits[i] = { text: t, by: 'sửa tay', accepted: true };
            return render();
        }
        if (a === 'accept') { S.edits[i].accepted = true; return render(); }
        if (a === 'reject' || a === 'undo') { delete S.edits[i]; return render(); }
        if (a === 'ai1') return runAi([i]);
        if (a === 'copy') {
            try { await navigator.clipboard.writeText(promptFor(i)); toast('Đã copy câu lệnh — dán vào ChatGPT/Claude/Gemini bên ngoài, rồi dán kết quả vào "Dán / sửa tay".'); }
            catch (e) { $('peM' + i).style.display = ''; $('peM' + i).querySelector('textarea').value = promptFor(i); toast('Không copy tự động được — câu lệnh đã hiện trong ô, sếp bôi đen và copy.', true); }
        }
    });
    modal.addEventListener('change', (ev) => {
        const cb = ev.target.closest('.pe-cb');
        if (cb) { if (cb.checked) S.sel.add(+cb.dataset.i); else S.sel.delete(+cb.dataset.i); }
        if (ev.target.id === 'peSelAll') { visible().forEach((i) => ev.target.checked ? S.sel.add(i) : S.sel.delete(i)); render(); }
    });
    document.addEventListener('click', (ev) => {
        if (ev.target.closest('#peRunAi')) runAi(Array.from(S ? S.sel : []).sort((x, y) => x - y));
        if (ev.target.closest('#peClose')) {
            const pend = S && Object.keys(S.edits).length;
            if (pend && !confirm('Có đoạn đã thay nhưng CHƯA LƯU. Đóng sẽ mất các thay đổi này?')) return;
            modal.style.display = 'none'; S = null;
        }
        if (ev.target.closest('#peSave')) save();
    });
    async function save() {
        if (!S) return;
        const acc = Object.keys(S.edits).filter((k) => S.edits[k].accepted).map(Number);
        if (!acc.length) return toast('Chưa thay đoạn nào.', true);
        const paras = S.paras.map((p, i) => (S.edits[i] && S.edits[i].accepted ? S.edits[i].text : p));
        const changes = acc.sort((x, y) => x - y).map((i) => ({ p: i + 1, by: S.edits[i].by, old: S.paras[i], new: S.edits[i].text }));
        const d = await (await fetch(`/api/para/${S.jobId}/save`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ f: S.file, paras, changes }) })).json();
        if (d.status !== 'success') return toast(d.message || 'Lưu thất bại', true);
        toast(`Đã lưu: thay ${acc.length} đoạn, đã ghép file hoàn thiện (${d.chars.toLocaleString('vi-VN')} ký tự).`);
        const cb = S.onSaved;
        S.paras = paras; S.edits = {}; render();
        if (cb) cb();
    }
})();

/* Gắn nút "Sửa từng đoạn" cạnh nút "Tải file này" của khung xem trước (prefix: lz, yt, nb, cg, cl). */
window.peBind = function (prefix, jobId, file, title, refresh) {
    const dl = document.getElementById(prefix + 'PreviewDl');
    if (!dl) return;
    let b = document.getElementById(prefix + 'PeBtn');
    if (!b) {
        b = document.createElement('button');
        b.type = 'button';
        b.id = prefix + 'PeBtn';
        b.className = 'btn-glow';
        b.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Sửa từng đoạn';
        b.title = 'Xem đoạn cần viết lại; nhờ AI khác viết lại, copy câu lệnh ra ngoài hoặc dán đoạn tự viết; lưu thành file hoàn thiện';
        dl.parentElement.insertBefore(b, dl);
    }
    b.onclick = () => window.openParaEditor(jobId, file, title, refresh);
};
