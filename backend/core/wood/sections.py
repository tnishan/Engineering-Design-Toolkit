"""Cross-section geometry for solid-sawn and built-up (multi-ply) members."""

from __future__ import annotations

from dataclasses import dataclass

from core.wood.materials import IN, WoodMaterial

# Canadian dressed dimension lumber, 38 mm nominal thickness (CSA O141).
SAWN_THICKNESS_MM = 38.0
SAWN_DEPTHS_MM: tuple[float, ...] = (89.0, 140.0, 184.0, 235.0, 286.0, 337.0)

SAWN_LABELS = {
    89.0: "2x4", 140.0: "2x6", 184.0: "2x8",
    235.0: "2x10", 286.0: "2x12", 337.0: "2x14",
}

# Shear-area factor for a rectangle (Timoshenko k_s = 5/6, so A_s = A / 1.2).
RECT_SHEAR_FACTOR = 1.2


@dataclass(frozen=True)
class BuiltUpSection:
    """A member made of ``plies`` identical rectangular laminations."""

    ply_width_mm: float
    depth_mm: float
    plies: int = 1

    @property
    def width_mm(self) -> float:
        return self.ply_width_mm * self.plies

    @property
    def area_mm2(self) -> float:
        return self.width_mm * self.depth_mm

    @property
    def section_modulus_mm3(self) -> float:
        return self.width_mm * self.depth_mm**2 / 6.0

    @property
    def inertia_mm4(self) -> float:
        return self.width_mm * self.depth_mm**3 / 12.0

    @property
    def shear_area_mm2(self) -> float:
        return self.area_mm2 / RECT_SHEAR_FACTOR

    def self_weight_n_per_mm(self, material: WoodMaterial) -> float:
        """Self weight as a downward line load, N/mm."""
        volume_m3_per_mm = self.area_mm2 * 1e-6 * 1e-3  # m^2 * m per mm of length
        return material.density_kg_m3 * volume_m3_per_mm * 9.81

    def label(self, material: WoodMaterial) -> str:
        if material.family == "sawn":
            base = SAWN_LABELS.get(self.depth_mm, f"{self.ply_width_mm:.0f}x{self.depth_mm:.0f}")
            ply = f"{self.plies}-ply " if self.plies > 1 else ""
            return f"{ply}{base} ({self.plies} x {self.ply_width_mm:.0f} x {self.depth_mm:.0f} mm)"
        w_in = self.ply_width_mm / IN
        d_in = self.depth_mm / IN
        ply = f"{self.plies}-ply " if self.plies > 1 else ""
        return (
            f"{ply}{_frac(w_in)}\" x {_frac(d_in)}\" {material.name} "
            f"({self.width_mm:.0f} x {self.depth_mm:.0f} mm)"
        )


def _frac(value: float) -> str:
    """Render an inch dimension the way a lumber schedule would (9 1/4, 1 3/4)."""
    whole = int(value)
    frac = value - whole
    sixteenths = round(frac * 16)
    if sixteenths == 0:
        return str(whole)
    if sixteenths == 16:
        return str(whole + 1)
    num, den = sixteenths, 16
    while num % 2 == 0 and den % 2 == 0:
        num //= 2
        den //= 2
    return f"{whole} {num}/{den}" if whole else f"{num}/{den}"


def candidates(material: WoodMaterial, max_plies: int = 6) -> list[BuiltUpSection]:
    """Every section the tool will consider when searching for a size.

    Ordered by area so the search returns the lightest adequate member first.
    """
    if material.family == "sawn":
        widths = (SAWN_THICKNESS_MM,)
        depths = SAWN_DEPTHS_MM
    else:
        widths = material.available_widths_mm or (1.75 * IN,)
        depths = material.available_depths_mm or (
            9.5 * IN, 11.875 * IN, 14.0 * IN, 16.0 * IN, 18.0 * IN,
        )

    out = [
        BuiltUpSection(w, d, p)
        for w in widths
        for d in depths
        for p in range(1, max_plies + 1)
    ]
    out.sort(key=lambda s: (s.area_mm2, s.depth_mm))
    return out
