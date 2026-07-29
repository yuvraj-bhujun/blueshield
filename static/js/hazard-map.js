document.addEventListener('DOMContentLoaded', async () => {
  const map = L.map('hazardMap', { zoomControl: true }).setView([-20.348, 57.552], 10);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    maxZoom: 18,
  }).addTo(map);

  function pulseIcon(color) {
    return L.divIcon({
      className: '',
      html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};box-shadow:0 0 0 4px ${color}33;border:2px solid #081820;"></div>`,
      iconSize: [14, 14],
    });
  }

  const [reefsRes, incidentsRes] = await Promise.all([
    fetch('/api/reefs').then(r => r.json()),
    fetch('/api/incidents').then(r => r.json()),
  ]);

  reefsRes.reefs.forEach(r => {
    L.marker([r.lat, r.lng], { icon: pulseIcon('#34DFC4') })
      .addTo(map)
      .bindPopup(`<strong>${r.name}</strong><br>Health score: ${r.health}/100<br>Status: ${r.status}`);
  });

  reefsRes.mpas.forEach(m => {
    L.circle([m.lat, m.lng], {
      radius: m.radius_km * 1000, color: '#FFB020', fillColor: '#FFB020', fillOpacity: 0.08, weight: 1.4,
    }).addTo(map).bindPopup(`<strong>${m.name}</strong><br>Marine Protected Area`);
  });

  function renderIncidents(incidents) {
    incidents.forEach(i => {
      L.marker([i.lat, i.lng], { icon: pulseIcon('#FF5A4E') })
        .addTo(map)
        .bindPopup(`<strong>${i.type}</strong><br>Confidence: ${i.confidence}%<br>${i.authority}<br><em>${i.status}</em>`);
    });

    const feed = document.getElementById('incidentFeed');
    feed.innerHTML = incidents.slice(0, 6).map(i => `
      <div class="incident-item">
        <div class="incident-icon">⚠</div>
        <div class="incident-body">
          <h4>${i.type}</h4>
          <div class="meta">${i.id} · ${timeAgo(i.reported_at)} · ${i.confidence}% confidence</div>
          <p>${i.description}</p>
        </div>
      </div>
    `).join('');
  }

  renderIncidents(incidentsRes.incidents);
});
