# FirePro3D

Fire protection sprinkler system design and analysis tool.

Plan piping layouts, auto-populate sprinklers by NFPA 13 density/area criteria, run Hazen-Williams hydraulic calculations, and produce professional reports — all in one desktop application.

## Features

- **2D Plan View** — draw pipes, walls, rooms, construction geometry with full OSNAP engine
- **3D Visualization** — PyVista/VTK mesh rendering with color-coded hydraulic results
- **Hydraulic Solver** — Hazen-Williams tree solver with supply curve validation, equivalent pipe lengths, hose stream allowance
- **Auto-Populate** — NFPA 13 density/area sprinkler placement with Voronoi relaxation
- **DXF/PDF Underlays** — import, scale-calibrate, and snap to background drawings
- **Section Views** — arbitrary-angle cut planes through the model
- **Paper Space** — sheet management, viewports, PDF export

## Requirements

- Python 3.11+
- Windows (PyQt6 desktop app)

## Setup

```bash
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

Project files use the `.fpd` extension.

## Documentation

```bash
pip install -r docs/requirements.txt
mkdocs serve
```

Then open http://127.0.0.1:8000.

## Tech Stack

| Component | Library |
|-----------|---------|
| UI framework | PyQt6 |
| DXF import/export | ezdxf |
| PDF import | PyMuPDF (fitz) |
| Numerics | numpy |
| 3D rendering | PyVista / VTK |

## License

Proprietary. All rights reserved.
