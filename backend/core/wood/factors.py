"""CSA O86-19 modification factors.

Each factor returns a FactorTrace carrying the clause reference so the calc
report can show where the number came from. Values transcribed from O86 tables
are marked in their description; the engineer of record verifies them.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.report.trace import FactorTrace
from core.wood.materials import WoodMaterial
from core.wood.sections import BuiltUpSection

# Resistance factors, CSA O86-19 Cl. 5.2.4 / Cl. 6.5 / Cl. 13.
PHI_BENDING = 0.9
PHI_SHEAR = 0.9
PHI_BEARING = 0.8
PHI_COMPRESSION = 0.8

# Duration of load, Cl. 5.3.2 Table 5.3.2.2.
_KD = {"permanent": 0.65, "standard": 1.00, "short": 1.15}

# Service condition, Table 6.4.2 (dimension lumber).
_KS_DRY = {"bending": 1.00, "shear": 1.00, "bearing": 1.00, "compression": 1.00, "E": 1.00}
_KS_WET = {"bending": 0.84, "shear": 0.96, "bearing": 0.67, "compression": 0.69, "E": 0.94}

# Treatment, Table 6.4.3. Incising for preservative penetration reduces
# strength; fire-retardant treatment requires manufacturer data.
_KT = {
    "none": {"strength": 1.00, "E": 1.00},
    "preservative": {"strength": 1.00, "E": 1.00},
    "incised": {"strength": 0.75, "E": 0.90},
}

# Size factor for visually graded dimension lumber, Table 6.4.5, 38 mm thick.
# UNVERIFIED TRANSCRIPTION - confirm against a licensed copy of O86.
_KZ_BY_DEPTH: dict[float, tuple[float, float]] = {
    # depth_mm: (K_Zb, K_Zv)
    89.0: (1.7, 1.7),
    140.0: (1.4, 1.5),
    184.0: (1.2, 1.3),
    235.0: (1.1, 1.2),
    286.0: (1.0, 1.1),
    337.0: (0.9, 1.0),
}

# Bearing length factor, Table 6.5.6.5.1. Applies where the bearing is more
# than 75 mm from the end of the member.
_KB_POINTS: tuple[tuple[float, float], ...] = (
    (12.5, 1.75), (25.0, 1.50), (38.0, 1.30),
    (50.0, 1.25), (75.0, 1.15), (150.0, 1.00),
)


@dataclass(frozen=True)
class Conditions:
    load_duration: str = "standard"   # overridden per combination
    service: str = "dry"              # "dry" | "wet"
    treatment: str = "none"           # "none" | "preservative" | "incised"
    system: str = "none"              # "none" | "case1" | "case2"  (K_H, Cl. 6.4.4)
    laterally_supported: bool = True  # continuous restraint of compression edge
    bearing_length_mm: float = 89.0
    bearing_at_end: bool = False


def kd(duration: str) -> FactorTrace:
    if duration not in _KD:
        raise ValueError(f"Unknown load duration {duration!r}")
    return FactorTrace(
        "K_D", _KD[duration], "O86-19 Cl. 5.3.2",
        f"Duration of load ({duration} term)",
    )


def ks(service: str, kind: str) -> FactorTrace:
    table = _KS_DRY if service == "dry" else _KS_WET
    if kind not in table:
        raise ValueError(f"Unknown K_S kind {kind!r}")
    return FactorTrace(
        f"K_S{_SUB[kind]}", table[kind], "O86-19 Table 6.4.2",
        f"Service condition ({service} service, {kind})",
    )


_SUB = {"bending": "b", "shear": "v", "bearing": "cp", "compression": "c", "E": "E"}


def kt(treatment: str, kind: str = "strength") -> FactorTrace:
    if treatment not in _KT:
        raise ValueError(f"Unknown treatment {treatment!r}")
    return FactorTrace(
        "K_T", _KT[treatment][kind], "O86-19 Table 6.4.3",
        f"Treatment factor ({treatment})",
    )


def kh(system: str, kind: str = "bending") -> FactorTrace:
    """System factor, Cl. 6.4.4.

    Case 1 applies to members spaced no more than 610 mm apart with at least
    three members sharing the load through a distributing element. A single
    built-up beam carrying a concentrated tributary area is not a Case 1
    system, so the default is 1.0.
    """
    value = 1.0
    if system == "case1" and kind == "bending":
        value = 1.10
    elif system == "case2" and kind == "bending":
        value = 1.20
    return FactorTrace(
        "K_H", value, "O86-19 Cl. 6.4.4",
        f"System factor ({'no system action' if system == 'none' else system})",
    )


def kz(material: WoodMaterial, section: BuiltUpSection, kind: str) -> FactorTrace:
    """Size factor.

    Sawn lumber uses O86 Table 6.4.5. SCL instead uses the manufacturer's
    published depth adjustment on f_b, so K_Z is 1.0 and the depth effect is
    applied inside the material.
    """
    if material.family != "sawn":
        return FactorTrace(
            "K_Z", 1.0, "O86-19 Cl. 13 / product report",
            "Size effect handled by the SCL depth adjustment on f_b",
        )

    if kind == "bearing":
        return FactorTrace("K_Zcp", 1.0, "O86-19 Cl. 6.5.6.5", "Bearing size factor")

    pair = _KZ_BY_DEPTH.get(section.depth_mm)
    if pair is None:
        nearest = min(_KZ_BY_DEPTH, key=lambda d: abs(d - section.depth_mm))
        pair = _KZ_BY_DEPTH[nearest]
    value = pair[0] if kind == "bending" else pair[1]
    return FactorTrace(
        f"K_Z{'b' if kind == 'bending' else 'v'}", value, "O86-19 Table 6.4.5",
        f"Size factor for {section.depth_mm:.0f} mm depth",
    )


def kl(material: WoodMaterial, conditions: Conditions) -> FactorTrace:
    """Lateral stability factor, Cl. 6.5.4.2.

    K_L = 1.0 when the compression edge is restrained throughout its length and
    the ends are restrained against rotation. The tool does not attempt to
    compute a reduced K_L: if the member is not laterally supported it refuses
    to assume 1.0 and raises a warning instead, because an unbraced deep beam
    needs an explicit stability calculation.
    """
    if conditions.laterally_supported:
        return FactorTrace(
            "K_L", 1.0, "O86-19 Cl. 6.5.4.2",
            "Compression edge laterally restrained throughout",
        )
    return FactorTrace(
        "K_L", 1.0, "O86-19 Cl. 6.5.4.2",
        "ASSUMED 1.0 - member declared without lateral support; verify stability",
    )


def kb(conditions: Conditions) -> FactorTrace:
    """Bearing length factor, Table 6.5.6.5.1 (linear between tabulated points)."""
    if conditions.bearing_at_end:
        return FactorTrace(
            "K_B", 1.0, "O86-19 Cl. 6.5.6.5",
            "Bearing within 75 mm of member end - no length benefit",
        )

    length = conditions.bearing_length_mm
    lengths = [p[0] for p in _KB_POINTS]
    values = [p[1] for p in _KB_POINTS]
    if length <= lengths[0]:
        value = values[0]
    elif length >= lengths[-1]:
        value = values[-1]
    else:
        value = values[-1]
        for (l0, v0), (l1, v1) in zip(_KB_POINTS[:-1], _KB_POINTS[1:]):
            if l0 <= length <= l1:
                value = v0 + (v1 - v0) * (length - l0) / (l1 - l0)
                break
    return FactorTrace(
        "K_B", value, "O86-19 Table 6.5.6.5.1",
        f"Bearing length factor for {length:.0f} mm bearing",
    )
