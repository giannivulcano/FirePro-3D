---
status: current          # built + code-verified 2026-09-14 (branch feat/settings-dialog)
last-verified: 2026-09-23
verified-commit: 434066c
applies-to:
  - firepro3d/settings/panes.py                    # new (this spec) — SettingsPane base + 6 panes
  - firepro3d/settings/project_settings_dialog.py  # new (this spec)
  - firepro3d/settings/system_settings_dialog.py   # new (this spec)
  - firepro3d/settings/template.py                 # new (this spec) — .fpdt lifecycle
  - firepro3d/preferences_dialog.py                # retired → thin re-export shim or hard-cut
  - firepro3d/main.py                              # ribbon buttons, startup/new-project wiring, override removal
  - firepro3d/scene_io.py                          # template = blank-project .fpd; clone/save-as-default
  - firepro3d/scale_manager.py                     # units source-of-truth (project-scoped)
  - firepro3d/app_data.py                          # AppData template path resolution
source-tasks:
  - "todo_open.md (Forge a governing spec for the Preferences dialog — this closes the orphan)"
  - "todo_open.md (Consolidate scattered/legacy settings dialogs into the one Settings dialog)"
  - "todo_open.md (Preferences UX-pane reorg — Snapping→UX; SNAP/ALIGN/HALO tabs)"
  - "todo_open.md (Normalize legacy snap dialog QSettings + retire Manage 'Snap Settings' button)"
  - "todo_open.md (Restore radiation dock + GeneralPane wiring — partial)"
  - "docs/specs/mainwindow-chrome-revamp.md (chrome revamp, merge 0a7b44a, 2026-09-19) — retired the ribbon Snap group; footer SNAP-pill now opens System Settings on the UX pane"
related-contract: docs/specs/mainwindow-chrome-revamp.md   # footer rail / InlineOsnapBar contract; SystemSettings entry-point change
---

# Settings Dialog — Design Spec

**Date:** 2026-09-14
**Complexity:** Large
**Status:** proposal (grill + brainstorm complete; not yet built)

> **Rename note:** The product feature "Preferences" is renamed "Settings" and split into **two** dialogs — **Project Settings** (project-scoped) and **System Settings** (app-wide). This spec is the governing home for the subsystem and **replaces the SPEC-INDEX orphan row** for `preferences_dialog.py` (previously governed only by `ribbon-bar.md §3.4` + the dated `docs/superpowers/specs/2026-08-22-ribbon-overhaul-design.md §3`).

> **See also:** `mainwindow-chrome-revamp.md` (status: current) — owns the footer rail / `InlineOsnapBar` contract and, at merge 0a7b44a (2026-09-19), deleted the ribbon Snap group and added the footer SNAP-pill entry point into System Settings' UX pane (§4.4/§4.6).

---

## 1. Goal

Replace the single flat-tab `PreferencesDialog` with two house-styled Settings dialogs split by **persistence domain**:

- **Project Settings** — settings that belong to the open project and travel in its `.fpd` (Project Info, Units & Precision).
- **System Settings** — app-wide machine preferences in QSettings (General, UX, UI, Import).

Consolidate the scattered/legacy snap dialogs into the UX pane, introduce a minimal AppData `.fpdt` template that seeds new-project defaults, and build both dialogs token-clean on `HouseDialog`.

## 2. Motivation

- **`preferences_dialog.py` is a SPEC-INDEX orphan** — no governing spec. This forges it (orphan-gate prerequisite).
- **Two persistence domains are conflated.** Units are app-wide QSettings today, but conceptually belong to a project (open a metric project, get metric). Project Info already lives in `.fpd`. Splitting the dialogs makes the domain boundary explicit and correct.
- **Parallel snap-settings systems.** Two inline `main.py` dialogs (`_open_snap_tolerance_dialog`, `_open_snap_settings`) duplicate the Snapping pane — the exact "which-owns-this" bug magnet the todo list flags. One home.
- **Chrome drift.** The current dialog is a bare `QDialog` outside the house design-system; both new dialogs adopt `HouseDialog` + tokens.
- **New-project defaults** have no user-controllable source once units go project-scoped; a minimal `.fpdt` template supplies them and forward-fits the deferred User-Profile/template subsystem.

