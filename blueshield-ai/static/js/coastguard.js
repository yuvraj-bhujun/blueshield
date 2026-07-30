const vesselCache = {};

// Global alarm sound object
const alarmAudio = new Audio('/static/sounds/alarm.mp3');
alarmAudio.loop = true;
let isAudioUnlocked = false;

// Unlock browser audio permission on first user click anywhere on the page
document.addEventListener('click', () => {
  if (!isAudioUnlocked) {
    alarmAudio.play().then(() => {
      alarmAudio.pause();
      alarmAudio.currentTime = 0;
      isAudioUnlocked = true;
      console.log("🔊 Coast Guard page audio unlocked!");
    }).catch(() => {});
  }
}, { once: true });

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

        onEachFeature: function (feature, layer) {

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

        style: function (feature) {

          return {

            color: "#00F5FF",
            weight: 1,

            fillColor: "#00BCD4",

            fillOpacity: 0.45

          };

        },

        onEachFeature: function (feature, layer) {

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

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderGemmaReasoning(reasoning) {
    if (reasoning === null || reasoning === undefined) {
      return 'No reasoning available.';
    }
    if (typeof reasoning === 'string') {
      return reasoning;
    }
    if (reasoning.raw_response) {
      return reasoning.raw_response;
    }
    if (reasoning.error) {
      return `Error: ${reasoning.message || reasoning.error}`;
    }
    return JSON.stringify(reasoning, null, 2);
  }

// Global variables to store cached audio in browser memory
let currentAudio = null;
let currentAudioUrl = null;
let currentVesselId = null;

async function playCreoleSpeech(vesselId) {
    const btn = document.getElementById("playCreoleBtn");
    const btnText = document.getElementById("btnText");
    const btnIcon = document.getElementById("btnIcon");
    const reportText = document.getElementById("gemmaReportText").innerText;

    // ⚡ INSTANT REPLAY: If audio is already loaded for this vessel, play/pause immediately!
    if (currentVesselId === vesselId && currentAudioUrl) {
        if (!currentAudio.paused) {
            currentAudio.pause();
            btnText.innerText = "Listen in Mauritian Creole (Kreol Morisien)";
            btnIcon.innerText = "🔊";
        } else {
            currentAudio.currentTime = 0; // Reset to start
            currentAudio.play();
            btnText.innerText = "Playing Creole Audio...";
            btnIcon.innerText = "▶️";
        }
        return;
    }

    // Stop existing audio if playing another vessel
    if (currentAudio) {
        currentAudio.pause();
    }

    btn.disabled = true;
    btnText.innerText = "Generating Creole Speech...";
    btnIcon.innerText = "⏳";

    try {
        const response = await fetch('/api/speech/creole', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                text: reportText,
                vessel_id: vesselId 
            })
        });

        if (!response.ok) throw new Error(`Server error (${response.status})`);

        const audioBlob = await response.blob();
        
        // Cache in browser memory
        if (currentAudioUrl) URL.revokeObjectURL(currentAudioUrl); // Free memory
        currentAudioUrl = URL.createObjectURL(audioBlob);
        currentAudio = new Audio(currentAudioUrl);
        currentVesselId = vesselId;

        btnText.innerText = "Playing Creole Audio...";
        btnIcon.innerText = "▶️";
        btn.disabled = false;

        currentAudio.onended = () => {
            btnText.innerText = "Listen in Mauritian Creole (Kreol Morisien)";
            btnIcon.innerText = "🔊";
        };

        currentAudio.onerror = () => {
            alert("Error playing audio.");
            resetButton();
        };

        await currentAudio.play();

    } catch (err) {
        console.error("Speech Error:", err);
        alert(`Error: ${err.message}`);
        resetButton();
    }

    function resetButton() {
        btn.disabled = false;
        btnText.innerText = "Listen in Mauritian Creole (Kreol Morisien)";
        btnIcon.innerText = "🔊";
    }
}

async function loadVessels() {
    try {
      const res = await fetch('/api/vessels');
      const data = await res.json();
      const list = document.getElementById('vesselList');
      list.innerHTML = '';

      updateAisBanner(data.ais_status);

      // =========================================================================
      // 🚨 ALARM TRIGGER: Check if ANY vessel in the fleet is High or Critical
      // =========================================================================
      const highRiskVessel = data.vessels.find(
        v => v.risk.level === 'High' || v.risk.level === 'Critical' || v.risk.score >= 75
      );

      if (highRiskVessel) {
        console.warn(`🚨 HIGH RISK VESSEL DETECTED: ${highRiskVessel.name}`);
        
        // Play local alarm sound
        alarmAudio.play().catch(err => {
          console.warn("Browser blocked autoplay. Click anywhere on the map to enable audio.", err);
        });

        // (Optional) Call your mobile phone alarm trigger endpoint
        fetch('/api/trigger-alarm', { method: 'POST' }).catch(() => {});

      } else {
        // Silence alarm if no high-risk vessels exist
        alarmAudio.pause();
        alarmAudio.currentTime = 0;
      }

      // Drop markers for vessels no longer in the feed
      const currentIds = new Set(data.vessels.map(v => v.id));
      Object.keys(vesselMarkers).forEach(id => {
        if (!currentIds.has(id)) {
          map.removeLayer(vesselMarkers[id]);
          delete vesselMarkers[id];
        }
      });

      // Render vessel markers and sidebar rows
      data.vessels.forEach(v => {
        // Marker creation/update
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

        // Sidebar list row
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

    } catch (err) {
      console.error("Error loading vessels:", err);
    }
  }

  // Load vessels immediately, then poll every 5 seconds for live risk monitoring
  loadVessels();
  setInterval(loadVessels, 5000);

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

      // Store gemma reasoning safely for JavaScript string handling
      const gemmaText = data.gemma_reasoning;

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

            <pre id="gemmaReportText" style="
                margin:0;
                background:#0b1320;
                border:1px solid rgba(52,223,196,.25);
                border-radius:10px;
                padding:15px;
                line-height:1.7;
                white-space:pre-wrap;
                font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
                font-size:13px;
            ">${escapeHtml(renderGemmaReasoning(gemmaText))}</pre>

            <!-- 🔊 Mauritian Creole Audio Play Button -->
            <button id="playCreoleBtn" style="
                margin-top: 15px;
                width: 100%;
                padding: 12px 18px;
                background: #0b1320;
                border: 1px solid #34dfc4;
                color: #34dfc4;
                border-radius: 8px;
                cursor: pointer;
                font-weight: 600;
                font-size: 14px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                transition: all 0.2s ease;
            ">
                <span id="btnIcon">🔊</span> 
                <span id="btnText">Listen in Mauritian Creole (Kreol Morisien)</span>
            </button>
        `;

        // Inside loadDetail(id) right after setting panel.innerHTML:
        const playBtn = document.getElementById("playCreoleBtn");
        if (playBtn) {
            playBtn.addEventListener("click", () => playCreoleSpeech(id));
        }
    }

    catch (error) {

      console.error(error);

      panel.innerHTML = `
            <h3>Error</h3>
            <p class="small">
                Unable to load vessel intelligence.
            </p>
        `;
    }
  }
});