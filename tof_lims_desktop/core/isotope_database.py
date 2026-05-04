from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IsotopeEntry:
    mass: float
    element: str
    isotope: str


class IsotopeDatabase:
    def __init__(self, json_path: str | Path):
        self.json_path = Path(json_path)
        self._entries = self._load_entries()

    def _load_entries(self) -> list[IsotopeEntry]:
        data = json.loads(self.json_path.read_text(encoding="utf-8"))
        entries = [
            IsotopeEntry(
                mass=float(item["mass"]),
                element=str(item["element"]),
                isotope=str(item["isotope"]),
            )
            for item in data
        ]
        return sorted(entries, key=lambda x: x.mass)

    @property
    def entries(self) -> list[IsotopeEntry]:
        return self._entries
