const vesselCache = {};
document.addEventListener('DOMContentLoaded', () => {
  const map = L.map('cgMap').setView([-20.348, 57.552], 8);
  // ========================================
// Coral Reef Extent
// ========================================

const reefLayer = L.layerGroup().addTo(map);

fetch("/api/reef_extent")
    .then(res => res.json())
    .then(data => {

        const reefs = L.geoJSON(data, {

            style: function () {

                return {

                    color: "#00FFF5",

                    weight: 1.5,

                    opacity: 1,

                    fillColor: "#00BCD4",

                    fillOpacity: 0.25

                };

            },

            onEachFeature: function(feature, layer){

                layer.bindPopup(
                    "<b>Coral Reef</b>"
                );

            }

        });

        reefs.addTo(reefLayer);

        map.setView([-20.348, 57.552], 8);

    });

    L.control.layers(
    {},
    {
        "🪸 Coral Reefs": reefLayer
    }
).addTo(map);


  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO', maxZoom: 18,
  }).addTo(map);
  L.circle([-20.348, 57.552], { radius: 350000, color: '#34DFC4', fillOpacity: 0.02, weight: 1, dashArray: '4 6' })
    .addTo(map).bindPopup('Simplified EEZ boundary (350km radius, demo)');
  
  // =========================
// Coral Reef Layer
// =========================

const coralLayer = L.layerGroup().addTo(map);

fetch("/api/coral")
    .then(response => response.json())
    .then(data => {

        L.geoJSON(data, {

            style: function(feature){

                return {

                    color: "#00F5FF",
                    weight: 1,

                    fillColor: "#00BCD4",

                    fillOpacity: 0.45

                };

            },

            onEachFeature: function(feature, layer){

                layer.bindPopup(
                    "<b>Coral Reef</b><br>" +
                    feature.properties.class
                );

            }

        }).addTo(coralLayer);

    })
    .catch(err => console.error(err));

  L.control.layers(
    {},
    {
        "🪸 Coral Reefs": coralLayer
    }
).addTo(map);

  let selectedVessel = null;
  const vesselMarkers = {};

  function riskColor(level) {
    return level === 'High' ? '#FF5A4E' : level === 'Medium' ? '#FFB020' : '#34DFC4';
  }
  function riskBadgeClass(level) {
    return level === 'High' ? 'badge-high' : level === 'Medium' ? 'badge-med' : 'badge-low';
  }

  function vesselIcon(v) {
    const color = riskColor(v.risk.level);
    const isLive = v.source === 'live';
    // Live AIS contacts get a solid signal-colored ring; simulated demo
    // vessels get a plain dark border, so the map is honest about which
    // markers are real traffic vs the scripted demo fleet.
    const ring = isLive ? 'box-shadow:0 0 0 4px rgba(52,223,196,0.55);' : `box-shadow:0 0 0 5px ${color}2e;`;
    return L.divIcon({
      className: '',
      html: `<div style="width:16px;height:16px;border-radius:50%;background:${color};${ring}border:2px solid #081820;"></div>`,
      iconSize: [16, 16],
    });
  }

  function updateAisBanner(status) {
    const banner = document.getElementById('aisBanner');
    const dot = document.getElementById('aisBannerDot');
    const text = document.getElementById('aisBannerText');
    if (!banner) return;

    if (status && status.connected && status.vessel_count > 0) {
      banner.className = 'ais-banner ais-live';
      text.textContent = `Live AIS feed connected — ${status.vessel_count} real vessel${status.vessel_count === 1 ? '' : 's'} in range (AISStream.io)`;
    } else if (status && status.configured) {
      banner.className = 'ais-banner ais-pending';
      text.textContent = 'Live AIS feed configured, waiting for the first position report…';
    } else {
      banner.className = 'ais-banner ais-off';
      text.textContent = 'Live AIS feed not configured — showing simulated fleet only. Set AISSTREAM_API_KEY to enable real vessel tracking (free at aisstream.io).';
    }
  }

  async function loadVessels() {
    const res = await fetch('/api/vessels');
    const data = await res.json();
    const list = document.getElementById('vesselList');
    list.innerHTML = '';

    updateAisBanner(data.ais_status);

    // Drop markers for vessels no longer in the feed (e.g. a live contact
    // that's gone quiet) so the map doesn't accumulate stale ghosts.
    const currentIds = new Set(data.vessels.map(v => v.id));
    Object.keys(vesselMarkers).forEach(id => {
      if (!currentIds.has(id)) {
        map.removeLayer(vesselMarkers[id]);
        delete vesselMarkers[id];
      }
    });

    data.vessels.forEach(v => {
      // marker
      if (vesselMarkers[v.id]) {
        vesselMarkers[v.id].setLatLng([v.lat, v.lng]);
      } else {
        const m = L.marker([v.lat, v.lng], { icon: vesselIcon(v) }).addTo(map);
        m.on('click', () => selectVessel(v.id));
        vesselMarkers[v.id] = m;
      }
      vesselMarkers[v.id].setIcon(vesselIcon(v));
      const sourceLabel = v.source === 'live' ? 'LIVE AIS' : 'SIMULATED';
      vesselMarkers[v.id].bindTooltip(`${v.name} — ${v.risk.score}% · ${sourceLabel}`);

      // list row
      const row = document.createElement('div');
      row.className = 'vessel-row' + (selectedVessel === v.id ? ' selected' : '');
      row.innerHTML = `
        <div>
          <div class="vessel-name">${v.name} <span class="src-tag ${v.source === 'live' ? 'src-live' : 'src-sim'}">${v.source === 'live' ? 'LIVE AIS' : 'SIM'}</span></div>
          <div class="vessel-meta">${v.type} · ${v.speed.toFixed(1)} kn · ${v.in_eez ? 'Inside EEZ' : 'Outside EEZ'}</div>
        </div>
        <div class="badge ${riskBadgeClass(v.risk.level)}"><span class="badge-dot"></span> ${v.risk.level}</div>
        <div class="risk-score" style="color:${riskColor(v.risk.level)}">${v.risk.score}%</div>
      `;
      row.addEventListener('click', () => selectVessel(v.id));
      list.appendChild(row);
    });

  }

