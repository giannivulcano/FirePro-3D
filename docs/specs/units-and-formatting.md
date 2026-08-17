---
status: current          # code-verified as-built conventions; divergences ledger at end
last-verified: 2026-08-17
verified-commit: a913e1b
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
| Angle | decimal degrees (unit-invariant) | decimal degrees (unit-invariant) | `ScaleManager.format_angle` / `parse_angle` — conventions in §4 |

**Spelling conventions (imperial):** `sq ft`, `cu ft`, `gpm/ft²`, `psi`, `gpm`, `gal`. **Not** `ft²`/`sqft`/`SF` in UI text. (`gpm/ft²` keeps the `ft²` glyph inside the compound unit only.)

## 4. Angles

Angles are **unit-invariant** — decimal degrees in both imperial and metric projects, unaffected by `display_unit`. That is why the three angle helpers (`normalize_angle`, `format_angle`, `parse_angle`) are `@staticmethod` on `ScaleManager`: they need no scene, no project, and no ScaleManager instance.

| Concern | Convention | Owner |
|---|---|---|
| Orientation | Y-up: `0°` = right (+X), `90°` = up | — |
| Display range | `(-180, 180]` — `270` displays as `-90°` | `ScaleManager.normalize_angle` |
| Display | decimal degrees, `°` glyph **inside** the string (`45°`, `-16.4°`); trailing zeros trimmed, capped at 2 decimals, rounded half-away-from-zero | `ScaleManager.format_angle` |
| Input | bare number = degrees; optional trailing `°` / `deg` / `degrees` (case-insensitive); negatives accepted; scientific notation deliberately rejected — `1e3` in an angle field is far more likely a typo than an intended 1000°, and rejecting it routes to revert-to-last-valid rather than a wild value | `ScaleManager.parse_angle` |

**Scene Y is down.** Converting a length + angle to a scene point therefore *subtracts* the sine:

```python
QPointF(anchor.x() + length * math.cos(theta),
        anchor.y() - length * math.sin(theta))   # Y-up → scene Y-down
```

The inverse negates the delta's Y before `atan2`. `dy` must be the **raw scene delta** — deriving it from an already-Y-flipped intermediate double-negates and yields a mirrored angle that is correct at `0°` and `180°` and wrong everywhere else, which is exactly the kind of bug that survives a smoke test:

```python
dx = p2.x() - p1.x()
dy = p2.y() - p1.y()                        # raw SCENE delta, Y-down
theta = math.degrees(math.atan2(-dy, dx))   # negate dy → Y-up angle
```

This sign flip is the single most common angle bug in this codebase — never call `atan2(dy, dx)` on raw scene deltas.

**Why the `°` lives inside the string.** Folding the glyph into the return value lets an angle field be an ordinary `DimensionEdit` with a custom `formatter`/parser pair — no sibling unit label widget, no layout special-casing. Contrast `format_length`, which returns a **space before the unit** (`3048.000 mm`) while `format_angle` returns **no space** (`45°`). The asymmetry is intentional: `°` is typographically bound to the number, `mm` is a separate word. New formatters should follow whichever of the two matches their glyph, not invent a third.

**Unparseable input returns `None`** — not `0.0`, and not an exception. This matters: `DimensionEdit` reverts to its last valid value on `None`, and that is precisely what stops a typo from silently committing geometry at zero degrees. A formatter that returned `0.0` on garbage would place real geometry from bad input.

**Non-finite input** (`NaN`, `±inf`) formats as `"0°"` rather than raising, because `format_angle` runs in Qt paint paths where an unhandled Python exception becomes a silent process crash.

**Precision** is independent of `ScaleManager.precision`, which drives fractional-inch denominators and is meaningless for angles.

**Storage and the normalization boundary.** Angles are stored as plain `float` degrees — there is no separate internal basis, so §2 does not apply to them. Unlike lengths, normalization happens on the way **in** as well as out: `parse_angle` normalizes before returning, so a user who types `270` gets `-90.0` stored. Clients doing angle arithmetic (relative angles, sums) can produce values outside `(-180, 180]` and should re-normalize before display — but `format_angle` normalizes defensively as well, so a client that forgets still renders correctly rather than silently wrong.

