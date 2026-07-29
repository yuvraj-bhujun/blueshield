# BlueShield AI — Flask Edition

An AI-powered Maritime Domain Awareness prototype for Mauritius' EEZ, built with **Flask**
(server-rendered Jinja2 templates + vanilla JS) instead of React, per the original spec.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000**.

## Live vessel tracking (free, real AIS data)

The Coast Guard dashboard now shows **real ships**, not just the scripted demo
fleet, using [AISStream.io](https://aisstream.io) — a free, real-time AIS
data stream over WebSocket. No credit card, no paid tier.

**Setup (2 minutes):**

1. Go to https://aisstream.io and sign up — you get a free API key instantly.
2. Set it as an environment variable before running the app:
   ```bash
   export AISSTREAM_API_KEY="your-key-here"      # Windows (PowerShell): $env:AISSTREAM_API_KEY="your-key-here"
   python app.py
   ```
3. Open `/coastguard` — the banner above the map will switch from
   "not configured" to "Live AIS feed connected — N real vessels in range"
   once the first position reports arrive (usually within a few seconds,
   depending on how much traffic is actually near Mauritius at that moment).

**How it works:**

- `ais_feed.py` runs a background thread with its own asyncio event loop,
  staying connected to `wss://stream.aisstream.io/v0/stream`, subscribed to
  a bounding box around Mauritius. It keeps an in-memory cache of the latest
  position report per vessel (MMSI), reconnecting automatically with
  backoff if the connection drops.
- `/api/vessels` merges that live cache with the simulated demo fleet, runs
  the same risk-scoring engine (`score_vessel`) over both, and tags each
  vessel with `"source": "live"` or `"source": "simulated"` so the frontend
  can show a `LIVE AIS` / `SIM` badge and a distinct marker ring on the map.
- If the key isn't set, or there's no traffic in range at that moment, the
  app falls back to the simulated fleet with no errors — `/api/ais-status`
  always reports what's actually happening so you're not left guessing
  during a demo.
- **Coverage note:** AISStream's feed depends on ground-station and
  satellite AIS receivers actually near Mauritius at the time you run it.
  If real traffic is sparse when you demo, that's expected — the simulated
  fleet keeps the dashboard populated regardless, clearly labeled `SIM`.

If you'd rather not create an account at all, just skip the env var — the
app runs exactly as before, on the simulated fleet only.

## What's inside

- `app.py` — Flask routes, in-memory demo data, and rule-based "AI" logic
  (`classify_report`, `score_vessel`, `explain_vessel`, `grounding_prediction`)
  standing in for Gemma 4 / YOLOv11 inference. Swap these for real model calls
  to go from demo to production.
- `ais_feed.py` — background AISStream.io WebSocket listener providing free,
  real-time vessel positions (see "Live vessel tracking" above).
- `templates/` — one template per portal:
  - `index.html` — landing page (radar-sweep hero, actor overview, architecture)
  - `report.html` — public incident reporting + marine education Q&A
  - `map.html` — coastal hazard map (Leaflet)
  - `ngo.html` — coral health monitoring + environmental dashboard
  - `coastguard.html` — maritime intelligence dashboard + AI investigation assistant
  - `wakashio.html` — the Wakashio replay demo scenario
- `static/css/style.css` — single stylesheet, dark "ocean/sonar" design system
- `static/js/*.js` — one file per page: map rendering, polling, and AI-panel wiring

## Notes for extending toward production

- Replace the rule-based functions in `app.py` with calls to Gemma 4 (text/vision)
  and a YOLOv11 detector for oil-spill / vessel / coral image analysis.
- Swap the in-memory lists (`INCIDENTS`, `CORAL_SAMPLES`, `VESSEL_STATE`) for
  PostgreSQL + PostGIS, as in the original architecture spec.
- `/api/vessels` is already wired to a real, free AIS feed (AISStream.io) —
  for production you'd likely add a paid/higher-coverage AIS provider and
  persist history instead of only keeping the latest report per vessel.
- Add authentication for the NGO and Coast Guard portals before any real deployment.
