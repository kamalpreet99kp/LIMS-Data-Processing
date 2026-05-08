from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SpectrumData:
    mass: np.ndarray
    counts: np.ndarray
    mass_column: str
    counts_column: str


def _norm(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


def load_spectrum(path: str, mass_column: str | None = None, counts_column: str | None = None) -> SpectrumData:
    df = pd.read_csv(path) if path.lower().endswith('.csv') else pd.read_excel(path)
    if df.shape[1] < 2:
        raise ValueError('Need at least two columns.')

    if mass_column is None or counts_column is None:
        mass_idx, counts_idx = detect_columns(df)
    else:
        mass_idx, counts_idx = df.columns.get_loc(mass_column), df.columns.get_loc(counts_column)

    mass = df.iloc[:, mass_idx].to_numpy(dtype=float)
    counts = df.iloc[:, counts_idx].to_numpy(dtype=float)
    order = np.argsort(mass)
    return SpectrumData(mass[order], counts[order], str(df.columns[mass_idx]), str(df.columns[counts_idx]))


def detect_columns(df: pd.DataFrame) -> tuple[int, int]:
    names = [_norm(str(c)) for c in df.columns]
    mass_kw = {'mass', 'mz', 'moverz', 'amu', 'x'}
    cnt_kw = {'count', 'counts', 'intensity', 'signal', 'y'}
    m = next((i for i, n in enumerate(names) if any(k in n for k in mass_kw)), None)
    c = next((i for i, n in enumerate(names) if any(k in n for k in cnt_kw)), None)
    if m is not None and c is not None and m != c:
        return m, c
    return 0, 1
