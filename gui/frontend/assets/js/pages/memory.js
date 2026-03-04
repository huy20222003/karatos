/**
 * Memory Page — Brain Hologram Visualization + Memory Browser.
 * Uses Three.js with a brain hologram background image overlay.
 */
const MemoryPage = {
    _scene: null,
    _camera: null,
    _renderer: null,
    _controls: null,
    _animId: null,
    _particles: [],
    _nodeGroups: [],

    async render(container) {
        container.innerHTML = `
            <div class="section-header">
                <h3 class="section-title">Memory Visualization</h3>
                <span class="badge badge-accent" id="mem-total">Loading...</span>
            </div>

            <div class="grid-1">
                <div class="card brain-card" style="padding:0;overflow:hidden;position:relative">
                    <div class="brain-bg">
                        <img src="/assets/img/brain_hologram.png" alt="" class="brain-img">
                        <div class="brain-overlay"></div>
                    </div>
                    <div id="three-canvas" style="position:absolute;top:0;left:0;width:100%;height:450px;z-index:2"></div>
                    <div id="three-legend" class="three-legend" style="z-index:3"></div>
                </div>
            </div>

            <div class="grid-1">
                <div class="card">
                    <div class="card-title"><i class="fas fa-folder-open" style="margin-right:6px;color:var(--accent)"></i> Memory Browser</div>
                    <div id="memory-categories" style="margin-top:12px">
                        <div class="loading-screen" style="height:150px"><div class="spinner"></div></div>
                    </div>
                </div>
            </div>

            <div id="memory-modal" class="modal" style="display:none">
                <div class="modal-overlay"></div>
                <div class="modal-content card">
                    <div class="section-header">
                        <h3 class="section-title" id="modal-title">Entries</h3>
                        <button class="btn btn-sm btn-ghost" id="modal-close">✕ Close</button>
                    </div>
                    <div id="modal-body" style="max-height:60vh;overflow-y:auto"></div>
                </div>
            </div>
        `;

        // Modal close
        document.getElementById('modal-close').addEventListener('click', () => {
            document.getElementById('memory-modal').style.display = 'none';
        });
        document.querySelector('.modal-overlay')?.addEventListener('click', () => {
            document.getElementById('memory-modal').style.display = 'none';
        });

        const [graphData, catData] = await Promise.all([
            API.get('/memory/graph'),
            API.get('/memory/categories'),
        ]);

        document.getElementById('mem-total').textContent = `${catData.total || 0} total entries`;

        this._render3D(graphData);
        this._renderCategories(catData);
    },

    _render3D(data) {
        const canvas = document.getElementById('three-canvas');
        if (!canvas || !window.THREE) {
            canvas.innerHTML = '<div class="loading-screen"><p style="color:var(--text-muted)">3D not available</p></div>';
            return;
        }

        const w = canvas.clientWidth;
        const h = canvas.clientHeight;

        // Scene — transparent to show brain image behind
        this._scene = new THREE.Scene();

        // Camera
        this._camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 1000);
        this._camera.position.set(0, 2, 55);

        // Renderer with transparent background
        this._renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        this._renderer.setClearColor(0x000000, 0);
        this._renderer.setSize(w, h);
        this._renderer.setPixelRatio(window.devicePixelRatio);
        canvas.innerHTML = '';
        canvas.appendChild(this._renderer.domElement);

        // Controls
        if (window.THREE.OrbitControls) {
            this._controls = new THREE.OrbitControls(this._camera, this._renderer.domElement);
            this._controls.enableDamping = true;
            this._controls.dampingFactor = 0.05;
            this._controls.autoRotate = true;
            this._controls.autoRotateSpeed = 0.3;
            this._controls.minDistance = 30;
            this._controls.maxDistance = 120;
        }

        // Soft ambient light
        this._scene.add(new THREE.AmbientLight(0x6c5ce7, 0.4));
        const pointLight = new THREE.PointLight(0x00d4ff, 1.5, 80);
        pointLight.position.set(0, 10, 30);
        this._scene.add(pointLight);
        const pointLight2 = new THREE.PointLight(0x6c5ce7, 1, 60);
        pointLight2.position.set(-15, -5, 20);
        this._scene.add(pointLight2);

        // Color palette
        const palette = [
            0x6c5ce7, 0x00d4a1, 0x3498ff, 0xffa502, 0xff4757,
            0xa55eea, 0x01a3a4, 0x21d4fd, 0xff6b6b, 0xfeca57,
            0x48dbfb, 0x5f27cd, 0x2ed573, 0xff9ff3, 0x54a0ff,
        ];

        const nodes = data.nodes || [];
        const legend = document.getElementById('three-legend');
        let legendHtml = '';

        // Position memory nodes in a brain-like ellipsoid shape
        nodes.forEach((node, idx) => {
            const color = palette[idx % palette.length];
            const count = node.count || 1;
            // Sphere size proportional to entry count
            const radius = Math.max(0.8, Math.min(Math.sqrt(count) * 0.6, 4));

            // Distribute in an ellipsoid (brain shape)
            const phi = (idx / nodes.length) * Math.PI * 2;  // angle around Y
            const theta = (Math.random() - 0.5) * Math.PI * 0.7; // vertical spread
            const rx = 18 + (Math.random() - 0.5) * 4; // horizontal radius
            const ry = 10 + (Math.random() - 0.5) * 4;  // vertical radius
            const cx = Math.cos(phi) * rx * Math.cos(theta);
            const cy = Math.sin(theta) * ry;
            const cz = Math.sin(phi) * rx * 0.5 * Math.cos(theta);

            // Glowing sphere for category center
            const geo = new THREE.SphereGeometry(radius, 24, 24);
            const mat = new THREE.MeshPhongMaterial({
                color: color,
                transparent: true,
                opacity: 0.6,
                emissive: color,
                emissiveIntensity: 0.5,
                shininess: 100,
            });
            const mesh = new THREE.Mesh(geo, mat);
            mesh.position.set(cx, cy, cz);
            mesh.userData = { name: node.id, count };
            this._scene.add(mesh);
            this._particles.push(mesh);

            // Outer glow ring
            const glowGeo = new THREE.SphereGeometry(radius * 1.6, 16, 16);
            const glowMat = new THREE.MeshBasicMaterial({
                color: color,
                transparent: true,
                opacity: 0.08,
            });
            const glow = new THREE.Mesh(glowGeo, glowMat);
            glow.position.copy(mesh.position);
            this._scene.add(glow);
            this._particles.push(glow);

            // Scattered neural particles around the node
            const particleCount = Math.min(count * 3, 60);
            const positions = new Float32Array(particleCount * 3);
            for (let i = 0; i < particleCount; i++) {
                positions[i * 3] = cx + (Math.random() - 0.5) * radius * 5;
                positions[i * 3 + 1] = cy + (Math.random() - 0.5) * radius * 5;
                positions[i * 3 + 2] = cz + (Math.random() - 0.5) * radius * 5;
            }
            const pGeo = new THREE.BufferGeometry();
            pGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
            const pMat = new THREE.PointsMaterial({
                color, size: 0.3, transparent: true, opacity: 0.5,
                blending: THREE.AdditiveBlending, depthWrite: false,
            });
            this._scene.add(new THREE.Points(pGeo, pMat));

            // Legend entry
            const hexColor = '#' + color.toString(16).padStart(6, '0');
            legendHtml += `<span class="legend-item"><span class="legend-dot" style="background:${hexColor}"></span>${node.id} (${count})</span>`;
        });

        // Draw neural connection lines between nodes
        for (let i = 0; i < this._particles.length; i += 2) {
            for (let j = i + 2; j < this._particles.length; j += 2) {
                if (Math.random() > 0.4) continue; // Only 60% connections
                const p1 = this._particles[i].position;
                const p2 = this._particles[j].position;

                // Curved line via a midpoint
                const mid = new THREE.Vector3(
                    (p1.x + p2.x) / 2 + (Math.random() - 0.5) * 3,
                    (p1.y + p2.y) / 2 + (Math.random() - 0.5) * 3,
                    (p1.z + p2.z) / 2 + (Math.random() - 0.5) * 3
                );

                const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
                const points = curve.getPoints(20);
                const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
                const lineMat = new THREE.LineBasicMaterial({
                    color: 0x00d4ff, transparent: true, opacity: 0.08,
                    blending: THREE.AdditiveBlending,
                });
                this._scene.add(new THREE.Line(lineGeo, lineMat));
            }
        }

        legend.innerHTML = legendHtml;

        // Animation loop
        const clock = new THREE.Clock();
        const animate = () => {
            this._animId = requestAnimationFrame(animate);
            const t = clock.getElapsedTime();

            // Gentle floating + pulsing
            for (let i = 0; i < this._particles.length; i += 2) {
                const mesh = this._particles[i];
                mesh.position.y += Math.sin(t * 0.8 + i) * 0.003;
                mesh.material.emissiveIntensity = 0.4 + Math.sin(t * 1.5 + i * 0.5) * 0.15;
            }

            if (this._controls) this._controls.update();
            this._renderer.render(this._scene, this._camera);
        };
        animate();

        // Resize handler
        const resizeObs = new ResizeObserver(() => {
            const nw = canvas.clientWidth;
            const nh = canvas.clientHeight;
            this._camera.aspect = nw / nh;
            this._camera.updateProjectionMatrix();
            this._renderer.setSize(nw, nh);
        });
        resizeObs.observe(canvas);
    },

    _renderCategories(data) {
        const el = document.getElementById('memory-categories');
        const cats = data.categories || [];
        if (!cats.length) {
            el.innerHTML = '<p style="color:var(--text-muted)">No memory categories found</p>';
            return;
        }

        const colors = ['#6c5ce7', '#00d4a1', '#3498ff', '#ffa502', '#ff4757', '#a55eea', '#01a3a4', '#21d4fd', '#ff6b6b', '#feca57'];

        el.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px">
            ${cats.filter(c => c.count > 0).map((cat, i) => `
                <div class="mem-category-card" data-category="${cat.name}" style="border-left:3px solid ${colors[i % colors.length]}">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <span style="font-weight:600;font-size:14px">${cat.name}</span>
                        <span class="badge badge-accent">${cat.count}</span>
                    </div>
                    ${(cat.samples || []).length ? `<div style="margin-top:8px;font-size:11px;color:var(--text-muted)">${(cat.samples || []).map(s => `• ${s}`).join('<br>')}</div>` : ''}
                </div>
            `).join('')}
        </div>`;

        // Click to browse entries
        document.querySelectorAll('.mem-category-card').forEach(card => {
            card.style.cursor = 'pointer';
            card.addEventListener('click', async () => {
                const category = card.dataset.category;
                const data = await API.get(`/memory/entries?category=${category}&limit=50`);
                this._showModal(category, data.entries || []);
            });
        });
    },

    _showModal(category, entries) {
        document.getElementById('modal-title').textContent = `${category} (${entries.length} entries)`;
        const body = document.getElementById('modal-body');
        body.innerHTML = entries.length ? entries.map(e => `
            <div style="padding:12px;border-bottom:1px solid var(--border)">
                <div style="font-weight:500;font-size:14px">${e.title || e.key || 'Untitled'}</div>
                <div style="font-size:12px;color:var(--text-muted);margin-top:4px">${e.preview || 'No preview'}</div>
                ${e.timestamp ? `<div style="font-size:11px;color:var(--text-muted);margin-top:4px;font-family:'JetBrains Mono'">${e.timestamp}</div>` : ''}
            </div>
        `).join('') : '<p style="color:var(--text-muted);padding:20px">No entries in this category</p>';
        document.getElementById('memory-modal').style.display = 'flex';
    },
};
