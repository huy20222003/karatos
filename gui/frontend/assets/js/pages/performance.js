/**
 * Performance Page — Deep telemetry analytics with Chart.js.
 */
const PerformancePage = {
    async render(container) {
        container.innerHTML = `
            <div class="section-header">
                <h3 class="section-title">Performance Analytics</h3>
                <span class="badge badge-accent"><i class="fas fa-chart-bar" style="margin-right:4px"></i> Telemetry Data</span>
            </div>

            <div class="grid-4" id="perf-stats">
                <div class="card"><div class="card-title">Total Interactions</div><div class="card-value" id="p-interactions">—</div></div>
                <div class="card"><div class="card-title">Total Tokens</div><div class="card-value" id="p-tokens">—</div></div>
                <div class="card"><div class="card-title">Tokens / Minute</div><div class="card-value" id="p-rate">—</div></div>
                <div class="card"><div class="card-title">Avg Latency</div><div class="card-value" id="p-latency">—</div></div>
            </div>

            <div class="grid-2">
                <div class="card">
                    <div class="card-title"><i class="fas fa-cube" style="margin-right:6px;color:var(--accent)"></i> Tokens Per Interaction</div>
                    <div style="position:relative;height:260px;margin-top:8px">
                        <canvas id="perf-scatter"></canvas>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title"><i class="fas fa-chart-bar" style="margin-right:6px;color:var(--accent)"></i> Latency Distribution</div>
                    <div style="position:relative;height:260px;margin-top:8px">
                        <canvas id="perf-histogram"></canvas>
                    </div>
                </div>
            </div>

            <div class="grid-1">
                <div class="card">
                    <div class="card-title"><i class="fas fa-chart-area" style="margin-right:6px;color:var(--accent)"></i> Cumulative Token Usage</div>
                    <div style="position:relative;height:280px;margin-top:8px">
                        <canvas id="perf-cumulative"></canvas>
                    </div>
                </div>
            </div>
        `;

        const [summary, history] = await Promise.all([
            API.get('/telemetry/summary'),
            API.get('/telemetry/history'),
        ]);

        this._renderStats(summary);
        this._renderCharts(history);
    },

    _renderStats(data) {
        if (!data) return;
        const t = data.total_tokens || 0;
        document.getElementById('p-interactions').textContent = data.total_interactions || 0;
        document.getElementById('p-tokens').textContent = t >= 1e6 ? `${(t / 1e6).toFixed(2)}M` : t >= 1e3 ? `${(t / 1e3).toFixed(1)}K` : t;
        document.getElementById('p-rate').textContent = `${data.tokens_per_minute?.toFixed(1) || 0}`;
        document.getElementById('p-latency').textContent = `${data.avg_latency || 0}s`;
    },

    _renderCharts(data) {
        if (!data || !data.entries || !data.entries.length) return;
        const entries = data.entries;

        // Helper: format timestamp
        const fmtDate = (ts) => {
            if (!ts) return '';
            const d = new Date(ts * 1000);
            return `${d.getDate().toString().padStart(2, '0')}/${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getFullYear()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
        };

        // Scatter: Tokens per Interaction
        const scatterCtx = document.getElementById('perf-scatter').getContext('2d');
        new Chart(scatterCtx, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Tokens',
                    data: entries.map((e, i) => ({ x: i + 1, y: e.tokens })),
                    backgroundColor: 'rgba(108, 92, 231, 0.6)',
                    pointRadius: 5,
                    pointHoverRadius: 8,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { callbacks: { title: (items) => fmtDate(entries[items[0].dataIndex]?.timestamp) } } },
                scales: {
                    x: { title: { display: true, text: 'Interaction #', color: '#555577' }, grid: { color: 'rgba(42,42,74,0.3)' }, ticks: { color: '#555577' } },
                    y: { title: { display: true, text: 'Tokens', color: '#555577' }, grid: { color: 'rgba(42,42,74,0.3)' }, ticks: { color: '#555577' } },
                }
            }
        });

        // Histogram: Latency Distribution
        const bins = [0, 2, 3, 4, 5, 7, 10];
        const counts = new Array(bins.length).fill(0);
        entries.forEach(e => {
            for (let i = bins.length - 1; i >= 0; i--) {
                if (e.latency >= bins[i]) { counts[i]++; break; }
            }
        });
        const binLabels = bins.map((b, i) => i < bins.length - 1 ? `${b}-${bins[i + 1]}s` : `${b}s+`);
        const histColors = ['#00d4a1', '#00d4a1', '#3498ff', '#ffa502', '#ff4757', '#ff4757', '#ff4757'];

        const histCtx = document.getElementById('perf-histogram').getContext('2d');
        new Chart(histCtx, {
            type: 'bar',
            data: {
                labels: binLabels,
                datasets: [{
                    label: 'Count',
                    data: counts,
                    backgroundColor: histColors.map(c => c + 'B3'),
                    borderRadius: 6,
                    borderSkipped: false,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#555577' } },
                    y: { title: { display: true, text: 'Frequency', color: '#555577' }, grid: { color: 'rgba(42,42,74,0.3)' }, ticks: { color: '#555577', stepSize: 1 } },
                }
            }
        });

        // Cumulative Token Usage
        let cumulative = 0;
        const cumData = entries.map(e => { cumulative += e.tokens; return cumulative; });
        const cumCtx = document.getElementById('perf-cumulative').getContext('2d');
        const cumLabels = entries.map(e => fmtDate(e.timestamp));
        new Chart(cumCtx, {
            type: 'line',
            data: {
                labels: cumLabels,
                datasets: [{
                    label: 'Cumulative Tokens',
                    data: cumData,
                    borderColor: '#00d4a1',
                    backgroundColor: 'rgba(0, 212, 161, 0.08)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                    borderWidth: 2,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { display: true, ticks: { color: '#555577', font: { size: 10 }, maxRotation: 45, maxTicksLimit: 8 }, grid: { display: false } },
                    y: { grid: { color: 'rgba(42,42,74,0.3)' }, ticks: { color: '#555577' } },
                }
            }
        });
    }
};
