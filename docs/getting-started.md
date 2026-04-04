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

## Running the Application

```bash
python main.py
```

This launches the main window with:

- **Ribbon bar** at the top with drawing and analysis tools
- **2D canvas** (Model Space) for plan-view editing
- **Property panel** on the right for inspecting/editing selected items
- **Model browser** for navigating project objects

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
