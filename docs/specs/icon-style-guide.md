---
status: current
last-verified: 2026-09-01
verified-commit: cfcb6d6
applies-to:
  - firepro3d/icons.py
  - firepro3d/svg_utils.py
  - firepro3d/graphics/Ribbon/
source-tasks: "ribbon-overhaul A3 — forge icon style-guide spec; accent-token reversal re-verified during 2026-08-27 floor-workflow task; Architecture-tab icon set authored 2026-08-28 (feat/architecture-tab-icons); underlay_icon.svg authored 2026-08-28 (feat/pdf-import-polish); accent unified onto theme.accent 2026-08-30 (feat/unify-accent-theme-token — ACCENT_BLUE/ACCENT_GREEN retired); underlay_import_icon.svg authored + import icon top layer made solid-accent for legibility 2026-09-01 (feat/import-dialog-redesign); underlay_manager_icon.svg (family-matched Manager icon) + graphics/chevron_{right,down}.svg tree decorations 2026-09-01 (feat/underlay-manager-chrome-match)"
---

# Ribbon Icon Style Guide — Governing Spec

**Date forged:** 2026-08-22 (Phase 1b orphan gate — spec forged on first touch during ribbon-overhaul)
**Adjacent docs:** `specs/ribbon-bar.md` (button sizes and layout — owns those facts), `architecture/theming.md` (QSS / theme tokens)

## 1. Goal / Scope

This spec governs every SVG icon file under `firepro3d/graphics/Ribbon/` and the code that loads and recolours them at runtime (`firepro3d/icons.py`, `firepro3d/svg_utils.py`).

It defines the authoring contract that keeps icons theme-neutral at rest and theme-correct at render time, without any per-icon theme knowledge baked into the SVG files.

Out of scope: SNAP toolbar icon conventions (owned by `specs/snap-toolbar.md §7`), QSS colour tokens (owned by `architecture/theming.md`), ribbon button sizes and layout (owned by `specs/ribbon-bar.md §3.1`).

## 2. Directory & Naming

- All ribbon icons live in `firepro3d/graphics/Ribbon/`.
- File names follow the pattern `{noun}_icon.svg` — lowercase, underscores, no spaces (e.g. `pipe_icon.svg`, `sprinkler_icon.svg`).
- One glyph per file. Composite icons are composed by the button layout, not by SVG nesting.
- Names beginning with `_` are **reserved for system assets** (e.g. `_missing_icon.svg` — the fallback glyph). Do not create user-facing icons with a leading underscore.
- `underlay_manager_icon.svg` (accent-top stacked-layers) is the family-matched
  sibling of `underlay_import_icon.svg` — both are ribbon icons under this
  contract.

> **Exception — UI-decoration SVGs are NOT two-token ribbon icons.** SVGs that
> live **outside** `firepro3d/graphics/Ribbon/` are ordinary chrome assets, not
> governed by §4's two-token rule. The tree expand/collapse chevrons
> (`graphics/chevron_right.svg`, `graphics/chevron_down.svg`, neutral grey, used
> as QSS `::branch` images by the Underlay Manager tree) are the current example:
> they are painted directly as authored and are never run through
> `icons.token_map()`. Only files under `graphics/Ribbon/` must obey the
> two-token contract.

## 3. Canvas

- Every icon uses `viewBox="0 0 48 48"` — all geometry coordinates are authored in this 48-unit space.
- Rendered sizes: **54×54 px** (large `RibbonButton`) and **27×27 px** (small `RibbonSmallButton`). These are owned by `specs/ribbon-bar.md §3.1` — do not restate them here.
- Avoid geometry within 2 units of the canvas edge so strokes are not clipped at small render sizes.

## 4. Two-Token Colour Rule (the Core Contract)

### 4.1 Authoring rule

Every colour value in an SVG icon **MUST** be exactly one of two authoring sentinels:

| Role | Sentinel hex | When to use |
|---|---|---|
| Primary | `#1A1A1A` | Main glyph strokes and fills — the "ink" colour |
| Accent | `#004CFF` | Highlights, state indicators, secondary call-outs |

`fill:none` and `stroke:none` are allowed and survive recolouring untouched. Any other literal hex colour value (e.g. `#FF0000`, `#888888`) is **forbidden** — it will not retheme and will produce a visual defect in one or both themes.

8-digit hex values (e.g. `#1A1A1A80`) are ignored by the substitution engine (see §4.3) and therefore also forbidden.

### 4.2 Per-theme token table

