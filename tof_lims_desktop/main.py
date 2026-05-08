from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from tof_lims_desktop.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow(Path(__file__).resolve().parent / 'data' / 'isotope_data.json')
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
