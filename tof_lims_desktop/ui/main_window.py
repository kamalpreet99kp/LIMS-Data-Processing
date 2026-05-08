from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import *

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
    candidate_idx: int = 0


class MovableTextItem(pg.TextItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFlag(self.ItemIsMovable, True)


class MainWindow(QMainWindow):
    def __init__(self, isotope_json: Path):
        super().__init__()
        self.db = IsotopeDatabase(isotope_json)
        self.mass = np.array([])
        self.counts_raw = np.array([])
        self.counts = np.array([])
        self.source_file = None
        self.a, self.b = 1.0, 0.0
        self.peak_rows: list[PeakRow] = []
        self.matches: dict[int, list] = {}
        self.labels, self.annotations = [], []
        self.style = dict(line_color='#2070b8', line_width=2.0, line_style=Qt.SolidLine, symbol_show=True, symbol_size=8, bg='#ffffff', grid=True, title='TOF-LIMS Spectrum', title_font=QFont('Segoe UI', 14, QFont.Bold), label_color='#FFD700', label_font=QFont('Segoe UI', 10), label_rot=0)
        self.cal_points: list[float] = []
        self.setWindowTitle('TOF-LIMS Professional Spectrum Studio v3.0')
        self.resize(1680, 980)
        self._build_ui()

    def _build_ui(self):
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage('Load data → calibrate/baseline → detect/label')
        m = self.menuBar().addMenu('File')
        for t, fn in [('Load Spectrum', self.load_file), ('Save Project', self.save_proj), ('Load Project', self.load_proj), ('Export Image', self.export_plot)]:
            a = QAction(t, self); a.triggered.connect(fn); m.addAction(a)

        root_split = QSplitter(Qt.Horizontal); self.setCentralWidget(root_split)

        graph_w = QWidget(); gl = QVBoxLayout(graph_w)
        self.title_lbl = QLabel(self.style['title']); self.title_lbl.setAlignment(Qt.AlignCenter); self.title_lbl.setFont(self.style['title_font'])
        self.title_lbl.mouseDoubleClickEvent = lambda _: self.edit_title_dialog()
        gl.addWidget(self.title_lbl)
        self.plot = pg.PlotWidget(); self.plot.scene().sigMouseMoved.connect(self._hover); self.plot.scene().sigMouseClicked.connect(self._plot_clicked)
        self.plot.setLabel('bottom', 'Mass (amu)'); self.plot.setLabel('left', 'Intensity (Counts)'); self.plot.setXRange(0, 260)
        gl.addWidget(self.plot)
        self.curve = self.plot.plot([], [], pen=pg.mkPen(self.style['line_color'], width=self.style['line_width']))
        self.scatter = pg.ScatterPlotItem(size=self.style['symbol_size'], brush='#D7263D', pen='w'); self.plot.addItem(self.scatter)
        root_split.addWidget(graph_w)

        right = QScrollArea(); right.setWidgetResizable(True); wrap = QWidget(); rv = QVBoxLayout(wrap); right.setWidget(wrap)
        root_split.addWidget(right); root_split.setSizes([980, 700])

        # STEP 1 Calibration/Baseline first
        step1 = QGroupBox('Step 1: Calibration / Baseline')
        f1 = QFormLayout(step1)
        self.base_mode = QComboBox(); self.base_mode.addItems(['none', 'subtract_min', 'subtract_constant'])
        self.base_const = QDoubleSpinBox(); self.base_const.setRange(-1e6, 1e6)
        self.cal_mode = QComboBox(); self.cal_mode.addItems(['none', 'linear'])
        self.cal_meas = QLineEdit('63,197'); self.cal_ref = QLineEdit('62.9296,196.9666')
        self.cal_out = QLabel('Calibration: not applied')
        for n,w in [('Baseline mode',self.base_mode),('Baseline constant',self.base_const),('Calibration mode',self.cal_mode),('Measured masses',self.cal_meas),('Reference masses',self.cal_ref)]: f1.addRow(n,w)
        p1=QPushButton('Apply Baseline'); p1.clicked.connect(self.apply_baseline)
        p2=QPushButton('Apply Calibration'); p2.clicked.connect(self.calibrate)
        p3=QPushButton('Reset Calibration'); p3.clicked.connect(self.reset_cal)
        p4=QPushButton('Pick Cal Point From Plot'); p4.clicked.connect(lambda: self.statusBar().showMessage('Double-click plot to add calibration measured mass point'))
        f1.addRow(p1); f1.addRow(p2); f1.addRow(p3); f1.addRow(p4); f1.addRow(self.cal_out)
        rv.addWidget(step1)

        # Step 2 detection
        step2 = QGroupBox('Step 2: Detection / Labels')
        f2 = QFormLayout(step2)
        self.threshold = QDoubleSpinBox(); self.threshold.setRange(0,1e9); self.threshold.setValue(365); self.threshold.setToolTip('Minimum counts needed to register a peak')
        self.prom = QDoubleSpinBox(); self.prom.setRange(0,1e9); self.prom.setValue(50); self.prom.setToolTip('Peak prominence above surrounding baseline')
        self.dist = QSpinBox(); self.dist.setRange(1,100000); self.dist.setValue(5); self.dist.setToolTip('Minimum spacing between peaks in data points')
        self.width = QDoubleSpinBox(); self.width.setRange(0,1e6)
        self.tol = QDoubleSpinBox(); self.tol.setRange(0.01,2); self.tol.setValue(0.3); self.tol.setToolTip('Narrow tolerances require good calibration')
        self.ion = QComboBox(); self.ion.addItems([IonMode.POSITIVE.value, IonMode.NEGATIVE.value])
        self.lmode = QComboBox(); self.lmode.addItems([m.value for m in LabelMode if m != LabelMode.ION] + ['ion'])
        self.mmode = QComboBox(); self.mmode.addItems([m.value for m in MatchMode])
        for n,w in [('Threshold',self.threshold),('Prominence',self.prom),('Distance',self.dist),('Peak width',self.width),('Mass tolerance (amu/Da)',self.tol),('Ion mode',self.ion),('Label mode',self.lmode),('Match mode',self.mmode)]: f2.addRow(n,w)
        pb=QPushButton('Detect / Re-detect Peaks'); pb.clicked.connect(self.detect); f2.addRow(pb)
        rv.addWidget(step2)

        # Step 3 style
        step3=QGroupBox('Step 3: Style / Axis (double click graph for quick edit)')
        h3=QHBoxLayout(step3)
        for t,fn in [('Line',self.edit_line_dialog),('X Axis',self.edit_xaxis),('Y Axis',self.edit_yaxis),('Title',self.edit_title_dialog),('Labels',self.edit_label_style),('Background/Grid',self.edit_background)]:
            b=QPushButton(t); b.clicked.connect(fn); h3.addWidget(b)
        rv.addWidget(step3)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(['Show','Measured','Calibrated','Counts','Suggested','Final Label','Mass Error','Candidates'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.table.itemChanged.connect(self._table_changed)
        rv.addWidget(self.table)

        actions=QHBoxLayout()
        for t,fn in [('Add Annotation',self.add_annotation),('Manual Peak Label',self.add_manual_label),('Save Project',self.save_proj),('Load Project',self.load_proj),('Export JPG/PNG/PDF',self.export_plot)]:
            b=QPushButton(t); b.clicked.connect(fn); actions.addWidget(b)
        rv.addLayout(actions); rv.addStretch(1)

    def calibrated_mass(self): return apply_calibration(self.mass, self.a, self.b)

    def load_file(self):
        p,_=QFileDialog.getOpenFileName(self,'Load','','Data (*.csv *.xlsx)')
        if not p:return
        try:
            d=load_spectrum(p); self.source_file=p; self.mass=d.mass; self.counts_raw=d.counts.copy(); self.counts=d.counts.copy(); self.cal_points=[]; self.statusBar().showMessage('File loaded. Step 1: baseline/calibration')
            self.render(); self.detect()
        except Exception as e:
            QMessageBox.critical(self,'Load Error',str(e))

    def render(self):
        if self.mass.size==0:return
        y=np.clip(self.counts,1e-12,None) if self.plot.plotItem.ctrl.logYCheck.isChecked() else self.counts
        pen=pg.mkPen(self.style['line_color'], width=self.style['line_width']); pen.setStyle(self.style['line_style'])
        self.curve.setPen(pen); self.curve.setData(self.calibrated_mass(), y)
        self.plot.setBackground(self.style['bg']); self.plot.showGrid(x=self.style['grid'], y=self.style['grid'], alpha=0.25)
        self.scatter.setData([p.calibrated_mass for p in self.peak_rows], [p.counts for p in self.peak_rows], size=self.style['symbol_size'] if self.style['symbol_show'] else 0)
        self.draw_labels()

    def detect(self):
        if self.counts.size==0:return
        idx=detect_peaks(self.counts, PeakDetectionSettings(self.threshold.value(),self.prom.value(),self.dist.value(), self.width.value() or None))
        ion=IonMode(self.ion.currentText()); mmode=MatchMode(self.mmode.currentText()); cm=self.calibrated_mass(); self.peak_rows=[]; self.matches={}
        for i in idx:
            cand=find_matches(float(cm[i]), self.db, self.tol.value(), mmode); self.matches[int(i)]=cand
            if cand:
                mode = LabelMode.ION if self.lmode.currentText() == 'ion' else LabelMode(self.lmode.currentText())
                lab=format_label(cand[0], mode, float(cm[i]), ion); err=f"{float(cm[i])-cand[0].exact_mass:+.4f}"
            else: lab,err='Unmatched','-'
            self.peak_rows.append(PeakRow(int(i), float(self.mass[i]), float(cm[i]), float(self.counts[i]), True, lab, lab, err, 0))
        self.refresh_table(); self.render()

    def refresh_table(self):
        self.table.blockSignals(True); self.table.setRowCount(len(self.peak_rows))
        for r,p in enumerate(self.peak_rows):
            chk=QTableWidgetItem(); chk.setFlags(chk.flags()|Qt.ItemIsUserCheckable); chk.setCheckState(Qt.Checked if p.show else Qt.Unchecked); self.table.setItem(r,0,chk)
            for j,v in enumerate([f'{p.measured_mass:.4f}',f'{p.calibrated_mass:.4f}',f'{p.counts:.1f}',p.suggested,p.final_label,p.error],1): self.table.setItem(r,j,QTableWidgetItem(v))
            combo=QComboBox(); cands=self.matches.get(p.index,[])
            if cands:
                for c in cands: combo.addItem(c.isotope)
                combo.setCurrentIndex(min(p.candidate_idx, len(cands)-1))
            else: combo.addItem('Unmatched')
            combo.currentIndexChanged.connect(lambda idx,row=r: self._candidate_changed(row,idx))
            self.table.setCellWidget(r,7,combo)
        self.table.blockSignals(False)

    def _candidate_changed(self,row,idx):
        if row>=len(self.peak_rows):return
        p=self.peak_rows[row]; p.candidate_idx=idx; c=self.matches.get(p.index,[])
        if c:
            sel=c[min(idx,len(c)-1)]
            mode = LabelMode.ION if self.lmode.currentText() == 'ion' else LabelMode(self.lmode.currentText())
            p.suggested=format_label(sel, mode, p.calibrated_mass, IonMode(self.ion.currentText())); p.final_label=p.suggested; p.error=f"{p.calibrated_mass-sel.exact_mass:+.4f}"
        self.refresh_table(); self.draw_labels()

    def _table_changed(self,item):
        if item.row()>=len(self.peak_rows):return
        p=self.peak_rows[item.row()]
        if item.column()==0: p.show=item.checkState()==Qt.Checked
        if item.column()==5: p.final_label=item.text()
        self.draw_labels()

    def draw_labels(self):
        for t in self.labels: self.plot.removeItem(t)
        self.labels=[]
        for p in self.peak_rows:
            if not p.show or not p.final_label: continue
            t=MovableTextItem(text=p.final_label,color=self.style['label_color'],anchor=(0.5,1.35)); t.setPos(p.calibrated_mass,p.counts)
            t.textItem.setFont(self.style['label_font']); t.setRotation(self.style['label_rot'])
            self.plot.addItem(t); self.labels.append(t)

    def edit_line_dialog(self):
        d=QDialog(self); d.setWindowTitle('Line Properties'); f=QFormLayout(d)
        w=QDoubleSpinBox(); w.setRange(0.5,10); w.setValue(self.style['line_width'])
        sym=QCheckBox('Show symbols'); sym.setChecked(self.style['symbol_show'])
        ss=QSpinBox(); ss.setRange(2,20); ss.setValue(self.style['symbol_size'])
        ls=QComboBox(); ls.addItems(['Solid','Dash','Dot'])
        cb=QPushButton('Choose line color'); cb.clicked.connect(lambda: self._pick_color('line_color'))
        f.addRow('Line width',w); f.addRow('Line style',ls); f.addRow(sym); f.addRow('Symbol size',ss); f.addRow(cb)
        bb=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); bb.accepted.connect(d.accept); bb.rejected.connect(d.reject); f.addRow(bb)
        if d.exec():
            self.style['line_width']=w.value(); self.style['symbol_show']=sym.isChecked(); self.style['symbol_size']=ss.value(); self.style['line_style']={0:Qt.SolidLine,1:Qt.DashLine,2:Qt.DotLine}[ls.currentIndex()]; self.render()

    def edit_title_dialog(self):
        t,ok=QInputDialog.getText(self,'Title','Text:',text=self.title_lbl.text())
        if ok and t:self.title_lbl.setText(t)

    def edit_xaxis(self): self._edit_axis('bottom')
    def edit_yaxis(self): self._edit_axis('left')
    def _edit_axis(self,axis):
        d=QDialog(self); d.setWindowTitle(f'{axis} axis'); f=QFormLayout(d)
        l=QLineEdit('Mass (amu)' if axis=='bottom' else 'Intensity (Counts)')
        lo=QDoubleSpinBox(); lo.setRange(-1e9,1e9); hi=QDoubleSpinBox(); hi.setRange(-1e9,1e9)
        vr=self.plot.plotItem.vb.viewRange(); vals=vr[0] if axis=='bottom' else vr[1]; lo.setValue(vals[0]); hi.setValue(vals[1])
        f.addRow('Label',l); f.addRow('Min',lo); f.addRow('Max',hi)
        bb=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); bb.accepted.connect(d.accept); bb.rejected.connect(d.reject); f.addRow(bb)
        if d.exec():
            self.plot.setLabel(axis,l.text()); (self.plot.setXRange if axis=='bottom' else self.plot.setYRange)(lo.value(),hi.value(),padding=0)

    def edit_label_style(self):
        d=QDialog(self); d.setWindowTitle('Label Style'); f=QFormLayout(d)
        fs=QSpinBox(); fs.setRange(8,26); fs.setValue(self.style['label_font'].pointSize())
        rot=QSpinBox(); rot.setRange(-180,180); rot.setValue(self.style['label_rot'])
        bold=QCheckBox('Bold'); bold.setChecked(self.style['label_font'].bold())
        color=QPushButton('Choose label color'); color.clicked.connect(lambda: self._pick_color('label_color'))
        f.addRow('Font size',fs); f.addRow('Rotation',rot); f.addRow(bold); f.addRow(color)
        bb=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); bb.accepted.connect(d.accept); bb.rejected.connect(d.reject); f.addRow(bb)
        if d.exec():
            font=QFont(self.style['label_font']); font.setPointSize(fs.value()); font.setBold(bold.isChecked())
            self.style['label_font']=font; self.style['label_rot']=rot.value(); self.draw_labels()

    def edit_background(self):
        self._pick_color('bg'); self.style['grid']=QMessageBox.question(self,'Grid','Show grid?',QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes; self.render()

    def _pick_color(self,key):
        c=QColorDialog.getColor(QColor(self.style[key]), self)
        if c.isValid(): self.style[key]=c.name()

    def apply_baseline(self):
        if self.counts_raw.size==0:return
        self.counts=self.counts_raw.copy(); mode=self.base_mode.currentText()
        if mode=='subtract_min': self.counts-=np.min(self.counts)
        elif mode=='subtract_constant': self.counts-=self.base_const.value()
        self.statusBar().showMessage(f'Data state: baseline={mode}, calibrated={self.a!=1.0 or self.b!=0.0}')
        self.render(); self.detect()

    def calibrate(self):
        if self.cal_mode.currentText()=='none': self.a,self.b=1.0,0.0; self.cal_out.setText('Calibration: none'); self.render(); self.detect(); return
        try:
            m=[float(x.strip()) for x in self.cal_meas.text().split(',') if x.strip()]; r=[float(x.strip()) for x in self.cal_ref.text().split(',') if x.strip()]
            self.a,self.b=fit_linear_calibration(m,r); res=[round(self.a*x+self.b-y,5) for x,y in zip(m,r)]
            self.cal_out.setText(f'Calibration: a={self.a:.8f}, b={self.b:.8f}, residuals={res}')
            self.render(); self.detect()
        except Exception as e: QMessageBox.warning(self,'Calibration',str(e))

    def reset_cal(self): self.a,self.b=1.0,0.0; self.cal_out.setText('Calibration: a=1.0, b=0.0'); self.render(); self.detect()

    def add_annotation(self):
        t,ok=QInputDialog.getText(self,'Annotation','Text');
        if not ok or not t:return
        x=float(np.mean(self.calibrated_mass())) if self.mass.size else 0; y=float(np.max(self.counts)) if self.counts.size else 0
        it=MovableTextItem(text=t,color='#ff7f0e'); it.setPos(x,y); it.textItem.setFont(self.style['label_font']); self.plot.addItem(it)

    def add_manual_label(self):
        m,ok=QInputDialog.getDouble(self,'Manual Label','Mass',50,0,1e6,4)
        if not ok:return
        txt,ok=QInputDialog.getText(self,'Manual Label','Text')
        if not ok or not txt:return
        idx=int(np.argmin(np.abs(self.calibrated_mass()-m))) if self.mass.size else 0
        # place at top of nearest detected peak if present
        peak=max(self.peak_rows, key=lambda p: p.counts) if self.peak_rows else None
        counts=peak.counts if peak and abs(peak.calibrated_mass-self.calibrated_mass()[idx])<0.3 else float(self.counts[idx])
        self.peak_rows.append(PeakRow(idx,float(self.mass[idx]),float(self.calibrated_mass()[idx]),counts,True,txt,txt,'-'))
        self.refresh_table(); self.draw_labels()

    def save_proj(self):
        p,_=QFileDialog.getSaveFileName(self,'Save Project','','TOF-LIMS Project (*.toflimsproj *.limsproj)')
        if not p:return
        payload={'source_file':self.source_file,'a':self.a,'b':self.b,'style':self.style,'rows':[asdict(x) for x in self.peak_rows],'threshold':self.threshold.value(),'prominence':self.prom.value(),'distance':self.dist.value(),'width':self.width.value(),'tol':self.tol.value(),'ion':self.ion.currentText(),'lmode':self.lmode.currentText(),'mmode':self.mmode.currentText(),'baseline_mode':self.base_mode.currentText(),'baseline_const':self.base_const.value()}
        save_project(p,payload)
        self.statusBar().showMessage(f'Project saved: {p}')

    def load_proj(self):
        p,_=QFileDialog.getOpenFileName(self,'Load Project','','TOF-LIMS Project (*.toflimsproj *.limsproj *.json)')
        if not p:return
        d=load_project(p); self.a=d.get('a',1.0); self.b=d.get('b',0.0); self.style.update(d.get('style',{})); self.threshold.setValue(d.get('threshold',365)); self.prom.setValue(d.get('prominence',50)); self.dist.setValue(d.get('distance',5)); self.width.setValue(d.get('width',0)); self.tol.setValue(d.get('tol',0.3)); self.ion.setCurrentText(d.get('ion','Positive')); self.lmode.setCurrentText(d.get('lmode','isotope')); self.mmode.setCurrentText(d.get('mmode','exact')); self.base_mode.setCurrentText(d.get('baseline_mode','none')); self.base_const.setValue(d.get('baseline_const',0))
        src=d.get('source_file')
        if src and Path(src).exists():
            sp=load_spectrum(src); self.source_file=src; self.mass=sp.mass; self.counts_raw=sp.counts.copy(); self.counts=sp.counts.copy(); self.apply_baseline()
        self.peak_rows=[PeakRow(**x) for x in d.get('rows',[])]; self.refresh_table(); self.render()

    def export_plot(self):
        p,_=QFileDialog.getSaveFileName(self,'Export','','Images (*.jpg *.png *.pdf)')
        if not p:return
        ex=pg.exporters.ImageExporter(self.plot.plotItem); ex.export(p+'.png' if p.lower().endswith('.pdf') else p)

    def _hover(self,pos):
        if self.mass.size==0:return
        pt=self.plot.plotItem.vb.mapSceneToView(pos); cm=self.calibrated_mass(); idx=int(np.argmin(np.abs(cm-pt.x())))
        self.statusBar().showMessage(f'Mass: {cm[idx]:.4f} | Counts(raw): {self.counts_raw[idx]:.2f} | Counts(display): {self.counts[idx]:.2f}')

    def _plot_clicked(self,ev):
        if self.mass.size==0:return
        pt=self.plot.plotItem.vb.mapSceneToView(ev.scenePos())
        if ev.double():
            self.cal_points.append(float(pt.x()))
            if len(self.cal_points)<=3:
                self.cal_meas.setText(','.join(f'{x:.4f}' for x in self.cal_points))
            if np.min(np.abs(self.calibrated_mass()-pt.x()))<0.8:
                self.edit_line_dialog()
