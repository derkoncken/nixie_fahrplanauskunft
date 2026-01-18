# get_departures.py  — VRR/EFA Direct Monitoring (JSON) -> nächste Abfahrt (STREAMING, robust)
import network
import time
import json
import gc
import usocket
import ssl

URL_HOST = "efa.vrr.de"
URL_PATH = "/standard/XML_DM_REQUEST"

REQUEST_TIMEOUT_S = 20
CHUNK_SIZE = 2048

# SSL read() "None"-Spins
NONE_SPIN_LIMIT = 2000
NONE_SPIN_SLEEP_MS = 2

# OSError-Timeouts beim Lesen
READ_RETRIES = 6
READ_RETRY_SLEEP_MS = 150

# WLAN Robustheit
WIFI_CONNECT_TIMEOUT_S = 25
WIFI_CONNECT_RETRIES = 4
WIFI_RESET_SLEEP_MS = 500

# DNS / Resolve Cache
DNS_FALLBACK_PUBLIC = "8.8.8.8"
RESOLVE_TTL_S = 6 * 60 * 60  # 6h

# Globales WLAN-Objekt
_WLAN = network.WLAN(network.STA_IF)

# Host-IP Cache
_EFA_IP = None
_EFA_IP_TS = 0


def to_int(x, default=None):
    try:
        return int(str(x).strip())
    except Exception:
        return default


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


def _wifi_status_name(code: int) -> str:
    m = {
        getattr(network, "STAT_IDLE", 0): "IDLE",
        getattr(network, "STAT_CONNECTING", 1): "CONNECTING",
        getattr(network, "STAT_WRONG_PASSWORD", -3): "WRONG_PASSWORD",
        getattr(network, "STAT_NO_AP_FOUND", -2): "NO_AP_FOUND",
        getattr(network, "STAT_CONNECT_FAIL", -1): "CONNECT_FAIL",
        getattr(network, "STAT_GOT_IP", 3): "GOT_IP",
    }
    return m.get(code, str(code))


def _wifi_hard_reset():
    try:
        _WLAN.disconnect()
    except Exception:
        pass
    try:
        _WLAN.active(False)
    except Exception:
        pass
    time.sleep_ms(WIFI_RESET_SLEEP_MS)
    _WLAN.active(True)
    time.sleep_ms(WIFI_RESET_SLEEP_MS)

    # Power Save aus (falls unterstützt)
    try:
        _WLAN.config(pm=0xa11140)
    except Exception:
        pass

    time.sleep_ms(200)


def ensure_dns(wlan, fallback_public=DNS_FALLBACK_PUBLIC, prefer_gw=True):
    """
    Wenn DHCP keinen DNS liefert (dns='0.0.0.0' / ''), setzen wir einen:
    bevorzugt Gateway als DNS (lokal meist stabil), sonst Public DNS.
    """
    try:
        ip, mask, gw, dns = wlan.ifconfig()
    except Exception:
        return None

    if not dns or dns == "0.0.0.0":
        new_dns = gw if (prefer_gw and gw and gw != "0.0.0.0") else fallback_public
        try:
            wlan.ifconfig((ip, mask, gw, new_dns))
        except Exception:
            pass

    try:
        return wlan.ifconfig()[3]
    except Exception:
        return None


def wifi_connect(ssid: str, password: str, timeout_s: int = WIFI_CONNECT_TIMEOUT_S) -> None:
    _WLAN.active(True)
    try:
        _WLAN.config(pm=0xa11140)
    except Exception:
        pass

    if _WLAN.isconnected():
        ensure_dns(_WLAN)
        return

    last_status = None

    for _ in range(WIFI_CONNECT_RETRIES):
        try:
            _WLAN.disconnect()
        except Exception:
            pass
        time.sleep_ms(150)

        try:
            _WLAN.connect(ssid, password)
        except OSError:
            _wifi_hard_reset()
            continue

        t0 = time.ticks_ms()
        while True:
            if _WLAN.isconnected():
                ensure_dns(_WLAN)
                return

            st = _WLAN.status()
            last_status = st

            if st in (-3, -2, -1):
                break

            if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
                break

            time.sleep(0.25)

        _wifi_hard_reset()

    raise RuntimeError("WLAN Verbindung Timeout (status={})".format(_wifi_status_name(last_status)))


