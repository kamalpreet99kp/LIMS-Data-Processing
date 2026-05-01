from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from tof_lims_desktop.ui.main_window import MainWindow
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    base_dir = Path(__file__).resolve().parent
    db_path = base_dir / "data" / "isotope_data.json"
    window = MainWindow(db_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
