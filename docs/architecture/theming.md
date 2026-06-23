# Theming & UI Style

`firepro3d/theme.py` is the **single source of truth** for the application's
visual language — colours, widget styling, and the dark/light variants. Every
UI component should derive its colours from this module rather than hard-coding
hex values, so a theme change stays a one-line switch.

## Token system

A theme is an immutable `Theme` dataclass of named colour tokens, grouped by
role:

| Group | Tokens |
|---|---|
| Backgrounds | `bg_base`, `bg_raised`, `bg_sunken`, `bg_tab_inactive`, `bg_tab_selected` |
| Button states | `btn_hover`, `btn_pressed`, `btn_checked`, `btn_checked_border` |
| Borders | `border_strong`, `border_subtle` |
| Text | `text_primary`, `text_secondary`, `text_disabled`, `text_accent` |
| Canvas | `canvas_bg`, `grid_dot` |
| Semantic | `accent_primary`, `status_ok`, `status_warn`, `status_error` |

Two presets are provided — `LIGHT` and `DARK` — and `detect()` picks one by
inspecting the application palette's window lightness:

```python
from firepro3d import theme as th

t = th.detect()                 # DARK or LIGHT
dot_color = QColor(t.grid_dot)  # derive a colour from a token
```

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

The single white-tick SVG works for both variants because the checked fill is
the blue accent in each. Radio buttons are intentionally left untouched (they
stay circular).

## UI conventions

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
