# FirePro3D

Fire protection sprinkler system design and analysis tool. Provides CAD-like 2D/3D editing, hydraulic analysis, and thermal radiation analysis for NFPA 13 compliant sprinkler system design.

## Features

- **2D CAD editing** — draw pipes, place sprinklers, define rooms and walls with snapping and constraints
- **3D visualization** — real-time 3D view via PyVista/VTK
- **Hydraulic analysis** — Hazen-Williams pressure/flow calculations per NFPA 13
- **Thermal radiation analysis** — fire dynamics and radiation heat transfer
- **DXF/PDF import** — bring in architectural backgrounds and reference drawings
- **Multi-floor support** — elevation-based level system with cross-section views
- **NFPA 13 compliance** — built-in coverage limits, hazard classifications, and spacing rules

## Tech Stack

| Component | Technology |
|-----------|-----------|
| UI framework | PyQt6 |
| DXF import/export | ezdxf |
| PDF import | PyMuPDF |
| Numerical computation | numpy |
| 3D visualization | PyVista / VTK |
| Internal units | millimeters |

## Quick Start

See [Getting Started](getting-started.md) for setup instructions.

## Documentation

- **[Architecture](architecture/overview.md)** — how the system is designed
- **[Contributing](contributing/guide.md)** — code style, conventions, how to add features
- **[API Reference](reference/)** — auto-generated from source code
