from __future__ import annotations

import numpy as np


def fit_linear_calibration(measured: list[float], reference: list[float]) -> tuple[float, float]:
    x = np.asarray(measured, dtype=float)
    y = np.asarray(reference, dtype=float)
    a, b = np.polyfit(x, y, 1)
    return float(a), float(b)


def apply_calibration(mass, a: float, b: float):
    return a * mass + b
