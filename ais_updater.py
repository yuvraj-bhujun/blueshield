import threading
import time

from services.myshiptracking import get_live_vessels
from services.vessel_memory import update_tracks, attach_tracks


latest_vessels = []


UPDATE_INTERVAL = 300   # 5 minutes


def update_ais():

    global latest_vessels

    while True:

        try:

            print("Updating AIS positions...")

            vessels = get_live_vessels()

            update_tracks(vessels)

            vessels = attach_tracks(vessels)


            latest_vessels = vessels


            print(
                "Updated vessels:",
                len(vessels)
            )


        except Exception as e:

            print(
                "AIS update error:",
                e
            )


        time.sleep(UPDATE_INTERVAL)



def start_ais_updater():

    thread = threading.Thread(
        target=update_ais,
        daemon=True
    )

    thread.start()



def get_latest_vessels():

    return latest_vessels