## 3. Existing Code Context (as-is, pre-build)

- `preferences_dialog.py` (~1248 lines): plain `QDialog` + flat `QTabWidget`, six `SettingsPane` subclasses — `SnappingPane` (SNAP/Grid+Angle/ALIGN inner tabs), `UnitsPane`, `ImportPane`, `GeneralPane`, `UIPane`, `ProjectInfoPane`. Pane protocol: `load()` snapshots + populates; `apply()` writes to live objects **and** QSettings; `revert()` restores the snapshot. Opened via `MainWindow._open_preferences`, Manage→Settings group, `info_icon.svg`.
- **ScaleManager** (`scale_manager.py`): **one instance per project**, owned by `Model_Space` (`model_space.py:186`), reconstructed on new/clear (`scene_io.py:575`) and load (`scene_io.py:236` via `ScaleManager.from_dict`, else fresh). **Already serialized** into `.fpd` at `scene_io.py:139` (`"scale"`) alongside `"project_info"` (`:140`). Formatters (`format_length`/`parse_dimension`/…) are read fresh per call by ~90 consumers — **no caching**.
- **Units behave app-wide only because** `main.py:_apply_persistent_unit_prefs()` (~867) **overrides** the project's loaded units from QSettings (`display/unit`,`display/precision`) after every startup/open/new; ribbon quick-menus `_set_display_unit` (~2555) and `_set_precision` (~4333) also write those QSettings keys.
- **Legacy snap dialogs:** `_open_snap_tolerance_dialog` (~2353; SNAP + partial ALIGN + partial HALO; **bare `QSettings()` at ~2443** for `align/enabled`), `_open_snap_settings` (~2306; grid spacing + angle). Wired to the Manage "Snap Settings" button (~1550) and "Angle Snap" menu (~1545). The live **OSNAP toolbar** toggles (`_SnapToolbar`) are a separate, kept system sharing the `snap/*` keys.
- **App is single-window / single-project** (no MDI). No multi-project ScaleManager dispatch needed.
- **House kit** (`ui_kit.py`): `SideTabs` (vertical exclusive rail + status, used by `underlay_import_dialog.py`) and `SwitchBar` (segmented control) + `HouseDialog` (header/body/footer + `build_dialog_qss` tokens; **no built-in tab support**).

## 4. Architecture & Constraints

### 4.1 Module layout — new `settings/` package
- `settings/panes.py` — `SettingsPane` base (the `load()/apply()/revert()` protocol, reused verbatim) + the six panes. `SnappingPane` → **`UXPane`** (its inner sections become a `SwitchBar`). Pane *content* is reused as-is except UXPane reorg (§4.4) and UnitsPane persistence rewire (§4.3).
- `settings/project_settings_dialog.py` — `ProjectSettingsDialog(HouseDialog)`.
- `settings/system_settings_dialog.py` — `SystemSettingsDialog(HouseDialog)`.
- `settings/template.py` — `.fpdt` lifecycle helpers (§4.5).
- `preferences_dialog.py` — retired. Grep all `preferences_dialog` / `PreferencesDialog` importers first; keep a **thin re-export shim same-commit** if any external caller exists, else hard-cut.

### 4.2 Dialog composition (house nav, not raw `QTabWidget`)
Each dialog = `HouseDialog` whose `body_layout()` holds **`SideTabs` rail + `QStackedWidget`** (one page per pane) — the `underlay_import_dialog.py` pattern (`SideTabs.tabSelected → stack.setCurrentIndex`).
- **ProjectSettingsDialog** rail: `Project Info` · `Units & Precision`. Footer via `set_footer_buttons`: OK/Apply/Cancel + **"Save as default for new projects"** in the `extra_left` slot.
- **SystemSettingsDialog** rail: `General` · `UX` · `UI` · `Import`. Footer: OK/Apply/Cancel. Exposes **`select_pane(key)`** — highlights the rail row and switches the stacked body to the named pane (e.g. `"ux"`); no-op for an unknown key. Used by the footer SNAP-pill entry point (§4.4/§4.6) to open directly on the snap-bearing UX pane.
- The **UX** page uses a **`SwitchBar`** (SNAP/ALIGN/HALO) over an inner `QStackedWidget` — no nested vertical rail.
- Both register in `test_theme_chrome_hexguard.py`'s allow-list; no raw hex/stylesheet chrome.

