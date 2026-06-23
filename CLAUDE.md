# FirePro3D

Fire protection sprinkler system design and analysis tool built with PyQt6.

For full documentation, see `docs/` or run `mkdocs serve`.

## Tech Stack

- **Python 3.x** with **PyQt6** (UI framework)
- **ezdxf** for DXF import (read-only; no DXF export exists)
- **PyMuPDF** for PDF import
- **ODA File Converter** (external CLI) for DWG→DXF conversion
- **numpy** for numerical computation
- **PyVista** / **VTK** for 3D visualization

## Package Structure

- `main.py` — Entry point (stays at project root)
- `firepro3d/` — All application code (flat package)
- `firepro3d/graphics/` — SVG symbols and icons
- `docs/` — Project documentation (MkDocs)

## Commands

```bash
# Activate virtual environment
source venv/Scripts/activate

# Run the application
python main.py

# Preview docs
pip install -r docs/requirements.txt
mkdocs serve
```

## Key Conventions

- All geometry stored internally in **millimeters**
- Constants centralized in `firepro3d/constants.py` — avoid magic numbers
- Graphics paths resolved via `firepro3d/assets.py` (`asset_path()`)
- NFPA 13 standards drive coverage limits and hazard classifications
- JSON-based project files for persistence
- Default level: "Level 1" (the per-item layer system was removed; `DEFAULT_ANNOTATION_GROUP = "Default"` is now only an annotation-grouping label)
- Default ceiling offset: -50.8 mm (-2 inches below ceiling)
- Z-ordering: Z_BELOW_GEOMETRY (-100) < Z_UNDERLAY (-79, initial) < Z_ROOF (-75); at runtime, elevation-based z-ordering sets: floors (0.0) < underlays (0.05) < roofs (0.1) < rooms (0.2) < walls (0.3) < pipes (0.4) < nodes (0.5)
- Imports: relative within `firepro3d/` (`from .node import Node`), absolute from `main.py` (`from firepro3d.node import Node`)
- Docstring style: Google
- Module naming: lowercase_with_underscores (PEP 8)

## Documentation governance (the leash)

Docs exist to keep the AI grounded in the *intended* architecture — they are a control surface, not a manual. **A wrong spec is worse than none.** Audience: future-self + the AI loop, so accuracy/anti-drift beats publishing polish.

- **Two layers.** `docs/architecture/` = cross-subsystem ripple map (orientation). `docs/design/` governing specs (currently `docs/specs/`) = per-subsystem contracts/invariants.
- **Rule A — one fact, one home.** Architecture *links* to specs; never restate an owned fact (Z-order → `docs/specs/view-relationships.md §7.3` + `constants.py`; signatures, enums, defaults). Never cite line/LOC counts.
- **Grounding:** before editing a subsystem, load its governing spec via the index → `docs/specs/SPEC-INDEX.md`.
- **Orphans (no spec yet — forge on first touch):** thermal radiation, 3D view, `.fpd` scene-I/O.
- **Enforcement:** the `/todo` skill clips the leash on — **Ground** (load specs, Phase 1b), **Forge** (blocking spec-creation + grill for ungoverned code), **Account** (re-audit + stamp specs at wrap-up). Full multi-agent doc audit → milestone-level.

> Note (2026-06-23): the curated docs were swept for the 2026-06-22 audit's drift findings in the Section-A drift-fix pass — the **layer system is removed** (`user_layer` gone; `DEFAULT_USER_LAYER` renamed to `DEFAULT_ANNOTATION_GROUP`), ezdxf is **import-only**, and PyVista/VTK (not `vispy`) drives 3D. Remaining doc-reorg work (directory moves, frontmatter backfill) is tracked in `DOCS-REVIEW.md`.
