<!-- last-verified: 2026-08-29 · verified-commit: ba9e090 (feat/design-token-system) -->

# Theming & UI Style

`firepro3d/theme.py` is the **single source of truth** for the application's
visual language — colours, widget styling, and the dark/light variants. Every
UI component's **chrome** should derive its colours from this module rather than
hard-coding hex values, so a theme change stays a small edit. (Scope: chrome +
canvas background + selection/grip feedback. Placed-element drawing colours —
walls, pipes, sprinklers… — are a separate functional palette owned by
`display_manager.py`, NOT this module.)

## Token system (two layers)

A `Theme` is an immutable dataclass, and a theme variant **authors only Layer-1
primitives**; everything else derives. Defining a new variant is just its ~16
primitive values — no logic.

**Layer 1 — primitives (the only authored values):**

| Group | Primitives |
|---|---|
| Surfaces (deepest→raised) | `ground`, `surface`, `sunken`, `raised` |
| Lines | `line`, `line_strong` |
| Ink (text) | `ink`, `muted`, `faint` |
| Accent | `accent`, `accent_ink` |
| Selection | `selection`, `selection_active` |
| Status | `ok`, `warn`, `danger` |

**Layer 2 — semantics (derived `@property`, shared by all variants):** the names
consumers actually use — `bg_base`/`bg_raised`/`bg_sunken`, `btn_hover`/
`btn_pressed`/`btn_checked`/`btn_checked_border`, `border_strong`/`border_subtle`,
`text_primary`/`text_secondary`/`text_disabled`/`text_accent`, `canvas_bg`,
`grid_dot`, `accent_primary`, `status_ok`/`status_warn`/`status_error`, and the
soft/rgba fills `accent_soft`/`accent_soft2`/`warn_soft`/`danger_soft`, plus
`chip`/`chip_ink`/`surface2`/`table`. Each is a pure function of primitives (an
alias or an alpha/`_mix` derivation), so LIGHT can't drift from DARK.

`Theme.color(name, alpha=255) -> QColor` resolves any primitive or hex-valued
semantic name (used for delegate/canvas painting; the rgba `*_soft` strings are
QSS-only).

```python
from firepro3d import theme as th

t = th.detect()                 # active variant (see below)
dot_color = QColor(t.grid_dot)  # derive a colour from a semantic token
grip = t.color("selection")     # or via the QColor accessor
```

### Choosing the variant — `detect()` + the theme preference

`detect()` returns the active `Theme` honouring the persisted **`ui/theme`**
preference (**Preferences → UI** tab, `UIPane`): `light`/`dark` force the
variant; `system` (default) picks DARK/LIGHT by the OS window-palette lightness.
The preference is cached (`theme_preference()`); call `refresh_theme_preference()`
after changing it. `MainWindow._apply_theme` re-applies the app + ribbon
stylesheets live on change — but consumers that latch `detect()` at construction
(dialogs, the 3D toolbar) only restyle when next opened.

**DARK is dialed-in** (the refined green palette; `accent = #63BE8B`).
**LIGHT is legible-but-provisional** — token-driven and readable, not held to the
DARK aesthetic bar.

### No hard-coded chrome colours

Chrome must derive from tokens. `tests/test_theme_chrome_hexguard.py` fails if a
migrated chrome file reintroduces raw hex in a `setStyleSheet(...)` call without
an explicit `# theme-exempt: <reason>` marker (used only for fixed paper/preview
backdrops). The guard is allow-listed to the migrated files today; extending it
to the full chrome set is a tracked follow-up.

## Global stylesheet

`build_app_qss(t)` returns the application-wide QSS, applied once at startup:

```python
app.setStyleSheet(th.build_app_qss(th.detect()))
```

Because it uses standard Qt widget selectors, it styles **every** widget
uniformly without per-widget stylesheets — windows, buttons (and their hover /
pressed / checked / disabled states), inputs, combo boxes, tabs, scrollbars,
group boxes, and checkbox indicators. `build_ribbon_qss(t)` provides the
ribbon-specific styling.

