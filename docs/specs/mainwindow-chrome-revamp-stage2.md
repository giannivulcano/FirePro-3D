---
status: current           # built + live-smoked (feat/chrome-revamp-stage2, 2026-09-19)
last-verified: 2026-09-19
verified-commit: 2330ae8
related-contract: extends mainwindow-chrome-revamp.md (Stage One shipped); reconciles ui-design-system.md (tab catalog), project-browser.md, property-panel.md
applies-to:
  - main.py
  - firepro3d/ui_kit.py
  - firepro3d/theme.py
  - firepro3d/ribbon_bar.py
  - firepro3d/header_rail.py
  - firepro3d/footer_rail.py
  - firepro3d/project_browser.py
  - firepro3d/model_browser.py
  - firepro3d/property_manager.py
source-tasks:
  - "user request 2026-09-19: Chrome Revamp Stage 2 — the 'middle' surfaces (browser, canvas tabs, property panel) + tokenization"
  - "folds in (slice): middle-surface files from 'Audit the ENTIRE codebase for non-tokenised chrome' [P1]"
  - "folds in (slice): dock/browser part of 'App-wide typography role sweep' [P3]"
---

# MainWindow Chrome Revamp (Stage Two) — Design Spec

> **Consolidating contract.** One design doc for the second chrome slice: everything *between* the Stage-One header and footer rails. Per-spec bodies (ui-design-system tab catalog, project-browser, property-panel) reconciled **in place** at wrap-up (Account). Stage One (header/footer rails, ribbon restyle, frameless-fullscreen) shipped 2026-09-19 (merge `0a7b44a`); this builds on its token system with **zero new raw chrome hex**.

> **As-built (2026-09-19, live-smoked).** The build grew past the original four-surface scope into a full **three-tone window scheme** (dialed via served mockups): **header + footer rails = `surface2`/`raised`; ribbon + ribbon tabs + browsers + canvas rail + docks = `surface` (body); canvas drawing = `ground`.** Rails/ribbon-wrap/browsers/canvas-wrap paint their tone via **`WA_StyledBackground`** (a QSS `background:` on a plain `QWidget` is a **live-only no-op** without it — offscreen render masks this; `project_qss_unstyled_state_invisible`). Key mechanism deviations, each because the obvious QSS path failed live: (1) **canvas close button** is a custom `QToolButton` (`_CanvasTabBar`/`_TabCloseButton` via `setTabButton`) — the built-in tab close indicator is capped/scaled by the platform style; the dot reuses `frameless_shell._winctl_pixmap` (18px, hover brightens the circle `line_strong`→`faint` like `_WinDot`); (2) **LeftTabs accent side-bar is painted** (`_WestTabBar.paintEvent`) — QSS `border-right` is unreliable on rotated West tabs; (3) **ribbon-tab 2px left inset via layout** — QSS `margin` on a `QTabBar` is ignored; (4) **canvas side rail dividers are explicit `QFrame` vlines** — a `QTabWidget` `border-left` is covered by the first tab. **Dividers (all `line_strong`):** header↔ribbon **2px**, ribbon-tabs↔groups 1px, ribbon↔canvas 1px, footer↔window **2px** (`QStatusBar` border-top), canvas side vlines + tabs↔canvas (pane `border-top`); the canvas `QGraphicsView` `StyledPanel` frame is cleared. **Selected ribbon + canvas tabs** take the accent-soft fill + 1px accent outline + accent bar (per-surface override on the shared `_tab_language_qss` underline base). **Footer mode badge** is an uppercase non-interactive `QToolButton` pill (was a taller `QLabel`) matching ALIGN/HALO. Metrics: `M.LEFT_TAB_W=24`, `LEFT_TAB_INSET=2`, `LEFT_TAB_GAP=2`; canvas tab padding `4px 10px 5px 16px` @ 9pt to match the ribbon tab height (~31px).

## Goal

Bring the three "middle" MainWindow surfaces onto the house visual language established in Stage One: (1) the left **browser dock** gains a new left-edge vertical-tab widget that mirrors the `TopTabs` language; (2) the **canvas view tabs** adopt the `TopTabs` selection language on the existing closable `QTabWidget`; (3) the **property panel** gets tokenized chrome + house overline section headers; plus a **tokenization sweep** of these files so the whole middle is token-driven and hexguard-covered.

## Motivation

Stage One re-shelled the header, footer, and ribbon, but the browser tabs (default West `QTabBar`), canvas tabs (default `QTabBar` + heavy `::pane`), and property panel still carry ad-hoc chrome and a handful of raw-hex leaks (`#ffffff`, `#888888`, `color: grey`, `#cccccc`). This closes the visual gap so the entire window reads as one surface, and pulls the middle-surface files under the chrome hexguard.

