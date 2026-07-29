document.addEventListener('DOMContentLoaded', async () => {
  const map = L.map('wakashioMap').setView([-20.35, 57.85], 9);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO', maxZoom: 18,
  }).addTo(map);

  const trackRes = await fetch('/api/wakashio-track').then(r => r.json());
  const track = trackRes.track;
  const reef = trackRes.reef;

  L.circleMarker([reef.lat, reef.lng], { radius: 9, color: '#34DFC4', fillColor: '#34DFC4', fillOpacity: 0.5 })
    .addTo(map).bindPopup(`${reef.name} (grounding site, July 2020)`);

  const fullLine = L.polyline(track.map(p => [p.lat, p.lng]), { color: '#5C7C81', weight: 2, dashArray: '3 7' }).addTo(map);
  const traveledLine = L.polyline([], { color: '#FF5A4E', weight: 3 }).addTo(map);
  const vesselMarker = L.marker([track[0].lat, track[0].lng], {
    icon: L.divIcon({ className: '', html: '<div style="width:18px;height:18px;border-radius:50%;background:#FF5A4E;border:2px solid #081820;box-shadow:0 0 0 6px rgba(255,90,78,0.25);"></div>', iconSize: [18, 18] }),
  }).addTo(map);

  map.fitBounds(fullLine.getBounds(), { padding: [40, 40] });

  const totalSteps = track.length;
  let step = 0;
  let playing = false;
  let timer = null;

  const timelineEl = document.getElementById('timeline');
  for (let i = 0; i < totalSteps; i++) {
    const seg = document.createElement('div');
    seg.className = 'timeline-step';
    seg.dataset.step = i;
    seg.addEventListener('click', () => { stop(); goTo(i); });
    timelineEl.appendChild(seg);
  }

  function riskColor(level) {
    return level === 'High' ? '#FF5A4E' : level === 'Medium' ? '#FFB020' : '#34DFC4';
  }
  function badgeClass(level) {
    return level === 'High' ? 'badge-high' : level === 'Medium' ? 'badge-med' : 'badge-low';
  }

  function updateTimelineUI() {
    document.getElementById('stepLabel').textContent = `Step ${step} / ${totalSteps - 1}`;
    [...timelineEl.children].forEach((el, i) => {
      el.classList.toggle('done', i < step);
      el.classList.toggle('active', i === step);
    });
  }

  function logEvent(text, tone) {
    const log = document.getElementById('eventLog');
    const li = document.createElement('li');
    li.className = 'done';
    li.innerHTML = tone ? `<span style="color:${tone}">${text}</span>` : text;
    log.appendChild(li);
    log.scrollTop = log.scrollHeight;
  }

  async function goTo(i) {
    step = Math.max(0, Math.min(i, totalSteps - 1));
    updateTimelineUI();

    const res = await fetch(`/api/wakashio-step/${step}`).then(r => r.json());
    const { point, vessel, risk, explanation, prediction, in_eez, final } = res;

    vesselMarker.setLatLng([point.lat, point.lng]);
    traveledLine.setLatLngs(track.slice(0, step + 1).map(p => [p.lat, p.lng]));
    map.panTo([point.lat, point.lng]);

    const statusPanel = document.getElementById('wakashioStatus');
    statusPanel.innerHTML = `
      <div class="flex-between">
        <h3 style="margin:0;">${vessel.name}</h3>
        <div class="badge ${badgeClass(risk.level)}"><span class="badge-dot"></span> ${risk.level} · ${risk.score}%</div>
      </div>
      <div class="result-row"><span>Speed / heading</span><span class="mono">${point.speed.toFixed(1)} kn / ${point.heading}°</span></div>
      <div class="result-row"><span>Distance to reef</span><span class="mono">${risk.reef_distance_km} km</span></div>
      <div class="result-row"><span>Lane deviation</span><span class="mono">${risk.deviation_km} km</span></div>
      <div class="result-row"><span>Grounding probability</span><span class="mono">${prediction.probability}%</span></div>
      <p class="small" style="margin-top:12px; background:rgba(52,223,196,0.06); border:1px solid rgba(52,223,196,0.2); border-radius:8px; padding:12px;">
        <strong style="color:var(--signal);">Gemma reasoning:</strong> ${explanation.narrative}
      </p>
    `;

    if (step === 0) logEvent('Vessel enters simulated tracking range, following standard approach heading.', null);
    if (step === 2 && in_eez) logEvent('⚑ AI Geo-Fence: vessel has entered the Mauritian EEZ.', '#FFB020');
    if (step === 3) logEvent(`⚑ Route deviation detected — vessel diverging from expected shipping corridor.`, '#FFB020');
    if (step === 5) logEvent(`⚑ Risk engine: score rising sharply as vessel nears reef (${risk.score}%).`, '#FF5A4E');
    if (step === 7) logEvent('⚑ Predictive analysis: grounding probability critical — alert dispatched to Coast Guard.', '#FF5A4E');
    if (final) logEvent('⚑ Simulated grounding at Pointe d\'Esny. NGO environmental task and citizen reporting now active.', '#FF5A4E');
  }

  document.getElementById('playBtn').addEventListener('click', () => { playing ? stop() : play(); });
  document.getElementById('resetBtn').addEventListener('click', () => { stop(); document.getElementById('eventLog').innerHTML = ''; goTo(0); });

  function play() {
    playing = true;
    document.getElementById('playBtn').textContent = '⏸ Pause';
    timer = setInterval(async () => {
      if (step >= totalSteps - 1) { stop(); return; }
      await goTo(step + 1);
    }, 1400);
  }
  function stop() {
    playing = false;
    document.getElementById('playBtn').textContent = '▶ Play';
    clearInterval(timer);
  }

  goTo(0);
});
