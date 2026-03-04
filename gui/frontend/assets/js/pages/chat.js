/**
 * Chat Page — Direct conversation with agent via GUI.
 */
const ChatPage = {
    async render(container) {
        container.innerHTML = `
            <div class="chat-container">
                <div class="chat-messages" id="chat-messages">
                    <!-- History and messages loaded here -->
                </div>
                <div class="chat-input-bar">
                    <button class="btn btn-icon" id="chat-attach-btn" title="Attach Image" style="padding: 0 8px; font-size: 16px; background: none; border: none; cursor: pointer; color: var(--text-secondary);"><i class="fas fa-paperclip"></i></button>
                    <button class="btn btn-icon" id="chat-voice-btn" title="Record Voice" style="padding: 0 8px; font-size: 16px; background: none; border: none; cursor: pointer; color: var(--text-secondary);"><i class="fas fa-microphone"></i></button>
                    <input type="file" id="chat-file-input" accept="image/*,audio/*,.pdf,.docx,.doc,.pptx,.xlsx,.xls,.csv,.ipynb,.txt,.md,.json,.jsonc,.json5,.yaml,.yml,.log,.py,.js,.mjs,.ts,.tsx,.jsx,.html,.css,.scss,.sass,.go,.rs,.cpp,.c,.h,.hpp,.java,.kt,.kts,.swift,.rb,.php,.lua,.dart,.sql,.sh,.bash,.bat,.ps1,.env,.ini,.toml,.conf,.xml,.props,.properties,.gitignore,.dockerfile" style="display:none">
                    <input type="text" id="chat-input" placeholder="Type your message..." autocomplete="off">
                    <button class="btn btn-primary" id="chat-send-btn">Send <i class="fas fa-paper-plane" style="margin-left:4px;"></i></button>
                </div>
                <!-- Media preview area -->
                <div id="chat-media-preview" style="display:none; padding: 10px; border-top: 1px solid var(--border); background: var(--bg-hover); align-items: center; justify-content: space-between;">
                   <div id="media-content" style="display:flex; align-items:center;"></div>
                   <button class="btn btn-small" id="chat-clear-media" style="padding: 4px 8px; font-size: 12px; background: transparent; color: var(--red); border: 1px solid var(--red);"><i class="fas fa-times"></i> Clear</button>
                </div>
            </div>
        `;

        const input = document.getElementById('chat-input');
        const btn = document.getElementById('chat-send-btn');
        const attachBtn = document.getElementById('chat-attach-btn');
        const voiceBtn = document.getElementById('chat-voice-btn');
        const fileInput = document.getElementById('chat-file-input');
        const mediaPreview = document.getElementById('chat-media-preview');
        const mediaContent = document.getElementById('media-content');
        const clearMediaBtn = document.getElementById('chat-clear-media');

        let currentImageB64 = null;
        let currentMimeType = null;
        let currentAudioB64 = null;
        let currentFileB64 = null;
        let currentFileName = null;

        let mediaRecorder = null;
        let audioChunks = [];
        let isRecording = false;

        const clearMedia = () => {
            currentImageB64 = null;
            currentAudioB64 = null;
            currentFileB64 = null;
            currentFileName = null;
            currentMimeType = null;
            mediaContent.innerHTML = '';
            mediaPreview.style.display = 'none';
        };

        clearMediaBtn.addEventListener('click', clearMedia);

        attachBtn.addEventListener('click', () => fileInput.click());

        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = (ev) => {
                const b64 = ev.target.result.split(',')[1];
                if (file.type.startsWith('image/')) {
                    currentImageB64 = b64;
                    mediaContent.innerHTML = `<img src="${ev.target.result}" style="max-height:80px; border-radius: 4px; border: 1px solid var(--border);">`;
                } else if (file.type.startsWith('audio/')) {
                    currentAudioB64 = b64;
                    mediaContent.innerHTML = `<audio controls src="${ev.target.result}" style="height:40px;"></audio>`;
                } else {
                    // Document file
                    currentFileB64 = b64;
                    currentFileName = file.name;
                    const ext = file.name.split('.').pop().toLowerCase();
                    const iconMap = { pdf: 'fa-file-pdf', doc: 'fa-file-word', docx: 'fa-file-word', xls: 'fa-file-excel', xlsx: 'fa-file-excel', csv: 'fa-file-csv', pptx: 'fa-file-powerpoint', py: 'fa-file-code', js: 'fa-file-code', ts: 'fa-file-code', html: 'fa-file-code', css: 'fa-file-code', json: 'fa-file-code', yaml: 'fa-file-code', yml: 'fa-file-code', md: 'fa-file-alt', txt: 'fa-file-alt', ipynb: 'fa-file-code' };
                    const icon = iconMap[ext] || 'fa-file';
                    mediaContent.innerHTML = `<div style="display:flex;align-items:center;gap:8px;"><i class="fas ${icon}" style="font-size:24px;color:var(--accent)"></i><span style="font-size:13px;color:var(--text-primary)">${file.name} <span style="color:var(--text-muted);font-size:11px">(${(file.size / 1024).toFixed(1)}KB)</span></span></div>`;
                }
                currentMimeType = file.type;
                mediaPreview.style.display = 'flex';
            };
            reader.readAsDataURL(file);
            fileInput.value = '';
        });

        voiceBtn.addEventListener('click', async () => {
            if (isRecording) {
                mediaRecorder.stop();
                isRecording = false;
                voiceBtn.innerHTML = '<i class="fas fa-microphone"></i>';
                voiceBtn.style.color = 'var(--text-secondary)';
                return;
            }
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                audioChunks = [];
                mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                mediaRecorder.onstop = () => {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    const reader = new FileReader();
                    reader.onload = (ev) => {
                        const b64 = ev.target.result.split(',')[1];
                        currentAudioB64 = b64;
                        currentMimeType = 'audio/webm';
                        mediaContent.innerHTML = `<audio controls src="${ev.target.result}" style="height:40px;"></audio>`;
                        mediaPreview.style.display = 'flex';
                    };
                    reader.readAsDataURL(audioBlob);
                    stream.getTracks().forEach(t => t.stop());
                };
                mediaRecorder.start();
                isRecording = true;
                voiceBtn.innerHTML = '<i class="fas fa-stop"></i>';
                voiceBtn.style.color = 'var(--red)';
            } catch (err) {
                console.error("Microphone access denied:", err);
            }
        });

        const sendMsg = () => {
            const msg = input.value.trim();
            if (!msg && !currentImageB64 && !currentAudioB64 && !currentFileB64) return;

            if (msg.length > 32000) {
                showToast('Message too long (max 32000 characters)', 'error');
                return;
            }

            UI.setLoading(btn, true);
            input.value = '';

            this._sendMessage(msg, currentImageB64, currentAudioB64, currentMimeType, currentFileB64, currentFileName)
                .finally(() => UI.setLoading(btn, false));
            clearMedia();
        };

        btn.addEventListener('click', sendMsg);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') sendMsg();
        });
        input.focus();
    },

    async init() {
        await this._loadHistory();
    },

    async _loadHistory() {
        const messagesContainer = document.getElementById('chat-messages');
        if (!messagesContainer) return;

        try {
            const data = await API.get('/chat/history');
            if (data && data.messages && data.messages.length > 0) {
                messagesContainer.innerHTML = ''; // Clear loading/placeholder
                data.messages.forEach(msg => {
                    const role = (msg.role === 'human' || msg.role === 'user') ? 'user' : 'agent';
                    const content = msg.content || msg.message || '';
                    if (content) {
                        const metaStr = (msg.metadata && msg.metadata.decision) ? `Final Decision: ${msg.metadata.decision}` : '';
                        this._addBubble(content, role, metaStr, msg.metadata);
                    }
                });
            } else {
                // If no history, show greeting
                messagesContainer.innerHTML = `
                    <div class="chat-bubble agent">
                        <div>👋 Hello! I'm ready to chat. Type a message below to begin.</div>
                        <div class="bubble-meta">System</div>
                    </div>
                `;
            }
        } catch (e) {
            console.error("Failed to load history:", e);
        }
    },

    _addBubble(text, type = 'user', meta = '', rawMeta = null, isRawHtml = false) {
        const messages = document.getElementById('chat-messages');
        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${type}`;

        // If text is present (including transcript from voice), render it.
        // We no longer hide text for voice messages as it's now the primary content.

        const renderedText = isRawHtml ? text : this._renderMarkdown(text);
        let innerHTML = `<div>${renderedText}</div>`;

        // Render document file attachment badge
        if (rawMeta && rawMeta.file_name) {
            const ext = rawMeta.file_name.split('.').pop().toLowerCase();
            const iconMap = { pdf: 'fa-file-pdf', doc: 'fa-file-word', docx: 'fa-file-word', xls: 'fa-file-excel', xlsx: 'fa-file-excel', csv: 'fa-file-csv', pptx: 'fa-file-powerpoint', py: 'fa-file-code', js: 'fa-file-code', ts: 'fa-file-code', html: 'fa-file-code', css: 'fa-file-code', json: 'fa-file-code', yaml: 'fa-file-code', yml: 'fa-file-code', md: 'fa-file-alt', txt: 'fa-file-alt', ipynb: 'fa-file-code' };
            const icon = iconMap[ext] || 'fa-file';
            const fileUrl = rawMeta.file_url;
            const nameHtml = fileUrl
                ? `<a href="${fileUrl}" target="_blank" style="color:var(--accent);text-decoration:none">${rawMeta.file_name}</a>`
                : rawMeta.file_name;
            innerHTML += `
                <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;margin-top:6px;border-radius:8px;background:rgba(108,92,231,0.1);border:1px solid rgba(108,92,231,0.2)">
                    <i class="fas ${icon}" style="font-size:20px;color:var(--accent)"></i>
                    <span style="font-size:13px;color:var(--text-primary)">${nameHtml}</span>
                </div>
            `;
        }
        if (rawMeta && (rawMeta.photo || rawMeta.image_base64 || rawMeta.image_url)) {
            const imgSrc = rawMeta.image_url || rawMeta.photo || `data:${rawMeta.mime_type || 'image/png'};base64,${rawMeta.image_base64}`;
            innerHTML += `
                <div class="chat-image-container">
                    <img src="${imgSrc}" onclick="window.open('${imgSrc}', '_blank')">
                </div>
            `;
        }

        // Render Audio if present (Voice messages — URL from history or base64 from live)
        if (rawMeta && (rawMeta.audio_base64 || rawMeta.audio_url)) {
            const audioId = `audio-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
            const audioSrc = rawMeta.audio_url || `data:${rawMeta.mime_type || 'audio/webm'};base64,${rawMeta.audio_base64}`;

            // Generate some random waveform bars for visual effect (Messenger style)
            let waveformHtml = '';
            for (let i = 0; i < 35; i++) {
                const height = Math.random() * 80 + 20; // 20% to 100% height
                waveformHtml += `<div class="waveform-bar" style="height: ${height}%;"></div>`;
            }

            innerHTML += `
                <div class="custom-audio-player" id="player-${audioId}">
                    <button class="audio-play-btn" onclick="ChatPage.toggleAudio('${audioId}')">
                        <i class="fas fa-play audio-icon" id="icon-${audioId}" style="margin-left: 2px;"></i>
                    </button>
                    <div class="audio-waveform" id="waveform-${audioId}">
                        ${waveformHtml}
                    </div>
                    <div class="audio-time" id="time-${audioId}">...</div>
                    <audio id="${audioId}" src="${audioSrc}" preload="metadata"
                           ontimeupdate="ChatPage.updateAudioProgress('${audioId}')"
                           onloadedmetadata="ChatPage.setAudioDuration('${audioId}')"
                           ondurationchange="ChatPage.setAudioDuration('${audioId}')"
                           onended="ChatPage.audioEnded('${audioId}')" style="display:none;"></audio>
                </div>
            `;
        }

        if (type === 'agent' && rawMeta) {
            innerHTML += this._renderThinkingCard(rawMeta);
            if (rawMeta.action === 'WAIT_FOR_APPROVAL' || rawMeta.requires_approval) {
                innerHTML += this._renderApprovalCard(rawMeta);
            }
        }

        if (meta) {
            innerHTML += `<div class="bubble-meta">${meta}</div>`;
        }

        bubble.innerHTML = innerHTML;
        messages.appendChild(bubble);
        messages.scrollTop = messages.scrollHeight;

        // Add toggle listeners for thinking cards
        const toggles = bubble.querySelectorAll('.thinking-header');
        toggles.forEach(t => {
            t.addEventListener('click', (e) => {
                const card = e.currentTarget.closest('.thinking-card');
                const body = card.querySelector('.thinking-body');
                const icon = e.currentTarget.querySelector('.toggle-icon');
                if (body.style.display === 'none') {
                    body.style.display = 'block';
                    icon.innerHTML = '<i class="fas fa-chevron-down"></i>';
                } else {
                    body.style.display = 'none';
                    icon.innerHTML = '<i class="fas fa-chevron-right"></i>';
                }
            });
        });

        // Approval listeners
        bubble.querySelectorAll('.btn-approve').forEach(b => {
            b.addEventListener('click', () => this._handleApproval(b.dataset.id, 'approve', b));
        });
        bubble.querySelectorAll('.btn-deny').forEach(b => {
            b.addEventListener('click', () => this._handleApproval(b.dataset.id, 'deny', b));
        });

        return bubble;
    },

    _renderDataTable(data) {
        if (!Array.isArray(data) || data.length === 0) return '';
        const keys = Object.keys(data[0]);
        let html = `<div style="overflow-x:auto; margin-top:4px;"><table style="width:100%; border-collapse:collapse; font-size:11px;">`;

        // Header
        html += `<thead style="background:rgba(255,255,255,0.05);"><tr>`;
        keys.forEach(k => html += `<th style="padding:6px; text-align:left; border:1px solid rgba(255,255,255,0.1); color:var(--text-secondary);">${this._escapeHtml(k)}</th>`);
        html += `</tr></thead><tbody>`;

        // Rows
        data.forEach(row => {
            html += `<tr>`;
            keys.forEach(k => {
                const val = row[k];
                const displayVal = typeof val === 'object' ? JSON.stringify(val) : String(val);
                html += `<td style="padding:6px; border:1px solid rgba(255,255,255,0.1); color:var(--text-primary);">${this._escapeHtml(displayVal)}</td>`;
            });
            html += `</tr>`;
        });

        html += `</tbody></table></div>`;
        return html;
    },

    _renderMarkdown(text) {
        if (!text) return '';
        // Basic Markdown parser
        let html = text
            // Escape HTML first to prevent XSS but keep some safety
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // Code blocks: ```code```
        html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');

        // Inline code: `code`
        html = html.replace(/`([^`]+)`/g, '<span class="md-code">$1</span>');

        // Bold: **text**
        html = html.replace(/\*\*(.*?)\*\*/g, '<span class="md-bold">$1</span>');

        // Italic: *text*
        html = html.replace(/\*((?!\*).*?)\*/g, '<em style="color:var(--text-secondary);">$1</em>');

        // Paragraphs: Split by double newline and wrap in <p>
        const blocks = html.split('\n\n');
        html = blocks.map(block => {
            const trimmed = block.trim();
            if (!trimmed) return '';
            // If it's a code block (pre), don't wrap in p
            if (trimmed.startsWith('<pre>')) return trimmed;
            // Handle single newlines within paragraph as <br/>
            return `<p>${trimmed.replace(/\n/g, '<br/>')}</p>`;
        }).join('');

        return html;
    },

    _renderThinkingCard(meta) {
        if (!meta.thoughts && !meta.tools_used && !meta.logic && !meta.plan) return '';

        let contentHtml = '';

        if (meta.thoughts && meta.thoughts.length > 0) {
            contentHtml += `<div class="think-section"><span class="think-label">System Thoughts</span><ul style="padding-left:18px;">`;
            meta.thoughts.forEach(t => contentHtml += `<li>${this._escapeHtml(t)}</li>`);
            contentHtml += `</ul></div>`;
        }

        if (meta.plan && meta.plan.length > 0) {
            contentHtml += `<div class="think-section"><span class="think-label">Plan of Action</span><ol style="padding-left:18px;">`;
            meta.plan.forEach(p => {
                let stepText = '';
                if (typeof p === 'string') {
                    stepText = p;
                } else if (p && typeof p === 'object') {
                    stepText = p.thought || p.task || p.name || JSON.stringify(p);
                }
                contentHtml += `<li>${this._escapeHtml(stepText)}</li>`;
            });
            contentHtml += `</ol></div>`;
        }

        if (meta.task_outputs && meta.task_outputs.length > 0) {
            contentHtml += `<div class="think-section"><span class="think-label">Data Collected</span><div style="margin-top:4px; max-height:300px; overflow-y:auto; font-size:12px; font-family:monospace; background:rgba(0,0,0,0.3); border:1px solid var(--border); border-radius:8px; padding:0;">`;
            meta.task_outputs.forEach((out, i) => {
                const toolName = out.tool || 'Tool Result';
                const result = out.result || out.output || out;

                contentHtml += `<div style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.05);">
                    <div style="color:var(--accent); font-weight:600; margin-bottom:6px; display:flex; align-items:center; gap:6px;">
                        <span style="background:var(--accent); color:#000; padding:1px 6px; border-radius:4px; font-size:10px;">STEP ${i + 1}</span> 
                        ${this._escapeHtml(toolName)}
                    </div>`;

                if (Array.isArray(result) && result.length > 0 && typeof result[0] === 'object') {
                    contentHtml += this._renderDataTable(result);
                } else {
                    const resultStr = typeof result === 'object' ? JSON.stringify(result, null, 2) : String(result);
                    contentHtml += `<pre style="white-space:pre-wrap; color:var(--text-primary); margin:0; padding:4px;">${this._escapeHtml(resultStr)}</pre>`;
                }
                contentHtml += `</div>`;
            });
            contentHtml += `</div></div>`;
        }

        if (meta.tools_used && meta.tools_used.length > 0) {
            contentHtml += `<div class="think-section"><span class="think-label">Tools Activated</span><div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:4px;">`;
            meta.tools_used.forEach(t => {
                const name = typeof t === 'string' ? t : (t.name || 'tool');
                contentHtml += `<span class="badge badge-accent" style="font-family:monospace; font-size:11px;">${this._escapeHtml(name)}</span>`;
            });
            contentHtml += `</div></div>`;
        }

        if (meta.logic) {
            contentHtml += `<div class="think-section"><span class="think-label">Agent Logic</span><div style="font-style:italic;">${this._escapeHtml(meta.logic)}</div></div>`;
        }

        if (!contentHtml) return '';

        return `
            <div class="thinking-card">
                <div class="thinking-header">
                    <span class="toggle-icon"><i class="fas fa-chevron-right"></i></span> Thought Process
                </div>
                <div class="thinking-body" style="display:none;">
                    ${contentHtml}
                </div>
            </div>
        `;
    },

    _createThinkingShell() {
        return `
            <div class="thinking-shell">
                <div class="thinking-shell-header">
                    <div class="spinner" style="width:16px;height:16px;border-width:2px;margin-right:10px;"></div>
                    <span class="thinking-status">Analyzing mission parameters...</span>
                </div>
                <div class="thinking-progress-bar">
                    <div class="thinking-progress-fill"></div>
                </div>
                <ul class="thinking-steps">
                </ul>
            </div>
        `;
    },

    _startSimulatedThinking(bubbleId) {
        const bubble = document.getElementById(bubbleId);
        if (!bubble) return;

        const progressFill = bubble.querySelector('.thinking-progress-fill');

        // Only run the progress bar animation continuously 
        let p = 0;
        this._thinkingTimers = this._thinkingTimers || {};
        this._thinkingTimers[bubbleId] = setInterval(() => {
            if (progressFill) {
                p = Math.min(p + (100 - p) * 0.05, 99);
                progressFill.style.width = p + '%';
            }
        }, 800);
    },

    _stopSimulatedThinking(bubbleId) {
        if (this._thinkingTimers && this._thinkingTimers[bubbleId]) {
            clearInterval(this._thinkingTimers[bubbleId]);
            delete this._thinkingTimers[bubbleId];
        }
    },

    _handleStreamEvent(event, bubbleId) {
        const bubble = document.getElementById(bubbleId);
        if (!bubble) return;

        const statusText = bubble.querySelector('.thinking-status');
        const stepsContainer = bubble.querySelector('.thinking-steps');

        if (event.type === 'start') {
            if (statusText) statusText.innerText = 'Initializing cognitive cycle...';
            if (stepsContainer) stepsContainer.innerHTML = '';
        } else if (event.type === 'thought') {
            if (statusText) statusText.innerText = 'Synthesizing knowledge...';
            if (stepsContainer) {
                const li = document.createElement('li');
                li.className = 'step-active';
                // Mark previous steps as done
                stepsContainer.querySelectorAll('li').forEach(el => {
                    el.className = 'step-done';
                });
                li.innerText = event.content.substring(0, 100) + (event.content.length > 100 ? '...' : '');
                stepsContainer.appendChild(li);
                // Scroll to bottom of steps if needed
                stepsContainer.scrollTop = stepsContainer.scrollHeight;
            }
        } else if (event.type === 'plan') {
            if (statusText) statusText.innerText = 'Executing task plan...';
        } else if (event.type === 'tool_start') {
            if (statusText) statusText.innerText = `Running: ${event.task.task || event.task.name || 'Tool'} (${event.step + 1}/${event.total})`;
            if (stepsContainer) {
                const li = document.createElement('li');
                li.className = 'step-active';
                stepsContainer.querySelectorAll('li').forEach(el => el.className = 'step-done');
                li.innerHTML = `<i class="fas fa-cog" style="margin-right:4px"></i> ${this._escapeHtml(event.task.task || event.task.name || 'Executing action')}`;
                stepsContainer.appendChild(li);
            }
        } else if (event.type === 'tool_end') {
            if (statusText) statusText.innerText = 'Analyzing tool output...';
        } else if (event.type === 'generating_response') {
            if (statusText) statusText.innerText = 'Finalizing neural output...';
            if (stepsContainer) {
                const li = document.createElement('li');
                li.className = 'step-active';
                stepsContainer.querySelectorAll('li').forEach(el => el.className = 'step-done');
                li.innerHTML = '<i class=\"fas fa-robot\" style=\"margin-right:4px\"></i> Drafting response to user';
                stepsContainer.appendChild(li);
            }
        }
    },

    _renderApprovalCard(meta) {
        const approvalId = meta.approval_id || 'pending';
        return `
            <div class="approval-card">
                <div style="font-weight:600; font-size:13px; color:var(--orange); display:flex; align-items:center; gap:6px; margin-bottom:8px;">
                    <i class="fas fa-exclamation-triangle" style="margin-right:4px"></i> Approval Required
                </div>
                <div style="font-size:13px; color:var(--text-secondary); margin-bottom:12px;">
                    The agent is requesting permission to perform a sensitive action.
                </div>
                <div class="approval-actions">
                    <button class="btn btn-approve" data-id="${approvalId}">Approve</button>
                    <button class="btn btn-deny" data-id="${approvalId}">Deny</button>
                </div>
            </div>
        `;
    },

    async _handleApproval(id, action, btn) {
        UI.setLoading(btn, true);
        const container = btn.closest('.approval-actions');

        try {
            const response = await API.post('/chat/approve', {
                id: id,
                action: action
            });

            if (response.error) {
                container.innerHTML = `<span style="color:var(--red); font-size:12px;">Failed: ${response.error}</span>`;
            } else {
                container.innerHTML = `<span style="color:var(--green); font-size:12px;">✓ ${action === 'approve' ? 'Approved' : 'Denied'}</span>`;
                // Optionally add a snackbar or message
                if (response.message) {
                    this._addBubble(response.message, 'agent', 'System Notification');
                }
            }
        } catch (e) {
            container.innerHTML = `<span style="color:var(--red); font-size:12px;">Network error</span>`;
        }
    },


    async _sendMessage(text, imageB64 = null, audioB64 = null, mimeType = null, fileB64 = null, fileName = null) {
        // Prepare metadata for rendering
        const meta = {
            image_base64: imageB64,
            audio_base64: audioB64,
            mime_type: mimeType,
            file_name: fileName
        };

        // If it's a media message without text, we show a clean preview.
        // If there's text, we show it first.
        let displayHtml = text ? this._escapeHtml(text) : '';
        if (!text) {
            if (audioB64) displayHtml = '';
            else if (imageB64) displayHtml = '<i><i class="fas fa-image" style="margin-right:6px;"></i>Attached Image</i>';
            else if (fileB64) displayHtml = `<i><i class="fas fa-file" style="margin-right:6px;"></i>${fileName || 'Attached File'}</i>`;
        }

        // Add local bubble immediately
        this._addBubble(displayHtml, 'user', '', meta, true);

        // Show dynamic thinking shell
        const thinkingShell = this._createThinkingShell();
        const bubble = this._addBubble(thinkingShell, 'agent', 'System', null, true);
        const bubbleId = 'thinking-' + Date.now();
        bubble.id = bubbleId;

        this._startSimulatedThinking(bubbleId);

        const payload = {
            message: text,
            image_base64: imageB64,
            audio_base64: audioB64,
            mime_type: mimeType,
            file_base64: fileB64,
            file_name: fileName
        };

        try {
            const response = await fetch('/api/chat/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                let lines = buffer.split("\n\n");
                buffer = lines.pop(); // keep the incomplete remainder in the buffer

                for (let line of lines) {
                    if (line.startsWith("data: ")) {
                        const dataStr = line.substring(6);
                        try {
                            const event = JSON.parse(dataStr);

                            if (event.type === "final_response") {
                                // Processing finished
                                this._stopSimulatedThinking(bubbleId);
                                const shellBubble = document.getElementById(bubbleId);
                                if (shellBubble) shellBubble.remove();

                                const result = event.data;
                                const metaStr = result.decision ? `Final Decision: ${result.decision}` : '';
                                // result contains text, photo, etc.
                                this._addBubble(result.text, 'agent', metaStr, result);

                            } else if (event.type === "error") {
                                this._stopSimulatedThinking(bubbleId);
                                const shellBubble = document.getElementById(bubbleId);
                                if (shellBubble) shellBubble.remove();

                                this._addBubble(`Error: ${event.message}`, 'agent', 'System Error');
                            } else {
                                // Dynamic UI update
                                this._handleStreamEvent(event, bubbleId);
                            }
                        } catch (e) {
                            console.error("Parse error for chunk:", dataStr, e);
                        }
                    }
                }
            }

        } catch (e) {
            console.error("Chat Error:", e);
            this._stopSimulatedThinking(bubbleId);
            const shellBubble = document.getElementById(bubbleId);
            if (shellBubble) shellBubble.remove();
            this._addBubble("I encountered a problem while processing your request. Please check the server logs.", 'agent', 'Connection Error');
        }
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    _formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) return "0:00";
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    },

    toggleAudio(audioId) {
        const audio = document.getElementById(audioId);
        const icon = document.getElementById(`icon-${audioId}`);
        if (!audio || !icon) return;

        if (audio.paused) {
            audio.play();
            icon.classList.remove('fa-play');
            icon.classList.add('fa-pause');
            icon.style.marginLeft = '0';
        } else {
            audio.pause();
            icon.classList.remove('fa-pause');
            icon.classList.add('fa-play');
            icon.style.marginLeft = '2px';
        }
    },

    updateAudioProgress(audioId) {
        const audio = document.getElementById(audioId);
        const timeDisplay = document.getElementById(`time-${audioId}`);
        if (!audio || !timeDisplay) return;

        let percent = 0;
        if (isFinite(audio.duration) && audio.duration > 0) {
            percent = (audio.currentTime / audio.duration);
            timeDisplay.textContent = this._formatTime(audio.currentTime);
        }

        const waveform = document.getElementById(`waveform-${audioId}`);
        if (waveform) {
            const bars = waveform.querySelectorAll('.waveform-bar');
            const activeCount = Math.floor(percent * bars.length);
            bars.forEach((bar, i) => {
                if (i <= activeCount) {
                    bar.classList.add('active');
                } else {
                    bar.classList.remove('active');
                }
            });
        }
    },

    setAudioDuration(audioId) {
        const audio = document.getElementById(audioId);
        const timeDisplay = document.getElementById(`time-${audioId}`);
        if (!audio || !timeDisplay) return;

        // Show total duration initially
        if (isFinite(audio.duration) && audio.duration > 0) {
            timeDisplay.textContent = this._formatTime(audio.duration);
        }
    },

    audioEnded(audioId) {
        const audio = document.getElementById(audioId);
        const icon = document.getElementById(`icon-${audioId}`);
        const timeDisplay = document.getElementById(`time-${audioId}`);
        if (!audio || !icon || !timeDisplay) return;

        icon.classList.remove('fa-pause');
        icon.classList.add('fa-play');
        icon.style.marginLeft = '2px';

        const waveform = document.getElementById(`waveform-${audioId}`);
        if (waveform) {
            waveform.querySelectorAll('.waveform-bar').forEach(b => b.classList.remove('active'));
        }

        if (isFinite(audio.duration) && audio.duration > 0) {
            timeDisplay.textContent = this._formatTime(audio.duration);
        } else {
            timeDisplay.textContent = "0:00";
        }
    }
};
