from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from tof_lims_desktop.core.isotope_database import IsotopeDatabase
from tof_lims_desktop.core.mass_matching import IonMode, LabelDisplayMode, find_isotope_matches, format_label
from tof_lims_desktop.core.peak_detection import PeakDetectionSettings, detect_peaks


@dataclass
class PeakRecord:
    index: int
    mass: float
    counts: float
    enabled: bool = True
    selected_match: int = 0
    custom_label: str = ""


class MainWindow(QMainWindow):
    def __init__(self, isotope_db_path: Path):
        super().__init__()
        self.setWindowTitle("TOF-LIMS Spectrum Analyzer")
        self.resize(1300, 800)

        self.db = IsotopeDatabase(isotope_db_path)
        self.source_file: str | None = None
        self.masses = np.array([])
        self.counts = np.array([])
        self.peaks: list[PeakRecord] = []
        self.matches: dict[int, list] = {}
        self.label_items: list[pg.TextItem] = []

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.addLegend()
        self.curve = self.plot_widget.plot([], [], pen=pg.mkPen("c", width=1.5), name="Spectrum")
        self.peak_scatter = pg.ScatterPlotItem(size=8, brush="r", pen="w")
        self.peak_scatter.sigClicked.connect(self._on_peak_clicked)
        self.plot_widget.addItem(self.peak_scatter)

        splitter.addWidget(self.plot_widget)
        splitter.addWidget(self._build_controls())
        splitter.setSizes([900, 400])

        self.setCentralWidget(central)

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        file_group = QGroupBox("Data")
        fl = QVBoxLayout(file_group)
        load_btn = QPushButton("Load CSV / XLSX")
        load_btn.clicked.connect(self.load_data)
        fl.addWidget(load_btn)

        save_btn = QPushButton("Save Project JSON")
        save_btn.clicked.connect(self.save_project)
        fl.addWidget(save_btn)

        load_proj_btn = QPushButton("Load Project JSON")
        load_proj_btn.clicked.connect(self.load_project)
        fl.addWidget(load_proj_btn)

        export_btn = QPushButton("Export Plot (PNG/JPG/PDF)")
        export_btn.clicked.connect(self.export_plot)
        fl.addWidget(export_btn)

        layout.addWidget(file_group)

        settings = QGroupBox("Peak Detection + Matching")
        form = QFormLayout(settings)

        self.threshold_spin = QDoubleSpinBox(); self.threshold_spin.setRange(0, 1e9); self.threshold_spin.setValue(365.0)
        self.prominence_spin = QDoubleSpinBox(); self.prominence_spin.setRange(0, 1e9); self.prominence_spin.setValue(50.0)
        self.distance_spin = QSpinBox(); self.distance_spin.setRange(1, 10000); self.distance_spin.setValue(5)
        self.tolerance_spin = QDoubleSpinBox(); self.tolerance_spin.setRange(0.001, 5.0); self.tolerance_spin.setDecimals(3); self.tolerance_spin.setValue(0.2)

        self.mode_combo = QComboBox(); self.mode_combo.addItems([IonMode.POSITIVE.value, IonMode.NEGATIVE.value])
        self.label_mode_combo = QComboBox(); self.label_mode_combo.addItems([
            LabelDisplayMode.ELEMENT.value,
            LabelDisplayMode.ISOTOPE.value,
            LabelDisplayMode.ELEMENT_MASS.value,
        ])

        form.addRow("Min counts", self.threshold_spin)
        form.addRow("Prominence", self.prominence_spin)
        form.addRow("Distance", self.distance_spin)
        form.addRow("Mass tolerance", self.tolerance_spin)
        form.addRow("Ion mode", self.mode_combo)
        form.addRow("Label display", self.label_mode_combo)

        detect_btn = QPushButton("Detect Peaks")
        detect_btn.clicked.connect(self.detect_and_match)
        form.addRow(detect_btn)

        layout.addWidget(settings)

        self.peak_list = QListWidget()
        self.peak_list.currentRowChanged.connect(self._sync_peak_editor)
        layout.addWidget(QLabel("Detected Peaks"))
        layout.addWidget(self.peak_list)

        edit_group = QGroupBox("Label Controls")
        ef = QFormLayout(edit_group)
        self.enable_check = QCheckBox("Enable label")
        self.enable_check.stateChanged.connect(self._update_peak_from_editor)
        self.match_combo = QComboBox()
        self.match_combo.currentIndexChanged.connect(self._update_peak_from_editor)
        self.custom_edit = QLineEdit()
        self.custom_edit.editingFinished.connect(self._update_peak_from_editor)
        apply_label_btn = QPushButton("Add Custom Label At Current Peak")
        apply_label_btn.clicked.connect(self._add_custom_label)

        ef.addRow(self.enable_check)
        ef.addRow("Match options", self.match_combo)
        ef.addRow("Manual label", self.custom_edit)
        ef.addRow(apply_label_btn)
        layout.addWidget(edit_group)

        layout.addStretch(1)
        return panel

    def load_data(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Spectrum", "", "Data Files (*.csv *.xlsx)")
        if not path:
            return
        self.source_file = path

        if path.lower().endswith(".csv"):
            df = pd.read_csv(path)
        else:
            df = pd.read_excel(path)

        if df.shape[1] < 2:
            QMessageBox.warning(self, "Invalid file", "Need at least two columns: mass, counts")
            return

        self.masses = df.iloc[:, 0].to_numpy(dtype=float)
        self.counts = df.iloc[:, 1].to_numpy(dtype=float)
        self.curve.setData(self.masses, self.counts)
        self.peaks = []
        self.matches = {}
        self.peak_list.clear()
        self._redraw_peak_markers()
        self._clear_labels()

    def detect_and_match(self):
        if self.counts.size == 0:
            return
        settings = PeakDetectionSettings(
            min_height=self.threshold_spin.value(),
            prominence=self.prominence_spin.value(),
            distance=self.distance_spin.value(),
        )
        peak_idx = detect_peaks(self.counts, settings)
        self.peaks = [
            PeakRecord(index=int(i), mass=float(self.masses[i]), counts=float(self.counts[i]))
            for i in peak_idx
        ]
        self.matches = {}
        tolerance = self.tolerance_spin.value()
        ion_mode = IonMode(self.mode_combo.currentText())

        for p in self.peaks:
            m = find_isotope_matches(p.mass, self.db, tolerance=tolerance, ion_mode=ion_mode)
            self.matches[p.index] = m.matches

        self._refresh_peak_list()
        self._redraw_peak_markers()
        self._draw_labels()

    def _refresh_peak_list(self):
        self.peak_list.clear()
        for p in self.peaks:
            item = QListWidgetItem(f"m/z={p.mass:.3f}, counts={p.counts:.1f}")
            self.peak_list.addItem(item)

    def _redraw_peak_markers(self):
        if not self.peaks:
            self.peak_scatter.setData([], [])
            return
        x = [p.mass for p in self.peaks]
        y = [p.counts for p in self.peaks]
        self.peak_scatter.setData(x=x, y=y)

    def _clear_labels(self):
        for item in self.label_items:
            self.plot_widget.removeItem(item)
        self.label_items.clear()

    def _draw_labels(self):
        self._clear_labels()
        mode = LabelDisplayMode(self.label_mode_combo.currentText())
        for p in self.peaks:
            if not p.enabled:
                continue
            text = p.custom_label.strip()
            if not text:
                options = self.matches.get(p.index, [])
                if options:
                    selected = min(p.selected_match, len(options) - 1)
                    text = format_label(options[selected], mode, p.mass)
                else:
                    text = f"{p.mass:.3f}"
            label = pg.TextItem(text=text, color="y", anchor=(0.5, 1.4))
            label.setPos(p.mass, p.counts)
            self.plot_widget.addItem(label)
            self.label_items.append(label)

    def _on_peak_clicked(self, _, points):
        if not points:
            return
        clicked_mass = float(points[0].pos().x())
        closest = min(range(len(self.peaks)), key=lambda i: abs(self.peaks[i].mass - clicked_mass))
        self.peak_list.setCurrentRow(closest)

    def _sync_peak_editor(self, row: int):
        if row < 0 or row >= len(self.peaks):
            return
        p = self.peaks[row]
        self.enable_check.blockSignals(True)
        self.match_combo.blockSignals(True)

        self.enable_check.setChecked(p.enabled)
        self.custom_edit.setText(p.custom_label)

        self.match_combo.clear()
        options = self.matches.get(p.index, [])
        if not options:
            self.match_combo.addItem("No isotope match")
        else:
            for opt in options:
                self.match_combo.addItem(f"{opt.isotope} ({opt.mass:.3f})")
            self.match_combo.setCurrentIndex(min(p.selected_match, len(options) - 1))

        self.enable_check.blockSignals(False)
        self.match_combo.blockSignals(False)

    def _update_peak_from_editor(self):
        row = self.peak_list.currentRow()
        if row < 0 or row >= len(self.peaks):
            return
        p = self.peaks[row]
        p.enabled = self.enable_check.isChecked()
        p.selected_match = max(0, self.match_combo.currentIndex())
        p.custom_label = self.custom_edit.text().strip()
        self._draw_labels()

    def _add_custom_label(self):
        self._update_peak_from_editor()

    def export_plot(self):
        if self.masses.size == 0:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Plot", "", "Images/PDF (*.png *.jpg *.pdf)")
        if not path:
            return
        exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
        if path.lower().endswith(".pdf"):
            # pyqtgraph image exporter doesn't directly write PDF; save PNG fallback for prototype.
            exporter.export(path + ".png")
            QMessageBox.information(self, "Export", "PDF placeholder: saved PNG with .pdf.png suffix")
        else:
            exporter.export(path)

    def save_project(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "JSON (*.json)")
        if not path:
            return
        payload = {
            "source_file": self.source_file,
            "threshold": self.threshold_spin.value(),
            "prominence": self.prominence_spin.value(),
            "distance": self.distance_spin.value(),
            "tolerance": self.tolerance_spin.value(),
            "ion_mode": self.mode_combo.currentText(),
            "label_mode": self.label_mode_combo.currentText(),
            "peaks": [p.__dict__ for p in self.peaks],
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "JSON (*.json)")
        if not path:
            return
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.threshold_spin.setValue(payload.get("threshold", 365.0))
        self.prominence_spin.setValue(payload.get("prominence", 50.0))
        self.distance_spin.setValue(payload.get("distance", 5))
        self.tolerance_spin.setValue(payload.get("tolerance", 0.2))
        self.mode_combo.setCurrentText(payload.get("ion_mode", IonMode.POSITIVE.value))
        self.label_mode_combo.setCurrentText(payload.get("label_mode", LabelDisplayMode.ISOTOPE.value))

        src = payload.get("source_file")
        if src and Path(src).exists():
            self.source_file = src
            df = pd.read_csv(src) if src.lower().endswith(".csv") else pd.read_excel(src)
            self.masses = df.iloc[:, 0].to_numpy(dtype=float)
            self.counts = df.iloc[:, 1].to_numpy(dtype=float)
            self.curve.setData(self.masses, self.counts)

        self.peaks = [PeakRecord(**item) for item in payload.get("peaks", [])]
        tolerance = self.tolerance_spin.value()
        ion_mode = IonMode(self.mode_combo.currentText())
        self.matches = {
            p.index: find_isotope_matches(p.mass, self.db, tolerance, ion_mode).matches
            for p in self.peaks
        }
        self._refresh_peak_list()
        self._redraw_peak_markers()
        self._draw_labels()