### 4.3 Persistence domains
- **Project Settings → `.fpd`.** Units via the already-serialized `ScaleManager.to_dict`/`from_dict`; Project Info via the existing `project_info` payload. `apply()` mutates the in-memory project (`scene.scale_manager`, project_info) and **marks the project dirty** (via a `set_units`/`set_info` callback, mirroring `ProjectInfoPane`), then refreshes (`_refresh_all_labels`). Serialized on the next project **Save**. **Not** on the undo stack. **Cancel** reverts via the existing snapshot protocol.
- **System Settings → QSettings** (`QSettings("GV","FirePro3D")`). Existing keys unchanged — `snap/*`, `align/*`, `halo/*`, `ui/*`, `import/*`, `dwg/*`, `dock/*`. **No key renames.**
- **Units source-of-truth becomes the project.** Remove `_apply_persistent_unit_prefs()` and its calls; the template clone (§4.5) replaces its "seed new/blank project" role. Ribbon quick-menus (`_set_display_unit`,`_set_precision`) **repoint** to mutate `scene.scale_manager` + mark dirty + refresh, **dropping their QSettings writes**. The `display/*` QSettings keys become **vestigial** — read once for the first-run template seed (§4.5), no live writers remain.

### 4.4 UX pane consolidation + OSNAP parity
- **SNAP** sub-tab: tolerance / hysteresis / grip radius + 8 snap-type toggles + **angle-snap moved in** (own container, default 5°). **Dead grid-spacing removed.**
- **ALIGN** sub-tab: the `align/*` knobs (enabled, path aperture, dwell, max points, 4 direction flags).
- **HALO** sub-tab: `halo/enabled` + `halo/aperture_px` **only** (migrate the interim tab as-is; richer HALO is separate deferred todos).
- Writes the **same keys** the retired dialogs did (behavior parity). `apply()`/`revert()` call **`snap_toolbar.refresh_from_engine()`** so the live snap bar and the pane stay in sync through the shared `snap/*` keys. Post chrome-revamp (merge 0a7b44a) the `snap_toolbar=` constructor arg is passed the footer's **`InlineOsnapBar`** (`firepro3d/footer_rail.py`), which satisfies the same `refresh_from_engine()` contract the retired `_SnapToolbar` did.
- **Retire:** delete `_open_snap_tolerance_dialog` + `_open_snap_settings`; remove the Manage "Snap Settings" button; repoint or remove "Angle Snap". The bare `QSettings()` at ~2443 vanishes with the deletion (Explore confirmed it is the only bare site).
- **Snap entry points (post chrome-revamp).** The ribbon **Snap group is deleted** — its ribbon "Snap Settings…" / Angle-Snap entries are gone. **Angle-snap remains reachable in this UX pane** (pane content unchanged). The live in-canvas snap control is now the footer rail's **`InlineOsnapBar`** (contract owned by `mainwindow-chrome-revamp.md`); **right-clicking the footer rail's SNAP pill** opens `SystemSettingsDialog` directly on this UX pane via `select_pane("ux")`.

