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

**House fonts (2026-09-01 decision).** Two families, exported from `theme.py`:

- **`FONT_UI = "Arial"`** — all prose and labels (Title / Body / Overline /
  Control). Applied app-wide at startup via `theme.apply_app_font(app)` in
  `main.py` (sets the `QApplication` font family, preserving point size). Do not
  hard-code a different UI family in QSS.
- **`FONT_VALUE = "Consolas"`** — numeric readouts (dimensions, scale, pressure,
  coordinates). Monospace so digit/decimal columns align and `1/l/0/O` stay
  distinct. Applied on `DimensionEdit` (the canonical numeric input) and any
  value/table cell showing numbers. **Not** for prose or labels.

**Five type roles** (name → use → spec):

| Role | Used for | Spec |
|---|---|---|
| **Title** | window/dialog/dock/tab names | `FONT_UI`, bold, ~14px, **pure ink** (`ink` token: `#F0F0F0` dark / `#1A1A1A` light) |
| **Body** | standard/descriptive text, hints | `FONT_UI`, regular, ~12px, `muted` |
| **Overline** | group/container labels (ribbon groups, dock sections, manager containers) | `FONT_UI`, **UPPERCASE**, bold, ~10px, `muted` — the shared `role="header"` style |
| **Control** | button & tab labels | `FONT_UI`, **bold, sentence case**, ~12px, `ink` |
| **Value** | numeric readouts | `FONT_VALUE`, ~12–13px, `ink` |

Rules:
- **No `letter-spacing`.** Character tracking is not part of the house style.
- **Overline labels are UPPERCASE** via `role="header"` (author normal-case and
  `QLabel(text.upper())`, or author uppercased). Field labels (`Scale:`, `X:`)
  stay sentence case; **button** labels are bold sentence case, never all-caps.
- **Button hover** in dialog chrome uses an **accent-soft** wash + accent border
  (not a neutral `surface2` fill). The base Underlay-Manager QSS predates this
  and may still use `surface2`; new/ported dialogs override to accent-soft.

### Selection controls

- **Binary on/off** (e.g. "Insert at origin") → a **toggle switch**: rounded
  track + sliding knob, **accent when on**, switch on the left with the label to
  its right. Not a lone checkbox, not radio buttons.
- **Single-select among 3+** mutually-exclusive options → a **switch bar**: a
  connected segmented control of exclusive buttons, active segment
  **accent-filled, white text**.
- **Multi-select** (independent options — Levels, Source Layers) → **checkboxes**
  (checkable list items).

### Windows & dialogs

- App dialogs are **frameless with a single custom header** styled like the
  footer (glyph + title + context), **Win11 DWM rounded corners**
  (`DWMWA_WINDOW_CORNER_PREFERENCE`), and a **thin light perimeter border**. The
  Underlay Manager / Import Underlay dialogs are the reference. Window controls =
  three circular icons (grey circle + accent inlay: – minimise / + maximise / ×
  close).
- **Panel containerization:** flat **overline sections** (UPPERCASE label +
  content); only *input surfaces* (lists, evidence readouts) get a border — do
  not wrap whole sections/pages in cards.
- **Panel seams:** use an explicit 1px divider **widget** between regions — QSS
  `border` on a `QStackedWidget` is unreliable (the page paints over it).
- **Scrollbars default to OFF** — only appear when content actually overflows.
  Use `ScrollBarAsNeeded` (or size the widget to its content, e.g. the auto-fit
  Levels list). Never `ScrollBarAlwaysOn`. For horizontal strips (PDF filmstrip)
  hide the bar and use **side arrows** shown only when scrollable.

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
