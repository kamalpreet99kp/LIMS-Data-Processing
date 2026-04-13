#!/usr/bin/env python3
"""
TOF-LIMS CSV peak detection and labeling pipeline.

Scope for this stage:
CSV input -> peak detection -> plotting -> peak labeling -> peak table output
"""

from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks


# ==============================
# Config (easy to edit)
# ==============================
PEAK_MIN_HEIGHT: Optional[float] = None
PEAK_MIN_PROMINENCE: float = 100.0
PEAK_MIN_DISTANCE: int = 5
MASS_MATCH_TOLERANCE: float = 0.3
MASS_LABEL_DECIMALS: int = 2
LABEL_MODE_DEFAULT: str = "element"  # one of: "mass", "element"
MAX_LABELS_ON_PLOT: int = 80
LABEL_Y_OFFSET_RATIO: float = 0.03

# User-editable elemental / isotope mass reference table.
# You can expand this later with more entries.
REFERENCE_MASSES: List[Dict[str, object]] = [
    {"mass": 12.0, "label": "C", "polarity": "any", "tolerance": 0.3},
    {"mass": 23.0, "label": "Na", "polarity": "any", "tolerance": 0.3},
    {"mass": 24.0, "label": "Mg", "polarity": "any", "tolerance": 0.3},
    {"mass": 56.0, "label": "Fe", "polarity": "any", "tolerance": 0.3},
    {"mass": 63.0, "label": "Cu-63", "polarity": "any", "tolerance": 0.3},
    {"mass": 65.0, "label": "Cu-65", "polarity": "any", "tolerance": 0.3},
    {"mass": 197.0, "label": "Au", "polarity": "any", "tolerance": 0.3},
]


@dataclass
class PeakRecord:
    peak_index: int
    mass: float
    intensity: float
    assigned_label: str
    assignment_type: str  # mass-only / matched-element / unmatched
    matched_reference_mass: Optional[float]
    mass_error: Optional[float]