### 4.5 `.fpdt` template subsystem (`settings/template.py`)
- **A template is a blank-project `.fpd`**: empty entity collections + a `scale` block + a `project_info` block + a `"template": true` marker. Reuses the exact project serialization (zero new format code; forward-fits templates that later carry levels/gridlines/title block). Carries **settings, not geometry**.
- **Path:** `<app_data.default_root()>/default.fpdt` (existing `%APPDATA%/FirePro3D` resolver, honoring the `paths/user_data_root` override).
- **Auto-create (first run / missing):** write a blank template seeded with units migrated once from `display/*` QSettings (else factory defaults), empty `project_info`.
- **Startup / New Project — apply template *settings*, not a full clone.** The app builds its default scene **procedurally** after `_clear_scene()` (default plan view, `_place_default_gridlines()`, elevation markers, display defaults). A full `load_from_file` clone of a blank template would wipe those. So startup and New Project call `apply_template_settings(scene)` — which reads the template and applies its `scale` (→ `scene.scale_manager`) and `project_info` onto the already-built default scene — replacing the removed `_apply_persistent_unit_prefs()` override at exactly the same point in each flow. `clone_template_into()` (full `load_from_file`) is retained as the forward-fit for when templates carry geometry/levels, but is **not** wired into startup/new while the default scene is constructed procedurally.
- **Linked default title block (Task A, 2026-09-15):** the template also carries `titleblock_template_uuid` — a **library uuid** (reference, not an embedded copy). `apply_template_titleblock(scene, data)` (called by `apply_template_settings`) resolves it against the title-block library and embeds the **current** version into the new project, so edits to the linked template flow into future projects; a blank/unresolvable uuid leaves the project with no title block (blank sheet + prompt). Contract + resolution chain owned by `titleblock-template-system.md §Renderer & Resolution Chain / DD-23–24`.
- **"Save as default for new projects":** writes the *current project's* `scale` + `project_info` (+ the current embedded title block's `uuid` as `titleblock_template_uuid`) into the template file, preserving its blank geometry (copies **settings only**).
- **Clone semantics — "untitled":** a clone loads the template *content* but sets the project to **no file path + not-dirty**; a subsequent Save prompts for a location and can **never overwrite the template**. The `"template": true` marker is **stripped on clone**.
- **Corrupt/unreadable:** log to `error.log`, regenerate a factory-default template, proceed — **never crash** (guards the qFatal/silent-crash class).

### 4.5b Data-folder location + migration (General pane; Task E, 2026-09-15)
- **Data folder** (`paths/user_data_root`) relocates the whole data root; **Title block library** (`paths/titleblock_dir`, **E2**) is a dedicated override *just* for the title-block `<uuid>.json` files. Precedence (`app_data.titleblock_library_dir`): explicit title-block override → `<data root>/titleblocks` → default. Both fields live in `GeneralPane`; blank = inherit.
- **Block library** (`paths/block_dir`, 2026-09-23, block polish) — a third `GeneralPane` row mirroring the title-block row (Browse / reset; placeholder `(data folder)/blocks`). Precedence (`app_data.block_library_dir`): explicit block override → `<data root>/blocks`. Both dedicated overrides read through the shared `app_data._configured_dir(key)` helper. Block-library consumers → `block-system.md`.
- **Migrate-on-change (E3):** changing the data folder used to silently strand existing content (`app_data` docstring: "existing content is NOT moved"). Now the **System Settings dialog** — after `_apply_all()` (Apply/OK), **not** inside `pane.apply()` — calls `GeneralPane.migrate_prompt_if_needed()`, which offers **Copy / Move / Leave** to bring the whole data root's content (`app_data._MIGRATABLE`: titleblocks/, blocks/, sprinklers.json, default.fpdt) to the new folder via `app_data.migrate_data_root` (best-effort, **never clobbers** an existing destination item; Move deletes the source after copy). Kept out of `apply()` so headless `apply()` never blocks on a modal.

### 4.6 Ribbon + icons
- Manage→Settings group: two large buttons — **"System Settings"** (gear) and **"Project Settings"** (gear-with-document). Remove the old "Preferences" button + `info_icon.svg` usage and the "Snap Settings" button.
- Icons: 2D-symbol two-token themed SVGs (`settings_system_icon.svg`, `settings_project_icon.svg`) in `graphics/Ribbon/`, authored per `icon-style-guide.md` and **mockup-gated** (rendered 54/27px light+dark for approval) before wiring.
- **Entry points (post chrome-revamp, merge 0a7b44a):** the Manage→Settings ribbon buttons remain the primary way to open both dialogs. The chrome revamp additionally **deleted the ribbon Snap group** (its "Snap Settings…" / Angle-Snap entries are gone) and added a footer entry point: **right-clicking the footer rail's SNAP pill** opens `SystemSettingsDialog` on the snap-bearing UX pane via `select_pane("ux")` (see §4.4). Footer contract → `mainwindow-chrome-revamp.md`.

## 5. Design Decisions

