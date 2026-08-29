---
status: proposal
last-verified: 2026-08-29
verified-commit: c8b7640
applies-to:
  - firepro3d/theme.py
  - firepro3d/underlay_manager.py
  - firepro3d/underlay_manager_delegates.py
  - firepro3d/model_view.py
source-tasks:
  - "TODO.md:360 House theme adopts the manager palette [P2]"
  - "TODO.md:147 Grab-handle style consistency [P3]"
---

# Design-Token System — Design Spec

## Goal

Make `firepro3d/theme.py` a **two-layer semantic design-token system** that is the
single aesthetic source of truth for all application chrome. A theme variant
authors **only** a small set of primitive colours; everything else derives. Defining
a new theme (e.g. a legible LIGHT variant) becomes ~16 values, no logic. The
governing doc (`docs/architecture/theming.md`) is the leash that keeps future
features conforming.

The Underlay Manager's refined green palette (`underlay_manager_theme.py`) is folded
in as the DARK values and the file is deleted; the manager becomes the reference
consumer of the house theme.

## Motivation

Two theme systems drifted apart: the house theme (`theme.py`, blue accent, ~24
hand-authored role tokens per variant, LIGHT+DARK kept in sync by hand) and the
manager's private theme (`underlay_manager_theme.py`, green accent, richer token
vocabulary, DARK-only). ~9 chrome surfaces also hard-code colours and ignore both.
The result is an inconsistent, hard-to-restyle app. A single small primitive palette
+ derived semantics fixes the drift structurally and gives a professional, consistent
look that future features inherit for free.

## Architecture & Constraints

**Two layers.**

- **Layer 1 — Primitives (16).** The only thing a theme variant authors. Grouped:
  - Surfaces (4, deepest→raised): `ground` · `surface` · `sunken` · `raised`
  - Lines (2): `line` · `line_strong`
  - Ink (3): `ink` · `muted` · `faint`
  - Accent (2): `accent` · `accent_ink`
  - Selection (2): `selection` · `selection_active`
  - Status (3): `ok` · `warn` · `danger`
- **Layer 2 — Semantics (authored once, shared by all variants, derived from Layer
  1).** The names consumers use. Includes the current `theme.py` role names (so chrome
  barely changes) plus the manager's needs. All `*_soft` rgba fills and
  `hover/pressed/checked` states are **functions of primitives**, not authored.

**Constraints.**
- Keep the semantic consumer API (`t.bg_raised`, `t.text_primary`, …) so existing
  chrome that already derives from tokens is untouched.
- `Theme` gains a `.color(name, alpha=255) -> QColor` accessor resolving primitive OR
  semantic names, so `underlay_manager_delegates` keeps painting after the swap.
- Scope: chrome + canvas **background** + grip/selection feedback IN; placed-element
  (entity) colours OUT (owned by `display_manager`).
- Rule A: `theming.md` owns the token vocabulary; `constants.py` keeps owning
  `SELECTION_*` metrics. No LOC/line counts in docs.

## Design Decisions

- **Token architecture: two-layer** (primitives + derived semantics) over flat
  role-tokens (a theme would be 32 hand-authored values, drift-prone) or pure abstract
  scale tokens (`Primary1/2/3` referenced directly — semantic knowledge leaks into
  every consumer). Two-layer delivers the "theme = flat value list" goal while keeping
  consumers readable.
- **DARK values: the manager palette, dialed** (mockup-approved, variant B):
  `ground #141619` · `surface #1E2125` · `sunken #212529` · `raised #24282D` ·
  `line #363B41` · `line_strong #454B52` · `ink #E6E9EC` · `muted #98A1AA` ·
  `faint #6F7982` · `accent #63BE8B` · `accent_ink #0E1712` · `selection #63BE8B` ·
  `selection_active #8FE3B4` · `ok #6FBE93` · `warn #D9A24A` · `danger #E07A6F`.
- **Selection is its own token** (default = accent green, tunable independently), NOT
  folded into `accent`. Active-grip highlight `selection_active` = brighter green
  `#8FE3B4` (mockup pick B).
- **Density: rounded + roomy app-wide** (mockup pick) — 6px corner radius, roomier
  padding, 13px base font baked into `build_app_qss`.
- **LIGHT: legible-but-provisional.** A structurally complete 16-value LIGHT preset
  that is legible (no invisible-on-white text, no hard-coded regressions) but not held
  to the DARK aesthetic bar. Proves the "5-line theme" claim; acceptance = legible +
  token-driven, not "beautiful".
- **Grip renderer fix is interim.** Point `model_view.drawForeground` grip painting at
  `selection` / `selection_active` tokens (minimal re-color). The full `SelectionBox`
  manipulator (8 handles + rotation) is a **separate dependent task**, not here.

