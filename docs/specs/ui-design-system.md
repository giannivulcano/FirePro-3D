---
status: partial           # core system BUILT + code-verified; "Deferred waves" section is partly future/unbuilt (wave #2 LANDED 2026-09-19)
last-verified: 2026-09-19  # 2026-09-19: MainWindow re-shell (wave #2) LANDED (merge 0a7b44a) — frameless-fullscreen MainWindow + header/footer rails; governing contract: docs/specs/mainwindow-chrome-revamp.md (status: current). prior: 2026-09-15 TopTabs composed QWidget + SwitchBar expanding=False + multi-rail tab-page recipe; 2026-09-06 core system
verified-commit: 2330ae8   # 2330ae8 (Stage-2 chrome: tab catalog += LeftTabs + canvas-tabs restyle); prior 0a7b44a (MainWindow chrome revamp), 9fe9985 (TopTabs/SwitchBar/Section)
related-contract: docs/specs/mainwindow-chrome-revamp.md  # governs header/footer-rail invariants + frameless MainWindow shell (wave #2)
applies-to:
  - firepro3d/theme.py
  - firepro3d/frameless_shell.py
  - firepro3d/house_dialog.py       # new (this spec)
  - firepro3d/ui_kit.py             # new (this spec)
  - firepro3d/themed_message.py
  - firepro3d/underlay_manager.py
  - firepro3d/underlay_import_dialog.py
  - firepro3d/make_block_dialog.py
  - firepro3d/block_manager.py
source-tasks:
  - "todo_open.md:69 (FramelessShellMixin governing spec — this closes the orphan)"
  - "todo_open.md:265 (chrome hexguard — partial: new files only)"
  - "todo_open.md:68 (global combo font pt — bundled)"
  - "todo_open.md:47 (frameless MainWindow — deferred wave)"
  - "todo_open.md:276 (live theme switch — deferred wave, seam only)"
---

# App-wide UI Design-System (kit + dialog system) — Design Spec

## Goal

Extract a tokenized, reusable UI design-system from the five existing frameless
dialogs, so that (a) one edit to a spacing/metric token reflows every consuming
dialog, (b) new dialogs inherit the house shell/header/footer for free, (c) a
shared **component kit** (side-rail tabs, details panel, sections, switch bar,
toggle, pill) is reusable in dialogs **and** MainWindow docks/panels, and
(d) the 39 native `QMessageBox`/`QInputDialog` calls are replaced with
house-themed equivalents.

## Motivation

The five frameless dialogs (`UnderlayManagerDialog`, `UnderlayImportDialog`,
`MakeBlockDialog`, `ThemedMessageDialog`, `BlockManagerDialog`) already share a
look, but they arrived at it by **copy-paste**: layout magic numbers drift
(body margins `20/18` vs `14/14` vs `14/12`; footer `16/10` vs `14/9` vs `12/8`),
and the QSS is one stylesheet **named after one dialog** (`build_underlay_manager_qss`)
that the others borrow via objectName hacks and `str.replace()` aliasing
(`build_block_manager_qss`). This is the anti-pattern from the
`project_qss_builder_selector_view_class` memory — a view-class swap silently
unstyles a table. There is **no governing spec** for the dialog/shell system;
`frameless_shell.py` is an owed orphan (`todo_open.md:69`). This spec forges the
leash and the system in one pass.

## Architecture & Constraints

- **`theme.py` stays the single source of truth** for the visual *language*.
  Colours (16 primitives → derived semantics) and the **new metrics tokens** and
  typography live there; see `docs/architecture/theming.md`. This spec governs
  the *system contracts* (classes, APIs, scoping) and **links** to theming.md for
  the language (Rule A: one fact, one home — do not restate colour tokens here).
- **Metrics are variant-independent** (a flat `Metrics` namespace `M`, not fields
  on `Theme`) and **semantic-first**: the named tokens are authoritative and
  single-homed; a documented base ramp is a *reference*, not a master multiplier.
