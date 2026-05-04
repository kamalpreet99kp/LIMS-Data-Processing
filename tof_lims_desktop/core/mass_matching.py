from __future__ import annotations

from enum import Enum

from tof_lims_desktop.core.isotope_database import IsotopeDatabase, IsotopeEntry


class IonMode(str, Enum):
    POSITIVE = 'Positive'
    NEGATIVE = 'Negative'


class MatchMode(str, Enum):
    EXACT = 'exact'
    NOMINAL = 'nominal'


class LabelMode(str, Enum):
    ELEMENT = 'element'
    ISOTOPE = 'isotope'
    ISOTOPE_MASS = 'isotope+mass'
    ION = 'ion'


def find_matches(peak_mass: float, db: IsotopeDatabase, tolerance: float, match_mode: MatchMode) -> list[IsotopeEntry]:
    if match_mode == MatchMode.NOMINAL:
        return [e for e in db.entries if abs(round(e.exact_mass) - round(peak_mass)) <= 0]
    return [e for e in db.entries if abs(e.exact_mass - peak_mass) <= tolerance]


def format_label(entry: IsotopeEntry, mode: LabelMode, peak_mass: float, ion_mode: IonMode) -> str:
    if mode == LabelMode.ELEMENT:
        return entry.element
    if mode == LabelMode.ISOTOPE:
        return entry.isotope
    if mode == LabelMode.ISOTOPE_MASS:
        return f"{entry.isotope} ({peak_mass:.2f})"
    return f"{entry.isotope}{'+' if ion_mode == IonMode.POSITIVE else '-'}"
