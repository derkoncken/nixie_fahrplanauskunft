# main.py  (ESP32_GENERIC_S3 MicroPython v1.27.0)
#
# Holt EFA/VRR Direct-Monitoring JSON und gibt die nächste Linie 701 an Bstg 4 aus.
# RAM-schonend (ohne urequests): HTTPS POST per socket + optional chunked decoding.
#
# ✅ Getestetes Ziel: ESP32_GENERIC_S3-20251209-v1.27.0.bin
#
# --- Konfiguration ---
WIFI_SSID = "DEIN_SSID"
WIFI_PASS = "DEIN_PASSWORT"

STOP_ID = "20018098"      # name_dm (Haltestellen-ID)
LIMIT = "4"              # kleiner = weniger RAM (8 ist meist gut)
LINE_NO = "701"          # gewünschte Linie
PLATFORM = "4"           # gewünschtes Gleis/Bstg

URL_HOST = "efa.vrr.de"
URL_PATH = "/standard/XML_DM_REQUEST"

REQUEST_TIMEOUT_S = 12
WIFI_TIMEOUT_S = 25

# --- Imports ---
import network
import time
import json
import gc
import usocket
import ssl



# ---------- Helpers ----------
def wifi_connect(ssid: str, password: str, timeout_s: int = WIFI_TIMEOUT_S) -> None:
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        return

    wlan.connect(ssid, password)
    t0 = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
            raise RuntimeError("WLAN Verbindung Timeout")
        time.sleep(0.2)


def fmt_hhmm(dt) -> str:
    """EFA dateTime/realDateTime dict -> 'HH:MM'"""
    if not isinstance(dt, dict):
        return "—"
    h = dt.get("hour")
    m = dt.get("minute")
    if h is None or m is None:
        return "—"
    try:
        return "%02d:%02d" % (int(h), int(m))
    except Exception:
        return "—"


def to_int(x, default=None):
    try:
        return int(str(x).strip())
    except Exception:
        return default


def _read_all(sock, bufsize=1024) -> bytes:
    """Liest bis EOF. (Connection: close)"""
    data = b""
    while True:
        chunk = sock.read(bufsize)
        if not chunk:
            break
        data += chunk
    return data


def _decode_chunked(body: bytes) -> bytes:
    """
    Minimaler Chunked-Decoder.
    Reicht für typische "Transfer-Encoding: chunked" Antworten.
    """
    out = b""
    i = 0
    n = len(body)
    while i < n:
        j = body.find(b"\r\n", i)
        if j == -1:
            break
        line = body[i:j].strip()
        i = j + 2
        if not line:
            continue
        try:
            size = int(line.split(b";")[0], 16)
        except Exception:
            break
        if size == 0:
            break
        out += body[i:i + size]
        i = i + size + 2  # skip data + trailing CRLF
    return out


# ---------- EFA Request ----------
def fetch_departures(stop_id: str = STOP_ID, limit: str = LIMIT) -> dict:
    """
    HTTPS POST an EFA Direct Monitor endpoint.
    Gibt das JSON (dict) zurück.
    """
    gc.collect()

    form = (
        "outputFormat=JSON&"
        "language=de&"
        "useRealtime=1&"
        "mode=direct&"
        "limit={}&"
        "type_dm=stopID&"
        "name_dm={}"
    ).format(limit, stop_id)

    addr = usocket.getaddrinfo(URL_HOST, 443)[0][-1]
    s = usocket.socket()
    s.settimeout(REQUEST_TIMEOUT_S)
    s.connect(addr)
    s = ssl.wrap_socket(s, server_hostname=URL_HOST)


    body_bytes = form.encode("utf-8")
    req = (
        "POST {} HTTP/1.1\r\n"
        "Host: {}\r\n"
        "User-Agent: esp32-micropython\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        "Content-Length: {}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).format(URL_PATH, URL_HOST, len(body_bytes))

    s.write(req.encode("utf-8"))
    s.write(body_bytes)

    resp = _read_all(s, 1024)
    s.close()

    sep = resp.find(b"\r\n\r\n")
    if sep == -1:
        raise RuntimeError("Ungültige HTTP Antwort (kein Header-Separator)")

    header = resp[:sep]
    body = resp[sep + 4:]

    # Statuscode prüfen
    first = header.split(b"\r\n", 1)[0]  # b'HTTP/1.1 200 OK'
    parts = first.split()
    if len(parts) < 2:
        raise RuntimeError("Ungültige Statuszeile")
    if parts[1] != b"200":
        raise RuntimeError("HTTP Fehler: %s" % parts[1].decode())

    # chunked?
    if b"transfer-encoding: chunked" in header.lower():
        body = _decode_chunked(body)

    gc.collect()
    return json.loads(body.decode("utf-8"))


# ---------- Business Logic ----------
def find_next_line_platform(data: dict, line_no: str = LINE_NO, platform: str = PLATFORM):
    """
    Sucht die nächste Fahrt für line_no an platform mit kleinstem countdown.
    Rückgabe: (countdown:int, entry:dict) oder None
    """
    departures = data.get("departureList")
    if not isinstance(departures, list):
        return None

    best = None  # (countdown, entry)
    for e in departures:
        serving = e.get("servingLine")
        if not isinstance(serving, dict):
            serving = {}

        line = str(serving.get("number", ""))
        bstg = str((e.get("platformName") or e.get("platform") or "")).strip()

        if line != line_no:
            continue
        if bstg != platform:
            continue

        countdown = to_int(e.get("countdown"))
        if countdown is None:
            continue

        if best is None or countdown < best[0]:
            best = (countdown, e)

    return best


def print_result(best):
    if best is None:
        print("Keine passende Abfahrt gefunden.")
        return

    countdown, e = best
    serving = e.get("servingLine") if isinstance(e.get("servingLine"), dict) else {}
    direction = serving.get("direction", "")

    planned = fmt_hhmm(e.get("dateTime"))
    real = fmt_hhmm(e.get("realDateTime"))

    delay = to_int(serving.get("delay"), 0)
"""
    print("Nächste {} (Bstg {}) → {}".format(LINE_NO, PLATFORM, direction))
    print("Geplant:     {}".format(planned))
    print("Tatsächlich: {}".format(real))
    print("In:          {} min".format(countdown))
    print("Verspätung:  +{} min".format(delay))
"""

# ---------- Main ----------
def main():
    wifi_connect(WIFI_SSID, WIFI_PASS)

    data = fetch_departures(STOP_ID, LIMIT)
    best = find_next_line_platform(data, LINE_NO, PLATFORM)
    print_result(best)


if __name__ == "__main__":
    try:
        print(time.time())
        for i in range(100):
            main()
        print(time.time())
            
    except MemoryError:
        # Falls doch noch RAM-Probleme auftreten: LIMIT weiter reduzieren (z.B. 6 oder 4)
        gc.collect()
        print("MemoryError: LIMIT weiter reduzieren (z.B. 6/4) und erneut versuchen.")
    except Exception as e:
        print("Fehler:", e)
