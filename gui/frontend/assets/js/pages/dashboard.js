/**
 * Dashboard Page — Enhanced with telemetry stats and Chart.js charts.
 */
const DashboardPage = {
    async render(container) {
        container.innerHTML = `
            <div class="grid-4" id="stat-cards">
                <div class="card"><div class="card-title">Status</div><div class="card-value" id="s-status">—</div><div class="card-sub" id="s-provider"></div></div>
                <div class="card"><div class="card-title">Model</div><div class="card-value" id="s-model" style="font-size:18px">—</div><div class="card-sub" id="s-model-sub"></div></div>
                <div class="card"><div class="card-title">Mood</div><div class="card-value" id="s-mood">—</div><div class="card-sub" id="s-energy"></div></div>
                <div class="card"><div class="card-title">Uptime</div><div class="card-value" id="s-uptime" style="font-size:22px">—</div><div class="card-sub">since start</div></div>
                <div class="card"><div class="card-title">Total Skills</div><div class="card-value" id="s-skills">—</div><div class="card-sub">registered skills</div></div>
                <div class="card"><div class="card-title">Total Tools</div><div class="card-value" id="s-tools">—</div><div class="card-sub">local & mcp</div></div>
                <div class="card"><div class="card-title">Total Tokens</div><div class="card-value" id="s-tokens">—</div><div class="card-sub" id="s-tokens-rate"></div></div>
                <div class="card"><div class="card-title">Avg Latency</div><div class="card-value" id="s-latency">—</div><div class="card-sub" id="s-interactions"></div></div>
            </div>

            <div class="grid-2">
                <div class="card">
                    <div class="card-title"><i class="fas fa-chart-line" style="margin-right:6px;color:var(--accent)"></i> Token Usage Over Time</div>
                    <div style="position:relative;height:220px;margin-top:8px">
                        <canvas id="chart-tokens"></canvas>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title"><i class="fas fa-stopwatch" style="margin-right:6px;color:var(--accent)"></i> Response Latency</div>
                    <div style="position:relative;height:220px;margin-top:8px">
                        <canvas id="chart-latency"></canvas>
                    </div>
                </div>
            </div>

            <div class="grid-2">
                <div class="card" style="padding-bottom:0;display:flex;flex-direction:column">
                    <div class="card-title" style="padding:20px 20px 0 20px"><i class="fas fa-brain" style="margin-right:6px;color:var(--accent)"></i> Memory Distribution</div>
                    <div class="expandable-card-content" id="memory-expander">
                        <div id="memory-bars" class="mem-bar-container" style="padding:0 20px 20px 20px">
                            <div class="loading-screen" style="height:150px"><div class="spinner"></div></div>
                        </div>
                        <div class="expandable-card-overlay"></div>
                    </div>
                    <button class="btn-view-more" data-target="memory-expander">
                        <span>View All</span> <i class="fas fa-chevron-down"></i>
                    </button>
                </div>
                <div class="card" style="padding-bottom:0;display:flex;flex-direction:column">
                    <div class="card-title" style="padding:20px 20px 0 20px"><i class="fas fa-tools" style="margin-right:6px;color:var(--accent)"></i> Registered Tools</div>
                    <div class="expandable-card-content" id="tools-expander">
                        <div id="tools-list" style="padding:0 20px 20px 20px">
                            <div class="loading-screen" style="height:150px"><div class="spinner"></div></div>
                        </div>
                        <div class="expandable-card-overlay"></div>
                    </div>
                    <button class="btn-view-more" data-target="tools-expander">
                        <span>View All</span> <i class="fas fa-chevron-down"></i>
                    </button>
                </div>
            </div>

            <div class="grid-1">
                <div class="card">
                    <div class="card-title"><i class="fas fa-clipboard-list" style="margin-right:6px;color:var(--accent)"></i> Recent Decisions</div>
                    <div class="table-container" style="margin-top:12px">
                        <table id="decisions-table">
                            <thead><tr><th>Time</th><th>Decision</th><th>Details</th></tr></thead>
                            <tbody id="decisions-body">
                                <tr><td colspan="3" style="text-align:center;color:var(--text-muted)">Loading...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        // Load data in parallel
        const [overview, telemetry, history, memory, tools, decisions] = await Promise.all([
            API.get('/dashboard/overview'),
            API.get('/telemetry/summary'),
            API.get('/telemetry/history'),
            API.get('/dashboard/memory'),
            API.get('/dashboard/tools'),
            API.get('/dashboard/decisions'),
        ]);

        this._renderOverview(overview);
        this._renderTelemetry(telemetry);
        this._renderCharts(history);
        this._renderMemory(memory);
        this._renderTools(tools);
        this._renderDecisions(decisions);

        // Update agent badge in topbar
        if (overview.agent) {
            document.getElementById('badge-name').textContent = overview.agent.name || 'Agent';
            document.getElementById('badge-mood').innerHTML = this._moodEmoji(overview.agent.mood);
            const statusEl = document.getElementById('agent-status');
            if (statusEl) statusEl.innerHTML = `<span class="status-dot online"></span><span class="status-text">Online</span>`;
        }

        this._setupExpanders();
    },

    _setupExpanders() {
        const buttons = document.querySelectorAll('.btn-view-more');
        buttons.forEach(btn => {
            btn.addEventListener('click', () => {
                const targetId = btn.getAttribute('data-target');
                const content = document.getElementById(targetId);
                const isExpanded = content.classList.toggle('expanded');
                btn.classList.toggle('active', isExpanded);

                const span = btn.querySelector('span');
                if (span) {
                    span.textContent = isExpanded ? 'Show Less' : 'View All';
                }
            });
        });
    },

    _renderOverview(data) {
        if (data.error) return;
        const a = data.agent || {};
        document.getElementById('s-status').innerHTML = '<i class="fas fa-circle" style="color:#00d4a1;font-size:10px;margin-right:6px"></i> Online';
        document.getElementById('s-provider').textContent = `Provider: ${a.llm_provider || '—'}`;
        document.getElementById('s-model').textContent = a.model || '—';
        document.getElementById('s-mood').innerHTML = `${this._moodEmoji(a.mood)} ${a.mood || '—'}`;
        document.getElementById('s-energy').textContent = `Energy: ${((a.energy || 0) * 100).toFixed(0)}%`;
        document.getElementById('s-skills').textContent = data.skill_count || 0;
        document.getElementById('s-tools').textContent = data.tool_count || 0;
    },

    _renderTelemetry(data) {
        if (!data) return;
        // Uptime
        const secs = data.uptime_seconds || 0;
        const h = Math.floor(secs / 3600);
        const m = Math.floor((secs % 3600) / 60);
        document.getElementById('s-uptime').textContent = h > 0 ? `${h}h ${m}m` : `${m}m`;

        // Tokens
        const tokens = data.total_tokens || 0;
        document.getElementById('s-tokens').textContent = tokens >= 1e6 ? `${(tokens / 1e6).toFixed(2)}M` : tokens >= 1e3 ? `${(tokens / 1e3).toFixed(1)}K` : tokens;
        document.getElementById('s-tokens-rate').textContent = `${data.tokens_per_minute?.toFixed(0) || 0} tok/min`;

        // Latency
        document.getElementById('s-latency').textContent = `${data.avg_latency || 0}s`;
        document.getElementById('s-interactions').textContent = `${data.total_interactions || 0} interactions`;
    },

    _renderCharts(data) {
        if (!data || !data.entries || !data.entries.length) return;
        const entries = data.entries;
        const labels = entries.map(e => {
            if (!e.timestamp) return '';
            const d = new Date(e.timestamp * 1000);
            return `${d.getDate().toString().padStart(2, '0')}/${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getFullYear()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
        });

        // Token Usage Chart
        const tokCtx = document.getElementById('chart-tokens').getContext('2d');
        new Chart(tokCtx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Tokens',
                    data: entries.map(e => e.tokens),
                    borderColor: '#6c5ce7',
                    backgroundColor: 'rgba(108, 92, 231, 0.1)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    borderWidth: 2,
                }]
            },
            options: this._chartOpts('Tokens', true),
        });

        // Latency Chart
        const latCtx = document.getElementById('chart-latency').getContext('2d');
        new Chart(latCtx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Latency (s)',
                    data: entries.map(e => e.latency),
                    backgroundColor: entries.map(e =>
                        e.latency < 3 ? 'rgba(0, 212, 161, 0.7)' :
                            e.latency < 4 ? 'rgba(52, 152, 255, 0.7)' :
                                e.latency < 5 ? 'rgba(255, 165, 2, 0.7)' :
                                    'rgba(255, 71, 87, 0.7)'
                    ),
                    borderRadius: 4,
                    borderSkipped: false,
                }]
            },
            options: this._chartOpts('Seconds', true),
        });
    },

    _chartOpts(yLabel, showX = false) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#161628',
                    borderColor: '#2a2a4a',
                    borderWidth: 1,
                    titleColor: '#e8e8f0',
                    bodyColor: '#8888aa',
                    cornerRadius: 8,
                    padding: 10,
                }
            },
            scales: {
                x: {
                    display: showX,
                    ticks: { color: '#555577', font: { size: 10 }, maxRotation: 45, maxTicksLimit: 8 },
                    grid: { display: false },
                },
                y: {
                    grid: { color: 'rgba(42, 42, 74, 0.3)' },
                    ticks: { color: '#555577', font: { size: 11 } },
                    title: { display: true, text: yLabel, color: '#555577', font: { size: 11 } },
                }
            }
        };
    },

    _renderMemory(data) {
        const el = document.getElementById('memory-bars');
        if (data.error || !data.categories) {
            el.innerHTML = '<p style="color:var(--text-muted)">Unable to load memory stats</p>';
            return;
        }

        const cats = Object.entries(data.categories).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
        const max = cats.length ? cats[0][1] : 1;
        const colors = ['#6c5ce7', '#00d4a1', '#3498ff', '#ffa502', '#ff4757', '#a55eea', '#01a3a4', '#21d4fd', '#ff6b6b', '#feca57'];

        el.innerHTML = cats.length ? cats.map(([cat, count], i) => `
            <div class="mem-bar-row">
                <span class="mem-bar-label">${cat}</span>
                <div class="mem-bar-track">
                    <div class="mem-bar-fill" style="width:${(count / max * 100).toFixed(1)}%;background:${colors[i % colors.length]}">${count}</div>
                </div>
            </div>
        `).join('') : '<p style="color:var(--text-muted)">No memories stored yet</p>';
    },

    _renderTools(data) {
        const el = document.getElementById('tools-list');
        if (data.error) { el.innerHTML = '<p style="color:var(--text-muted)">Unable to load tools</p>'; return; }

        const tools = Array.isArray(data.tools) ? data.tools : [];
        const mcp = Array.isArray(data.mcp_servers) ? data.mcp_servers : [];

        let html = tools.map(t => `
            <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)">
                <div>
                    <span style="font-weight:500">${t.name || 'unknown'}</span>
                    <div style="font-size:11px;color:var(--text-muted);margin-top:2px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.description || ''}</div>
                </div>
                <span class="badge badge-green">LOCAL</span>
            </div>
        `).join('');

        html += mcp.map(s => `
            <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)">
                <span style="font-weight:500">MCP: ${s.name}</span>
                <span class="badge ${s.connected ? 'badge-green' : 'badge-yellow'}">${s.connected ? 'CONNECTED' : 'STANDBY'}</span>
            </div>
        `).join('');

        el.innerHTML = html || '<p style="color:var(--text-muted)">No tools registered</p>';
    },

    _renderDecisions(data) {
        const body = document.getElementById('decisions-body');
        const decisions = data.decisions || [];
        if (!decisions.length) {
            body.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted)">No recent decisions</td></tr>';
            return;
        }
        body.innerHTML = decisions.slice(-10).reverse().map(d => {
            let ts = d.timestamp || '—';
            if (ts && ts.includes('-') && ts.length >= 10) {
                const parts = ts.split(' ');
                const dateParts = parts[0].split('-');
                if (dateParts.length === 3) {
                    ts = `${dateParts[2]}/${dateParts[1]}/${dateParts[0]}${parts[1] ? ' ' + parts[1] : ''}`;
                }
            }
            return `
            <tr>
                <td style="font-family:'JetBrains Mono';font-size:12px">${ts}</td>
                <td><span class="badge badge-accent">${d.decision || d.type || '—'}</span></td>
                <td style="color:var(--text-secondary)">${d.details || d.message || '—'}</td>
            </tr>
            `;
        }).join('');
    },

    _moodEmoji(mood) {
        const map = { OPTIMISTIC: '<i class="fas fa-smile" style="color:#00d4a1"></i>', NEUTRAL: '<i class="fas fa-meh" style="color:#8888aa"></i>', CAUTIOUS: '<i class="fas fa-question-circle" style="color:#ffa502"></i>', FRUSTRATED: '<i class="fas fa-angry" style="color:#ff4757"></i>', EXCITED: '<i class="fas fa-grin-stars" style="color:#feca57"></i>', CALM: '<i class="fas fa-smile-beam" style="color:#6c5ce7"></i>' };
        return map[mood] || '<i class="fas fa-robot" style="color:var(--accent)"></i>';
    }
};
