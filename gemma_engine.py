import json
import requests


import os
from dotenv import load_dotenv

load_dotenv()

GEMMA_API_KEY = os.getenv("GEMMA_API_KEY")


def build_fallback_reasoning(vessel, reef_analysis):
    vessel_name = vessel.get("VesselName", vessel.get("vessel_name", "Unknown"))
    mmsi = vessel.get("MMSI", vessel.get("mmsi", ""))
    reef_analysis = reef_analysis or {}
    trend = reef_analysis.get("reef_trend", "Unknown")
    distance = reef_analysis.get("closest_reef_distance_km")
    eta = reef_analysis.get("eta_hours_to_reef")

    if trend == "Approaching" and (eta is None or eta <= 1):
        risk = "high"
        action = "Immediate course adjustment recommended."
    elif trend == "Approaching":
        risk = "medium"
        action = "Monitor the vessel and reassess the approach."
    else:
        risk = "low"
        action = "Continue current course and monitor proximity."

    return {
        "vessel_name": vessel_name,
        "mmsi": str(mmsi),
        "collision_risk": risk,
        "confidence": calculate_confidence(reef_analysis),
        "reason": (
    f"Vessel is {trend.lower()} toward reef area. "
    f"Current distance is {distance} km with estimated arrival "
    f"in {eta} hours."
),        "reef_distance_km": distance,
        "reef_trend": trend,
        "eta_hours_to_reef": eta,
        "recommended_action": action,
    }


GEMMA_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemma-4-26b-a4b-it:generateContent"
)

def calculate_confidence(reef_analysis):

    confidence = 50

    if reef_analysis.get("reef_trend") == "Approaching":
        confidence += 20

    distance = reef_analysis.get(
        "closest_reef_distance_km",
        999
    )

    if distance < 5:
        confidence += 20

    if reef_analysis.get("eta_hours_to_reef") is not None:
        confidence += 5

    return min(confidence, 99)


def validate_gemma_response(result, reef_analysis):

    if not isinstance(result, dict):
        return build_fallback_reasoning(
            {},
            reef_analysis
        )

    result["reef_distance_km"] = reef_analysis.get(
        "closest_reef_distance_km"
    )

    result["eta_hours_to_reef"] = reef_analysis.get(
        "eta_hours_to_reef"
    )

    result["reef_trend"] = reef_analysis.get(
        "reef_trend"
    )

    return result

def generate_vessel_reasoning(vessel, reef_analysis):

    prompt = f"""
    You are BlueShield AI, a maritime environmental risk analyst.

    Analyse the vessel approaching reef data.

    IMPORTANT:
        - Use ONLY the provided reef_analysis values.
        - Do not invent coordinates.
- Do not change distance or ETA values.
- If ETA is very low, classify risk as high.

Return ONLY valid JSON.

Format:

{{
  "vessel_name": "",
  "mmsi": "",
  "collision_risk": "low|medium|high",
  "confidence": 0,
  "reason": "",
  "reef_distance_km": 0,
  "reef_trend": "",
  "eta_hours_to_reef": 0,
  "recommended_action": ""
}}

Vessel:
{json.dumps(vessel, indent=2)}

Reef analysis:
{json.dumps(reef_analysis, indent=2)}
"""

    headers = {
        "Content-Type": "application/json"
    }


    params = {
        "key": GEMMA_API_KEY
    }


    data = {

        "contents":[
            {
                "parts":[
                    {
                        "text":prompt
                    }
                ]
            }
        ]

    }


    try:
        print("CALLING GEMMA API...")
        print("KEY USED:", GEMMA_API_KEY[:10] if GEMMA_API_KEY else "NO KEY")
        response = requests.post(
            GEMMA_API_URL,
            headers=headers,
            params=params,
            json=data,
            timeout=8
        )

        print("HTTP Status:", response.status_code)
        print(response.text)

        response.raise_for_status()
        result = response.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        print("Gemma response:", text)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = text[start:end + 1]
                try:
                    return validate_gemma_response(
                        json.loads(candidate),
                        reef_analysis
                    )
                except json.JSONDecodeError:
                    pass

            # Try to extract the first balanced JSON object from the response
            brace_depth = 0
            json_start = None
            for index, char in enumerate(text):
                if char == "{":
                    if brace_depth == 0:
                        json_start = index
                    brace_depth += 1
                elif char == "}":
                    if brace_depth > 0:
                        brace_depth -= 1
                        if brace_depth == 0 and json_start is not None:
                            candidate = text[json_start:index + 1]
                            try:
                                return validate_gemma_response(
                                    json.loads(candidate),
                                    reef_analysis
                                )
                            except json.JSONDecodeError:
                                break
            return {
                "error": "Gemma returned invalid JSON",
                "raw_response": text,
            }

    except requests.Timeout:
        print("TIMEOUT - Using fallback")
        return build_fallback_reasoning(vessel, reef_analysis)

    except requests.RequestException as e:
        print("REQUEST ERROR:", e)
        print("Using fallback")
        return build_fallback_reasoning(vessel, reef_analysis)

    except Exception as e:
        print("GENERAL ERROR:", e)
        return {
            "error": "Gemma error",
            "message": str(e),
        }

