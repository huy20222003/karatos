/**
 * Credentials Page — Manage encrypted VAULT entries.
 */
const CredentialsPage = {
    async render(container) {
        container.innerHTML = `
            <div class="section-header">
                <h3 class="section-title">Credential Vault</h3>
                <button class="btn btn-primary" id="add-cred-btn"><i class="fas fa-key" style="margin-right:4px"></i> Add Credential</button>
            </div>

            <!-- Add Form (hidden by default) -->
            <div class="card" id="cred-form" style="display:none;margin-bottom:20px">
                <div class="card-title">New Credential</div>
                <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px">
                    <div class="form-group">
                        <label class="form-label">Name</label>
                        <input class="form-input" id="cred-name" placeholder="e.g., github_pat">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Service</label>
                        <input class="form-input" id="cred-service" placeholder="e.g., GitHub">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Token / API Key</label>
                        <input class="form-input" id="cred-token" type="password" placeholder="Paste your token here">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Notes (optional)</label>
                        <input class="form-input" id="cred-notes" placeholder="e.g., expires 2026-12-31">
                    </div>
                </div>
                <div style="display:flex;gap:8px;margin-top:12px">
                    <button class="btn btn-primary" id="save-cred-btn"><i class="fas fa-save" style="margin-right:4px"></i> Encrypt & Save</button>
                    <button class="btn btn-ghost" id="cancel-cred-btn">Cancel</button>
                </div>
            </div>

            <!-- Credentials List -->
            <div class="card">
                <div class="table-container">
                    <table>
                        <thead><tr><th>Name</th><th>Service</th><th>Notes</th><th>Created</th><th>Actions</th></tr></thead>
                        <tbody id="cred-list">
                            <tr><td colspan="5" style="text-align:center;color:var(--text-muted)">Loading...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `;

        document.getElementById('add-cred-btn').addEventListener('click', () => {
            document.getElementById('cred-form').style.display = 'block';
        });
        document.getElementById('cancel-cred-btn').addEventListener('click', () => {
            document.getElementById('cred-form').style.display = 'none';
        });
        document.getElementById('save-cred-btn').addEventListener('click', () => this._saveCred());

        await this._loadList();
    },

    async _loadList() {
        const data = await API.get('/credentials');
        const body = document.getElementById('cred-list');
        const creds = data.credentials || [];

        if (!creds.length) {
            body.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No credentials stored. Click "Add Credential" to get started.</td></tr>';
            return;
        }

        body.innerHTML = creds.map(c => `
            <tr>
                <td><strong>${c.name}</strong></td>
                <td><span class="badge badge-accent">${c.service}</span></td>
                <td style="color:var(--text-secondary)">${c.notes || '—'}</td>
                <td style="font-family:'JetBrains Mono';font-size:12px">${c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}</td>
                <td><button class="btn btn-danger btn-sm" onclick="CredentialsPage._handleRevokeClick(this, '${c.name}')"><i class="fas fa-trash" style="margin-right:4px"></i> Revoke</button></td>
            </tr>
        `).join('');
    },

    async _handleRevokeClick(btn, name) {
        if (!confirm(`Revoke credential "${name}"? This cannot be undone.`)) return;
        UI.setLoading(btn, true);
        await this._revoke(name, btn);
    },

    async _saveCred() {
        const nameInp = document.getElementById('cred-name');
        const tokenInp = document.getElementById('cred-token');
        const name = nameInp.value.trim();
        const token = tokenInp.value.trim();
        const service = document.getElementById('cred-service').value.trim();
        const notes = document.getElementById('cred-notes').value.trim();

        UI.clearError(nameInp);
        UI.clearError(tokenInp);

        let hasError = false;
        if (!Validator.isSafeName(name)) {
            UI.showError(nameInp, 'Invalid name. Use alphanumeric, - and _ only.');
            hasError = true;
        }
        if (!token) {
            UI.showError(tokenInp, 'Token is required.');
            hasError = true;
        }

        if (hasError) return;

        const btn = document.getElementById('save-cred-btn');
        UI.setLoading(btn, true);

        try {
            const result = await API.post('/credentials', { name, service, token, notes });
            if (result.status === 'success') {
                showToast(`<i class="fas fa-lock"></i> Credential "${name}" encrypted and stored`, 'success');
                document.getElementById('cred-form').style.display = 'none';
                ['cred-name', 'cred-service', 'cred-token', 'cred-notes'].forEach(id => document.getElementById(id).value = '');
                await this._loadList();
            } else {
                showToast(`<i class="fas fa-times-circle"></i> ${result.error || 'Failed to store credential'}`, 'error');
            }
        } finally {
            UI.setLoading(btn, false);
        }
    },

    async _revoke(name, btn) {
        try {
            const result = await API.del(`/credentials/${encodeURIComponent(name)}`);
            if (result.status === 'success') {
                showToast(`<i class="fas fa-trash"></i> Credential "${name}" revoked`, 'success');
                await this._loadList();
                // No need to UI.setLoading(false) because list is re-rendered
            } else {
                showToast(`<i class="fas fa-times-circle"></i> ${result.error || 'Failed to revoke'}`, 'error');
                UI.setLoading(btn, false);
            }
        } catch (e) {
            UI.setLoading(btn, false);
        }
    }
};