function selectVessel(id) {

    if (selectedVessel === id)
        return;

    selectedVessel = id;

    loadDetail(id);

    const m = vesselMarkers[id];

    if (m)
        map.panTo(m.getLatLng());

}

async function loadDetail(id) {

    const panel = document.getElementById("detailPanel");

    // Loading message while Gemma is generating
    panel.innerHTML = `
        <h3>Analysing vessel...</h3>
        <p class="small muted">
            BlueShield AI is generating a maritime intelligence report...
        </p>
    `;

    try {

        const res = await fetch(`/api/vessel/${id}`);
        const data = await res.json();

        const v = data.vessel;
        const risk = data.risk;

        panel.innerHTML = `
            <div class="flex-between">
                <h3 style="margin:0;">${v.VesselName}</h3>

                <div class="badge ${riskBadgeClass(risk.level)}">
                    <span class="badge-dot"></span>
                    ${risk.level} Risk · ${risk.score}/100
                </div>
            </div>

            <p class="small muted" style="margin-top:10px;">
                ${v.VesselType} ·
                Cargo: ${v.Cargo} ·
                Flag: ${v.Flag}
            </p>

            <div class="result-row">
                <span>Destination</span>
                <span class="mono">${v.Destination}</span>
            </div>

            <div class="result-row">
                <span>Current Reef Distance</span>
                <span class="mono">${risk.current_distance} km</span>
            </div>

            <div class="result-row">
                <span>Trend</span>
                <span class="mono">${risk.trend}</span>
            </div>

            <div class="result-row">
                <span>Closing Speed</span>
                <span class="mono">${risk.closing_speed} km/h</span>
            </div>

            <div class="result-row">
                <span>ETA to Reef</span>
                <span class="mono">
                    ${risk.eta == null ? "N/A" : risk.eta + " h"}
                </span>
            </div>

            <div class="result-row">
                <span>Lane Deviation</span>
                <span class="mono">${risk.lane_deviation} km</span>
            </div>

            <div class="result-row">
                <span>Inside Reef</span>
                <span class="mono">
                    ${risk.inside_reef ? "YES" : "NO"}
                </span>
            </div>

            <hr style="margin:20px 0;">

            <h4 style="margin-bottom:10px;">
                🤖 BlueShield AI (Gemma 4)
            </h4>

            <div style="
                background:#0b1320;
                border:1px solid rgba(52,223,196,.25);
                border-radius:10px;
                padding:15px;
                line-height:1.7;
                white-space:pre-wrap;
            ">
                ${data.gemma_reasoning}
            </div>
        `;

    }

    catch(error){

        console.error(error);

        panel.innerHTML = `
            <h3>Error</h3>
            <p class="small">
                Unable to load vessel intelligence.
            </p>
        `;
    }
}

  loadVessels();
});