- **D1 — Two dialogs, not one two-group dialog.** The persistence split (project vs app-wide) is the organizing principle; two dialogs make it structural rather than cosmetic and keep each dialog's Apply/Cancel semantics coherent.
- **D2 — Units are project-scoped.** They serialize in `.fpd` and take effect on open (removing the app-wide override). New-project defaults come from the template, not a QSettings seed.
- **D3 — Template = blank-project `.fpd` + marker.** Reuses serialization, forward-fits, and "Save as default" copies only `scale`+`project_info`.
- **D4 — `SideTabs`+`QStackedWidget` (house nav), `SwitchBar` for UX sub-modes.** Matches the import dialog; avoids nested rails.
- **D5 — Keep the live OSNAP toolbar; retire only the dialogs.** Toolbar is an in-canvas control, not a settings surface; parity via shared `snap/*` keys.
- **D6 — Import tab labelled "Import".** No export feature exists; the label stays honest until one does.
- **D7 — Deferred:** full template *library* / per-size templates / User-Profile UI / `.fpdt` as a managed subsystem; richer HALO controls; app-wide chrome sweep (its own P1 todo).

## 6. Acceptance Criteria

1. **Structure.** Two dialogs open from two Manage→Settings ribbon buttons. Project Settings rail = [Project Info, Units & Precision]; System Settings rail = [General, UX, UI, Import]; UX SwitchBar = [SNAP, ALIGN, HALO]. Both are `HouseDialog` subclasses, token-clean, hexguard-listed.
2. **Units round-trip.** Setting units in Project Settings → project Save → reload restores those units (observable via the loaded project's `scale_manager` / a formatted length).
3. **Legacy `.fpd`.** A `.fpd` with no units key loads without error and falls back to the template/factory default.
4. **Template.** First run auto-creates `default.fpdt`; startup opens a clone; New Project clones it (blank geometry, template's default units, **untitled + not-dirty**); "Save as default" writes settings into the template and the *next* New Project reflects them; a corrupt template regenerates without crashing.
5. **Consolidation.** `_open_snap_tolerance_dialog`, `_open_snap_settings`, the Manage "Snap Settings" button, and the bare `QSettings()` site are gone. The UX pane writes the same `snap/*`/`align/*`/`halo/*`/angle keys and refreshes the OSNAP toolbar. OSNAP toolbar toggles still work and stay in sync.
6. **Chrome.** Both dialogs render token-correct in light + dark; the two gear icons render at 54/27px in both themes.

## 7. Edge Cases & Error Handling

- **Corrupt/missing template** → regenerate factory default, log, proceed.
- **Legacy `.fpd` without units** → `ScaleManager.from_dict` fallback (already handled).
- **Save-over-template guard** → untitled clone (no path) prevents accidental overwrite.
- **Units/precision coupling** → precision applies within the chosen unit; both write together.
- **`display/*` vestigial keys** → read only for first-run seed; safe to leave (no live writers).

## 8. Testing

- `test_settings_dialogs.py` — two-dialog structure (driven through built widgets, not source introspection); "Save as default" write; snap-key parity after retirement; hexguard entry.
- `test_units_project_scoping.py` — `.fpd` units round-trip on a real project; legacy-`.fpd` fallback.
- `test_settings_template.py` — auto-create/seed; startup + New-Project clone; corrupt-recovery; untitled-clone guard.
- Reuse the autouse QSettings-isolation fixture. Rewrite `test_preferences_dialog.py` and `test_ribbon_restructure.py::test_open_preferences_has_six_tabs` to the two-dialog structure. Each guard shown RED with the fix reverted.
- **Live smoke (headless-dodgers):** startup opens the template; both ribbon buttons open the correct dialog; gear icons + chrome render in both themes; changing units re-renders the open project; New Project uses template defaults; the retired dialogs/button are gone.

## 9. Verification Checklist (Phase 6)

- [ ] All §6 acceptance criteria met; §8 guards green and shown-RED-when-reverted.
- [ ] Whole-repo grep clean for `PreferencesDialog` / `_open_preferences` / `_open_snap_settings` / `_open_snap_tolerance_dialog` / `_apply_persistent_unit_prefs` / `info_icon` (Settings button) — no dangling refs.
- [ ] Launch-smoke passes; live-smoke checklist walked.
- [ ] `settings-dialog.md` stamped `status`/`last-verified`/`verified-commit`; SPEC-INDEX orphan row replaced with the governing row; `ribbon-bar.md §3.4` temporary-governance note updated.
- [ ] Absorbed cluster todos moved to `todo_closed.md`; follow-ups filed.
