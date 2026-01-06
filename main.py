from pathlib import Path
import subprocess
import json
import sys

# --- Pfade ---
BASE = Path(__file__).resolve().parent
DM_JSON = BASE / "dm.json"


def fmt_hhmm(dt: dict) -> str:
    """EFA dateTime/realDateTime -> 'HH:MM' """
    if not isinstance(dt, dict):
        return "—"
    h = dt.get("hour")
    m = dt.get("minute")
    if h is None or m is None:
        return "—"
    return f"{int(h):02d}:{int(m):02d}"


def to_int(x, default=None):
    try:
        return int(str(x).strip())
    except Exception:
        return default


# --- curl-Befehl ---
curl_cmd = [
    "curl", "-sL",
    "https://efa.vrr.de/standard/XML_DM_REQUEST",
    "--data-urlencode", "outputFormat=JSON",
    "--data-urlencode", "language=de",
    "--data-urlencode", "useRealtime=1",
    "--data-urlencode", "mode=direct",
    "--data-urlencode", "limit=20",
    "--data-urlencode", "type_dm=stopID",
    "--data-urlencode", "name_dm=20018098",
    "-o", str(DM_JSON)
]

# --- curl ausführen ---
result = subprocess.run(curl_cmd)

if result.returncode != 0 or not DM_JSON.exists():
    print("❌ Fehler beim Abrufen der Abfahrten")
    sys.exit(1)

# --- JSON laden ---
with DM_JSON.open("r", encoding="utf-8") as f:
    data = json.load(f)

departures = data.get("departureList")
if not isinstance(departures, list):
    print("❌ Keine departureList im JSON gefunden")
    sys.exit(1)

# --- nächste 701 an Bstg 4 suchen (kleinstes countdown) ---
best = None

for e in departures:
    serving = e.get("servingLine", {}) if isinstance(e.get("servingLine"), dict) else {}
    line = str(serving.get("number", ""))
    bstg = str((e.get("platformName") or e.get("platform") or "")).strip()

    if line != "701":
        continue
    if bstg != "4":
        continue

    countdown = to_int(e.get("countdown"))
    if countdown is None:
        continue

    if best is None or countdown < best[0]:
        best = (countdown, e)

if best is None:
    print("Keine 701 an Bstg 4 gefunden.")
    sys.exit(0)

countdown, e = best
serving = e.get("servingLine", {})
direction = serving.get("direction", "")

planned = fmt_hhmm(e.get("dateTime"))
real = fmt_hhmm(e.get("realDateTime"))

delay = to_int(serving.get("delay"), 0)

print(
    f"Nächste 701 (Bstg 4) → {direction}\n"
    f"Geplant:     {planned}\n"
    f"Tatsächlich: {real}\n"
    f"In:          {countdown} min\n"
    f"Verspätung:  +{delay} min"
)
