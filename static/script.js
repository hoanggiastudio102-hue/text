document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const fileList = document.getElementById('fileList');
    const rawText = document.getElementById('rawText');
    const charCount = document.getElementById('charCount');
    const translatorForm = document.getElementById('translatorForm');
    
    const submitBtn = document.getElementById('submitBtn');
    
    const loadingState = document.getElementById('loadingState');
    const resultState = document.getElementById('resultState');
    const emptyState = document.getElementById('emptyState');
    
    const previewOutput = document.getElementById('previewOutput');
    const downloadBtn = document.getElementById('downloadBtn');

    // Prompts
    const promptSelect = document.getElementById('promptSelect');
    const batchPromptSelect = document.getElementById('batchPromptSelect');
    const creativeChecklist = document.getElementById('creativePromptChecklist');
    
    const promptForm = document.getElementById('promptForm');
    const promptsListBody = document.getElementById('promptsListBody');
    
    // Tabs Logic
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => {
                c.classList.remove('active');
                c.style.display = 'none';
            });
            
            btn.classList.add('active');
            const target = document.getElementById(btn.getAttribute('data-tab'));
            target.classList.add('active');
            
            if (target.id === 'tab-translate' || target.id === 'tab-localize') {
                target.style.display = 'grid';
            } else {
                target.style.display = 'block';
            }
            
            if (btn.getAttribute('data-tab') === 'tab-history') {
                loadHistory();
            }
            if (btn.getAttribute('data-tab') === 'tab-prompts') {
                loadPrompts();

    async function loadProfiles() {
        try {
            const res = await fetch('/api/profiles');
            const result = await res.json();
            if (result.status === 'success') {
                const select = document.getElementById('activeProfile');
                if (select) {
                    select.innerHTML = '';
                    result.data.forEach(p => {
                        select.innerHTML += `<option value="${p}">${p}</option>`;
                    });
                }
            }
        } catch (e) { console.error("Error loading profiles:", e); }
    }
    loadProfiles();
    
            }
        });
    });

    // Prompt Sub-tabs
    const promptSubTabs = document.querySelectorAll('.prompt-sub-tab');
    const promptSubContents = document.querySelectorAll('.prompt-sub-content');
    promptSubTabs.forEach(btn => {
        btn.addEventListener('click', () => {
            promptSubTabs.forEach(t => { t.classList.remove('active'); t.style.background = 'rgba(255,255,255,0.05)'; t.style.color = 'var(--text-muted)'; });
            promptSubContents.forEach(c => c.style.display = 'none');
            
            btn.classList.add('active');
            btn.style.background = ''; // reset to default .btn-primary background
            btn.style.color = 'white';
            const targetId = btn.getAttribute('data-target');
            document.getElementById(targetId).style.display = 'flex';
        });
    });

    // Ô "Chế độ" chỉ hiện với mẫu Viết Lại
    function syncPromptModeVisibility() {
        const t = document.getElementById('promptType');
        const g = document.getElementById('promptModeGroup');
        if (t && g) g.style.display = (t.value === 'rewrite') ? 'block' : 'none';
    }
    document.getElementById('promptType').addEventListener('change', syncPromptModeVisibility);

    // Render Prompts logic
    window.allPrompts = [];
    
    const LANG_EMOJIS = {
        'all': '🌍 Tất cả',
        'en': '🇺🇸 Tiếng Anh',
        'vi': '🇻🇳 Tiếng Việt',
        'ja': '🇯🇵 Tiếng Nhật',
        'ko': '🇰🇷 Tiếng Hàn',
        'zh': '🇨🇳 Tiếng Trung',
        'fr': '🇫🇷 Tiếng Pháp'
    };

    function renderPrompts() {
        const translateListBody = document.getElementById('list-translate');
        const creativeListBody = document.getElementById('list-creative');
        const rewriteListBody = document.getElementById('list-rewrite');
        if (translateListBody) translateListBody.innerHTML = '';
        if (creativeListBody) creativeListBody.innerHTML = '';
        if (rewriteListBody) rewriteListBody.innerHTML = '';
        
        const promptSelect = document.getElementById('promptSelect');
        const batchPromptSelect = document.getElementById('batchPromptSelect');
        const creativeChecklist = document.getElementById('creativePromptChecklist');
        
        if (promptSelect) promptSelect.innerHTML = '';
        if (batchPromptSelect) batchPromptSelect.innerHTML = '';
        if (creativeChecklist) creativeChecklist.innerHTML = '';

        const activeTargetLang = document.getElementById('targetLang') ? document.getElementById('targetLang').value : 'all';
        const activeBatchTargetLang = document.getElementById('batchTargetLang') ? document.getElementById('batchTargetLang').value : 'all';
        const activeCreativeTargetLang = document.getElementById('creativeTargetLang') ? document.getElementById('creativeTargetLang').value : 'all';

        window.allPrompts.forEach(p => {
            const promptType = p.type || 'translate'; // Default for old prompts
            const promptLang = p.targetLang || 'all'; // Default for old prompts
            
            // Build badge HTML
            let badgeHtml = `<span style="font-size: 11px; padding: 2px 6px; background: rgba(255,255,255,0.1); border-radius: 4px; margin-left: 8px; color: var(--text-muted);">${LANG_EMOJIS[promptLang] || promptLang}</span>`;
            if (p.code) {
                badgeHtml += `<span style="font-size: 11px; padding: 2px 6px; background: rgba(59, 130, 246, 0.2); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 4px; margin-left: 6px; color: #60a5fa;"><i class="fa-solid fa-hashtag" style="margin-right: 3px;"></i>${p.code}</span>`;
            }
            
            // Cards for list
            const div = document.createElement('div');
            div.className = 'prompt-item';
            div.innerHTML = `
                <div class="prompt-info" style="flex: 1; min-width: 0;">
                    <h4 style="margin-bottom: 5px; color: var(--text-main); font-size: 15px; display: flex; align-items: center;">${p.name} ${badgeHtml}</h4>
                    <div style="font-size: 13px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        ${p.content}
                    </div>
                </div>
                <div class="prompt-actions" style="margin-left: 15px;">
                    ${p.id !== 'default' ? `<button class="btn-delete-prompt" data-id="${p.id}" style="background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); padding: 8px 12px; border-radius: 8px; cursor: pointer; transition: all 0.2s;" onmouseover="this.style.background='#ef4444'; this.style.color='white';" onmouseout="this.style.background='rgba(239, 68, 68, 0.2)'; this.style.color='#ef4444';"><i class="fa-solid fa-trash"></i></button>` : `<span style="font-size: 12px; padding: 4px 8px; background: rgba(255,255,255,0.1); border-radius: 4px;">Mặc định</span>`}
                </div>
            `;
            div.style.cssText = `
                display: flex;
                align-items: center;
                padding: 15px;
                background: rgba(0,0,0,0.2);
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 12px;
                cursor: pointer;
                transition: all 0.3s ease;
            `;
            div.onmouseover = () => div.style.borderColor = 'var(--primary)';
            div.onmouseout = () => div.style.borderColor = 'rgba(255,255,255,0.05)';
            
            div.onclick = (e) => {
                if(!e.target.closest('.btn-delete-prompt')) {
                    document.getElementById('promptName').value = p.name;
                    document.getElementById('promptContent').value = p.content;
                    const pTypeElem = document.getElementById('promptType');
                    if (pTypeElem) pTypeElem.value = promptType;
                    const pLangElem = document.getElementById('promptTargetLang');
                    if (pLangElem) pLangElem.value = promptLang;
                    const pCodeElem = document.getElementById('promptCode');
                    if (pCodeElem) pCodeElem.value = p.code || '';
                    const pModeElem = document.getElementById('promptMode');
                    if (pModeElem) pModeElem.value = p.mode || 'rewrite';
                    syncPromptModeVisibility();
                    
                    document.querySelectorAll('.prompt-item').forEach(el => { el.style.background = 'rgba(0,0,0,0.2)'; el.style.borderColor = 'rgba(255,255,255,0.05)'; });
                    div.style.background = 'rgba(59, 130, 246, 0.1)';
                    div.style.borderColor = 'var(--primary)';
                }
            };
            
            if (promptType === 'translate' && translateListBody) {
                translateListBody.appendChild(div);
                
                // Add to single select if it matches activeTargetLang or is global
                if (promptLang === 'all' || promptLang === activeTargetLang) {
                    if (promptSelect) promptSelect.innerHTML += `<option value="${p.id}">${p.name}</option>`;
                }
                // Add to batch select if it matches activeBatchTargetLang or is global
                if (promptLang === 'all' || promptLang === activeBatchTargetLang) {
                    if (batchPromptSelect) batchPromptSelect.innerHTML += `<option value="${p.id}">${p.name}</option>`;
                }
            } else if (promptType === 'rewrite' && rewriteListBody) {
                rewriteListBody.appendChild(div);
            } else if (promptType === 'creative' && creativeListBody) {
                creativeListBody.appendChild(div);
                
                // Add to creative checklist if it matches activeCreativeTargetLang or is global
                if (promptLang === 'all' || promptLang === activeCreativeTargetLang) {
                    if (creativeChecklist) {
                        creativeChecklist.innerHTML += `
                            <div style="margin-bottom: 8px;">
                                <label style="display: flex; align-items: center; cursor: pointer; font-weight: normal; font-size: 14px;">
                                    <input type="checkbox" name="creativePrompts" value="${p.id}" checked style="margin-right: 10px; accent-color: var(--primary);">
                                    <span>${p.name} ${badgeHtml}</span>
                                </label>
                            </div>
                        `;
                    }
                }
            }
        });
        
        // Re-bind delete events
        document.querySelectorAll('.btn-delete-prompt').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = btn.getAttribute('data-id');
                if(confirm('Bạn có chắc chắn muốn xóa mẫu lệnh này?')) {
                    try {
                        const res = await fetch(`/api/prompts/${id}`, { method: 'DELETE' });
                        const result = await res.json();
                        showToast(result.message, result.status === 'error');
                        if(result.status === 'success') loadPrompts();

    async function loadProfiles() {
        try {
            const res = await fetch('/api/profiles');
            const result = await res.json();
            if (result.status === 'success') {
                const select = document.getElementById('activeProfile');
                if (select) {
                    select.innerHTML = '';
                    result.data.forEach(p => {
                        select.innerHTML += `<option value="${p}">${p}</option>`;
                    });
                }
            }
        } catch (e) { console.error("Error loading profiles:", e); }
    }
    loadProfiles();
    
                    } catch (err) {
                        showToast('Lỗi kết nối', true);
                    }
                }
            });
        });
    }

    // Load Prompts Function
    async function loadPrompts() {
        try {
            const res = await fetch('/api/prompts');
            const data = await res.json();
            if (data.status === 'success') {
                window.allPrompts = data.data;
                renderPrompts();
            }
        } catch (e) {
            console.error(e);
        }
    }
    
    // Auto load prompts on start
    loadPrompts();

    async function loadProfiles() {
        try {
            const res = await fetch('/api/profiles');
            const result = await res.json();
            if (result.status === 'success') {
                const select = document.getElementById('activeProfile');
                if (select) {
                    select.innerHTML = '';
                    result.data.forEach(p => {
                        select.innerHTML += `<option value="${p}">${p}</option>`;
                    });
                }
            }
        } catch (e) { console.error("Error loading profiles:", e); }
    }
    loadProfiles();
    

    // Re-render when languages change
    if (document.getElementById('targetLang')) {
        document.getElementById('targetLang').addEventListener('change', renderPrompts);
    }
    if (document.getElementById('batchTargetLang')) {
        document.getElementById('batchTargetLang').addEventListener('change', renderPrompts);
    }
    if (document.getElementById('creativeTargetLang')) {
        document.getElementById('creativeTargetLang').addEventListener('change', renderPrompts);
    }

    // New Prompt Btn
    const btnNewPrompt = document.getElementById('btnNewPrompt');
    if (btnNewPrompt) {
        btnNewPrompt.addEventListener('click', () => {
            promptForm.reset();
            syncPromptModeVisibility();
            document.getElementById('promptName').focus();
            document.querySelectorAll('.prompt-item').forEach(el => { el.style.background = 'rgba(0,0,0,0.2)'; el.style.borderColor = 'rgba(255,255,255,0.05)'; });
        });
    }

    // Create Prompt Logic
    promptForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('promptName').value;
        const content = document.getElementById('promptContent').value;
        const type = document.getElementById('promptType') ? document.getElementById('promptType').value : 'translate';
        const targetLang = document.getElementById('promptTargetLang') ? document.getElementById('promptTargetLang').value : 'all';
        const code = document.getElementById('promptCode') ? document.getElementById('promptCode').value.trim() : '';
        
        try {
            const res = await fetch('/api/prompts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                        profileName: document.getElementById('activeProfile') ? document.getElementById('activeProfile').value : 'gemini_profile',
                        name, content, type, targetLang, code,
                        mode: document.getElementById('promptMode') ? document.getElementById('promptMode').value : 'rewrite'
                })
            });
            const data = await res.json();
            showToast(data.message, data.status === 'error');
            if (data.status === 'success') {
                promptForm.reset();
                syncPromptModeVisibility();
                loadPrompts();

    async function loadProfiles() {
        try {
            const res = await fetch('/api/profiles');
            const result = await res.json();
            if (result.status === 'success') {
                const select = document.getElementById('activeProfile');
                if (select) {
                    select.innerHTML = '';
                    result.data.forEach(p => {
                        select.innerHTML += `<option value="${p}">${p}</option>`;
                    });
                }
            }
        } catch (e) { console.error("Error loading profiles:", e); }
    }
    loadProfiles();
    
            }
        } catch (e) {
            showToast('Lỗi kết nối', true);
        }
    });

    
    // Image Generation Logic
    const imageForm = document.getElementById('imageForm');
    if (imageForm) {
        imageForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('imageSubmitBtn');
            const originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Vẽ Ảnh...';
            
            const promptContent = document.getElementById('imagePromptContent').value;
            const resultContainer = document.getElementById('imageResultContainer');
            
            resultContainer.innerHTML = `
                <div style="text-align: center; color: var(--primary);">
                    <i class="fa-solid fa-wand-magic-sparkles fa-bounce" style="font-size: 2em; margin-bottom: 10px;"></i>
                    <p>AI đang vẽ ảnh, vui lòng chờ khoảng 30-60 giây...</p>
                </div>
            `;
            
            try {
                const res = await fetch('/api/generate_image', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        profileName: document.getElementById('activeProfile') ? document.getElementById('activeProfile').value : 'gemini_profile',
promptContent: promptContent,
                        imagePromptId: document.getElementById('imagePromptId').value,
                        imageCharacterSync: document.getElementById('imageCharacterSync').value
                    })
                });
                
                const data = await res.json();
                
                if (data.status === 'success' && data.images && data.images.length > 0) {
                    showToast(data.message, false);
                    resultContainer.innerHTML = '';
                    
                    data.images.forEach(img => {
                        const imgWrapper = document.createElement('div');
                        imgWrapper.style.cssText = 'position: relative; width: 45%; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.3);';
                        
                        imgWrapper.innerHTML = `
                            <img src="/outputs/images/${img}" style="width: 100%; height: auto; display: block;" alt="Generated Image">
                            <a href="/outputs/images/${img}" download="${img}" style="position: absolute; bottom: 10px; right: 10px; background: rgba(0,0,0,0.6); color: white; padding: 5px 10px; border-radius: 5px; text-decoration: none; font-size: 12px; backdrop-filter: blur(4px);">
                                <i class="fa-solid fa-download"></i> Tải Xuống
                            </a>
                        `;
                        resultContainer.appendChild(imgWrapper);
                    });
                } else {
                    showToast(data.message || 'Lỗi không xác định', true);
                    resultContainer.innerHTML = `<div class="empty-state"><i class="fa-solid fa-circle-exclamation" style="color: #ef4444;"></i><p>${data.message || 'Lỗi tạo ảnh'}</p></div>`;
                }
            } catch (err) {
                showToast('Lỗi kết nối máy chủ', true);
                resultContainer.innerHTML = `<div class="empty-state"><i class="fa-solid fa-triangle-exclamation" style="color: #ef4444;"></i><p>Lỗi kết nối máy chủ</p></div>`;
            }
            
            btn.disabled = false;
            btn.innerHTML = originalText;
        });
    }

    async function loadHistory() {
        const tbody = document.getElementById('historyTableBody');
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center;">Đang tải dữ liệu...</td></tr>';
        
        try {
            const res = await fetch('/api/history');
            const data = await res.json();
            
            if (data.status === 'success') {
                if (data.data.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Chưa có file nào được tạo.</td></tr>';
                } else {
                    tbody.innerHTML = '';
                    data.data.forEach(file => {
                        const tr = document.createElement('tr');
                        
                        let isBatch = file.name.endsWith('.zip');
                        let badgeClass = isBatch ? 'dich-loat' : 'dich-don';
                        let badgeText = isBatch ? 'Sáng Tạo Ngữ Hàng Loạt' : 'Sáng Tạo Ngữ';
                        let iconColor = isBatch ? '#f59e0b' : '#3b82f6';
                        let iconClass = isBatch ? 'fa-file-zipper' : 'fa-file-lines';
                        
                        tr.innerHTML = `
                            <td style="color: #9ca3af; font-family: monospace;">${file.time}</td>
                            <td>${file.size} KB</td>
                            <td><span class="badge-pill ${badgeClass}">${badgeText}</span></td>
                            <td><span class="text-ellipsis"><i class="fa-solid ${iconClass}" style="color: ${iconColor}; margin-right: 8px;"></i>${file.name}</span></td>
                            <td style="color: var(--success); font-family: monospace;">${file.processing_time || '-'}</td>
                            <td style="text-align: center;">
                                <a href="/api/download/${file.name}" download class="btn-primary" style="padding: 6px 12px; font-size: 12px; display: inline-block;"><i class="fa-solid fa-download"></i></a>
                            </td>
                        `;
                        tbody.appendChild(tr);
                    });
                }
            }
        } catch (e) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #ef4444;">Lỗi tải dữ liệu.</td></tr>';
        }
    }

    // Global Log Polling
    setInterval(async () => {
        try {
            let logRes = await fetch('/api/logs');
            let logText = await logRes.text();
            
            // Update small log
            const logEl = document.getElementById('botLogs');
            if(logEl) {
                logEl.innerText = logText;
                logEl.scrollTop = logEl.scrollHeight;
            }
            
            // Update system log
            const sysLogEl = document.getElementById('systemLogs');
            if(sysLogEl) {
                const isScrolledToBottom = sysLogEl.scrollHeight - sysLogEl.clientHeight <= sysLogEl.scrollTop + 10;
                sysLogEl.innerText = logText;
                if (isScrolledToBottom) {
                    sysLogEl.scrollTop = sysLogEl.scrollHeight;
                }
            }
        } catch (e) {}
    }, 1500);
    
    // Character Counter
    rawText.addEventListener('input', () => {
        const len = rawText.value.length;
        charCount.textContent = `${len.toLocaleString()} / 100,000 ký tự`;
        if (len > 100000) {
            charCount.style.color = 'var(--danger)';
        } else {
            charCount.style.color = 'var(--text-muted)';
        }
    });

    // Drag and Drop Logic
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
    });

    dropZone.addEventListener('drop', handleDrop, false);
    dropZone.addEventListener('click', () => fileInput.click());
    
    let customFiles = [];

    fileInput.addEventListener('change', function() {
        handleFiles(this.files);
    });

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    }

    function handleFiles(files) {
        Array.from(files).forEach(file => {
            if (file.name.endsWith('.txt')) {
                customFiles.push(file);
            } else {
                showToast("Chỉ hỗ trợ định dạng file .txt", true);
            }
        });
        renderFileList();
    }

    function renderFileList() {
        fileList.innerHTML = '';
        customFiles.forEach((file, index) => {
            const item = document.createElement('div');
            item.className = 'file-item';
            item.innerHTML = `
                <span><i class="fa-solid fa-file-lines"></i> ${file.name}</span>
                <button type="button" onclick="removeFile(${index})"><i class="fa-solid fa-xmark"></i></button>
            `;
            fileList.appendChild(item);
        });
    }

    window.removeFile = (index) => {
        customFiles.splice(index, 1);
        renderFileList();
    };

    // Form Submission
    translatorForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const gdocUrl = document.getElementById('gdocUrl').value.trim();
        const ytUrl = document.getElementById('ytUrl').value.trim();
        const rawTextValue = rawText.value.trim();
        
        if (!gdocUrl && !ytUrl && !rawTextValue && customFiles.length === 0) {
            showToast("Vui lòng cung cấp ít nhất một nội dung đầu vào!", true);
            return;
        }
        
        // Show loading state
        emptyState.style.display = 'none';
        resultState.style.display = 'none';
        loadingState.style.display = 'block';
        
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Sáng Tạo Ngữ...';
        
        const logEl = document.getElementById('botLogs');
        if (logEl) logEl.innerText = "Khởi tạo hệ thống...";

        const formData = new FormData();
        formData.append('profileName', document.getElementById('activeProfile') ? document.getElementById('activeProfile').value : 'gemini_profile');
                formData.append('sourceLang', document.getElementById('sourceLang').value);
        formData.append('targetLang', document.getElementById('targetLang').value);
        formData.append('promptId', promptSelect.value);
        formData.append('chunkSize', document.getElementById('chunkSize').value || 'auto');
        formData.append('customFilename', document.getElementById('customFilename').value.trim());
        formData.append('gdocUrl', document.getElementById('gdocUrl').value);
        formData.append('ytUrl', ytUrl);
        formData.append('rawText', rawTextValue);
        
        customFiles.forEach(file => {
            formData.append('files[]', file);
        });

        try {
            const response = await fetch('/api/translate/single', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            loadingState.style.display = 'none';
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Sáng Tạo Ngữ & Hoàn Thiện';
            
            if (response.ok && data.status === 'success') {
                resultState.style.display = 'block';
                previewOutput.value = data.preview;
                downloadBtn.href = `/api/download/${data.filename}`;
                downloadBtn.download = data.filename;
                
                if(data.processing_time) {
                    const timeNow = new Date().toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', year: 'numeric' });
                    document.getElementById('processingTimeInfo').innerHTML = `⏱️ <i>Hoàn thành lúc: ${timeNow} (Thời gian xử lý: ${data.processing_time} giây)</i>`;
                } else {
                    document.getElementById('processingTimeInfo').innerHTML = '';
                }
                
                loadMiniHistory();
                showToast("Sáng tạo ngữ hoàn tất thành công!");
            } else {
                emptyState.style.display = 'block';
                showToast(data.message || "Có lỗi xảy ra", true);
            }
        } catch (error) {
            loadingState.style.display = 'none';
            emptyState.style.display = 'block';
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Sáng Tạo Ngữ & Hoàn Thiện';
            showToast("Lỗi kết nối tới máy chủ", true);
        }
    });

    // Batch Mode Logic
    const batchForm = document.getElementById('batchForm');
    const batchDropZone = document.getElementById('batchDropZone');
    const batchFileInput = document.getElementById('batchFileInput');
    const batchFileList = document.getElementById('batchFileList');
    const batchSubmitBtn = document.getElementById('batchSubmitBtn');
    
    const batchLoadingState = document.getElementById('batchLoadingState');
    const batchResultState = document.getElementById('batchResultState');
    const batchEmptyState = document.getElementById('batchEmptyState');
    const batchDownloadBtn = document.getElementById('batchDownloadBtn');
    
    let batchCustomFiles = [];

    batchDropZone.addEventListener('click', () => batchFileInput.click());
    
    batchDropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        batchDropZone.style.borderColor = 'var(--primary)';
        batchDropZone.style.background = 'rgba(59, 130, 246, 0.1)';
    });
    
    batchDropZone.addEventListener('dragleave', () => {
        batchDropZone.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        batchDropZone.style.background = 'rgba(255, 255, 255, 0.03)';
    });
    
    batchDropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        batchDropZone.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        batchDropZone.style.background = 'rgba(255, 255, 255, 0.03)';
        
        if (e.dataTransfer.files.length) {
            handleBatchFiles(e.dataTransfer.files);
        }
    });
    
    batchFileInput.addEventListener('change', function() {
        if (this.files.length) {
            handleBatchFiles(this.files);
        }
    });

    function handleBatchFiles(files) {
        Array.from(files).forEach(file => {
            if (file.type === "text/plain" || file.name.endsWith(".txt")) {
                batchCustomFiles.push(file);
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                fileItem.innerHTML = `
                    <i class="fa-solid fa-file-lines"></i>
                    <span>${file.name}</span>
                    <i class="fa-solid fa-xmark remove-file" style="cursor: pointer;"></i>
                `;
                
                fileItem.querySelector('.remove-file').addEventListener('click', () => {
                    batchCustomFiles = batchCustomFiles.filter(f => f !== file);
                    fileItem.remove();
                });
                
                batchFileList.appendChild(fileItem);
            } else {
                showToast(`File ${file.name} không được hỗ trợ. Chỉ hỗ trợ .txt`, true);
            }
        });
    }

    batchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const batchLinks = document.getElementById('batchLinks').value.trim();
        
        if (!batchLinks && batchCustomFiles.length === 0) {
            showToast("Vui lòng cung cấp ít nhất một File hoặc một Link!", true);
            return;
        }

        // Chuyển Tab Nhật ký hệ thống tự động để user xem log
        document.querySelector('[data-tab="tab-logs"]').click();

        batchEmptyState.style.display = 'none';
        batchResultState.style.display = 'none';
        batchLoadingState.style.display = 'block';
        
        batchSubmitBtn.disabled = true;
        batchSubmitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Xử Lý Hàng Loạt...';

        const formData = new FormData();
        formData.append('profileName', document.getElementById('activeProfile') ? document.getElementById('activeProfile').value : 'gemini_profile');
                formData.append('sourceLang', document.getElementById('batchSourceLang').value);
        formData.append('targetLang', document.getElementById('batchTargetLang').value);
        formData.append('promptId', batchPromptSelect.value);
        formData.append('chunkSize', document.getElementById('batchChunkSize').value || 'auto');
        formData.append('batchLinks', document.getElementById('batchLinks').value);
        
        batchCustomFiles.forEach(file => {
            formData.append('files[]', file);
        });

        try {
            const response = await fetch('/api/translate_batch', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            batchLoadingState.style.display = 'none';
            batchSubmitBtn.disabled = false;
            batchSubmitBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Sáng Tạo Ngữ Hàng Loạt';
            
            // Quay lại tab Batch
            document.querySelector('[data-tab="tab-batch"]').click();
            
            if (response.ok && data.status === 'success') {
                batchResultState.style.display = 'block';
                batchDownloadBtn.href = `/api/download/${data.filename}`;
                showToast("Sáng tạo ngữ hàng loạt hoàn tất thành công!");
            } else {
                batchEmptyState.style.display = 'block';
                showToast(data.message || "Có lỗi xảy ra", true);
            }
        } catch (error) {
            batchLoadingState.style.display = 'none';
            batchEmptyState.style.display = 'block';
            batchSubmitBtn.disabled = false;
            batchSubmitBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Sáng Tạo Ngữ Hàng Loạt';
            showToast("Lỗi kết nối tới máy chủ", true);
        }
    });

    // Creative Logic
    const creativeForm = document.getElementById('creativeForm');
    const creativeDropZone = document.getElementById('creativeDropZone');
    const creativeFileInput = document.getElementById('creativeFileInput');
    const creativeFileList = document.getElementById('creativeFileList');
    
    const creativeSubmitBtn = document.getElementById('creativeSubmitBtn');
    const creativeEmptyState = document.getElementById('creativeEmptyState');
    const creativeLoadingState = document.getElementById('creativeLoadingState');
    const creativeResultState = document.getElementById('creativeResultState');
    const creativePreviewOutput = document.getElementById('creativePreviewOutput');
    const creativeDownloadBtn = document.getElementById('creativeDownloadBtn');

    let creativeCustomFiles = [];

    // Creative Drag and Drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        creativeDropZone.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        creativeDropZone.addEventListener(eventName, () => creativeDropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        creativeDropZone.addEventListener(eventName, () => creativeDropZone.classList.remove('dragover'), false);
    });

    creativeDropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        creativeDropZone.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        creativeDropZone.style.background = 'rgba(255, 255, 255, 0.03)';
        
        if (e.dataTransfer.files.length) {
            handleCreativeFiles(e.dataTransfer.files);
        }
    });
    
    creativeDropZone.addEventListener('click', () => creativeFileInput.click());

    creativeFileInput.addEventListener('change', function() {
        if (this.files.length) {
            handleCreativeFiles(this.files);
        }
    });

    function handleCreativeFiles(files) {
        Array.from(files).forEach(file => {
            if (file.type === "text/plain" || file.name.endsWith(".txt")) {
                creativeCustomFiles.push(file);
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                fileItem.innerHTML = `
                    <i class="fa-solid fa-file-lines"></i>
                    <span>${file.name}</span>
                    <i class="fa-solid fa-xmark remove-file" style="cursor: pointer;"></i>
                `;
                
                fileItem.querySelector('.remove-file').addEventListener('click', () => {
                    creativeCustomFiles = creativeCustomFiles.filter(f => f !== file);
                    fileItem.remove();
                });
                
                creativeFileList.appendChild(fileItem);
            } else {
                showToast(`File ${file.name} không được hỗ trợ. Chỉ hỗ trợ .txt`, true);
            }
        });
    }

    creativeForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const rawText = document.getElementById('creativeRawText').value.trim();
        const gdocUrl = document.getElementById('creativeGdocUrl').value.trim();
        const ytUrl = document.getElementById('creativeYtUrl').value.trim();
        
        const selectedPrompts = Array.from(document.querySelectorAll('input[name="creativePrompts"]:checked')).map(cb => cb.value);
        if (selectedPrompts.length === 0) {
            showToast("Vui lòng chọn ít nhất 1 Mẫu Prompt!", true);
            return;
        }
        
        if (!rawText && !gdocUrl && !ytUrl && creativeCustomFiles.length === 0) {
            showToast("Vui lòng cung cấp Dữ liệu văn bản, Link hoặc File đính kèm!", true);
            return;
        }

        // Chuyển Tab Nhật ký hệ thống tự động để user xem log
        document.querySelector('[data-tab="tab-logs"]').click();

        creativeEmptyState.style.display = 'none';
        creativeResultState.style.display = 'none';
        creativeLoadingState.style.display = 'block';
        
        creativeSubmitBtn.disabled = true;
        creativeSubmitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Phân Tích & Sáng Tạo...';

        const formData = new FormData();
        formData.append('profileName', document.getElementById('activeProfile') ? document.getElementById('activeProfile').value : 'gemini_profile');
                formData.append('sourceLang', document.getElementById('creativeSourceLang').value || 'auto');
        formData.append('targetLang', document.getElementById('creativeTargetLang').value || 'en');
        formData.append('chunkSize', document.getElementById('creativeChunkSize').value || 'auto');
        formData.append('detailLevel', document.getElementById('creativeDetailLevel').value || 'expand');
        formData.append('customFilename', document.getElementById('creativeFilename').value.trim());
        formData.append('gdocUrl', gdocUrl);
        formData.append('ytUrl', ytUrl);
        formData.append('rawText', rawText);
        formData.append('selectedPrompts', JSON.stringify(selectedPrompts));
        
        if (creativeCustomFiles.length > 0) {
            formData.append('file', creativeCustomFiles[0]);
        }

        try {
            const response = await fetch('/api/creative', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            creativeLoadingState.style.display = 'none';
            creativeSubmitBtn.disabled = false;
            creativeSubmitBtn.innerHTML = '<i class="fa-solid fa-bolt"></i> Bắt Đầu Sáng Tạo Bằng AI';
            
            // Quay lại tab Creative
            document.querySelector('[data-tab="tab-creative"]').click();
            
            if (response.ok && data.status === 'success') {
                creativeResultState.style.display = 'block';
                creativePreviewOutput.value = data.preview;
                creativeDownloadBtn.href = `/api/download/${data.filename}`;
                showToast("Quá trình sáng tạo hoàn tất xuất sắc!");
            } else {
                creativeEmptyState.style.display = 'block';
                showToast(data.message || "Có lỗi xảy ra", true);
            }
        } catch (error) {
            creativeLoadingState.style.display = 'none';
            creativeSubmitBtn.disabled = false;
            creativeSubmitBtn.innerHTML = '<i class="fa-solid fa-bolt"></i> Bắt Đầu Sáng Tạo Bằng AI';
            creativeEmptyState.style.display = 'block';
            showToast("Lỗi kết nối", true);
        }
    });
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            const activeProfile = document.getElementById('activeProfile').value;
            if (confirm(`Bạn có chắc muốn XÓA DỮ LIỆU ĐĂNG NHẬP của tài khoản '${activeProfile}' không? Bạn sẽ phải đăng nhập lại nếu muốn dùng tiếp.`)) {
                try {
                    const res = await fetch('/api/logout', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ profileName: activeProfile })
                    });
                    const result = await res.json();
                    showToast(result.message);
                    if(typeof loadProfiles === 'function') loadProfiles();
                } catch (e) { showToast("Lỗi kết nối", true); }
            }
        });
    }

    if(loginBtn) {
        loginBtn.addEventListener('click', async () => {
            let profileName = 'gemini_profile';
            
            const originalText = loginBtn.innerHTML;
            loginBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang mở Chrome...';
            loginBtn.disabled = true;
            
            showToast("Trình duyệt đang mở. Hãy đăng nhập tài khoản Google của bạn và TẮT HẲN CỬA SỔ khi xong!");
            
            try {
                const response = await fetch('/api/login', { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ profileName: profileName })
                });
                const result = await response.json();
                if(result.status === 'success') {
                    showToast(result.message);
                    if(typeof loadProfiles === 'function') loadProfiles();
                } else {
                    showToast(result.message, true);
                }
            } catch (e) {
                showToast("Lỗi kết nối", true);
            }
            
            loginBtn.innerHTML = originalText;
            loginBtn.disabled = false;
        });
    }

    // Toast logic
    const toast = document.getElementById('toast');
    let toastTimeout;
    function showToast(message, isError = false) {
        toast.textContent = message;
        toast.style.background = isError ? 'rgba(239, 68, 68, 0.9)' : 'rgba(16, 185, 129, 0.9)';
        toast.classList.add('show');
        
        clearTimeout(toastTimeout);
        toastTimeout = setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }
    
    async function loadMiniHistory() {
        try {
            const res = await fetch('/api/history');
            const data = await res.json();
            const list = document.getElementById('quickHistoryList');
            if(!list) return;
            
            list.innerHTML = '';
            if (data.status === 'success' && data.data && data.data.length > 0) {
                // limit to 10
                const files = data.data.slice(0, 10);
                files.forEach(file => {
                    const tr = document.createElement('tr');
                    
                    let isBatch = file.name.endsWith('.zip');
                    let badgeClass = isBatch ? 'dich-loat' : 'dich-don';
                    let badgeText = isBatch ? 'Sáng Tạo Ngữ Hàng Loạt' : 'Sáng Tạo Ngữ Đơn';
                    let iconColor = isBatch ? '#f59e0b' : '#3b82f6';
                    let iconClass = isBatch ? 'fa-file-zipper' : 'fa-file-lines';
                    
                    tr.innerHTML = `
                        <td style="color: #9ca3af; font-family: monospace;">${file.time.split(' ')[1]}</td>
                        <td><span class="badge-pill ${badgeClass}">${badgeText}</span></td>
                        <td><span class="text-ellipsis" style="max-width: 150px;"><i class="fa-solid ${iconClass}" style="color: ${iconColor}; margin-right: 5px;"></i>${file.name}</span></td>
                        <td style="color: var(--success); font-family: monospace;">${file.processing_time || '-'}</td>
                        <td style="text-align: center;">
                            <a href="/api/download/${file.name}" download class="btn-primary" style="padding: 4px 10px; font-size: 11px; display: inline-block;">
                                <i class="fa-solid fa-download"></i>
                            </a>
                        </td>
                    `;
                    list.appendChild(tr);
                });
            } else {
                list.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Chưa có dữ liệu lịch sử</td></tr>';
            }
        } catch(e) {
            console.error(e);
        }
    }
    
    // Load once on start
    loadMiniHistory();
});
