---
status: current
last-verified: 2026-10-06  # LT4 Account: §5 linetype_icon.svg stroke deviation (4-unit butt-cap accent dashes, candidate A); prior 2026-10-02 CS1 Account: §5.1 constraint icon family joins the 40-unit family (guard _CONSTRAINT_ICONS; shapes owned by parametric-constraint-system.md D25); prior 2026-10-01 scene-tools P1 Account: §5.1 Modify/Edit icons in the 40-unit family + Flip/Mirror/Scale grammar + Scale base-ring carve-out; §4.1 white-fill scope; §8 stale 27 px line; prior 2026-09-30 chrome polish: render-size ref de-restated (was stale 54/27), app_glyph_icon stroke deviation; prior 2026-09-19
verified-commit: b9b1094   # feat/lt4-repeat-authoring (linetype_icon.svg); prior 2a22ba9 feat/cs1-constraint-foundation; prior c8ff4f4 feat/scene-tools-p1-batch; prior 416584c   # prior 0a7b44a
applies-to:
  - firepro3d/icons.py
  - firepro3d/svg_utils.py
  - firepro3d/graphics/Ribbon/
source-tasks: "ribbon-overhaul A3 — forge icon style-guide spec; accent-token reversal re-verified during 2026-08-27 floor-workflow task; Architecture-tab icon set authored 2026-08-28 (feat/architecture-tab-icons); underlay_icon.svg authored 2026-08-28 (feat/pdf-import-polish); accent unified onto theme.accent 2026-08-30 (feat/unify-accent-theme-token — ACCENT_BLUE/ACCENT_GREEN retired); underlay_import_icon.svg authored + import icon top layer made solid-accent for legibility 2026-09-01 (feat/import-dialog-redesign); underlay_manager_icon.svg (family-matched Manager icon) + graphics/chevron_{right,down}.svg tree decorations 2026-09-01 (feat/underlay-manager-chrome-match); Blocks-group icons make/insert/block_manager authored 2026-09-05 (feat/block-ribbon-icons — block-system S5; two-token guards in test_icon_theming.py); ellipse_icon.svg + spline_icon.svg node-marker fills flipped #ffffff→none to honour §4.1 (fix/test-fallout-12-reconcile, 2026-09-18); chrome File-group + header-rail icons authored (new/open/save_as/recent_icon.svg) and re-authored from legacy 40mm/#000000 Inkscape files (save/undo/redo_icon.svg) as two-token 48-unit icons 2026-09-19 (feat/mainwindow-chrome — chrome revamp; _CHROME_ICONS two-token + both-theme render guard in test_icon_theming.py); Flip / Mirror / Scale Modify icons (flip_icon.svg new; mirror_icon.svg + scale_icon.svg legacy Inkscape files overwritten) authored and approved at a live-render mockup gate 2026-10-01 (feat/scene-tools-p1-batch — DD11; Flip/Mirror simplified by the user; Scale base-ring carve-out; added to the _MODIFY_ICONS 40-unit two-token + both-theme guard)"
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
- Rendered sizes are owned by `specs/ribbon-bar.md §3.1` (`theme.M.RIBBON_LARGE_ICON` / `RIBBON_SMALL_ICON`) — do not restate them here. *(2026-09-30: this line previously quoted 54/27 px, which had drifted from the code — the Rule A failure it now avoids.)*
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

**Carve-out — white grip fill on 2D-geometry control-point markers.** The 2D-geometry icon family (`line`, `rectangle`, `circle`, `arc`, `polyline`, `polygon`, `ellipse`, `spline`) draws its control-point / node markers as **white-filled accent-ringed dots** — `fill:#ffffff` inside a `stroke:#004CFF` ring — mirroring the CAD grip convention (a white grip with a coloured border). `#ffffff` is therefore an **allowed** literal *for those marker fills only*. It is intentionally non-rethemeing: the accent ring carries the marker in the light theme (where the white fill blends into the light ribbon surface), and the white pops in the dark theme. This is the sole permitted non-sentinel colour, scoped to grip/base-point ring fills on the 40-unit family — the 2D-geo icons and the Modify/Edit icons that joined it (§5.1); the guards `test_geom2d_icons_exist_and_are_two_token_compliant` and `test_modify_icons_40unit_two_token` encode it via `_GEOM2D_ALLOWED_HEX`. Everywhere else (glyph strokes, main fills, all non-geo icons) the two-token rule stands unmodified.

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
- Prefer **stroked glyphs over filled shapes** where both are readable. Stroked glyphs stay crisp at the small-button render size; heavy fills tend to blob.
- **Deviation — `app_glyph_icon.svg`** (header-rail identity glyph, chrome polish 2026-09-30): hexagon outline at `stroke-width="3"` — the mockup-approved identity weight at the `M.HEADER_ICON` render size. Still two-token + 48-unit (guarded in `test_icon_theming._CHROME_ICONS`).
- **Deviation — `linetype_icon.svg`** (Block Editor Linetype toggle, linetypes LT4-11f): the accent dash-dash line is `stroke-width:4` with `stroke-linecap:butt` (the ink frame stays at 2) — user-picked candidate A (2026-10-05): the heavy square-ended dashes read as a dash pattern at the live small-button size. Still two-token + 48-unit (guarded in `test_icon_theming._BLOCK_ICONS`).
- When a fill is needed (e.g. arrowhead, solid dot), use a filled path with `stroke="none"` rather than a filled-and-stroked shape at the same colour (avoids double-draw artefacts at small sizes).

