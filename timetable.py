from pathlib import Path
import subprocess
import json
import sys

# =========================
# KONSTANTEN (hier einstellen)
# =========================
HALTESTELLE_ID = "20018235"   # z.B. "20018098"
LINIE = "S6"                  # z.B. "701" oder "S6"
BAHNSTEIG = "11"              # z.B. "4" (ohne "Gleis")
LIMIT = 100                   # wie viele Abfahrten holen
# =========================

BASE = Path(__file__).resolve().parent
DM_JSON = BASE / "dm.json"

def fmt_hhmm(dt: dict) -> str:
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

def norm_platform(x) -> str:
    s = str(x or "").strip()
    s = s.replace("Gleis", "").replace("gl.", "").strip()
    return s

def matches_line(serving: dict, wanted: str) -> bool:
    wanted = str(wanted).strip()
    if not wanted:
        return False
    # mögliche Felder in EFA:
    candidates = [
        serving.get("number"),
        serving.get("symbol"),
        serving.get("name"),
        serving.get("trainNumber"),
    ]
    for c in candidates:
        if c is None:
            continue
        if str(c).strip() == wanted:
            return True
    return False

curl_cmd = [
    "curl", "-sS", "-L",
    "https://efa.vrr.de/standard/XML_DM_REQUEST",
    "--data-urlencode", "outputFormat=JSON",
    "--data-urlencode", "language=de",
    "--data-urlencode", "useRealtime=1",
    "--data-urlencode", "mode=direct",
    "--data-urlencode", f"limit={LIMIT}",
    "--data-urlencode", "type_dm=stopID",
    "--data-urlencode", f"name_dm={HALTESTELLE_ID}",
    "-o", str(DM_JSON)
]

result = subprocess.run(curl_cmd)
if result.returncode != 0 or not DM_JSON.exists():
    print("❌ Fehler beim Abrufen der Abfahrten (curl fehlgeschlagen).")
    sys.exit(1)

try:
    with DM_JSON.open("r", encoding="utf-8") as f:
        data = json.load(f)
except Exception as ex:
    print("❌ JSON konnte nicht geladen werden:", ex)
    print("➡️ Inhalt beginnt mit:")
    print(DM_JSON.read_text(encoding="utf-8")[:400])
    sys.exit(1)

departures = data.get("departureList")
if not isinstance(departures, list):
    print("❌ Keine departureList im JSON gefunden.")
    sys.exit(1)

best = None
for e in departures:
    serving = e.get("servingLine") if isinstance(e.get("servingLine"), dict) else {}

    # Linie matchen
    if not matches_line(serving, LINIE):
        continue

    # Bahnsteig matchen
    bstg_raw = e.get("platformName") or e.get("platform") or ""
    bstg = norm_platform(bstg_raw)
    if str(BAHNSTEIG).strip() and bstg != str(BAHNSTEIG).strip():
        continue

    countdown = to_int(e.get("countdown"))
    if countdown is None:
        continue

    if best is None or countdown < best[0]:
        best = (countdown, e)

if best is None:
    msg = f"❌ Keine passende Abfahrt für Linie '{LINIE}'"
    if str(BAHNSTEIG).strip():
        msg += f" an Bahnsteig/Gleis '{BAHNSTEIG}'"
    msg += " gefunden."
    print(msg)
    sys.exit(0)

countdown, e = best
serving = e.get("servingLine") if isinstance(e.get("servingLine"), dict) else {}

direction = serving.get("direction", "—") or "—"
planned = fmt_hhmm(e.get("dateTime"))
real = fmt_hhmm(e.get("realDateTime"))

# Achtung: delay kann je nach EFA-Variante woanders stehen; wir versuchen ein paar Stellen:
delay = (
    to_int(e.get("delay")) or
    to_int(serving.get("delay")) or
    0
)

print(
    f"Nächste {LINIE}"
    + (f" (Gleis {BAHNSTEIG})" if str(BAHNSTEIG).strip() else "")
    + (f" → {direction}" if direction else "")
    + "\n"
    f"Geplant:     {planned}\n"
    f"Tatsächlich: {real}\n"
    f"In:          {countdown} min\n"
    f"Verspätung:  +{delay} min"
)
