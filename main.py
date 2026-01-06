from pathlib import Path
import subprocess
import json
import sys

# --- Pfade ---
BASE = Path(__file__).resolve().parent
DM_JSON = BASE / "dm.json"

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

# --- departureList holen ---
if "departureList" not in data:
    print("❌ Keine departureList im JSON gefunden")
    sys.exit(1)

departures = data["departureList"]

# --- nächste 701 an Bstg 4 suchen ---
best = None

for e in departures:
    line = e.get("servingLine", {}).get("number")
    bstg = e.get("platformName") or e.get("platform")

    if line != "701":
        continue
    if bstg != "4":
        continue

    try:
        countdown = int(e.get("countdown"))
    except (TypeError, ValueError):
        continue

    if best is None or countdown < best[0]:
        best = (countdown, e)

# --- Ausgabe ---
if best is None:
    print("Keine 701 an Bstg 4 gefunden.")
else:
    countdown, e = best
    direction = e["servingLine"].get("direction", "")
    delay = e["servingLine"].get("delay", "0")

    print(
        f"Nächste 701 (Bstg 4): "
        f"in {countdown} min → {direction} (+{delay})"
    )
