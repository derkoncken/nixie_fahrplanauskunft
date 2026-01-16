import json

# WICHTIG: haltestelle_1/2 sind bei dir QLabel -> kind="label"
# spinBox_2/3/6 etc sind QSpinBox -> kind="spin"
# wlan_name/wlan_ssid sind QLineEdit -> kind="lineedit"

UI_MAP = {
    # 1. Abfahrt
    "haltestelle_1": ("haltestelle_1", "label"),
    "line_no_1":     ("line_no_1", "label"),
    "bahnsteig_1":   ("bahnsteig_1", "label"),
    "abfahrten_1":   ("spinBox_2", "spin"),

    # 2. Abfahrt
    "haltestelle_2": ("haltestelle_2", "label"),
    "line_no_2":     ("line_no_2", "label"),
    "bahnsteig_2":   ("bahnsteig_2", "label"),
    "abfahrten_2":   ("spinBox_3", "spin"),

    # Alarm
    "alarm_abfahrt": ("comboBox", "combo_index"),
    "alarm_minuten": ("spinBox_6", "spin"),

    # WLAN
    "wlan_name": ("wlan_name", "lineedit"),
    "wlan_ssid": ("wlan_ssid", "lineedit"),
}

# Optional: stop_id separat speichern (Property vom QLabel)
STOP_ID_KEYS = {
    "stop_id_1": "haltestelle_1",
    "stop_id_2": "haltestelle_2",
}


def save_ui_to_json(ui, path: str = "config.json") -> None:
    data = {}

    for key, (attr, kind) in UI_MAP.items():
        w = getattr(ui, attr, None)
        if w is None:
            continue

        if kind == "label":
            data[key] = w.text()
        elif kind == "lineedit":
            data[key] = w.text()
        elif kind == "spin":
            data[key] = int(w.value())
        elif kind == "combo_index":
            data[key] = int(w.currentIndex())
        else:
            raise ValueError(f"Unknown kind: {kind}")

    # stop_id properties (wenn gesetzt)
    for key, label_attr in STOP_ID_KEYS.items():
        w = getattr(ui, label_attr, None)
        if w is None:
            continue
        sid = w.property("stop_id")
        if sid:
            data[key] = str(sid)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_ui_from_json(ui, path: str = "config.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for key, (attr, kind) in UI_MAP.items():
        if key not in data:
            continue

        w = getattr(ui, attr, None)
        if w is None:
            continue

        val = data[key]

        if kind == "label":
            w.setText("" if val is None else str(val))
        elif kind == "lineedit":
            w.setText("" if val is None else str(val))
        elif kind == "spin":
            try:
                w.setValue(int(val))
            except Exception:
                pass
        elif kind == "combo_index":
            try:
                w.setCurrentIndex(int(val))
            except Exception:
                pass

    # stop_id properties zurückschreiben
    if "stop_id_1" in data and hasattr(ui, "haltestelle_1"):
        ui.haltestelle_1.setProperty("stop_id", str(data["stop_id_1"]))
    if "stop_id_2" in data and hasattr(ui, "haltestelle_2"):
        ui.haltestelle_2.setProperty("stop_id", str(data["stop_id_2"]))

    return data
