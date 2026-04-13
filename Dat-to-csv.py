import os
import csv
import struct
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


class DatBatchCalibrationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DAT Batch Mass Calibration")

        self.dat_files = []
        self.reference_file = None

        self.ref_channels = None
        self.ref_counts = None

        self.selected_channel_16 = None
        self.selected_channel_197 = None
        self.click_mode = None

        self.a = None
        self.b = None
        self.calibration_model = None

        self.build_ui()
        self.build_plot()

    def build_ui(self):
        ctrl = ttk.Frame(self.root, padding=10)
        ctrl.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(ctrl, text="Select DAT/AVG Files", command=self.select_dat_files).grid(row=0, column=0, padx=5, pady=5)

        ttk.Label(ctrl, text="Peak 1 mass:").grid(row=0, column=1, sticky="e")
        self.mass1_var = tk.StringVar(value="16")
        ttk.Entry(ctrl, textvariable=self.mass1_var, width=8).grid(row=0, column=2, padx=5)

        ttk.Label(ctrl, text="Peak 2 mass:").grid(row=0, column=3, sticky="e")
        self.mass2_var = tk.StringVar(value="197")
        ttk.Entry(ctrl, textvariable=self.mass2_var, width=8).grid(row=0, column=4, padx=5)

        ttk.Label(ctrl, text="Snap window:").grid(row=0, column=5, sticky="e")
        self.snap_var = tk.StringVar(value="12")
        ttk.Entry(ctrl, textvariable=self.snap_var, width=8).grid(row=0, column=6, padx=5)

        ttk.Label(ctrl, text="Model:").grid(row=0, column=7, sticky="e")
        self.model_var = tk.StringVar(value="TOF (sqrt(m) vs channel)")
        ttk.Combobox(
            ctrl,
            textvariable=self.model_var,
            values=("TOF (sqrt(m) vs channel)", "Linear (m vs channel)"),
            state="readonly",
            width=24,
        ).grid(row=0, column=8, padx=5)

        ttk.Button(ctrl, text="Mark 16 Peak", command=lambda: self.set_click_mode("16")).grid(row=1, column=0, padx=5, pady=5)
        ttk.Button(ctrl, text="Mark 197 Peak", command=lambda: self.set_click_mode("197")).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(ctrl, text="Compute Calibration", command=self.compute_calibration).grid(row=1, column=2, padx=5, pady=5)
        ttk.Button(ctrl, text="Export All CSVs", command=self.export_all).grid(row=1, column=3, padx=5, pady=5)
        ttk.Button(ctrl, text="Reset Marks", command=self.reset_marks).grid(row=1, column=4, padx=5, pady=5)

        self.status_var = tk.StringVar(value="Select one or more DAT/AVG files.")
        ttk.Label(self.root, textvariable=self.status_var, padding=(10, 0)).pack(anchor="w")

        self.cal_var = tk.StringVar(value="Calibration: not computed")
        ttk.Label(self.root, textvariable=self.cal_var, padding=(10, 0)).pack(anchor="w")

    def build_plot(self):
        self.fig, self.ax = plt.subplots(figsize=(10, 5))
        self.ax.set_title("Reference Spectrum")
        self.ax.set_xlabel("Channel")
        self.ax.set_ylabel("Counts")

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar = NavigationToolbar2Tk(self.canvas, self.root)
        toolbar.update()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.canvas.mpl_connect("button_press_event", self.on_plot_click)

    def select_dat_files(self):
        paths = filedialog.askopenfilenames(
            title="Select DAT/AVG files",
            filetypes=[("DAT/AVG files", "*.dat *.avg"), ("DAT files", "*.dat"), ("AVG files", "*.avg"), ("All files", "*.*")]
        )
        if not paths:
            return

        self.dat_files = list(paths)
        self.reference_file = self.dat_files[0]

        try:
            self.ref_channels, self.ref_counts = self.read_spectrum_dat(self.reference_file)
        except Exception as e:
            messagebox.showerror("Read Error", f"Could not parse DAT file:\n{e}")
            self.dat_files = []
            self.reference_file = None
            self.ref_channels = None
            self.ref_counts = None
            return

        self.reset_marks(redraw=False)
        self.redraw_plot(use_mass_axis=False)

        self.status_var.set(
            f"Loaded {len(self.dat_files)} file(s). Reference: {os.path.basename(self.reference_file)}"
        )

    def read_spectrum_dat(self, path):
        with open(path, "rb") as f:
            raw = f.read()

        # Assumes the spectrum-style DAT layout previously inferred:
        # 30-byte header + 4096 uint16 counts = 8222 bytes
        if len(raw) < 30 + 4096 * 2:
            raise ValueError(f"File too small: {len(raw)} bytes")

        payload = raw[30:30 + 4096 * 2]
        if len(payload) != 4096 * 2:
            raise ValueError("Could not extract 4096-channel spectrum payload")

        counts = np.frombuffer(payload, dtype="<u2").astype(float)
        channels = np.arange(len(counts), dtype=float)

        return channels, counts

    def set_click_mode(self, mode):
        if self.ref_channels is None:
            messagebox.showinfo("No data", "Select DAT files first.")
            return
        self.click_mode = mode
        self.status_var.set(f"Click near the {mode} peak on the plot.")

    def on_plot_click(self, event):
        if self.ref_channels is None or self.click_mode is None:
            return
        if event.inaxes != self.ax or event.xdata is None:
            return

        try:
            window = int(self.snap_var.get())
        except ValueError:
            messagebox.showerror("Input Error", "Snap window must be an integer.")
            return

        channel, count = self.snap_to_peak(event.xdata, window)

        if self.click_mode == "16":
            self.selected_channel_16 = channel
            self.status_var.set(f"16 peak marked at channel {channel:.1f}")
        else:
            self.selected_channel_197 = channel
            self.status_var.set(f"197 peak marked at channel {channel:.1f}")

        self.click_mode = None
        self.redraw_plot(use_mass_axis=False)

    def snap_to_peak(self, clicked_x, window):
        idx = int(np.argmin(np.abs(self.ref_channels - clicked_x)))
        left = max(0, idx - window)
        right = min(len(self.ref_channels), idx + window + 1)

        local_idx = left + int(np.argmax(self.ref_counts[left:right]))
        return self.ref_channels[local_idx], self.ref_counts[local_idx]

    def compute_calibration(self):
        if self.selected_channel_16 is None or self.selected_channel_197 is None:
            messagebox.showwarning("Missing marks", "Mark both peaks first.")
            return

        try:
            m1 = float(self.mass1_var.get())
            m2 = float(self.mass2_var.get())
        except ValueError:
            messagebox.showerror("Input Error", "Peak masses must be numeric.")
            return

        c1 = self.selected_channel_16
        c2 = self.selected_channel_197

        if c1 == c2:
            messagebox.showerror("Calibration Error", "Selected peaks are at the same channel.")
            return

        if m1 <= 0 or m2 <= 0:
            messagebox.showerror(
                "Calibration Error",
                "Masses must be positive values for calibration.",
            )
            return

        selected_model = self.model_var.get()
        if selected_model == "TOF (sqrt(m) vs channel)":
            # Two-point TOF calibration:
            # sqrt(m) = a*channel + b  ->  m = (a*channel + b)^2
            self.a = (np.sqrt(m2) - np.sqrt(m1)) / (c2 - c1)
            self.b = np.sqrt(m1) - self.a * c1
            self.calibration_model = "tof"
            self.cal_var.set(
                f"Calibration (TOF): mass = ({self.a:.10f} * channel + {self.b:.10f})^2"
            )
        else:
            # Legacy linear model:
            # m = a*channel + b
            self.a = (m2 - m1) / (c2 - c1)
            self.b = m1 - self.a * c1
            self.calibration_model = "linear"
            self.cal_var.set(
                f"Calibration (Linear): mass = {self.a:.10f} * channel + {self.b:.10f}"
            )

        self.status_var.set("Calibration computed. You can now export all selected DAT files.")
        self.redraw_plot(use_mass_axis=True)

    def channel_to_mass(self, channels):
        if self.calibration_model == "tof":
            return (self.a * channels + self.b) ** 2
        return self.a * channels + self.b

    def export_all(self):
        if not self.dat_files:
            messagebox.showinfo("No files", "Select DAT files first.")
            return

        if self.a is None or self.b is None:
            messagebox.showwarning("No calibration", "Compute calibration first.")
            return

        out_dir = filedialog.askdirectory(title="Select output folder")
        if not out_dir:
            return

        errors = []
        written = 0

        for path in self.dat_files:
            try:
                channels, counts = self.read_spectrum_dat(path)
                masses = self.channel_to_mass(channels)

                base = os.path.splitext(os.path.basename(path))[0]
                out_csv = os.path.join(out_dir, f"{base}_calibrated.csv")

                with open(out_csv, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["Channel", "Counts", "CalibratedMass"])
                    for ch, ct, ms in zip(channels, counts, masses):
                        w.writerow([int(ch), int(ct), ms])

                written += 1

            except Exception as e:
                errors.append(f"{os.path.basename(path)}: {e}")

        msg = f"Wrote {written} calibrated CSV file(s)."
        if errors:
            msg += "\n\nErrors:\n" + "\n".join(errors[:10])

        messagebox.showinfo("Batch Export Complete", msg)

    def reset_marks(self, redraw=True):
        self.selected_channel_16 = None
        self.selected_channel_197 = None
        self.click_mode = None
        self.a = None
        self.b = None
        self.cal_var.set("Calibration: not computed")
        if redraw:
            self.redraw_plot(use_mass_axis=False)

    def redraw_plot(self, use_mass_axis=False):
        self.ax.clear()

        if self.ref_channels is None:
            self.ax.set_title("Reference Spectrum")
            self.ax.set_xlabel("Channel")
            self.ax.set_ylabel("Counts")
            self.canvas.draw()
            return

        x = self.ref_channels
        xlabel = "Channel"

        if use_mass_axis and self.a is not None and self.b is not None:
            x = self.channel_to_mass(self.ref_channels)
            xlabel = "Mass"

        self.ax.plot(x, self.ref_counts, lw=1)
        self.ax.set_title("Reference Spectrum")
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel("Counts")

        if self.selected_channel_16 is not None:
            x16 = self.selected_channel_16 if not use_mass_axis else self.channel_to_mass(self.selected_channel_16)
            self.ax.axvline(x16, color="green", linestyle="--", label="16 peak")

        if self.selected_channel_197 is not None:
            x197 = self.selected_channel_197 if not use_mass_axis else self.channel_to_mass(self.selected_channel_197)
            self.ax.axvline(x197, color="red", linestyle="--", label="197 peak")

        if self.selected_channel_16 is not None or self.selected_channel_197 is not None:
            self.ax.legend()

        self.fig.tight_layout()
        self.canvas.draw()


def main():
    root = tk.Tk()
    app = DatBatchCalibrationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
