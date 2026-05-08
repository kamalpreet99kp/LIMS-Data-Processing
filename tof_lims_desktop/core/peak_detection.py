from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks


@dataclass
class PeakDetectionSettings:
    threshold: float = 365.0
    prominence: float = 50.0
    distance: int = 5
    width: float | None = None


def detect_peaks(counts: np.ndarray, settings: PeakDetectionSettings) -> np.ndarray:
    idx, _ = find_peaks(
        counts,
        height=settings.threshold,
        prominence=settings.prominence,
        distance=max(1, int(settings.distance)),
        width=settings.width,
    )
    return idx
