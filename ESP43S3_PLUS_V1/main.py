# main.py — VRR/EFA -> Waveshare 2.9" E-Ink Anzeige (Querformat, Rotation 90°)
import gc
import time
import sys
import micropython
import socket
import _thread
from machine import Pin, PWM

BTN_GPIO = 43
LED_GPIO = 44
BUZ_GPIO = 6

from get_departures import get_data, ensure_wifi
from display_driver import EPD29V2, rotated_pixel_90, print_text
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
LIMIT_S6     = "70"

REFRESH_S = 10

# ---------- Alarm/LED/Buzzer ----------
ALARM_THRESHOLD_MIN = 200      # Alarm wird ausgelöst wenn Countdown < ALARM_THRESHOLD_MIN Minuten

alarm_armed = False          # scharfgestellt?
alarm_triggered = False      # <ALARM_THRESHOLD_MIN schon ausgelöst?
last_cd_701 = None

blink_enabled = False
blink_state = 0
blink_last_ms = 0
BLINK_INTERVAL_MS = 250

BEEP_MS = 140
BEEP_FREQ = 880
BEEP_DUTY = 5000

# ---------- Pins ----------
button = Pin(BTN_GPIO, Pin.IN)  # extern Pull-Down: gedrückt = 1
led = Pin(LED_GPIO, Pin.OUT)
led.value(0)

pwm = PWM(Pin(BUZ_GPIO))
pwm.freq(BEEP_FREQ)
pwm.duty_u16(0)  # aus

# ---------- Button-IRQ -> nur Flag setzen (und LED sofort an als Feedback) ----------
_DEBOUNCE_MS = 200
_last_irq_ms = 0
_arm_request = False

def _btn_irq(pin):
    global _last_irq_ms, _arm_request
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_irq_ms) < _DEBOUNCE_MS:
        return
    _last_irq_ms = now

    if pin.value() == 1:
        _arm_request = True
        # sofortiges Feedback (kurz & sicher)
        led.value(1)

button.irq(trigger=Pin.IRQ_RISING, handler=_btn_irq)

def _beep_once():
    pwm.freq(BEEP_FREQ)
    pwm.duty_u16(BEEP_DUTY)
    time.sleep_ms(BEEP_MS)
    pwm.duty_u16(0)
    time.sleep_ms(BEEP_MS)
    pwm.duty_u16(BEEP_DUTY)
    time.sleep_ms(BEEP_MS)
    pwm.duty_u16(0)

def _disarm_alarm():
    """Alarm vollständig aus + LED aus."""
    global alarm_armed, alarm_triggered, blink_enabled, blink_state
    alarm_armed = False
    alarm_triggered = False
    blink_enabled = False
    blink_state = 0
    led.value(0)

def _arm_alarm():
    """Alarm scharf + LED an (nicht blinkend)."""
    global alarm_armed, alarm_triggered, blink_enabled, blink_state, blink_last_ms, last_cd_701
    alarm_armed = True
    alarm_triggered = False
    blink_enabled = False
    blink_state = 0
    blink_last_ms = time.ticks_ms()
    last_cd_701 = None
    led.value(1)

def _set_led_logic():
    """LED je nach Zustand setzen (dauerhaft / blink / aus)."""
    global blink_state, blink_last_ms

    if not alarm_armed:
        led.value(0)
        return

    if not blink_enabled:
        led.value(1)
        return

    # blink
    now = time.ticks_ms()
    if time.ticks_diff(now, blink_last_ms) >= BLINK_INTERVAL_MS:
        blink_last_ms = now
        blink_state ^= 1
        led.value(blink_state)

# ---------- Shared State für Thread (Main liest nur, Worker schreibt) ----------
data_lock = _thread.allocate_lock()
shared = {
    "r701": None,
    "rs6": None,
    "err": None,
    "seq": 0,   # hochzählen wenn neue Daten da sind
}

def _should_beep_after_fetch():
    """Nur piepen, wenn Alarm bereits getriggert ist (blink läuft)."""
    # alarm_triggered ist global; lesen ist ok
    return alarm_triggered

