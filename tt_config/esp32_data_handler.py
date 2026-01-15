import subprocess
import time
from pathlib import Path
from typing import List, Optional

from serial.tools import list_ports

ESPRESSIF_VID = 0x303A


def _ports_with_vid(vid: int) -> List[str]:
    return [p.device for p in list_ports.comports() if p.vid == vid]


def _mpremote_call(port: str, *args: str, timeout: int = 10) -> None:
    subprocess.check_call(
        ["mpremote", "connect", port, *args],
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def _mpremote_out(port: str, *args: str, timeout: int = 3) -> str:
    return subprocess.check_output(
        ["mpremote", "connect", port, *args],
        stderr=subprocess.STDOUT,
        timeout=timeout,
        text=True,
    )


def _is_micropython_esp32(port: str) -> bool:
    try:
        out = _mpremote_out(port, "exec", "import sys; print(sys.platform)", timeout=2)
        return "esp32" in out.lower()
    except Exception:
        return False


def upload_json_to_esp32(
    json_path: str,
    remote_name: str = "config.json",
    wait_timeout_s: float = 60.0,
    poll_s: float = 0.5,
) -> str:
    """
    Lädt eine JSON-Datei auf den ESP32 hoch, OHNE das laufende Programm zu stoppen.

    Verhalten:
    - Findet Kandidatenports anhand ESPRESSIF_VID (0x303A)
    - Wartet, bis ein Kandidat als MicroPython/esp32 antwortet
    - Versucht `mpremote fs cp` wiederholt, bis es klappt oder wait_timeout_s erreicht ist
    - Kein reset/interrupt/start

    Status via print(). Gibt den verwendeten Port zurück.
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"JSON-Datei nicht gefunden: {path}")

    print("[1/4] Suche ESP32 (VID 0x303A)…")
    candidates = _ports_with_vid(ESPRESSIF_VID)
    if not candidates:
        raise RuntimeError("Kein ESP32 (VID 0x303A) gefunden.")
    print(f"      Kandidaten: {', '.join(candidates)}")

    deadline = time.time() + wait_timeout_s

    print("[2/4] Warte, bis MicroPython ansprechbar ist (ohne Stop/Reset)…")
    port: Optional[str] = None
    last_probe_err: Optional[str] = None
    while time.time() < deadline:
        for p in candidates:
            try:
                if _is_micropython_esp32(p):
                    port = p
                    break
            except Exception as e:
                last_probe_err = str(e)
        if port:
            break
        print("      Noch nicht erreichbar… retry")
        time.sleep(poll_s)

    if not port:
        raise RuntimeError(
            f"ESP32 gefunden ({', '.join(candidates)}), aber MicroPython wurde in {wait_timeout_s:.0f}s nicht ansprechbar. "
            f"Letzter Probe-Fehler: {last_probe_err}"
        )

    print(f"      Verwende Port: {port}")

    print("[3/4] Lade JSON hoch (wartet, bis es passt)…")
    attempt = 0
    last_err: Optional[Exception] = None
    while time.time() < deadline:
        attempt += 1
        try:
            print(f"      Upload Versuch {attempt}…")
            _mpremote_call(port, "fs", "cp", str(path), f":{remote_name}", timeout=10)
            print("      Upload OK.")
            last_err = None
            break
        except Exception as e:
            last_err = e
            # Typisch: busy / port in use / timeout / device not ready
            msg = str(e).strip().replace("\n", " ")
            print(f"      Busy/Fehler: {msg} → warte {poll_s}s…")
            time.sleep(poll_s)

    if last_err is not None:
        raise RuntimeError(f"Upload hat innerhalb {wait_timeout_s:.0f}s nicht geklappt. Letzter Fehler: {last_err}")

    print("[4/4] Fertig.")
    return port

def download_json_from_esp32(
    remote_name: str = "config.json",
    local_path: str = "config.json",
    wait_timeout_s: float = 60.0,
    poll_s: float = 0.5,
) -> str:
    """
    Lädt eine Datei vom ESP32 herunter, ohne das laufende Programm zu stoppen.

    - Wartet, bis der ESP ansprechbar ist
    - Versucht den Download wiederholt, bis es klappt
    - Kein reset/interrupt

    Gibt den verwendeten Port zurück.
    """
    print("[1/4] Suche ESP32 (VID 0x303A)…")
    candidates = _ports_with_vid(ESPRESSIF_VID)
    if not candidates:
        raise RuntimeError("Kein ESP32 (VID 0x303A) gefunden.")
    print(f"      Kandidaten: {', '.join(candidates)}")

    deadline = time.time() + wait_timeout_s
    port: Optional[str] = None

    print("[2/4] Warte, bis MicroPython ansprechbar ist…")
    while time.time() < deadline:
        for p in candidates:
            if _is_micropython_esp32(p):
                port = p
                break
        if port:
            break
        print("      Noch nicht erreichbar… retry")
        time.sleep(poll_s)

    if not port:
        raise RuntimeError("ESP32 gefunden, aber nicht ansprechbar.")

    print(f"      Verwende Port: {port}")

    print("[3/4] Lade Datei herunter…")
    attempt = 0
    last_err = None
    while time.time() < deadline:
        attempt += 1
        try:
            print(f"      Download Versuch {attempt}…")
            _mpremote_call(port, "fs", "cp", f":{remote_name}", local_path, timeout=10)
            print("      Download OK.")
            last_err = None
            break
        except Exception as e:
            last_err = e
            print(f"      Busy/Fehler ({e}) → warte {poll_s}s…")
            time.sleep(poll_s)

    if last_err is not None:
        raise RuntimeError(f"Download fehlgeschlagen. Letzter Fehler: {last_err}")

    print("[4/4] Fertig.")
    return port