- **QSS scoping is by marker + child objectName**, never by dialog objectName.
  Every house dialog sets `houseDialog=True`; one `build_dialog_qss(t)` styles all.
- **`HouseDialog` owns shell + header + footer; the subclass owns the body.** The
  base flexes from a 15-line form dialog to the multi-region import dialog by
  *composition* (call helpers), not overrides.
- **Kit components standardize container/chrome + a thin content API, never domain
  content.** They are widgets, usable anywhere in the app.
- **Pure-parity migration**: the 5 existing dialogs must not change structure,
  behavior, or visible styling. Only invisible ≤2px margin normalization is
  permitted (option C below). New value = only the 39 native boxes become themed.
- **Live chrome bugs dodge headless tests** (`project_live_render_bugs_dodge_headless`,
  `unstyled_qwidget_black_live`): the real look-gate is live smoke on a shown
  widget in both themes, not headless renders (offscreen QPA is 72dpi, no fonts).

## Design Decisions

### D1 — Metrics: canonical-with-honest-splits (option C)

Drift is reconciled by **canonicalizing accidental copy-paste noise** while
**keeping content-driven differences as distinct named tokens**. "Pure parity"
means no structural/behavioral/visible-restyle change; a ≤2px margin snap is
invisible normalization, not a violation. Rejected: (B) preserve-every-value
(encodes the drift, defeats "one value"); (A) flatten-everything (would wrongly
force the two legitimately-different panel widths equal).

### D2 — Semantic-first tokens, ramp as reference (no master multiplier)

The user-visible promise ("edit once, all update") is satisfied by single-homed
semantic tokens; it never required a master density multiplier. Tokens may hold
off-ramp px where parity demands (`HEADER_H=40`, `HEADER_ICON=22`). A density
multiplier is the deferred density-mode extension the flat namespace allows.
Rejected: (A) strict 4px ramp — forces extra off-parity nudges (22→24 icon).

### D3 — `HouseDialog` footer is a helper, not an abstract method

`set_footer_buttons(...)` composes the canonical `QDialogButtonBox`
(**Cancel-left / primary-right**, house rule) so dialogs with unusual footers
(Manager = Close-only + hint; Import = commit sentence) compose rather than fight
an override contract. Body is a `set_body(widget, margin=…)` seam.

### D4 — `SideTabs` is a general vertical tab rail with optional numbering

Extracted from `_StepRow`/`_StepRail` but generalized: a column of exclusive
rows `(key, label, icon?, sub?, step_no?)`. `step_no` set → numbered chip +
`done`/`warn` states (reproduces the import wizard exactly); omitted → a plain
nav rail (serves future master/detail dialogs). Rejected: step-specific-only.

### D5 — `ThemedMessageDialog` subclasses `HouseDialog`; 7 thin helpers

One flexible class (icon variant, custom/danger buttons, optional input
`body_widget`); seven module-level helpers give 1:1 native-parity call sites.
Existing `themed_info`/`themed_confirm` signatures are **preserved** (additive
kwargs only) so the 9 already-migrated sites don't churn.

## Metrics token schema (`theme.py` → `M`)

Base ramp (reference): `xs=4, sm=8, md=12, lg=16, xl=20` (off-ramp values held
raw where parity requires). Margins are `(l,t,r,b)` tuples. Python consumes via
splat: `layout.setContentsMargins(*M.FOOTER_MARGIN)`. QSS consumes via f-string
interpolation in `build_dialog_qss` (`{M.RADIUS_INPUT}` alongside `{t.accent}`).