def wifi_internet_ok():
    """
    Minimaler Check: DNS-Auflösung muss funktionieren.
    (genau der Pfad, der bei dir mit -202 knallt)
    """
    try:
        usocket.getaddrinfo("example.com", 80, usocket.AF_INET, usocket.SOCK_STREAM)
        return True
    except Exception:
        return False


def ensure_wifi(ssid: str, password: str, tries: int = 3) -> bool:
    """
    Reconnect + DNS prüfen, ohne Endlosschleife.
    """
    for _ in range(tries):
        try:
            wifi_connect(ssid, password)
            if wifi_internet_ok():
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _resolve_host_ipv4(host: str, port: int):
    # IPv4 erzwingen
    infos = usocket.getaddrinfo(host, port, usocket.AF_INET, usocket.SOCK_STREAM)
    # infos[0][-1] ist (ip, port)
    return infos[0][-1][0]


def _get_cached_efa_ip():
    global _EFA_IP, _EFA_IP_TS
    now = time.time()
    if _EFA_IP and (now - _EFA_IP_TS) < RESOLVE_TTL_S:
        return _EFA_IP
    # Cache abgelaufen
    _EFA_IP = None
    return None


def _set_cached_efa_ip(ip: str):
    global _EFA_IP, _EFA_IP_TS
    _EFA_IP = ip
    _EFA_IP_TS = time.time()


def _open_https():
    """
    DNS/Resolve robust:
    - IPv4-only resolve
    - IP Cache
    - bei -202: Cache leeren und nochmal versuchen (nach WLAN/DNS repair)
    """
    ip = _get_cached_efa_ip()
    if not ip:
        try:
            ip = _resolve_host_ipv4(URL_HOST, 443)
            _set_cached_efa_ip(ip)
        except OSError as e:
            # DNS fail
            if e.args and e.args[0] == -202:
                # Versuch: DNS/WLAN reparieren -> nochmal resolve
                try:
                    ensure_dns(_WLAN)
                except Exception:
                    pass
                ip = _resolve_host_ipv4(URL_HOST, 443)
                _set_cached_efa_ip(ip)
            else:
                raise

    addr = (ip, 443)
    s = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
    s.settimeout(REQUEST_TIMEOUT_S)
    s.connect(addr)

    # Wichtig: SNI bleibt Hostname, auch wenn wir zur IP connecten
    return ssl.wrap_socket(s, server_hostname=URL_HOST)


def _send_request(sock, stop_id: str, limit: str):
    form = (
        "outputFormat=JSON&language=de&useRealtime=1&mode=direct&"
        "limit={}&type_dm=stopID&name_dm={}"
    ).format(limit, stop_id)

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

    sock.write(req.encode("utf-8"))
    sock.write(body_bytes)


def _read_retry(sock, nbytes: int):
    retries = READ_RETRIES
    while True:
        try:
            return sock.read(nbytes)
        except OSError as e:
            code = e.args[0] if e.args else None
            # -116 ETIMEDOUT / -11 EAGAIN (je nach Port)
            if code in (-116, -11) and retries > 0:
                retries -= 1
                time.sleep_ms(READ_RETRY_SLEEP_MS)
                continue
            raise


def _read_until_headers_done(sock, chunk_size=1024):
    buf = bytearray()
    none_spins = 0
    while True:
        data = _read_retry(sock, chunk_size)

        if data is None:
            none_spins += 1
            if none_spins > NONE_SPIN_LIMIT:
                raise RuntimeError("HTTP: read() returned None too often (header)")
            time.sleep_ms(NONE_SPIN_SLEEP_MS)
            continue

        if not data:
            raise RuntimeError("HTTP: socket closed before header finished")

        buf.extend(data)
        idx = buf.find(b"\r\n\r\n")
        if idx != -1:
            header = bytes(buf[:idx])
            rest = bytes(buf[idx + 4:])
            return header, rest

        if len(buf) > 32 * 1024:
            raise RuntimeError("HTTP: header > 32k (unexpected)")


def _parse_status_and_headers(header: bytes):
    lines = header.split(b"\r\n")
    status = lines[0].decode("latin-1", "ignore") if lines else ""
    hmap = {}
    for ln in lines[1:]:
        p = ln.find(b":")
        if p > 0:
            k = ln[:p].decode("latin-1", "ignore").strip().lower()
            v = ln[p + 1:].decode("latin-1", "ignore").strip()
            hmap[k] = v
    return status, hmap


