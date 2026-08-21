# Engineering Design Toolkit

Self-hosted structural design tools for an Ontario engineering office, to
OBC 2024 / NBC 2020 / CSA O86-19. Three tabs today:

- **Beam design** — continuous wood beams with SFD/BMD/deflection diagrams,
  a beam elevation, and a printable calculation report.
- **Post design** — posts and columns to CSA O86-19 Cl. 6.5.6, with a
  capacity-against-length curve. A beam support reaction can be carried
  straight into the post tab.
- **Pipe surcharge** — pressure at the crown of a buried pipe from excavator
  tracks, wheel loads, or a multi-axle truck (CL-625, a tri-axle roll-off, or
  your own axle configuration). Six methods side by side, a pressure bulb
  through the section, both travel directions computed every time, and a
  vehicle-comparison table for "which of these governs."

> **This is a design aid, not a design.** The engineer of record is responsible
> for verifying every input, material property, code clause and result. Sawn
> lumber properties in this repository are an unverified transcription of CSA
> O86-19 tables and are flagged as such throughout the app and the report.

## Architecture

```
backend/
  core/                  pure Python calculation engine - no web imports
    units.py             ft / in / m / mm parsing -> SI
    loads/combinations.py NBC 2020 Table 4.1.3.2
    analysis/beam.py     Timoshenko continuous-beam direct-stiffness solver
    wood/                materials, sections, O86 factors, checks, orchestrator
      compression.py     posts and columns (Cl. 6.5.6)
      scl_columns.py     Trus Joist published column tables
    soil/                elastic stress distribution (metres, kN, kPa)
      boussinesq.py      point and rectangle solutions, load spread
      westergaard.py     layered-deposit counterpart, integrated numerically
      contours.py        marching squares for the pressure-bulb iso-lines
      loads.py           track / wheel / multi-axle-truck configurations
      vehicles.py        CL-625, a tri-axle roll-off, an excavator - presets
      buried_pipe.py     crown surcharge, method comparison, position sweep
    report/              calc traces + Jinja2 printable HTML report
  api/                   FastAPI wrapper over core (routers + Pydantic schemas)
  projects/              saved jobs, one JSON file each (git-ignored)
  tests/                 closed-form, manufacturer-table and API tests
frontend/                React + TypeScript (Vite), recharts diagrams
Materials/               manufacturer literature (TJ-9500 specifier's guide)
```

`core/` never imports FastAPI, so it is reusable from scripts, a CLI, or a
future job queue.

## Running it

Backend (port 8010):

```bash
cd backend && .venv/Scripts/python -m uvicorn api.main:app --port 8010 --reload
```

Frontend (port 5173, proxies `/api` to the backend):

```bash
cd frontend && npm run dev
```

Then open http://localhost:5173.

Tests:

```bash
cd backend && .venv/Scripts/python -m pytest -q
```

## What the tool shows

- **Beam model (live)** — sits at the top of the results column and redraws as you
  type, before anything is analysed. Elevation on the left: supports with
  pin/roller/fixed symbols, each load case as its own labelled band (self weight
  faded), span dimensions in metric and feet, and — once designed — reaction arrows
  with the bearing length each support needs. Cross-section on the right: individual
  plies drawn and numbered with ply and overall dimensions. Underneath, a plain
  sentence of the section, its A / S / I, and self weight.

  The preview parses through the *same backend code the design uses*
  (`POST /api/beam/preview` shares `_parse` with `/design`), so the drawing on
  screen can never disagree with what is analysed — there is a test asserting it.
  A half-typed span shows a message and keeps the last valid drawing rather than
  blanking. Editing after a run marks the results stale and clears the reaction
  arrows, since they no longer belong to the section on screen.
- **SFD / BMD / deflection** — factored envelopes over all combinations, filled and
  annotated with peak values and their locations. All three share an identical plot
  area, so a feature at a given `x` lines up vertically across the three charts. The
  BMD can be flipped between sagging-up and tension-side conventions. Deflection
  carries a dashed allowable line per span.