def _normalize_name(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def load_csv(csv_path: str) -> Tuple[List[str], List[List[str]]]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        raise ValueError("CSV is empty.")

    header = rows[0]
    data_rows = [row for row in rows[1:] if any(cell.strip() for cell in row)]
    if not data_rows:
        raise ValueError("CSV has header but no data rows.")

    return header, data_rows


def detect_columns(header: Sequence[str], data_rows: Sequence[Sequence[str]]) -> Tuple[int, int]:
    normalized = [_normalize_name(h) for h in header]

    mass_keywords = {
        "mass", "mz", "moverz", "massnumber", "nominalmass", "calibratedmass", "x", "amu"
    }
    intensity_keywords = {
        "counts", "count", "intensity", "signal", "y", "abundance", "height"
    }

    mass_idx = None
    intensity_idx = None

    for i, name in enumerate(normalized):
        if mass_idx is None and any(k in name for k in mass_keywords):
            mass_idx = i
        if intensity_idx is None and any(k in name for k in intensity_keywords):
            intensity_idx = i

    if mass_idx is not None and intensity_idx is not None and mass_idx != intensity_idx:
        return mass_idx, intensity_idx

    # Fallback: select first two numeric-rich columns.
    n_cols = len(header)
    numeric_scores = []
    for i in range(n_cols):
        ok = 0
        total = 0
        for row in data_rows[: min(300, len(data_rows))]:
            if i >= len(row):
                continue
            total += 1
            try:
                float(row[i].strip())
                ok += 1
            except Exception:
                pass
        ratio = ok / total if total else 0
        numeric_scores.append((ratio, i))

    numeric_scores.sort(reverse=True)
    if len(numeric_scores) < 2 or numeric_scores[1][0] < 0.5:
        raise ValueError(
            "Could not detect mass/intensity columns. "
            "Please ensure CSV has numeric mass and counts columns."
        )

    i1 = numeric_scores[0][1]
    i2 = numeric_scores[1][1]

    # Guess mass column by monotonic trend where possible.
    def monotonic_score(col_idx: int) -> float:
        vals = []
        for row in data_rows[: min(1000, len(data_rows))]:
            if col_idx < len(row):
                try:
                    vals.append(float(row[col_idx]))
                except Exception:
                    pass
        if len(vals) < 3:
            return 0.0
        diffs = np.diff(vals)
        return float(np.mean(diffs > 0))

    if monotonic_score(i1) >= monotonic_score(i2):
        return i1, i2
    return i2, i1


def _parse_numeric_columns(
    data_rows: Sequence[Sequence[str]], mass_idx: int, intensity_idx: int
) -> Tuple[np.ndarray, np.ndarray]:
    masses = []
    intensities = []

    for row in data_rows:
        if mass_idx >= len(row) or intensity_idx >= len(row):
            continue
        try:
            m = float(row[mass_idx].strip())
            y = float(row[intensity_idx].strip())
        except Exception:
            continue
        masses.append(m)
        intensities.append(y)

    if len(masses) < 10:
        raise ValueError("Not enough numeric data rows after parsing columns.")

    x = np.asarray(masses, dtype=float)
    y = np.asarray(intensities, dtype=float)

    # Ensure sorted by mass for plotting + peak finding.
    order = np.argsort(x)
    return x[order], y[order]


def find_spectrum_peaks(
    masses: np.ndarray,
    intensities: np.ndarray,
    *,
    min_height: Optional[float],
    min_prominence: float,
    min_distance: int,
):
    if len(masses) != len(intensities):
        raise ValueError("Mass and intensity arrays must have the same length.")

    distance = max(1, int(min_distance))

    peak_indices, properties = find_peaks(
        intensities,
        height=min_height,
        prominence=min_prominence,
        distance=distance,
    )

    return peak_indices, properties


def _best_reference_match(
    mass_value: float,
    references: Sequence[Dict[str, object]],
    default_tolerance: float,
) -> Tuple[Optional[Dict[str, object]], Optional[float]]:
    best = None
    best_abs_err = None

    for ref in references:
        ref_mass = float(ref["mass"])
        tol = float(ref.get("tolerance", default_tolerance))
        err = mass_value - ref_mass
        if abs(err) <= tol:
            if best is None or abs(err) < best_abs_err:
                best = ref
                best_abs_err = abs(err)

    if best is None:
        return None, None
    return best, mass_value - float(best["mass"])


def assign_peak_labels(
    masses: np.ndarray,
    intensities: np.ndarray,
    peak_indices: Sequence[int],
    *,
    label_mode: str,
    references: Sequence[Dict[str, object]],
    default_tolerance: float,
    mass_label_decimals: int,
) -> List[PeakRecord]:
    mode = label_mode.lower().strip()
    if mode not in {"mass", "element"}:
        raise ValueError("label_mode must be 'mass' or 'element'.")

    records: List[PeakRecord] = []
    for idx in peak_indices:
        m = float(masses[idx])
        y = float(intensities[idx])
        mass_label = f"{m:.{mass_label_decimals}f}"

        if mode == "mass":
            records.append(
                PeakRecord(
                    peak_index=int(idx),
                    mass=m,
                    intensity=y,
                    assigned_label=mass_label,
                    assignment_type="mass-only",
                    matched_reference_mass=None,
                    mass_error=None,
                )
            )
            continue

        # element mode: try reference matching first
        ref, err = _best_reference_match(m, references, default_tolerance)
        if ref is not None:
            records.append(
                PeakRecord(
                    peak_index=int(idx),
                    mass=m,
                    intensity=y,
                    assigned_label=str(ref["label"]),
                    assignment_type="matched-element",
                    matched_reference_mass=float(ref["mass"]),
                    mass_error=float(err),
                )
            )
        else:
            records.append(
                PeakRecord(
                    peak_index=int(idx),
                    mass=m,
                    intensity=y,
                    assigned_label=mass_label,
                    assignment_type="unmatched",
                    matched_reference_mass=None,
                    mass_error=None,
                )
            )

    return records


def plot_spectrum_with_labels(
    masses: np.ndarray,
    intensities: np.ndarray,
    peak_records: Sequence[PeakRecord],
    out_png: str,
    *,
    max_labels: int,
    y_offset_ratio: float,
):
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(masses, intensities, lw=1.0, color="navy", label="Spectrum")

    if peak_records:
        p_idx = np.array([r.peak_index for r in peak_records], dtype=int)
        ax.scatter(masses[p_idx], intensities[p_idx], color="crimson", s=20, zorder=3, label="Detected peaks")

    y_max = float(np.max(intensities)) if len(intensities) else 1.0
    y_base_offset = max(1.0, y_max * y_offset_ratio)

    # Label strongest peaks first, and cap labels to reduce clutter.
    sorted_records = sorted(peak_records, key=lambda r: r.intensity, reverse=True)
    label_records = sorted_records[: max_labels]

    # Stagger vertical offsets to reduce overlap.
    for i, rec in enumerate(label_records):
        offset = y_base_offset * (1.0 + 0.35 * (i % 4))
        ax.text(
            rec.mass,
            rec.intensity + offset,
            rec.assigned_label,
            fontsize=8,
            rotation=45,
            ha="left",
            va="bottom",
            color="black",
            clip_on=True,
        )

    ax.set_xlabel("Mass / m/z")
    ax.set_ylabel("Counts / Intensity")
    ax.set_title("TOF-LIMS Spectrum with Detected Peaks")
    ax.grid(alpha=0.2)
    ax.legend(loc="upper right")
    fig.tight_layout()

    fig.savefig(out_png, dpi=180)
    plt.close(fig)


def export_peak_table(peak_records: Sequence[PeakRecord], out_csv: str):
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "peak_index",
                "detected_peak_mass",
                "peak_intensity",
                "assigned_label",
                "assignment_type",
                "matched_reference_mass",
                "mass_error",
            ]
        )
        for rec in sorted(peak_records, key=lambda r: r.mass):
            w.writerow(
                [
                    rec.peak_index,
                    f"{rec.mass:.6f}",
                    f"{rec.intensity:.6f}",
                    rec.assigned_label,
                    rec.assignment_type,
                    "" if rec.matched_reference_mass is None else f"{rec.matched_reference_mass:.6f}",
                    "" if rec.mass_error is None else f"{rec.mass_error:.6f}",
                ]
            )


