# app_config.py — Konfiguration + Policy
import ujson

CONFIG_FILE = "config.json"

# --- Refresh ---
REFRESH_S = 5

# --- Full/Partial Policy ---
# Full-Refresh im Betrieb grundsätzlich erlauben?
ENABLE_FULL_REFRESH = False   # <-- True/False (Startsequenz macht immer Full)

# Nach wie vielen Partial-Updates soll ein Full erfolgen?
# 0 oder None => nie Full im Betrieb
PARTIALS_PER_FULL = 25        # <-- z.B. 20..40; wird ignoriert wenn ENABLE_FULL_REFRESH=False

# --- Hardware Pins (XIAO ESP32S3) ---
BTN_GPIO = 43
LED_GPIO = 44
BUZ_GPIO = 6

def load_config():
    with open(CONFIG_FILE, "r") as f:
        return ujson.load(f)

def read_runtime_config():
    cfg = load_config()

    # Slot 1
    stop_id_1  = cfg.get("stop_id_1", "")
    line_no_1  = cfg.get("line_no_1", "")
    platform_1 = str(cfg.get("bahnsteig_1", ""))
    limit_1    = int(cfg.get("abfahrten_1", 10))

    # Slot 2
    stop_id_2  = cfg.get("stop_id_2", "")
    line_no_2  = cfg.get("line_no_2", "")
    platform_2 = str(cfg.get("bahnsteig_2", ""))
    limit_2    = int(cfg.get("abfahrten_2", 10))

    # WLAN
    wifi_ssid = cfg.get("wlan_name", "")
    wifi_pass = cfg.get("wlan_password", "")

    # Alarm
    alarm_source = int(cfg.get("alarm_abfahrt", 0))   # 0 -> Slot 1, 1 -> Slot 2
    alarm_threshold_min = int(cfg.get("alarm_minuten", 4))

    return {
        "STOP_ID_1": stop_id_1, "LINE_NO_1": line_no_1, "PLATFORM_1": platform_1, "LIMIT_1": limit_1,
        "STOP_ID_2": stop_id_2, "LINE_NO_2": line_no_2, "PLATFORM_2": platform_2, "LIMIT_2": limit_2,
        "WIFI_SSID": wifi_ssid, "WIFI_PASS": wifi_pass,
        "ALARM_SOURCE": alarm_source, "ALARM_THRESHOLD_MIN": alarm_threshold_min,
    }