- **Reactions and bearing** — per support: envelope maximum, which combination
  produced it, the bearing length required, and the utilisation.

## Saved projects

Projects are stored as JSON in `backend/projects/`, one file per job, so they can be
copied, backed up or diffed like any other engineering file. Only the *inputs* are
saved — results are recomputed on open, so a saved job never carries stale numbers
after a formula or material change. `Export .json` / `Import .json` move a job
between machines.

## Analysis method

Two-node Timoshenko beam elements solved by the direct stiffness method. Shear
deformation is included because Weyerhaeuser requires it for SCL products and
publishes a shear modulus for the purpose; it also slightly relieves the hogging
moment at interior supports of a continuous member. Setting G very large
recovers the Euler-Bernoulli solution, which the test suite uses to check
against closed-form results.

Each load case (D, L, S, W) is solved once and combinations are formed by
superposition. Shear and moment are recovered from statics on the free body left
of each station, so the diagrams are mesh-independent and checkable by hand.

## Verification status

| Area | Status |
|---|---|
| Beam solver | Verified against closed-form: simple-span UDL and point load, cantilever, two-span continuous (wL²/8), three-moment equation for unequal spans, partial UDL statics, and the Timoshenko shear-deflection closed form. |
| SCL (LVL / PSL / LSL) properties | Transcribed from `Materials/TJ-9500.pdf` (Weyerhaeuser Trus Joist, Eastern Canada, Feb 2026, stated for CSA O86:19). **35 published factored moment and shear resistances are reproduced exactly** by the implementation — see `tests/test_scl_against_tj9500.py`. |
| Sawn lumber properties | **UNVERIFIED transcription** of CSA O86-19 Table 6.3.1A. Must be checked against a licensed copy before office use. |
| SCL column capacities | Read from the TJ-9500 published tables, not computed. All 100+ tabulated values are reproduced exactly by the lookup — see `tests/test_post_design.py`. |
| Post design formula (sawn) | Implements Cl. 6.5.6 as written. Factor behaviour is unit-tested (K_Zcg cap, C_c ≤ 50, effect of bracing and end fixity), but there is no published Canadian sawn column table in the repo to check the absolute numbers against — **hand-check one case**. |
| Size factors K_Z (Table 6.4.5) | **UNVERIFIED transcription.** |
| Boussinesq stress | Verified: point-load closed form, equilibrium (stress integrates to the applied load), the m=n=1 tabulated influence factor 0.1752, the 1/4 limit for a large area, and the rectangle closed form checked against brute-force numerical integration of point loads at five plan positions. |
| Westergaard stress | Verified: closed form on the load axis (P/(pi z^2) at nu = 0), the classical 2/3 ratio to Boussinesq there, equilibrium at nu = 0 and nu = 0.3, rectangle integration converged and checked against the point-load limit at depth. |
| Pressure-bulb contours | Marching squares; every contour vertex is checked to lie at its own stated pressure, interpolated from the grid it came from. |
| Method working | Each method's per-area rows are checked to reconcile with its headline: the superposition methods must sum to it, the spread methods must have it as their largest candidate area. The Boussinesq and point-load rows are re-derived from the text of the row itself. |
| Load-spread factors | **UNVERIFIED transcription** of AASHTO-style live-load distribution and depth-reduced impact. Flagged as such on every result. No CSA S6 values included. |
| Load combinations | NBC 2020 Table 4.1.3.2; combinations whose loads are absent are collapsed so the report never cites a term such as "1.5L" on a member with no live load. |

## Engineer's checklist before office use

1. Verify sawn lumber specified strengths in `core/wood/materials.py` against CSA O86-19 Table 6.3.1A.
2. Verify size factors K_Zb / K_Zv in `core/wood/factors.py` against Table 6.4.5.
3. Confirm bearing (`Q_r`) omits K_D per Cl. 6.5.7 as implemented.
4. Confirm the creep factor policy for total deflection (Cl. 4.5.3) matches office practice — the default of 1.0 excludes creep and the app warns about it.
5. Hand-check one full worked example end to end against the Wood Design Manual.

