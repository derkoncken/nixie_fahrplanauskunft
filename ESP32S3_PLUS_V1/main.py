# main.py — VRR/EFA -> Waveshare 2.9" E-Ink Anzeige (Querformat, Rotation 90°)
import gc
import time
import micropython
import _thread

from display_driver import EPD29V2, rotated_pixel_90
from helper import normalize_text

from app_config import (
    REFRESH_S,
    ENABLE_FULL_REFRESH,
    PARTIALS_PER_FULL,
    BTN_GPIO, LED_GPIO, BUZ_GPIO,
    read_runtime_config,
)
from render_ui import (
    render_loading_screen, render_error_fullscreen, redraw_full
)
from display_updates import (
    update_time_and_countdown_partial,
    make_full_state, make_time_state
)
from alarm_io import AlarmIO
from fetch_thread import start_fetch_thread


def log_mem(tag=""):
    try:
        gc.collect()
        print("\n[MEM] {} free={} alloc={}".format(tag, gc.mem_free(), gc.mem_alloc()))
        micropython.mem_info()
    except Exception as e:
        print("[MEM] mem_info failed:", repr(e))


def main():
    cfg = read_runtime_config()

    STOP_ID_1 = cfg["STOP_ID_1"]; LINE_NO_1 = cfg["LINE_NO_1"]; PLATFORM_1 = cfg["PLATFORM_1"]; LIMIT_1 = cfg["LIMIT_1"]
    STOP_ID_2 = cfg["STOP_ID_2"]; LINE_NO_2 = cfg["LINE_NO_2"]; PLATFORM_2 = cfg["PLATFORM_2"]; LIMIT_2 = cfg["LIMIT_2"]
    WIFI_SSID = cfg["WIFI_SSID"]; WIFI_PASS = cfg["WIFI_PASS"]
    ALARM_SOURCE = cfg["ALARM_SOURCE"]; ALARM_THRESHOLD_MIN = cfg["ALARM_THRESHOLD_MIN"]

    # Display
    epd = EPD29V2()
    pix = rotated_pixel_90(epd.fb, epd.W, epd.H)

    # IO/Alarm
    aio = AlarmIO(BTN_GPIO, LED_GPIO, BUZ_GPIO)

    print("\n=== START ===")
    print("[CFG] line1={}, stop1={}, pf1={}, lim1={}".format(LINE_NO_1, STOP_ID_1, PLATFORM_1, LIMIT_1))
    print("[CFG] line2={}, stop2={}, pf2={}, lim2={}".format(LINE_NO_2, STOP_ID_2, PLATFORM_2, LIMIT_2))
    print("[CFG] alarm_source={}, alarm_threshold={}min".format(ALARM_SOURCE, ALARM_THRESHOLD_MIN))
    print("[POLICY] ENABLE_FULL_REFRESH={}, PARTIALS_PER_FULL={}".format(ENABLE_FULL_REFRESH, PARTIALS_PER_FULL))
    log_mem("boot")

    # Startsequenz: immer Full (sauberer Start + RAM sync)
    render_loading_screen(epd, pix, LINE_NO_1, LINE_NO_2)

    # Shared State für Fetch-Thread
    data_lock = _thread.allocate_lock()
    shared = {"r1": None, "r2": None, "err": None, "seq": 0, "ready": False}

    start_fetch_thread(
        shared, data_lock,
        WIFI_SSID, WIFI_PASS,
        STOP_ID_1, LIMIT_1, LINE_NO_1, PLATFORM_1,
        STOP_ID_2, LIMIT_2, LINE_NO_2, PLATFORM_2,
        REFRESH_S
    )

    last_seq = -1
    last_full_state = None
    last_time_state = None

    # zählt nur Partial-Updates (für optionales Full)
    partial_since_full = 0

    while True:
        gc.collect()

        # Button -> Alarm togglen
        if aio.arm_request:
            aio.arm_request = False
            if aio.alarm_armed:
                aio.disarm()
                print("[ALARM] entschaerft")
            else:
                aio.arm()
                print("[ALARM] scharf (Schwelle: <{} min)".format(ALARM_THRESHOLD_MIN))

        # LED tick
        aio.tick_led()

        # Daten holen
        data_lock.acquire()
        try:
            seq = shared["seq"]
            r1 = shared["r1"]
            r2 = shared["r2"]
            err = shared["err"]
            ready = shared["ready"]
        finally:
            data_lock.release()

        if not ready:
            time.sleep_ms(20)
            continue

        if seq != last_seq:
            last_seq = seq

            if err is not None:
                state_err = "ERR|" + err
                if state_err != last_full_state:
                    render_error_fullscreen(epd, pix, "WLAN/Request Fehler")
                    last_full_state = state_err
                    last_time_state = None
                    partial_since_full = 0
            else:
                # Alarm-Logik (Display unabhängig)
                aio.apply_alarm_logic(r1, r2, ALARM_SOURCE, ALARM_THRESHOLD_MIN)
                aio.tick_led()

                # States
                full_state = (
                    make_full_state(LINE_NO_1, r1, normalize_text) +
                    "||" +
                    make_full_state(LINE_NO_2, r2, normalize_text)
                )
                time_state = (
                    make_time_state(LINE_NO_1, r1) +
                    "||" +
                    make_time_state(LINE_NO_2, r2)
                )

                # ---- Änderung: Layout/Content-Änderung => Full ist stabilitätskritisch ----
                layout_changed = (full_state != last_full_state)

                # 1) Layout/Content geändert -> Full immer (für Stabilität)
                if layout_changed:
                    redraw_full(epd, pix, LINE_NO_1, LINE_NO_2, r1, r2)
                    last_full_state = full_state
                    last_time_state = time_state
                    partial_since_full = 0

                # 2) Nur Zeit/Countdown geändert -> immer Partial (deine Regel)
                elif time_state != last_time_state:
                    if r1 is not None:
                        cd, direction, planned, real, delay = r1
                        update_time_and_countdown_partial(epd, pix, y_offset=5, real=real, countdown=cd)
                    if r2 is not None:
                        cd, direction, planned, real, delay = r2
                        update_time_and_countdown_partial(epd, pix, y_offset=70, real=real, countdown=cd)

                    last_time_state = time_state
                    partial_since_full += 1

                    # Optionaler Hygiene-Full nach N Partials (nur wenn global erlaubt)
                    if ENABLE_FULL_REFRESH and PARTIALS_PER_FULL and PARTIALS_PER_FULL > 0:
                        if partial_since_full >= PARTIALS_PER_FULL:
                            redraw_full(epd, pix, LINE_NO_1, LINE_NO_2, r1, r2)
                            partial_since_full = 0
                            last_full_state = full_state
                            last_time_state = time_state

        time.sleep_ms(20)


main()
