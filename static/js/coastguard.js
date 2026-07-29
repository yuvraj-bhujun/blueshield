document.addEventListener('DOMContentLoaded', () => {

    // ---------- MAP ----------
    const map = L.map('cgMap').setView([-20.348, 57.552], 8);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap & CARTO',
        maxZoom: 18
    }).addTo(map);

    // EEZ circle (demo)
    L.circle([-20.348, 57.552], {
        radius: 350000,
        color: '#34DFC4',
        fillOpacity: 0.05,
        weight: 1,
        dashArray: '4 6'
    }).addTo(map).bindPopup('Simplified EEZ (350km)');

    // ---------- Vessel Markers and List ----------
    let selectedVessel = null;
    const vesselMarkers = {};

    function riskColor(level) {
        if (level === 'High') return '#FF5A4E';
        if (level === 'Medium') return '#FFB020';
        return '#34DFC4';
    }

    function riskBadgeClass(level) {
        if (level === 'High') return 'badge-high';
        if (level === 'Medium') return 'badge-med';
        return 'badge-low';
    }

    function vesselIcon(v) {
        const color = riskColor(v.risk.level);
        return L.divIcon({
            className: '',
            html: `<div style="width:16px;height:16px;border-radius:50%;background:${color};border:2px solid #081820;box-shadow:0 0 0 4px ${color}44;"></div>`,
            iconSize: [16, 16]
        });
    }

    async function loadVessels() {
        try {
            const res = await fetch('/api/vessels');
            const data = await res.json();

            // Update AIS banner
            const banner = document.getElementById('aisBanner');
            const dot = document.getElementById('aisBannerDot');
            const text = document.getElementById('aisBannerText');
            if (data.ais_status && data.ais_status.connected && data.vessels.length > 0) {
                banner.className = 'ais-banner ais-live';
                text.textContent = `Live AIS feed — ${data.vessels.length} vessel${data.vessels.length === 1 ? '' : 's'} in range`;
            } else {
                banner.className = 'ais-banner ais-off';
                text.textContent = 'No live AIS data — showing simulated fleet.';
            }

            const list = document.getElementById('vesselList');
            list.innerHTML = '';

            // Update markers
            const currentIds = new Set(data.vessels.map(v => v.id));
            Object.keys(vesselMarkers).forEach(id => {
                if (!currentIds.has(id)) {
                    map.removeLayer(vesselMarkers[id]);
                    delete vesselMarkers[id];
                }
            });

            data.vessels.forEach(v => {
                // Marker
                if (vesselMarkers[v.id]) {
                    vesselMarkers[v.id].setLatLng([v.lat, v.lng]);
                } else {
                    const m = L.marker([v.lat, v.lng], { icon: vesselIcon(v) }).addTo(map);
                    m.on('click', () => selectVessel(v.id));
                    vesselMarkers[v.id] = m;
                }
                vesselMarkers[v.id].setIcon(vesselIcon(v));
                vesselMarkers[v.id].bindTooltip(`${v.name} — ${v.risk.score}%`);

                // List row
                const row = document.createElement('div');
                row.className = 'vessel-row' + (selectedVessel === v.id ? ' selected' : '');
                row.innerHTML = `
                    <div>
                        <div class="vessel-name">${v.name}</div>
                        <div class="vessel-meta">${v.type} · ${v.speed.toFixed(1)} kn · ${v.in_eez ? 'Inside EEZ' : 'Outside EEZ'}</div>
                    </div>
                    <div class="badge ${riskBadgeClass(v.risk.level)}"><span class="badge-dot"></span> ${v.risk.level}</div>
                    <div class="risk-score" style="color:${riskColor(v.risk.level)}">${v.risk.score}%</div>
                `;
                row.addEventListener('click', () => selectVessel(v.id));
                list.appendChild(row);
            });

        } catch (err) {
            console.error('Failed to load vessels:', err);
        }
    }

    // ---------- Vessel Detail ----------
    async function selectVessel(id) {
        if (selectedVessel === id) return;
        selectedVessel = id;
        // Highlight in list
        document.querySelectorAll('.vessel-row').forEach(el => el.classList.remove('selected'));
        document.querySelectorAll('.vessel-row').forEach(el => {
            if (el.innerText.includes(id)) el.classList.add('selected');
        });

        const panel = document.getElementById('detailPanel');
        panel.innerHTML = `<h3>Loading vessel data...</h3><p class="muted small">Fetching intelligence report.</p>`;

        try {
            const res = await fetch(`/api/vessel/${id}`);
            const data = await res.json();
            if (data.error) {
                panel.innerHTML = `<h3>Error</h3><p class="muted small">${data.error}</p>`;
                return;
            }
            const v = data.vessel;
            const risk = data.risk;
            panel.innerHTML = `
                <div class="flex-between">
                    <h3 style="margin:0;">${v.VesselName}</h3>
                    <div class="badge ${riskBadgeClass(risk.level)}"><span class="badge-dot"></span> ${risk.level} · ${risk.score}/100</div>
                </div>
                <p class="small muted">${v.VesselType} · Cargo: ${v.Cargo}</p>
                <div class="result-row"><span>Destination</span><span class="mono">${v.Destination || 'Unknown'}</span></div>
                <div class="result-row"><span>Distance to reef</span><span class="mono">${risk.current_distance} km</span></div>
                <div class="result-row"><span>Trend</span><span class="mono">${risk.trend}</span></div>
                <div class="result-row"><span>Closing speed</span><span class="mono">${risk.closing_speed} km/h</span></div>
                <div class="result-row"><span>ETA to reef</span><span class="mono">${risk.eta !== null ? risk.eta + ' h' : 'N/A'}</span></div>
                <div class="result-row"><span>Lane deviation</span><span class="mono">${risk.lane_deviation} km</span></div>
                <hr style="margin:16px 0;">
                <h4>🤖 AI Reasoning</h4>
                <div style="background:#0b1320;border:1px solid rgba(52,223,196,.25);border-radius:10px;padding:15px;line-height:1.7;white-space:pre-wrap;">
                    ${data.gemma_reasoning}
                </div>
            `;
        } catch (err) {
            panel.innerHTML = `<h3>Error</h3><p class="muted small">Unable to load vessel intelligence.</p>`;
        }
    }

    // Load vessels every 10 seconds (demo polling)
    loadVessels();
    setInterval(loadVessels, 10000);
});