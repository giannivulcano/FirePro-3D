# Getting Started

## Prerequisites

- Python 3.10 or later
- Windows (primary platform), macOS/Linux may work but are untested
- Git

## Setup

Clone the repository and create a virtual environment:

```bash
git clone <repo-url>
cd FirePro3D
python -m venv venv
```

Activate the virtual environment:

```bash
# Windows (Git Bash)
source venv/Scripts/activate

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# macOS/Linux
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

This includes the 3D view stack (`pyvista`, `pyvistaqt`, `vtk`), which
`firepro3d/view_3d.py` imports at startup — the app will not launch without it.
On Windows the `vtk` wheel bundles its own native libraries; no separate VTK
install is needed.

### Optional: DWG import (ODA File Converter)

DWG files are imported by first converting them to DXF with the free
[ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)
(an external tool, not a Python package). It is only required if you import
`.dwg` files; `.dxf` and `.pdf` underlays work without it.

The app auto-detects the converter in this order:

1. The QSettings key `dwg/oda_converter_path` (set it via the import dialog if
   the converter lives in a non-standard location);
2. `ODAFileConverter.exe` on your system `PATH`;
3. Common install dirs (`%ProgramFiles%\ODA\ODAFileConverter <version>`).

## Running the Application

```bash
python main.py
```

This launches the main window with:

- **Ribbon bar** at the top with drawing and analysis tools
- **2D canvas** (Model Space) for plan-view editing
- **Property panel** on the right for inspecting/editing selected items
- **Model browser** for navigating project objects

If the window opens and the ribbon, canvas, property panel, and model browser
are all visible, the install (including the 3D stack) is working.

## Building Documentation

Install doc dependencies (separate from app dependencies):

```bash
pip install -r docs/requirements.txt
```

Preview docs locally:

```bash
mkdocs serve
```

Then open `http://127.0.0.1:8000` in your browser.

Build static site:

```bash
mkdocs build
```

Output goes to `site/`.

## Project files and backups

Every Save keeps a dated copy of the previous file in a `Backups` folder beside the project,
newest 10 per project. To go back, copy one out of that folder and open it. Autosave does not
add to this folder.

If a save would write away most of the project on disk, FirePro3D asks first; Cancel leaves the
file alone. If a project fails to load, the file is not changed and what is on screen is not
connected to it, so Save asks for a new name.
