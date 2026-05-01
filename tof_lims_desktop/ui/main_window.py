from __future__ import annotations

import json
from dataclasses import asdict, dataclass
codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

from dataclasses import dataclass
 main
from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtCore import Qt
 codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac
from PySide6.QtGui import QAction

from PySide6.QtGui import QAction, QColor
main
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
 main
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
 codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
 main
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
 codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

    QSplitter,
 main
    QVBoxLayout,
    QWidget,
)

from tof_lims_desktop.core.mass_matching import (
    IonMode,
    LabelDisplayMode,
    find_isotope_matches,
    format_label,
)
from tof_lims_desktop.core.isotope_database import IsotopeDatabase
from tof_lims_desktop.core.peak_detection import PeakDetectionSettings, detect_peaks
codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

from core.isotope_database import IsotopeDatabase
from core.mass_matching import IonMode, LabelDisplayMode, find_isotope_matches, format_label
from core.peak_detection import PeakDetectionSettings, detect_peaks
main


@dataclass
class PeakRecord:
    index: int
    measured_mass: float
    calibrated_mass: float
    counts: float
    enabled: bool = True
    selected_match: int = 0
    final_label: str = ""


class CalibrationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mass Calibration")
        self.a_spin = QDoubleSpinBox(); self.a_spin.setRange(0.1, 10.0); self.a_spin.setValue(1.0); self.a_spin.setDecimals(8)
        self.b_spin = QDoubleSpinBox(); self.b_spin.setRange(-1000, 1000); self.b_spin.setValue(0.0); self.b_spin.setDecimals(8)
        f = QFormLayout(self)
        f.addRow("a (slope)", self.a_spin)
        f.addRow("b (offset)", self.b_spin)
        f.addRow(QLabel("Model: calibrated_mass = a * measured_mass + b"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def values(self):
        return self.a_spin.value(), self.b_spin.value()
 codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

    mass: float
    counts: float
    enabled: bool = True
    selected_match: int = 0
    custom_label: str = ""
 main


class MainWindow(QMainWindow):
    def __init__(self, isotope_db_path: Path):
        super().__init__()
        self.setWindowTitle("TOF-LIMS Spectrum Analyzer")
        self.resize(1500, 900)
codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

        self.resize(1300, 800)
 main

        self.db = IsotopeDatabase(isotope_db_path)
        self.source_file: str | None = None
        self.masses = np.array([])
        self.raw_counts = np.array([])
        self.display_counts = np.array([])
        self.calibration_a = 1.0
        self.calibration_b = 0.0
        self.baseline_mode = "none"
        self.manual_baseline = 0.0

        self.peaks: list[PeakRecord] = []
        self.matches: dict[int, list] = {}
        self.label_items: list[pg.TextItem] = []
        self.manual_notes: list[dict] = []

        self._build_ui()
        self._apply_plot_style()

    def _build_ui(self):
        self.setStatusBar(QStatusBar())
        self._build_menu_toolbar()

        central = QWidget()
        root = QHBoxLayout(central)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setLabel("bottom", "Mass (amu)")
        self.plot_widget.setLabel("left", "Intensity (Counts)")
        self.plot_widget.setXRange(0, 260)
        self.plot_widget.setYRange(1, 1e4)

        self.title_item = pg.TextItem(text="TOF-LIMS Spectrum", anchor=(0.5, 0), color="w")
        self.plot_widget.addItem(self.title_item)

        self.curve = self.plot_widget.plot([], [], pen=pg.mkPen("#00C8FF", width=2.0), name="Spectrum")
        self.symbol_scatter = pg.ScatterPlotItem(size=4, brush="#00C8FF", pen=None)
        self.plot_widget.addItem(self.symbol_scatter)

codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

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
 main
        self.peak_scatter = pg.ScatterPlotItem(size=8, brush="r", pen="w")
        self.peak_scatter.sigClicked.connect(self._on_peak_clicked)
        self.plot_widget.addItem(self.peak_scatter)

        root.addWidget(self.plot_widget, 3)
        root.addWidget(self._build_controls(), 2)
        self.setCentralWidget(central)

    def _build_menu_toolbar(self):
        m = self.menuBar().addMenu("File")
        load = QAction("Load CSV/XLSX", self); load.triggered.connect(self.load_data); m.addAction(load)
        save_proj = QAction("Save Editable Project", self); save_proj.triggered.connect(self.save_project); m.addAction(save_proj)
        load_proj = QAction("Load Project", self); load_proj.triggered.connect(self.load_project); m.addAction(load_proj)
        export = QAction("Export JPG/PNG/PDF", self); export.triggered.connect(self.export_plot); m.addAction(export)

        tools = self.menuBar().addMenu("Tools")
        cal = QAction("Calibrate Mass", self); cal.triggered.connect(self.open_calibration_dialog); tools.addAction(cal)
        reset_cal = QAction("Reset Calibration", self); reset_cal.triggered.connect(self.reset_calibration); tools.addAction(reset_cal)
        add_note = QAction("Add Text Note", self); add_note.triggered.connect(self.add_manual_note); tools.addAction(add_note)

        tb = QToolBar("Main")
        tb.addAction(load); tb.addAction(save_proj); tb.addAction(export); tb.addAction(cal)
        self.addToolBar(tb)

    def _build_controls(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        file_box = QGroupBox("File / Project")
        fl = QVBoxLayout(file_box)
        for txt, cb in [
            ("Load CSV / XLSX", self.load_data),
            ("Save Editable Project", self.save_project),
            ("Load Project", self.load_project),
            ("Export JPG", self.export_plot),
        ]:
            b = QPushButton(txt); b.clicked.connect(cb); fl.addWidget(b)
        layout.addWidget(file_box)

        peak_box = QGroupBox("Peak Detection")
        pf = QFormLayout(peak_box)
        self.threshold_spin = QDoubleSpinBox(); self.threshold_spin.setRange(0, 1e9); self.threshold_spin.setValue(365.0); self.threshold_spin.setToolTip("Threshold: minimum intensity required to count as a peak.")
        self.prominence_spin = QDoubleSpinBox(); self.prominence_spin.setRange(0, 1e9); self.prominence_spin.setValue(50.0); self.prominence_spin.setToolTip("Prominence: height above local baseline/noise.")
        self.distance_spin = QSpinBox(); self.distance_spin.setRange(1, 100000); self.distance_spin.setValue(5); self.distance_spin.setToolTip("Distance: minimum spacing in data points.")
        self.width_spin = QDoubleSpinBox(); self.width_spin.setRange(0, 1e6); self.width_spin.setValue(0.0)
        self.tolerance_spin = QDoubleSpinBox(); self.tolerance_spin.setRange(0.01, 5.0); self.tolerance_spin.setValue(0.2); self.tolerance_spin.setDecimals(3)
        self.tolerance_spin.setToolTip("Mass tolerance (amu/Da). Narrow tolerance requires calibration.")
 codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

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

 main
        self.mode_combo = QComboBox(); self.mode_combo.addItems([IonMode.POSITIVE.value, IonMode.NEGATIVE.value])
        self.label_mode_combo = QComboBox(); self.label_mode_combo.addItems([
            LabelDisplayMode.ELEMENT.value,
            LabelDisplayMode.ISOTOPE.value,
            LabelDisplayMode.ELEMENT_MASS.value,
            "ion",
        ])
        detect = QPushButton("Re-detect Peaks"); detect.clicked.connect(self.detect_and_match)
        pf.addRow("Threshold", self.threshold_spin); pf.addRow("Prominence", self.prominence_spin)
        pf.addRow("Distance (pts)", self.distance_spin); pf.addRow("Peak width", self.width_spin)
        pf.addRow("Mass tolerance (amu/Da)", self.tolerance_spin)
        pf.addRow("Ion mode", self.mode_combo); pf.addRow("Label format", self.label_mode_combo)
        pf.addRow(detect)
        layout.addWidget(peak_box)

        style_box = QGroupBox("Graph Style")
        sf = QFormLayout(style_box)
        self.line_width_spin = QDoubleSpinBox(); self.line_width_spin.setRange(0.1, 10); self.line_width_spin.setValue(2.0)
        self.symbol_show_check = QCheckBox("Show symbols")
        self.symbol_size_spin = QDoubleSpinBox(); self.symbol_size_spin.setRange(1, 20); self.symbol_size_spin.setValue(4)
        self.grid_check = QCheckBox("Show grid"); self.grid_check.setChecked(True)
        self.bg_btn = QPushButton("Background color")
        self.line_btn = QPushButton("Line color")
        self.label_color_btn = QPushButton("Label color")
        self.axis_font_spin = QSpinBox(); self.axis_font_spin.setRange(8, 28); self.axis_font_spin.setValue(12)
        self.label_font_spin = QSpinBox(); self.label_font_spin.setRange(8, 28); self.label_font_spin.setValue(11)
        self.label_rot_spin = QSpinBox(); self.label_rot_spin.setRange(-180, 180); self.label_rot_spin.setValue(0)
        self.label_bold_check = QCheckBox("Label bold")
        self.label_italic_check = QCheckBox("Label italic")
        for w in [self.line_width_spin, self.symbol_show_check, self.symbol_size_spin, self.grid_check,
                  self.axis_font_spin, self.label_font_spin, self.label_rot_spin, self.label_bold_check, self.label_italic_check]:
            if hasattr(w, 'valueChanged'): w.valueChanged.connect(self._apply_plot_style)
            if hasattr(w, 'stateChanged'): w.stateChanged.connect(self._apply_plot_style)
        self.line_btn.clicked.connect(lambda: self._pick_color("line"))
        self.bg_btn.clicked.connect(lambda: self._pick_color("bg"))
        self.label_color_btn.clicked.connect(lambda: self._pick_color("label"))
        sf.addRow("Line width", self.line_width_spin); sf.addRow(self.symbol_show_check)
        sf.addRow("Symbol size", self.symbol_size_spin); sf.addRow(self.grid_check)
        sf.addRow(self.line_btn); sf.addRow(self.bg_btn); sf.addRow(self.label_color_btn)
        sf.addRow("Axis font size", self.axis_font_spin); sf.addRow("Label font size", self.label_font_spin)
        sf.addRow("Label rotation", self.label_rot_spin); sf.addRow(self.label_bold_check); sf.addRow(self.label_italic_check)
        layout.addWidget(style_box)

        axis_box = QGroupBox("Axes and Title")
        af = QFormLayout(axis_box)
        self.x_label_edit = QLineEdit("Mass (amu)")
        self.y_label_edit = QLineEdit("Intensity (Counts)")
        self.title_edit = QLineEdit("TOF-LIMS Positive Mode Spectrum")
        self.title_size_spin = QSpinBox(); self.title_size_spin.setRange(10, 36); self.title_size_spin.setValue(16)
        self.title_show_check = QCheckBox("Show title"); self.title_show_check.setChecked(True)
        self.xmin_spin = QDoubleSpinBox(); self.xmin_spin.setRange(-1e6, 1e6); self.xmin_spin.setValue(0)
        self.xmax_spin = QDoubleSpinBox(); self.xmax_spin.setRange(-1e6, 1e6); self.xmax_spin.setValue(260)
        self.ymin_spin = QDoubleSpinBox(); self.ymin_spin.setRange(-1e6, 1e9); self.ymin_spin.setValue(1)
        self.ymax_spin = QDoubleSpinBox(); self.ymax_spin.setRange(-1e6, 1e9); self.ymax_spin.setValue(1e4)
        self.y_scale_combo = QComboBox(); self.y_scale_combo.addItems(["linear", "log"])
        axis_apply = QPushButton("Apply Axis/Title"); axis_apply.clicked.connect(self._apply_axis_title)
        axis_reset = QPushButton("Reset Auto Scale"); axis_reset.clicked.connect(self._auto_scale)
        af.addRow("X label", self.x_label_edit); af.addRow("Y label", self.y_label_edit)
        af.addRow("Title", self.title_edit); af.addRow("Title font size", self.title_size_spin); af.addRow(self.title_show_check)
        af.addRow("X min", self.xmin_spin); af.addRow("X max", self.xmax_spin); af.addRow("Y min", self.ymin_spin); af.addRow("Y max", self.ymax_spin)
        af.addRow("Y scale", self.y_scale_combo); af.addRow(axis_apply); af.addRow(axis_reset)
        layout.addWidget(axis_box)

        baseline_box = QGroupBox("Baseline")
        bf = QFormLayout(baseline_box)
        self.baseline_combo = QComboBox(); self.baseline_combo.addItems(["none", "subtract_min", "constant"])
        self.manual_baseline_spin = QDoubleSpinBox(); self.manual_baseline_spin.setRange(-1e6, 1e6)
        apply_baseline = QPushButton("Apply Baseline"); apply_baseline.clicked.connect(self.apply_baseline)
        bf.addRow("Mode", self.baseline_combo); bf.addRow("Constant", self.manual_baseline_spin); bf.addRow(apply_baseline)
        layout.addWidget(baseline_box)

        self.peak_table = QTableWidget(0, 8)
        self.peak_table.setHorizontalHeaderLabels(["Show", "Measured", "Calibrated", "Counts", "Suggested", "Final Label", "Error", "Candidates"])
        self.peak_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.peak_table.itemChanged.connect(self._table_item_changed)
        layout.addWidget(QLabel("Detected Peaks"))
        layout.addWidget(self.peak_table)
        layout.addStretch(1)
        return panel

    def _apply_plot_style(self):
        if not hasattr(self, "curve"):
            return
        pen = pg.mkPen(getattr(self, "line_color", "#00C8FF"), width=self.line_width_spin.value())
        self.curve.setPen(pen)
        self.plot_widget.showGrid(x=self.grid_check.isChecked(), y=self.grid_check.isChecked(), alpha=0.2)
        if self.symbol_show_check.isChecked():
            self.symbol_scatter.setData(self._plot_x_data(), self.display_counts, size=self.symbol_size_spin.value(), brush=getattr(self, "line_color", "#00C8FF"))
        else:
            self.symbol_scatter.setData([], [])
        self._draw_labels()

    def _pick_color(self, target: str):
        c = QColorDialog.getColor(parent=self)
        if not c.isValid():
            return
        if target == "line": self.line_color = c.name()
        elif target == "bg": self.plot_widget.setBackground(c.name())
        elif target == "label": self.label_color = c.name()
        self._apply_plot_style()

    def _plot_x_data(self):
        return self.calibrated_masses() if self.masses.size else np.array([])

    def calibrated_masses(self):
        return self.calibration_a * self.masses + self.calibration_b

    def load_data(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Spectrum", "", "Data Files (*.csv *.xlsx)")
        if not path: return
        self.source_file = path
        df = pd.read_csv(path) if path.lower().endswith(".csv") else pd.read_excel(path)
        self.masses = df.iloc[:, 0].to_numpy(dtype=float)
        self.raw_counts = df.iloc[:, 1].to_numpy(dtype=float)
        self.display_counts = self.raw_counts.copy()
        self._render_curve(); self.detect_and_match()

    def _render_curve(self):
        x = self._plot_x_data()
        y = np.clip(self.display_counts, 1e-12, None) if self.y_scale_combo.currentText() == "log" else self.display_counts
        self.curve.setData(x, y)
        self._apply_plot_style()
        self._apply_axis_title()

    def apply_baseline(self):
        self.baseline_mode = self.baseline_combo.currentText()
        self.manual_baseline = self.manual_baseline_spin.value()
        if self.raw_counts.size == 0: return
        if self.baseline_mode == "none":
            self.display_counts = self.raw_counts.copy()
        elif self.baseline_mode == "subtract_min":
            self.display_counts = self.raw_counts - np.min(self.raw_counts)
        else:
            self.display_counts = self.raw_counts - self.manual_baseline
        self._render_curve(); self.detect_and_match()

    def detect_and_match(self):
        if self.display_counts.size == 0: return
        settings = PeakDetectionSettings(self.threshold_spin.value(), self.prominence_spin.value(), self.distance_spin.value())
        idx = detect_peaks(self.display_counts, settings)
        cal = self.calibrated_masses()
        tol = self.tolerance_spin.value()
        ion_mode = IonMode(self.mode_combo.currentText())
        self.peaks, self.matches = [], {}
        for i in idx:
            p = PeakRecord(int(i), float(self.masses[i]), float(cal[i]), float(self.display_counts[i]))
            matches = find_isotope_matches(p.calibrated_mass, self.db, tol, ion_mode).matches
            self.peaks.append(p)
            self.matches[p.index] = matches
        self._refresh_peak_table(); self._redraw_peak_markers(); self._draw_labels()

    def _format_match_label(self, peak: PeakRecord, match_idx: int):
        opts = self.matches.get(peak.index, [])
        if not opts:
            return "Unmatched"
        m = opts[min(match_idx, len(opts)-1)]
        mode = self.label_mode_combo.currentText()
        if mode == "ion":
            suffix = "+" if self.mode_combo.currentText() == IonMode.POSITIVE.value else "-"
            return f"{m.isotope}{suffix}"
        label_mode = LabelDisplayMode(mode)
        return format_label(m, label_mode, peak.calibrated_mass)

    def _refresh_peak_table(self):
        self.peak_table.blockSignals(True)
        self.peak_table.setRowCount(len(self.peaks))
        for r, p in enumerate(self.peaks):
            chk = QTableWidgetItem(); chk.setFlags(chk.flags() | Qt.ItemIsUserCheckable); chk.setCheckState(Qt.Checked if p.enabled else Qt.Unchecked)
            self.peak_table.setItem(r, 0, chk)
            self.peak_table.setItem(r, 1, QTableWidgetItem(f"{p.measured_mass:.4f}"))
            self.peak_table.setItem(r, 2, QTableWidgetItem(f"{p.calibrated_mass:.4f}"))
            self.peak_table.setItem(r, 3, QTableWidgetItem(f"{p.counts:.1f}"))
            suggested = self._format_match_label(p, p.selected_match)
            self.peak_table.setItem(r, 4, QTableWidgetItem(suggested))
            self.peak_table.setItem(r, 5, QTableWidgetItem(p.final_label or suggested))
            opts = self.matches.get(p.index, [])
            err = "-" if not opts else f"{p.calibrated_mass - opts[p.selected_match].mass:+.4f}"
            self.peak_table.setItem(r, 6, QTableWidgetItem(err))
            cand = "; ".join([o.isotope for o in opts]) if opts else "Unmatched"
            self.peak_table.setItem(r, 7, QTableWidgetItem(cand))
        self.peak_table.blockSignals(False)

    def _table_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        if row < 0 or row >= len(self.peaks): return
        p = self.peaks[row]
        if item.column() == 0:
            p.enabled = item.checkState() == Qt.Checked
        elif item.column() == 5:
            p.final_label = item.text().strip()
        self._draw_labels()

    def _redraw_peak_markers(self):
        if not self.peaks:
            self.peak_scatter.setData([], []); return
        self.peak_scatter.setData([p.calibrated_mass for p in self.peaks], [p.counts for p in self.peaks])

    def _clear_labels(self):
        for i in self.label_items: self.plot_widget.removeItem(i)
 codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

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
 main
        self.label_items.clear()

    def _draw_labels(self):
        self._clear_labels()
        color = getattr(self, "label_color", "#FFFF00")
        for p in self.peaks:
            if not p.enabled: continue
            text = p.final_label or self._format_match_label(p, p.selected_match)
            lb = pg.TextItem(text=text, color=color, anchor=(0.5, 1.2))
            f = lb.textItem.font()
            f.setPointSize(self.label_font_spin.value())
            f.setBold(self.label_bold_check.isChecked()); f.setItalic(self.label_italic_check.isChecked())
            lb.textItem.setFont(f)
            lb.setRotation(self.label_rot_spin.value())
            lb.setPos(p.calibrated_mass, p.counts)
            self.plot_widget.addItem(lb)
            self.label_items.append(lb)
        self._update_title_position()

    def _apply_axis_title(self):
        self.plot_widget.setLabel("bottom", self.x_label_edit.text(), **{"size": f"{self.axis_font_spin.value()}pt"})
        self.plot_widget.setLabel("left", self.y_label_edit.text(), **{"size": f"{self.axis_font_spin.value()}pt"})
        self.plot_widget.setXRange(self.xmin_spin.value(), self.xmax_spin.value(), padding=0)
        self.plot_widget.setYRange(self.ymin_spin.value(), self.ymax_spin.value(), padding=0)
        self.plot_widget.setLogMode(x=False, y=self.y_scale_combo.currentText() == "log")
        self.title_item.setText(self.title_edit.text() if self.title_show_check.isChecked() else "", color="w")
        font = self.title_item.textItem.font(); font.setPointSize(self.title_size_spin.value()); self.title_item.textItem.setFont(font)
        self._update_title_position()

    def _update_title_position(self):
        vb = self.plot_widget.plotItem.vb.viewRange()
        x = (vb[0][0] + vb[0][1]) / 2
        y = vb[1][1]
        self.title_item.setPos(x, y)

    def _auto_scale(self):
        self.plot_widget.enableAutoRange()

    def _on_peak_clicked(self, _, points):
        if not points: return
        x = float(points[0].pos().x())
        row = min(range(len(self.peaks)), key=lambda i: abs(self.peaks[i].calibrated_mass - x))
        self.peak_table.selectRow(row)

    def _on_mouse_moved(self, pos):
        vb = self.plot_widget.plotItem.vb
        point = vb.mapSceneToView(pos)
        self.statusBar().showMessage(f"Mass: {point.x():.4f} | Intensity: {point.y():.2f}")

    def open_calibration_dialog(self):
        d = CalibrationDialog(self)
        d.a_spin.setValue(self.calibration_a); d.b_spin.setValue(self.calibration_b)
        if d.exec():
            self.calibration_a, self.calibration_b = d.values()
            self._render_curve(); self.detect_and_match()

    def reset_calibration(self):
        self.calibration_a, self.calibration_b = 1.0, 0.0
        self._render_curve(); self.detect_and_match()

    def add_manual_note(self):
        x = float(np.mean(self._plot_x_data())) if self.masses.size else 0
        y = float(np.max(self.display_counts)) if self.display_counts.size else 0
        text = "Manual note"
        item = pg.TextItem(text=text, color="#FFA500", anchor=(0, 1))
        item.setPos(x, y)
        self.plot_widget.addItem(item)
        self.manual_notes.append({"text": text, "x": x, "y": y, "color": "#FFA500"})

    def save_project(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "TOF-LIMS Project (*.toflimsproj *.json)")
        if not path: return
        payload = {
            "source_file": self.source_file,
            "threshold": self.threshold_spin.value(), "prominence": self.prominence_spin.value(), "distance": self.distance_spin.value(),
            "tolerance": self.tolerance_spin.value(), "ion_mode": self.mode_combo.currentText(), "label_mode": self.label_mode_combo.currentText(),
            "calibration": {"a": self.calibration_a, "b": self.calibration_b},
            "baseline": {"mode": self.baseline_mode, "constant": self.manual_baseline},
            "axis": {"xlabel": self.x_label_edit.text(), "ylabel": self.y_label_edit.text(), "xmin": self.xmin_spin.value(), "xmax": self.xmax_spin.value(), "ymin": self.ymin_spin.value(), "ymax": self.ymax_spin.value(), "yscale": self.y_scale_combo.currentText()},
            "title": {"text": self.title_edit.text(), "show": self.title_show_check.isChecked(), "size": self.title_size_spin.value()},
            "style": {"line_width": self.line_width_spin.value(), "line_color": getattr(self, "line_color", "#00C8FF"), "show_symbols": self.symbol_show_check.isChecked(), "symbol_size": self.symbol_size_spin.value(), "label_color": getattr(self, "label_color", "#FFFF00"), "label_font_size": self.label_font_spin.value(), "label_rotation": self.label_rot_spin.value(), "label_bold": self.label_bold_check.isChecked(), "label_italic": self.label_italic_check.isChecked()},
            "peaks": [asdict(p) for p in self.peaks], "manual_notes": self.manual_notes,
codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

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
 main
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "TOF-LIMS Project (*.toflimsproj *.json)")
        if not path: return
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.threshold_spin.setValue(payload.get("threshold", 365.0)); self.prominence_spin.setValue(payload.get("prominence", 50.0)); self.distance_spin.setValue(payload.get("distance", 5))
        self.tolerance_spin.setValue(payload.get("tolerance", 0.2)); self.mode_combo.setCurrentText(payload.get("ion_mode", "positive")); self.label_mode_combo.setCurrentText(payload.get("label_mode", "isotope"))
        c = payload.get("calibration", {}); self.calibration_a = c.get("a", 1.0); self.calibration_b = c.get("b", 0.0)
        b = payload.get("baseline", {}); self.baseline_mode = b.get("mode", "none"); self.manual_baseline = b.get("constant", 0.0)
        a = payload.get("axis", {})
        self.x_label_edit.setText(a.get("xlabel", "Mass (amu)")); self.y_label_edit.setText(a.get("ylabel", "Intensity (Counts)"))
        self.xmin_spin.setValue(a.get("xmin", 0)); self.xmax_spin.setValue(a.get("xmax", 260)); self.ymin_spin.setValue(a.get("ymin", 1)); self.ymax_spin.setValue(a.get("ymax", 1e4)); self.y_scale_combo.setCurrentText(a.get("yscale", "linear"))
        t = payload.get("title", {}); self.title_edit.setText(t.get("text", "TOF-LIMS Spectrum")); self.title_show_check.setChecked(t.get("show", True)); self.title_size_spin.setValue(t.get("size", 16))
        s = payload.get("style", {})
        self.line_width_spin.setValue(s.get("line_width", 2.0)); self.line_color = s.get("line_color", "#00C8FF"); self.symbol_show_check.setChecked(s.get("show_symbols", False)); self.symbol_size_spin.setValue(s.get("symbol_size", 4.0))
        self.label_color = s.get("label_color", "#FFFF00"); self.label_font_spin.setValue(s.get("label_font_size", 11)); self.label_rot_spin.setValue(s.get("label_rotation", 0)); self.label_bold_check.setChecked(s.get("label_bold", False)); self.label_italic_check.setChecked(s.get("label_italic", False))
 codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

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
 main

        src = payload.get("source_file")
        if src and Path(src).exists():
            self.source_file = src
            df = pd.read_csv(src) if src.lower().endswith(".csv") else pd.read_excel(src)
            self.masses = df.iloc[:, 0].to_numpy(dtype=float)
            self.raw_counts = df.iloc[:, 1].to_numpy(dtype=float)
            self.display_counts = self.raw_counts.copy()
            self.apply_baseline()

        self.peaks = [PeakRecord(**x) for x in payload.get("peaks", [])]
        self.matches = {p.index: find_isotope_matches(p.calibrated_mass, self.db, self.tolerance_spin.value(), IonMode(self.mode_combo.currentText())).matches for p in self.peaks}
        self.manual_notes = payload.get("manual_notes", [])
        for note in self.manual_notes:
            item = pg.TextItem(text=note["text"], color=note.get("color", "#FFA500"), anchor=(0, 1)); item.setPos(note["x"], note["y"]); self.plot_widget.addItem(item)
        self._render_curve(); self._refresh_peak_table(); self._redraw_peak_markers(); self._draw_labels()

    def export_plot(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Plot", "", "Image/PDF (*.jpg *.png *.pdf)")
        if not path: return
        exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
        if path.lower().endswith(".pdf"):
            exporter.export(path + ".png")
            QMessageBox.information(self, "Export", "PDF fallback: saved PNG suffix .pdf.png")
        else:
            exporter.export(path)
codex/create-python-app-for-tof-lims-spectrum-analysis-xqqtac

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
main
