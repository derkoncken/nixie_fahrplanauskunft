# main.py — VRR/EFA -> Waveshare 2.9" E-Ink Anzeige (Querformat, Rotation 90°)
import gc
import time
import sys
import micropython

from print_tt import get_data, wifi_connect
from ink import EPD29V2, rotated_pixel_90, print_text
from helper import split_string, normalize_text

WIFI_SSID = "ich_mag_kein_gurkenwasser"
WIFI_PASS = "gurkenhuette187!"

# 1) 701
STOP_ID_701  = "20018098"
LINE_NO_701  = "701"
PLATFORM_701 = "4"
LIMIT_701    = "10"

# 2) S6
STOP_ID_S6   = "20018235"
LINE_NO_S6   = "S6"
PLATFORM_S6  = "11"
LIMIT_S6     = "100"

REFRESH_S = 10


def log_mem(tag=""):
    try:
        gc.collect()
        print("\n[MEM] {} free={} alloc={}".format(tag, gc.mem_free(), gc.mem_alloc()))
        micropython.mem_info()
    except Exception as e:
        print("[MEM] mem_info failed:", repr(e))


def render_card(epd, pix, line_no, countdown, direction, planned, real, delay, y_offset):
    print_text(epd.fb, pix, line_no, 0, 5 + y_offset, size=3, bold=True)

    direction = normalize_text(direction)
    s1, s2 = split_string(direction, 23)
    print_text(epd.fb, pix, s1, 100, 5 + y_offset, size=1, bold=False)
    if s2:
        print_text(epd.fb, pix, s2, 100, 20 + y_offset, size=1, bold=False)

    print_text(epd.fb, pix, real, 0, 35 + y_offset, size=2, bold=False)
    print_text(epd.fb, pix, "-> {} min".format(countdown), 100, 35 + y_offset, size=2, bold=False)


def render_none_card(epd, pix, line_no, msg, y_offset):
    print_text(epd.fb, pix, line_no, 0, 5 + y_offset, size=3, bold=True)
    print_text(epd.fb, pix, msg, 100, 12 + y_offset, size=1, bold=True)


def render_error_fullscreen(epd, pix, msg="Fehler"):
    epd.fb.fill(1)
    print_text(epd.fb, pix, msg, 10, 10, size=2, bold=True)
    epd.display()


def make_state(tag, result):
    if result is None:
        return tag + "|NONE"
    countdown, direction, planned, real, delay = result
    direction_norm = normalize_text(direction)
    return "{}|{}|{}|{}|{}".format(tag, countdown, direction_norm, real, delay)


def draw_hline(pix, x0, x1, y, color=0):
    for x in range(x0, x1 + 1):
        pix(x, y, color)


def ensure_wifi():
    # versucht reconnect, ohne Endlosschleife im Fehlerfall
    for _ in range(3):
        try:
            wifi_connect(WIFI_SSID, WIFI_PASS)
            return True
        except Exception:
            time.sleep(1)
    return False


def main():
    epd = EPD29V2()
    pix = rotated_pixel_90(epd.fb, epd.W, epd.H)

    last_state = None

    print("\n=== START ===")
    log_mem("boot")

    # WLAN einmal initial verbinden
    if not ensure_wifi():
        render_error_fullscreen(epd, pix, "WLAN Fehler")

    while True:
        gc.collect()
        try:
            # get_data hat jetzt KEINE SSID/PASS mehr
            print(time.time())
            r_701 = get_data(STOP_ID_701, LIMIT_701, LINE_NO_701, PLATFORM_701)
            r_s6  = get_data(STOP_ID_S6,  LIMIT_S6,  LINE_NO_S6,  PLATFORM_S6)
            print(time.time())
        except Exception as e:
            print("\n[ERR] request crashed!")
            print("[ERR] type:", type(e))
            print("[ERR] repr:", repr(e))
            try:
                sys.print_exception(e)
            except Exception:
                pass
            log_mem("after exception")

            # Versuch: WLAN wiederherstellen
            ensure_wifi()

            state = "ERR|" + repr(e)
            if state != last_state:
                render_error_fullscreen(epd, pix, "Fehler")
                last_state = state

            time.sleep(REFRESH_S)
            continue

        state = make_state("701", r_701) + "||" + make_state("S6", r_s6)

        if state != last_state:
            epd.fb.fill(1)
            draw_hline(pix, 0, 295, 65, color=0)

            if r_701 is None:
                render_none_card(epd, pix, LINE_NO_701, "Keine Abfahrt", y_offset=5)
            else:
                cd, direction, planned, real, delay = r_701
                render_card(epd, pix, LINE_NO_701, cd, direction, planned, real, delay, y_offset=5)

            if r_s6 is None:
                render_none_card(epd, pix, LINE_NO_S6, "Keine Abfahrt", y_offset=70)
            else:
                cd, direction, planned, real, delay = r_s6
                render_card(epd, pix, LINE_NO_S6, cd, direction, planned, real, delay, y_offset=70)

            epd.display()
            last_state = state

        time.sleep(REFRESH_S)


main()
