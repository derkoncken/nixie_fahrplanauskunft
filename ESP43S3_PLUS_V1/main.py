# main.py — VRR/EFA -> Waveshare 2.9" E-Ink Anzeige (Querformat, Rotation 90°)
import gc
import time

from print_tt import get_data
from ink import EPD29V2, rotated_pixel_90, print_text
from helper import split_string, normalize_text

WIFI_SSID = "ich_mag_kein_gurkenwasser"
WIFI_PASS = "gurkenhuette187!"

LIMIT         = "4"

STOP_ID_701   = "20018098"
LINE_NO_701   = "701"
PLATFORM_701  = "4"

REFRESH_S = 10


def render_701(epd, pix, countdown, direction, planned, real, delay):
    epd.fb.fill(1)

    # Linienbezeichnung
    print_text(epd.fb, pix, LINE_NO_701, 0, 5, size=3, bold=True)

    # Zielhaltestelle
    direction = normalize_text(direction)
    s1, s2 = split_string(direction, 23)
    print_text(epd.fb, pix, s1, 100, 5, size=1, bold=False)
    if s2:
        print_text(epd.fb, pix, s2, 100, 20, size=1, bold=False)

    # Abfahrtszeit (real)
    print_text(epd.fb, pix, real, 0, 35, size=2, bold=True)

    # Countdown
    print_text(epd.fb, pix, "-> {} min".format(countdown), 100, 35, size=2, bold=True)

    epd.display()


def render_error(epd, pix, msg="Fehler"):
    epd.fb.fill(1)
    print_text(epd.fb, pix, msg, 10, 10, size=2, bold=True)
    epd.display()


def main():
    epd = EPD29V2()
    pix = rotated_pixel_90(epd.fb, epd.W, epd.H)

    last_state = None

    while True:
        gc.collect()
        try:
            result = get_data(WIFI_SSID, WIFI_PASS, STOP_ID_701, LIMIT, LINE_NO_701, PLATFORM_701) # Latenz: 1,27s
        except Exception as e:
            # Nur anzeigen, wenn sich auch der Fehlertext ändert
            state = "ERR|" + repr(e)
            if state != last_state:
                render_error(epd, pix, "Fehler")
                last_state = state
            time.sleep(REFRESH_S)
            continue

        if result is None:
            state = "NONE"
            if state != last_state:
                epd.fb.fill(1)
                print_text(epd.fb, pix, "Keine Abfahrt", 10, 10, size=2, bold=True)
                epd.display()
                last_state = state
            time.sleep(REFRESH_S)
            continue

        countdown, direction, planned, real, delay = result

        # >>> Das ist der entscheidende Vergleich:
        # Nimm genau die Felder, die auf dem Display stehen.
        direction_norm = normalize_text(direction)
        state = "701|{}|{}|{}|{}".format(countdown, direction_norm, real, delay)

        if state != last_state:
            render_701(epd, pix, countdown, direction_norm, planned, real, delay)
            last_state = state

        time.sleep(REFRESH_S)


main()
