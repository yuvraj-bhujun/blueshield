"""
vessel_memory.py

Stores AIS vessel movement history.
Used by BlueShield AI to calculate:
- vessel trajectory
- reef approach
- risk prediction
"""

from datetime import datetime, timezone


MAX_HISTORY = 20


# MMSI -> list of positions
vessel_tracks = {}



def update_tracks(vessels):
    """
    Update memory with latest AIS API results.

    Input example:

    [
        {
            "mmsi":636021544,
            "lat":-20.13,
            "lng":57.35,
            "speed":13.3,
            "course":265
        }
    ]

    """

    for vessel in vessels:

        mmsi = str(vessel["mmsi"])


        position = {

            "lat": vessel["lat"],

            "lng": vessel["lng"],

            "speed": vessel.get("speed",0),

            "course": vessel.get("course",0),

            "time": datetime.now(
                timezone.utc
            ).isoformat()

        }


        if mmsi not in vessel_tracks:

            vessel_tracks[mmsi] = []


        vessel_tracks[mmsi].append(position)



        # Keep only latest 20 points

        vessel_tracks[mmsi] = (
            vessel_tracks[mmsi][-MAX_HISTORY:]
        )



def attach_tracks(vessels):
    """
    Attach historical tracks to current vessels.

    Converts:

    {
      mmsi:123,
      lat:...
    }

    into:

    {
      mmsi:123,
      track:[
          previous positions
      ]
    }

    """

    for vessel in vessels:

        mmsi = str(vessel["mmsi"])


        vessel["track"] = vessel_tracks.get(
            mmsi,
            []
        )


    return vessels



def get_vessel_track(mmsi):

    return vessel_tracks.get(
        str(mmsi),
        []
    )