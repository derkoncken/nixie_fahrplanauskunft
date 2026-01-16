# stop_finder.py
# -*- coding: utf-8 -*-
"""
StopFinder + Departures (VRR/EFA) für deinen GUI_2 Dialog.

UI-Objektnamen (aus deinem Ui_Dialog):
- le_query (QLineEdit)
- btn_search (QPushButton)
- sp_limit_stops (QSpinBox)   -> Anzahl Haltestellen
- sp_limit_deps  (QSpinBox)   -> Anzahl Abfahrten
- tbl_stops (QTableWidget, 1 Spalte)
- tbl_departures (QTableWidget, 4 Spalten)
- btn_apply (QPushButton)
- btn_close (QPushButton)

Tabellen-Dynamik (nach Ermessen):
- Stops: 1 Spalte, immer Stretch auf volle Breite
- Departures: Zeit/Linie/Bahnsteig ResizeToContents, Richtung Stretch (füllt Rest)
- horizontales Scrollen aus, Tabellen passen sich der Dialogbreite an
- Zeilenhöhe kompakt, AlternatingRowColors, Sortierung/Selektionshandling robust
- Abfahrten: Duplikate raus (Linie+Richtung+Bahnsteig), dann sortiert nach:
    Linie → Richtung → Bahnsteig (natürlich für Zahlen in Linien, z.B. 2 vor 10)
"""

import json
import logging
import os
import re
import time
from logging.handlers import RotatingFileHandler
from urllib.parse import urlencode

import requests
from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidgetItem,
)


EFA_BASE = "https://efa.vrr.de/standard"
URL_STOPFINDER = f"{EFA_BASE}/XML_STOPFINDER_REQUEST"
URL_DM = f"{EFA_BASE}/XML_DM_REQUEST"


