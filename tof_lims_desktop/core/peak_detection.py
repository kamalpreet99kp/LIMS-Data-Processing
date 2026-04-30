from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks


@dataclass
class PeakDetectionSettings:
    min_height: float = 365.0
    prominence: float = 50.0
    distance: int = 5


def detect_peaks(counts: np.ndarray, settings: PeakDetectionSettings) -> np.ndarray:
    peak_indices, _ = find_peaks(
        counts,
        height=settings.min_height,
        prominence=settings.prominence,
        distance=max(1, int(settings.distance)),
    )
    return peak_indices
