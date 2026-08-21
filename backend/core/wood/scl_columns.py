"""Published axial resistances for Trus Joist SCL columns.

The CSA O86 Cl. 6.5.6 slenderness formula does **not** reproduce Weyerhaeuser's
published column tables: back-solving E05 from their 1.8E Parallam PSL values
gives 5314 MPa at 6 ft rising to 9572 MPa at 14 ft, so a single elastic
property cannot explain the table. TJ-9500 does not publish E05 for SCL either.

Rather than invent a formula, SCL column capacities are read straight from the
manufacturer's published table (TJ-9500 p.19, "Axial Factored Resistances"),
interpolating linearly between tabulated lengths. That is what an engineer
would do by hand, and the number carries the manufacturer's own authority.

Values are factored resistances in pounds, standard term, dry service.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.units import MM_PER_FOOT, MM_PER_INCH, N_PER_LBF

TJ_SOURCE = "Weyerhaeuser Trus Joist TJ-9500 (E. Canada, Feb 2026), Columns p.19"

# Bearing condition at the column end. The wood-plate case is limited by
# compression perpendicular to grain in the plate, so it caps out at short
# lengths where the column itself would otherwise carry far more.
BEARING_TYPES = ("column_base", "wood_plate")


@dataclass(frozen=True)
class SclColumnSize:
    width_in: float
    depth_in: float

    @property
    def label(self) -> str:
        def frac(v: float) -> str:
            whole = int(v)
            sixteenths = round((v - whole) * 16)
            if sixteenths == 0:
                return str(whole)
            num, den = sixteenths, 16
            while num % 2 == 0 and den % 2 == 0:
                num //= 2
                den //= 2
            return f"{whole} {num}/{den}" if whole else f"{num}/{den}"

        return f'{frac(self.width_in)}" x {frac(self.depth_in)}"'

    @property
    def width_mm(self) -> float:
        return self.width_in * MM_PER_INCH

    @property
    def depth_mm(self) -> float:
        return self.depth_in * MM_PER_INCH

    @property
    def least_dimension_mm(self) -> float:
        return min(self.width_mm, self.depth_mm)


@dataclass(frozen=True)
class SclColumnProduct:
    key: str
    name: str
    sizes: tuple[SclColumnSize, ...]
    # bearing type -> {length_ft: (resistance_lb per size, None where not listed)}
    tables: dict[str, dict[float, tuple[float | None, ...]]]


_LSL_SIZES = (
    SclColumnSize(3.5, 3.5),
    SclColumnSize(3.5, 4.375),
    SclColumnSize(3.5, 5.5),
    SclColumnSize(3.5, 7.25),
)

_LSL_13E = SclColumnProduct(
    key="LSL-1.3E-Column",
    name="TimberStrand LSL 1.3E column",
    sizes=_LSL_SIZES,
    tables={
        "column_base": {
            3: (18915, 23500, 29335, 38340),
            4: (17620, 21905, 27365, 35790),
            5: (15820, 19680, 24605, 32210),
            6: (13705, 17065, 21350, 27985),
            7: (11405, 14260, 17925, 23615),
            8: (9295, 11620, 14605, 19250),
            9: (7565, 9460, 11890, 15675),
            10: (6170, 7715, 9700, 12785),
            12: (4150, 5185, 6520, 8595),
            14: (2845, 3560, 4475, 5895),
        },
        # The 3 ft to 8 ft band is a single plate-bearing-limited value.
        "wood_plate": {
            3: (8340, 10225, 12645, 15605),
            8: (8340, 10225, 12645, 15605),
            9: (7565, 9460, 11890, 15605),
            10: (6170, 7715, 9700, 12785),
            12: (4150, 5185, 6520, 8595),
            14: (2845, 3560, 4475, 5895),
        },
    },
)

_PSL_SIZES = (
    SclColumnSize(3.5, 3.5),
    SclColumnSize(3.5, 5.25),
    SclColumnSize(3.5, 7.0),
    SclColumnSize(5.25, 5.25),
    SclColumnSize(5.25, 7.0),
    SclColumnSize(7.0, 7.0),
)

_N = None  # slenderness ratio exceeds 50 - not tabulated

_PSL_18E = SclColumnProduct(
    key="PSL-1.8E-Column",
    name="Parallam PSL 1.8E column",
    sizes=_PSL_SIZES,
    tables={
        "column_base": {
            6: (19010, 28490, 37735, 54365, 72490, 100000),
            7: (15815, 23720, 31630, 50835, 67775, 99560),
            8: (12890, 19330, 25775, 46760, 62345, 95745),
            9: (10490, 15735, 20980, 42370, 56490, 91230),
            10: (8555, 12830, 17110, 37790, 50385, 86135),
            12: (5750, 8620, 11495, 28835, 38445, 74805),
            14: (3940, 5915, 7885, 21945, 29260, 62550),
            16: (_N, _N, _N, 16770, 22360, 51050),
            18: (_N, _N, _N, 12900, 17200, 41615),
            20: (_N, _N, _N, 10010, 13350, 33980),
            22: (_N, _N, _N, _N, _N, 27830),
            24: (_N, _N, _N, _N, _N, 22885),
        },
        "wood_plate": {
            6: (8340, 12105, 15065, 18160, 22600, 30135),
            10: (8340, 12105, 15065, 18160, 22600, 30135),
            12: (5750, 8620, 11495, 18160, 22600, 30135),
            14: (3940, 5915, 7885, 18160, 22600, 30135),
            16: (_N, _N, _N, 16770, 22360, 30135),
            18: (_N, _N, _N, 12900, 17200, 30135),
            20: (_N, _N, _N, 10010, 13350, 30135),
            22: (_N, _N, _N, _N, _N, 27830),
            24: (_N, _N, _N, _N, _N, 22885),
        },
    },
)

PRODUCTS: dict[str, SclColumnProduct] = {p.key: p for p in (_LSL_13E, _PSL_18E)}


class SclColumnError(ValueError):
    """Raised when the requested column is outside the published table."""


def capacity_n(
    product_key: str,
    size_index: int,
    length_mm: float,
    bearing: str = "column_base",
) -> tuple[float, str]:
    """Published factored axial resistance in newtons, plus a provenance note.

    Interpolates linearly between tabulated lengths; refuses to extrapolate
    beyond the ends of the table, where the manufacturer stopped publishing
    because the slenderness ratio exceeds 50.
    """
    product = PRODUCTS.get(product_key)
    if product is None:
        raise SclColumnError(f"Unknown SCL column product {product_key!r}.")
    if bearing not in product.tables:
        raise SclColumnError(f"Unknown bearing condition {bearing!r}.")
    if not 0 <= size_index < len(product.sizes):
        raise SclColumnError("Column size is not in the published table.")

    table = product.tables[bearing]
    lengths = sorted(l for l in table if table[l][size_index] is not None)
    if not lengths:
        raise SclColumnError(
            f"{product.sizes[size_index].label} {product.name} is not tabulated "
            f"for {bearing.replace('_', ' ')} bearing."
        )

    length_ft = length_mm / MM_PER_FOOT
    lo, hi = lengths[0], lengths[-1]

    if length_ft < lo - 1e-9:
        # Shorter than the table starts: the shortest tabulated value is safe
        # to use, because capacity only decreases with length.
        value = float(table[lo][size_index])
        note = (
            f"Length {length_ft:.1f} ft is below the {lo:g} ft start of the table; "
            f"the {lo:g} ft value was used, which is conservative."
        )
    elif length_ft > hi + 1e-9:
        raise SclColumnError(
            f"{product.sizes[size_index].label} {product.name} is only published "
            f"to {hi:g} ft ({hi * 0.3048:.2f} m). Beyond that the slenderness ratio "
            f"exceeds 50 - choose a larger section."
        )
    else:
        below = max(l for l in lengths if l <= length_ft + 1e-9)
        above = min(l for l in lengths if l >= length_ft - 1e-9)
        if below == above:
            value = float(table[below][size_index])
        else:
            v0 = float(table[below][size_index])
            v1 = float(table[above][size_index])
            t = (length_ft - below) / (above - below)
            value = v0 + (v1 - v0) * t
        note = (
            f"Read from the published table at {length_ft:.2f} ft"
            + ("" if below == above else f" (interpolated between {below:g} and {above:g} ft)")
            + "."
        )

    return value * N_PER_LBF, note


def sizes_for(product_key: str) -> list[dict]:
    product = PRODUCTS[product_key]
    return [
        {
            "index": i,
            "label": s.label,
            "width_mm": round(s.width_mm, 1),
            "depth_mm": round(s.depth_mm, 1),
        }
        for i, s in enumerate(product.sizes)
    ]


def products() -> list[dict]:
    return [
        {"key": p.key, "name": p.name, "source": TJ_SOURCE, "sizes": sizes_for(p.key)}
        for p in PRODUCTS.values()
    ]
