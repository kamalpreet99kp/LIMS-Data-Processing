from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
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
        self.labels = []
        self.annotations = []
        self.style = dict(line_color='#1f77b4', line_width=2.0, symbol_show=True, symbol_size=8, bg='#ffffff', label_color='#FFD700', label_font=11, label_rot=0)
        self.setWindowTitle('TOF-LIMS Professional Spectrum Studio')
        self.resize(1600, 960)
        self._build_ui()

    def _build_ui(self):
        self.setStatusBar(QStatusBar())
        m = self.menuBar().addMenu('File')
        for t, fn in [('Load', self.load_file), ('Save Project', self.save_proj), ('Load Project', self.load_proj), ('Export', self.export_plot)]:
            a = QAction(t, self); a.triggered.connect(fn); m.addAction(a)

        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)
        g = QWidget(); gl = QVBoxLayout(g)
        self.title_lbl = QLabel('TOF-LIMS Spectrum'); self.title_lbl.setStyleSheet('font-size:18px;font-weight:600;padding:4px;')
        self.title_lbl.mouseDoubleClickEvent = lambda e: self.edit_title()
        gl.addWidget(self.title_lbl)
        self.plot = pg.PlotWidget(); self.plot.scene().sigMouseMoved.connect(self._hover); self.plot.scene().sigMouseClicked.connect(self._plot_clicked)
        self.plot.setLabel('bottom', 'Mass (amu)'); self.plot.setLabel('left', 'Intensity (Counts)'); self.plot.setXRange(0, 260)
        gl.addWidget(self.plot)
        self.curve = self.plot.plot([], [], pen=pg.mkPen(self.style['line_color'], width=self.style['line_width']))
        self.scatter = pg.ScatterPlotItem(size=self.style['symbol_size'], brush='#D7263D', pen='w'); self.plot.addItem(self.scatter)
        splitter.addWidget(g)

        right = QScrollArea(); right.setWidgetResizable(True); wrapper = QWidget(); right.setWidget(wrapper); rv = QVBoxLayout(wrapper)
        splitter.addWidget(right); splitter.setSizes([900, 700])

        wf = QGroupBox('Workflow (load → calibration/baseline → detect)'); f = QFormLayout(wf)
        self.base_mode = QComboBox(); self.base_mode.addItems(['none', 'subtract_min', 'subtract_constant'])
        self.base_const = QDoubleSpinBox(); self.base_const.setRange(-1e6,1e6)
        self.cal_mode = QComboBox(); self.cal_mode.addItems(['none', 'linear'])
        self.cal_meas = QLineEdit('63,197'); self.cal_ref = QLineEdit('62.9296,196.9666')
        self.cal_out = QLabel('Calibration: a=1.0, b=0.0')
        for n,w in [('Baseline mode',self.base_mode),('Baseline constant',self.base_const),('Calibration mode',self.cal_mode),('Measured masses',self.cal_meas),('Reference masses',self.cal_ref)]: f.addRow(n,w)
        b=QPushButton('Apply Baseline'); b.clicked.connect(self.apply_baseline)
        c=QPushButton('Apply Calibration'); c.clicked.connect(self.calibrate)
        r=QPushButton('Reset Calibration'); r.clicked.connect(self.reset_cal)
        f.addRow(b); f.addRow(c); f.addRow(r); f.addRow(self.cal_out); rv.addWidget(wf)

        det = QGroupBox('Peak Detection & Matching'); df = QFormLayout(det)
        self.threshold=QDoubleSpinBox(); self.threshold.setRange(0,1e9); self.threshold.setValue(365)
        self.prom=QDoubleSpinBox(); self.prom.setRange(0,1e9); self.prom.setValue(50)
        self.dist=QSpinBox(); self.dist.setRange(1,100000); self.dist.setValue(5)
        self.width=QDoubleSpinBox(); self.width.setRange(0,1e6)
        self.tol=QDoubleSpinBox(); self.tol.setRange(0.01,5); self.tol.setValue(0.2); self.tol.setToolTip('Narrow tolerance (e.g. ±0.05) usually requires good calibration')
        self.ion=QComboBox(); self.ion.addItems([IonMode.POSITIVE.value, IonMode.NEGATIVE.value])
        self.lmode=QComboBox(); self.lmode.addItems([m.value for m in LabelMode])
        self.mmode=QComboBox(); self.mmode.addItems([m.value for m in MatchMode])
        for n,w in [('Threshold',self.threshold),('Prominence',self.prom),('Distance',self.dist),('Width',self.width),('Mass tolerance (amu/Da)',self.tol),('Ion mode',self.ion),('Label mode',self.lmode),('Match mode',self.mmode)]: df.addRow(n,w)
        d=QPushButton('Re-detect Peaks'); d.clicked.connect(self.detect); df.addRow(d); rv.addWidget(det)

        self.table=QTableWidget(0,8); self.table.setHorizontalHeaderLabels(['Show','Measured','Calibrated','Counts','Suggested','Final Label','Mass Error','Candidates'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.table.itemChanged.connect(self._table_changed)
        rv.addWidget(self.table)

        ops=QHBoxLayout();
        for t,fn in [('Line Properties',self.edit_line),('Edit X Axis',self.edit_xaxis),('Edit Y Axis',self.edit_yaxis),('Add Annotation',self.add_annotation),('Manual Peak Label',self.add_manual_label),('Export JPG/PNG/PDF',self.export_plot)]:
            b=QPushButton(t); b.clicked.connect(fn); ops.addWidget(b)
        rv.addLayout(ops); rv.addStretch(1)

    def calibrated_mass(self): return apply_calibration(self.mass, self.a, self.b)

    def load_file(self):
        p,_=QFileDialog.getOpenFileName(self,'Load','','Data (*.csv *.xlsx)')
        if not p:return
        d=load_spectrum(p); self.source_file=p; self.mass=d.mass; self.counts_raw=d.counts.copy(); self.counts=d.counts.copy(); self.render(); self.detect()

    def render(self):
        if self.mass.size==0:return
        y=np.clip(self.counts,1e-12,None) if self.plot.plotItem.ctrl.logYCheck.isChecked() else self.counts
        self.curve.setData(self.calibrated_mass(), y)
        self.curve.setPen(pg.mkPen(self.style['line_color'],width=self.style['line_width']))
        self.plot.setBackground(self.style['bg'])
        self.scatter.setData([p.calibrated_mass for p in self.peak_rows], [p.counts for p in self.peak_rows], size=self.style['symbol_size'] if self.style['symbol_show'] else 0)
        self.draw_labels()

    def detect(self):
        if self.counts.size==0:return
        idx=detect_peaks(self.counts, PeakDetectionSettings(self.threshold.value(),self.prom.value(),self.dist.value(), self.width.value() or None))
        ion=IonMode(self.ion.currentText()); lmode=LabelMode(self.lmode.currentText()); mmode=MatchMode(self.mmode.currentText())
        cm=self.calibrated_mass(); self.peak_rows=[]; self.matches={}
        for i in idx:
            cand=find_matches(float(cm[i]), self.db, self.tol.value(), mmode); self.matches[int(i)]=cand
            if cand:
                lab=format_label(cand[0], lmode, float(cm[i]), ion); err=f"{float(cm[i])-cand[0].exact_mass:+.4f}"
            else:
                lab='Unmatched'; err='-'
            self.peak_rows.append(PeakRow(int(i), float(self.mass[i]), float(cm[i]), float(self.counts[i]), True, lab, lab, err, 0))
        self.refresh_table(); self.render()

    def refresh_table(self):
        self.table.blockSignals(True); self.table.setRowCount(len(self.peak_rows))
        for r,p in enumerate(self.peak_rows):
            chk=QTableWidgetItem(); chk.setFlags(chk.flags()|Qt.ItemIsUserCheckable); chk.setCheckState(Qt.Checked if p.show else Qt.Unchecked); self.table.setItem(r,0,chk)
            for j,v in enumerate([f'{p.measured_mass:.4f}',f'{p.calibrated_mass:.4f}',f'{p.counts:.1f}',p.suggested,p.final_label,p.error],1): self.table.setItem(r,j,QTableWidgetItem(v))
            combo=QComboBox();
            cands=self.matches.get(p.index,[])
            if cands:
                for c in cands: combo.addItem(c.isotope)
                combo.setCurrentIndex(min(p.candidate_idx,len(cands)-1))
            else:
                combo.addItem('Unmatched')
            combo.currentIndexChanged.connect(lambda idx,row=r: self._candidate_changed(row,idx))
            self.table.setCellWidget(r,7,combo)
        self.table.blockSignals(False)

    def _candidate_changed(self,row,idx):
        if row>=len(self.peak_rows): return
        p=self.peak_rows[row]; p.candidate_idx=idx
        c=self.matches.get(p.index,[])
        if c:
            sel=c[min(idx,len(c)-1)]
            p.suggested=format_label(sel, LabelMode(self.lmode.currentText()), p.calibrated_mass, IonMode(self.ion.currentText()))
            p.final_label=p.suggested; p.error=f"{p.calibrated_mass-sel.exact_mass:+.4f}"
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
            t=MovableTextItem(text=p.final_label,color=self.style['label_color'],anchor=(0.5,1.2))
            f=t.textItem.font(); f.setPointSize(self.style['label_font']); t.textItem.setFont(f); t.setRotation(self.style['label_rot'])
            t.setPos(p.calibrated_mass,p.counts)
            self.plot.addItem(t); self.labels.append(t)

    def edit_line(self):
        d=QDialog(self); d.setWindowTitle('Line Properties'); f=QFormLayout(d)
        color=QComboBox(); color.addItems(['#1f77b4','#D7263D','#2CA02C','#FF7F0E','#9467BD','#000000']); color.setCurrentText(self.style['line_color'])
        width=QDoubleSpinBox(); width.setRange(0.5,10); width.setValue(self.style['line_width'])
        sym=QCheckBox('Show symbols'); sym.setChecked(self.style['symbol_show'])
        sz=QSpinBox(); sz.setRange(2,20); sz.setValue(self.style['symbol_size'])
        f.addRow('Color',color); f.addRow('Width',width); f.addRow(sym); f.addRow('Symbol size',sz)
        bb=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); f.addRow(bb); bb.accepted.connect(d.accept); bb.rejected.connect(d.reject)
        if d.exec():
            self.style.update(line_color=color.currentText(), line_width=width.value(), symbol_show=sym.isChecked(), symbol_size=sz.value()); self.render()

    def edit_xaxis(self): self._edit_axis('bottom')
    def edit_yaxis(self): self._edit_axis('left')
    def _edit_axis(self,ax):
        d=QDialog(self); d.setWindowTitle(f'Edit {ax} axis'); f=QFormLayout(d)
        label=QLineEdit('Mass (amu)' if ax=='bottom' else 'Intensity (Counts)')
        lo=QDoubleSpinBox(); lo.setRange(-1e9,1e9); hi=QDoubleSpinBox(); hi.setRange(-1e9,1e9)
        vr=self.plot.plotItem.vb.viewRange(); vals=vr[0] if ax=='bottom' else vr[1]; lo.setValue(vals[0]); hi.setValue(vals[1])
        f.addRow('Label',label); f.addRow('Min',lo); f.addRow('Max',hi)
        bb=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); f.addRow(bb); bb.accepted.connect(d.accept); bb.rejected.connect(d.reject)
        if d.exec():
            self.plot.setLabel(ax,label.text())
            (self.plot.setXRange if ax=='bottom' else self.plot.setYRange)(lo.value(),hi.value(),padding=0)

    def edit_title(self):
        t,ok=QInputDialog.getText(self,'Edit Title','Title',text=self.title_lbl.text())
        if ok and t: self.title_lbl.setText(t)

    def apply_baseline(self):
        if self.counts_raw.size==0:return
        mode=self.base_mode.currentText(); self.counts=self.counts_raw.copy()
        if mode=='subtract_min': self.counts-=np.min(self.counts)
        elif mode=='subtract_constant': self.counts-=self.base_const.value()
        self.statusBar().showMessage(f'Data state: baseline={mode}, calibrated={self.a!=1.0 or self.b!=0.0}')
        self.render(); self.detect()

    def calibrate(self):
        if self.cal_mode.currentText()=='none': self.a,self.b=1.0,0.0; self.cal_out.setText('Calibration: none'); self.render(); self.detect(); return
        try:
            m=[float(x.strip()) for x in self.cal_meas.text().split(',') if x.strip()]
            r=[float(x.strip()) for x in self.cal_ref.text().split(',') if x.strip()]
            self.a,self.b=fit_linear_calibration(m,r)
            residuals=[self.a*x+self.b-y for x,y in zip(m,r)]
            self.cal_out.setText(f'Calibration: a={self.a:.8f}, b={self.b:.8f}, residuals={[round(v,5) for v in residuals]}')
            self.render(); self.detect()
        except Exception as e:
            QMessageBox.warning(self,'Calibration',str(e))

    def reset_cal(self):
        self.a,self.b=1.0,0.0; self.cal_out.setText('Calibration: a=1.0, b=0.0'); self.render(); self.detect()

    def add_annotation(self):
        t,ok=QInputDialog.getText(self,'Annotation','Text:')
        if not ok or not t:return
        x=float(np.mean(self.calibrated_mass())) if self.mass.size else 0; y=float(np.max(self.counts)) if self.counts.size else 0
        it=MovableTextItem(text=t,color='#FF7F0E'); it.setPos(x,y); self.plot.addItem(it); self.annotations.append({'text':t,'x':x,'y':y})

    def add_manual_label(self):
        mass,ok=QInputDialog.getDouble(self,'Manual Peak Label','Mass',50,0,1e6,4)
        if not ok:return
        txt,ok=QInputDialog.getText(self,'Manual Peak Label','Text')
        if not ok or not txt:return
        idx=int(np.argmin(np.abs(self.calibrated_mass()-mass))) if self.mass.size else 0
        self.peak_rows.append(PeakRow(idx,float(self.mass[idx]),float(self.calibrated_mass()[idx]),float(self.counts[idx]),True,txt,txt,'-'))
        self.refresh_table(); self.draw_labels()

    def save_proj(self):
        p,_=QFileDialog.getSaveFileName(self,'Save','','Project (*.toflimsproj *.limsproj *.json)')
        if not p:return
        save_project(p,{'source_file':self.source_file,'a':self.a,'b':self.b,'style':self.style,'rows':[asdict(r) for r in self.peak_rows],'annotations':self.annotations,'threshold':self.threshold.value(),'prominence':self.prom.value(),'distance':self.dist.value(),'width':self.width.value(),'tol':self.tol.value(),'ion':self.ion.currentText(),'lmode':self.lmode.currentText(),'mmode':self.mmode.currentText(),'baseline_mode':self.base_mode.currentText(),'baseline_const':self.base_const.value()})

    def load_proj(self):
        p,_=QFileDialog.getOpenFileName(self,'Load','','Project (*.toflimsproj *.limsproj *.json)')
        if not p:return
        d=load_project(p); self.a=d.get('a',1.0); self.b=d.get('b',0.0); self.style.update(d.get('style',{}))
        self.threshold.setValue(d.get('threshold',365)); self.prom.setValue(d.get('prominence',50)); self.dist.setValue(d.get('distance',5)); self.width.setValue(d.get('width',0)); self.tol.setValue(d.get('tol',0.2)); self.ion.setCurrentText(d.get('ion','Positive')); self.lmode.setCurrentText(d.get('lmode','isotope')); self.mmode.setCurrentText(d.get('mmode','exact')); self.base_mode.setCurrentText(d.get('baseline_mode','none')); self.base_const.setValue(d.get('baseline_const',0))
        src=d.get('source_file')
        if src and Path(src).exists():
            sp=load_spectrum(src); self.source_file=src; self.mass=sp.mass; self.counts_raw=sp.counts.copy(); self.counts=sp.counts.copy(); self.apply_baseline()
        self.peak_rows=[PeakRow(**x) for x in d.get('rows',[])]; self.refresh_table(); self.draw_labels(); self.render()
        for a in d.get('annotations',[]): it=MovableTextItem(text=a['text'],color='#FF7F0E'); it.setPos(a['x'],a['y']); self.plot.addItem(it)

    def export_plot(self):
        p,_=QFileDialog.getSaveFileName(self,'Export','','Images (*.jpg *.png *.pdf)')
        if not p:return
        ex=pg.exporters.ImageExporter(self.plot.plotItem)
        ex.export(p+'.png' if p.lower().endswith('.pdf') else p)

    def _hover(self,pos):
        if self.mass.size==0:return
        pt=self.plot.plotItem.vb.mapSceneToView(pos)
        cm=self.calibrated_mass(); idx=int(np.argmin(np.abs(cm-pt.x())))
        self.statusBar().showMessage(f'Mass: {cm[idx]:.4f} | Counts: {self.counts[idx]:.2f}')

    def _plot_clicked(self,ev):
        if ev.double():
            p=ev.scenePos(); v=self.plot.plotItem.vb.mapSceneToView(p)
            # open line properties if near curve
            if self.mass.size and np.min(np.abs(self.calibrated_mass()-v.x()))<1.0:
                self.edit_line()
