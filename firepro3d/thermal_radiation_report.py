"""
thermal_radiation_report.py
===========================
Report widget for thermal radiation analysis results.

Provides a QWidget with three tabs:
  1. Summary            — pass/fail banner + max flux + area exceeding
  2. Receiver Results   — per-receiver max flux, area exceeding
  3. Emitter Contributions — per-emitter total contribution

Export:
  - PDF  — via Qt's QPrinter
  - CSV  — Python built-in csv module
"""

from __future__ import annotations

import csv

import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHBoxLayout, QPushButton, QTextBrowser,
    QHeaderView, QFileDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QTextDocument

try:
    from PyQt6.QtPrintSupport import QPrinter
    _PRINTER_AVAILABLE = True
except ImportError:
    _PRINTER_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Colour helpers
# ─────────────────────────────────────────────────────────────────────────────

_GREEN = QColor(210, 245, 215)
_RED   = QColor(255, 205, 205)
_TEXT_GREEN = QColor(0, 100, 0)
_TEXT_RED   = QColor(160, 0, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Table helpers
# ─────────────────────────────────────────────────────────────────────────────

def _item(text: str, color: QColor | None = None, bold: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    if color:
        it.setBackground(color)
        if color.rgb() == _GREEN.rgb():
            it.setForeground(_TEXT_GREEN)
        elif color.rgb() == _RED.rgb():
            it.setForeground(_TEXT_RED)
    if bold:
        font = it.font()
        font.setBold(True)
        it.setFont(font)
    return it


def _make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setSortingEnabled(True)
    return t


# ─────────────────────────────────────────────────────────────────────────────
# Main widget
# ─────────────────────────────────────────────────────────────────────────────

class ThermalRadiationReportWidget(QWidget):
    """Tabbed thermal radiation report panel for embedding in a dock widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result = None
        self._scene = None
        self._sm = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── Export buttons ────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        self._pdf_btn = QPushButton("\u2b07 Export PDF")
        self._csv_btn = QPushButton("\u2b07 Export CSV")
        self._pdf_btn.setEnabled(False)
        self._csv_btn.setEnabled(False)
        self._pdf_btn.clicked.connect(self._export_pdf)
        self._csv_btn.clicked.connect(self._export_csv)
        btn_bar.addWidget(self._pdf_btn)
        btn_bar.addWidget(self._csv_btn)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        # ── Tabs ──────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Summary
        self._summary = QTextBrowser()
        self._summary.setOpenExternalLinks(False)
        self._summary.setPlaceholderText(
            "Run thermal radiation analysis to see results."
        )
        self.tabs.addTab(self._summary, "Summary")

        # Tab 2: Receiver Results
        self._recv_table = _make_table([
            "Surface", "Max Flux (kW/m\u00b2)", "Avg Flux (kW/m\u00b2)",
            "Area Exceeding (m\u00b2)", "% Exceeding", "Status",
        ])
        self.tabs.addTab(self._recv_table, "Receiver Results")

        # Tab 3: Emitter Contributions
        self._emit_table = _make_table([
            "Surface", "Total Contribution (kW/m\u00b2)", "% of Total",
        ])
        self.tabs.addTab(self._emit_table, "Emitter Contributions")

    # ------------------------------------------------------------------
    # Public API

    def populate(self, result, scene, sm):
        """Fill all tabs from a completed RadiationResult."""
        self._result = result
        self._scene = scene
        self._sm = sm

        self._fill_summary()
        self._fill_receiver_results()
        self._fill_emitter_contributions()

        self._pdf_btn.setEnabled(_PRINTER_AVAILABLE)
        self._csv_btn.setEnabled(True)

    def clear(self):
        """Reset all tabs to empty state."""
        self._result = self._scene = self._sm = None
        self._summary.clear()
        self._recv_table.setRowCount(0)
        self._emit_table.setRowCount(0)
        self._pdf_btn.setEnabled(False)
        self._csv_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Tab fillers

    def _fill_summary(self):
        r = self._result
        ok = r.passed
        status_html = (
            '<div style="background:#c8f7c8;padding:8px;border-radius:4px;'
            'text-align:center;font-size:16px;font-weight:bold;color:#006400;">'
            '\u2713 PASS — Radiation below threshold</div>'
            if ok else
            '<div style="background:#ffc8c8;padding:8px;border-radius:4px;'
            'text-align:center;font-size:16px;font-weight:bold;color:#a00000;">'
            '\u2717 FAIL — Radiation exceeds threshold</div>'
        )

        params = r.parameters
        curve = params.get("fire_curve", "Constant")
        if curve == "Constant":
            temp_str = f"{params.get('emitter_temp_c', 800):.0f} \u00b0C (constant)"
        else:
            temp_str = (
                f"{curve} @ {params.get('fire_duration_min', 60):.0f} min"
            )

        # Format location
        loc = r.max_location
        if self._sm:
            loc_str = (
                f"({self._sm.format_length(loc[0])}, "
                f"{self._sm.format_length(loc[1])}, "
                f"{self._sm.format_length(loc[2])})"
            )
        else:
            loc_str = f"({loc[0]:.0f}, {loc[1]:.0f}, {loc[2]:.0f}) mm"

        html = f"""
        {status_html}
        <table style="margin-top:12px;font-size:13px;" cellpadding="4">
        <tr><td><b>Maximum Radiation:</b></td>
            <td>{r.max_radiation:.2f} kW/m\u00b2</td></tr>
        <tr><td><b>Threshold:</b></td>
            <td>{r.threshold:.1f} kW/m\u00b2</td></tr>
        <tr><td><b>Peak Location:</b></td>
            <td>{loc_str}</td></tr>
        <tr><td><b>Area Exceeding:</b></td>
            <td>{r.area_exceeding:.2f} m\u00b2</td></tr>
        <tr><td><b>Total Receiver Area:</b></td>
            <td>{r.total_receiver_area:.2f} m\u00b2</td></tr>
        <tr><td colspan="2"><hr></td></tr>
        <tr><td><b>Emitter Temperature:</b></td>
            <td>{temp_str}</td></tr>
        <tr><td><b>Ambient Temperature:</b></td>
            <td>{params.get('ambient_c', 20):.0f} \u00b0C</td></tr>
        <tr><td><b>Emissivity:</b></td>
            <td>{params.get('emissivity', 1.0):.2f}</td></tr>
        <tr><td><b>Mesh Resolution:</b></td>
            <td>{params.get('resolution_mm', 500):.0f} mm</td></tr>
        <tr><td><b>Distance Cutoff:</b></td>
            <td>{params.get('cutoff_mm', 50000):.0f} mm</td></tr>
        </table>
        """

        if r.messages:
            html += "<h4>Messages</h4><ul>"
            for msg in r.messages:
                html += f"<li>{msg}</li>"
            html += "</ul>"

        self._summary.setHtml(html)

    def _fill_receiver_results(self):
        r = self._result
        table = self._recv_table
        table.setSortingEnabled(False)
        table.setRowCount(0)

        for entity, flux in r.per_receiver_flux.items():
            row = table.rowCount()
            table.insertRow(row)

            name = getattr(entity, "_name", None) or str(type(entity).__name__)
            max_flux = float(np.max(flux)) if len(flux) > 0 else 0.0
            avg_flux = float(np.mean(flux)) if len(flux) > 0 else 0.0

            # Compute area exceeding for this receiver
            mesh = r.per_receiver_mesh.get(entity)
            if mesh is not None and len(flux) > 0:
                verts = np.asarray(mesh["vertices"], dtype=np.float64)
                faces = np.asarray(mesh["faces"], dtype=np.int32)
                # Compute per-face area
                v0 = verts[faces[:, 0]]
                v1 = verts[faces[:, 1]]
                v2 = verts[faces[:, 2]]
                areas = np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1) / 2.0 / 1e6  # m^2
                exceed_mask = flux >= r.threshold
                area_exc = float(np.sum(areas[exceed_mask]))
                total_area = float(np.sum(areas))
                pct = (area_exc / total_area * 100.0) if total_area > 0 else 0.0
            else:
                area_exc = 0.0
                pct = 0.0

            status = "PASS" if max_flux < r.threshold else "FAIL"
            color = _GREEN if status == "PASS" else _RED

            table.setItem(row, 0, _item(name))
            table.setItem(row, 1, _item(f"{max_flux:.2f}", color))
            table.setItem(row, 2, _item(f"{avg_flux:.2f}"))
            table.setItem(row, 3, _item(f"{area_exc:.2f}"))
            table.setItem(row, 4, _item(f"{pct:.1f}%", color))
            table.setItem(row, 5, _item(status, color, bold=True))

        table.setSortingEnabled(True)

    def _fill_emitter_contributions(self):
        r = self._result
        table = self._emit_table
        table.setSortingEnabled(False)
        table.setRowCount(0)

        total = sum(r.per_emitter_contribution.values())
        if total <= 0:
            total = 1.0  # avoid division by zero

        for entity, contrib in r.per_emitter_contribution.items():
            row = table.rowCount()
            table.insertRow(row)

            name = getattr(entity, "_name", None) or str(type(entity).__name__)
            pct = contrib / total * 100.0

            table.setItem(row, 0, _item(name))
            table.setItem(row, 1, _item(f"{contrib:.2f}"))
            table.setItem(row, 2, _item(f"{pct:.1f}%"))

        table.setSortingEnabled(True)

    # ------------------------------------------------------------------
    # Export

    def _export_pdf(self):
        if not self._result or not _PRINTER_AVAILABLE:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Thermal Radiation Report PDF",
            "thermal_radiation_report.pdf", "PDF Files (*.pdf)"
        )
        if not path:
            return

        doc = QTextDocument()
        doc.setHtml(self._build_html())

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        doc.print_(printer)

    def _export_csv(self):
        if not self._result:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Thermal Radiation Report CSV",
            "thermal_radiation_report.csv", "CSV Files (*.csv)"
        )
        if not path:
            return

        r = self._result

        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)

            # Summary section
            w.writerow(["=== THERMAL RADIATION ANALYSIS SUMMARY ==="])
            w.writerow(["Result", "PASS" if r.passed else "FAIL"])
            w.writerow(["Max Radiation (kW/m2)", f"{r.max_radiation:.2f}"])
            w.writerow(["Threshold (kW/m2)", f"{r.threshold:.1f}"])
            w.writerow(["Area Exceeding (m2)", f"{r.area_exceeding:.2f}"])
            w.writerow(["Total Receiver Area (m2)", f"{r.total_receiver_area:.2f}"])
            w.writerow([])

            # Parameters
            w.writerow(["=== PARAMETERS ==="])
            for k, v in r.parameters.items():
                w.writerow([k, str(v)])
            w.writerow([])

            # Receiver results
            w.writerow(["=== RECEIVER RESULTS ==="])
            w.writerow(["Surface", "Max Flux (kW/m2)", "Avg Flux (kW/m2)", "Status"])
            for entity, flux in r.per_receiver_flux.items():
                name = getattr(entity, "_name", None) or str(type(entity).__name__)
                max_f = float(np.max(flux)) if len(flux) > 0 else 0.0
                avg_f = float(np.mean(flux)) if len(flux) > 0 else 0.0
                status = "PASS" if max_f < r.threshold else "FAIL"
                w.writerow([name, f"{max_f:.2f}", f"{avg_f:.2f}", status])
            w.writerow([])

            # Emitter contributions
            w.writerow(["=== EMITTER CONTRIBUTIONS ==="])
            w.writerow(["Surface", "Total Contribution (kW/m2)"])
            for entity, contrib in r.per_emitter_contribution.items():
                name = getattr(entity, "_name", None) or str(type(entity).__name__)
                w.writerow([name, f"{contrib:.2f}"])

    def _build_html(self) -> str:
        """Build an HTML document for PDF export."""
        r = self._result
        if not r:
            return "<p>No results.</p>"

        ok = r.passed
        status_color = "#006400" if ok else "#a00000"
        status_bg = "#c8f7c8" if ok else "#ffc8c8"
        status_text = "PASS" if ok else "FAIL"

        params = r.parameters
        curve = params.get("fire_curve", "Constant")
        if curve == "Constant":
            temp_str = f"{params.get('emitter_temp_c', 800):.0f} \u00b0C"
        else:
            temp_str = f"{curve} @ {params.get('fire_duration_min', 60):.0f} min"

        html = f"""
        <h1>Thermal Radiation Analysis Report</h1>
        <div style="background:{status_bg};padding:10px;border-radius:4px;
                    text-align:center;font-size:18px;font-weight:bold;
                    color:{status_color};">
            {status_text} &mdash; Max {r.max_radiation:.2f} kW/m&sup2;
            (Threshold: {r.threshold:.1f} kW/m&sup2;)
        </div>

        <h2>Input Parameters</h2>
        <table border="1" cellpadding="4" cellspacing="0">
        <tr><td><b>Emitter Temperature</b></td><td>{temp_str}</td></tr>
        <tr><td><b>Ambient Temperature</b></td>
            <td>{params.get('ambient_c', 20):.0f} &deg;C</td></tr>
        <tr><td><b>Emissivity</b></td>
            <td>{params.get('emissivity', 1.0):.2f}</td></tr>
        <tr><td><b>Mesh Resolution</b></td>
            <td>{params.get('resolution_mm', 500):.0f} mm</td></tr>
        <tr><td><b>Distance Cutoff</b></td>
            <td>{params.get('cutoff_mm', 50000):.0f} mm</td></tr>
        </table>

        <h2>Results Summary</h2>
        <table border="1" cellpadding="4" cellspacing="0">
        <tr><td><b>Maximum Radiation</b></td>
            <td>{r.max_radiation:.2f} kW/m&sup2;</td></tr>
        <tr><td><b>Area Exceeding Threshold</b></td>
            <td>{r.area_exceeding:.2f} m&sup2;</td></tr>
        <tr><td><b>Total Receiver Area</b></td>
            <td>{r.total_receiver_area:.2f} m&sup2;</td></tr>
        </table>

        <h2>Receiver Results</h2>
        <table border="1" cellpadding="4" cellspacing="0">
        <tr><th>Surface</th><th>Max Flux (kW/m&sup2;)</th>
            <th>Avg Flux (kW/m&sup2;)</th><th>Status</th></tr>
        """

        for entity, flux in r.per_receiver_flux.items():
            name = getattr(entity, "_name", None) or str(type(entity).__name__)
            max_f = float(np.max(flux)) if len(flux) > 0 else 0.0
            avg_f = float(np.mean(flux)) if len(flux) > 0 else 0.0
            status = "PASS" if max_f < r.threshold else "FAIL"
            bg = "#c8f7c8" if status == "PASS" else "#ffc8c8"
            html += (
                f'<tr style="background:{bg};">'
                f"<td>{name}</td><td>{max_f:.2f}</td>"
                f"<td>{avg_f:.2f}</td><td><b>{status}</b></td></tr>"
            )

        html += """
        </table>

        <h2>Emitter Contributions</h2>
        <table border="1" cellpadding="4" cellspacing="0">
        <tr><th>Surface</th><th>Total Contribution (kW/m&sup2;)</th></tr>
        """

        for entity, contrib in r.per_emitter_contribution.items():
            name = getattr(entity, "_name", None) or str(type(entity).__name__)
            html += f"<tr><td>{name}</td><td>{contrib:.2f}</td></tr>"

        html += "</table>"

        if r.messages:
            html += "<h2>Messages</h2><ul>"
            for msg in r.messages:
                html += f"<li>{msg}</li>"
            html += "</ul>"

        return html
