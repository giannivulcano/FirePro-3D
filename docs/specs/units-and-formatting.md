---
status: current          # code-verified as-built conventions; divergences ledger at end
last-verified: 2026-07-14
verified-commit: 696ad74
applies-to:
  - firepro3d/scale_manager.py
  - firepro3d/dimension_edit.py   # widget contract owned by property-panel.md §3.8; unit rules owned here
source-tasks: "Design-Area Criteria System wrap-up (2026-07-14) — user-requested consistency guide after mixed ft²/sq ft surfaced in smoke test"
---

# Units & Formatting — Governing Style Guide

**One rule above all: no widget, panel, dialog, report, or scene item formats a physical quantity with its own ad-hoc string.** Every displayed value goes through the conventions below, and every *new* formatter lands on `ScaleManager` — the single formatting home.

## 1. Goal

One place that answers "how do I display/parse this quantity?" so units stay consistent across the property panel, dialogs, reports, badges, and scene annotations — and so metric/imperial switching works everywhere for free.

## 2. The two internal unit bases

| Domain | Internal basis | Rationale |
|---|---|---|
| **Geometry** (lengths, coordinates, areas/volumes derived from geometry) | **millimeters** (mm, mm², mm³) | Scene-wide canon (CLAUDE.md); 1 scene unit = 1 mm. |
| **NFPA hydraulic quantities** (design areas, densities, pressures, flows, K-factors, pipe capacity) | **imperial-native** (ft², gpm/ft², psi, gpm, gal, K in gpm/√psi) | NFPA 13 tables/curves are defined in these units; storing native avoids double-conversion drift. |

Values are converted **at display time only**. Never store a display string as the source of truth for math (the design-area `Area` panel property is display-only; calc reads the numeric `_as_entries`).

## 3. Display conventions by quantity

`ScaleManager.display_unit` (`DisplayUnit.IMPERIAL / METRIC_MM / METRIC_M`) drives everything.

| Quantity | Imperial | Metric | Formatter (the one home) |
|---|---|---|---|
| Length | `10' 6 1/2"` | mm / m per unit + precision | `ScaleManager.format_length(mm)` |
| Length input | any format | any format | `ScaleManager.parse_dimension(text, fallback=sm.bare_number_unit())` via **`DimensionEdit`** (never `QDoubleSpinBox` — property-panel.md §3.8) |
| Area (geometry-derived) | `2304.0 sq ft` | `214.0 m²` (mm² for METRIC_MM) | `Room._fmt_area(mm2)` — **divergence D1**, consolidate onto ScaleManager on next touch |
| Volume | `23040 cu ft` | `652.4 m³` | `Room._fmt_volume(mm3)` — same D1 |
| Area (NFPA design basis, stored ft²) | `1500 sq ft` | `139.4 m²` | `ScaleManager.format_area_sqft(sqft)`; None-safe module wrapper `scale_manager.format_area_sqft(sqft, sm)` |
| Sprinkler density | `0.15 gpm/ft²` | `6.11 mm/min` (×40.746) | `ScaleManager.format_density(gpm_ft2)`; None-safe wrapper likewise |
| Pressure | `68.3 psi` | psi (no metric variant yet) | inline `:.1f` + "psi" — add `format_pressure` to ScaleManager if bar/kPa is ever needed |
| Flow | `750 gpm` | gpm (no metric variant yet) | inline `:.0f` + "gpm" |
| Text size (annotations) | Word-style **pt** display | pt | storage stays mm cap-height (paper-space.md §9; user_word_like_text_ux) |

**Spelling conventions (imperial):** `sq ft`, `cu ft`, `gpm/ft²`, `psi`, `gpm`, `gal`. **Not** `ft²`/`sqft`/`SF` in UI text. (`gpm/ft²` keeps the `ft²` glyph inside the compound unit only.)

## 4. Input round-trips

- Editable dimension fields: `DimensionEdit` (stores mm; seed guard prevents re-quantization — property-panel.md §3.8).
- Editable NFPA-basis fields (e.g. design-area base): display converts native→display units; `set_property` converts back to the native basis. The load path must bypass conversion (properties are applied before the item joins a scene → no ScaleManager → values pass through in the native basis; keep it that way).

## 5. Deliberate exceptions

- **The DESIGN CRITERIA badge** uses the user's AHJ reference-image conventions (`usgpm`, `ft²`, `usgpm/ft²`) regardless of project units — it is a drawing artifact matching industry sheet standards, not a UI surface. Locked at the 2026-07-14 mockup gate.
- **NFPA curve-picker dialogs** (density/area graph) render the curves in their native `ft²`-axis basis with `sq ft` labels; the curves have no metric edition.

## 6. Rules for new code

1. New quantity → new `ScaleManager.format_<quantity>()` method + None-safe module wrapper if callers can be scene-less. Never a local helper in an entity/dialog module.
2. New editable dimension → `DimensionEdit`. New editable NFPA field → convert at the `set_property` boundary, store native.
3. Copy the spelling table verbatim; when in doubt, match the Room properties panel.
4. Tests asserting display strings should construct a real `ScaleManager` (not a MagicMock) and set `display_unit` explicitly.

## 7. Divergences ledger

| # | Divergence | Status |
|---|---|---|
| D1 | `Room._fmt_area/_fmt_volume` are local (mm²/mm³-based) instead of ScaleManager methods; wall/floor/other entities may have siblings. | Consolidate onto `ScaleManager.format_area(mm2)` / `format_volume(mm3)` on next touch of those files. |
| D2 | Pressure/flow have no ScaleManager formatter (inline f-strings in report/badge/solver messages). | Acceptable while psi/gpm are the only display units; promote when metric pressure/flow is requested. |
| D3 | `hydraulic_solver`/`equivalent_length` internals mix ft/psi/gpm computation constants — out of scope here (they compute, not display). | By design. |
| D4 | `design_area.py` imports the private `_SQFT_TO_M2` from scale_manager for its set_property back-conversion. | Cosmetic; expose a public constant or a `parse_area_to_sqft` helper on next touch. |
