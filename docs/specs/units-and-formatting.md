---
status: current          # code-verified as-built conventions; divergences ledger at end
last-verified: 2026-10-24  # SB2a Account: §3 area / volume / pressure / flow rows name the ScaleManager formatters, new velocity + pipe ID rows, D1 resolved, D2 reworded; prior 2026-10-01 scene-tools P1 Account: Factor row (format_factor/parse_factor), §7 rule 1 unitless example, D5 COUNT + D6 _ANGLE_RE divergences; prior 2026-09-24
verified-commit: a6122a0e   # SB2a Account; prior c8ff4f4   # feat/scene-tools-p1-batch; prior 762d083
applies-to:
  - firepro3d/scale_manager.py
  - firepro3d/dynamic_input.py    # FieldKind formatter/parser shells (FACTOR → ScaleManager; COUNT still local — §8 D5)
  - firepro3d/dimension_edit.py   # widget contract owned by property-panel.md §3.8; unit rules owned here
  - firepro3d/length_expr.py      # §3.1 NUM_PATTERN + §3.2 length grammar / expression evaluator
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
| Length input | any format | any format | `ScaleManager.parse_dimension(text, fallback=sm.bare_number_unit())` via **`DimensionEdit`** (never `QDoubleSpinBox` — property-panel.md §3.8); grammar per §3.1, literals and expressions per §3.2 |
| Area (geometry-derived) | `2304.0 sq ft` | `214.00 m²` (`N mm²` for METRIC_MM) | `ScaleManager.format_area_mm2(mm2)` (+ `area_mm2_value` numeric twin); `Room._fmt_area` delegates to it |
| Volume | `23040 cu ft` | `652.4 m³` (`N mm³` for METRIC_MM) | `ScaleManager.format_volume_mm3(mm3)` (+ `volume_mm3_value`); `Room._fmt_volume` delegates to it |
| Area (NFPA design basis, stored ft²) | `1500 sq ft` | `139.4 m²` | `ScaleManager.format_area_sqft(sqft)`; None-safe module wrapper `scale_manager.format_area_sqft(sqft, sm)` |
| Sprinkler density | `0.15 gpm/ft²` | `6.11 mm/min` (×40.746) | `ScaleManager.format_density(gpm_ft2)`; None-safe wrapper likewise |
| Pressure | `68.3 psi` | psi (no metric variant yet) | `ScaleManager.format_pressure(psi)` (`@staticmethod`, `:.1f` + " psi"); no metric variant |
| Flow | `750 gpm` | gpm (no metric variant yet) | `ScaleManager.format_flow(gpm)` (`@staticmethod`, `:.0f` + " gpm"); no metric variant |
| Velocity | `12.3 ft/s` | ft/s (no metric variant yet) | `ScaleManager.format_velocity(fps)` (`@staticmethod`, `:.1f` + " ft/s") |
| Pipe inner diameter (stored in) | `1.049"` | `26.6 mm` (all metric units) | `ScaleManager.format_pipe_id(inches)` (+ `pipe_id_value`); imperial `:.3f"`, metric `inches × 25.4` at `:.1f mm` |
| Text size (annotations) | Word-style **pt** display | pt | storage stays mm cap-height (paper-space.md §9; user_word_like_text_ux) |
| Angle | decimal degrees (unit-invariant) | decimal degrees (unit-invariant) | `ScaleManager.format_angle` / `parse_angle` — conventions in §4 |
| Factor (unitless ratio — the Scale tool's factor, added 2026-10-01) | bare decimal, no unit glyph (unit-invariant): `2`, `0.5`, `0.3333`, `0.00002`, `12345.6` | same | `ScaleManager.format_factor` / `parse_factor` (`@staticmethod`s; `dynamic_input._format_factor`/`_parse_factor` are delegating shells for `FieldKind.FACTOR`). **Display:** values ≥ 1 keep up to 4 decimals, values < 1 keep 4 *significant* digits (a tiny positive factor never collapses to `0`); never scientific notation; trailing zeros trimmed, rounded half-up; non-finite (`NaN`/`±inf`) displays `1` (the identity — it reaches paint paths). **Input:** the §3.1 number grammar (`_NUM`), **unsigned** (a sign is refused), optional trailing `x` / `X` / `×` (`2x`); `1e3`, `1_000`, `nan`, `inf` refused → `None` (revert). Positivity (> 0) is the field `minimum` / applier's job, not the parser's. The one precision for every factor display (HUD field, live status, commit message). |

**Spelling conventions (imperial):** `sq ft`, `cu ft`, `gpm/ft²`, `psi`, `gpm`, `gal`. **Not** `ft²`/`sqft`/`SF` in UI text. (`gpm/ft²` keeps the `ft²` glyph inside the compound unit only.)

### 3.1 Numeric grammar — shared by both parsers

The way a *number* may be written is one fact, and both `parse_dimension` and `parse_angle` obey it. They are separate functions because their **units** differ, not their arithmetic; when the grammar lived twice they drifted, and `.5` was accepted as an angle while being refused as a length.

| Form | Accepted | Note |
|---|---|---|
| `12`, `12.5`, `-12.5` | ✅ | |
| `.5`, `-.5` | ✅ | leading dot — and `.` is one of `Model_Space.ENGAGE_CHARS`, so it is the keystroke that *opens* the dynamic-input HUD; refusing it there made the key that starts a decimal produce unparseable text |
| `12.` | ✅ | trailing dot |
| `.`, `-`, `-.` | ❌ | a sign or dot alone is not a number |
| `1e3` | ❌ | far more likely a typo than an intended 1000 |
| `1,5` | ❌ | decimal comma is ambiguous against a thousands separator |
| `3/8`, `5 3/8` | lengths only (§3.2) | fraction / mixed number (whole + space + fraction); `parse_angle` and `parse_factor` refuse it |
| `6-1/2` | inch values only (§3.2) | drafting hyphen form — after a foot mark or before an inch mark; elsewhere `-` is subtraction |

Rejections route to `DimensionEdit`'s revert-to-last-valid, never to a wild value. Implementation: the shared `NUM_PATTERN` in `length_expr.py`, imported by `scale_manager.py` as `_NUM` (used by `parse_factor`, unsigned); `length_expr.py` builds its fraction and mixed-number forms on top of it; the unit suffixes and sign rules wrapped around it are each parser's own business. Two parsers still re-spell the grammar instead of reusing `_NUM` — see §8 D5 (COUNT) and D6 (angle/span).

### 3.2 Length literals and expressions

`parse_dimension` delegates to `length_expr.evaluate_length` (added 2026-10-30, backlog 823 + 1066). The text is tokenized into length literals, bare numbers and operators, then evaluated by a recursive-descent parser over typed values (length vs. bare number) — never `eval()`. Every `DimensionEdit` and every dynamic-input HUD length field gets it through `parse_dimension`.

| Literal | Forms | Value |
|---|---|---|
| Feet | `5'`, `5 ft`, then an optional inch part separated by a space or `-`: `5' 6"`, `5'-6"`, `5' 5.5"`, `5'6-1/2"`, `5'-6 1/2"`, `5ft 6in`, `5' 6` (closing inch mark optional) | ft × 12 + in, in inches |
| Inch | `6"`, `6 in`, `6 inch`, `6 inches`; `6 1/2"`, `6-1/2"`, `3/8"` | inches |
| Metric | `3048 mm`, `3.048 m` | mm / m |
| Bare | `10`, `5 3/8`, `3/8` | the field's default unit — `fallback_unit`, i.e. `sm.bare_number_unit()` |

Unit words end at a letter boundary (`5 min` is refused, not read as `5 m`) and are case-insensitive.

**Rules (ratified 2026-10-30, Phase 2 FP1):**

1. A bare mixed number (`5 3/8`, `3/8`) is a value in the field's default unit (feet in imperial).
2. Drafting minus rule: a `-` *directly* after a foot mark that leads into an inch value is the ft-in separator (`5'-6"`, `5'- 6"`); every other `-` is subtraction or a leading sign (`10' - 3"` = 9'-9", `12"-3"` = 9"). The hyphen mixed number `6-1/2` is an inch value only when followed by an inch mark or when it is the inch part after a foot mark.
3. With `*` `/`, a unitless operand is a scalar; with `+` `−`, it is a length in the default unit. Bare ⊕ bare stays bare. Length × length, anything ÷ length, ÷ 0 → rejected.
4. Lengths only (angle/factor/count untouched); standard precedence; parentheses.

**Operators:** `+`, `-` / `−`, `*` / `×`, `/` / `÷`, `(` `)`; `×` `÷` bind tighter than `+` `−`, and chain left to right; unary minus (`-10'`, `-(5')`). A bare unspaced `a/b` (`3/8`) is evaluated as division — the same value as the fraction, so rule 1 holds — which keeps `10'/2/5` = 1'; only a marked fraction (`3/8"`, `1/2'`) or a spaced mixed number (`5 3/8`) is one literal. A marked fraction after `/` is a length, so `10'/1/2"` is a ratio and refused. Right after a `/`, whatever the spacing, a bare value is a plain number, never a mixed number: `1/2 3/4` and `1/ 2 3/4` are two fractions side by side (refused), and dividing by a mixed number takes brackets — `10' / (2 1/2)` = 4', while `10' / 2 1/2` is refused (ratified 2026-10-30, after the T1-2 review found spacing-dependent readings).

**Unknown default unit:** when `fallback_unit` is not one `_to_mm` knows, only text whose result carries its own unit parses; a bare result returns `None`.

**Rejected → `None` (revert-to-last-valid):** length × length (an area), anything ÷ a length (a ratio), ÷ 0, a zero denominator (`1/0"`), juxtaposed literals (`5' 6" 3"`, `5ft 6in 2`, `1m 50mm` — never truncated to the leading part), unbalanced or empty brackets, a dangling operator, input over 200 characters (bounds the recursion depth), a non-finite result.

**Behaviour change:** `5' -6"` (a space before the minus) now reads 5' − 6" = 4'-6" (it was 5'-6").

Angle, span, factor and count fields take no arithmetic.

## 4. Angles

Angles are **unit-invariant** — decimal degrees in both imperial and metric projects, unaffected by `display_unit`. That is why the three angle helpers (`normalize_angle`, `format_angle`, `parse_angle`) are `@staticmethod` on `ScaleManager`: they need no scene, no project, and no ScaleManager instance.

| Concern | Convention | Owner |
|---|---|---|
| Orientation | Y-up: `0°` = right (+X), `90°` = up | — |
| Display range | `(-180, 180]` — `270` displays as `-90°` | `ScaleManager.normalize_angle` |
| Display | decimal degrees, `°` glyph **inside** the string (`45°`, `-16.4°`); trailing zeros trimmed, capped at 2 decimals, rounded half-away-from-zero | `ScaleManager.format_angle` |
| Input | bare number = degrees; optional trailing `°` / `deg` / `degrees` (case-insensitive); negatives accepted; number grammar per **§3.1** (shared with `parse_dimension`) | `ScaleManager.parse_angle` |
| Unsigned sweep (arc span, included angle) | `[0, 360]`, **not** normalised — `270` displays as `270°`; same glyph / trim / non-finite rules as `format_angle` | `ScaleManager.format_span` / `parse_span` (promoted 2026-09-24; `dynamic_input._format_span`/`_parse_span` are delegating shells) |

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

**Absolute vs relative.** `format_angle`/`parse_angle` carry no notion of a reference — they always render and parse a plain degree value. A client whose angle is *relative* to something (e.g. a connected pipe's angle relative to its reference pipe) owns the subtraction and **must** make the convention visible in the field label (`Rel A` vs `A`), because the formatted string is identical either way. See `align-placement.md §4`.

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

1. New quantity → new `ScaleManager.format_<quantity>()` method + None-safe module wrapper if callers can be scene-less. Never a local helper in an entity/dialog module. **Exception:** a *unit-invariant* quantity needs no wrapper — make its helpers `@staticmethod`s, which are inherently scene-less, and there is nothing for a wrapper to guard against (see angles, §4, and the unitless factor, `format_factor` / `parse_factor`, §3). A widget layer that needs a module-level formatter/parser pair (e.g. `dynamic_input`) keeps only thin delegating shells (precedent: `_format_span` / `_format_factor`).
2. New editable dimension → `DimensionEdit`. New editable NFPA field → convert at the `set_property` boundary, store native.
3. Copy the spelling table verbatim; when in doubt, match the Room properties panel.
4. Tests asserting display strings should construct a real `ScaleManager` (not a MagicMock) and set `display_unit` explicitly.

## 8. Divergences ledger

| # | Divergence | Status |
|---|---|---|
| D1 | ~~`Room._fmt_area/_fmt_volume` are local formatters~~ | **Resolved** by SB2a T1: Room's own formatters retired onto `ScaleManager.format_area_mm2` / `format_volume_mm3` (Room keeps one-line delegates). |
| D2 | ScaleManager formatters exist (SB2a: `format_pressure` / `format_flow` / `format_velocity`); no metric variant yet. Inline f-strings in report / badge / solver messages remain (`hydraulic_report.py`, `hydraulic_solver.py`, `design_area.py`). | Acceptable while psi/gpm are the only display units; promote the inline sites and add a metric variant when metric pressure/flow is requested. |
| D3 | `hydraulic_solver`/`equivalent_length` internals mix ft/psi/gpm computation constants — out of scope here (they compute, not display). | By design. |
| D4 | `design_area.py` imports the private `_SQFT_TO_M2` from scale_manager for its set_property back-conversion. | Cosmetic; expose a public constant or a `parse_area_to_sqft` helper on next touch. |
| D5 | COUNT (`FieldKind.COUNT` — array / gridline counts) is still formatted and parsed by local helpers `dynamic_input._format_count` / `_parse_count`, not `ScaleManager`. `_parse_count` uses bare `float()`, so it accepts `1e3` / `1_000` against §3.1, and typing `inf` raises `OverflowError` inside `editingFinished`. (Recorded 2026-10-01; `FACTOR` was moved onto `ScaleManager` in the same batch, COUNT was not — the move is not mechanical.) | Bug filed (todo `_parse_count accepts 1e3/1_000 …`): move COUNT format/parse onto `ScaleManager` static methods on the `_NUM` grammar, then add its §3 row. |
| D6 | `ScaleManager._ANGLE_RE` (behind `parse_angle` / `parse_span`) re-spells the number grammar inline instead of reusing `_NUM`, and additionally accepts a leading `+`. Same accepted forms otherwise. (Recorded 2026-10-01.) | Fold onto `_NUM` with the COUNT move (D5, same filed task). |