### 5.1 2D-geometry icon family (40-unit legacy canvas, 2026-09-16)

The 2D-geo primitive icons (`line`, `polyline`, `circle`, `rectangle`, `arc`, `ellipse`, `spline`) share a canvas and marker convention distinct from the 48-unit axo set:
- **Canvas:** 40-unit `viewBox` (legacy; match the family, not the 48-unit guide).
- **Main glyph:** the primary sentinel `#1a1a1a` (→ ink), `stroke-width:2.4`. (Legacy line/circle/rect/arc previously used `#ffffff`, which vanished on light backgrounds — fixed to the ink sentinel.)
- **Vertex/endpoint markers:** hollow accent rings with a **white centre** — `fill:#ffffff;stroke:#004cff` (accent), `r=1.8`, `stroke-width:1.6`. The white fill keeps the centre readable in both themes (a `fill:none` hollow ring shows the dark background through on the dark theme, reading as a black centre).
- Every icon in the family uses these exact metrics (polyline is the reference), except the documented carve-out below.

**Modify / Edit icons join the family.** The Edit + Modify group icons (`copy`, `cut`, `paste`, `duplicate`, `delete`, `move`, `rotate`, `offset`, `array`, `explode`, and since 2026-10-01 `scale`, `flip`, `mirror`) use the same 40-unit canvas, ink stroke and white-centred accent rings (guard: `test_icon_theming._MODIFY_ICONS` — 40-unit `viewBox` + two-token-plus-white). Which icons exist and their tool meaning are owned by `scene-tools.md` (D12); this section owns only the drawing grammar:
- **Ink = source, accent = result / motion.** A **dashed** ink source (`stroke-dasharray:2.6 2.6`; Explode's legacy `2 2.4`) means the original is transformed in place or removed (Move, Explode, Scale, Flip); a **solid** ink source means the original is kept (Copy, Array, Offset, Mirror). Exception as-built: Rotate (approved 2026-09-25) keeps a solid source although it rotates in place.
- **Flip / Mirror** (approved 2026-10-01, simplified by the user at the live-render gate): a source triangle and its accent copy reflected across a **thin solid ink reference-line axis** (`stroke-width:1.6`); no rings and no motion arrow. Flip's source is dashed (reflected in place), Mirror's solid (a reflected copy is added). The two differ only in that dash.
- **Scale** (approved 2026-10-01): a dashed small ink square, its accent enlarged copy sharing the base corner, an accent diagonal motion arrow (filled `stroke:none` arrowhead), and one accent base-corner ring.
- **Carve-out — Scale's base ring is `r=2.4`, `stroke-width:1.4`** (not the family `r=1.8` / `1.6`): at the live small-button size in the dark theme the family ring's white centre does not survive, so the base point read as a solid dot. Observation (not yet acted on): the family-wide `r=1.8` rings lose their white centre at that size too (Offset / Rotate / Array) — a candidate follow-up, not a rule change.

**Constraint icons join the family (2026-10-01, CS1).** The Block Editor's parametric-constraint icons (`constraint_<type>_icon.svg` — the Constrain types plus the Inspect icons) sit beside Modify on the same tab and use the same 40-unit canvas, ink stroke and white-centred accent rings; **accent = the relation**. Guard: `test_icon_theming._CONSTRAINT_ICONS` (40-unit `viewBox` + two-token-plus-white, both-theme render without the fallback glyph). The approved per-icon shapes and which icons are wired to buttons are owned by `parametric-constraint-system.md` (D25, §10) — not restated here.

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

No `placeholder_icon.svg` file may appear in the shipped ribbon. Every `themed_icon(name, theme)` call in `ribbon_bar.py` / `main.py` must resolve to a real icon file before a release build. Authoring the approximately 47 currently-placeholder icons is a tracked follow-up outside the scope of this spec. (The File-group placeholders — `new`/`open`/`save_as`/`recent` — are now real, authored during the 2026-09-19 chrome revamp.)

## 8. Verification Checklist

When authoring or reviewing a new ribbon icon, confirm:

- [ ] SVG uses only `#1A1A1A` (primary) and/or `#004CFF` (accent) as colour values — no other hex literals, no 8-digit hex.
- [ ] `viewBox="0 0 48 48"` declared; no geometry closer than 2 units to any edge.
- [ ] `stroke-width="2"`, `stroke-linecap="round"`, `stroke-linejoin="round"` on all stroked paths.
- [ ] Icon renders legibly at the live small-button icon size (`theme.M.RIBBON_SMALL_ICON`, owned by `ribbon-bar.md §3.1`) in **both** themes — test by rendering at that size before merging. *(2026-10-01: this line previously said "27×27 px"; that figure is moot — `RibbonSmallButton` has a fixed height `RIBBON_SMALL_H` smaller than 27 px, so a 27 px icon would be clamped. Thin rings and white centres are the first details to fail at the live size — see the §5.1 Scale carve-out.)*
- [ ] `themed_icon(name, "light")` and `themed_icon(name, "dark")` both return a non-blank icon (no `_missing_icon.svg` fallback in the warning log).
- [ ] `_missing_icon.svg` fallback still displays a recognisable "missing" glyph (regression guard — do not delete or blank that file).
