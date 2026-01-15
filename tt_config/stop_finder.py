# stopfinder.py
import json
import os
import time
import logging
from logging.handlers import RotatingFileHandler
from urllib.parse import urlencode

import requests

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QAbstractItemView, QTableWidgetItem


EFA_STOPFINDER_URL = "https://efa.vrr.de/standard/XML_STOPFINDER_REQUEST"


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("stopfinder")
    if logger.handlers:
        return logger  # schon konfiguriert

    logger.setLevel(logging.DEBUG)

    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", "stopfinder.log")

    fh = RotatingFileHandler(log_path, maxBytes=512_000, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Optional: auch auf Konsole (praktisch beim Start aus Terminal)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info("Logger initialized -> %s", log_path)
    return logger


LOG = _setup_logger()


def _safe_snippet(text: str, n: int = 800) -> str:
    text = text or ""
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    return text[:n]


def _extract_locations(payload: dict):
    """
    Robust: EFA-JSON ist leider nicht überall identisch.
    Wir versuchen mehrere mögliche Pfade.
    """
    if not isinstance(payload, dict):
        return []

    candidates = [
        payload.get("locations"),
        payload.get("stopFinder", {}).get("locations") if isinstance(payload.get("stopFinder"), dict) else None,
        payload.get("sf", {}).get("locations") if isinstance(payload.get("sf"), dict) else None,
        payload.get("stopFinder", {}).get("points") if isinstance(payload.get("stopFinder"), dict) else None,
        payload.get("points"),
        payload.get("location"),
    ]

    for c in candidates:
        if isinstance(c, list) and c:
            return c

    # manchmal ist es eine leere Liste, die wir auch akzeptieren
    for c in candidates:
        if isinstance(c, list):
            return c

    return []

def _is_stop_like(loc: dict) -> bool:
    """
    EFA liefert je nach Instanz unterschiedliche Typen für Haltestellen.
    Wir akzeptieren mehrere Varianten.
    """
    t = str(loc.get("type", "") or "").strip().lower()

    # häufige Varianten
    if t in ("stop", "stoparea", "stoppoint", "station", "halt", "halte"):
        return True

    # fuzzy fallback: alles was mit stop anfängt
    if t.startswith("stop"):
        return True

    # manche Antworten haben kein sauberes type, aber eine id
    # Wenn es eine id gibt, behandeln wir es als nutzbaren Treffer.
    if loc.get("id"):
        return True

    return False


class StopFinderWorker(QObject):
    """
    Läuft in einem QThread und holt StopFinder-Daten via requests.
    """
    finished = pyqtSignal(list)   # list[dict]
    error = pyqtSignal(str)

    def __init__(self, query: str, timeout_s: int = 20, debug: bool = True):
        super().__init__()
        self.query = query
        self.timeout_s = timeout_s
        self.debug = debug

    def run(self):
        req_id = int(time.time() * 1000)  # simple correlation id
        try:
            # Wir probieren zuerst POST (bei vielen EFA-Instanzen am stabilsten)
            post_data = {
                "outputFormat": "JSON",
                "language": "de",
                "type_sf": "any",
                "name_sf": self.query,

                # häufig hilfreich bei EFA:
                "locationServerActive": 1,
                "coordOutputFormat": "WGS84[DD.DDDDD]",
                # stop-only kann auch serverseitig helfen, UI filtert zusätzlich:
                # "anyObjFilter_sf": 2,
            }

            headers = {
                "User-Agent": "tt_config-stopfinder",
                "Accept": "application/json,text/plain,*/*",
            }

            LOG.info("[%s] StopFinder POST start query=%r", req_id, self.query)
            LOG.debug("[%s] POST url=%s data=%s", req_id, EFA_STOPFINDER_URL, post_data)

            r = requests.post(
                EFA_STOPFINDER_URL,
                data=post_data,
                headers=headers,
                timeout=self.timeout_s,
            )

            LOG.info("[%s] HTTP %s %s", req_id, r.status_code, r.reason)
            LOG.debug("[%s] Resp headers=%s", req_id, dict(r.headers))
            LOG.debug("[%s] Resp snippet=%s", req_id, _safe_snippet(r.text, 800))

            # Falls der Server HTML zurückgibt (Fehlerseite), sehen wir es im snippet.
            r.raise_for_status()

            # Manche Instanzen liefern falschen Content-Type -> json.loads(r.text) ist robuster als r.json()
            try:
                payload = json.loads(r.text)
            except Exception as e:
                msg = f"Antwort ist kein JSON (parse error: {e})"
                LOG.error("[%s] %s", req_id, msg)
                self.error.emit(msg)
                return

            locations = _extract_locations(payload)
            LOG.info("[%s] locations count=%d", req_id, len(locations))

            items = []
            for loc in locations:
                if not isinstance(loc, dict):
                    continue
                items.append({
                    "name": loc.get("name", "") or "",
                    "type": loc.get("type", "") or "",
                    "id": loc.get("id", "") or "",
                    "matchQuality": int(loc.get("matchQuality") or 0),
                    "isBest": bool(loc.get("isBest", False)),
                })

            # Wenn wirklich 0 rauskommt: zusätzlich kompletten Top-Level keys loggen
            if self.debug and not items:
                LOG.warning("[%s] No items parsed. Top-level keys: %s", req_id, list(payload.keys())[:50])

            self.finished.emit(items)

        except requests.exceptions.RequestException as e:
            LOG.exception("[%s] Network/HTTP error", req_id)
            self.error.emit(f"Netzwerk/HTTP-Fehler: {e}")
        except Exception as e:
            LOG.exception("[%s] Unexpected error", req_id)
            self.error.emit(f"Unerwarteter Fehler: {e}")


class StopFinderController(QObject):
    stop_selected = pyqtSignal(str, str)  # stop_id, name

    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui

        self._thread = None
        self._worker = None

        self.debounce = QTimer(self)
        self.debounce.setInterval(350)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.do_search)

        self._setup_ui()

    def _setup_ui(self):
        self.ui.tbl_results.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ui.tbl_results.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ui.tbl_results.setEditTriggers(QAbstractItemView.NoEditTriggers)

        if hasattr(self.ui, "sp_limit"):
            self.ui.sp_limit.setMinimum(1)
            self.ui.sp_limit.setMaximum(50)
            if self.ui.sp_limit.value() <= 0:
                self.ui.sp_limit.setValue(10)

        if hasattr(self.ui, "cb_only_stops"):
            self.ui.cb_only_stops.setChecked(True)

        self.ui.lbl_status.setText("Bereit.")

        self.ui.btn_search.clicked.connect(self.do_search)
        self.ui.le_query.returnPressed.connect(self.do_search)
        self.ui.le_query.textChanged.connect(lambda _: self.debounce.start())

        self.ui.btn_copy.clicked.connect(self.copy_selected_id)
        self.ui.btn_select.clicked.connect(self.emit_selected)
        self.ui.btn_close.clicked.connect(self._close_dialog)
        self.ui.tbl_results.cellDoubleClicked.connect(lambda r, c: self.emit_selected())

        self.ui.tbl_results.setColumnCount(5)
        self.ui.tbl_results.setHorizontalHeaderLabels(["Name", "Typ", "Qualität", "Best", "ID"])

    def _close_dialog(self):
        dlg = self.ui.le_query.window()
        if dlg:
            dlg.close()

    def _stop_running_thread(self):
        if self._thread is not None:
            try:
                self._thread.quit()
            except Exception:
                pass
            try:
                self._thread.wait(50)
            except Exception:
                pass
        self._thread = None
        self._worker = None

    def do_search(self):
        query = self.ui.le_query.text().strip()
        if len(query) < 2:
            self.ui.lbl_status.setText("Bitte mindestens 2 Zeichen eingeben.")
            return

        self.ui.lbl_status.setText("Suche…")
        LOG.info("UI search triggered: %r", query)

        self._stop_running_thread()

        self._thread = QThread(self)
        self._worker = StopFinderWorker(query=query, timeout_s=20, debug=True)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_results)
        self._worker.error.connect(self._on_error)

        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_error(self, msg: str):
        self.ui.lbl_status.setText(msg)
        LOG.error("UI error: %s", msg)

    def _on_results(self, items: list):
        only_stops = bool(getattr(self.ui, "cb_only_stops", None).isChecked()) if hasattr(self.ui, "cb_only_stops") else False
        if only_stops:
            items = [x for x in items if _is_stop_like(x)]


        def sort_key(x):
            return (
                0 if x.get("type") == "stop" else 1,
                0 if x.get("isBest") else 1,
                -int(x.get("matchQuality") or 0),
            )
        items.sort(key=sort_key)

        limit = 10
        if hasattr(self.ui, "sp_limit"):
            try:
                limit = int(self.ui.sp_limit.value())
            except Exception:
                limit = 10
        items = items[:limit]

        self._fill_table(items)

        if items:
            self.ui.tbl_results.selectRow(0)

        self.ui.lbl_status.setText(f"{len(items)} Treffer.")
        LOG.info("UI results shown: %d", len(items))

    def _fill_table(self, items: list):
        self.ui.tbl_results.setRowCount(0)
        for it in items:
            r = self.ui.tbl_results.rowCount()
            self.ui.tbl_results.insertRow(r)

            self.ui.tbl_results.setItem(r, 0, QTableWidgetItem(it.get("name", "")))
            self.ui.tbl_results.setItem(r, 1, QTableWidgetItem(it.get("type", "")))
            self.ui.tbl_results.setItem(r, 2, QTableWidgetItem(str(it.get("matchQuality", 0))))
            self.ui.tbl_results.setItem(r, 3, QTableWidgetItem("✓" if it.get("isBest") else ""))
            self.ui.tbl_results.setItem(r, 4, QTableWidgetItem(it.get("id", "")))

        self.ui.tbl_results.resizeColumnsToContents()

    def _get_selected_row(self):
        sel = self.ui.tbl_results.selectionModel()
        if not sel:
            return None
        rows = sel.selectedRows()
        if not rows:
            return None
        return rows[0].row()

    def copy_selected_id(self):
        r = self._get_selected_row()
        if r is None:
            self.ui.lbl_status.setText("Nichts ausgewählt.")
            return

        stop_id = self.ui.tbl_results.item(r, 4).text()
        QGuiApplication.clipboard().setText(stop_id)
        self.ui.lbl_status.setText(f"ID kopiert: {stop_id}")

    def emit_selected(self):
        r = self._get_selected_row()
        if r is None:
            self.ui.lbl_status.setText("Nichts ausgewählt.")
            return

        stop_id = self.ui.tbl_results.item(r, 4).text()
        name = self.ui.tbl_results.item(r, 0).text()

        QGuiApplication.clipboard().setText(stop_id)
        self.stop_selected.emit(stop_id, name)
        self.ui.lbl_status.setText(f"Übernommen: {stop_id} ({name})")
