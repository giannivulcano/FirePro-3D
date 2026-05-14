"""
dwg_converter.py
================
DWG to DXF conversion via ODA File Converter.

ODA File Converter is a free tool from Open Design Alliance that converts
between DWG and DXF formats.  This module handles finding the ODA executable,
running the conversion, and listing layouts from the resulting DXF.

ODA CLI usage::

    ODAFileConverter <input_dir> <output_dir> <version> <type> <recurse> <audit>

The converter operates on directories, not individual files, so we copy
the source DWG into a temp input directory and read the output DXF from
a temp output directory.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

_last_error: str = ""


def _set_last_error(msg: str) -> None:
    global _last_error
    _last_error = msg


def get_last_error() -> str:
    """Return diagnostic info from the last failed conversion."""
    return _last_error


_COMMON_ODA_DIRS: list[str] = [
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "ODA", "ODAFileConverter 27.1.0"),
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "ODA", "ODAFileConverter 26.3.0"),
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "ODA", "ODAFileConverter 25.12.0"),
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "ODA", "ODAFileConverter 25.6.0"),
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "ODA", "ODAFileConverter"),
]

_ODA_EXE = "ODAFileConverter.exe"

# Download page for error dialogs
ODA_DOWNLOAD_URL = "https://www.opendesign.com/guestfiles/oda_file_converter"


def _oda_path_from_settings() -> str | None:
    """Read the ODA converter path from QSettings, if set."""
    try:
        from PyQt6.QtCore import QSettings
        s = QSettings("GV", "FirePro3D")
        path = s.value("dwg/oda_converter_path", None)
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass
    return None


def find_oda_converter() -> str | None:
    """Locate the ODA File Converter executable.

    Search order:
    1. QSettings (user-configured path)
    2. System PATH (shutil.which)
    3. Common install directories

    Returns:
        Absolute path to ODAFileConverter.exe, or None if not found.
    """
    # 1. QSettings
    path = _oda_path_from_settings()
    if path:
        return path

    # 2. PATH
    which = shutil.which(_ODA_EXE)
    if which and os.path.isfile(which):
        return which

    # 3. Common install directories
    for d in _COMMON_ODA_DIRS:
        candidate = os.path.join(d, _ODA_EXE)
        if os.path.isfile(candidate):
            return candidate

    return None


def _ref_dir_for_project(project_dir: str | None) -> str | None:
    """Return the UNDERLAY_REF directory for a project, creating if needed.

    Args:
        project_dir: Directory containing the ``.fpd`` project file,
            or ``None`` if the project has not been saved yet.

    Returns:
        Absolute path to ``<project_dir>/UNDERLAY_REF/``, or ``None``
        if no project directory is available.
    """
    if not project_dir:
        return None
    ref_dir = os.path.join(project_dir, "UNDERLAY_REF")
    os.makedirs(ref_dir, exist_ok=True)
    return ref_dir


def convert_dwg_to_dxf(oda_path: str, dwg_path: str,
                        project_dir: str | None = None) -> str | None:
    """Convert a DWG file to DXF using ODA File Converter.

    When *project_dir* is given the converted DXF is saved to
    ``<project_dir>/UNDERLAY_REF/<stem>.dxf`` so it persists across
    sessions.  If the DXF already exists and is newer than the source
    DWG, the conversion is skipped entirely.

    When *project_dir* is ``None`` (project not saved yet), a temporary
    directory is used instead.

    Args:
        oda_path: Absolute path to ODAFileConverter.exe.
        dwg_path: Absolute path to the source ``.dwg`` file.
        project_dir: Directory containing the ``.fpd`` project file.

    Returns:
        Absolute path to the converted ``.dxf`` file, or ``None`` on
        failure (ODA crash, no output produced, source file missing).
    """
    if not os.path.isfile(dwg_path):
        return None

    basename = os.path.basename(dwg_path)
    stem = os.path.splitext(basename)[0]

    # Determine output directory
    ref_dir = _ref_dir_for_project(project_dir)
    if ref_dir:
        out_dir = ref_dir
        is_temp = False
        # Skip conversion if a fresh DXF already exists
        existing = os.path.join(out_dir, f"{stem}.dxf")
        if os.path.isfile(existing):
            if os.path.getmtime(existing) >= os.path.getmtime(dwg_path):
                return existing
    else:
        out_dir = tempfile.mkdtemp(prefix="fpro_dwg_out_")
        is_temp = True

    # ODA operates on directories — isolate the source file
    in_dir = tempfile.mkdtemp(prefix="fpro_dwg_in_")

    last_error = ""
    try:
        shutil.copy2(dwg_path, os.path.join(in_dir, basename))

        # ODA args: input_dir output_dir version output_type recurse audit
        cmd = [oda_path, in_dir, out_dir, "ACAD2018", "DXF", "0", "1"]

        # Suppress the ODA GUI window on Windows
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

        result = subprocess.run(cmd, timeout=120, capture_output=True,
                                text=True, startupinfo=startupinfo)
        last_error = (f"ODA exit code {result.returncode}\n"
                      f"stdout: {(result.stdout or '')[:500]}\n"
                      f"stderr: {(result.stderr or '')[:500]}")
        if result.returncode != 0:
            _set_last_error(last_error)
            if is_temp:
                shutil.rmtree(out_dir, ignore_errors=True)
            return None
    except subprocess.TimeoutExpired:
        _set_last_error("ODA conversion timed out after 120 seconds")
        shutil.rmtree(in_dir, ignore_errors=True)
        if is_temp:
            shutil.rmtree(out_dir, ignore_errors=True)
        return None
    except OSError as e:
        _set_last_error(f"OSError launching ODA: {e}")
        shutil.rmtree(in_dir, ignore_errors=True)
        if is_temp:
            shutil.rmtree(out_dir, ignore_errors=True)
        return None
    finally:
        shutil.rmtree(in_dir, ignore_errors=True)

    # Find the output DXF
    expected = os.path.join(out_dir, f"{stem}.dxf")
    if os.path.isfile(expected):
        return expected

    # Fallback: pick the first .dxf in the output directory
    try:
        out_files = os.listdir(out_dir)
    except OSError:
        out_files = []
    for f in out_files:
        if f.lower().endswith(".dxf"):
            return os.path.join(out_dir, f)

    # No DXF produced — store diagnostics
    _set_last_error(
        last_error or
        f"No DXF produced. Output dir contents: {out_files}\n"
        f"cmd: {cmd}")
    if is_temp:
        shutil.rmtree(out_dir, ignore_errors=True)
    return None


def cleanup_converted_dxf(dxf_path: str) -> None:
    """Remove a converted DXF only if it lives in a temp directory.

    DXFs in ``UNDERLAY_REF/`` are kept for reuse across sessions.
    Only temp directories created when no project is saved are cleaned up.
    """
    if not dxf_path:
        return
    parent = os.path.dirname(dxf_path)
    if os.path.basename(parent).startswith("fpro_dwg_out_"):
        shutil.rmtree(parent, ignore_errors=True)


def list_dwg_layouts(dxf_path: str) -> list[str]:
    """Read layout names from a converted DXF file.

    Args:
        dxf_path: Path to a DXF file (output of :func:`convert_dwg_to_dxf`).

    Returns:
        List of layout names with ``"Model"`` always first.
        Returns ``["Model"]`` on any error.
    """
    try:
        import ezdxf
        doc = ezdxf.readfile(dxf_path)
        names = list(doc.layouts.names())
    except Exception:
        return ["Model"]

    # Ensure "Model" is first
    if "Model" in names:
        names.remove("Model")
    return ["Model"] + sorted(names)
