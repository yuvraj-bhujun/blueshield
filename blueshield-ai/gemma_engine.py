"""
gemma_engine.py

BlueShield AI
Local Gemma model using Ollama
"""

import requests


OLLAMA_URL = "http://localhost:11434/api/generate"

MODEL_NAME = "gemma4:e2b"


def generate_vessel_reasoning(vessel, risk):


    prompt = f"""
You are BlueShield AI, an expert maritime collision-risk analyst.

Analyze the vessel and reef-analysis data below and generate a short professional executive risk report.

STRICT OUTPUT RULES:
- Output ONLY the final report.
- No JSON.
- No markdown formatting (no #, *, **, etc).
- Write the main analysis as exactly 3 to 4 sentences in a single paragraph.
- Then, on new lines, add the "Recommended Actions:" section with items
  "1) ..." and "2) ..." as described below — this is the ONLY place
  numbered items are allowed.
- Use professional Coast Guard language throughout.

Requirements:
1. Mention vessel name and MMSI.
2. Mention reef distance and trajectory trend.
3. State collision risk level and main cause.
4. Recommend immediate action.
5. Finish with exactly two concrete recommended follow-up actions, labeled
   "Recommended Actions:" followed by "1) ..." and "2) ...". These must be
   phrased generally enough to be actionable by EITHER a coast guard
   authority (e.g. patrol dispatch, vessel hailing, interception) OR an
   NGO / environmental responder (e.g. reef monitoring, community alert,
   pollution containment prep) — do not assume which type of reader will
   receive the report.

VESSEL:

Name:
{vessel.get("VesselName")}

MMSI:
{vessel.get("MMSI")}

Type:
{vessel.get("VesselType")}

Flag:
{vessel.get("Flag")}

Destination:
{vessel.get("Destination")}


NAVIGATION:

Speed:
{vessel.get("Speed")} knots

Heading:
{vessel.get("Heading")} degrees


RISK ENGINE:

Risk Level:
{risk.get("level")}

Risk Score:
{risk.get("score")}/100

Distance To Reef:
{risk.get("current_distance")} km

Trend:
{risk.get("trend")}

ETA:
{risk.get("eta")} hours

Closing Speed:
{risk.get("closing_speed")} km/h

Lane Deviation:
{risk.get("lane_deviation")} km

Inside Reef:
{risk.get("inside_reef")}

Generate the final report.
"""


    payload = {

        "model": MODEL_NAME,

        "prompt": prompt,

        "stream": False

    }


    try:

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=120
        )


        result = response.json()


        return result.get(
            "response",
            "No report generated."
        )


    except Exception as e:

        return f"Local Gemma error: {str(e)}"