## Architecture & Constraints

- **Tokens only.** All chrome colours/spacing/fonts resolve through `theme.py` (`detect()`, `M` metrics, `FONT_*`). Canvas/geometry colours (Display-Manager-owned) are out of scope.
- **Reuse the Stage-One language, don't fork it.** The `TopTabs` accent-underline/hover treatment must have **one styling home** shared by the ribbon (done), the canvas strip, and the new left-tabs widget — not three copies (`feedback_match_working_architecture`, `project_qss_builder_selector_view_class`).
- **Widget-swap only where safe.** The browser tabs are 4 static panels → a widget swap fits. The **canvas** tabs are closable/removable with per-tab close-button hiding, context menus, and 6+ add-sites → **styling language only**, keep the `QTabWidget` (mirrors the Stage-One ribbon Option A; `TopTabs` has no `removeTab`/per-tab close API).
- **Property panel: visual-only.** Restyle `type:"header"` rows to overline typography without touching the flat-dict property protocol, the §3.4 special cases, or multi-select/mixed logic. (A future structural audit is owed — see `project-property-panel-structure-audit` memory.)
- **Widgetization-review rule.** The new left-tabs widget lives in `ui_kit.py` (reusable), per the ui-design-system governance rule.
- **Live-only render class.** Chrome bugs dodge headless (offscreen QPA 72dpi, no fonts); the acceptance gate is live smoke in light+dark. Guards are structural/hex/metrics only.
- **Rule A.** Links to owned facts (theme tokens in `theme.py`; TopTabs contract in `ui-design-system.md`; header X glyph in `frameless_shell._WINCTL_INLAY`); no restated values, no line counts.

## Design Decisions

### DD1 — Browser left-tabs widget (`ui_kit`)
New reusable widget, visual/behavioral twin of `TopTabs` rotated to the left edge:
- Tabs on the **left**, **bottom-to-top** vertical text (matches ribbon `_VLabel`), proper-case labels.
- **~30px strip** (`M.LEFT_TAB_W`, mockup-tuned), **2px accent side-bar** on selected (vertical analogue of the TopTabs underline), muted others, accent-soft hover.
- **Text-only** (no icons; browser icons deferred, mockup-gated).
- Drives a `QStackedWidget` of the 4 browsers; **drop-in API** for `_left_tabs`: `addTab(widget, label)` + `setCurrentWidget(widget)` + QTabWidget-compat subset; `tabSelected(key)` signal.
- **Mechanism (decided):** a **new `LeftTabs(QWidget)` sibling** in `ui_kit.py`, composed like `TopTabs` but rotated — `QHBoxLayout` = `QTabBar(shape=RoundedWest)` (Qt auto-rotates its text bottom-to-top) + a **vertical** `line_strong` divider + `QStackedWidget`. The 2px accent side-bar = `border-right: 2px solid {accent}` on `::tab:selected`. Shares the look via the DD2 fragment (`#leftTabsBar` selector, `edge="right"`). **Rejected:** parameterizing the test-covered `TopTabs` with an orientation flag (higher parity risk to a shipped widget used by the Title Block editor; the left layout differs enough — H-vs-V layout, divider orientation, tab shape, accent edge — that branching would muddy it). Honest reuse happens at the QSS-language layer (DD2), not by destabilizing `TopTabs`.

### DD2 — Canvas view tabs (styling language on existing `QTabWidget`)
- Selected = ink + semibold + **2px accent underline**; muted others; accent-soft hover + 1px accent border + rounded top; **full-bleed `line_strong` divider** under the strip; **drop the `::pane` border**.
- **Keep** closable tabs, per-tab close-button hiding (3D Model/Paper), the "View Range…" context menu, and all add/close wiring.
- **Swap the tab close glyph** to the header-rail X (`frameless_shell._WINCTL_INLAY["close"]` SVG path, token-stroked) → retires `_setup_tab_close_icon()` PNG and the `#ffffff`/`m=4` hardcodes.
- Style overflow scroll arrows (`QTabBar::scroller`) via tokens.
- **Shared-QSS home (decided):** extract `_tab_language_qss(t, selector, *, edge="bottom")` in `theme.py` emitting the *language only* (transparent+muted default, accent-soft hover + 1px accent border + rounded top, ink + 600 + **2px accent bar on `edge`**, faint disabled). All four consumers call it, appending their own metric literals (padding/font/radius): `build_ribbon_qss` (`RibbonBar QTabBar::tab`, edge=bottom), `build_dialog_qss` (`QTabBar#topTabsBar::tab`, edge=bottom), `build_app_qss` canvas (`QTabWidget#centralTabs QTabBar::tab`, edge=bottom — **new `centralTabs` objectName so the rule is scoped and does NOT restyle the out-of-scope hydraulic/radiation report tabs**), and `build_app_qss` left-tabs (`QTabBar#leftTabsBar::tab`, edge=right). This collapses the **two existing copies** (ribbon `theme.py` ~692–714 + dialog ~869–877) plus the two new consumers into one definition. **Parity gate:** ribbon + dialogs must stay pixel-identical (live smoke + existing tests); the fragment reproduces their current colour/state rules, metric literals unchanged.

