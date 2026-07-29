document.addEventListener('DOMContentLoaded', () => {
  const chips = document.querySelectorAll('#typeChips .chip');
  const description = document.getElementById('description');
  let seedText = '';

  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      chips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      seedText = chip.dataset.val;
      if (!description.value.trim()) {
        description.placeholder = `Describe the ${chip.textContent.toLowerCase()} in more detail…`;
      }
    });
  });
  chips[0].classList.add('active');
  seedText = chips[0].dataset.val;

  const form = document.getElementById('reportForm');
  const submitBtn = document.getElementById('submitBtn');
  const loadingRow = document.getElementById('loadingRow');
  const resultCard = document.getElementById('resultCard');
  const emptyState = document.getElementById('emptyState');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const desc = description.value.trim() || seedText;
    submitBtn.disabled = true;
    loadingRow.style.display = 'flex';
    resultCard.classList.remove('show');
    emptyState.style.display = 'none';

    try {
      const res = await fetch('/api/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: desc,
          lat: document.getElementById('lat').value,
          lng: document.getElementById('lng').value,
        }),
      });
      const data = await res.json();
      await new Promise(r => setTimeout(r, 550)); // let the analysis feel real

      document.getElementById('resultType').textContent = data.ai.category;
      document.getElementById('resultConf').textContent = data.ai.confidence + '%';
      document.getElementById('resultAuthority').textContent = data.ai.authority;
      document.getElementById('resultId').textContent = data.incident.id;
      document.getElementById('resultStatus').textContent = data.incident.status;
      resultCard.classList.add('show');
    } catch (err) {
      emptyState.textContent = 'Something went wrong reaching the analysis service. Please try again.';
      emptyState.style.display = 'block';
    } finally {
      loadingRow.style.display = 'none';
      submitBtn.disabled = false;
    }
  });

  // Marine education mini chat
  const eduLog = document.getElementById('eduLog');
  const eduInput = document.getElementById('eduInput');
  const eduSend = document.getElementById('eduSend');

  async function askEdu() {
    const q = eduInput.value.trim();
    if (!q) return;
    const userMsg = document.createElement('div');
    userMsg.className = 'chat-msg user';
    userMsg.textContent = q;
    eduLog.appendChild(userMsg);
    eduInput.value = '';
    eduLog.scrollTop = eduLog.scrollHeight;

    const aiMsg = document.createElement('div');
    aiMsg.className = 'chat-msg ai';
    aiMsg.innerHTML = '<span class="spinner"></span>';
    eduLog.appendChild(aiMsg);
    eduLog.scrollTop = eduLog.scrollHeight;

    try {
      const res = await fetch('/api/marine-education', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      });
      const data = await res.json();
      aiMsg.textContent = data.answer;
    } catch {
      aiMsg.textContent = "I couldn't reach the reasoning service — please try again.";
    }
    eduLog.scrollTop = eduLog.scrollHeight;
  }

  eduSend.addEventListener('click', askEdu);
  eduInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') askEdu(); });
});
