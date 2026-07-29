import requests


API_KEY = "x48UtXu2y%6lbmQieD7ve%tOwbaQaMeKDh."

BASE_URL = "https://api.myshiptracking.com/api/v2"


def get_live_vessels():

    url = f"{BASE_URL}/vessel/zone"

    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    params = {
        "minlon": "57.0",
        "maxlon": "58.3",
        "minlat": "-20.8",
        "maxlat": "-19.6",
        "minutesBack": "60",
        "response": "simple"
    }


    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=10
    )


    print("STATUS:", response.status_code)


    data = response.json()


    # ADD PRINT HERE ↓

    print(type(data))
    print(data)


    if response.status_code != 200:

        return []


    vessels = data.get(
        "data",
        []
    )


    # ADD PRINT HERE ↓

    print(type(vessels))
    print(vessels)


    return vessels