**Absolute vs relative.** `format_angle`/`parse_angle` carry no notion of a reference — they always render and parse a plain degree value. A client whose angle is *relative* to something (e.g. a connected pipe's angle relative to its reference pipe) owns the subtraction and **must** make the convention visible in the field label (`Rel A` vs `A`), because the formatted string is identical either way. See `inferred-dimension-driven-placement.md §4`.

### 4.1 The two normalization conventions (drift guard)

There are **two** angle-normalization ranges in the codebase, and they are deliberately distinct. Do not "unify" them.

**Which one do I call?** Ask what the number is *for*:

- It will be **shown to or typed by a user** (widget, label, scene annotation, HUD field) → `ScaleManager.normalize_angle`, `(-180, 180]`.
- It decides **whether a point lies on an arc** → `geometry_intersect._normalize_angle`, `[0, 360)`.
- It is **neither** — intermediate math such as snap-octant selection, 45°-multiple validation, or relative-angle subtraction against a reference pipe → normalize only if the math needs it, and normalize at the **display boundary**, not inside the computation. **Do not add a third range.**

| Range | Owner | Use it for |
|---|---|---|
| `(-180, 180]` | `ScaleManager.normalize_angle` | Display and input. Signed readouts (`-90°`) match CAD convention. |
| `[0, 360)` | `geometry_intersect._normalize_angle` | Arc-containment sweep comparisons in `_angle_in_arc`, where a monotonic non-negative range makes wrap-around tests tractable. Never surfaced to the user. |

## 5. Input round-trips

- Editable dimension fields: `DimensionEdit` (stores mm; seed guard prevents re-quantization — property-panel.md §3.8).
- Editable NFPA-basis fields (e.g. design-area base): display converts native→display units; `set_property` converts back to the native basis. The load path must bypass conversion (properties are applied before the item joins a scene → no ScaleManager → values pass through in the native basis; keep it that way).

## 6. Deliberate exceptions

- **The DESIGN CRITERIA badge** uses the user's AHJ reference-image conventions (`usgpm`, `ft²`, `usgpm/ft²`) regardless of project units — it is a drawing artifact matching industry sheet standards, not a UI surface. Locked at the 2026-07-14 mockup gate.
- **NFPA curve-picker dialogs** (density/area graph) render the curves in their native `ft²`-axis basis with `sq ft` labels; the curves have no metric edition.

## 7. Rules for new code

1. New quantity → new `ScaleManager.format_<quantity>()` method + None-safe module wrapper if callers can be scene-less. Never a local helper in an entity/dialog module. **Exception:** a *unit-invariant* quantity needs no wrapper — make its helpers `@staticmethod`s, which are inherently scene-less, and there is nothing for a wrapper to guard against (see angles, §4).
2. New editable dimension → `DimensionEdit`. New editable NFPA field → convert at the `set_property` boundary, store native.
3. Copy the spelling table verbatim; when in doubt, match the Room properties panel.
4. Tests asserting display strings should construct a real `ScaleManager` (not a MagicMock) and set `display_unit` explicitly.

## 8. Divergences ledger

| # | Divergence | Status |
|---|---|---|
| D1 | `Room._fmt_area/_fmt_volume` are local (mm²/mm³-based) instead of ScaleManager methods; wall/floor/other entities may have siblings. | Consolidate onto `ScaleManager.format_area(mm2)` / `format_volume(mm3)` on next touch of those files. |
| D2 | Pressure/flow have no ScaleManager formatter (inline f-strings in report/badge/solver messages). | Acceptable while psi/gpm are the only display units; promote when metric pressure/flow is requested. |
| D3 | `hydraulic_solver`/`equivalent_length` internals mix ft/psi/gpm computation constants — out of scope here (they compute, not display). | By design. |
| D4 | `design_area.py` imports the private `_SQFT_TO_M2` from scale_manager for its set_property back-conversion. | Cosmetic; expose a public constant or a `parse_area_to_sqft` helper on next touch. |
