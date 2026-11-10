"""doc_converter.py
===================
.docx -> PDF through Microsoft Word (sheet-linked-document design D3).

Word is driven over COM from a ``powershell.exe`` subprocess (no Python COM
dependency), on a temp COPY of the file so it works while the original is open
in Word or locked by OneDrive. The PowerShell script is a fixed string; the file
paths reach it only as command-line arguments, never interpolated into script
text. Pattern: ``dwg_converter.convert_dwg_to_dxf`` (hidden window, timeout,
temp dirs). ``ConvertWorker`` runs a conversion off the GUI thread (AC13).
"""
from __future__ import annotations

import functools
import os
import shutil
import subprocess
import tempfile
import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal

from .constants import LINKED_DOC_CONVERT_TIMEOUT_S

# Fixed script: paths arrive as -InPath / -OutPath arguments only. A Word
# instance that already holds documents is the user's: never hide or quit it.
_PS_SCRIPT = r"""param(
    [Parameter(Mandatory = $true)][string]$InPath,
    [Parameter(Mandatory = $true)][string]$OutPath
)
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$shared = $word.Documents.Count -gt 0
try {
    if (-not $shared) {
        $word.Visible = $false
        $word.DisplayAlerts = 0
    }
    $doc = $word.Documents.Open($InPath, $false, $true, $false)
    try {
        $doc.ExportAsFixedFormat($OutPath, 17, $false, 0)
    } finally {
        $doc.Close(0)
    }
} finally {
    if (-not $shared) { $word.Quit() }
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
"""


class ConversionError(RuntimeError):
    """Word could not convert the document; the message is user-facing."""


@functools.lru_cache(maxsize=1)
def word_available() -> bool:
    """True when Word's COM class is registered (``HKCR\\Word.Application``)."""
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID"):
            return True
    except OSError:
        return False


def build_command(script_path: str, in_path: str, out_path: str) -> "list[str]":
    """The powershell.exe argv: the script file plus the two paths as arguments."""
    return ["powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", script_path,
            "-InPath", in_path, "-OutPath", out_path]


class ConversionCancelled(ConversionError):
    """The app stopped waiting (window close); the PowerShell run is left to
    finish on its own and quit the Word instance it started."""


def convert_docx_to_pdf_bytes(docx_path: str,
                              timeout: int = LINKED_DOC_CONVERT_TIMEOUT_S,
                              cancel: "threading.Event | None" = None) -> bytes:
    """Convert *docx_path* to PDF through Word and return the PDF bytes.

    Args:
        docx_path: The user's .docx (left untouched; a temp copy is converted).
        timeout: Seconds before the conversion is abandoned.
        cancel: Set by ``LinkedDocService.shutdown`` (ratified 2026-11-09:
            "Close now, drop update"). When set, stop waiting at once and raise
            ``ConversionCancelled`` WITHOUT killing PowerShell (killing it would
            orphan a hidden WINWORD) and without deleting the work folder the
            still-running script uses.

    Raises:
        ConversionError: missing file, PowerShell/Word failure, or timeout.
        ConversionCancelled: *cancel* was set.
    """
    if not os.path.isfile(docx_path):
        raise ConversionError("the file was not found")
    work = tempfile.mkdtemp(prefix="fpro_docx_")
    keep_work = False
    try:
        src = os.path.join(work, "source.docx")
        shutil.copy2(docx_path, src)
        script = os.path.join(work, "convert.ps1")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(_PS_SCRIPT)
        out = os.path.join(work, "out.pdf")
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
        try:
            proc = subprocess.Popen(build_command(script, src, out),
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True,
                                    startupinfo=startupinfo)
        except OSError as exc:
            raise ConversionError(f"PowerShell could not start ({exc})") from exc
        deadline = time.monotonic() + timeout
        while True:
            if cancel is not None and cancel.is_set():
                keep_work = True        # the script still runs from this folder
                raise ConversionCancelled("the app closed before Word finished")
            try:
                stdout, stderr = proc.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    proc.kill()
                    proc.communicate()
                    raise ConversionError(
                        f"Word did not finish in {timeout} s") from None
        if proc.returncode != 0 or not os.path.isfile(out):
            lines = [ln.strip() for ln in
                     (stderr or stdout or "").splitlines() if ln.strip()]
            raise ConversionError(
                lines[0][:200] if lines else f"exit code {proc.returncode}")
        with open(out, "rb") as fh:
            return fh.read()
    finally:
        if not keep_work:
            shutil.rmtree(work, ignore_errors=True)


class ConvertWorker(QThread):
    """Runs one conversion off the GUI thread (AC13).

    Signals:
        converted(str, object): source path, PDF bytes.
        failed(str, str): source path, user-facing reason.
    """

    converted = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, path: str, convert_fn=None, parent=None):
        super().__init__(parent)
        self.path = path
        self.cancel_event = threading.Event()
        self._convert = convert_fn or convert_docx_to_pdf_bytes

    def cancel(self) -> None:
        """Stop waiting on Word (window close); the run ends within ~0.25 s."""
        self.cancel_event.set()

    def run(self) -> None:
        try:
            if self._convert is convert_docx_to_pdf_bytes:
                data = self._convert(self.path, cancel=self.cancel_event)
            else:
                data = self._convert(self.path)
        except ConversionCancelled:
            return                      # dropped on purpose: no signal
        except Exception as exc:  # noqa: BLE001 -- a worker must always report
            self.failed.emit(self.path, str(exc) or type(exc).__name__)
            return
        self.converted.emit(self.path, data)
