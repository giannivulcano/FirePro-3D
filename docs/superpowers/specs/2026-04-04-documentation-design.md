# FirePro3D Documentation — Design Spec

**Date:** 2026-04-04
**Status:** Approved
**Audience:** Developer (self + contributors)

## Goal

Create comprehensive project documentation that serves two audiences: the primary developer returning to the project after time away, and new contributors who need to understand and modify the codebase. Documentation should auto-generate as much as possible from code, with hand-written narrative for architecture and contributing guides.

This effort includes three work streams:
1. **Package restructure** — reorganize flat files into a `firepro3d/` package
2. **Docs tooling** — MkDocs setup with auto-generated API reference
3. **Content writing** — hand-written architecture and contributing guides

## Decisions Log

| # | Question | Decision |
|---|----------|----------|
| 1 | Flat files vs. mkdocstrings | Restructure into `firepro3d/` package |
| 2 | Flat package vs. sub-packages | Flat package — single `__init__.py` |
| 3 | .gitignore cleanup | Replace 597KB file with standard Python .gitignore |
| 4 | Docstring style conflict | Standardize to Google style (convert NumPy in hydraulic_solver) |
| 5 | Model_Space docstring priority | Priority #2 + section grouping for methods |
| 6 | API reference scope | All 74 files, grouped by tier in nav sidebar |
| 7 | Diagrams | Mermaid only — no static images |
| 8 | CLAUDE.md | Slim down to AI essentials, link to docs |
| 9 | Entry point | `main.py` stays at root, imports from `firepro3d.*` |
| 10 | `graphics/` directory | Move into `firepro3d/`, fix path resolution |
| 11 | Docstring improvements | Separate effort — not part of this plan |
| 12 | Refactoring catalog | Standalone `docs/architecture/refactoring.md` |
| 13 | Build integration | Manual only — document commands, no CI/CD |
| 14 | File naming | Rename to PEP 8 during the move |

## Explicitly Deferred

- Docstring improvements (incremental, separate effort)
- Sub-package reorganization (flat package for now)
- Model_Space decomposition (catalog in refactoring.md, execute later)
- CI/CD for docs (manual builds for now)

---

## Work Stream 1: Package Restructure

### Step 1: Clean up .gitignore

Replace the 597KB .gitignore with a standard Python .gitignore (~3KB) covering:
- `venv/`, `__pycache__/`, `*.pyc`
- `.vscode/`, `.idea/`
- `site/` (MkDocs output)
- `*.egg-info/`, `dist/`, `build/`

Separate commit before any file moves.

### Step 2: Create `firepro3d/` package

Move all 73 `.py` files (everything except `main.py`) into `firepro3d/` with PEP 8 renaming:

| Current Name | New Name |
|---|---|
| `Model_Space.py` | `model_space.py` |
| `Model_View.py` | `model_view.py` |
| `CAD_Math.py` | `cad_math.py` |
| `Annotations.py` | `annotations.py` |
| All other files | Already lowercase — no rename needed |

Create `firepro3d/__init__.py` (minimal, possibly empty).

Move `graphics/` into `firepro3d/graphics/`.

### Step 3: Fix all imports

Update every import across all files:
- `from node import Node` → `from firepro3d.node import Node`
- `from Model_Space import Model_Space` → `from firepro3d.model_space import Model_Space`
- `from CAD_Math import CAD_Math` → `from firepro3d.cad_math import CAD_Math`
- etc.

`main.py` stays at root, imports from `firepro3d.*`.

Internal imports within `firepro3d/` should use relative imports:
- `from .node import Node`
- `from .constants import DEFAULT_LEVEL`

### Step 4: Fix graphics path resolution

Two patterns exist today:
- **Bare relative paths** (`"graphics/fitting_symbols/tee.svg"`) — used in `fitting.py`, `main.py`
- **`__file__`-relative** (`os.path.dirname(__file__)`) — used in `hydraulic_node_badge.py`

After the move:
- `__file__`-relative paths work automatically (graphics moved alongside code)
- Bare relative paths need updating — add an `ASSETS_DIR` constant in `constants.py` using `os.path.dirname(__file__)` and resolve paths through it
- `main.py` icon paths (`graphics/Ribbon/...`) update to reference `firepro3d/graphics/Ribbon/...` or use `ASSETS_DIR`

### Step 5: Update CLAUDE.md

Slim down to AI-essential context:
- Tech stack (keep)
- Commands (update paths)
- Key conventions: mm units, constants.py, Z-ordering, default level/layer (keep)
- Remove architecture narrative — link to `docs/architecture/` instead
- Remove detailed project structure — link to `docs/` instead

---

## Work Stream 2: Docs Tooling

### Dependencies

`docs/requirements.txt`:
```
mkdocs-material
mkdocstrings[python]
mkdocs-gen-files
mkdocs-literate-nav
```

### Configuration

`mkdocs.yml` at project root:
- Theme: Material for MkDocs
- Plugins: mkdocstrings (Google style, `allow_inspection: false` for static analysis), gen-files, literate-nav
- Mermaid diagrams enabled via Material's built-in support
- Navigation structure matching the docs layout below

### Auto-generated API Reference

`docs/gen_ref_pages.py` runs at build time:
1. Scans all `.py` files in `firepro3d/`
2. Generates `reference/<module>.md` containing a `:::firepro3d.<module>` directive
3. mkdocstrings renders via static analysis (griffe, no imports)
4. Navigation sidebar groups modules into tiers:

