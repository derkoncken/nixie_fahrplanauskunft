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

from stop_finder import StopFinderController  # <-- NEU


ESPRESSIF_VID = 0x303A
PORT = "/dev/ttyACM0"


# Wird später gelöscht, nur für UI-Kompilierung
def compile_ui(ui_path: Path, py_path: Path) -> None:
    """
    Compiles a Qt Designer .ui file into a Python file using pyuic via the current interpreter.
    """
    subprocess.run(
        [
            sys.executable,
            "-m", "PyQt5.uic.pyuic",
            str(ui_path.name),
            "-o",
            str(py_path.name),
        ],
        cwd=str(ui_path.parent),
        check=True,
    )


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

        # StopFinder Controller an Dialog-UI binden
        self.stopfinder = StopFinderController(self.ui, parent=self)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # UI setup
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Dialog-Handle (wichtig, sonst None / sofort zerstört)
        self.dialog = None

        # QAction -> Dialog öffnen
        self.ui.stop_finder.triggered.connect(self.open_dialog)

        # Timer setup für Status an den Radiobuttons
        self.timer = QTimer(self)
        self.timer.setInterval(1000)  # 1 Sekunde
        self.timer.timeout.connect(self.find_esp32_ports)
        self.ui.ping_blank.setVisible(False)
        self.timer.start()

        # Button-Verbindungen
        self.ui.upload_json.clicked.connect(self.send_json)
        self.ui.download_json.clicked.connect(self.download_json)

    # Functions triggered by UI actions
    def send_json(self):
        save_ui_to_json(self.ui)
        upload_json_to_esp32("config.json")
        self.reset_esp32()

    def download_json(self):
        download_json_from_esp32("config.json")
        load_ui_from_json(self.ui)
        self.reset_esp32()

    def reset_esp32(self):
        subprocess.run(["mpremote", "connect", PORT, "reset"], check=True)

    def open_dialog(self):
        if self.dialog is None:
            self.dialog = SettingsDialog(self)

            # Wenn im Dialog eine stop_id ausgewählt wird -> ins Mainwindow übernehmen
            self.dialog.stopfinder.stop_selected.connect(self.apply_stop_id_to_main)

        self.dialog.show()  # nicht-modal
        self.dialog.raise_()
        self.dialog.activateWindow()

    def apply_stop_id_to_main(self, stop_id: str, name: str):
        """
        Speichert die ausgewählte stop_id in das Feld 'haltestelle_1' (MainWindow UI).
        Optional kannst du auch den Namen irgendwo anzeigen – hier nur die ID.
        """
        # haltestelle_1 muss ein Widget mit setText() sein (z.B. QLineEdit)
        self.ui.haltestelle_1.setText(stop_id)

        # Optional: Dialog schließen nach Übernahme
        # if self.dialog is not None:
        #     self.dialog.close()

    # Status-Funktionen
    def find_esp32_ports(self):
        ports = []
        for p in list_ports.comports():
            if p.vid == ESPRESSIF_VID:
                ports.append(p.device)

        if ports:
            self.toggle_radiobuttons()
        else:
            self.ui.ping_blank.setChecked(True)

    def toggle_radiobuttons(self):
        if self.ui.ping.isChecked():
            self.ui.ping_blank.setChecked(True)
        else:
            self.ui.ping.setChecked(True)


def main() -> None:
    # Optional: UI vor dem Start kompilieren
    ui_file = Path("assets/GUI.ui")
    py_file = Path("assets/GUI.py")
    if ui_file.exists():
        compile_ui(ui_file, py_file)

    ui_file_2 = Path("assets/GUI_2.ui")
    py_file_2 = Path("assets/GUI_2.py")
    if ui_file_2.exists():
        compile_ui(ui_file_2, py_file_2)

    app = QApplication(sys.argv)

    # Theme setzen
    qdarktheme.setup_theme(corner_shape="sharp")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
