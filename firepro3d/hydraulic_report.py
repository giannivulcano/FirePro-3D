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
import math

from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHBoxLayout, QPushButton, QTextBrowser,
    QHeaderView, QFileDialog, QMessageBox, QCheckBox,
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QTextDocument, QPainter, QPen, QFont, QBrush, QPainterPath

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

# Dark text colours for coloured fills (legible on light cell backgrounds)
_TEXT_GREEN  = QColor(0, 100, 0)       # dark green
_TEXT_ORANGE = QColor(160, 120, 0)     # dark yellow / amber
_TEXT_RED    = QColor(160, 0, 0)       # dark red

# Map fill → text colour
_TEXT_FOR_BG = {
    _GREEN.rgb():  _TEXT_GREEN,
    _ORANGE.rgb(): _TEXT_ORANGE,
    _RED.rgb():    _TEXT_RED,
}


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
        fg = _TEXT_FOR_BG.get(color.rgb())
        if fg:
            it.setForeground(fg)
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
# Hydraulic Graph (Pressure vs Flow with semi-exponential X axis)
# ─────────────────────────────────────────────────────────────────────────────

class _HydraulicGraphWidget(QWidget):
    """Custom painted graph: Pressure (Y) vs Flow (X, Q^1.85 scale).

    The X-axis is *semi-exponential*: screen position is proportional to
    Q^1.85.  This makes the NFPA supply curve a straight line.
    """

    _MARGIN_L = 60
    _MARGIN_R = 20
    _MARGIN_T = 20
    _MARGIN_B = 50

    def __init__(self, parent=None):
        super().__init__(parent)
        self._p_static = 0.0       # psi at 0 gpm
        self._p_residual = 0.0     # psi at test flow
        self._q_test = 0.0         # gpm at residual
        self._q_demand = 0.0       # system demand flow (gpm)
        self._p_demand = 0.0       # system required pressure (psi)
        self._q_max = 1000.0       # x-axis upper bound (gpm)
        self._p_max = 100.0        # y-axis upper bound (psi)
        self.setMinimumHeight(300)

    def set_supply_data(self, p_static: float, p_residual: float, q_test: float):
        """Set the two-point supply curve data."""
        self._p_static = max(p_static, 0.0)
        self._p_residual = max(p_residual, 0.0)
        self._q_test = max(q_test, 0.0)
        self._recalc_axes()
        self.update()

    def set_demand_point(self, q_demand: float, p_required: float):
        """Set the system demand operating point for plotting."""
        self._q_demand = max(q_demand, 0.0)
        self._p_demand = max(p_required, 0.0)
        self._recalc_axes()
        self.update()

    def _recalc_axes(self):
        """Recompute axis ranges to encompass plotted data points only.

        X: nearest 100 GPM above the greatest plotted point (Q_test or Q_demand).
           The extended supply-curve line is intentionally ignored.
        Y: nearest 10 PSI above the greatest plotted point, plus 10 PSI padding.
        """
        q_hi = max(self._q_test, self._q_demand)
        p_hi = max(self._p_static, self._p_demand)
        self._q_max = max(math.ceil(q_hi / 100) * 100, 100) + 100
        self._p_max = max(math.ceil(p_hi / 10) * 10, 10) + 10

    # ── Coordinate mapping ──────────────────────────────────────────────

    def _plot_rect(self) -> QRectF:
        w, h = self.width(), self.height()
        return QRectF(self._MARGIN_L, self._MARGIN_T,
                      w - self._MARGIN_L - self._MARGIN_R,
                      h - self._MARGIN_T - self._MARGIN_B)

    def _q_to_x(self, q: float, rect: QRectF) -> float:
        """Map flow (gpm) to pixel X using Q^1.85 scale."""
        q = max(q, 0.0)
        q_norm = (q / self._q_max) ** 1.85 if self._q_max > 0 else 0.0
        return rect.left() + q_norm * rect.width()

    def _p_to_y(self, p: float, rect: QRectF) -> float:
        """Map pressure (psi) to pixel Y (linear, 0 at bottom)."""
        p = max(p, 0.0)
        p_norm = p / self._p_max if self._p_max > 0 else 0.0
        return rect.bottom() - p_norm * rect.height()

    # ── Supply curve evaluation ─────────────────────────────────────────

    def _supply_pressure_at(self, q: float) -> float:
        """NFPA supply curve: P = Ps - (Ps - Pr) * (Q/Qt)^1.85."""
        if self._q_test <= 0 or q <= 0:
            return self._p_static
        ratio = (q / self._q_test) ** 1.85
        return max(self._p_static - (self._p_static - self._p_residual) * ratio, 0.0)

    # ── Painting ────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()

        # Background
        p.fillRect(self.rect(), QColor(255, 255, 255))

        # Grid & axes
        self._draw_grid(p, rect)
        self._draw_axes(p, rect)

        # Supply curve (straight line on Q^1.85 scale)
        if self._q_test > 0 and self._p_static > 0:
            self._draw_supply_curve(p, rect)

        # System demand point
        if self._q_demand > 0 and self._p_demand > 0:
            self._draw_demand_point(p, rect)

        p.end()

    def _draw_grid(self, p: QPainter, rect: QRectF):
        grid_pen = QPen(QColor(220, 220, 220), 1, Qt.PenStyle.DotLine)
        p.setPen(grid_pen)

        # Horizontal grid (pressure, every 10 psi)
        step_p = 10
        pv = step_p
        while pv < self._p_max:
            y = self._p_to_y(pv, rect)
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            pv += step_p

        # Vertical grid (flow, every 100 gpm) — mapped through Q^1.85
        step_q = 100
        qv = step_q
        while qv < self._q_max:
            x = self._q_to_x(qv, rect)
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            qv += step_q

    def _draw_axes(self, p: QPainter, rect: QRectF):
        axis_pen = QPen(QColor(0, 0, 0), 2)
        p.setPen(axis_pen)

        # X axis (bottom)
        p.drawLine(QPointF(rect.left(), rect.bottom()),
                   QPointF(rect.right(), rect.bottom()))
        # Y axis (left)
        p.drawLine(QPointF(rect.left(), rect.top()),
                   QPointF(rect.left(), rect.bottom()))

        # Tick labels
        label_font = QFont("Arial", 8)
        p.setFont(label_font)
        p.setPen(QPen(QColor(0, 0, 0)))

        # X tick labels (flow, every 100 gpm)
        qv = 0
        while qv <= self._q_max:
            x = self._q_to_x(qv, rect)
            # Tick mark
            p.drawLine(QPointF(x, rect.bottom()), QPointF(x, rect.bottom() + 5))
            # Label
            label_rect = QRectF(x - 25, rect.bottom() + 6, 50, 20)
            p.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, str(int(qv)))
            qv += 100

        # Y tick labels (pressure, every 10 psi)
        pv = 0
        while pv <= self._p_max:
            y = self._p_to_y(pv, rect)
            # Tick mark
            p.drawLine(QPointF(rect.left() - 5, y), QPointF(rect.left(), y))
            # Label
            label_rect = QRectF(rect.left() - 55, y - 10, 50, 20)
            p.drawText(label_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       str(int(pv)))
            pv += 10

        # Axis titles
        title_font = QFont("Arial", 9, QFont.Weight.Bold)
        p.setFont(title_font)
        # X title
        x_title_rect = QRectF(rect.left(), rect.bottom() + 28,
                               rect.width(), 20)
        p.drawText(x_title_rect, Qt.AlignmentFlag.AlignCenter, "Flow (GPM)")
        # Y title (rotated)
        p.save()
        p.translate(14, rect.center().y())
        p.rotate(-90)
        p.drawText(QRectF(-60, -10, 120, 20), Qt.AlignmentFlag.AlignCenter,
                   "Pressure (PSI)")
        p.restore()

    def _draw_supply_curve(self, p: QPainter, rect: QRectF):
        """Draw the supply curve — straight line on Q^1.85 X-axis."""
        supply_pen = QPen(QColor(0, 100, 200), 3)
        p.setPen(supply_pen)

        # Two known points: (0, P_static) and (Q_test, P_residual)
        x1 = self._q_to_x(0, rect)
        y1 = self._p_to_y(self._p_static, rect)
        x2 = self._q_to_x(self._q_test, rect)
        y2 = self._p_to_y(self._p_residual, rect)

        # Extend line to right edge of graph
        # On Q^1.85 scale this IS a straight line, so just extend
        if abs(x2 - x1) > 0.1:
            slope = (y2 - y1) / (x2 - x1)
            x_end = rect.right()
            y_end = y1 + slope * (x_end - x1)
            # Clip to plot area bottom
            if y_end > rect.bottom():
                x_end = x1 + (rect.bottom() - y1) / slope if slope != 0 else x_end
                y_end = rect.bottom()
            p.drawLine(QPointF(x1, y1), QPointF(x_end, y_end))
        else:
            # Horizontal line at static pressure
            p.drawLine(QPointF(x1, y1), QPointF(rect.right(), y1))

        # Plot the two data points
        point_pen = QPen(QColor(0, 100, 200), 2)
        p.setPen(point_pen)
        p.setBrush(QBrush(QColor(0, 100, 200)))
        p.drawEllipse(QPointF(x1, y1), 5, 5)
        p.drawEllipse(QPointF(x2, y2), 5, 5)

        # Labels
        label_font = QFont("Arial", 8)
        p.setFont(label_font)
        p.setPen(QPen(QColor(0, 70, 160)))
        p.drawText(QPointF(x1 + 8, y1 - 8),
                   f"0 GPM @ {self._p_static:.0f} PSI")
        p.drawText(QPointF(x2 + 8, y2 - 8),
                   f"{self._q_test:.0f} GPM @ {self._p_residual:.0f} PSI")

    def _draw_demand_point(self, p: QPainter, rect: QRectF):
        """Plot the system demand operating point as a red marker."""
        x = self._q_to_x(self._q_demand, rect)
        y = self._p_to_y(self._p_demand, rect)
        # Red dot
        p.setPen(QPen(QColor(200, 0, 0), 2))
        p.setBrush(QBrush(QColor(200, 0, 0)))
        p.drawEllipse(QPointF(x, y), 6, 6)
        # Label
        label_font = QFont("Arial", 8, QFont.Weight.Bold)
        p.setFont(label_font)
        p.setPen(QPen(QColor(180, 0, 0)))
        p.drawText(QPointF(x + 10, y - 10),
                   f"Demand: {self._q_demand:.0f} GPM @ {self._p_demand:.1f} PSI")


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
            "#", "From", "To", "Diameter", "Schedule", "C-Factor",
            "Length", "Flow (gpm)", "Velocity (fps)", "hf (psi)", "Status",
        ])
        pipe_res_container = QWidget()
        pipe_res_layout = QVBoxLayout(pipe_res_container)
        pipe_res_layout.setContentsMargins(0, 0, 0, 0)
        self._show_minor_cb = QCheckBox("Show minor nodes")
        self._show_minor_cb.setChecked(False)
        self._show_minor_cb.toggled.connect(self._on_minor_toggle)
        pipe_res_layout.addWidget(self._show_minor_cb)
        pipe_res_layout.addWidget(self._pipe_res)
        self.tabs.addTab(pipe_res_container, "Pipe Results")

        # Tab 3: Sprinkler Schedule
        self._spr_sched = _make_table([
            "#", "Node", "K-Factor", "Model", "Orientation", "Temp",
            "Min P (psi)", "Act P (psi)", "Act Q (gpm)", "Coverage (sq ft)",
            "S Spacing", "L Spacing",
        ])
        self.tabs.addTab(self._spr_sched, "Sprinkler Schedule")

        # Tab 4: Pipe Schedule
        self._pipe_sched = _make_table([
            "#", "Diameter", "Schedule", "Material", "C-Factor", "Length",
        ])
        self.tabs.addTab(self._pipe_sched, "Pipe Schedule")

        # Tab 5: Hydraulic Graph
        self._graph = _HydraulicGraphWidget()
        self.tabs.addTab(self._graph, "Hydraulic Graph")

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
        self._fill_graph()

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

    def _on_minor_toggle(self, checked: bool):
        """Re-fill the pipe results table when minor-node visibility changes."""
        if self._result:
            self._fill_pipe_results()

    def _fill_pipe_results(self):
        r = self._result
        sm = self._sm
        nn = getattr(r, 'node_labels', None) or (r.node_numbers if hasattr(r, 'node_numbers') else {})
        show_minor = self._show_minor_cb.isChecked()

        pipes = sorted(r.pipe_flows.keys(),
                       key=lambda p: r.pipe_flows[p], reverse=True)

        # Filter to calc-path pipes only; optionally hide minor-node pipes
        filtered = []
        for pipe in pipes:
            l1 = nn.get(pipe.node1) if pipe.node1 else None
            l2 = nn.get(pipe.node2) if pipe.node2 else None
            if l1 is None and l2 is None:
                continue  # not on calc path
            if not show_minor:
                # Hide pipes where BOTH nodes are minor (non-digit label)
                l1_major = l1 is not None and str(l1).isdigit()
                l2_major = l2 is not None and str(l2).isdigit()
                if not l1_major and not l2_major:
                    continue
            filtered.append(pipe)

        t = self._pipe_res
        t.setSortingEnabled(False)
        t.setRowCount(len(filtered))

        for row, pipe in enumerate(filtered):
            q  = r.pipe_flows.get(pipe, 0.0)
            v  = r.pipe_velocity.get(pipe, 0.0)
            hf = r.pipe_friction_loss.get(pipe, 0.0)
            d  = pipe._properties["Diameter"]["value"]
            sc = pipe._properties["Schedule"]["value"]
            cf = pipe._properties["C-Factor"]["value"]
            length_str = (
                sm.scene_to_display(pipe.length)
                if sm
                else f"{pipe.length:.0f} px"
            )

            # Node labels for From / To columns
            n1_num = str(nn.get(pipe.node1, "—")) if pipe.node1 else "—"
            n2_num = str(nn.get(pipe.node2, "—")) if pipe.node2 else "—"

            vcol = _velocity_color(v)
            vstatus = (
                "⚠️ HIGH" if v > 20 else
                "⚠️ ELEV" if v > 12 else
                "✅ OK"
            )

            vals = [
                str(row + 1), n1_num, n2_num, d, sc, cf, length_str,
                f"{q:.1f}", f"{v:.1f}", f"{hf:.2f}", vstatus,
            ]
            for col, val in enumerate(vals):
                color = vcol if col in (8, 10) else None
                t.setItem(row, col, _item(val, color))

        t.setSortingEnabled(True)

    def _fill_sprinkler_schedule(self):
        r   = self._result
        nn  = getattr(r, 'node_labels', None) or (r.node_numbers if hasattr(r, 'node_numbers') else {})
        sprs = list(self._scene.sprinkler_system.sprinklers)
        t = self._spr_sched
        t.setSortingEnabled(False)
        t.setRowCount(len(sprs))

        for row, spr in enumerate(sprs):
            props = spr._properties
            k_str    = props["K-Factor"]["value"]
            spr_model = props["Model"]["value"]
            orient   = props["Orientation"]["value"]
            temp     = props["Temperature"]["value"]
            p_min_s  = props["Min Pressure"]["value"]
            coverage = props["Coverage Area"]["value"]
            s_spacing = props.get("S Spacing", {}).get("value", "---")
            l_spacing = props.get("L Spacing", {}).get("value", "---")

            try:
                k = float(k_str)
                p_min = float(p_min_s)
            except (ValueError, TypeError):
                k, p_min = 5.6, 7.0

            p_act   = r.node_pressures.get(spr.node, None)
            q_act   = k * (max(p_act, 0.0) ** 0.5) if p_act is not None else None

            p_act_s = f"{p_act:.1f}"  if p_act  is not None else "—"
            q_act_s = f"{q_act:.1f}"  if q_act  is not None else "—"

            node_num = str(nn.get(spr.node, "—"))

            pcol = _pressure_color(p_act, p_min)

            vals = [
                str(row + 1), node_num, k_str, spr_model, orient, temp,
                p_min_s, p_act_s, q_act_s, coverage, s_spacing, l_spacing,
            ]
            for col, val in enumerate(vals):
                color = pcol if col in (7, 8) else None
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
                if sm
                else f"{pipe.length:.0f} px"
            )
            vals = [str(row + 1), d, sc, mat, cf, length_str]
            for col, val in enumerate(vals):
                t.setItem(row, col, _item(val))

        t.setSortingEnabled(True)

    def _fill_graph(self):
        """Populate the hydraulic graph with supply curve and demand data."""
        ws = getattr(self._scene, "water_supply_node", None)
        if ws is not None:
            self._graph.set_supply_data(
                ws.static_pressure, ws.residual_pressure, ws.test_flow
            )
        if self._result and self._result.total_demand > 0:
            self._graph.set_demand_point(
                self._result.total_demand, self._result.required_pressure
            )

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
            nn = getattr(r, 'node_labels', None) or (r.node_numbers if hasattr(r, 'node_numbers') else {})
            w.writerow(["PIPE RESULTS"])
            w.writerow(["#", "From", "To", "Diameter", "Schedule", "C-Factor",
                        "Length", "Flow (gpm)", "Velocity (fps)", "hf (psi)"])
            for i, (pipe, q) in enumerate(
                sorted(r.pipe_flows.items(), key=lambda x: x[1], reverse=True), 1
            ):
                v  = r.pipe_velocity.get(pipe, 0.0)
                hf = r.pipe_friction_loss.get(pipe, 0.0)
                d  = pipe._properties["Diameter"]["value"]
                sc = pipe._properties["Schedule"]["value"]
                cf = pipe._properties["C-Factor"]["value"]
                n1 = nn.get(pipe.node1, "") if pipe.node1 else ""
                n2 = nn.get(pipe.node2, "") if pipe.node2 else ""
                length_str = (
                    sm.scene_to_display(pipe.length)
                    if sm and sm.is_calibrated
                    else f"{pipe.length:.0f} px"
                )
                w.writerow([i, n1, n2, d, sc, cf, length_str,
                            f"{q:.1f}", f"{v:.1f}", f"{hf:.2f}"])
            w.writerow([])

            # ── Sprinkler Schedule ────────────────────────────────────────
            w.writerow(["SPRINKLER SCHEDULE"])
            w.writerow(["#", "Node", "K-Factor", "Model", "Orientation", "Temperature",
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
                node_num = nn.get(spr.node, "")
                w.writerow([
                    i, node_num, k_str,
                    p["Model"]["value"], p["Orientation"]["value"], p["Temperature"]["value"],
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
        .ok   { background: #d2f5d7; color: #006400; }
        .warn { background: #ffebb8; color: #a07800; }
        .bad  { background: #ffcdcd; color: #a00000; }
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
        nn = r.node_numbers if hasattr(r, 'node_numbers') else {}
        html += """<h3>Pipe Results</h3>
        <table>
          <tr><th>#</th><th>From</th><th>To</th><th>Diameter</th><th>Schedule</th>
              <th>C-Factor</th><th>Length</th><th>Flow (gpm)</th>
              <th>Velocity (fps)</th><th>hf (psi)</th><th>Status</th></tr>"""
        for i, (pipe, q) in enumerate(
            sorted(r.pipe_flows.items(), key=lambda x: x[1], reverse=True), 1
        ):
            v  = r.pipe_velocity.get(pipe, 0.0)
            hf = r.pipe_friction_loss.get(pipe, 0.0)
            d  = pipe._properties["Diameter"]["value"]
            sc = pipe._properties["Schedule"]["value"]
            cf = pipe._properties["C-Factor"]["value"]
            n1 = nn.get(pipe.node1, "—") if pipe.node1 else "—"
            n2 = nn.get(pipe.node2, "—") if pipe.node2 else "—"
            length_str = (
                sm.scene_to_display(pipe.length)
                if sm else f"{pipe.length:.0f} px"
            )
            vcls = "bad" if v > 20 else "warn" if v > 12 else "ok"
            vstatus = "⚠ HIGH" if v > 20 else "⚠ ELEV" if v > 12 else "OK"
            html += (
                f"<tr><td>{i}</td><td>{n1}</td><td>{n2}</td>"
                f"<td>{d}</td><td>{sc}</td><td>{cf}</td>"
                f"<td>{length_str}</td><td>{q:.1f}</td>"
                f"<td class='{vcls}'>{v:.1f}</td><td>{hf:.2f}</td>"
                f"<td class='{vcls}'>{vstatus}</td></tr>"
            )
        html += "</table>"

        # Sprinkler schedule
        html += """<h3>Sprinkler Schedule</h3>
        <table>
          <tr><th>#</th><th>Node</th><th>K-Factor</th><th>Model</th><th>Orientation</th>
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
            node_num = nn.get(spr.node, "—")
            pcls = (
                "bad"  if p_act is not None and p_act < p_min else
                "warn" if p_act is not None and p_act < p_min * 1.5 else
                "ok"   if p_act is not None else ""
            )
            html += (
                f"<tr><td>{i}</td><td>{node_num}</td><td>{k_str}</td>"
                f"<td>{p['Model']['value']}</td><td>{p['Orientation']['value']}</td>"
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
                if sm else f"{pipe.length:.0f} px"
            )
            html += (
                f"<tr><td>{i}</td><td>{p['Diameter']['value']}</td>"
                f"<td>{p['Schedule']['value']}</td><td>{p['Material']['value']}</td>"
                f"<td>{p['C-Factor']['value']}</td><td>{length_str}</td></tr>"
            )
        html += "</table>"

        html += "</body></html>"
        return html
