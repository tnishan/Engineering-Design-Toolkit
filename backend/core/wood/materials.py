"""Material properties for wood design.

Two families are supported:

*Sawn lumber* - specified strengths from CSA O86-19 Table 6.3.1A (visually
graded dimension lumber). These are transcribed values and are flagged
``verified=False``: the engineer of record must check every number against a
licensed copy of CSA O86 / the Wood Design Manual before the output is used on
a real project. The toolkit surfaces this in the warnings list and the calc
report rather than hiding it.

*Structural composite lumber (SCL)* - specified strengths transcribed from
Weyerhaeuser Trus Joist specifier's guide TJ-9500 (Eastern Canada, February
2026), which states it is for use with CSA O86:19. These are flagged
``verified=True`` because the implementation reproduces the factored moment and
shear resistance tables published in the same document to within rounding; see
tests/test_scl_against_tj9500.py.

All strengths are stored in MPa. Source values in psi are converted explicitly
so the original published figure stays visible in the code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.units import psi_to_mpa


@dataclass(frozen=True)
class WoodMaterial:
    key: str
    name: str
    family: str  # "sawn" | "scl" | "custom"

    fb_mpa: float  # specified bending strength
    fv_mpa: float  # specified longitudinal shear strength
    fcp_mpa: float  # specified compression perpendicular to grain
    fc_mpa: float  # specified compression parallel to grain
    ft_mpa: float  # specified tension parallel to grain
    e_mpa: float  # modulus of elasticity
    e05_mpa: float  # 5th-percentile modulus (stability calculations)
    g_mpa: float  # shear modulus (SCL: published; sawn: taken as E/16)
    density_kg_m3: float

    source: str
    verified: bool = False

    # SCL only: f_b is published at a reference depth and scaled by
    # (d_ref / d) ** exponent. Empty for sawn lumber, which uses K_Z instead.
    depth_ref_mm: float | None = None
    depth_exponent: float | None = None

    # SCL only: the widths and depths the manufacturer actually lists.
    available_widths_mm: tuple[float, ...] = field(default_factory=tuple)
    available_depths_mm: tuple[float, ...] = field(default_factory=tuple)

    def fb_at_depth(self, d_mm: float) -> float:
        """Specified bending strength adjusted for member depth (SCL only)."""
        if self.depth_ref_mm is None or self.depth_exponent is None:
            return self.fb_mpa
        return self.fb_mpa * (self.depth_ref_mm / d_mm) ** self.depth_exponent

    def depth_factor(self, d_mm: float) -> float:
        if self.depth_ref_mm is None or self.depth_exponent is None:
            return 1.0
        return (self.depth_ref_mm / d_mm) ** self.depth_exponent


# --------------------------------------------------------------------------
# Sawn lumber - CSA O86-19 Table 6.3.1A, visually graded dimension lumber.
# UNVERIFIED TRANSCRIPTION - engineer of record must confirm against O86.
# --------------------------------------------------------------------------

_O86_TABLE = "CSA O86-19 Table 6.3.1A (dimension lumber) - VERIFY against licensed copy"

# key: (fb, ft, fv, fcp, fc, E, E05) in MPa
_SAWN_VALUES: dict[str, tuple[str, tuple[float, ...]]] = {
    "SPF-SS": ("S-P-F Select Structural", (16.5, 8.6, 1.5, 5.3, 14.5, 10500, 7500)),
    "SPF-No1No2": ("S-P-F No.1/No.2", (11.8, 5.5, 1.5, 5.3, 11.5, 9500, 6500)),
    "SPF-No3": ("S-P-F No.3/Stud", (7.0, 3.2, 1.5, 5.3, 9.0, 9000, 6000)),
    "DFirL-SS": ("D Fir-L Select Structural", (16.0, 10.6, 1.9, 7.0, 19.0, 12500, 8500)),
    "DFirL-No1No2": ("D Fir-L No.1/No.2", (12.0, 7.0, 1.9, 7.0, 14.0, 11000, 7000)),
    "HemFir-SS": ("Hem-Fir Select Structural", (16.0, 9.7, 1.6, 4.6, 17.6, 12000, 8500)),
    "HemFir-No1No2": ("Hem-Fir No.1/No.2", (11.0, 6.2, 1.6, 4.6, 14.8, 11000, 7500)),
    "Northern-SS": ("Northern Select Structural", (10.6, 6.2, 1.3, 3.5, 13.0, 7500, 5500)),
    "Northern-No1No2": ("Northern No.1/No.2", (7.5, 4.0, 1.3, 3.5, 10.4, 7000, 5000)),
}


def _sawn(key: str) -> WoodMaterial:
    name, (fb, ft, fv, fcp, fc, e, e05) = _SAWN_VALUES[key]
    return WoodMaterial(
        key=key,
        name=name,
        family="sawn",
        fb_mpa=fb,
        fv_mpa=fv,
        fcp_mpa=fcp,
        fc_mpa=fc,
        ft_mpa=ft,
        e_mpa=e,
        e05_mpa=e05,
        # O86 does not tabulate G for sawn lumber; E/16 is the conventional
        # ratio and shear deflection is negligible at normal span-to-depth
        # ratios, so this only affects the analysis at the margins.
        g_mpa=e / 16.0,
        density_kg_m3=420.0,
        source=_O86_TABLE,
        verified=False,
    )


# --------------------------------------------------------------------------
# Structural composite lumber - Weyerhaeuser TJ-9500 (E. Canada, Feb 2026),
# "Specified Strengths and Moduli of Elasticity (Standard Term)", page 5.
# --------------------------------------------------------------------------

_TJ = "Weyerhaeuser Trus Joist TJ-9500 (E. Canada, Feb 2026), Design Properties p.5"

IN = 25.4
DEPTH_REF_MM = 12.0 * IN  # published f_b is at 12 in. depth


def _scl(
    key: str,
    name: str,
    *,
    g_psi: float,
    e_psi: float,
    fb_psi: float,
    ft_psi: float,
    fcp_psi: float,
    fc_psi: float,
    fv_psi: float,
    exponent: float,
    widths_in: tuple[float, ...],
    depths_in: tuple[float, ...],
    density: float,
) -> WoodMaterial:
    return WoodMaterial(
        key=key,
        name=name,
        family="scl",
        fb_mpa=psi_to_mpa(fb_psi),
        fv_mpa=psi_to_mpa(fv_psi),
        fcp_mpa=psi_to_mpa(fcp_psi),
        fc_mpa=psi_to_mpa(fc_psi),
        ft_mpa=psi_to_mpa(ft_psi),
        e_mpa=psi_to_mpa(e_psi),
        # TJ-9500 does not publish E05 for SCL. The guide requires lateral
        # support at bearings and at 24 in. on-centre along the span, under
        # which K_L = 1.0 and E05 is not needed for bending. E/1.05 is a
        # placeholder used only if a stability check is ever requested.
        e05_mpa=psi_to_mpa(e_psi) / 1.05,
        g_mpa=psi_to_mpa(g_psi),
        density_kg_m3=density,
        source=_TJ,
        verified=True,
        depth_ref_mm=DEPTH_REF_MM,
        depth_exponent=exponent,
        available_widths_mm=tuple(w * IN for w in widths_in),
        available_depths_mm=tuple(d * IN for d in depths_in),
    )


_SCL_MATERIALS = {
    m.key: m
    for m in [
        _scl(
            "LVL-2.0E-Microllam",
            "Microllam LVL 2.0E",
            g_psi=125_000, e_psi=2.0e6, fb_psi=4805, ft_psi=2870,
            fcp_psi=1365, fc_psi=4005, fv_psi=530, exponent=0.136,
            widths_in=(1.75,),
            depths_in=(9.25, 9.5, 11.25, 11.875, 14.0, 16.0, 18.0, 20.0),
            density=670.0,
        ),
        _scl(
            "PSL-2.0E-Parallam",
            "Parallam PSL 2.0E (beam)",
            g_psi=125_000, e_psi=2.0e6, fb_psi=5360, ft_psi=3750,
            fcp_psi=1365, fc_psi=4630, fv_psi=540, exponent=0.111,
            widths_in=(3.5, 5.25, 7.0),
            depths_in=(9.5, 11.875, 14.0, 16.0, 18.0),
            density=800.0,
        ),
        _scl(
            "LSL-1.55E-TimberStrand",
            "TimberStrand LSL 1.55E (beam)",
            g_psi=96_875, e_psi=1.55e6, fb_psi=4295, ft_psi=1975,
            fcp_psi=1635, fc_psi=3465, fv_psi=575, exponent=0.092,
            widths_in=(1.75, 3.5),
            depths_in=(9.5, 11.875, 14.0, 16.0),
            density=670.0,
        ),
        _scl(
            "LSL-1.3E-TimberStrand",
            "TimberStrand LSL 1.3E (beam/column)",
            g_psi=81_250, e_psi=1.3e6, fb_psi=3140, ft_psi=1985,
            fcp_psi=1295, fc_psi=2930, fv_psi=780, exponent=0.092,
            widths_in=(3.5,),
            depths_in=(5.5, 7.25),
            density=670.0,
        ),
    ]
}

# Weyerhaeuser: beams 1-3/4 in. x 16 in. and deeper require multiple plies.
SCL_MIN_PLIES_DEPTH_MM = 16.0 * IN
SCL_MIN_PLIES_WIDTH_MM = 1.75 * IN

# TJ-9500 general assumptions: SCL requires lateral support at bearings and at
# 24 in. on-centre maximum along the span.
SCL_MAX_LATERAL_SPACING_MM = 24.0 * IN


_MATERIALS: dict[str, WoodMaterial] = {
    **{k: _sawn(k) for k in _SAWN_VALUES},
    **_SCL_MATERIALS,
}


def get(key: str) -> WoodMaterial:
    try:
        return _MATERIALS[key]
    except KeyError:
        raise KeyError(
            f"Unknown material {key!r}. Available: {', '.join(sorted(_MATERIALS))}"
        ) from None


def all_materials() -> list[WoodMaterial]:
    return list(_MATERIALS.values())


def custom(
    name: str,
    fb_mpa: float,
    fv_mpa: float,
    fcp_mpa: float,
    e_mpa: float,
    *,
    fc_mpa: float = 0.0,
    ft_mpa: float = 0.0,
    e05_mpa: float | None = None,
    g_mpa: float | None = None,
    density_kg_m3: float = 670.0,
    source: str = "User-entered product evaluation report",
    depth_ref_mm: float | None = None,
    depth_exponent: float | None = None,
) -> WoodMaterial:
    """Build a material from values the engineer types in from a product report."""
    return WoodMaterial(
        key="custom",
        name=name,
        family="custom",
        fb_mpa=fb_mpa,
        fv_mpa=fv_mpa,
        fcp_mpa=fcp_mpa,
        fc_mpa=fc_mpa,
        ft_mpa=ft_mpa,
        e_mpa=e_mpa,
        e05_mpa=e05_mpa if e05_mpa is not None else e_mpa / 1.05,
        g_mpa=g_mpa if g_mpa is not None else e_mpa / 16.0,
        density_kg_m3=density_kg_m3,
        source=source,
        verified=True,  # entered by the engineer from a report they hold
        depth_ref_mm=depth_ref_mm,
        depth_exponent=depth_exponent,
    )
