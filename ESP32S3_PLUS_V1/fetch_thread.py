# fetch_thread.py — Background Fetch Worker
import time
import _thread

from get_departures import get_data, ensure_wifi

def start_fetch_thread(shared, data_lock, wifi_ssid, wifi_pass,
                       stop_id_1, limit_1, line_no_1, platform_1,
                       stop_id_2, limit_2, line_no_2, platform_2,
                       refresh_s,
                       should_beep_fn=None):
    """
    should_beep_fn(): optional callback -> bool (wenn True, kann main beep auslösen)
    """
    def worker():
        first_done = False
        while True:
            r1 = None
            r2 = None
            err = None

            try:
                ensure_wifi(wifi_ssid, wifi_pass, tries=1)

                r1 = get_data(stop_id_1, limit_1, line_no_1, platform_1)
                if should_beep_fn and should_beep_fn():
                    pass

                r2 = get_data(stop_id_2, limit_2, line_no_2, platform_2)
                if should_beep_fn and should_beep_fn():
                    pass

            except Exception as e:
                err = repr(e)

            data_lock.acquire()
            try:
                shared["r1"] = r1
                shared["r2"] = r2
                shared["err"] = err
                shared["seq"] += 1
                if not first_done:
                    shared["ready"] = True
                    first_done = True
            finally:
                data_lock.release()

            time.sleep(refresh_s)

    _thread.start_new_thread(worker, ())
