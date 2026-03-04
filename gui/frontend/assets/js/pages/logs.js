/**
 * Logs Page — Real-time log viewer with level filtering.
 */
const LogsPage = {
    _autoScroll: true,
    _currentLevel: 'ALL',

    async render(container) {
        container.innerHTML = `
            <div class="section-header">
                <h3 class="section-title">Agent Logs</h3>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                    <div class="log-filters" id="log-filters">
                        <button class="btn btn-sm log-filter-btn active" data-level="ALL">ALL</button>
                        <button class="btn btn-sm log-filter-btn" data-level="INFO">INFO</button>
                        <button class="btn btn-sm log-filter-btn" data-level="WARNING">WARN</button>
                        <button class="btn btn-sm log-filter-btn" data-level="ERROR">ERROR</button>
                    </div>
                    <input class="form-input" id="log-search" placeholder="Filter logs..." style="flex:1;min-width:120px;padding:6px 12px;font-size:12px">
                    <button class="btn btn-sm btn-ghost" id="log-scroll-toggle" title="Auto-scroll"><i class="fas fa-arrow-down" style="margin-right:4px"></i>Auto</button>
                    <button class="btn btn-sm btn-primary" id="log-refresh"><i class="fas fa-sync" style="margin-right:4px"></i>Refresh</button>
                </div>
            </div>
            <div class="card log-viewer-card">
                <div class="log-viewer" id="log-viewer">
                    <div class="loading-screen" style="height:200px"><div class="spinner"></div></div>
                </div>
            </div>
        `;

        // Filter buttons
        document.querySelectorAll('.log-filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.log-filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this._currentLevel = btn.dataset.level;
                this._loadLogs();
            });
        });

        // Search
        document.getElementById('log-search').addEventListener('input', (e) => {
            this._filterVisible(e.target.value);
        });

        // Auto-scroll toggle
        document.getElementById('log-scroll-toggle').addEventListener('click', () => {
            this._autoScroll = !this._autoScroll;
            document.getElementById('log-scroll-toggle').innerHTML = this._autoScroll ? '<i class="fas fa-arrow-down" style="margin-right:4px"></i>Auto' : '<i class="fas fa-pause" style="margin-right:4px"></i>Paused';
        });

        // Refresh
        document.getElementById('log-refresh').addEventListener('click', () => this._loadLogs());

        await this._loadLogs();
    },

    async _loadLogs() {
        const data = await API.get(`/logs?lines=300&level=${this._currentLevel}`);
        const viewer = document.getElementById('log-viewer');

        if (data.error || !data.entries) {
            viewer.innerHTML = `<div class="log-empty">No logs available: ${data.error || 'unknown'}</div>`;
            return;
        }

        viewer.innerHTML = data.entries.map(e => {
            const levelClass = `log-${(e.level || 'INFO').toLowerCase()}`;
            // Format timestamp from YYYY-MM-DD HH:MM:SS to DD/MM/YYYY HH:MM:SS
            let ts = e.timestamp || '';
            if (ts.length >= 10 && ts.includes('-')) {
                const parts = ts.split(' ');
                const dateParts = parts[0].split('-');
                if (dateParts.length === 3) {
                    ts = `${dateParts[2]}/${dateParts[1]}/${dateParts[0]}${parts[1] ? ' ' + parts[1] : ''}`;
                }
            }
            return `<div class="log-line ${levelClass}">
                <span class="log-time">${ts}</span>
                <span class="log-level">${e.level || 'INFO'}</span>
                <span class="log-msg">${this._escapeHtml(e.message || '')}</span>
            </div>`;
        }).join('');

        // File info
        viewer.innerHTML += `<div class="log-meta">${data.entries.length} entries from ${data.file || 'unknown'} (${data.total_lines || 0} total lines)</div>`;

        if (this._autoScroll) {
            viewer.scrollTop = viewer.scrollHeight;
        }
    },

    _filterVisible(query) {
        const q = query.toLowerCase();
        document.querySelectorAll('.log-line').forEach(el => {
            el.style.display = !q || el.textContent.toLowerCase().includes(q) ? '' : 'none';
        });
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};