# ---------------- Logging ----------------
def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("stopfinder")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    os.makedirs("logs", exist_ok=True)
    path = os.path.join("logs", "stopfinder.log")

    fh = RotatingFileHandler(path, maxBytes=800_000, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info("Logger initialized -> %s", path)
    return logger


LOG = _setup_logger()


def _safe_snippet(text: str, n: int = 1200) -> str:
    text = (text or "").replace("\r", "\\r").replace("\n", "\\n")
    return text[:n]


def _post_form_utf8(url: str, form: dict, timeout_s: int = 20) -> requests.Response:
    """x-www-form-urlencoded als UTF-8 Bytes senden -> Umlaute sicher korrekt."""
    body = urlencode(form, encoding="utf-8").encode("utf-8")
    headers = {
        "User-Agent": "tt_config",
        "Accept": "application/json,text/plain,*/*",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
    }
    return requests.post(url, data=body, headers=headers, timeout=timeout_s)


def _decode_response_json(resp: requests.Response) -> dict:
    """
    VRR liefert oft content-type text/html, manchmal ohne charset.
    Robust dekodieren: utf-8 default, fallback latin-1.
    """
    raw = resp.content or b""
    if not resp.encoding:
        resp.encoding = "utf-8"

    try:
        return json.loads(resp.text)
    except Exception:
        pass

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        pass

    return json.loads(raw.decode("latin-1", errors="replace"))


def fmt_hhmm(dt) -> str:
    if not isinstance(dt, dict):
        return "—"
    h = dt.get("hour")
    m = dt.get("minute")
    if h is None or m is None:
        return "—"
    try:
        return f"{int(h):02d}:{int(m):02d}"
    except Exception:
        return "—"


def _extract_points(payload: dict) -> list:
    """stopFinder.points ist im VRR JSON stabil vorhanden."""
    if not isinstance(payload, dict):
        return []
    sf = payload.get("stopFinder")
    if not isinstance(sf, dict):
        return []
    pts = sf.get("points")
    return pts if isinstance(pts, list) else []


def _extract_departure_list(payload: dict) -> list:
    """departureList kann verschachtelt sein -> rekursive Suche."""
    def find_key(obj, key: str):
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            for v in obj.values():
                got = find_key(v, key)
                if got is not None:
                    return got
        elif isinstance(obj, list):
            for it in obj:
                got = find_key(it, key)
                if got is not None:
                    return got
        return None

    dep = find_key(payload, "departureList")
    return dep if isinstance(dep, list) else []


def _nat_key(s: str):
    """Natürlicher Sort-Key: 'U11' < 'U2'? -> wird zu ['u', 11] etc."""
    s = (s or "").strip()
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


# ---------------- Workers ----------------
class StopSearchWorker(QObject):
    finished = pyqtSignal(list)  # list[{"id","name"}]
    error = pyqtSignal(str)

    def __init__(self, query: str, limit: int = 20, timeout_s: int = 20):
        super().__init__()
        self.query = query
        self.limit = max(1, int(limit))
        self.timeout_s = timeout_s

    def run(self):
        req_id = int(time.time() * 1000)
        try:
            form = {
                "outputFormat": "JSON",
                "language": "de",
                "type_sf": "any",
                "name_sf": self.query,
                "locationServerActive": 1,
                "anyMaxSizeHitList": max(30, self.limit * 4),
            }

            LOG.info("[%s] StopFinder start query=%r", req_id, self.query)
            LOG.debug("[%s] StopFinder POST %s form=%s", req_id, URL_STOPFINDER, form)

            r = _post_form_utf8(URL_STOPFINDER, form, timeout_s=self.timeout_s)
            LOG.info("[%s] StopFinder HTTP %s %s", req_id, r.status_code, r.reason)
            LOG.debug("[%s] StopFinder headers=%s", req_id, dict(r.headers))
            LOG.debug(
                "[%s] StopFinder raw-snippet=%s",
                req_id,
                _safe_snippet((r.content or b"")[:1200].decode("latin-1", "replace")),
            )
            r.raise_for_status()

            payload = _decode_response_json(r)
            points = _extract_points(payload)
            LOG.info("[%s] StopFinder points=%d", req_id, len(points))

            stops = []
            for p in points:
                if not isinstance(p, dict):
                    continue
                if str(p.get("anyType", "")).lower() != "stop":
                    continue

                name = str(p.get("name") or "").strip()
                if not name:
                    continue

                stop_id = str(p.get("stateless") or "").strip()
                if not stop_id:
                    ref = p.get("ref") if isinstance(p.get("ref"), dict) else {}
                    stop_id = str(ref.get("id") or "").strip()
                if not stop_id:
                    continue

                best = str(p.get("best") or "0") == "1"
                quality = int(p.get("quality") or 0)
                stops.append({"id": stop_id, "name": name, "best": best, "quality": quality})

            stops.sort(key=lambda x: (0 if x["best"] else 1, -x["quality"], x["name"].lower()))

            seen = set()
            out = []
            for s in stops:
                if s["id"] in seen:
                    continue
                seen.add(s["id"])
                out.append({"id": s["id"], "name": s["name"]})
                if len(out) >= self.limit:
                    break

            LOG.info("[%s] StopFinder stops(final)=%d", req_id, len(out))
            self.finished.emit(out)

        except Exception as e:
            LOG.exception("[%s] StopFinder error", req_id)
            self.error.emit(f"StopFinder Fehler: {e}")


class DeparturesWorker(QObject):
    finished = pyqtSignal(list)  # list[{"time","line","direction","platform"}]
    error = pyqtSignal(str)

    def __init__(self, stop_id: str, limit: int = 10, timeout_s: int = 20):
        super().__init__()
        self.stop_id = str(stop_id)
        self.limit = max(1, int(limit))
        self.timeout_s = timeout_s

    def run(self):
        req_id = int(time.time() * 1000)
        try:
            form = {
                "outputFormat": "JSON",
                "language": "de",
                "useRealtime": 1,
                "mode": "direct",
                "limit": self.limit,
                "type_dm": "stopID",
                "name_dm": self.stop_id,
            }

            LOG.info("[%s] DM start stop_id=%r limit=%s", req_id, self.stop_id, self.limit)
            LOG.debug("[%s] DM POST %s form=%s", req_id, URL_DM, form)

            r = _post_form_utf8(URL_DM, form, timeout_s=self.timeout_s)
            LOG.info("[%s] DM HTTP %s %s", req_id, r.status_code, r.reason)
            LOG.debug("[%s] DM headers=%s", req_id, dict(r.headers))
            LOG.debug(
                "[%s] DM raw-snippet=%s",
                req_id,
                _safe_snippet((r.content or b"")[:1200].decode("latin-1", "replace")),
            )
            r.raise_for_status()

            payload = _decode_response_json(r)
            dep_list = _extract_departure_list(payload)
            LOG.info("[%s] DM departureList=%d", req_id, len(dep_list))

            deps = []
            for e in dep_list:
                if not isinstance(e, dict):
                    continue

                serving = e.get("servingLine") if isinstance(e.get("servingLine"), dict) else {}
                line = str(serving.get("number") or "—").strip()
                direction = str(serving.get("direction") or "—").strip()
                platform = str((e.get("platformName") or e.get("platform") or "—")).strip()

                planned = fmt_hhmm(e.get("dateTime"))
                real = fmt_hhmm(e.get("realDateTime"))
                time_str = real if real != "—" else planned

                deps.append({"time": time_str, "line": line, "direction": direction, "platform": platform})

            # Duplikate raus: gleiche Linie + Richtung + Bahnsteig (Zeit egal)
            seen = set()
            deduped = []
            for d in deps:
                key = (
                    (d.get("line") or "").strip(),
                    (d.get("direction") or "").strip(),
                    (d.get("platform") or "").strip(),
                )
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(d)

            # Sortierung: Linie → Richtung → Bahnsteig (natürlich bei Linie + Bahnsteig)
            deduped.sort(
                key=lambda x: (
                    _nat_key(x.get("line", "")),
                    (x.get("direction") or "").strip().lower(),
                    _nat_key(x.get("platform", "")),
                )
            )

            # hart begrenzen
            deduped = deduped[: self.limit]
            self.finished.emit(deduped)

        except Exception as e:
            LOG.exception("[%s] DM error", req_id)
            self.error.emit(f"DM Fehler: {e}")


# ---------------- Controller ----------------
class StopFinderController(QObject):
    """
    Output:
      selection_applied.emit({
        "stop_id": ...,
        "stop_name": ...,
        "platform": ...,
        "line": ...,
      })
    """
    selection_applied = pyqtSignal(dict)

    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui

        self._thread = None
        self._worker = None

        self._selected_stop = None  # {"id","name"}
        self._selected_dep = None   # {"time","line","direction","platform"}

        self.debounce = QTimer(self)
        self.debounce.setInterval(350)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.search_stops)

        self._setup_ui()

    # ---------- UI setup / Table dynamics ----------
    def _setup_ui(self):
        # Stops table (1 Spalte)
        self.ui.tbl_stops.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ui.tbl_stops.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ui.tbl_stops.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ui.tbl_stops.setSortingEnabled(False)
        self.ui.tbl_stops.setColumnCount(1)
        self.ui.tbl_stops.setHorizontalHeaderLabels(["Haltestelle"])
        self.ui.tbl_stops.verticalHeader().setVisible(False)
        self.ui.tbl_stops.setAlternatingRowColors(True)
        self.ui.tbl_stops.setShowGrid(False)
        self.ui.tbl_stops.setWordWrap(False)
        self.ui.tbl_stops.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.ui.tbl_stops.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        # Departures table (4 Spalten)
        self.ui.tbl_departures.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ui.tbl_departures.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ui.tbl_departures.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ui.tbl_departures.setSortingEnabled(False)
        self.ui.tbl_departures.setColumnCount(4)
        self.ui.tbl_departures.setHorizontalHeaderLabels(["Zeit", "Linie", "Richtung", "Bahnsteig"])
        self.ui.tbl_departures.verticalHeader().setVisible(False)
        self.ui.tbl_departures.setAlternatingRowColors(True)
        self.ui.tbl_departures.setShowGrid(False)
        self.ui.tbl_departures.setWordWrap(False)
        self.ui.tbl_departures.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # ⭐ Spalten-Layout (dynamisch, widget-breit)
        hdr = self.ui.tbl_departures.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Zeit
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Linie
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Bahnsteig
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)           # Richtung füllt Rest
        hdr.setStretchLastSection(False)

        # angenehme Row-Höhe/Look
        self.ui.tbl_stops.verticalHeader().setDefaultSectionSize(24)
        self.ui.tbl_departures.verticalHeader().setDefaultSectionSize(24)

        # Spinboxes
        self.ui.sp_limit_stops.setMinimum(1)
        self.ui.sp_limit_stops.setMaximum(200)
        if self.ui.sp_limit_stops.value() < 1:
            self.ui.sp_limit_stops.setValue(10)

        self.ui.sp_limit_deps.setMinimum(1)
        self.ui.sp_limit_deps.setMaximum(200)
        if self.ui.sp_limit_deps.value() < 1:
            self.ui.sp_limit_deps.setValue(20)

        # Wiring
        self.ui.btn_search.clicked.connect(self.search_stops)
        self.ui.le_query.returnPressed.connect(self.search_stops)
        self.ui.le_query.textChanged.connect(lambda _: self.debounce.start())

        self.ui.tbl_stops.cellClicked.connect(self._on_stop_clicked)
        self.ui.tbl_departures.cellClicked.connect(self._on_dep_clicked)

        self.ui.btn_apply.clicked.connect(self.apply_selection)
        self.ui.btn_close.clicked.connect(self._close_dialog)

        # initial clear
        self._fill_stops([])
        self._fill_departures([])

        # optional: Start-Fokus ins Suchfeld
        try:
            self.ui.le_query.setFocus()
        except Exception:
            pass

    def _close_dialog(self):
        dlg = self.ui.le_query.window()
        if dlg:
            dlg.close()

    # ---------- Thread helper ----------
    def _stop_thread(self):
        if self._thread is not None:
            try:
                self._thread.quit()
            except Exception:
                pass
            try:
                self._thread.wait(120)
            except Exception:
                pass
        self._thread = None
        self._worker = None

    def _run_worker(self, worker: QObject, on_ok, on_err):
        self._stop_thread()
        self._thread = QThread(self)
        self._worker = worker
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(on_ok)
        self._worker.error.connect(on_err)

        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    # ---------- Search Stops ----------
    def search_stops(self):
        q = self.ui.le_query.text().strip()
        if len(q) < 2:

            return

        limit = max(1, int(self.ui.sp_limit_stops.value()))

        self._selected_stop = None
        self._selected_dep = None
        self._fill_stops([])
        self._fill_departures([])


        LOG.info("UI limits: stops=%s deps=%s", self.ui.sp_limit_stops.value(), self.ui.sp_limit_deps.value())
        self._run_worker(StopSearchWorker(q, limit=limit), self._on_stops, self._on_error)

    def _on_stops(self, stops: list):
        self._fill_stops(stops)

        if stops:
            self.ui.tbl_stops.selectRow(0)
            self._select_stop_row(0)

    def _fill_stops(self, stops: list):
        tbl = self.ui.tbl_stops
        tbl.setUpdatesEnabled(False)
        try:
            tbl.setRowCount(0)
            for s in stops:
                r = tbl.rowCount()
                tbl.insertRow(r)
                item = QTableWidgetItem(s.get("name", ""))
                item.setData(Qt.UserRole, s.get("id", ""))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                tbl.setItem(r, 0, item)
        finally:
            tbl.setUpdatesEnabled(True)

    def _on_stop_clicked(self, row: int, col: int):
        self._select_stop_row(row)

    def _select_stop_row(self, row: int):
        it = self.ui.tbl_stops.item(row, 0)
        if not it:
            return

        stop_id = str(it.data(Qt.UserRole) or "").strip()
        stop_name = it.text().strip()
        if not stop_id:
            return

        self._selected_stop = {"id": stop_id, "name": stop_name}
        self.fetch_departures()

    # ---------- Fetch Departures ----------
    def fetch_departures(self):
        if not self._selected_stop:
            return

        limit = max(1, int(self.ui.sp_limit_deps.value()))
        self._selected_dep = None
        self._fill_departures([])


        self._run_worker(
            DeparturesWorker(self._selected_stop["id"], limit=limit),
            self._on_deps,
            self._on_error,
        )

    def _on_deps(self, deps: list):
        self._fill_departures(deps)
        if deps:
            self.ui.tbl_departures.selectRow(0)
            self._select_dep_row(0)

        # kleiner Trick: nach dem Füllen einmal resize triggern (für ResizeToContents-Spalten)
        try:
            self.ui.tbl_departures.horizontalHeader().setMinimumSectionSize(20)
        except Exception:
            pass

    def _fill_departures(self, deps: list):
        tbl = self.ui.tbl_departures
        tbl.setUpdatesEnabled(False)
        try:
            tbl.setRowCount(0)
            for d in deps:
                r = tbl.rowCount()
                tbl.insertRow(r)

                def _mk(text: str):
                    it = QTableWidgetItem(text if text is not None else "—")
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    return it

                tbl.setItem(r, 0, _mk(d.get("time", "—")))
                tbl.setItem(r, 1, _mk(d.get("line", "—")))
                tbl.setItem(r, 2, _mk(d.get("direction", "—")))
                tbl.setItem(r, 3, _mk(d.get("platform", "—")))
        finally:
            tbl.setUpdatesEnabled(True)

    def _on_dep_clicked(self, row: int, col: int):
        self._select_dep_row(row)

    def _select_dep_row(self, row: int):
        t = self.ui.tbl_departures.item(row, 0)
        l = self.ui.tbl_departures.item(row, 1)
        d = self.ui.tbl_departures.item(row, 2)
        p = self.ui.tbl_departures.item(row, 3)
        if not (t and l and d and p):
            return
        self._selected_dep = {
            "time": t.text(),
            "line": l.text(),
            "direction": d.text(),
            "platform": p.text(),
        }

    # ---------- Apply ----------
    def apply_selection(self):
        if not self._selected_stop:
            return
        if not self._selected_dep:
            return

        payload = {
            "stop_id": self._selected_stop["id"],
            "stop_name": self._selected_stop["name"],
            "platform": self._selected_dep["platform"],
            "line": self._selected_dep["line"],
        }
        self.selection_applied.emit(payload)
        self._close_dialog()

    def _on_error(self, msg: str):
        LOG.error("UI error: %s", msg)