The loader substitutes sentinels with theme values at load time. `icons.token_map()`
builds the mapping; primary derives from the fixed ink table in `icons.py`
(`_PRIMARY`), and **accent derives from the active theme variant's `accent`
token** — `theme.py` is the single source of truth for the accent colour:

| Token role | Sentinel (authored in SVG) | Light theme | Dark theme |
|---|---|---|---|
| Primary | `#1A1A1A` | `#1A1A1A` (black) | `#F0F0F0` (white) |
| Accent | `#004CFF` | `theme.LIGHT.accent` (`#2f9e63` green) | `theme.DARK.accent` (`#63BE8B` sage) |

Accent convention: **the accent display value is the active theme's `accent`
token — one accent everywhere.** `icons.token_map()` reads `theme.LIGHT.accent` /
`theme.DARK.accent`; there are no standalone accent constants in `icons.py`
(`ACCENT_BLUE`/`ACCENT_GREEN` were retired). The same `theme.accent` drives the
SNAP/ALIGN status-bar pills, the SNAP toolbar checked border, and the mode badge
in `main.py` (each reads `theme.detect().accent`), plus ribbon-button selection
and grip/selection rendering. The authoring sentinel stays `#004CFF` — SVGs are
always authored with the blue sentinel regardless of the per-theme display value.

To change the accent, edit `theme.py` (the variant's `accent`). To change the
primary ink, edit `icons.py` `_PRIMARY`. SVG geometry is never touched for
retheming — that is the purpose of this contract.

### 4.3 Substitution mechanics

Recolouring is performed by `svg_utils.svg_recolor(svg_text, color_map)`:

- Matches 6-digit hex values (`#RRGGBB`) only — 8-digit (`#RRGGBBAA`) and `none` are skipped.
- Case-insensitive on the source hex (both `#1a1a1a` and `#1A1A1A` are matched).
- Returns UTF-8 bytes ready for `QSvgRenderer`.

## 5. Stroke Conventions

- Stroke width: **2 px at the 48-unit canvas** (i.e. `stroke-width="2"`).
- Caps and joins: `stroke-linecap="round"` and `stroke-linejoin="round"`.
- Prefer **stroked glyphs over filled shapes** where both are readable. Stroked glyphs stay crisp at the 27×27 small-button render size; heavy fills tend to blob.
- When a fill is needed (e.g. arrowhead, solid dot), use a filled path with `stroke="none"` rather than a filled-and-stroked shape at the same colour (avoids double-draw artefacts at small sizes).

## 6. Loader Contract

The sole runtime entry point is `icons.themed_icon(name, theme)` in `firepro3d/icons.py`. Callers must not load, recolour, or render SVG files directly.

Behaviour:

| Scenario | Outcome |
|---|---|
| `firepro3d/graphics/Ribbon/{name}` exists | Loaded, recoloured with `token_map(theme)`, rendered, cached |
| File not found | `_missing_icon.svg` fallback rendered (never a blank/null icon); one `logging.warning` emitted (once per missing name per session) |
| Same `(name, theme)` requested again | Returned from `_cache` — no re-read or re-render |

Theme constants: `icons.LIGHT = "light"`, `icons.DARK = "dark"`. The theme is resolved once at ribbon-build time; **runtime theme switching is not currently supported** (the cache is process-lifetime and `icons.py` exposes no cache-invalidation API).

## 7. Coverage Mandate

No `placeholder_icon.svg` file may appear in the shipped ribbon. Every `themed_icon(name, theme)` call in `ribbon_bar.py` / `main.py` must resolve to a real icon file before a release build. Authoring the approximately 47 currently-placeholder icons is a tracked follow-up outside the scope of this spec.

## 8. Verification Checklist

When authoring or reviewing a new ribbon icon, confirm:

- [ ] SVG uses only `#1A1A1A` (primary) and/or `#004CFF` (accent) as colour values — no other hex literals, no 8-digit hex.
- [ ] `viewBox="0 0 48 48"` declared; no geometry closer than 2 units to any edge.
- [ ] `stroke-width="2"`, `stroke-linecap="round"`, `stroke-linejoin="round"` on all stroked paths.
- [ ] Icon renders legibly at 27×27 px (small button size) — test by rendering at that size before merging.
- [ ] `themed_icon(name, "light")` and `themed_icon(name, "dark")` both return a non-blank icon (no `_missing_icon.svg` fallback in the warning log).
- [ ] `_missing_icon.svg` fallback still displays a recognisable "missing" glyph (regression guard — do not delete or blank that file).