| Tier | Modules |
|------|---------|
| **Core** | model_space, model_view, scene_tools, scene_io, snap_engine |
| **Entities** | node, pipe, sprinkler, room, wall, fitting, roof, floor_slab, wall_opening, annotations, construction_geometry, gridline, grid_line, view_marker, underlay, block_item, water_supply, design_area |
| **Managers** | display_manager, level_manager, scale_manager, layer_manager, user_layer_manager, elevation_manager |
| **Analysis** | hydraulic_solver, hydraulic_report, hydraulic_node_badge, thermal_radiation_solver, thermal_radiation_report, fire_curves |
| **UI** | ribbon_bar, theme, property_manager, model_browser, project_browser, level_widget, view_cube |
| **Dialogs** | auto_populate_dialog, dxf_preview_dialog, roof_dialog, wall_dialog, array_dialog, grid_lines_dialog, view_range_dialog, calibrate_dialog, detail_view, dimension_edit, fs_visibility_dialog, underlay_context_menu, entity_context_menu |
| **Views** | view_3d, elevation_scene, elevation_view, paper_space |
| **Utilities** | cad_math, geometry_utils, geometry_intersect, format_utils, hatch_patterns, constants, constraints, displayable_item, sprinkler_db, sprinkler_system |
| **Workers** | dxf_import_worker, pdf_import_worker |

### Commands

- `mkdocs serve` — local dev server with hot reload
- `mkdocs build` — generate static site to `site/`
- No CI/CD — manual builds only

---

## Work Stream 3: Content Writing

### Documentation Structure

```
docs/
├── index.md                        # Project overview (replaces README)
├── getting-started.md              # Setup, install, running the app
├── architecture/
│   ├── overview.md                 # System architecture, mixin pattern, data flow
│   ├── entities.md                 # Entity hierarchy and relationships
│   ├── display-system.md           # DisplayManager, DisplayableItemMixin, Z-ordering
│   ├── level-system.md             # Multi-floor, elevation, ScaleManager
│   ├── analysis.md                 # Hydraulic solver, thermal radiation
│   ├── io.md                       # Scene I/O, DXF/PDF import
│   └── refactoring.md             # Refactoring candidates identified during doc pass
├── contributing/
│   ├── guide.md                    # Code style, conventions, how to contribute
│   ├── adding-entities.md          # Recipe: add a new entity type
│   └── adding-tools.md            # Recipe: add a new drawing tool
├── reference/                      # Auto-generated (one page per module, grouped)
│   ├── SUMMARY.md
│   └── <module>.md
├── gen_ref_pages.py
└── requirements.txt
```

### Page Details

**`index.md`** — Project overview: what FirePro3D is, key features, tech stack, link to getting-started.

**`getting-started.md`** — Clone, create venv, install dependencies, run `python main.py`. Prerequisites (Python 3.x, platform notes).

**Architecture pages** — each includes:
- "Key files" list at top with source links
- Narrative explanation of the subsystem
- Mermaid diagrams where helpful
- How the subsystem connects to others

| Page | Covers |
|------|--------|
| `overview.md` | Mixin composition (SceneToolsMixin, SceneIOMixin), Model_Space as central hub, manager services, overall data flow |
| `entities.md` | Entity hierarchy: QGraphicsItem + DisplayableItemMixin. Node/Pipe/Sprinkler network, Wall/Room/Floor geometry |
| `display-system.md` | DisplayManager per-category/per-instance overrides, DisplayableItemMixin, Z-ordering convention |
| `level-system.md` | LevelManager, multi-floor elevations, elevation views, ScaleManager unit conversions |
| `analysis.md` | Hydraulic solver (Hazen-Williams, tree topology), thermal radiation solver, report generation |
| `io.md` | SceneIOMixin JSON serialization, DXF import/export (ezdxf), PDF import (PyMuPDF), background workers |

**`refactoring.md`** — Refactoring candidates discovered during documentation:
- Model_Space decomposition (7,195 lines, 55 public methods)
- Other candidates identified during the pass
- For each: what the problem is, why it matters, rough approach

**Contributing pages:**

| Page | Covers |
|------|--------|
| `guide.md` | Conventions: mm internal units, constants.py, Z-ordering values, default level/layer, Google-style docstrings, PEP 8 naming |
| `adding-entities.md` | Step-by-step: subclass QGraphicsItem + DisplayableItemMixin, register with DisplayManager, add to scene_io, add to model_space |
| `adding-tools.md` | How to add a drawing tool via SceneToolsMixin, connect to ribbon_bar |

---

## Current Codebase State

- 74 Python files, ~44,600 lines
- 100% file-level docstring coverage
- 88% type hint coverage (65/74 files)
- Inconsistent method-level docstrings (mostly Google-style, some NumPy-style)
- Flat file structure (no `__init__.py`, no package)
- Imports: absolute, direct module names
- No tests, no CI/CD
- .gitignore is 597KB (bloated with venv entries)

## Maintenance Model

- **API reference:** Zero maintenance — auto-generated from code on every build
- **Architecture docs:** Update when system design changes
- **Contributing docs:** Update when conventions change
- **Refactoring.md:** Update as opportunities are identified or completed
- **CLAUDE.md:** Keep in sync with conventions — slim version pointing to docs
- **Docstrings:** Improve incrementally as modules are touched (separate effort)
