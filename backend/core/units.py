"""Unit parsing and conversion.

All calculations are performed in SI base-ish units:
    length      mm
    force       N
    moment      N.mm
    stress      MPa (N/mm^2)
    area load   kPa (kN/m^2)
    line load   N/mm

Input may be given in imperial or metric; everything is converted on entry.
"""

from __future__ import annotations

import re

MM_PER_INCH = 25.4
MM_PER_FOOT = 304.8
MPA_PER_PSI = 0.00689475729
KPA_PER_PSF = 0.0478802589
N_PER_LBF = 4.4482216153
NMM_PER_FTLB = 1355.8179483

_LENGTH_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": MM_PER_INCH,
    '"': MM_PER_INCH,
    "ft": MM_PER_FOOT,
    "'": MM_PER_FOOT,
}

# "12 ft 6 in", "12'-6\"", "3.5m", "235", "9 1/4 in". A leading sign is accepted
# so a signed position - a machine offset to one side of a pipe centreline,
# say - parses the same way a length does; callers that need a length to stay
# non-negative (a span, a section width) already enforce that separately.
_FEET_INCHES = re.compile(
    r"""^\s*
    (?P<sign>-)?\s*
    (?P<ft>\d+(?:\.\d+)?)\s*(?:ft|foot|feet|')
    \s*(?:-|and)?\s*
    (?:(?P<in_whole>\d+)\s*)?
    (?:(?P<in_num>\d+)\s*/\s*(?P<in_den>\d+)\s*)?
    (?:in|inch|inches|")?
    \s*$""",
    re.VERBOSE | re.IGNORECASE,
)

_VALUE_UNIT = re.compile(
    r"""^\s*
    (?P<sign>-)?\s*
    (?P<whole>\d+(?:\.\d+)?)?
    \s*
    (?:(?P<num>\d+)\s*/\s*(?P<den>\d+))?
    \s*
    (?P<unit>mm|cm|m|in|inch|inches|ft|foot|feet|"|')?
    \s*$""",
    re.VERBOSE | re.IGNORECASE,
)

_UNIT_ALIASES = {
    "inch": "in",
    "inches": "in",
    "foot": "ft",
    "feet": "ft",
}


class UnitError(ValueError):
    """Raised when a dimension string cannot be interpreted."""


def parse_length_mm(value: str | float | int, default_unit: str = "mm") -> float:
    """Parse a user-entered length into millimetres.

    Accepts plain numbers (interpreted as ``default_unit``), unit-suffixed values
    ("3.5 m", "235mm", '9 1/4"'), and feet-inches ("12 ft 6 in", "12'-6\"").
    """
    if isinstance(value, (int, float)):
        return float(value) * _unit_factor(default_unit)

    text = str(value).strip()
    if not text:
        raise UnitError("Empty length value.")

    m = _FEET_INCHES.match(text)
    if m and m.group("ft") is not None:
        mm = float(m.group("ft")) * MM_PER_FOOT
        if m.group("in_whole"):
            mm += float(m.group("in_whole")) * MM_PER_INCH
        if m.group("in_num"):
            mm += (float(m.group("in_num")) / float(m.group("in_den"))) * MM_PER_INCH
        return -mm if m.group("sign") else mm

    m = _VALUE_UNIT.match(text)
    if not m or (m.group("whole") is None and m.group("num") is None):
        raise UnitError(f"Could not interpret length: {value!r}")

    magnitude = float(m.group("whole")) if m.group("whole") else 0.0
    if m.group("num"):
        magnitude += float(m.group("num")) / float(m.group("den"))
    if m.group("sign"):
        magnitude = -magnitude

    unit = m.group("unit") or default_unit
    return magnitude * _unit_factor(unit)


def _unit_factor(unit: str) -> float:
    key = _UNIT_ALIASES.get(unit.lower(), unit.lower())
    if key not in _LENGTH_TO_MM:
        raise UnitError(f"Unknown length unit: {unit!r}")
    return _LENGTH_TO_MM[key]


def psi_to_mpa(psi: float) -> float:
    return psi * MPA_PER_PSI


def psf_to_kpa(psf: float) -> float:
    return psf * KPA_PER_PSF


def area_load_to_line_load(load_kpa: float, tributary_mm: float) -> float:
    """kPa over a tributary width (mm) -> line load in N/mm.

    1 kPa = 1 kN/m^2 = 1e-3 N/mm^2; multiplied by mm of width gives N/mm.
    """
    return load_kpa * 1e-3 * tributary_mm


def nmm_to_knm(nmm: float) -> float:
    return nmm * 1e-6


def n_to_kn(n: float) -> float:
    return n * 1e-3


def mm_to_ft_in(mm: float) -> str:
    """Format a millimetre length as feet-inches, for echoing imperial input."""
    total_in = mm / MM_PER_INCH
    feet = int(total_in // 12)
    inches = total_in - feet * 12
    return f"{feet}'-{inches:.2f}\""
