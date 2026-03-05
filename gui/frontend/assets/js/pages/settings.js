/**
 * Settings Page — Edit agent configuration from encrypted secure_config.
 */
const SettingsPage = {
    async render(container) {
        container.innerHTML = `
            <div class="section-header">
                <h3 class="section-title">Agent Configuration</h3>
                <div style="display:flex;gap:8px">
                    <span class="badge badge-green" style="align-self:center"><i class="fas fa-lock" style="margin-right:4px"></i> Encrypted Storage</span>
                    <button class="btn btn-primary" id="save-settings-btn" disabled><i class="fas fa-save" style="margin-right:4px"></i> Save Changes</button>
                </div>
            </div>
            <div id="settings-form">
                <div class="loading-screen"><div class="spinner"></div></div>
            </div>
        `;

        const data = await API.get('/settings');
        if (data.error) { container.innerHTML = `<p>Error: ${data.error}</p>`; return; }
        this._renderForm(data.settings);
    },

    _renderForm(settings) {
        const groups = {
            'Database': ['database_url'],
            'Identity': ['bot_name', 'user_pronoun', 'bot_pronoun', 'avatar_model_url'],
            'General LLM Settings': ['llm_provider'],
            'Ollama (Local)': ['ollama_base_url', 'ollama_model_name', 'ollama_vision_model_name'],
            'OpenAI': ['openai_model_name', 'openai_api_base'],
            'Anthropic': ['anthropic_model_name'],
            'DeepSeek': ['deepseek_model_name'],
            'Claude Web': ['claude_web_model_name', 'claude_web_endpoint', 'claude_web_timeout_seconds', 'claude_web_port'],
            'Model Parameters': ['model_temperature', 'model_max_tokens', 'model_context_size', 'model_threads', 'model_parallelism'],
            'Agent Behavior': ['scan_interval_minutes', 'rolling_window_hours', 'max_actions_per_hour', 'action_cooldown_minutes', 'failure_streak_threshold', 'human_approval_required'],
            'Context Limits': ['user_language', 'context_planning_limit', 'context_generation_limit'],
            'Telegram': ['telegram_bot_token', 'telegram_chat_id', 'telegram_polling_timeout'],
            'API Keys': ['openai_api_key', 'anthropic_api_key', 'deepseek_api_key', 'tavily_api_key', 'resend_api_key'],
            'External Services': ['resend_from_email'],
            'Audio': ['whisper_model_size'],
            'System Ports': ['dashboard_port'],
            'Cloudinary': ['cloudinary_cloud_name', 'cloudinary_api_key', 'cloudinary_api_secret'],
        };

        const form = document.getElementById('settings-form');
        let html = '';

        for (const [group, fields] of Object.entries(groups)) {
            const visibleFields = fields.filter(f => settings.hasOwnProperty(f));
            if (!visibleFields.length) continue;

            html += `<div class="card" style="margin-bottom:20px">
                <div class="card-title">${group}</div>
                <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px">`;

            for (const field of visibleFields) {
                const entry = settings[field];
                const isMasked = entry?.masked === true;
                const value = isMasked ? '' : (entry?.value ?? '');
                const placeholder = isMasked ? (entry?.value || 'Not configured') : '';
                const label = field.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

                if (typeof value === 'boolean') {
                    html += `<div class="form-group">
                        <label class="form-label">${label}</label>
                        <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
                            <input type="checkbox" class="settings-field" data-field="${field}" data-original="${value}" ${value ? 'checked' : ''} style="width:18px;height:18px;accent-color:var(--accent)">
                            <span style="font-size:13px;color:var(--text-secondary)">${value ? 'Enabled' : 'Disabled'}</span>
                        </label>
                    </div>`;
                } else {
                    const inputType = isMasked ? 'password' :
                        (typeof value === 'number' ? 'number' : 'text');
                    html += `<div class="form-group">
                        <label class="form-label">${label}${isMasked ? ' <i class="fas fa-lock" style="font-size:11px;color:var(--text-muted)"></i>' : ''}</label>
                        <input class="form-input settings-field" type="${inputType}"
                               data-field="${field}" data-original="${this._escapeHtml(String(value))}" value="${this._escapeHtml(String(value))}"
                               placeholder="${placeholder}" ${inputType === 'number' ? 'step="any"' : ''}>
                    </div>`;
                }
            }

            html += '</div></div>';
        }

        // Show remaining ungrouped fields
        const allGrouped = Object.values(groups).flat();
        const ungrouped = Object.keys(settings).filter(k => !allGrouped.includes(k));
        if (ungrouped.length) {
            html += `<div class="card" style="margin-bottom:20px">
                <div class="card-title">Other</div>
                <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px">`;
            for (const field of ungrouped) {
                const entry = settings[field];
                const isMasked = entry?.masked === true;
                const value = isMasked ? '' : (entry?.value ?? '');
                const label = field.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                html += `<div class="form-group">
                    <label class="form-label">${label}${isMasked ? ' 🔒' : ''}</label>
                    <input class="form-input settings-field" type="${isMasked ? 'password' : 'text'}"
                           data-field="${field}" data-original="${this._escapeHtml(String(value))}" value="${this._escapeHtml(String(value))}"
                           placeholder="${isMasked ? entry?.value : ''}">
                </div>`;
            }
            html += '</div></div>';
        }

        form.innerHTML = html;

        // Enable save button on change
        const btn = document.getElementById('save-settings-btn');
        form.addEventListener('input', () => { btn.disabled = false; });
        btn.addEventListener('click', () => this._save());
    },

    async _save() {
        const fields = document.querySelectorAll('.settings-field');
        const updates = {};
        let hasError = false;
        let hasChanges = false;

        const rules = {
            'model_temperature': { min: 0, max: 2, name: 'Temperature' },
            'model_max_tokens': { min: 1, name: 'Max Tokens' },
            'model_context_size': { min: 1, name: 'Context Size' },
            'dashboard_port': { min: 1, max: 65535, name: 'Dashboard Port' },
            'claude_web_port': { min: 1, max: 65535, name: 'Claude Web Port' },
            'ollama_base_url': { isURL: true, name: 'Ollama URL' },
            'openai_api_base': { isURL: true, name: 'OpenAI API Base' },
            'claude_web_endpoint': { isURL: true, name: 'Claude Web Endpoint' }
        };

        fields.forEach(f => {
            const key = f.dataset.field;
            UI.clearError(f);

            let val = f.type === 'checkbox' ? f.checked :
                f.type === 'number' ? Number(f.value) : f.value;

            const originalVal = f.dataset.original;

            // Skip unchanged fields
            if (f.type === 'checkbox') {
                if (String(val) === originalVal) return;
            } else {
                if (f.value === originalVal) return;
            }

            // Password fields are only 'changed' if they have a non-empty value
            if (f.type === 'password' && !f.value) return;

            hasChanges = true;

            // Apply rule-based validation only on changed fields
            const rule = rules[key];
            if (rule) {
                const isEmpty = val === '' || val === null;
                const numVal = Number(val);

                if (rule.min !== undefined && !isEmpty && numVal < rule.min) {
                    UI.showError(f, `${rule.name} must be at least ${rule.min}`);
                    hasError = true;
                }
                if (rule.max !== undefined && !isEmpty && numVal > rule.max) {
                    UI.showError(f, `${rule.name} must be at most ${rule.max}`);
                    hasError = true;
                }
                if (rule.isURL && val && !Validator.isURL(val)) {
                    UI.showError(f, `Invalid URL format for ${rule.name}`);
                    hasError = true;
                }
            }

            updates[key] = val;
        });

        if (hasError) {
            showToast('Please fix the highlighted errors before saving.', 'error');
            return;
        }

        const btn = document.getElementById('save-settings-btn');

        if (!hasChanges) {
            showToast('No changes to save.');
            btn.disabled = true;
            return;
        }

        // Show loading effect immediately
        const originalHtml = btn.innerHTML;
        UI.setLoading(btn, true);
        btn.innerHTML = '<i class="fas fa-circle-notch fa-spin" style="margin-right:4px"></i> Saving...';

        try {
            const result = await API.post('/settings', { updates });
            if (result.status === 'success') {
                showToast(`<i class="fas fa-lock"></i> Saved ${result.updated.length} settings to ${result.storage}`, 'success');
                btn.disabled = true; // Keep disabled because changes are now saved
                btn.innerHTML = '<i class="fas fa-check" style="margin-right:4px"></i> Saved';

                // Update original values so we don't think they're modified anymore
                fields.forEach(f => {
                    const key = f.dataset.field;
                    if (updates[key] !== undefined) {
                        if (f.type === 'checkbox') f.dataset.original = String(f.checked);
                        else f.dataset.original = f.value;
                    }
                });

                // Reset button text after 2 seconds
                setTimeout(() => {
                    btn.innerHTML = originalHtml;
                }, 2000);
            } else {
                showToast(`<i class="fas fa-times-circle"></i> ${result.error || 'Save failed'}`, 'error');
                btn.disabled = false;
                btn.innerHTML = originalHtml;
            }
        } catch (e) {
            showToast(`<i class="fas fa-times-circle"></i> Error saving settings`, 'error');
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        } finally {
            UI.setLoading(btn, false);
            // Re-apply disabled state if it was successful (setLoading false removes disabled)
            if (btn.innerHTML.includes('Saved') && !btn.innerHTML.includes('fa-spin')) {
                btn.disabled = true;
            }
        }
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};
