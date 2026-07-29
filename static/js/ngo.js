document.addEventListener('DOMContentLoaded', async () => {
  const reefBars = document.getElementById('reefBars');
  const coralTableBody = document.querySelector('#coralTable tbody');

  function scoreColor(score) {
    if (score >= 75) return 'var(--signal)';
    if (score >= 50) return 'var(--amber)';
    return 'var(--coral)';
  }

  async function loadReefs() {
    const res = await fetch('/api/reefs');
    const data = await res.json();
    reefBars.innerHTML = data.reefs.map(r => `
      <div style="margin-bottom:14px;">
        <div class="flex-between small"><span>${r.name}</span><span class="mono">${r.health}/100</span></div>
        <div style="height:8px;border-radius:6px;background:rgba(159,192,196,0.15);overflow:hidden;margin-top:5px;">
          <div style="height:100%;width:${r.health}%;background:${scoreColor(r.health)};border-radius:6px;"></div>
        </div>
      </div>
    `).join('');
  }

  function renderSamples(samples) {
    coralTableBody.innerHTML = samples.map(s => `
      <tr>
        <td>${s.site}</td>
        <td>${s.bleaching_pct}%</td>
        <td style="color:${scoreColor(s.score)}">${s.score}/100</td>
        <td class="muted">${s.submitted}</td>
      </tr>
    `).join('');
  }

  async function loadSamples() {
    const res = await fetch('/api/coral-samples');
    const data = await res.json();
    renderSamples(data.samples);
  }

  async function loadSummary() {
    const res = await fetch('/api/ngo-report');
    const data = await res.json();
    document.getElementById('ngoSummary').textContent = data.summary;
    document.getElementById('avgHealth').textContent = data.avg_health + '/100';
    document.getElementById('prioritySite').textContent = data.priority_site;
    document.getElementById('openIncidents').textContent = data.open_incidents;
  }

  loadReefs();
  loadSamples();
  loadSummary();

  document.getElementById('coralForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const site = document.getElementById('siteName').value;
    const resultBox = document.getElementById('coralResult');
    resultBox.innerHTML = '<div class="loading-text"><span class="spinner"></span> Running coral vision model…</div>';

    const res = await fetch('/api/coral-upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ site }),
    });
    const data = await res.json();
    await new Promise(r => setTimeout(r, 500));

    const s = data.sample;
    resultBox.innerHTML = `
      <div class="result-card show">
        <div class="small muted">Reef health score</div>
        <div class="conf" style="color:${scoreColor(s.score)}">${s.score}/100</div>
        <div class="result-row"><span>Bleaching estimate</span><span class="mono">${s.bleaching_pct}%</span></div>
        <div class="result-row"><span>Note</span><span class="mono" style="text-align:right; max-width:60%;">${s.note}</span></div>
      </div>`;
    loadSamples();
    loadSummary();
  });
});
