"""
hydraulic_report.py
===================
Hydraulic reporting widget (NFPA-format 3-tab report).

Provides a QWidget with three tabs:
  1. Summary            — pass/fail banner, project metadata, design criteria,
                          water supply data, results, solver messages
  2. Node Summary Table — NFPA calc-sheet: one row per calc-path node with
                          the pipe leading to it from upstream
  3. Hydraulic Graph    — supply curve vs demand on a Q^1.85 axis

Export:
  • PDF  — rendered via Qt's QPrinter (no external dependency)
  • CSV  — Python built-in csv module
"""

import csv
import html
import math
import os
import re

from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHBoxLayout, QPushButton, QTextBrowser,
    QHeaderView, QFileDialog, QMessageBox, QCheckBox,
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QUrl
from PyQt6.QtGui import (QColor, QTextDocument, QPainter, QPen, QFont, QBrush,
                         QPainterPath, QImage, QPageSize)

try:
    from PyQt6.QtPrintSupport import QPrinter
    _PRINTER_AVAILABLE = True
except ImportError:
    _PRINTER_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Table helpers
# ─────────────────────────────────────────────────────────────────────────────

def _item(text: str, bold: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
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
# Report data-assembly helpers
# ─────────────────────────────────────────────────────────────────────────────

_DASH = "—"

NODE_SUMMARY_HEADERS = [
    "Node #", "Elev (ft)", "Flow (gpm)", "Diameter", "Length (ft)",
    "Equiv (ft)", "Total (ft)", "C-Factor", "psi/ft", "Total hf (psi)",
    "Req P (psi)", "Act P (psi)", "Velocity (fps)", "Notes",
]

_FITTING_NOTE_LABELS = {
    "90elbow": "90° Elbow", "45elbow": "45° Elbow",
    "elbow_up": "90° Elbow (up)", "elbow_down": "90° Elbow (down)",
    "tee": "Tee", "tee_up": "Tee (up)", "tee_down": "Tee (down)",
    "wye": "Wye", "cross": "Cross", "cap": "Cap",
}


def _label_sort_key(label: str):
    """BFS-order sort key for node labels: '1' < '2' < '2a' < '3' < '10'."""
    m = re.match(r"(\d+)([a-z]*)", str(label))
    if not m:
        return (10 ** 9, str(label))
    return (int(m.group(1)), m.group(2))



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
        self._q_sprinkler = 0.0    # sprinkler-only demand (gpm)
        self._hose_stream = 0.0    # hose stream allowance (gpm)
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

    def set_demand_points(self, q_sprinkler: float, hose_stream: float,
                          p_required: float):
        """Set demand with separate sprinkler and hose stream components.

        Args:
            q_sprinkler: Sprinkler demand flow (gpm).
            hose_stream: Hose stream allowance (gpm).
            p_required: Required pressure at supply (psi).
        """
        self._q_sprinkler = max(q_sprinkler, 0.0)
        self._hose_stream = max(hose_stream, 0.0)
        self._q_demand = self._q_sprinkler + self._hose_stream
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
        label_font = QFont("Arial", 8, QFont.Weight.Bold)
        p.setFont(label_font)
        p.setPen(QPen(QColor(0, 70, 160)))
        p.drawText(QPointF(x1 + 8, y1 - 8),
                   f"0 GPM @ {self._p_static:.0f} PSI")
        p.drawText(QPointF(x2 + 8, y2 - 8),
                   f"{self._q_test:.0f} GPM @ {self._p_residual:.0f} PSI")

    def _draw_demand_point(self, p: QPainter, rect: QRectF):
        """Plot demand markers: origin, sprinkler point, and hose stream point."""
        label_font = QFont("Arial", 8, QFont.Weight.Bold)

        # Gray dot at origin (0, 0)
        x0 = self._q_to_x(0, rect)
        y0 = self._p_to_y(0, rect)
        p.setPen(QPen(QColor(140, 140, 140), 2))
        p.setBrush(QBrush(QColor(140, 140, 140)))
        p.drawEllipse(QPointF(x0, y0), 5, 5)

        # Red dot at sprinkler demand point
        q_spr = self._q_sprinkler if self._q_sprinkler > 0 else self._q_demand
        x_spr = self._q_to_x(q_spr, rect)
        y_spr = self._p_to_y(self._p_demand, rect)

        # Dashed line from origin to sprinkler demand point
        dash_pen = QPen(QColor(180, 0, 0), 2, Qt.PenStyle.DashLine)
        p.setPen(dash_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(x0, y0), QPointF(x_spr, y_spr))

        # Sprinkler demand marker
        p.setPen(QPen(QColor(200, 0, 0), 2))
        p.setBrush(QBrush(QColor(200, 0, 0)))
        p.drawEllipse(QPointF(x_spr, y_spr), 6, 6)
        p.setFont(label_font)
        p.setPen(QPen(QColor(180, 0, 0)))
        p.drawText(QPointF(x_spr + 10, y_spr - 10),
                   f"Sprinkler: {q_spr:.0f} GPM @ {self._p_demand:.1f} PSI")

        # Red dot at total demand (sprinkler + hose) — only when hose > 0
        if self._hose_stream > 0:
            x_total = self._q_to_x(self._q_demand, rect)
            y_total = self._p_to_y(self._p_demand, rect)

            # Dashed line between sprinkler and total demand points
            p.setPen(dash_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(QPointF(x_spr, y_spr), QPointF(x_total, y_total))

            # Total demand marker
            p.setPen(QPen(QColor(200, 0, 0), 2))
            p.setBrush(QBrush(QColor(200, 0, 0)))
            p.drawEllipse(QPointF(x_total, y_total), 6, 6)
            p.setFont(label_font)
            p.setPen(QPen(QColor(180, 0, 0)))
            p.drawText(QPointF(x_total + 10, y_total + 16),
                       f"Total: {self._q_demand:.0f} GPM @ {self._p_demand:.1f} PSI")


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
        self._ref_btn = QPushButton("Equiv. Length Table")
        self._ref_btn.clicked.connect(self._show_equiv_length_ref)
        btn_bar.addWidget(self._ref_btn)
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

        # Tab 2: Node Summary Table (NFPA calc-sheet format)
        self._node_table = _make_table(NODE_SUMMARY_HEADERS)
        node_container = QWidget()
        node_layout = QVBoxLayout(node_container)
        node_layout.setContentsMargins(0, 0, 0, 0)
        self._show_minor_cb = QCheckBox("Show minor nodes")
        self._show_minor_cb.setChecked(False)
        self._show_minor_cb.toggled.connect(self._on_minor_toggle)
        node_layout.addWidget(self._show_minor_cb)
        node_layout.addWidget(self._node_table)
        self.tabs.addTab(node_container, "Node Summary Table")

        # Tab 3: Hydraulic Graph
        self._graph = _HydraulicGraphWidget()
        self.tabs.addTab(self._graph, "Hydraulic Graph")

    # ------------------------------------------------------------------
    # Public API

    def populate(self, result, scene, sm):
        """Fill all three tabs from a completed HydraulicResult."""
        self._result = result
        self._scene  = scene
        self._sm     = sm

        self._fill_summary()
        self._fill_node_summary()
        self._fill_graph()

        self._pdf_btn.setEnabled(_PRINTER_AVAILABLE)
        self._csv_btn.setEnabled(True)

    def clear(self):
        """Reset all tabs to their empty state."""
        self._result = self._scene = self._sm = None
        self._summary.clear()
        self._node_table.setRowCount(0)
        self._graph.set_supply_data(0.0, 0.0, 0.0)
        self._graph.set_demand_points(0.0, 0.0, 0.0)
        self._pdf_btn.setEnabled(False)
        self._csv_btn.setEnabled(False)

    def _show_equiv_length_ref(self):
        """Show the NFPA 13 equivalent length reference dialog."""
        dlg = EquivalentLengthDialog(self)
        dlg.show()

    # ------------------------------------------------------------------
    # Data assembly (shared by screen tabs, CSV, and PDF HTML)

    def _summary_sections(self) -> list:
        """Return [(section_title, [(label, value), ...]), ...] for the
        Summary tab, CSV block, and PDF header — single source of truth.

        Note: refreshes the active design area's rect/Area property via
        compute_area() before reading it."""
        r = self._result
        scene = self._scene

        info = getattr(scene, "_project_info", {}) or {}
        addr = ", ".join(p for p in (info.get("address1", ""),
                                     info.get("address2", ""),
                                     info.get("address3", "")) if p)
        project = [
            ("Project Name",     info.get("name") or _DASH),
            ("Project Number",   info.get("number") or _DASH),
            ("Address",          addr or _DASH),
            ("Client",           info.get("client") or _DASH),
            ("Designer",         info.get("designer") or _DASH),
            ("System Description", info.get("description") or _DASH),
            ("Calculation Date", getattr(r, "calc_date", "") or _DASH),
        ]

        da = getattr(scene, "active_design_area", None)
        if da is not None:
            da.compute_area(self._sm)
            crit = da.effective_criteria()
            props = da.get_properties()
            dry = crit.system_type == "Dry"
            # Shared unit convention (imperial "sq ft" / metric m² + mm/min)
            from .scale_manager import format_area_sqft, format_density
            criteria = [
                ("Hazard Classification", crit.hazard or _DASH),
                ("System Type",           crit.system_type),
                ("Design Point",
                 (f"{format_area_sqft(crit.base_area_sqft, self._sm)} @ "
                  f"{format_density(crit.density, self._sm)}")
                 if crit.base_area_sqft else _DASH),
                ("Required Area",
                 (format_area_sqft(crit.required_area_sqft, self._sm)
                  + (" (+30% dry system — NFPA 13)" if dry else ""))
                 if crit.required_area_sqft else _DASH),
                ("Drawn Area", props["Area"]["value"] or _DASH),
            ]
        else:
            criteria = [("Hazard Classification", _DASH),
                        ("System Type", _DASH), ("Design Point", _DASH),
                        ("Required Area", _DASH), ("Drawn Area", _DASH)]
        spr_count = len(getattr(scene, "design_area_sprinklers", []) or [])
        hose = getattr(r, "hose_stream_gpm", 0.0)
        criteria += [
            ("Sprinklers in Design Area", str(spr_count) if spr_count else _DASH),
            ("Hose Stream Allowance", f"{hose:.0f} gpm" if hose > 0 else "None"),
        ]

        ws = getattr(scene, "water_supply_node", None)
        if ws is not None:
            test_date = ws.get_properties().get("Test Date", {}).get("value", "")
            supply = [
                ("Static Pressure",   f"{ws.static_pressure:.1f} psi"),
                ("Residual Pressure", f"{ws.residual_pressure:.1f} psi"),
                ("Test Flow",         f"{ws.test_flow:.0f} gpm"),
                ("Gauge Elevation",   f"{ws.elevation:.1f} ft"),
                ("Test Date",         test_date or _DASH),
            ]
        else:
            supply = [
                ("Static Pressure", _DASH), ("Residual Pressure", _DASH),
                ("Test Flow", _DASH), ("Gauge Elevation", _DASH),
                ("Test Date", _DASH),
            ]

        results = [("Status", "PASS" if r.passed else "FAIL"),
                   ("Sprinkler Demand", f"{r.total_demand:.1f} gpm")]
        if hose > 0:
            results.append(("Hose Stream", f"{hose:.0f} gpm"))
            results.append(("Total Demand", f"{r.total_demand + hose:.1f} gpm"))
        results.append(("Required Pressure", f"{r.required_pressure:.1f} psi"))
        results.append(("Supply Available", f"{r.supply_pressure:.1f} psi"))

        return [("Project", project), ("Design Criteria", criteria),
                ("Water Supply", supply), ("Results", results)]

    def _node_summary_rows(self, show_minor: bool) -> list:
        """One 14-column row per calc-path node (NFPA calc-sheet format).

        Each row pairs a node with the pipe leading to it from upstream
        (spec §9.2); the supply node has no upstream pipe.
        """
        from .equivalent_length import equivalent_length_ft

        r = self._result
        sm = self._sm
        labels = getattr(r, "node_labels", {}) or {}
        parent_pipe = getattr(r, "node_parent_pipe", {}) or {}
        supply_node = getattr(self._scene, "_supply_network_node", None)

        spr_by_node = {}
        system = getattr(self._scene, "sprinkler_system", None)
        if system is not None:
            for spr in system.sprinklers:
                if spr.node is not None:
                    spr_by_node[spr.node] = spr

        rows = []
        for node in sorted(labels, key=lambda n: _label_sort_key(labels[n])):
            label = str(labels[node])
            if not show_minor and not label.isdigit():
                continue

            pipe = parent_pipe.get(node)

            # Notes: what the node IS — sprinkler (K), supply, or a plain
            # fitting. The fitting is only informative on plain junction
            # nodes; on sprinkler/supply nodes it's noise.
            notes = []
            spr = spr_by_node.get(node)
            if spr is not None:
                notes.append(f"K={spr._properties['K-Factor']['value']}")
            elif pipe is not None:
                ft_obj = getattr(node, "fitting", None)
                if ft_obj is not None:
                    notes.append(_FITTING_NOTE_LABELS.get(ft_obj.type, ft_obj.type))

            elev = f"{node.z_pos / 304.8:.1f}"
            req = r.required_node_pressures.get(node)
            act = r.node_pressures.get(node)
            req_s = f"{req:.1f}" if req is not None else _DASH
            act_s = f"{act:.1f}" if act is not None else _DASH

            if pipe is None:
                notes.insert(0, "Supply")
                rows.append([label, elev, f"{r.total_demand:.1f}",
                             _DASH, _DASH, _DASH, _DASH, _DASH, _DASH, _DASH,
                             req_s, act_s, _DASH, ", ".join(notes)])
                continue

            q = r.pipe_flows.get(pipe, 0.0)
            v = r.pipe_velocity.get(pipe, 0.0)
            hf = r.pipe_friction_loss.get(pipe, 0.0)
            d = str(pipe._properties["Diameter"]["value"])
            cf = str(pipe._properties["C-Factor"]["value"])
            equiv_ft = 0.0
            for end_node in (pipe.node1, pipe.node2):
                if end_node is None or end_node is supply_node:
                    continue
                f = getattr(end_node, "fitting", None)
                if f is not None:
                    equiv_ft += equivalent_length_ft(f.type, d)
            phys_ft = pipe.get_length_ft(sm=sm)
            total_ft = phys_ft + equiv_ft
            psi_ft = hf / total_ft if total_ft > 0 else 0.0

            rows.append([label, elev, f"{q:.1f}", d, f"{phys_ft:.1f}",
                         f"{equiv_ft:.1f}", f"{total_ft:.1f}", cf,
                         f"{psi_ft:.3f}", f"{hf:.2f}", req_s, act_s,
                         f"{v:.1f}", ", ".join(notes) or _DASH])
        return rows

    # ------------------------------------------------------------------
    # Tab fillers

    def _fill_summary(self):
        r = self._result
        status_html = (
            "<span style='color:green;font-weight:bold'>✅ PASS</span>"
            if r.passed else
            "<span style='color:red;font-weight:bold'>❌ FAIL</span>"
        )
        out = f"<h2 style='margin-bottom:2px'>Hydraulic Summary</h2>{status_html}"
        # Messages up top — a failed calc's reason must be the first thing read
        if r.messages:
            out += "<br><b>Messages:</b><ul style='margin-top:4px'>"
            for msg in r.messages:
                out += f"<li style='margin-bottom:2px'>{html.escape(msg)}</li>"
            out += "</ul>"
        for title, rows in self._summary_sections():
            out += f"<h3 style='margin-bottom:2px'>{title}</h3>"
            out += "<table style='font-size:11pt;border-collapse:collapse;'>"
            for label, value in rows:
                value = status_html if label == "Status" else html.escape(value)
                out += (f"<tr><td style='padding:2px 12px'><b>{label}</b></td>"
                        f"<td>{value}</td></tr>")
            out += "</table>"
        self._summary.setHtml(out)

    def _on_minor_toggle(self, checked: bool):
        """Re-fill the node summary table when minor-node visibility changes."""
        if self._result:
            self._fill_node_summary()

    def _fill_node_summary(self):
        rows = self._node_summary_rows(self._show_minor_cb.isChecked())
        t = self._node_table
        t.setSortingEnabled(False)
        t.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for col, val in enumerate(row):
                t.setItem(i, col, _item(val))
        t.setSortingEnabled(True)

    def _fill_graph(self):
        """Populate the hydraulic graph with supply curve and demand data.

        Always resets first so a removed supply / failed run can't leave a
        stale curve on screen (or baked into an exported PDF).
        """
        ws = getattr(self._scene, "water_supply_node", None)
        if ws is not None:
            self._graph.set_supply_data(
                ws.static_pressure, ws.residual_pressure, ws.test_flow
            )
        else:
            self._graph.set_supply_data(0.0, 0.0, 0.0)
        if self._result and self._result.total_demand > 0:
            hose = getattr(self._result, 'hose_stream_gpm', 0.0)
            self._graph.set_demand_points(
                self._result.total_demand, hose,
                self._result.required_pressure
            )
        else:
            self._graph.set_demand_points(0.0, 0.0, 0.0)

    # ------------------------------------------------------------------
    # Export — PDF

    def _graph_image(self, width: int = 1000, height: int = 620) -> "QImage":
        """Render the hydraulic graph to an off-screen image for PDF export."""
        g = _HydraulicGraphWidget()
        g.set_supply_data(self._graph._p_static, self._graph._p_residual,
                          self._graph._q_test)
        g.set_demand_points(self._graph._q_sprinkler, self._graph._hose_stream,
                            self._graph._p_demand)
        g.resize(width, height)
        img = QImage(width, height, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.white)
        painter = QPainter(img)
        g.render(painter)
        painter.end()
        return img

    def _export_pdf(self):
        if not self._result or not _PRINTER_AVAILABLE:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Hydraulic Report PDF",
            os.path.join(self._export_dir(), "hydraulic_report.pdf"),
            "PDF Files (*.pdf)"
        )
        if not path:
            return

        doc = QTextDocument()
        doc.addResource(QTextDocument.ResourceType.ImageResource,
                        QUrl("hydraulic_graph"), self._graph_image())
        doc.setHtml(self._build_html())

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        doc.print(printer)

        QMessageBox.information(self, "Export Complete",
                                f"PDF saved to:\n{path}")

    # Export — CSV

    def _export_dir(self) -> str:
        """Default export folder: ``<project folder>/HC Reports`` when the
        project has been saved, else '' (dialog falls back to CWD).

        Creates the folder on first use so the save dialog opens inside it.
        """
        proj = getattr(self._scene, "_project_path", None)
        if not proj:
            return ""
        out_dir = os.path.join(os.path.dirname(proj), "HC Reports")
        os.makedirs(out_dir, exist_ok=True)
        return out_dir

    def _export_csv(self):
        if not self._result:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Hydraulic Report CSV",
            os.path.join(self._export_dir(), "hydraulic_report.csv"),
            "CSV Files (*.csv)"
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            self._write_csv(f)
        QMessageBox.information(self, "Export Complete",
                                f"CSV saved to:\n{path}")

    def _write_csv(self, f):
        """Write the summary sections + node summary table to a file object."""
        r = self._result
        w = csv.writer(f)
        w.writerow(["HYDRAULIC CALCULATION REPORT — NFPA 13"])
        w.writerow([])
        if r.messages:
            w.writerow(["MESSAGES"])
            for msg in r.messages:
                w.writerow(["", msg])
            w.writerow([])
        for title, rows in self._summary_sections():
            w.writerow([title.upper()])
            for label, value in rows:
                w.writerow([label, value])
            w.writerow([])
        w.writerow(["NODE SUMMARY"])
        w.writerow(NODE_SUMMARY_HEADERS)
        for row in self._node_summary_rows(self._show_minor_cb.isChecked()):
            w.writerow(row)

    # ------------------------------------------------------------------
    # HTML builder (used by PDF export)

    def _build_html(self) -> str:
        r = self._result
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
        ul    { margin-top: 4px; }
        li    { margin-bottom: 3px; }
        """
        out = f"<html><head><style>{css}</style></head><body>"
        out += "<h2>Hydraulic Calculation Report — NFPA 13</h2>"

        sc = "pass" if r.passed else "fail"
        if r.messages:
            out += "<h3>Analysis Messages</h3><ul>"
            for msg in r.messages:
                out += f"<li>{html.escape(msg)}</li>"
            out += "</ul>"

        for title, rows in self._summary_sections():
            out += f"<h3>{title}</h3><table><tr><th>Item</th><th>Value</th></tr>"
            for label, value in rows:
                cls = f" class='{sc}'" if label == "Status" else ""
                out += (f"<tr><td>{label}</td>"
                        f"<td{cls}>{html.escape(value)}</td></tr>")
            out += "</table>"

        out += "<h3>Node Summary</h3><table><tr>"
        for h in NODE_SUMMARY_HEADERS:
            out += f"<th>{h}</th>"
        out += "</tr>"
        for row in self._node_summary_rows(self._show_minor_cb.isChecked()):
            out += ("<tr>" +
                    "".join(f"<td>{html.escape(v)}</td>" for v in row) +
                    "</tr>")
        out += "</table>"

        out += "<h3>Hydraulic Graph</h3>"
        out += "<img src='hydraulic_graph' width='650'>"
        out += "</body></html>"
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Equivalent Length Reference Dialog
# ─────────────────────────────────────────────────────────────────────────────

class EquivalentLengthDialog(QWidget):
    """Read-only reference dialog showing NFPA 13 Table 22.4.3.1.1."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Equivalent Pipe Lengths — NFPA 13 Table 22.4.3.1.1")
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(700, 250)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        from firepro3d.equivalent_length import _DIAMETERS, _TABLE

        diameters_display = [d.replace("Ø", "").strip() for d in _DIAMETERS]
        headers = ["Fitting Type"] + diameters_display

        table = _make_table(headers)
        table.setRowCount(len(_TABLE))

        row_labels = {
            "90_elbow": "90° Elbow",
            "45_elbow": "45° Elbow",
            "tee_flow_turn": "Tee (flow turn)",
            "cross_flow_turn": "Cross (flow turn)",
            "cap": "Cap (end)",
        }

        for row, (key, values) in enumerate(_TABLE.items()):
            table.setItem(row, 0, _item(row_labels.get(key, key), bold=True))
            for col, val in enumerate(values):
                table.setItem(row, col + 1, _item(str(int(val)) if val == int(val) else str(val)))

        layout.addWidget(table)

        note = QTextBrowser()
        note.setMaximumHeight(40)
        note.setHtml(
            "<i>Values in feet. Source: NFPA 13, Table 22.4.3.1.1. "
            "Wye fittings use 45° elbow values. Vertical elbows/tees use "
            "corresponding horizontal values.</i>"
        )
        layout.addWidget(note)
