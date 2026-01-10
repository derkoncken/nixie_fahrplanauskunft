# print_tt.py — VRR/EFA Direct Monitoring (JSON) -> nächste Abfahrt als Tuple
import network
import time
import json
import gc
import usocket
import ssl

# --- Konfiguration (kann auch in main.py überschrieben werden) ---
URL_HOST = "efa.vrr.de"
URL_PATH = "/standard/XML_DM_REQUEST"

REQUEST_TIMEOUT_S = 12
WIFI_TIMEOUT_S = 25


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
    data = b""
    while True:
        chunk = sock.read(bufsize)
        if not chunk:
            break
        data += chunk
    return data


def _decode_chunked(body: bytes) -> bytes:
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
        i = i + size + 2
    return out


def fetch_departures(stop_id: str, limit: str) -> dict:
    gc.collect()

    form = (
        "outputFormat=JSON&language=de&useRealtime=1&mode=direct&"
        "limit={}&type_dm=stopID&name_dm={}"
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

    first = header.split(b"\r\n", 1)[0]
    parts = first.split()
    if len(parts) < 2 or parts[1] != b"200":
        raise RuntimeError("HTTP Fehler: %s" % (parts[1].decode() if len(parts) > 1 else "?"))

    if b"transfer-encoding: chunked" in header.lower():
        body = _decode_chunked(body)

    gc.collect()
    return json.loads(body.decode("utf-8"))


def find_next_line_platform(data: dict, line_no: str, platform: str):
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

        if line != line_no or bstg != platform:
            continue

        countdown = to_int(e.get("countdown"))
        if countdown is None:
            continue

        if best is None or countdown < best[0]:
            best = (countdown, e)

    return best


def get_data(ssid, password, stop_id, limit, line_no, platform):
    """
    Rückgabe:
      None
      oder (countdown:int, direction:str, planned:str, real:str, delay:int)
    """
    wifi_connect(ssid, password)
    data = fetch_departures(stop_id, limit)
    best = find_next_line_platform(data, line_no, platform)
    if best is None:
        return None

    countdown, e = best
    serving = e.get("servingLine") if isinstance(e.get("servingLine"), dict) else {}
    direction = serving.get("direction", "") or "—"
    planned = fmt_hhmm(e.get("dateTime"))
    real = fmt_hhmm(e.get("realDateTime"))
    delay = to_int(serving.get("delay"), 0)

    return (countdown, direction, planned, real, delay)
