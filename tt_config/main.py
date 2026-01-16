import sys
import subprocess
from pathlib import Path

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QDialog
import qdarktheme

from assets.GUI import Ui_MainWindow
from assets.GUI_2 import Ui_Dialog

from esp32_data_handler import upload_json_to_esp32, download_json_from_esp32
from json_handler import save_ui_to_json, load_ui_from_json
from serial.tools import list_ports

from stop_finder import StopFinderController  # wichtig


ESPRESSIF_VID = 0x303A
PORT = "/dev/ttyACM0"


def compile_ui(ui_path: Path, py_path: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "PyQt5.uic.pyuic", str(ui_path.name), "-o", str(py_path.name)],
        cwd=str(ui_path.parent),
        check=True,
    )


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        self.stopfinder = StopFinderController(self.ui, parent=self)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.dialog = None
        self._target_departure = 1  # 1 oder 2

        # Theme state (NEU)
        self._theme = "dark"  # oder "light" als Startwert
        self._corner_shape = "sharp"

        # Buttons im UI
        self.ui.choose_line_1.clicked.connect(lambda: self.open_dialog(target=1))
        self.ui.choose_line_2.clicked.connect(lambda: self.open_dialog(target=2))

        # Upload/Download/Reset
        self.ui.upload_json.clicked.connect(self.on_upload_clicked)
        self.ui.download_json.clicked.connect(self.on_download_clicked)
        self.ui.reset_esp.clicked.connect(self.reset_esp32)

        # Theme Toggle Button (NEU)
        # Voraussetzung: im QtDesigner heißt der Button wirklich "switch_mode"
        self.ui.switch_mode.triggered.connect(self.toggle_theme)

        # Timer: ESP Status
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.find_esp32_ports)
        self.ui.ping_blank.setVisible(False)
        self.timer.start()

        # Theme initial setzen (NEU)
        qdarktheme.setup_theme(self._theme, corner_shape=self._corner_shape)

    # -------- Theme --------
    def toggle_theme(self):
        self._theme = "light" if self._theme == "dark" else "dark"
        qdarktheme.setup_theme(self._theme, corner_shape=self._corner_shape)
        self.ui.switch_mode.setText("Darkmode" if self._theme == "light" else "Lightmode")

        # Optional: Plot-Widgets background switchen (wenn du welche hast)
        # Beispiel:
        # self.plot_widget.setBackground("k" if self._theme == "dark" else "w")

    # -------- Upload/Download Flow --------
    def on_upload_clicked(self):
        save_ui_to_json(self.ui, "config.json")
        upload_json_to_esp32("config.json")
        self.reset_esp32()

    def on_download_clicked(self):
        download_json_from_esp32("config.json", "config.json")
        load_ui_from_json(self.ui, "config.json")

    def reset_esp32(self):
        subprocess.run(["mpremote", "connect", PORT, "reset"], check=True)

    # -------- StopFinder Dialog --------
    def open_dialog(self, target: int):
        self._target_departure = 1 if target != 2 else 2

        if self.dialog is None:
            self.dialog = SettingsDialog(self)
            self.dialog.stopfinder.selection_applied.connect(self.apply_selection_to_main)

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def apply_selection_to_main(self, data: dict):
        stop_id = data.get("stop_id", "")
        stop_name = data.get("stop_name", "")
        platform = data.get("platform", "")
        line = data.get("line", "")

        if self._target_departure == 1:
            self.ui.haltestelle_1.setText(stop_name)
            self.ui.line_no_1.setText(line)
            self.ui.bahnsteig_1.setText(platform)
            self.ui.haltestelle_1.setProperty("stop_id", stop_id)
        else:
            self.ui.haltestelle_2.setText(stop_name)
            self.ui.line_no_2.setText(line)
            self.ui.bahnsteig_2.setText(platform)
            self.ui.haltestelle_2.setText(stop_name)
            self.ui.bahnsteig_2.setText(platform)
            self.ui.haltestelle_2.setProperty("stop_id", stop_id)

    # -------- ESP Status --------
    def find_esp32_ports(self):
        ports = [p.device for p in list_ports.comports() if p.vid == ESPRESSIF_VID]

        if ports:
            self.toggle_radiobuttons()
            self.ui.upload_json.setEnabled(True)
            self.ui.download_json.setEnabled(True)
            self.ui.reset_esp.setEnabled(True)
        else:
            self.ui.ping_blank.setChecked(True)
            self.ui.upload_json.setEnabled(False)
            self.ui.download_json.setEnabled(False)
            self.ui.reset_esp.setEnabled(False)

    def toggle_radiobuttons(self):
        if self.ui.ping.isChecked():
            self.ui.ping_blank.setChecked(True)
        else:
            self.ui.ping.setChecked(True)


def main() -> None:
    ui_file = Path("assets/GUI.ui")
    py_file = Path("assets/GUI.py")
    if ui_file.exists():
        compile_ui(ui_file, py_file)

    ui_file_2 = Path("assets/GUI_2.ui")
    py_file_2 = Path("assets/GUI_2.py")
    if ui_file_2.exists():
        compile_ui(ui_file_2, py_file_2)

    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