def fetch_worker():
    """Läuft im Hintergrund: WLAN sicherstellen + get_data() ausführen.
       NICHTS am Display machen (nur Daten holen)!"""
    global shared

    while True:
        r701 = None
        rs6 = None
        err = None

        try:
            ensure_wifi(WIFI_SSID, WIFI_PASS, tries=1)

            print("Get Data...")
            r701 = get_data(STOP_ID_701, LIMIT_701, LINE_NO_701, PLATFORM_701)
            if _should_beep_after_fetch():
                _beep_once()  # <- nur wenn Alarm getriggert ist

            rs6  = get_data(STOP_ID_S6,  LIMIT_S6,  LINE_NO_S6,  PLATFORM_S6)
            if _should_beep_after_fetch():
                _beep_once()  # <- nur wenn Alarm getriggert ist

            print("Found Data!")
        except Exception as e:
            err = repr(e)

        data_lock.acquire()
        try:
            shared["r701"] = r701
            shared["rs6"] = rs6
            shared["err"] = err
            shared["seq"] += 1
        finally:
            data_lock.release()

        time.sleep(REFRESH_S)

# ---------- Render Helpers ----------
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

def render_info_fullscreen(epd, pix, msg="Start..."):
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

def main():
    global alarm_armed, alarm_triggered, last_cd_701
    global blink_enabled, blink_state, blink_last_ms, _arm_request

    epd = EPD29V2()
    pix = rotated_pixel_90(epd.fb, epd.W, epd.H)

    print("\n=== START ===")
    log_mem("boot")

    # Initiale Anzeige (damit direkt was da ist)
    render_info_fullscreen(epd, pix, "Starte...")

    # Fetch-Thread starten (nur einmal!)
    _thread.start_new_thread(fetch_worker, ())

    last_seq = -1
    last_state = None
    had_any_data = False

    while True:
        gc.collect()

        # Button-Request verarbeiten (Alarm togglen)
        if _arm_request:
            _arm_request = False

            if alarm_armed:
                _disarm_alarm()
                print("[ALARM] entschaerft")
            else:
                _arm_alarm()
                print("[ALARM] scharf (Schwelle: <{} min)".format(ALARM_THRESHOLD_MIN))

        # LED/Alarm immer flüssig updaten (unabhängig vom Netzwerk)
        _set_led_logic()

        # Daten schnell aus shared kopieren
        data_lock.acquire()
        try:
            seq = shared["seq"]
            r_701 = shared["r701"]
            r_s6  = shared["rs6"]
            err   = shared["err"]
        finally:
            data_lock.release()

        # Nur bei neuen Daten rendern / Alarm-Logik prüfen
        if seq != last_seq:
            last_seq = seq

            if err is not None:
                state = "ERR|" + err
                if state != last_state:
                    render_error_fullscreen(epd, pix, "WLAN/Request Fehler")
                    last_state = state
            else:
                had_any_data = True

                # --- Alarm-Logik für 701 ---
                cd_701 = r_701[0] if r_701 is not None else None

                if alarm_armed:
                    # Trigger wenn < ALARM_THRESHOLD_MIN Minuten
                    if (cd_701 is not None) and (cd_701 < ALARM_THRESHOLD_MIN) and (not alarm_triggered):
                        alarm_triggered = True
                        blink_enabled = True
                        blink_state = 1
                        blink_last_ms = time.ticks_ms()
                        print("[ALARM] 701 <{}min -> beep + blink".format(ALARM_THRESHOLD_MIN))
                        _beep_once()

                    # "Zug abgefahren": Countdown geht wieder hoch (und ist wieder >= ALARM_THRESHOLD_MIN)
                    if alarm_triggered:
                        if cd_701 is None:
                            print("[ALARM] 701 weg -> Alarm aus")
                            _disarm_alarm()
                        elif (last_cd_701 is not None) and (cd_701 > last_cd_701) and (cd_701 >= ALARM_THRESHOLD_MIN):
                            print("[ALARM] countdown wieder hoch -> Alarm aus")
                            _disarm_alarm()

                last_cd_701 = cd_701
                _set_led_logic()
                # --- Ende Alarm-Logik ---

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

        # Falls Thread noch keine Daten geliefert hat, aber kein Fehler kam:
        if (not had_any_data) and (last_state is None) and (seq == 0):
            pass

        # Kurzer Sleep -> Button/LED super responsiv
        time.sleep_ms(20)

main()
