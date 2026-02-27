"""
hydraulic_report.py
===================
Sprint 3A/3B — Hydraulic reporting widget.

Provides a QWidget with four tabs:
  1. Summary      — pass/fail banner + system totals + solver messages
  2. Pipe Results — per-pipe flow, velocity, friction loss (with status colours)
  3. Sprinkler Schedule — per-sprinkler K, pressures, actual flow
  4. Pipe Schedule      — pipe sizes, materials, lengths (no flow results needed)

Export:
  • PDF  — rendered via Qt's QPrinter (no external dependency)
  • CSV  — Python built-in csv module
"""

import csv

from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHBoxLayout, QPushButton, QTextBrowser,
    QHeaderView, QFileDialog, QMessageBox,
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

_GREEN  = QColor(210, 245, 215)
_ORANGE = QColor(255, 235, 185)
_RED    = QColor(255, 205, 205)


def _velocity_color(v: float) -> QColor | None:
    if v > 20:
        return _RED
    if v > 12:
        return _ORANGE
    return _GREEN


def _pressure_color(p_act: float | None, p_min: float) -> QColor | None:
    if p_act is None:
        return None
    if p_act < p_min:
        return _RED
    if p_act < p_min * 1.5:
        return _ORANGE
    return _GREEN


# ─────────────────────────────────────────────────────────────────────────────
# Table helpers
# ─────────────────────────────────────────────────────────────────────────────

