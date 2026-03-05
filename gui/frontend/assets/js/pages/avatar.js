/**
 * Avatar Page — 3D Agent Representation with Animations.
 */
const AvatarPage = {
    async render(container) {
        container.innerHTML = `
            <div class="avatar-container" style="display:flex; flex-direction:column; gap:20px; height: calc(100vh - 120px)">
                <!-- Main Viewer Card -->
                <div class="card" style="flex:1; position:relative; overflow:hidden; display:flex; flex-direction:column; background: radial-gradient(circle at center, rgba(108, 92, 231, 0.1), transparent)">
                    <div class="card-title" style="position:absolute; top:20px; left:20px; z-index:10">
                        <i class="fas fa-cube"></i> 3D Neural Presence
                    </div>
                    
                    <!-- 3D Model Viewer -->
                    <model-viewer 
                        id="agent-model"
                        src="/assets/models/sweeper.glb"
                        alt="Karatos Agent Avatar"
                        auto-rotate 
                        camera-controls 
                        shadow-intensity="1" 
                        environment-image="neutral" 
                        exposure="0.8" 
                        autoplay 
                        style="width:100%; height:100%; background: transparent;">
                        
                    </model-viewer>

                    <!-- Overlay Stats -->
                    <div style="position:absolute; left:20px; bottom:20px; padding:15px; background: rgba(0,0,0,0.4); border-radius:12px; backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.1); width:200px">
                        <div style="display:flex; justify-content:space-between; margin-bottom:10px">
                            <span style="font-size:11px; opacity:0.7">NEURAL LINK</span>
                            <span style="font-size:11px; color:#00d4a1">ACTIVE</span>
                        </div>
                        <div style="height:4px; background:rgba(255,255,255,0.1); border-radius:2px; overflow:hidden; margin-bottom:15px">
                            <div id="neural-sync-bar" style="height:100%; width:85%; background: var(--accent); box-shadow: 0 0 10px var(--accent)"></div>
                        </div>
                        <div style="font-size:10px; opacity:0.6; font-family:var(--font-mono)">SYNC_ID: BRAIN_0XA12F</div>
                    </div>
                </div>
            </div>
        `;

        this._setupListeners();
    },

    async init() {
        try {
            const data = await API.get('/dashboard/overview');
            if (data && data.agent && data.agent.avatar_url) {
                const model = document.getElementById('agent-model');
                if (model) model.src = data.agent.avatar_url;
            }
        } catch (e) {
            console.error('[AVATAR] Failed to load dynamic model:', e);
        }
    },

    _setupListeners() {
        const neuralBar = document.getElementById('neural-sync-bar');

        // Animate neural bar slightly
        setInterval(() => {
            if (neuralBar) {
                const w = 80 + Math.random() * 20;
                neuralBar.style.width = `${w}%`;
            }
        }, 3000);
    }
};