def _iter_departure_objects(sock, first_body_bytes: bytes, total_body_len: int):
    buf = bytearray(first_body_bytes)
    pos = 0

    remaining = total_body_len - len(first_body_bytes)
    if remaining < 0:
        remaining = 0

    none_spins = 0

    def _trim_front():
        nonlocal buf, pos
        if pos > 8192:
            buf = buf[pos:]
            pos = 0

    def _read_more():
        nonlocal buf, pos, remaining, none_spins
        if remaining <= 0:
            return False

        data = _read_retry(sock, min(CHUNK_SIZE, remaining))

        if data is None:
            none_spins += 1
            if none_spins > NONE_SPIN_LIMIT:
                raise RuntimeError("HTTP: read() returned None too often (body)")
            time.sleep_ms(NONE_SPIN_SLEEP_MS)
            return True

        if not data:
            remaining = 0
            return False

        remaining -= len(data)
        _trim_front()
        buf.extend(data)
        return True

    # A) find "departureList"
    key = b'"departureList"'
    overlap = len(key) - 1

    while True:
        idx = buf.find(key, pos)
        if idx != -1:
            pos = idx + len(key)
            break

        if len(buf) > overlap:
            buf = buf[-overlap:]
        pos = 0

        if not _read_more():
            return

    # B) find '['
    while True:
        idx = buf.find(b"[", pos)
        if idx != -1:
            pos = idx + 1
            break

        if len(buf) > 64:
            buf = buf[-64:]
        pos = 0

        if not _read_more():
            return

    # C) extract objects
    in_string = False
    esc = False
    depth = 0
    obj = None

    def _need_one():
        nonlocal buf, pos
        while pos >= len(buf):
            buf = bytearray()
            pos = 0
            if not _read_more():
                return False
        return True

    while True:
        if not _need_one():
            return

        b0 = buf[pos]
        pos += 1

        if obj is None:
            if b0 == ord(']'):
                return
            if b0 == ord('{'):
                obj = bytearray()
                obj.append(b0)
                depth = 1
                in_string = False
                esc = False
            else:
                continue
        else:
            obj.append(b0)

            if in_string:
                if esc:
                    esc = False
                else:
                    if b0 == ord('\\'):
                        esc = True
                    elif b0 == ord('"'):
                        in_string = False
            else:
                if b0 == ord('"'):
                    in_string = True
                elif b0 == ord('{'):
                    depth += 1
                elif b0 == ord('}'):
                    depth -= 1
                    if depth == 0:
                        yield bytes(obj)
                        obj = None

        if pos > 16384:
            buf = buf[pos:]
            pos = 0


def fetch_next(stop_id: str, limit: str, line_no: str, platform: str):
    s = _open_https()
    try:
        _send_request(s, stop_id, limit)

        header, rest = _read_until_headers_done(s)
        status_line, h = _parse_status_and_headers(header)

        parts = status_line.split()
        if len(parts) < 2 or parts[1] != "200":
            raise RuntimeError("HTTP Fehler: %s" % (parts[1] if len(parts) > 1 else "?"))

        te = (h.get("transfer-encoding") or "").lower()
        if "chunked" in te:
            raise RuntimeError("Chunked Transfer-Encoding nicht unterstützt (nur Content-Length).")

        cl = to_int(h.get("content-length"), None)
        if cl is None:
            raise RuntimeError("Kein Content-Length (erwartet).")

        best = None
        for obj_bytes in _iter_departure_objects(s, rest, cl):
            try:
                e = json.loads(obj_bytes.decode("utf-8"))
            except Exception:
                continue

            serving = e.get("servingLine") if isinstance(e.get("servingLine"), dict) else {}
            line = str(serving.get("number", ""))
            bstg = str((e.get("platformName") or e.get("platform") or "")).strip()

            if line != line_no or bstg != platform:
                continue

            cd = to_int(e.get("countdown"))
            if cd is None:
                continue

            direction = serving.get("direction", "") or "—"
            planned = fmt_hhmm(e.get("dateTime"))
            real = fmt_hhmm(e.get("realDateTime"))
            delay = to_int(serving.get("delay"), 0)

            if best is None or cd < best[0]:
                best = (cd, direction, planned, real, delay)
                if cd == 0:
                    break

        return best
    finally:
        try:
            s.close()
        except Exception:
            pass


def get_data(stop_id, limit, line_no, platform):
    """
    Rückgabe:
      None
      oder (countdown:int, direction:str, planned:str, real:str, delay:int)
    """
    gc.collect()
    return fetch_next(stop_id, limit, line_no, platform)
