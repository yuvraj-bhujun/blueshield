import requests


GEMMA_API_KEY = "AQ.Ab8RN6KOksLjaVx1ZrW4ovgGgR26GviNWSzNDgczw2Pwps_9hA"


GEMMA_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemma-4-26b-a4b-it:generateContent"
)



def generate_vessel_reasoning(vessel, risk):

    prompt = f"""
    You are BlueShield AI, a Maritime Intelligence Analyst assisting a Coast Guard command centre.

    Generate a professional maritime risk assessment report based ONLY on the vessel information and risk engine data provided below.

    OUTPUT RULES:
    - Do not use markdown symbols such as *, **, -, or bullet points.
    - Do not use emojis.
    - Do not repeat the raw input data.
    - Use numbered sections and clear headings.
    - Write in a professional maritime intelligence style.
    - Do not invent missing information.
    - If information is unavailable, state that it is unavailable.
    - If the automated risk score conflicts with trajectory behaviour, highlight the difference and explain why.

    ================================================

    VESSEL INFORMATION

    Vessel Name:
    {vessel['VesselName']}

    MMSI:
    {vessel['MMSI']}

    IMO:
    {vessel['IMO']}

    Vessel Type:
    {vessel['VesselType']}

    Flag:
    {vessel['Flag']}

    Cargo:
    {vessel['Cargo']}

    Destination:
    {vessel['Destination']}


    NAVIGATION INFORMATION

    Speed:
    {vessel['Speed']} knots

    Heading:
    {vessel['Heading']} degrees

    Draft:
    {vessel['Draft']} metres


    ================================================

    RISK ENGINE DATA

    Risk Level:
    {risk['level']}

    Risk Score:
    {risk['score']}/100

    Distance From Coral Reef:
    {risk['current_distance']} km

    Trajectory History:
    {risk['history']}

    Trend:
    {risk['trend']}

    Closing Speed:
    {risk['closing_speed']}

    Estimated Time To Reef:
    {risk['eta']} hours

    Lane Deviation:
    {risk['lane_deviation']} km

    Inside Reef:
    {risk['inside_reef']}


    ================================================

    GENERATE THE REPORT USING THIS STRUCTURE:

    BLUE SHIELD AI - MARITIME INTELLIGENCE REPORT


    1. EXECUTIVE SUMMARY

    Provide a concise summary of the vessel's current situation.
    Mention the automated risk level and whether the vessel requires monitoring.


    2. RISK ASSESSMENT ANALYSIS

    Analyse the risk score using only the available indicators.

    Explain:
    - What the current risk level means.
    - Whether the vessel is moving closer or further away from the reef.
    - The importance of reef distance, trend, closing speed, ETA, and lane deviation.
    - Whether the vessel presents an increasing or decreasing risk.


    3. CORAL REEF AND ENVIRONMENTAL RISK

    Assess the potential environmental impact if the vessel continues towards sensitive marine areas.

    Consider:
    - Possibility of grounding.
    - Potential coral reef damage.
    - Consequences of a large vessel entering shallow reef areas.

    Do not assume pollution or cargo risks unless supported by the provided data.


    4. COAST GUARD MONITORING PRIORITIES

    Recommend what should be monitored based on the available information.

    Include:
    - AIS position updates.
    - Vessel heading and speed changes.
    - Distance from coral reefs.
    - Changes in trajectory trend.
    - Increasing lane deviation.


    5. RECOMMENDED ACTIONS

    Separate recommendations into:

    Immediate Monitoring:
    Actions required based on the current vessel situation.

    Preventive Measures:
    Actions to reduce potential future risk.

    Escalation Criteria:
    Conditions that would justify intervention, such as decreasing reef distance, increasing deviation, or entering restricted areas.


    6. FINAL INTELLIGENCE JUDGEMENT

    Provide a final assessment stating:
    - Overall maritime threat level.
    - Main risk factor.
    - Whether continued monitoring or intervention is recommended.


    Use professional terms where appropriate:
    Dynamic Risk Assessment,
    Maritime Domain Awareness,
    AIS Monitoring,
    Navigational Deviation,
    Grounding Risk,
    Environmental Protection.

    Return only the final report.
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
            json=data
        )


        result = response.json()


        return result["candidates"][0]["content"]["parts"][0]["text"]


    except Exception as e:

        return f"Gemma error: {e}"