### DD3 — Property panel overline restyle + tokenization
- Re-skin `type:"header"` rows (incl. §3.4 injected "── Node N ──") to house **Overline** typography (UPPERCASE, muted, letter-spacing, tokens). No protocol/form-structure change.
- Tokenize `color: grey` (×2), `#cccccc` colour-picker fallback.
- **Overline mechanism (decided):** reuse the **existing `QLabel[role="header"]`** overline role (already app-wide in `build_app_qss` ~664, used by `ui_kit.Section` ~272). The header row sets `label.setProperty("role","header")` + uppercased text (drop the `── ──` decoration). **Zero new code, single-homed.** Rejected: a new typography helper (redundant) and boxed `Section` containers (structural — deferred per the `project-property-panel-structure-audit` memory).

### DD4 — Tokenization sweep (middle-surface files only)
- Fix: `project_browser.py` (`#ffffff`, `#888888`), `model_browser.py` (`#ffffff`, `_GREY`), `property_manager.py` (see DD3), `theme.py` dock/tab hardcoded metrics → `M`, `main.py` tab-X (via DD2 reuse).
- Extend `test_theme_chrome_hexguard.py` to the `firepro3d/` middle-surface files + the new widget. `main.py` stays outside (root-level, Stage-One precedent).

### Spec reconciliation map (applied Phase 6 Account)
- `ui-design-system.md` tab catalog — add the **left-tabs** entry; flip "App/plan `QTabBar` … untouched" → restyled to TopTabs language.
- `mainwindow-chrome-revamp.md` — link Stage Two.
- `property-panel.md §3.2` — header-row overline render note.
- `project-browser.md` — note the `_left_tabs` container swap (browser internals unchanged).

## Acceptance Criteria

**Browser**
- [ ] New `ui_kit` left-tabs widget: left-edge bottom-to-top vertical text, ~30px `M.LEFT_TAB_W`, 2px accent side-bar selected, muted/hover states, tokenized.
- [ ] Replaces `_left_tabs`; the 4 browsers switch correctly; `setCurrentWidget(blocks_browser)` (main.py:2278) still works.

**Canvas**
- [ ] Canvas strip uses the TopTabs language (accent underline, muted, accent-soft hover, full-bleed divider, no `::pane` border); overflow arrows tokenized.
- [ ] Closable tabs, per-tab close-button hiding, context menu, add/close wiring all still work.
- [ ] Tab close glyph is the header-rail X (tokenized); `_setup_tab_close_icon()` PNG + `#ffffff`/`m=4` removed.

**Property panel**
- [ ] `header` rows render as house overline; no protocol/§3.4/multi-select regression.
- [ ] `grey`/`#cccccc` tokenized.

**Tokenization**
- [ ] All middle-surface raw hex/named-colour gaps tokenized; hexguard extended to the `firepro3d/` files + new widget; green.

## Verification Checklist
- [ ] All acceptance criteria met.
- [ ] Full suite green (headless); new left-tabs widget test drives the real widget.
- [ ] Live smoke: all 4 surfaces in light + dark (the render gate).
- [ ] No regressions: browser switching, canvas tab close/context menu, property multi-select/mixed + §3.4 special cases.
- [ ] Hexguard + metrics-drift guards extended and green; each shown RED with the fix reverted.
- [ ] Spec reconciliation map applied; `verified-commit`/`last-verified` stamped on each touched spec.

## Edge Cases & Error Handling
- **Browser dock float/redock / narrow width:** fixed strip width holds; vertical text renders regardless.
- **Canvas tab overflow:** many open tabs → tokenized scroll arrows, TopTabs language preserved.
- **Live theme switch:** the new widget reads tokens at construction (latched `detect()`); live restyle is **out of scope**, consistent with the existing deferred live-switch task — restyles on next launch.
- **Property `header` casing:** "── Node 1 ──" becomes "NODE 1" (overline uppercase) — intended.

## Code Style & Testing
PyQt6, Google docstrings, relative imports within `firepro3d/`, tokens via `theme.py`. Tests: pytest `qapp` fixture (no pytest-qt); **drive real widgets**; each guard shown RED with the fix reverted; hexguard + metrics-drift run in-suite. Live smoke is the render gate (offscreen QPA is 72dpi/no fonts).
