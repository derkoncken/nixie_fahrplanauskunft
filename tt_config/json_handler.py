import json
import subprocess
import time

PORT = "/dev/ttyACM0"

UI_MAP = {
    # --- 1. Abfahrt ---
    "haltestelle_1": ("haltestelle_1", "text"),   # QLineEdit
    "bahnsteig_1":   ("spinBox", "value"),        # QSpinBox
    "abfahrten_1":   ("spinBox_2", "value"),      # QSpinBox

    # --- 2. Abfahrt ---
    "haltestelle_2": ("haltestelle_2", "text"),   # QLineEdit
    "bahnsteig_2":   ("spinBox_3", "value"),      # QSpinBox
    "abfahrten_2":   ("spinBox_4", "value"),      # QSpinBox

    # --- Alarm ---
    "alarm_abfahrt": ("comboBox", "currentIndex"),  # QComboBox (0 = 1. Abfahrt, 1 = 2. Abfahrt)
    "alarm_minuten": ("spinBox_6", "value"),        # QSpinBox

    # --- WLAN ---
    "wlan_name":     ("wlan_name", "text"),      # QLineEdit
    "wlan_ssid":     ("wlan_ssid", "text"),      # QLineEdit
}


def ui_to_dict(ui, mapping: dict) -> dict:
    data = {}
    for key, (attr, kind) in mapping.items():
        w = getattr(ui, attr, None)
        if w is None:
            continue

        if kind == "text":
            data[key] = w.text()
        elif kind == "plainText":
            data[key] = w.toPlainText()
        elif kind == "checked":
            data[key] = bool(w.isChecked())
        elif kind == "value":
            data[key] = w.value()
        elif kind == "currentText":
            data[key] = w.currentText()
        elif kind == "currentIndex":
            data[key] = int(w.currentIndex())
        else:
            raise ValueError(f"Unbekannter kind: {kind} für {attr}")

    return data


def save_ui_to_json(ui) -> None:
    data = ui_to_dict(ui, UI_MAP)
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


    



def dict_to_ui(ui, mapping: dict, data: dict) -> None:
    for key, (attr, kind) in mapping.items():
        if key not in data:
            continue

        w = getattr(ui, attr, None)
        if w is None:
            continue

        val = data[key]

        if kind == "text":
            w.setText("" if val is None else str(val))
        elif kind == "plainText":
            w.setPlainText("" if val is None else str(val))
        elif kind == "checked":
            w.setChecked(bool(val))
        elif kind == "value":
            # SpinBox/DoubleSpinBox: erwartet int/float
            w.setValue(val)
        elif kind == "currentText":
            # Setzt auf passenden Text, falls vorhanden
            idx = w.findText(str(val))
            if idx >= 0:
                w.setCurrentIndex(idx)
        elif kind == "currentIndex":
            w.setCurrentIndex(int(val))
        else:
            raise ValueError(f"Unbekannter kind: {kind} für {attr}")


def load_ui_from_json(ui):
    with open("config.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    dict_to_ui(ui, UI_MAP, data)
    return data

