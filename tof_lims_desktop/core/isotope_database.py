from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IsotopeEntry:
    atomic_number: int
    element: str
    mass_number: int
    exact_mass: float
    abundance: float
    isotope: str


class IsotopeDatabase:
    def __init__(self, path: str | Path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        self.entries = [IsotopeEntry(**item) for item in data]