Prefer the global stylesheet over per-widget `setStyleSheet()`. Reach for a
local stylesheet only for a genuinely component-specific look (e.g. the import
dialog's compact "pill" buttons), and derive any colours from theme tokens.

### Checkbox indicators

The default dark-palette checkbox indicator is near-invisible, so the global
stylesheet styles `QCheckBox::indicator` **and** `QAbstractItemView::indicator`
(covering standalone checkboxes and item-view check columns alike):

- **Unchecked** — empty box (`border_strong` border on `bg_base`).
- **Checked** — `accent_primary` fill plus a white tick from
  `firepro3d/graphics/checkmark.svg`.
- **Indeterminate** — `accent_primary` fill, no tick (Word-style mixed-value
  square, used by the property panel's multi-select checkboxes). QSS replaces
  native painting entirely, so a state without a rule silently renders as
  unchecked — every new state needs an explicit rule.

The single white-tick SVG works for both variants because the checked fill is
the blue accent in each.

### Radio-button indicators

`QRadioButton::indicator` is also styled explicitly (circular, 14 px, same
border/accent tokens as checkboxes) because QSS replaces native painting
entirely — an unstyled state renders identically to the base state and becomes
invisible on the dark theme. States covered: unchecked, `:hover`,
`:checked` (radial-gradient filled dot), `:disabled`.

## UI conventions

### Typography & labels

- **Font family:** the app sets **no** explicit family — it inherits the system
  default (**Segoe UI** on Windows). Do not hard-code a UI font family in QSS;
  `main.py` uses `QFont("Segoe UI", …)` only for the splash logo/status where an
  explicit size is needed.
- **Monospace** (`"IBM Plex Mono", Consolas, monospace`) is reserved for
  *technical values* — layer-name lists, scale/ratio readouts — never for prose
  or labels.
- **No `letter-spacing`.** Character tracking is not part of the house style;
  don't add it to headers or labels.
- **Group / section labels are UPPERCASE** and use the shared `role="header"`
  style (muted, ~10px, weight 600) — e.g. `SOURCE`, `PLACEMENT`, `DETAILS`.
  Author the label text in normal case and uppercase in code
  (`QLabel(text.upper())` + `setProperty("role","header")`) or author it
  uppercased; either way the rendered label is uppercase. Field labels
  (`Scale:`, `X:`) stay sentence case.
- **Button hover** in dialog chrome uses an **accent-soft** wash with an accent
  border (not a neutral `surface2` fill). Object-scoped dialogs that predate this
  (the base Underlay-Manager QSS) may still use `surface2`; new/ported dialogs
  should override to accent-soft.

### Canvas selection & resize grips (base style)

The canonical look-and-feel for any selectable/resizable canvas item
(established 2026-07-20 from the paper-space viewport; sheet text conforms;
future resizable items must too). Values live in `constants.py`
(`SELECTION_OUTLINE_COLOR`, `SELECTION_OUTLINE_WIDTH_MM`,
`SELECTION_GRIP_SIZE_MM`, `SELECTION_GRIP_OUTLINE_WIDTH_MM`) — one home,
deliberately theme-independent (CAD selection blue reads on both themes):

- **Selected boundary** — dashed `SELECTION_OUTLINE_COLOR` outline at
  `SELECTION_OUTLINE_WIDTH_MM` around the item's box.
- **Grips** — **8 handles** (4 corners + 4 edge midpoints): white-filled
  squares of `SELECTION_GRIP_SIZE_MM` with a `SELECTION_OUTLINE_COLOR`
  outline, centred on the box corners/midpoints. Scaled items divide by their
  scale so grips stay true paper-mm.
- **Resize behavior** — corner grips resize both axes anchoring the
  diagonally-opposite corner; midpoint grips resize one axis; a drag gesture
  is captured press→release and lands as **one undo command**.
- **Distinct states keep distinct looks** — e.g. sheet text inline-*editing*
  uses its own lighter `#88aaff` dashed frame; only the *selected* state uses
  the base style.
- **Model-space grab handles** are screen-pixel sized rather than paper-mm (they
  use `ItemIgnoresTransformations`; `SELECTION_GRIP_SIZE_MM` is paper-only). The
  gridline pull-tab grip (`_PullTabGrip` in `gridline.py`) uses the
  `SELECTION_OUTLINE_COLOR` constant. The central grip renderer in
  `model_view.drawForeground` (which paints handles for all `grip_points()`
  items) reads the **theme** `selection` / `selection_active` tokens instead — so
  model-space grips follow the accent (green), while paper-space grips and the
  dashed selection boundary still use the blue `SELECTION_*` constants. This
  split is **interim**: the `SelectionBox` manipulator task (8 handles + rotation,
  accent-styled) unifies both onto the selection tokens.

### ALIGN alignment guide

The `AlignEngine` overlay (dashed alignment guide line + reference glyph,
drawn in `model_view.drawForeground`) has its own dedicated style so it reads
as *ALIGN* rather than geometry or OSNAP:

- **Color** — `ALIGN_GUIDE_COLOR` (`constants.py`, cyan `#00c8ff`), distinct
  from gridline blue and OSNAP marker colors.
- **Line** — cosmetic dashed pen, pattern `ALIGN_GUIDE_DASH`.
- **Glyph** — a crosshair of `ALIGN_GLYPH_PX` (screen px) on the reference
  point being aligned to.

Reuse this token for all future ALIGN clients (walls, pipes,
sprinklers) — do not re-derive an alignment-guide color per tool.

- **Pill buttons** — compact rounded action buttons (`border-radius` ≈ half the
  height, tight padding, content-sized). Used for dense control clusters such as
  the import dialog's File / Preview / Placement rows. Applied via a small local
  stylesheet; size policy is `Fixed` (or `Expanding` when several share a row as
  a segmented control).
- **Assets** — graphics live under `firepro3d/graphics/`, resolved through
  `assets.asset_path(...)`. QSS `image: url(...)` references (e.g. the checkbox
  tick) use forward-slashed absolute paths.

## Adding a styled component

1. Take colours from `theme.detect()` tokens — never hard-code hex.
2. If a widget type needs consistent styling app-wide, add a selector to
   `build_app_qss()` rather than styling each instance.
3. Keep both `LIGHT` and `DARK` legible — test against `detect()`'s output for
   the active palette.
