
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import ()

from tof_lims_desktop.core.calibration import apply_calibration, fit_linear_calibration
from tof_lims_desktop.core.data_loader import load_spectrum
from tof_lims_desktop.core.isotope_database import IsotopeDatabase
from tof_lims_desktop.core.mass_matching import IonMode, LabelMode, MatchMode, find_matches, format_label
from tof_lims_desktop.core.peak_detection import PeakDetectionSettings, detect_peaks
from tof_lims_desktop.core.project_io import load_project, save_project


@dataclass
class PeakRow:
    index: int
    measured_mass: float
    calibrated_mass: float
    counts: float
    show: bool = True
    suggested: str = "Unmatched"
    final_label: str = ""
    error: str = "-"


class MovableTextItem(pg.TextItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFlag(self.ItemIsMovable, True)


class MainWindow(QMainWindow):
    def __init__(self, isotope_json: Path):
        super().__init__()
        self.db = IsotopeDatabase(isotope_json)
        self.source_file = None
        self.mass = np.array([])
        self.counts = np.array([])
        self.a, self.b = 1.0, 0.0
        self.peak_rows: list[PeakRow] = []
        self.matches: dict[int, list] = {}
        self.annotations = []
        self.labels = []
        self.setWindowTitle('TOF-LIMS Professional Spectrum Studio')
        self.resize(1650, 980)
        self.setWindowTitle('TOF-LIMS Desktop')
        self.resize(1500, 900)
        self._build_ui()

    def _build_ui(self):
        self.setStatusBar(QStatusBar())
        self._build_menu()
        root = QWidget(); self.setCentralWidget(root); h = QHBoxLayout(root)
        h.setContentsMargins(8, 8, 8, 8); h.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        h.addWidget(splitter)

        graph_container = QWidget(); gl = QVBoxLayout(graph_container)
        self.plot = pg.PlotWidget(); self.plot.scene().sigMouseMoved.connect(self._hover)
        self.plot.setLabel('bottom', 'Mass (amu)'); self.plot.setLabel('left', 'Intensity (Counts)')
        self.plot.setXRange(0, 260)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.title_label = QLabel('TOF-LIMS Spectrum')
        self.title_label.setStyleSheet('font-size:18px;font-weight:600;padding:4px;')
        gl.addWidget(self.title_label)
        gl.addWidget(self.plot)
        self.curve = self.plot.plot([], [], pen=pg.mkPen('#1f77b4', width=2.0))
        self.scatter = pg.ScatterPlotItem(size=8, brush='#D7263D', pen='w')
        self.plot.addItem(self.scatter)
        splitter.addWidget(graph_container)

        controls = QTabWidget()
        controls.setMinimumWidth(580)
        splitter.addWidget(controls)
        splitter.setSizes([950, 700])

        controls.addTab(self._build_project_tab(), 'Project')
        controls.addTab(self._build_detect_tab(), 'Detection/Labels')
        controls.addTab(self._build_style_tab(), 'Style/Axes')
        controls.addTab(self._build_cal_tab(), 'Calibration/Baseline')

    def _build_menu(self):
        file_menu = self.menuBar().addMenu('File')
        for txt, fn in [('Load Spectrum', self.load_file), ('Save Project', self.save_proj), ('Load Project', self.load_proj), ('Export Plot', self.export_plot)]:
            a = QAction(txt, self); a.triggered.connect(fn); file_menu.addAction(a)

    def _build_project_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        for txt, fn in [('Load CSV/XLSX', self.load_file), ('Save Editable Project (.toflimsproj)', self.save_proj), ('Load Editable Project', self.load_proj), ('Export JPG/PNG/PDF', self.export_plot), ('Add Movable Annotation', self.add_annotation), ('Add Manual Peak Label', self.add_manual_label)]:
            b = QPushButton(txt); b.setMinimumHeight(36); b.clicked.connect(fn); v.addWidget(b)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(['Show', 'Measured', 'Calibrated', 'Counts', 'Suggested', 'Final Label', 'Mass Error', 'Candidates'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._table_changed)
        v.addWidget(self.table)
        return w

    def _build_detect_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.threshold = QDoubleSpinBox(); self.threshold.setRange(0, 1e9); self.threshold.setValue(365)
        self.prom = QDoubleSpinBox(); self.prom.setRange(0, 1e9); self.prom.setValue(50)
        self.dist = QSpinBox(); self.dist.setRange(1, 100000); self.dist.setValue(5)
        self.width = QDoubleSpinBox(); self.width.setRange(0, 1e6)
        self.tol = QDoubleSpinBox(); self.tol.setRange(0.01, 5); self.tol.setValue(0.2)
        self.ion = QComboBox(); self.ion.addItems([IonMode.POSITIVE.value, IonMode.NEGATIVE.value])
        self.lmode = QComboBox(); self.lmode.addItems([m.value for m in LabelMode])
        self.mmode = QComboBox(); self.mmode.addItems([m.value for m in MatchMode])
        self.threshold.setToolTip('Threshold = minimum intensity/counts needed for a peak')
        self.prom.setToolTip('Prominence = how much a peak stands above local baseline/noise')
        self.dist.setToolTip('Distance = minimum spacing between peaks, in data points')
        self.tol.setToolTip('Narrow tolerance requires good mass calibration. Increase tolerance or calibrate if labels are missing.')
        f.addRow('Threshold', self.threshold); f.addRow('Prominence', self.prom); f.addRow('Distance (points)', self.dist)
        f.addRow('Peak width', self.width); f.addRow('Mass tolerance (amu / Da)', self.tol)
        f.addRow('Ion mode', self.ion); f.addRow('Label format', self.lmode); f.addRow('Match mode', self.mmode)
        btn = QPushButton('Re-detect Peaks'); btn.clicked.connect(self.detect); btn.setMinimumHeight(38)
        f.addRow(btn)
        return w

    def _build_style_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.line_color = QComboBox(); self.line_color.addItems(['#1f77b4', '#D7263D', '#2CA02C', '#FF7F0E', '#9467BD', '#111111'])
        self.line_width = QDoubleSpinBox(); self.line_width.setRange(0.5, 10); self.line_width.setValue(2.0)
        self.symbols = QCheckBox('Show peak symbols'); self.symbols.setChecked(True)
        self.symbol_size = QSpinBox(); self.symbol_size.setRange(2, 20); self.symbol_size.setValue(8)
        self.grid = QCheckBox('Grid'); self.grid.setChecked(True)
        self.bg_color = QComboBox(); self.bg_color.addItems(['#FFFFFF', '#F7F7F7', '#0E1117'])
        self.title = QLineEdit('TOF-LIMS Spectrum')
        self.title_size = QSpinBox(); self.title_size.setRange(10, 40); self.title_size.setValue(18)
        self.xlabel = QLineEdit('Mass (amu)'); self.ylabel = QLineEdit('Intensity (Counts)')
        self.axis_font = QSpinBox(); self.axis_font.setRange(8, 24); self.axis_font.setValue(12)
        self.label_font = QSpinBox(); self.label_font.setRange(8, 24); self.label_font.setValue(11)
        self.label_color = QComboBox(); self.label_color.addItems(['#FFD700', '#00FFAA', '#FFFFFF', '#FF66C4'])
        self.label_rot = QSpinBox(); self.label_rot.setRange(-180, 180)
        self.ylog = QCheckBox('Log Y')
        self.xmin = QDoubleSpinBox(); self.xmin.setRange(-1e6, 1e6); self.xmin.setValue(0)
        self.xmax = QDoubleSpinBox(); self.xmax.setRange(-1e6, 1e6); self.xmax.setValue(260)
        self.ymin = QDoubleSpinBox(); self.ymin.setRange(-1e6, 1e9); self.ymin.setValue(0)
        self.ymax = QDoubleSpinBox(); self.ymax.setRange(-1e6, 1e9); self.ymax.setValue(1e4)
        for n, wdg in [('Line color', self.line_color), ('Line width', self.line_width), ('', self.symbols), ('Symbol size', self.symbol_size), ('', self.grid), ('Background', self.bg_color), ('Title', self.title), ('Title size', self.title_size), ('X label', self.xlabel), ('Y label', self.ylabel), ('Axis font size', self.axis_font), ('Peak label font size', self.label_font), ('Peak label color', self.label_color), ('Label rotation', self.label_rot), ('', self.ylog), ('X min', self.xmin), ('X max', self.xmax), ('Y min', self.ymin), ('Y max', self.ymax)]:
            f.addRow(n, wdg)
        b = QPushButton('Apply Style / Axis / Scale'); b.clicked.connect(self.apply_style); b.setMinimumHeight(36)
        reset = QPushButton('Auto Scale'); reset.clicked.connect(self.auto_scale)
        f.addRow(b); f.addRow(reset)
        return w

    def _build_cal_tab(self):
        w = QWidget(); f = QFormLayout(w)
        self.base_mode = QComboBox(); self.base_mode.addItems(['none', 'subtract_min', 'subtract_constant'])
        self.base_const = QDoubleSpinBox(); self.base_const.setRange(-1e6, 1e6)
        self.cal_meas = QLineEdit('63,197'); self.cal_ref = QLineEdit('62.9296,196.9666')
        f.addRow('Baseline mode', self.base_mode); f.addRow('Baseline constant', self.base_const)
        f.addRow('Measured masses (comma)', self.cal_meas); f.addRow('Reference masses (comma)', self.cal_ref)
        b1 = QPushButton('Apply Baseline'); b1.clicked.connect(self.apply_baseline)
        b2 = QPushButton('Calibrate Mass (Linear)'); b2.clicked.connect(self.calibrate)
        b3 = QPushButton('Reset Calibration'); b3.clicked.connect(self.reset_cal)
        f.addRow(b1); f.addRow(b2); f.addRow(b3)
        return w

    def calibrated_mass(self):
        return apply_calibration(self.mass, self.a, self.b)

    def load_file(self):
        p, _ = QFileDialog.getOpenFileName(self, 'Load', '', 'Data (*.csv *.xlsx)')
        if not p: return
        d = load_spectrum(p); self.source_file = p; self.mass = d.mass; self.counts = d.counts; self.render(); self.detect()

    def render(self):
        y = np.clip(self.counts, 1e-12, None) if self.ylog.isChecked() else self.counts
        self.curve.setData(self.calibrated_mass(), y)
        self.apply_style()

    def apply_style(self):
        self.curve.setPen(pg.mkPen(self.line_color.currentText(), width=self.line_width.value()))
        self.plot.showGrid(x=self.grid.isChecked(), y=self.grid.isChecked(), alpha=0.25)
        self.plot.setBackground(self.bg_color.currentText())
        self.plot.setLogMode(y=self.ylog.isChecked())
        self.plot.setLabel('bottom', self.xlabel.text(), **{'size': f'{self.axis_font.value()}pt'})
        self.plot.setLabel('left', self.ylabel.text(), **{'size': f'{self.axis_font.value()}pt'})
        self.plot.setXRange(self.xmin.value(), self.xmax.value(), padding=0); self.plot.setYRange(self.ymin.value(), self.ymax.value(), padding=0)
        self.title_label.setText(self.title.text()); self.title_label.setStyleSheet(f'font-size:{self.title_size.value()}px;font-weight:600;padding:4px;')
        if self.symbols.isChecked():
            self.scatter.setData([r.calibrated_mass for r in self.peak_rows], [r.counts for r in self.peak_rows], size=self.symbol_size.value(), brush='#D7263D')
        else:
            self.scatter.setData([], [])
        self.draw_labels()

    def auto_scale(self):
        self.plot.enableAutoRange()

    def detect(self):
        if self.counts.size == 0: return
        idx = detect_peaks(self.counts, PeakDetectionSettings(self.threshold.value(), self.prom.value(), self.dist.value(), self.width.value() or None))
        ion = IonMode(self.ion.currentText()); lmode = LabelMode(self.lmode.currentText()); mmode = MatchMode(self.mmode.currentText())
        cm = self.calibrated_mass(); self.peak_rows = []; self.matches = {}
        for i in idx:
            m = find_matches(float(cm[i]), self.db, self.tol.value(), mmode); self.matches[int(i)] = m
            if m:
                lab = format_label(m[0], lmode, float(cm[i]), ion); err = f"{float(cm[i]) - m[0].exact_mass:+.4f}"
            else:
                lab = 'Unmatched'; err = '-'
            self.peak_rows.append(PeakRow(int(i), float(self.mass[i]), float(cm[i]), float(self.counts[i]), True, lab, lab, err))
        self.refresh_table(); self.apply_style()

    def refresh_table(self):
        self.table.blockSignals(True); self.table.setRowCount(len(self.peak_rows))
        for r, p in enumerate(self.peak_rows):
            c = QTableWidgetItem(); c.setFlags(c.flags() | Qt.ItemIsUserCheckable); c.setCheckState(Qt.Checked if p.show else Qt.Unchecked); self.table.setItem(r, 0, c)
            candidates = '; '.join(x.isotope for x in self.matches.get(p.index, [])) or 'Unmatched'
            vals = [f'{p.measured_mass:.4f}', f'{p.calibrated_mass:.4f}', f'{p.counts:.1f}', p.suggested, p.final_label, p.error, candidates]
            for j, v in enumerate(vals, 1): self.table.setItem(r, j, QTableWidgetItem(v))
        self.table.blockSignals(False)

    def _table_changed(self, item):
        p = self.peak_rows[item.row()]
        if item.column() == 0: p.show = item.checkState() == Qt.Checked
        if item.column() == 5: p.final_label = item.text()
        self.draw_labels()

    def draw_labels(self):
        for it in self.labels: self.plot.removeItem(it)
        self.labels = []
        for p in self.peak_rows:
            if not p.show or not p.final_label: continue
            t = MovableTextItem(text=p.final_label, color=self.label_color.currentText(), anchor=(0.5, 1.2))
            f = t.textItem.font(); f.setPointSize(self.label_font.value()); t.textItem.setFont(f)
            t.setRotation(self.label_rot.value())
            t.setPos(p.calibrated_mass, p.counts)
            self.plot.addItem(t); self.labels.append(t)

    def calibrate(self):
        try:
            m = [float(x.strip()) for x in self.cal_meas.text().split(',') if x.strip()]
            r = [float(x.strip()) for x in self.cal_ref.text().split(',') if x.strip()]
            self.a, self.b = fit_linear_calibration(m, r); self.render(); self.detect()
        except Exception as e:
            QMessageBox.warning(self, 'Calibration', str(e))

    def reset_cal(self):
        self.a, self.b = 1.0, 0.0; self.render(); self.detect()

    def apply_baseline(self):
        if self.counts.size == 0: return
        mode = self.base_mode.currentText()
        if mode == 'subtract_min': self.counts = self.counts - np.min(self.counts)
        elif mode == 'subtract_constant': self.counts = self.counts - self.base_const.value()
        self.render(); self.detect()

    def add_annotation(self):
        t, ok = QInputDialog.getText(self, 'Annotation', 'Text:')
        if not ok or not t: return
        x = float(np.mean(self.calibrated_mass())) if self.mass.size else 0
        y = float(np.max(self.counts)) if self.counts.size else 0
        it = MovableTextItem(text=t, color='#FF7F0E'); it.setPos(x, y); self.plot.addItem(it)
        self.annotations.append({'text': t, 'x': x, 'y': y})

    def add_manual_label(self):
        mass, ok = QInputDialog.getDouble(self, 'Manual Peak Label', 'Mass (amu):', 50.0, 0, 1e6, 4)
        if not ok: return
        text, ok = QInputDialog.getText(self, 'Manual Peak Label', 'Label text:')
        if not ok or not text: return
        idx = int(np.argmin(np.abs(self.calibrated_mass() - mass))) if self.mass.size else 0
        counts = float(self.counts[idx]) if self.counts.size else 0.0
        p = PeakRow(idx, float(self.mass[idx]), float(self.calibrated_mass()[idx]), counts, True, text, text, '-')
        self.peak_rows.append(p); self.refresh_table(); self.draw_labels()

    def save_proj(self):
        p, _ = QFileDialog.getSaveFileName(self, 'Save', '', 'Project (*.toflimsproj *.limsproj *.json)')
        if not p: return
        save_project(p, {
            'source_file': self.source_file, 'a': self.a, 'b': self.b, 'threshold': self.threshold.value(), 'prominence': self.prom.value(), 'distance': self.dist.value(),
            'tolerance': self.tol.value(), 'ion_mode': self.ion.currentText(), 'label_mode': self.lmode.currentText(), 'match_mode': self.mmode.currentText(),
            'style': {'line_color': self.line_color.currentText(), 'line_width': self.line_width.value(), 'title': self.title.text(), 'title_size': self.title_size.value(), 'xlabel': self.xlabel.text(), 'ylabel': self.ylabel.text(), 'xmin': self.xmin.value(), 'xmax': self.xmax.value(), 'ymin': self.ymin.value(), 'ymax': self.ymax.value()},
            'peak_rows': [asdict(x) for x in self.peak_rows], 'annotations': self.annotations,
        })

    def load_proj(self):
        p, _ = QFileDialog.getOpenFileName(self, 'Load', '', 'Project (*.toflimsproj *.limsproj *.json)')
        if not p: return
        d = load_project(p)
        self.a, self.b = d.get('a', 1.0), d.get('b', 0.0)
        self.threshold.setValue(d.get('threshold', 365)); self.prom.setValue(d.get('prominence', 50)); self.dist.setValue(d.get('distance', 5)); self.tol.setValue(d.get('tolerance', 0.2))
        self.ion.setCurrentText(d.get('ion_mode', 'Positive')); self.lmode.setCurrentText(d.get('label_mode', 'isotope')); self.mmode.setCurrentText(d.get('match_mode', 'exact'))
        st = d.get('style', {}); self.line_color.setCurrentText(st.get('line_color', '#1f77b4')); self.line_width.setValue(st.get('line_width', 2.0)); self.title.setText(st.get('title', 'TOF-LIMS Spectrum')); self.title_size.setValue(st.get('title_size', 18)); self.xlabel.setText(st.get('xlabel', 'Mass (amu)')); self.ylabel.setText(st.get('ylabel', 'Intensity (Counts)'))
        self.xmin.setValue(st.get('xmin', 0)); self.xmax.setValue(st.get('xmax', 260)); self.ymin.setValue(st.get('ymin', 0)); self.ymax.setValue(st.get('ymax', 1e4))
        src = d.get('source_file')
        if src and Path(src).exists():
            sp = load_spectrum(src); self.source_file = src; self.mass = sp.mass; self.counts = sp.counts; self.render(); self.detect()
        self.peak_rows = [PeakRow(**x) for x in d.get('peak_rows', [])]; self.refresh_table(); self.draw_labels()
        self.annotations = d.get('annotations', [])
        for a in self.annotations:
            it = MovableTextItem(text=a['text'], color='#FF7F0E'); it.setPos(a['x'], a['y']); self.plot.addItem(it)

    def export_plot(self):
        p, _ = QFileDialog.getSaveFileName(self, 'Export', '', 'Images (*.jpg *.png *.pdf)')
        if not p: return
        ex = pg.exporters.ImageExporter(self.plot.plotItem)
        if p.lower().endswith('.pdf'):
            ex.export(p + '.png')
        else:
            ex.export(p)

    def _hover(self, pos):
        vb = self.plot.plotItem.vb; pt = vb.mapSceneToView(pos)
        self.statusBar().showMessage(f'Mass: {pt.x():.4f} | Counts: {pt.y():.2f}')
        root = QWidget(); self.setCentralWidget(root); h = QHBoxLayout(root)
        self.plot = pg.PlotWidget(); self.plot.scene().sigMouseMoved.connect(self._hover)
        self.plot.setLabel('bottom', 'Mass (amu)'); self.plot.setLabel('left', 'Intensity (Counts)')
        self.plot.setXRange(0, 260)
        self.curve = self.plot.plot([], [], pen=pg.mkPen('#00BFFF', width=2))
        self.scatter = pg.ScatterPlotItem(); self.plot.addItem(self.scatter)
        h.addWidget(self.plot, 3)

        panel = QWidget(); v = QVBoxLayout(panel); h.addWidget(panel, 2)
        file_box = QGroupBox('File/Project'); f = QVBoxLayout(file_box)
        for text, fn in [('Load CSV/XLSX', self.load_file), ('Save Editable Project', self.save_proj), ('Load Project', self.load_proj), ('Export JPG/PNG/PDF', self.export_plot), ('Add Text Annotation', self.add_annotation)]:
            b=QPushButton(text); b.clicked.connect(fn); f.addWidget(b)
        v.addWidget(file_box)

        det = QGroupBox('Peak Detection'); form=QFormLayout(det)
        self.threshold=QDoubleSpinBox(); self.threshold.setRange(0,1e9); self.threshold.setValue(365); self.threshold.setToolTip('Threshold = minimum intensity/counts needed for a peak')
        self.prom=QDoubleSpinBox(); self.prom.setRange(0,1e9); self.prom.setValue(50); self.prom.setToolTip('Prominence = peak height above local baseline/noise')
        self.dist=QSpinBox(); self.dist.setRange(1,100000); self.dist.setValue(5); self.dist.setToolTip('Distance = minimum spacing in data points')
        self.width=QDoubleSpinBox(); self.width.setRange(0,1e6)
        self.tol=QDoubleSpinBox(); self.tol.setRange(0.01,5); self.tol.setValue(0.2); self.tol.setToolTip('Narrow tolerance requires good mass calibration. If labels are missing, increase tolerance or calibrate the mass axis.')
        self.ion=QComboBox(); self.ion.addItems([IonMode.POSITIVE.value, IonMode.NEGATIVE.value])
        self.lmode=QComboBox(); self.lmode.addItems([m.value for m in LabelMode])
        self.mmode=QComboBox(); self.mmode.addItems([m.value for m in MatchMode])
        btn=QPushButton('Re-detect Peaks'); btn.clicked.connect(self.detect)
        for n,w in [('Threshold',self.threshold),('Prominence',self.prom),('Distance',self.dist),('Width',self.width),('Mass tolerance (amu / Da)',self.tol),('Ion mode',self.ion),('Label format',self.lmode),('Match mode',self.mmode)]: form.addRow(n,w)
        form.addRow(btn); v.addWidget(det)

        style=QGroupBox('Graph Style'); sf=QFormLayout(style)
        self.line_w=QDoubleSpinBox(); self.line_w.setRange(0.1,10); self.line_w.setValue(2)
        self.grid=QCheckBox('Grid'); self.grid.setChecked(True)
        self.ylog=QCheckBox('Log Y')
        self.title=QLineEdit('TOF-LIMS Spectrum')
        self.title_size=QSpinBox(); self.title_size.setRange(8,36); self.title_size.setValue(16)
        self.xlabel=QLineEdit('Mass (amu)'); self.ylabel=QLineEdit('Intensity (Counts)')
        self.xmin=QDoubleSpinBox(); self.xmin.setRange(-1e6,1e6); self.xmin.setValue(0)
        self.xmax=QDoubleSpinBox(); self.xmax.setRange(-1e6,1e6); self.xmax.setValue(260)
        self.ymin=QDoubleSpinBox(); self.ymin.setRange(-1e6,1e9); self.ymin.setValue(0)
        self.ymax=QDoubleSpinBox(); self.ymax.setRange(-1e6,1e9); self.ymax.setValue(1e4)
        apply=QPushButton('Apply Style/Axis'); apply.clicked.connect(self.apply_style)
        for n,w in [('Line width',self.line_w),('',self.grid),('',self.ylog),('Title',self.title),('Title size',self.title_size),('X label',self.xlabel),('Y label',self.ylabel),('X min',self.xmin),('X max',self.xmax),('Y min',self.ymin),('Y max',self.ymax)]: sf.addRow(n,w)
        sf.addRow(apply); v.addWidget(style)

        cal=QGroupBox('Calibration/Baseline'); cf=QFormLayout(cal)
        self.base_mode=QComboBox(); self.base_mode.addItems(['none','subtract_min','subtract_constant'])
        self.base_const=QDoubleSpinBox(); self.base_const.setRange(-1e6,1e6)
        self.cal_meas=QLineEdit('63,197'); self.cal_ref=QLineEdit('62.9296,196.9666')
        cbtn=QPushButton('Calibrate Mass'); cbtn.clicked.connect(self.calibrate)
        rbtn=QPushButton('Reset Calibration'); rbtn.clicked.connect(self.reset_cal)
        bbtn=QPushButton('Apply Baseline'); bbtn.clicked.connect(self.apply_baseline)
        cf.addRow('Baseline mode', self.base_mode); cf.addRow('Baseline constant', self.base_const)
        cf.addRow('Measured masses (comma)', self.cal_meas); cf.addRow('Reference masses (comma)', self.cal_ref)
        cf.addRow(cbtn); cf.addRow(rbtn); cf.addRow(bbtn); v.addWidget(cal)

        self.table = QTableWidget(0,8); self.table.setHorizontalHeaderLabels(['Show','Measured','Calibrated','Counts','Suggested','Final Label','Mass Error','Candidates'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemChanged.connect(self._table_changed)
        v.addWidget(self.table)

    def calibrated_mass(self): return apply_calibration(self.mass, self.a, self.b)
    def load_file(self):
        p,_=QFileDialog.getOpenFileName(self,'Load','','Data (*.csv *.xlsx)')
        if not p: return
        d=load_spectrum(p); self.source_file=p; self.mass=d.mass; self.counts=d.counts; self.render(); self.detect()
    def render(self):
        y=np.clip(self.counts,1e-12,None) if self.ylog.isChecked() else self.counts
        self.curve.setData(self.calibrated_mass(), y); self.apply_style()
    def apply_style(self):
        self.curve.setPen(pg.mkPen('#00BFFF', width=self.line_w.value())); self.plot.showGrid(x=self.grid.isChecked(),y=self.grid.isChecked(),alpha=0.2)
        self.plot.setLogMode(y=self.ylog.isChecked()); self.plot.setLabel('bottom',self.xlabel.text()); self.plot.setLabel('left',self.ylabel.text())
        self.plot.setXRange(self.xmin.value(), self.xmax.value(), padding=0); self.plot.setYRange(self.ymin.value(), self.ymax.value(), padding=0)
    def detect(self):
        if self.counts.size==0: return
        idx=detect_peaks(self.counts, PeakDetectionSettings(self.threshold.value(),self.prom.value(),self.dist.value(), self.width.value() or None))
        ion=IonMode(self.ion.currentText()); lmode=LabelMode(self.lmode.currentText()); mmode=MatchMode(self.mmode.currentText())
        cm=self.calibrated_mass(); self.peak_rows=[]; self.matches={}
        for i in idx:
            m=find_matches(float(cm[i]), self.db, self.tol.value(), mmode); self.matches[int(i)] = m
            if m:
                lab=format_label(m[0], lmode, float(cm[i]), ion); err=f"{float(cm[i])-m[0].exact_mass:+.4f}"; cand='; '.join(x.isotope for x in m)
            else:
                lab='Unmatched'; err='-'; cand='Unmatched'
            self.peak_rows.append(PeakRow(int(i), float(self.mass[i]), float(cm[i]), float(self.counts[i]), True, lab, lab, err));
        self.scatter.setData([r.calibrated_mass for r in self.peak_rows], [r.counts for r in self.peak_rows])
        self.refresh_table(); self.draw_labels()
    def refresh_table(self):
        self.table.blockSignals(True); self.table.setRowCount(len(self.peak_rows))
        for r,p in enumerate(self.peak_rows):
            c=QTableWidgetItem(); c.setFlags(c.flags()|Qt.ItemIsUserCheckable); c.setCheckState(Qt.Checked if p.show else Qt.Unchecked); self.table.setItem(r,0,c)
            vals=[f'{p.measured_mass:.4f}',f'{p.calibrated_mass:.4f}',f'{p.counts:.1f}',p.suggested,p.final_label,p.error,'; '.join(x.isotope for x in self.matches.get(p.index,[])) or 'Unmatched']
            for j,v in enumerate(vals,1): self.table.setItem(r,j,QTableWidgetItem(v))
        self.table.blockSignals(False)
    def _table_changed(self,item):
        p=self.peak_rows[item.row()]
        if item.column()==0: p.show=item.checkState()==Qt.Checked
        if item.column()==5: p.final_label=item.text()
        self.draw_labels()
    def draw_labels(self):
        for it in self.labels: self.plot.removeItem(it)
        self.labels=[]
        for p in self.peak_rows:
            if not p.show or not p.final_label: continue
            t=pg.TextItem(text=p.final_label,color='y',anchor=(0.5,1.2)); t.setPos(p.calibrated_mass,p.counts); self.plot.addItem(t); self.labels.append(t)
    def calibrate(self):
        try:
            m=[float(x.strip()) for x in self.cal_meas.text().split(',') if x.strip()]; r=[float(x.strip()) for x in self.cal_ref.text().split(',') if x.strip()]
            self.a,self.b=fit_linear_calibration(m,r); self.render(); self.detect()
        except Exception as e: QMessageBox.warning(self,'Calibration',str(e))
    def reset_cal(self): self.a,self.b=1.0,0.0; self.render(); self.detect()
    def apply_baseline(self):
        if self.counts.size==0:return
        mode=self.base_mode.currentText()
        if mode=='none': pass
        elif mode=='subtract_min': self.counts=self.counts-np.min(self.counts)
        else: self.counts=self.counts-self.base_const.value()
        self.render(); self.detect()
    def add_annotation(self):
        t,ok=QInputDialog.getText(self,'Annotation','Text:')
        if not ok or not t:return
        x=float(np.mean(self.calibrated_mass())) if self.mass.size else 0
        y=float(np.max(self.counts)) if self.counts.size else 0
        it=pg.TextItem(text=t,color='#FFA500'); it.setPos(x,y); self.plot.addItem(it); self.annotations.append({'text':t,'x':x,'y':y})
    def save_proj(self):
        p,_=QFileDialog.getSaveFileName(self,'Save','','Project (*.toflimsproj *.limsproj *.json)')
        if not p:return
        save_project(p,{'source_file':self.source_file,'a':self.a,'b':self.b,'threshold':self.threshold.value(),'prominence':self.prom.value(),'distance':self.dist.value(),'tolerance':self.tol.value(),'ion_mode':self.ion.currentText(),'label_mode':self.lmode.currentText(),'peak_rows':[asdict(x) for x in self.peak_rows],'annotations':self.annotations})
    def load_proj(self):
        p,_=QFileDialog.getOpenFileName(self,'Load','','Project (*.toflimsproj *.limsproj *.json)')
        if not p:return
        d=load_project(p); self.a=d.get('a',1.0); self.b=d.get('b',0.0); self.threshold.setValue(d.get('threshold',365)); self.prom.setValue(d.get('prominence',50)); self.dist.setValue(d.get('distance',5)); self.tol.setValue(d.get('tolerance',0.2)); self.ion.setCurrentText(d.get('ion_mode','Positive')); self.lmode.setCurrentText(d.get('label_mode','isotope'))
        src=d.get('source_file')
        if src and Path(src).exists():
            sp=load_spectrum(src); self.source_file=src; self.mass=sp.mass; self.counts=sp.counts; self.render(); self.detect()
        self.peak_rows=[PeakRow(**x) for x in d.get('peak_rows',[])]; self.refresh_table(); self.draw_labels()
        self.annotations=d.get('annotations',[])
        for a in self.annotations: it=pg.TextItem(text=a['text'],color='#FFA500'); it.setPos(a['x'],a['y']); self.plot.addItem(it)
    def export_plot(self):
        p,_=QFileDialog.getSaveFileName(self,'Export','','Images (*.jpg *.png *.pdf)')
        if not p:return
        ex=pg.exporters.ImageExporter(self.plot.plotItem)
        if p.lower().endswith('.pdf'): ex.export(p+'.png')
        else: ex.export(p)
    def _hover(self, pos):
        vb=self.plot.plotItem.vb; pt=vb.mapSceneToView(pos); self.statusBar().showMessage(f"Mass: {pt.x():.4f}, Counts: {pt.y():.2f}")
