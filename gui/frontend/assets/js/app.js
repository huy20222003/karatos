/**
 * Karatos SPA Router — Hash-based routing for single-page navigation.
 */
const App = {
    pages: {
        dashboard: { page: DashboardPage, title: 'Dashboard' },
        memory: { page: MemoryPage, title: 'Memory' },
        performance: { page: PerformancePage, title: 'Performance' },
        logs: { page: LogsPage, title: 'Logs' },
        settings: { page: SettingsPage, title: 'Settings' },
        credentials: { page: CredentialsPage, title: 'Credentials' },
        chat: { page: ChatPage, title: 'Chat' },
        mcp: { page: McpPage, title: 'MCP Servers' },
        avatar: { page: AvatarPage, title: 'Agent Avatar' },
    },

    init() {
        window.addEventListener('hashchange', () => {
            this.route();
            this.closeSidebar(); // Close sidebar on mobile after navigation
        });
        this.route();

        // Sidebar Toggle Logic for Mobile
        const menuToggle = document.getElementById('menu-toggle');
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebar-overlay');

        if (menuToggle && sidebar && overlay) {
            menuToggle.addEventListener('click', () => {
                sidebar.classList.toggle('active');
                overlay.classList.toggle('active');
            });

            overlay.addEventListener('click', () => {
                sidebar.classList.remove('active');
                overlay.classList.remove('active');
            });
        }

        // Start background polling for agent status (Online/Offline)
        this.startStatusPoller();
    },

    closeSidebar() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        if (sidebar && overlay) {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
        }
    },

    startStatusPoller() {
        // Run immediately once, then every 10 seconds
        const poll = async () => {
            try {
                const overview = await API.get('/dashboard/overview');
                if (overview && !overview.error && overview.agent) {
                    const a = overview.agent;
                    const badgeName = document.getElementById('badge-name');
                    if (badgeName) badgeName.textContent = a.name || 'Agent';

                    const badgeMood = document.getElementById('badge-mood');
                    if (badgeMood) badgeMood.textContent = this._moodEmoji(a.mood);

                    const statusEl = document.getElementById('agent-status');
                    if (statusEl) {
                        statusEl.innerHTML = `<span class="status-dot online"></span><span class="status-text">Online</span>`;
                    }
                } else {
                    const statusEl = document.getElementById('agent-status');
                    if (statusEl) {
                        statusEl.innerHTML = `<span class="status-dot offline"></span><span class="status-text">Offline</span>`;
                    }
                }
            } catch (e) {
                const statusEl = document.getElementById('agent-status');
                if (statusEl) {
                    statusEl.innerHTML = `<span class="status-dot offline"></span><span class="status-text">Disconnected</span>`;
                }
            }
        };
        poll();
        setInterval(poll, 10000);
    },

    _moodEmoji(mood) {
        const map = {
            OPTIMISTIC: '😊',
            NEUTRAL: '😐',
            CAUTIOUS: '🤔',
            FRUSTRATED: '😤',
            EXCITED: '🤩',
            CALM: '😌',
            ANGRY: '😡'
        };
        return map[mood] || '🤖';
    },

    async route() {
        const hash = window.location.hash.replace('#/', '') || 'dashboard';
        const pageKey = hash.split('/')[0] || 'dashboard';
        const entry = this.pages[pageKey];

        if (!entry) {
            window.location.hash = '#/';
            return;
        }

        // Update nav active state
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.page === pageKey);
        });

        // Update page title
        document.getElementById('page-title').textContent = entry.title;

        // Render page
        const container = document.getElementById('content-area');
        container.innerHTML = '<div class="loading-screen"><div class="spinner"></div></div>';

        try {
            // All pages now implement async render(container)
            await entry.page.render(container);

            if (entry.page.init) await entry.page.init();
        } catch (e) {
            console.error(`[App] Error rendering ${pageKey}:`, e);
            container.innerHTML = `<div class="card"><p style="color:var(--red)">Error loading page: ${e.message}</p></div>`;
        }
    }
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
