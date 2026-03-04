/**
 * MCP Management Page — Monitor and configure Model Context Protocol servers.
 */
const McpPage = {
    async render(container) {
        container.innerHTML = `
            <div class="mcp-page">
                <div class="grid-2">
                    <div class="card">
                        <div class="card-title">Active Servers</div>
                        <div class="card-value" id="active-mcp-count">0</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Total Tools</div>
                        <div class="card-value" id="total-mcp-tools">0</div>
                    </div>
                </div>

                <div class="content-split">
                    <!-- Right: Add Server Form -->
                    <div class="section-card">
                        <h3 class="section-title" style="margin-bottom:20px">Add New MCP Server</h3>
                        <form id="add-mcp-form" class="config-form">
                            <div class="form-group">
                                <label class="form-label">Server Name</label>
                                <input type="text" name="name" class="form-input" placeholder="e.g. filesystem" required>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Command / URL</label>
                                <input type="text" name="command" class="form-input" placeholder="npx, python, or http://..." required>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Arguments (comma separated)</label>
                                <input type="text" name="args" class="form-input" placeholder="-y, @modelcontextprotocol/server-memory">
                            </div>
                            <div class="form-group">
                                <label class="form-label">Environment Variables (JSON format)</label>
                                <textarea name="env" class="form-input" style="min-height:80px" placeholder='{"API_KEY": "..."}'></textarea>
                            </div>
                            <div class="form-actions">
                                <button type="submit" class="btn btn-primary" style="width:100%">Connect Server</button>
                            </div>
                        </form>
                    </div>

                    <!-- Left: Server List -->
                    <div class="section-card">
                        <div class="section-header">
                            <h3 class="section-title">Configured Servers</h3>
                            <button class="btn btn-sm btn-ghost" id="refresh-mcp"><i class="fas fa-sync" style="margin-right:4px"></i> Refresh</button>
                        </div>
                        <div class="server-grid" id="mcp-server-list">
                            <div class="loading-screen" style="height:100px"><div class="spinner"></div></div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    },

    async init() {
        this._loadServers();

        document.getElementById('refresh-mcp').addEventListener('click', () => this._loadServers());
        document.getElementById('add-mcp-form').addEventListener('submit', (e) => this._handleAddServer(e));
    },

    async _loadServers() {
        const listEl = document.getElementById('mcp-server-list');
        const countEl = document.getElementById('active-mcp-count');
        const toolsEl = document.getElementById('total-mcp-tools');

        const data = await API.get('/mcp/list');
        if (data.error) {
            listEl.innerHTML = `<div class="error-inline">${data.error}</div>`;
            return;
        }

        // The API now returns { servers, active_count, total_tools }
        const { servers, active_count, total_tools } = data;

        countEl.textContent = active_count || 0;
        toolsEl.textContent = total_tools || 0;

        if (servers.length === 0) {
            listEl.innerHTML = '<div class="empty-inline">No MCP servers configured.</div>';
            return;
        }

        listEl.innerHTML = '';
        servers.forEach(srv => {
            const card = document.createElement('div');
            card.className = `server-card`;
            card.innerHTML = `
                <div class="server-header">
                    <div class="server-title">
                        <span class="server-status-dot ${srv.status === 'connected' ? 'connected' : 'offline'}"></span>
                        <span class="server-name">${srv.name}</span>
                        ${srv.tool_count > 0 ? `<span class="badge badge-sm" style="margin-left:8px; opacity:0.8">${srv.tool_count} tools</span>` : ''}
                    </div>
                    <button class="btn btn-sm btn-ghost btn-remove" data-name="${srv.name}" title="Remove Server"><i class="fas fa-trash"></i></button>
                </div>
                <div class="server-cmd">${srv.command} ${srv.args.join(' ')}</div>
            `;

            card.querySelector('.btn-remove').addEventListener('click', (e) => this._handleRemove(srv.name, e.currentTarget));
            listEl.appendChild(card);
        });
    },

    async _handleAddServer(e) {
        e.preventDefault();
        const formData = new FormData(e.target);

        const name = formData.get('name');
        const command = formData.get('command');
        const argsStr = formData.get('args');
        const envStr = formData.get('env');

        const nameInput = e.target.querySelector('[name="name"]');
        const envInput = e.target.querySelector('[name="env"]');
        const cmdInput = e.target.querySelector('[name="command"]');

        UI.clearError(nameInput);
        UI.clearError(envInput);
        UI.clearError(cmdInput);

        let hasError = false;

        if (!Validator.isSafeName(name)) {
            UI.showError(nameInput, 'Invalid name. Use alphanumeric, - and _ only.');
            hasError = true;
        }

        if (!command || !command.trim()) {
            UI.showError(cmdInput, 'Command/URL is required.');
            hasError = true;
        }

        let env = {};
        if (envStr && envStr.trim()) {
            try {
                env = JSON.parse(envStr);
            } catch (err) {
                UI.showError(envInput, 'Invalid JSON format.');
                hasError = true;
            }
        }

        if (hasError) return;

        const args = argsStr ? argsStr.split(',').map(a => a.trim()) : [];
        const btn = e.target.querySelector('button');
        UI.setLoading(btn, true);

        try {
            const res = await API.post('/mcp/add', { name, command, args, env });
            if (res.status === 'success') {
                showToast(`Server '${name}' added successfully`);
                e.target.reset();
                this._loadServers();
            } else {
                showToast(res.error || 'Failed to add server', 'error');
            }
        } finally {
            UI.setLoading(btn, false);
        }
    },

    async _handleRemove(name, btn) {
        if (!confirm(`Are you sure you want to remove MCP server '${name}'?`)) return;

        UI.setLoading(btn, true);
        try {
            const res = await API.del(`/mcp/remove/${name}`);
            if (res.status === 'success') {
                showToast(`Server '${name}' removed`);
                this._loadServers();
            } else {
                showToast(res.error || 'Failed to remove server', 'error');
                UI.setLoading(btn, false);
            }
        } catch (e) {
            UI.setLoading(btn, false);
        }
    }
};