| Token | Value | Source / reconciliation |
|---|---|---|
| `HEADER_H` | 40 | shared |
| `HEADER_MARGIN` | (14,7,10,7) | shared |
| `HEADER_ICON` / `HEADER_ICON_GAP` / `HEADER_TITLE_GAP` | 22 / 8 / 10 | shared |
| `WINCTL_DOT` / `WINCTL_ICON` | 20 / 18 | `_WinDot` |
| `DIALOG_BODY_MARGIN` | (20,18,20,18) | simple form dialogs (content-driven, kept) |
| `PANEL_PAGE_MARGIN` | (14,14,14,14) | dense panel pages (Manager `14/12`→`14/14`, invisible) |
| `FOOTER_MARGIN` | (14,9,14,9) | **canonical** (MakeBlock `16/10` & Manager `12/8` snap in) |
| `FOOTER_BTN_GAP` | 8 | shared |
| `FOOTER_H` / `FOOTER_SUBRAIL_MARGIN` / `FOOTER_TOGGLE_GAP` / `FOOTER_OSNAP_GAP` | — | MainWindow footer rail (wave #2, LANDED 2026-09-19); values/contract → `docs/specs/mainwindow-chrome-revamp.md` |
| `PANEL_W` / `PANEL_W_WIDE` | 268 / 324 | two tokens (grid vs stacked pages) |
| `TOOLBAR_MARGIN` / `TOOLBAR_GAP` | (12,9,12,9) / 8 | Manager toolbar |
| `SIDE_RAIL_W` / `SIDE_RAIL_MARGIN` / `SIDE_RAIL_ROW_GAP` | 188 / (6,12,6,12) / 4 | Import rail |
| `STEP_ROW_MARGIN` / `STEP_ROW_GAP` / `STEP_CHIP` | (10,6,8,6) / 8 / 16 | Import step rows |
| `SEAM` | 1 | region divider |
| `SECTION_GAP` | 8 | overline → content |
| `RADIUS_INPUT` / `RADIUS_CARD` / `RADIUS_PILL` / `RADIUS_CHIP` | 6 / 7 / 11 / 8 | existing radii |
| `PILL_PADDING` | (3,10) | existing |

Bundled: the `todo_open.md:68` fix — `build_app_qss`'s global `QWidget { font-size:13px }`
becomes a **pt** value (9.75pt == 13px @ 96dpi) to stop the `QFont::setPointSize<=0`
warning on combo popups (`project_qss_pixel_font_pointsize_warning`).

## QSS unification (`build_dialog_qss(t)`)

One builder replaces `build_underlay_manager_qss` + `build_block_manager_qss` +
`_import_extra_qss` (all deleted). Scoping:

- Top-level rules → `QDialog[houseDialog="true"]`.
- Structural chrome keeps existing child objectNames, styled once: `#shellHeader`,
  `#footerBar`, `#dialogBody`, `#detailsPanel`, `#toolbarBar`,
  `QTreeView#underlayTable` **and** `QTableView#underlayTable` (both — replaces the
  `.replace()` mirror so the Block Manager's flat table and the Underlay tree share
  rules).
- Kit rules carry their own objectNames/properties: `#stepRail`, `[stepRow="true"]`,
  `[stepNo="true"]`, `[switch="true"][segpos=…]`, section header, `.pill`, plus the
  reusable card/pill/section bits folded out of `_import_extra_qss`
  (`#scaleCard`, `#srcCard`, `#panelPage`, `#scalePill`, `#dropHint`).
- Dialog `objectName`s are **kept as identity** but no longer referenced by QSS.
- `QTreeView::branch` chevron images stay wired via `asset_path()` (styling
  `::branch` kills native arrows — `project_qtreeview_branch_styling_kills_arrows`).
- Genuinely one-off widget styling (import preview `QGraphicsView` bg) stays a tiny
  local stylesheet deriving colours from tokens (theming.md blesses this).

## Component & class APIs

### `firepro3d/house_dialog.py`

```python
class HouseDialog(FramelessShellMixin, QDialog):
    def __init__(self, parent=None, *, title, icon=None, controls=("close",),
                 resizable=False, min_width=None, theme=None): ...
    def set_header_context(self, text: str | None) -> None      # secondary muted label
    def set_body(self, widget, *, margin=M.DIALOG_BODY_MARGIN) -> None
    def body_layout(self) -> QVBoxLayout                        # pre-margined alt to set_body
    def set_footer_buttons(self, *, primary=None, cancel=True,  # (label, slot)
                           extra_left=None, danger=False) -> dict   # Cancel-left/primary-right
    def restyle(self) -> None                                   # re-apply build_dialog_qss(detect())
```

### `firepro3d/ui_kit.py`

```python
class SideTabs(QFrame):                 # #stepRail — vertical exclusive tab rail
    def add_tab(self, key, label, *, icon=None, sub=None, step_no=None): ...
    def set_current(self, key); def current(self) -> str
    def set_status(self, key, text, state)     # state ∈ {"", "done", "warn"}
    def set_label(self, key, text)             # relabel a tab in place (dynamic rails)
    def set_header(self, widget); def clear()  # header strip / rebuild dynamic rails
    tabSelected = pyqtSignal(str)

class TopTabs(QWidget):                 # #topTabs/#topTabsBar — peer pages in a section
    # COMPOSED (not a QTabWidget subclass — a QTabWidget's ::pane border is
    # unreliable and its bar sizes to the tabs, so its own underline stops short
    # of the content width): QTabBar(#topTabsBar) + full-bleed 1px divider
    # (#topTabsDivider, line_strong) + QStackedWidget(#topTabsStack). Bar muted
    # default, accent-underline + semibold selected, accent-soft hover. Key API
    # mirrors SideTabs; a QTabWidget-COMPAT subset (count/tabText/widget/
    # currentWidget/setCurrentWidget/currentChanged) keeps callers+tests working.
    def __init__(self, *, page_inset=12, page_top=14): ...
    #   page_inset — horizontal inset on the tab BAR only; the STACK is full-bleed
    #                (0 horizontal) so a page that leads with a rail sits flush-
    #                left like the main dialog rail — each page owns its padding.
    #   page_top   — top inset on page content (breathing room below the divider
    #                so Section overline labels don't crowd the tab ribbon).
    def add_tab(self, key, label, widget, *, icon=None) -> int: ...
    def set_current(self, key); def current(self) -> str | None
    tabSelected = pyqtSignal(str)
    # Rail → tabs is the MAX depth — never nest TopTabs.
    # BG: container/rows/stack AND every page are pinned the OPAQUE dialog
    # `surface` via targeted objectName selectors (unstyled QStackedWidget pages
    # paint BLACK live; transparent does NOT fix it — see the black-bar note in
    # the canonical recipe below).

class DetailsPanel(QFrame):             # #detailsPanel — fixed-width bordered side panel
    def __init__(self, *, width=M.PANEL_W, title=None): ...
    def set_title(self, text): ...
    def content_layout(self) -> QVBoxLayout    # PANEL_PAGE_MARGIN

class Section(QWidget):                 # overline UPPERCASE label + content
    def __init__(self, title, content=None): ...
    def set_content(self, widget): ...

class SwitchBar(QWidget):               # segmented single-select (switch/segpos)
    def __init__(self, options: list[tuple], *, expanding=True): ...  # [(key,label),…]
    #   expanding=False → content-fit: every segment = widest label's width, then
    #   a trailing stretch keeps the compact switch left-aligned (use for small
    #   fixed choice-sets: orientation, corner, alignment, sizing). Selected
    #   segment is SOLID accent (:checked). Bind the SAME token as ToggleSwitch.
    def set_current(self, key); def current(self) -> str
    changed = pyqtSignal(str)

class ToggleSwitch(QWidget):            # binary on/off, accent when on, label right (net-new)
    def __init__(self, label, checked=False): ...
    def isChecked(self) -> bool; def setChecked(self, on): ...
    toggled = pyqtSignal(bool)

class Pill(QPushButton):                # compact rounded action button (.pill, RADIUS_PILL)
    def __init__(self, text="", *, icon=None, checkable=False, expanding=False): ...
```

`ToolbarBar` is a **styling hook only** (`#toolbarBar` + QSS), not a widget class.

### `firepro3d/themed_message.py`

```python
class ThemedMessageDialog(HouseDialog):
    def __init__(self, parent, *, title, message=None,
                 icon="info"|"warn"|"error"|None,
                 body_widget=None, buttons=[(label, role, variant)], default=None): ...
    def value(self): ...                # parsed field value (input variants)

# 7 helpers — 1:1 native-parity:
themed_info(parent, title, msg) -> None                 # .information (5)
themed_warn(parent, title, msg) -> None                 # .warning (11)
themed_error(parent, title, msg) -> None                # .critical (3)
themed_confirm(parent, title, msg, *, danger=False,
               ok_label="Yes", cancel_label="No") -> bool   # .question (11) + 3 custom instances
themed_input_text(parent, title, label, *, initial="") -> tuple[str, bool]    # getText
themed_input_number(parent, title, label, *, initial,
                    dimension=True) -> tuple[float, bool]    # getDouble (4)
themed_input_choice(parent, title, label, items, *, current=0) -> tuple[str, bool]  # getItem
```

`themed_input_number(dimension=True)` uses `DimensionEdit` +
`format_length`/`parse_dimension` (`feedback_dimension_input_pattern` — never
`QDoubleSpinBox`); `dimension=False` = validated plain field. The 3 destructive
`QMessageBox()` instances map to `themed_confirm(..., danger=True, ok_label="Delete")`.

## Native-dialog sweep census (39 sites)

`QMessageBox`: `.question` 11 · `.warning` 11 · `.information` 5 · `.critical` 3 ·
instance-with-custom-buttons 3.  `QInputDialog`: `getText` 1 · `getDouble` 4 ·
`getItem` 1 (= 6). `main.py` holds the largest share (11+). Each replaced 1:1 with
matching return semantics; surrounding logic (`if ok:`, `clickedButton() is …`)
rewrites mechanically. **`QFileDialog` (15) and `QColorDialog` (14) stay native.**

## Build phasing & parity gates

| Phase | Work | Gate |
|---|---|---|
| P1 | `M` namespace + font `px→pt` fix | `test_combo_font_warning.py` green; app launches; metrics-resolve test |
| P2 | `build_dialog_qss` (fold 3 builders in), repoint 5 dialogs, delete old builders | 5 dialogs render identically (smoke, both themes); 3 QSS-plumbing tests updated + green |
| P3 | `house_dialog.py` + `ui_kit.py` (no migration) | structural tests (regions, footer order, token reads); kit instantiates |
| P4 | Migrate 5 dialogs (1 commit each; simple → Manager/Block → Import last) | per-dialog parity smoke (both themes) vs pre-migration screenshot; that dialog's tests green |
| P5 | Grow `ThemedMessageDialog` + 7 helpers; replace 39 sites 1:1 | helper return-semantics tests; one live site per shape; full suite green |
| P6 | Spec + guards + theming.md link + SPEC-INDEX | guards green over new files; spec self-review |

Migrations are relocations (`feedback_relocation_smoke_preexisting`): parity-green +
smoke proves the move. Pre-existing full-suite failures verified on `main` first
(`feedback_pytest_pipe_masks_exitcode`: redirect to file + check exit code, never `| tail`).

## Governance — widgetization-review rule

**Before building a new UI component inline, review whether it belongs in
`ui_kit.py`.** Promote if it's container/chrome with plausible reuse; keep inline
only if genuinely one-off. Mirrors the `/todo` reuse-sweep. (Also saved as a
feedback memory.)

## Tab-style catalog (documented; scope-flagged)

- **Side-rail** — `SideTabs` (`ui_kit.py`); **widgetized**. Table of contents / stepped sequence / 4+ sections.
- **Top tabs (dialogs)** — `TopTabs` (`ui_kit.py`, `#topTabs`/`#topTabsBar`); **widgetized 2026-09-15** (first adopter: Title Block editor). Peer pages inside one section (2–5 flat pages). Accent-underline selected, accent-soft hover, no base line, scroll-on-overflow. **Hover carries the button-style green highlight (2026-09-19, wave #2 chrome revamp): accent_soft fill + 1px `accent` border + rounded top; the base tab reserves a 1px transparent border so the hover border adds no layout shift.** **Composed** (QTabBar + full-bleed `#topTabsDivider` + QStackedWidget), NOT a `QTabWidget` subclass — a QTabWidget's `::pane` line is unreliable and its bar underline stops short of the content width. The **tab bar** is inset by `page_inset`; the **stack is full-bleed** so a page that leads with a rail sits flush-left (each page owns its padding); `page_top` keeps Section overlines off the ribbon. **Rail → tabs is the max depth; never nest tabs-in-tabs** (a page needing sub-nav uses collapsible groups). New house dialogs with top tabs use `TopTabs`, not a bare `QTabWidget`.
- **Left tabs (west/vertical)** — `LeftTabs` (`ui_kit.py`, `#leftTabsBar`); **widgetized 2026-09-19 (Stage-2 chrome revamp)**. `TopTabs` rotated to the West edge for the MainWindow browser dock (Project/Model/Features/Blocks). `QTabBar(RoundedWest)` (bottom-to-top labels, matching the ribbon `_VLabel`) + vertical `line_strong` divider + `QStackedWidget`; shares the state colours via `theme._tab_language_qss(edge="right")`. Selected = accent-soft fill + 1px accent outline + a **painted** 2px accent side-bar (`_WestTabBar.paintEvent` — QSS `border-right` is unreliable on rotated tabs). Same key-/QTabWidget-compat API as `TopTabs`. Governed by `mainwindow-chrome-revamp-stage2.md`.
- **App/plan `QTabBar` (canvas view tabs)** — `build_app_qss` `QTabWidget#centralTabs`; **restyled to the TopTabs language 2026-09-19 (Stage-2)**: shares `_tab_language_qss(edge="bottom")`; selected = accent-soft fill + border + underline; custom header-style close dot (`main._CanvasTabBar`); `surface` strip; flanking `QFrame` rail dividers. Governed by `mainwindow-chrome-revamp-stage2.md`.
- **Ribbon tabs** — `build_ribbon_qss` (tab-scoped shortcut semantics); adopted the TopTabs language in the Stage-1 revamp; **Stage-2 (2026-09-19)** added the selected accent-soft fill + border (matching canvas/left tabs) and a 2px left inset. Governed by `mainwindow-chrome-revamp.md` / `-stage2.md`.

## Multi-section dialog layout (canonical recipe)

Any dialog with multiple sections (settings, wizards, managers) uses the **side-rail
+ content-panel** composition — the Underlay Import dialog and the Settings dialogs
(`settings/system_settings_dialog.py`, `settings/project_settings_dialog.py`) are the
reference implementations. The recipe (get all four right or the rail reads as a black
bar / merges with the content):

1. **Shell:** subclass `HouseDialog`; pass a header **`icon="<name>_icon.svg"`** (SVG
   filename — rendered via `themed_icon`) so the title has its glyph, and
   `controls=("min","max","close")` + `resizable=True` for a maximize affordance.
2. **Body:** `set_body(container, margin=(0, 0, 0, 0))` so the rail sits **flush** to the
   dialog edge (no inset).
3. **Layout:** a `QHBoxLayout` with `setContentsMargins(0,0,0,0)` **and `setSpacing(0)`** —
   the zero spacing is load-bearing: a non-zero gap exposes the unstyled body behind the
   rail as a black bar. Left = `SideTabs` (rail, `#stepRail`, `surface` + `border-right`
   in `line_strong` — the **single canonical rail/content separator token**); right = the
   content `QStackedWidget(objectName="railContent")` (`surface`, **no** border of its own,
   so the seam is one 1px line, not a doubled 2px one).
4. **Content background:** the rail-adjacent content stack **must** carry a themed
   objectName — `railContent` (rail-adjacent, no left border) or `detailsPanel` (when a
   column sits between it and the rail, e.g. Underlay Import's preview). A bare
   `QStackedWidget()` — and equally a bare `QStackedWidget`/`QWidget` **page inside
   `TopTabs`** — paints the default (black) brush live (transparent only offscreen), the
   #1 recurring defect for this layout. `TopTabs` pins its container/rows/stack and every
   page the OPAQUE `surface` via targeted objectName selectors; **transparent does NOT
   fix it — the bg must be opaque** (`project_unstyled_qwidget_black_live`). ⚠ **Open
   defect (todo):** even opaque-surface pinning left the Title Block editor pages black
   live in one report — leading hypothesis is that a stylesheet `background:` is ignored
   on a *plain* `QWidget` without `WA_StyledBackground`; verify at the paint seam in the
   running app before trusting either route.
5. **Sequential vs not:** use `add_tab(key, label, step_no=N)` for wizards (numbered
   chips); plain `add_tab(key, label)` for non-sequential sections (settings).
6. Binary on/off controls inside the panes use **`ToggleSwitch`**, never `QCheckBox`
   (theming.md binary-toggle mandate).

### Multi-rail tab pages (Title Block editor pattern, 2026-09-15)

A `TopTabs` page that is itself a **multi-column workspace** (roster | form | preview)
follows these rules so every column reads as a proper rail:

1. **Sections, never `QGroupBox`.** Group a page's controls with `Section` (uppercase
   overline `role="header"` label, **no box**), not a titled `QGroupBox`. Left-align the
   form labels (`AlignLeft`) and cap input widths (they needn't be full-bleed).
2. **Dynamic roster → `SideTabs` rail**, not a `QListWidget`. A page's item roster
   (fields, layers, …) uses `SideTabs` keyed by a stable id, with `+/−/⧉` action buttons
   in `set_header(...)` — the SAME chrome as the dialog's main rail (extract one helper).
   Its manual-drag variant (e.g. the arrangements pool) stays a `QListWidget` but is
   **restyled to the rail look** via a targeted `#…Rail` stylesheet (surface field,
   accent-soft hover, `accent` left-bar on `:selected`) so the drag machinery survives.
3. **Full-height rail dividers.** A rail's `border-right` (or a column divider) must span
   the whole column height. Two gotchas: (a) give the rail **Expanding vertical** size
   policy — `Preferred` stops at the rows' content height; (b) `Section` adds its content
   **without a stretch factor**, so a list inside a Section needs an explicit
   `layout().setStretchFactor(list, 1)` or it stops short.
4. **Column dividers use one tokenized `_vrule()`** — a 1px `QFrame`, `line_strong`,
   Expanding-vertical — between the info/form rail and the preview rail (matches the rail
   `border-right`). Same token as the canonical rail separator.
5. **Full-bleed stack → per-page padding.** Because the `TopTabs` stack is full-bleed, a
   page that leads with a rail sets its own `contentsMargins` (small left gap for the
   rail, right padding for the content) so the rail sits near the left edge like the main
   dialog rail — not double-inset. Roster rails get a tighter internal top margin than the
   default (they're nested one level deeper than the main rail).
6. **Small fixed choice-sets → `SwitchBar(expanding=False)`** (orientation, corner,
   alignment, sizing): content-fit segments, selected segment SOLID accent. Larger/open
   sets stay a `QComboBox`.

## Acceptance Criteria

- [ ] One edit to a metrics token reflows every consuming dialog; no house
      dialog (kit + `HouseDialog` + 5 migrated) contains a raw layout literal in
      `setContentsMargins/setFixedHeight/setFixedWidth/setSpacing`.
- [ ] `build_dialog_qss(t)` is the sole dialog stylesheet; the 3 old builders are
      deleted; scoping is `houseDialog` marker + child objectNames.
- [ ] All 5 frameless dialogs look/behave identically pre/post (live smoke, both
      themes); only ≤2px invisible margin normalization changed.
- [ ] All 39 native `QMessageBox`/`QInputDialog` sites replaced 1:1 with matching
      return semantics; now house-themed. `QFileDialog`/`QColorDialog` untouched.
- [ ] `ToggleSwitch` implements the theming.md binary-toggle mandate.
- [ ] `theming.md` documents the metrics vocabulary and links here; SPEC-INDEX row
      added; `frameless_shell.py` orphan closed.
- [ ] Testing gate met (below).

## Verification Checklist

- [ ] All acceptance criteria met.
- [ ] `test_theme_chrome_hexguard.py` extended to new kit + 5 migrated dialog files (green).
- [ ] `ThemedMessageDialog` return-semantics unit tests per shape (bool / (value, ok)).
- [ ] Structural tests: `#shellHeader`/`#dialogBody`/`#footerBar` present; footer
      **Cancel-left/primary-right by position**; a metrics token resolves + a dialog
      reads it (not a literal).
- [ ] Light metrics-drift guard (allow-listed) green.
- [ ] Live smoke: 5 dialogs both themes + one swept site per shape.
- [ ] No regressions: all existing dialog tests green except the 3 QSS-plumbing
      tests (updated to the unified builder).
- [ ] Not gating on pixel-DPI (offscreen QPA is 72dpi).

## Deferred waves (recorded so the leash covers the whole system)

1. **20 native-title-bar dialogs → `HouseDialog`** conversion waves. **Migrated
   2026-09-15 (title-block bundle Task D): `TitleBlockEditorDialog` +
   `RevisionsDialog`** (both wrap existing content into `set_body`; the editor
   keeps its 3-button `Save / Save && Close / Close` box in-body). Remaining:
   `PreferencesDialog`, `DisplayManager`,
   `AutoPopulateDialog`, `SprinklerManagerDialog`, `RoofDialog`, `WallDialog`,
   `PaperExportDialog`, `ArrayDialog`, `CalibrateDialog`, `LevelDialog`,
   `ViewRangeDialog`, `ThermalRadiationDialog`, `DesignPointDialog`,
   `FSVisibilityDialog`, `SectionPatternDialog`, `SheetViewPropertiesDialog`,
   `_RecordEditDialog`, `AlgorithmParamsDialog`.
2. **MainWindow re-shell** + custom header/footer rails + frameless-fullscreen —
   **LANDED 2026-09-19 (merge `0a7b44a`).** `MainWindow(FramelessShellMixin,
   QMainWindow)` is now frameless-fullscreen by default (taskbar hidden); the
   mixin gained a `window_type` param (Dialog default, Window for the shell),
   startup fullscreen applied in `main()`, `ui/immersive`→`ui/fullscreen` pref
   migration; custom `header_rail.py` (via `setMenuWidget`, stacked above the
   ribbon) + `footer_rail.py` (3 sub-rails, replaces the status bar) drive the
   chrome. Full header/footer-rail invariants + the frameless-MainWindow contract
   → **`docs/specs/mainwindow-chrome-revamp.md` (status: current)** — the
   governing spec for this wave (this spec links, does not restate).
3. **Live-theme-switch-while-open** wiring (`todo_open.md:276`) — the `restyle()`
   seam exists; wiring `MainWindow._apply_theme` to walk open dialogs is deferred.
4. **Full-app chrome-hexguard extension** (`todo_open.md:265`) — this task adds only
   the new/migrated files.
5. **Density-mode multiplier** — future extension the flat metrics namespace allows.

## Existing Code Context (current behavior, code-verified @ a91e35b)

- `theme.py`: two-layer colour tokens; `build_app_qss`, `build_ribbon_qss`,
  `build_underlay_manager_qss` (+ `_UNDERLAY_MANAGER_QSS` template + `_UM_QSS_TOKENS`),
  `build_block_manager_qss` (aliases via `.replace`); `FONT_UI`/`FONT_VALUE`; `detect()`.
- `frameless_shell.py`: `FramelessShellMixin` (`init_frameless_shell`, `_build_titlebar`
  → `#shellHeader` h40 m(14,7,10,7), `_WinDot`, drag/resize, DWM corners).
- The 5 dialogs' current structure (regions, magic numbers) is captured in the P2
  grill review; see `source-tasks`.

## Out of scope

20 native-dialog conversions; MainWindow re-shell + fullscreen + mixin `window_type`;
live-switch wiring; `QFileDialog`/`QColorDialog`; density modes; top-`QTabBar`/ribbon
restyle; full-app hexguard; canvas/entity colours (`display_manager`-owned).