## Buried pipe surcharge

Five methods are reported side by side at crown level, and as curves against
depth:

| Method | What it is for |
|---|---|
| **Boussinesq (rectangles)** | The primary result. Contact areas integrated with the Newmark corner influence factor and superposed. Independent of E and Poisson's ratio. |
| Boussinesq (point idealisation) | Shown to expose its own error — it is singular at the surface and overstates badly when the contact area is not small against the depth. At 0.4 m cover under an excavator it reads 2.6x the rectangle solution; by 12 m the two agree. Left out of the depth chart on purpose - it would swamp the scale. |
| Westergaard | Half-space restrained against lateral strain by rigid horizontal layers — a layered or varved deposit, or backfill compacted in thin lifts. Two thirds of Boussinesq on the load axis at nu = 0, crossing above it near r = 1.5z. |
| 2:1 spread (merged) | Classical bookkeeping rule; where two footprints' spread areas overlap they are merged into one combined area. |
| 2:1 spread (individual, summed) | Same rule, but each footprint's spread area is kept separate and summed at the point of interest instead of merged - the other common reading of the 2:1 rule. |
| Code spread (LLDF) | Same merged-area form with a prescribed factor. Unverified, see below. |

Every method shows its **supporting calculation**: the formula, a row per
contact area with the contact pressure, the patch edges measured from the point
of interest and the influence factor that came out of them, and the sum. A
reviewer can take `q` and `I` off a row and reproduce it by hand — there are
tests that do exactly that.

Graphically:

- **Isometric cutaway** — the loads on the ground surface, the pipe, the
  pressure bulb painted on the vertical cut face, and the crown-level slice
  revealed by the cut. Plain SVG, so it prints; the projection of a rectangle
  is a parallelogram, so the stress fields go on with an affine transform and
  no distortion.
- **Pressure bulb** through the section, with round-number kPa contours.
- Stress against depth with one curve per method, and crown stress against
  machine position across the pipe.

Section and plan sit side by side, as do the two charts — laid out with a
container query on the results column, because the column's width depends on
whether the app itself is one or two columns and a viewport media query got
that wrong.

Both travel directions are computed on every run, so the table always shows
whether crossing the pipe or tracking along it governs — you never have to
remember to check the other one.

Two things the tool is deliberate about:

- **It reports free-field stress, and says so everywhere.** There is no pipe in
  the model. A rigid pipe stiffer than its surround attracts more than this; a
  flexible one sheds load into the sidefill. Turning the number into a design
  pressure needs a bedding factor and a pipe-stiffness assessment.
- **It searches for the worst machine position** rather than assuming centred is
  critical. Tracking *along* a pipe, a wide-gauge machine on shallow cover
  leaves the pipe in the gap between its tracks: a 20 t excavator at 0.5 m cover
  gives 3.4 kPa centred but 42.2 kPa with one track over the pipe — 12x higher.
  Crossing the pipe there is no gap, and centred always governs.

Load-spread factors are transcribed and flagged unverified in the UI and the
report. **No CSA S6 values are built in** — enter your own with the custom
preset.

## Why SCL columns are looked up, not computed

The CSA O86 Cl. 6.5.6 slenderness formula does not reproduce Weyerhaeuser's
published column tables. Back-solving E05 from their 1.8E Parallam values gives
5314 MPa at 6 ft rising to 9572 MPa at 14 ft — no single elastic property
explains the table, and TJ-9500 does not publish E05 for SCL at all. Rather than
invent a formula, SCL column capacities are read straight from the manufacturer's
table and interpolated on length, which is what an engineer would do by hand and
carries the manufacturer's own authority. The app says so on every SCL result.

## Roadmap

- Tool 2: retaining wall detail generator (ezdxf DXF export) on the same skeleton
- Combined axial + bending, glulam, joist vibration
- Bridge tools to CSA S6: load rating, bearing design, live-load distribution