### Semantic mapping (Layer 2 → Layer 1)

| Semantic (consumer name) | Derivation |
|---|---|
| `bg_base` / `canvas_bg` | `ground` |
| `bg_raised` | `raised` |
| `bg_sunken` | `sunken` |
| `bg_tab_inactive` | `surface` |
| `bg_tab_selected` | `raised` |
| `btn_hover` | `accent_soft` = alpha(`accent`, 34) |
| `btn_pressed` | `raised` |
| `btn_checked` | `accent_soft2` = alpha(`accent`, 56) |
| `btn_checked_border` | `accent` |
| `border_strong` | `line_strong` |
| `border_subtle` | `line` |
| `text_primary` | `ink` |
| `text_secondary` / `chip_ink` | `muted` |
| `text_disabled` | `faint` |
| `text_accent` / `accent_primary` | `accent` |
| `grid_dot` | subtle mix(`ground`, `faint`) |
| `chip` | `raised` |
| `accent_soft` / `accent_soft2` | alpha(`accent`, 34 / 56) |
| `warn_soft` / `danger_soft` | alpha(`warn`, 40) / alpha(`danger`, 38) |
| `status_ok` / `status_warn` / `status_error` | `ok` / `warn` / `danger` |

### Migrations

- `underlay_manager_theme.py` **deleted**; `underlay_manager.py` +
  `underlay_manager_delegates.py` consume the house `Theme` (QSS via a house
  `build_*` path or object-scoped rules folded into `build_app_qss`; delegates via
  `Theme.color()`). Manager visually equivalent in DARK; renders (provisional) in LIGHT.
- 9 chrome hard-coders migrated onto tokens: `loading_bar.py`, `view_3d.py`
  (toolbar/info — fixes LIGHT unreadability), `auto_populate_dialog.py` (status labels →
  `status_*`), `roof_dialog.py`/`wall_dialog.py` (`grey` → `text_secondary`),
  `titleblock_arrange.py`/`titleblock_editor.py` (amber `#b8620a` → `warn`),
  `dxf_preview_dialog.py` (grays/blue). Any single rabbit hole → its own follow-up.

## Acceptance Criteria

- [ ] `theme.py` presets are pure 16-primitive value sets; a variant authors nothing
      else. Semantics derive from primitives, shared across variants.
- [ ] DARK matches the mockup-approved green palette (variant B).
- [ ] `underlay_manager_theme.py` deleted, zero importers; manager visually equivalent
      in DARK and renders (provisional) in LIGHT via the house theme; delegates paint
      via `Theme.color()`.
- [ ] All 9 chrome surfaces legible and token-driven in **both** themes.
- [ ] Model-space grips read as `selection` (resting) / `selection_active` (dragging).
- [ ] LIGHT is legible and fully token-driven (no invisible text, no hard-coded chrome).
- [ ] Unit tests: token-presence/consistency; built-QSS contains token values
      (behavior, not source inspection); scoped anti-drift hex-guard flags raw-hex chrome
      in migrated files.
- [ ] `docs/architecture/theming.md` updated to govern the two-layer token vocabulary
      (Rule A; stamped in Phase 6).

## Verification Checklist

- [ ] All acceptance criteria met.
- [ ] Tests pass (`pytest` on touched areas + full suite before done).
- [ ] No DARK visual regression (manager, ribbon, docks, dialogs) — manual LIGHT+DARK
      smoke over the enumerated surface checklist gates wrap-up.
- [ ] No remaining `underlay_manager_theme` importers.

## Tech Context

- **Framework:** PyQt6; theming via QSS built from tokens (`build_app_qss` /
  `build_ribbon_qss`), applied once at startup; `detect()` picks LIGHT/DARK by window
  lightness.
- **Dependencies:** none new.

## Existing Code Context

- `firepro3d/theme.py` — current flat `Theme` dataclass + QSS builders + `detect()`.
- `firepro3d/underlay_manager_theme.py` — source palette, object-scoped QSS,
  delegate `.color()` (to be deleted).
- `firepro3d/constants.py` — `SELECTION_OUTLINE_COLOR`/`*_MM` grip metrics (kept).
- `firepro3d/model_view.py` — `drawForeground` grip renderer (interim re-color).
- `docs/architecture/theming.md` — governing doc (updated Phase 6).

## Out of Scope (filed as sibling task)

Adopt the `SelectionBox` manipulator (8 resize handles + rotation knob, accent-styled,
transform→baked-geometry integration, snapping/HUD/undo/rotation-convention work)
app-wide, consuming the `selection`/`selection_active` tokens from this system. Its own
[P1] follow-up = review every item with a selection box and match it. Depends on this
token system landing first.