def _default_out_paths(csv_path: str, label_mode: str) -> Tuple[str, str]:
    base, _ = os.path.splitext(csv_path)
    mode_tag = label_mode.lower()
    return f"{base}_peaks_{mode_tag}.csv", f"{base}_labeled_{mode_tag}.png"


def main():
    parser = argparse.ArgumentParser(
        description="TOF-LIMS CSV peak detection + labeling (mass / elemental mode)."
    )
    parser.add_argument("csv_path", help="Input spectrum CSV path")
    parser.add_argument(
        "--label-mode",
        choices=["mass", "element"],
        default=LABEL_MODE_DEFAULT,
        help="Peak labeling mode",
    )
    parser.add_argument("--out-peak-csv", default=None, help="Output peak table CSV path")
    parser.add_argument("--out-plot", default=None, help="Output labeled plot PNG path")
    parser.add_argument("--height", type=float, default=PEAK_MIN_HEIGHT, help="find_peaks minimum height")
    parser.add_argument(
        "--prominence",
        type=float,
        default=PEAK_MIN_PROMINENCE,
        help="find_peaks minimum prominence",
    )
    parser.add_argument("--distance", type=int, default=PEAK_MIN_DISTANCE, help="find_peaks minimum distance")
    parser.add_argument(
        "--match-tolerance",
        type=float,
        default=MASS_MATCH_TOLERANCE,
        help="Default mass matching tolerance for element assignment",
    )
    args = parser.parse_args()

    header, data_rows = load_csv(args.csv_path)
    mass_idx, intensity_idx = detect_columns(header, data_rows)
    masses, intensities = _parse_numeric_columns(data_rows, mass_idx, intensity_idx)

    peak_indices, _ = find_spectrum_peaks(
        masses,
        intensities,
        min_height=args.height,
        min_prominence=args.prominence,
        min_distance=args.distance,
    )

    peak_records = assign_peak_labels(
        masses,
        intensities,
        peak_indices,
        label_mode=args.label_mode,
        references=REFERENCE_MASSES,
        default_tolerance=args.match_tolerance,
        mass_label_decimals=MASS_LABEL_DECIMALS,
    )

    out_peak_csv, out_plot = _default_out_paths(args.csv_path, args.label_mode)
    if args.out_peak_csv:
        out_peak_csv = args.out_peak_csv
    if args.out_plot:
        out_plot = args.out_plot

    plot_spectrum_with_labels(
        masses,
        intensities,
        peak_records,
        out_plot,
        max_labels=MAX_LABELS_ON_PLOT,
        y_offset_ratio=LABEL_Y_OFFSET_RATIO,
    )
    export_peak_table(peak_records, out_peak_csv)

    n_total = len(peak_records)
    n_assigned = sum(1 for r in peak_records if r.assignment_type == "matched-element")
    n_unmatched = sum(1 for r in peak_records if r.assignment_type == "unmatched")

    print(f"Input CSV: {args.csv_path}")
    print(f"Detected columns -> mass: '{header[mass_idx]}', intensity: '{header[intensity_idx]}'")
    print(f"Peak detection params -> height={args.height}, prominence={args.prominence}, distance={args.distance}")
    print(f"Label mode: {args.label_mode}")
    print(f"Peaks found: {n_total}")
    print(f"Assigned peaks: {n_assigned}")
    print(f"Unmatched peaks: {n_unmatched}")
    print(f"Peak table saved: {out_peak_csv}")
    print(f"Plot saved: {out_plot}")


if __name__ == "__main__":
    main()
