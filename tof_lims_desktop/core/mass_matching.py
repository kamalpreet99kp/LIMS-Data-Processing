from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tof_lims_desktop.core.isotope_database import IsotopeDatabase, IsotopeEntry
from core.isotope_database import IsotopeDatabase, IsotopeEntry


class IonMode(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"  # future extension


class LabelDisplayMode(str, Enum):
    ELEMENT = "element"
    ISOTOPE = "isotope"
    ELEMENT_MASS = "element+mass"


@dataclass
class MatchResult:
    peak_mass: float
    matches: list[IsotopeEntry]


def find_isotope_matches(
    peak_mass: float,
    db: IsotopeDatabase,
    tolerance: float,
    ion_mode: IonMode = IonMode.POSITIVE,
) -> MatchResult:
    if ion_mode == IonMode.NEGATIVE:
        # Placeholder: future cluster matching will be added here.
        pass

    matches = [
        entry for entry in db.entries if abs(entry.mass - peak_mass) <= tolerance
    ]
    matches.sort(key=lambda item: abs(item.mass - peak_mass))
    return MatchResult(peak_mass=peak_mass, matches=matches)


def format_label(entry: IsotopeEntry, display_mode: LabelDisplayMode, peak_mass: float) -> str:
    if display_mode == LabelDisplayMode.ELEMENT:
        return entry.element
    if display_mode == LabelDisplayMode.ISOTOPE:
        return entry.isotope
    return f"{entry.isotope} ({peak_mass:.3f})"
