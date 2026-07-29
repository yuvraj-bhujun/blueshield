import json
import requests


GEMMA_API_KEY = "..."


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
        "confidence": 70,
        "reason": "Fallback reasoning generated locally while the remote Gemma service is unavailable.",
        "reef_distance_km": distance,
        "reef_trend": trend,
        "eta_hours_to_reef": eta,
        "recommended_action": action,
    }


GEMMA_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-3.1-flash-lite:generateContent"
)



def generate_vessel_reasoning(vessel, reef_analysis):

    prompt = f"""
        You are BlueShield AI, an expert maritime collision-risk analyst.

        Analyze the vessel and reef-analysis data provided below and generate a short, professional executive report paragraph summarizing the risk level and situation.

        STRICT OUTPUT RULES:
        - Output ONLY the raw text paragraph. 
        - Do NOT output JSON, markdown formatting (no **, no headers), bullet points, or code blocks.
        - Do NOT include intro/outro phrases (e.g., do NOT say "Here is the report:").
        - Write 3 to 4 clear, continuous English sentences suitable for direct translation and speech synthesis.

        PARAGRAPH REQUIREMENTS:
        1. State the vessel name, MMSI, current distance to reef (in km), and trend/ETA.
        2. State the assessed collision risk level (Low, Medium, or High) and the main cause.
        3. State the required immediate action for operators or coast guard.

        Vessel data:
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

        response = requests.post(
            GEMMA_API_URL,
            headers=headers,
            params=params,
            json=data,
            timeout=100
        )

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
                    return json.loads(candidate)
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
                                return json.loads(candidate)
                            except json.JSONDecodeError:
                                break
            return {
                "error": "Gemma returned invalid JSON",
                "raw_response": text,
            }

    except requests.Timeout:
        return build_fallback_reasoning(vessel, reef_analysis)

    except requests.RequestException as e:
        return build_fallback_reasoning(vessel, reef_analysis)

    except Exception as e:

        return {
            "error": "Gemma error",
            "message": str(e),
        }