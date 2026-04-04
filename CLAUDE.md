# FirePro3D

Fire protection sprinkler system design and analysis tool built with PyQt6.

For full documentation, see `docs/` or run `mkdocs serve`.

## Tech Stack

- **Python 3.x** with **PyQt6** (UI framework)
- **ezdxf** for DXF import/export
- **PyMuPDF** for PDF import
- **numpy** for numerical computation
- **vispy** / **PyVista** for 3D visualization

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
- Default level: "Level 1"; default layer: "Default"
- Default ceiling offset: -50.8 mm (-2 inches below ceiling)
- Z-ordering: Z_BELOW_GEOMETRY (-100) < Z_ROOF (-75) < walls/floors (0-50) < nodes (10+) < sprinklers (100)
- Imports: relative within `firepro3d/` (`from .node import Node`), absolute from `main.py` (`from firepro3d.node import Node`)
- Docstring style: Google
- Module naming: lowercase_with_underscores (PEP 8)