def _item(text: str, color: QColor | None = None, bold: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    if color:
        it.setBackground(color)
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

class HydraulicReportWidget(QWidget):
    """Tabbed hydraulic report panel embedded in a dock widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result = None
        self._scene  = None
        self._sm     = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── Export buttons ──────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        self._pdf_btn = QPushButton("⬇ Export PDF")
        self._csv_btn = QPushButton("⬇ Export CSV")
        self._pdf_btn.setEnabled(False)
        self._csv_btn.setEnabled(False)
        self._pdf_btn.clicked.connect(self._export_pdf)
        self._csv_btn.clicked.connect(self._export_csv)
        btn_bar.addWidget(self._pdf_btn)
        btn_bar.addWidget(self._csv_btn)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        # ── Tabs ────────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Summary
        self._summary = QTextBrowser()
        self._summary.setOpenExternalLinks(False)
        self._summary.setPlaceholderText(
            "Run hydraulics to see the summary report."
        )
        self.tabs.addTab(self._summary, "Summary")

        # Tab 2: Pipe Results
        self._pipe_res = _make_table([
            "#", "Diameter", "Schedule", "C-Factor",
            "Length", "Flow (gpm)", "Velocity (fps)", "hf (psi)", "Status",
        ])
        self.tabs.addTab(self._pipe_res, "Pipe Results")

        # Tab 3: Sprinkler Schedule
        self._spr_sched = _make_table([
            "#", "K-Factor", "Type", "Orientation", "Temp",
            "Min P (psi)", "Act P (psi)", "Act Q (gpm)", "Coverage (sq ft)",
        ])
        self.tabs.addTab(self._spr_sched, "Sprinkler Schedule")

        # Tab 4: Pipe Schedule
        self._pipe_sched = _make_table([
            "#", "Diameter", "Schedule", "Material", "C-Factor", "Length",
        ])
        self.tabs.addTab(self._pipe_sched, "Pipe Schedule")

    # ------------------------------------------------------------------
    # Public API

    def populate(self, result, scene, sm):
        """Fill all four tabs from a completed HydraulicResult."""
        self._result = result
        self._scene  = scene
        self._sm     = sm

        self._fill_summary()
        self._fill_pipe_results()
        self._fill_sprinkler_schedule()
        self._fill_pipe_schedule()

        self._pdf_btn.setEnabled(_PRINTER_AVAILABLE)
        self._csv_btn.setEnabled(True)

    def clear(self):
        """Reset all tabs to their empty state."""
        self._result = self._scene = self._sm = None
        self._summary.clear()
        for t in (self._pipe_res, self._spr_sched, self._pipe_sched):
            t.setRowCount(0)
        self._pdf_btn.setEnabled(False)
        self._csv_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Tab fillers

    def _fill_summary(self):
        r = self._result
        ok = r.passed
        status_html = (
            "<span style='color:green;font-weight:bold'>✅ PASS</span>"
            if ok else
            "<span style='color:red;font-weight:bold'>❌ FAIL</span>"
        )
        html = f"""
        <h2 style='margin-bottom:4px'>Hydraulic Summary</h2>
        <table style='font-size:12pt;border-collapse:collapse;'>
          <tr><td style='padding:3px 12px'><b>Status</b></td>
              <td>{status_html}</td></tr>
          <tr><td style='padding:3px 12px'><b>Total Demand</b></td>
              <td>{r.total_demand:.1f} gpm</td></tr>
          <tr><td style='padding:3px 12px'><b>Required Pressure</b></td>
              <td>{r.required_pressure:.1f} psi</td></tr>
          <tr><td style='padding:3px 12px'><b>Supply Available</b></td>
              <td>{r.supply_pressure:.1f} psi</td></tr>
        </table>
        """
        if r.messages:
            html += "<br><b>Messages:</b><ul style='margin-top:4px'>"
            for msg in r.messages:
                html += f"<li style='margin-bottom:2px'>{msg}</li>"
            html += "</ul>"
        self._summary.setHtml(html)

    def _fill_pipe_results(self):
        r = self._result
        sm = self._sm
        pipes = sorted(r.pipe_flows.keys(),
                       key=lambda p: r.pipe_flows[p], reverse=True)
        t = self._pipe_res
        t.setSortingEnabled(False)
        t.setRowCount(len(pipes))

        for row, pipe in enumerate(pipes):
            q  = r.pipe_flows.get(pipe, 0.0)
            v  = r.pipe_velocity.get(pipe, 0.0)
            hf = r.pipe_friction_loss.get(pipe, 0.0)
            d  = pipe._properties["Diameter"]["value"]
            sc = pipe._properties["Schedule"]["value"]
            cf = pipe._properties["C-Factor"]["value"]
            length_str = (
                sm.scene_to_display(pipe.length)
                if sm and sm.is_calibrated
                else f"{pipe.length:.0f} px"
            )

            vcol = _velocity_color(v)
            vstatus = (
                "⚠️ HIGH" if v > 20 else
                "⚠️ ELEV" if v > 12 else
                "✅ OK"
            )

            vals = [
                str(row + 1), d, sc, cf, length_str,
                f"{q:.1f}", f"{v:.1f}", f"{hf:.2f}", vstatus,
            ]
            for col, val in enumerate(vals):
                color = vcol if col in (6, 8) else None
                t.setItem(row, col, _item(val, color))

        t.setSortingEnabled(True)

    def _fill_sprinkler_schedule(self):
        r   = self._result
        sprs = list(self._scene.sprinkler_system.sprinklers)
        t = self._spr_sched
        t.setSortingEnabled(False)
        t.setRowCount(len(sprs))

        for row, spr in enumerate(sprs):
            props = spr._properties
            k_str    = props["K-Factor"]["value"]
            spr_type = props["Type"]["value"]
            orient   = props["Orientation"]["value"]
            temp     = props["Temperature"]["value"]
            p_min_s  = props["Min Pressure"]["value"]
            coverage = props["Coverage Area"]["value"]

            try:
                k = float(k_str)
                p_min = float(p_min_s)
            except (ValueError, TypeError):
                k, p_min = 5.6, 7.0

            p_act   = r.node_pressures.get(spr.node, None)
            q_act   = k * (max(p_act, 0.0) ** 0.5) if p_act is not None else None

            p_act_s = f"{p_act:.1f}"  if p_act  is not None else "—"
            q_act_s = f"{q_act:.1f}"  if q_act  is not None else "—"

            pcol = _pressure_color(p_act, p_min)

            vals = [
                str(row + 1), k_str, spr_type, orient, temp,
                p_min_s, p_act_s, q_act_s, coverage,
            ]
            for col, val in enumerate(vals):
                color = pcol if col in (6, 7) else None
                t.setItem(row, col, _item(val, color))

        t.setSortingEnabled(True)

    def _fill_pipe_schedule(self):
        sm    = self._sm
        pipes = self._scene.sprinkler_system.pipes
        t     = self._pipe_sched
        t.setSortingEnabled(False)
        t.setRowCount(len(pipes))

        for row, pipe in enumerate(pipes):
            props = pipe._properties
            d   = props["Diameter"]["value"]
            sc  = props["Schedule"]["value"]
            mat = props["Material"]["value"]
            cf  = props["C-Factor"]["value"]
            length_str = (
                sm.scene_to_display(pipe.length)
                if sm and sm.is_calibrated
                else f"{pipe.length:.0f} px"
            )
            vals = [str(row + 1), d, sc, mat, cf, length_str]
            for col, val in enumerate(vals):
                t.setItem(row, col, _item(val))

        t.setSortingEnabled(True)

    # ------------------------------------------------------------------
    # Export — PDF

    def _export_pdf(self):
        if not self._result or not _PRINTER_AVAILABLE:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Hydraulic Report PDF",
            "hydraulic_report.pdf", "PDF Files (*.pdf)"
        )
        if not path:
            return

        doc = QTextDocument()
        doc.setHtml(self._build_html())

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setPageSize(QPrinter.PageSize.A4)
        doc.print_(printer)

        QMessageBox.information(self, "Export Complete",
                                f"PDF saved to:\n{path}")

    # Export — CSV

    def _export_csv(self):
        if not self._result:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Hydraulic Report CSV",
            "hydraulic_report.csv", "CSV Files (*.csv)"
        )
        if not path:
            return

        r  = self._result
        sm = self._sm

        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)

            # ── Summary ──────────────────────────────────────────────────
            w.writerow(["HYDRAULIC SUMMARY"])
            w.writerow(["Status",             "PASS" if r.passed else "FAIL"])
            w.writerow(["Total Demand (gpm)", f"{r.total_demand:.1f}"])
            w.writerow(["Required Pressure (psi)", f"{r.required_pressure:.1f}"])
            w.writerow(["Supply Available (psi)",  f"{r.supply_pressure:.1f}"])
            w.writerow([])
            if r.messages:
                w.writerow(["Messages"])
                for msg in r.messages:
                    w.writerow(["", msg])
                w.writerow([])

            # ── Pipe Results ──────────────────────────────────────────────
            w.writerow(["PIPE RESULTS"])
            w.writerow(["#", "Diameter", "Schedule", "C-Factor", "Length",
                        "Flow (gpm)", "Velocity (fps)", "hf (psi)"])
            for i, (pipe, q) in enumerate(
                sorted(r.pipe_flows.items(), key=lambda x: x[1], reverse=True), 1
            ):
                v  = r.pipe_velocity.get(pipe, 0.0)
                hf = r.pipe_friction_loss.get(pipe, 0.0)
                d  = pipe._properties["Diameter"]["value"]
                sc = pipe._properties["Schedule"]["value"]
                cf = pipe._properties["C-Factor"]["value"]
                length_str = (
                    sm.scene_to_display(pipe.length)
                    if sm and sm.is_calibrated
                    else f"{pipe.length:.0f} px"
                )
                w.writerow([i, d, sc, cf, length_str,
                            f"{q:.1f}", f"{v:.1f}", f"{hf:.2f}"])
            w.writerow([])

            # ── Sprinkler Schedule ────────────────────────────────────────
            w.writerow(["SPRINKLER SCHEDULE"])
            w.writerow(["#", "K-Factor", "Type", "Orientation", "Temperature",
                        "Min P (psi)", "Act P (psi)", "Act Q (gpm)", "Coverage (sq ft)"])
            for i, spr in enumerate(self._scene.sprinkler_system.sprinklers, 1):
                p  = spr._properties
                k_str = p["K-Factor"]["value"]
                try:
                    k = float(k_str)
                except (ValueError, TypeError):
                    k = 5.6
                p_act = r.node_pressures.get(spr.node, None)
                q_act = k * (max(p_act, 0.0) ** 0.5) if p_act is not None else None
                w.writerow([
                    i, k_str,
                    p["Type"]["value"], p["Orientation"]["value"], p["Temperature"]["value"],
                    p["Min Pressure"]["value"],
                    f"{p_act:.1f}" if p_act is not None else "",
                    f"{q_act:.1f}" if q_act is not None else "",
                    p["Coverage Area"]["value"],
                ])
            w.writerow([])

            # ── Pipe Schedule ─────────────────────────────────────────────
            w.writerow(["PIPE SCHEDULE"])
            w.writerow(["#", "Diameter", "Schedule", "Material", "C-Factor", "Length"])
            for i, pipe in enumerate(self._scene.sprinkler_system.pipes, 1):
                p = pipe._properties
                length_str = (
                    sm.scene_to_display(pipe.length)
                    if sm and sm.is_calibrated
                    else f"{pipe.length:.0f} px"
                )
                w.writerow([
                    i, p["Diameter"]["value"], p["Schedule"]["value"],
                    p["Material"]["value"], p["C-Factor"]["value"], length_str,
                ])

        QMessageBox.information(self, "Export Complete",
                                f"CSV saved to:\n{path}")

    # ------------------------------------------------------------------
    # HTML builder (used by PDF export)

    def _build_html(self) -> str:
        r  = self._result
        sm = self._sm

        css = """
        body { font-family: Arial, sans-serif; font-size: 10pt; }
        h2   { color: #1a3c6e; border-bottom: 2px solid #1a3c6e; padding-bottom:4px; }
        h3   { color: #336699; margin-top: 18px; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 16px; }
        th { background: #1a3c6e; color: white; padding: 5px 8px; text-align: center; }
        td { padding: 3px 8px; border: 1px solid #ccc; text-align: center; }
        tr:nth-child(even) { background: #f5f5f5; }
        .pass { color: #007700; font-weight: bold; }
        .fail { color: #cc0000; font-weight: bold; }
        .ok   { background: #d2f5d7; }
        .warn { background: #ffebb8; }
        .bad  { background: #ffcdcd; }
        ul    { margin-top: 4px; }
        li    { margin-bottom: 3px; }
        """

        ok  = r.passed
        html = f"<html><head><style>{css}</style></head><body>"
        html += "<h2>Hydraulic Calculation Report — NFPA 13</h2>"

        # Summary table
        sc = "pass" if ok else "fail"
        st = "PASS" if ok else "FAIL"
        html += f"""<h3>System Summary</h3>
        <table>
          <tr><th>Item</th><th>Value</th></tr>
          <tr><td>Status</td>
              <td class='{sc}'>{st}</td></tr>
          <tr><td>Total Demand</td>
              <td>{r.total_demand:.1f} gpm</td></tr>
          <tr><td>Required Pressure at Supply</td>
              <td>{r.required_pressure:.1f} psi</td></tr>
          <tr><td>Supply Pressure Available</td>
              <td>{r.supply_pressure:.1f} psi</td></tr>
        </table>"""

        if r.messages:
            html += "<h3>Analysis Messages</h3><ul>"
            for msg in r.messages:
                html += f"<li>{msg}</li>"
            html += "</ul>"

        # Pipe results
        html += """<h3>Pipe Results</h3>
        <table>
          <tr><th>#</th><th>Diameter</th><th>Schedule</th><th>C-Factor</th>
              <th>Length</th><th>Flow (gpm)</th><th>Velocity (fps)</th>
              <th>hf (psi)</th><th>Status</th></tr>"""
        for i, (pipe, q) in enumerate(
            sorted(r.pipe_flows.items(), key=lambda x: x[1], reverse=True), 1
        ):
            v  = r.pipe_velocity.get(pipe, 0.0)
            hf = r.pipe_friction_loss.get(pipe, 0.0)
            d  = pipe._properties["Diameter"]["value"]
            sc = pipe._properties["Schedule"]["value"]
            cf = pipe._properties["C-Factor"]["value"]
            length_str = (
                sm.scene_to_display(pipe.length)
                if sm and sm.is_calibrated else f"{pipe.length:.0f} px"
            )
            vcls = "bad" if v > 20 else "warn" if v > 12 else "ok"
            vstatus = "⚠ HIGH" if v > 20 else "⚠ ELEV" if v > 12 else "OK"
            html += (
                f"<tr><td>{i}</td><td>{d}</td><td>{sc}</td><td>{cf}</td>"
                f"<td>{length_str}</td><td>{q:.1f}</td>"
                f"<td class='{vcls}'>{v:.1f}</td><td>{hf:.2f}</td>"
                f"<td class='{vcls}'>{vstatus}</td></tr>"
            )
        html += "</table>"

        # Sprinkler schedule
        html += """<h3>Sprinkler Schedule</h3>
        <table>
          <tr><th>#</th><th>K-Factor</th><th>Type</th><th>Orientation</th>
              <th>Temperature</th><th>Min P (psi)</th><th>Act P (psi)</th>
              <th>Act Q (gpm)</th><th>Coverage (sq ft)</th></tr>"""
        for i, spr in enumerate(self._scene.sprinkler_system.sprinklers, 1):
            p     = spr._properties
            k_str = p["K-Factor"]["value"]
            try:
                k     = float(k_str)
                p_min = float(p["Min Pressure"]["value"])
            except (ValueError, TypeError):
                k, p_min = 5.6, 7.0
            p_act = r.node_pressures.get(spr.node, None)
            q_act = k * (max(p_act, 0.0) ** 0.5) if p_act is not None else None
            p_act_s = f"{p_act:.1f}" if p_act is not None else "—"
            q_act_s = f"{q_act:.1f}" if q_act is not None else "—"
            pcls = (
                "bad"  if p_act is not None and p_act < p_min else
                "warn" if p_act is not None and p_act < p_min * 1.5 else
                "ok"   if p_act is not None else ""
            )
            html += (
                f"<tr><td>{i}</td><td>{k_str}</td>"
                f"<td>{p['Type']['value']}</td><td>{p['Orientation']['value']}</td>"
                f"<td>{p['Temperature']['value']}</td>"
                f"<td>{p['Min Pressure']['value']}</td>"
                f"<td class='{pcls}'>{p_act_s}</td>"
                f"<td class='{pcls}'>{q_act_s}</td>"
                f"<td>{p['Coverage Area']['value']}</td></tr>"
            )
        html += "</table>"

        # Pipe schedule
        html += """<h3>Pipe Schedule</h3>
        <table>
          <tr><th>#</th><th>Diameter</th><th>Schedule</th>
              <th>Material</th><th>C-Factor</th><th>Length</th></tr>"""
        for i, pipe in enumerate(self._scene.sprinkler_system.pipes, 1):
            p = pipe._properties
            length_str = (
                sm.scene_to_display(pipe.length)
                if sm and sm.is_calibrated else f"{pipe.length:.0f} px"
            )
            html += (
                f"<tr><td>{i}</td><td>{p['Diameter']['value']}</td>"
                f"<td>{p['Schedule']['value']}</td><td>{p['Material']['value']}</td>"
                f"<td>{p['C-Factor']['value']}</td><td>{length_str}</td></tr>"
            )
        html += "</table>"

        html += "</body></html>"
        return html
