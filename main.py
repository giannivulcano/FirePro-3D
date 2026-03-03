import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow,
                              QFileDialog, QDockWidget, QInputDialog,
                              QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QSpinBox, QDialogButtonBox, QLineEdit,
                              QTabWidget, QMenu, QStyle, QWidget, QColorDialog)
from PyQt6.QtGui import QPainter, QIcon, QColor, QPixmap
from PyQt6.QtCore import Qt, QSettings, QSize
from Model_Space import Model_Space
from Model_View import Model_View
from sprinkler import Sprinkler
from pipe import Pipe
from dxf_import_dialog import DxfImportDialog
from dxf_preview_dialog import DxfPreviewDialog
from property_manager import PropertyManager
from scale_manager import DisplayUnit
from layer_manager import LayerManager
from hydraulic_report import HydraulicReportWidget
from user_layer_manager import UserLayerManager, UserLayerWidget
from paper_space import PaperSpaceWidget, PAPER_SIZES
from ribbon_bar import RibbonBar
from array_dialog import ArrayDialog
from project_browser import ProjectBrowser
from grid_lines_dialog import GridLinesDialog
import theme as th


# ─────────────────────────────────────────────────────────────────────────────
# PDF Import Dialog
# ─────────────────────────────────────────────────────────────────────────────

class ImportDialog(QDialog):
    """Ask user for PDF import options: file, DPI, page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import PDF Underlay")

        layout = QVBoxLayout(self)

        # File picker row
        file_layout = QHBoxLayout()
        self.file_edit = QLineEdit()
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(QLabel("PDF File:"))
        file_layout.addWidget(self.file_edit)
        file_layout.addWidget(browse_btn)
        layout.addLayout(file_layout)

        # DPI option
        dpi_layout = QHBoxLayout()
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(50, 600)
        self.dpi_spin.setValue(150)
        dpi_layout.addWidget(QLabel("Render DPI:"))
        dpi_layout.addWidget(self.dpi_spin)
        layout.addLayout(dpi_layout)

        # Page number option
        page_layout = QHBoxLayout()
        self.page_spin = QSpinBox()
        self.page_spin.setRange(0, 999)
        self.page_spin.setValue(0)
        page_layout.addWidget(QLabel("Page:"))
        page_layout.addWidget(self.page_spin)
        layout.addLayout(page_layout)

        # OK/Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF Files (*.pdf)")
        if file:
            self.file_edit.setText(file)

    def get_options(self):
        return {
            "file": str(self.file_edit.text()),
            "dpi":  self.dpi_spin.value(),
            "page": self.page_spin.value(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Main Window
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FireFlow Pro - Sprinkler Design Software")

        # Settings
        self.settings = QSettings("GV", "SprinklerAPP")
        self.current_sprinkler_template = Sprinkler(None)
        self.current_pipe_template = Pipe(None, None)

        # Scene + View
        self.scene = Model_Space()
        self.view = Model_View(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Draw tool style defaults (white pen in dark theme, 1px cosmetic)
        _t = th.detect()
        self._draw_color: str = _t.text_primary        # "#ffffff" dark / "#000000" light
        self._draw_lineweight: float = 1.0
        self.scene._draw_color = self._draw_color
        self.scene._draw_lineweight = self._draw_lineweight

        # User layer manager — shared between scene and UI
        self.user_layer_mgr = UserLayerManager()
        self.scene._user_layer_manager = self.user_layer_mgr   # for save/load

        # Central tab widget: Model Space | Layout 1 (Paper Space)
        self.paper_space_widget = PaperSpaceWidget(self.scene)
        self.central_tabs = QTabWidget()
        self.central_tabs.addTab(self.view, "Model Space")
        self.central_tabs.addTab(self.paper_space_widget, "Layout 1")

        # Ribbon spans full window width (above docks) via setMenuWidget
        self.ribbon = RibbonBar()
        self.setMenuWidget(self.ribbon)
        self.setCentralWidget(self.central_tabs)

        # Property manager dock
        self.prop_manager = PropertyManager()
        self.scene.requestPropertyUpdate.connect(self.prop_manager.show_properties)
        self.dock = QDockWidget("Properties", self)
        self.init_property_manager_dock()

        # Combined left-side dock: DXF Layers | User Layers | Project Browser
        self.layer_manager = LayerManager(self.scene)
        self.user_layer_widget = UserLayerWidget(
            self.user_layer_mgr, scene=self.scene
        )
        self.user_layer_widget.activeLayerChanged.connect(
            lambda name: setattr(self.scene, "active_user_layer", name)
        )
        self.user_layer_widget.layersChanged.connect(
            lambda: self.user_layer_mgr.apply_to_scene(self.scene)
        )
        self.project_browser = ProjectBrowser()
        self.project_browser.activateModelSpace.connect(
            lambda: self.central_tabs.setCurrentWidget(self.view)
        )
        self.project_browser.activatePaperSheet.connect(
            self._activate_paper_sheet
        )

        self._left_tabs = QTabWidget()
        self._left_tabs.addTab(self.project_browser, "Project Browser")
        self._left_tabs.addTab(self.layer_manager, "DXF Layers")
        self._left_tabs.addTab(self.user_layer_widget, "User Layers")

        self.browser_dock = QDockWidget("", self)
        self.browser_dock.setObjectName("BrowserDock")
        self.browser_dock.setTitleBarWidget(QWidget())  # hide title bar
        self.browser_dock.setWidget(self._left_tabs)
        self.browser_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.browser_dock)
        self.browser_dock.setMinimumWidth(200)

        # Hydraulic report dock (tabbed: Summary | Pipe Results | Schedules)
        self.hydro_report = HydraulicReportWidget()
        self.hydro_dock = QDockWidget("Hydraulic Report", self)
        self.hydro_dock.setObjectName("HydraulicsDock")
        self.hydro_dock.setWidget(self.hydro_report)
        self.hydro_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea |
            Qt.DockWidgetArea.TopDockWidgetArea  |
            Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.hydro_dock)
        self.hydro_dock.hide()   # hidden until the user runs hydraulics

        # Status bar with cursor coordinates
        status_bar = self.statusBar()
        self.coord_label = QLabel("X: —   Y: —")
        self.coord_label.setMinimumWidth(280)
        status_bar.addPermanentWidget(self.coord_label)
        self.mode_label = QLabel("Mode: —")
        status_bar.addWidget(self.mode_label)
        self.scene.cursorMoved.connect(self.coord_label.setText)
        self.scene.modeChanged.connect(self._update_mode_label)

        self.init_ribbon()

        # Restore settings
        self.restore_settings()

    def restore_settings(self):
        geom = self.settings.value("geometry", b"")
        if geom:
            self.restoreGeometry(geom)
        state = self.settings.value("windowState", b"")
        if state:
            self.restoreState(state, self._STATE_VERSION)
        # Restore dock visibility (only if settings exist, otherwise keep defaults)
        if self.settings.contains("dock/properties"):
            self.dock.setVisible(self.settings.value("dock/properties", True, type=bool))
        if self.settings.contains("dock/browser"):
            self.browser_dock.setVisible(self.settings.value("dock/browser", True, type=bool))
        if self.settings.contains("dock/hydraulics"):
            self.hydro_dock.setVisible(self.settings.value("dock/hydraulics", False, type=bool))

    def _activate_paper_sheet(self, name: str):
        """Switch the central area to the paper space tab matching *name*."""
        for i in range(self.central_tabs.count()):
            if self.central_tabs.tabText(i) == name:
                self.central_tabs.setCurrentIndex(i)
                return
        # Sheet not found — switch to the first paper space tab as fallback
        self.central_tabs.setCurrentWidget(self.paper_space_widget)

    # ─────────────────────────────────────────────────────────────────────────
    # RIBBON INITIALISATION
    # ─────────────────────────────────────────────────────────────────────────

    def init_ribbon(self):
        """Build the six workflow ribbon tabs and wire every button.

        Tabs:
          1. Manage   — file I/O, import, settings, grid, undo/redo, panels
          2. Draw     — geometry tools, style, snap, annotations
          3. Build    — pipe/sprinkler placement, system, library
          4. Modify   — edit/transform/scale tools (auto-switches on selection)
          5. Analyze  — hydraulics, export
          6. Draft    — workspace switching, page setup

        Must be called *after* all dock widgets are created so that dock
        visibility toggles can be wired correctly.
        """
        s = self.style()
        _I = lambda name: QIcon(f"graphics/Ribbon/{name}")

        # ── Tab 1: Manage ────────────────────────────────────────────────────
        manage_page = self.ribbon.add_page("Manage")

        # --- File ---
        g_file = manage_page.add_group("File")
        g_file.add_large_button("Open", _I("load_icon.svg"), self.open_file)
        g_file.add_large_button("Save", _I("save_icon.svg"), self.save_file)
        g_file.add_large_button("Save As", _I("saveas_icon.svg"), self.save_file_as)

        # --- Import (split menu: PDF / DXF) ---
        g_imp = manage_page.add_group("Import")
        import_menu = QMenu(self)
        import_menu.addAction("PDF Underlay\u2026", self.open_pdf_import_dialog)
        import_menu.addAction("DXF Underlay\u2026", self.open_dxf_import_dialog)
        g_imp.add_large_menu_button(
            "Import\nUnderlay", _I("import_icon.svg"), import_menu)
        g_imp.add_small_button(
            "Refresh All",
            s.standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
            self.refresh_underlays)

        # --- Settings ---
        g_set = manage_page.add_group("Settings")
        g_set.add_small_menu_button(
            "Units", _I("info_icon.svg"), self._build_units_menu())
        g_set.add_small_menu_button(
            "Precision", _I("info_icon.svg"), self._build_precision_menu())

        # --- Grid ---
        g_grid = manage_page.add_group("Grid")
        self._grid_btn = g_grid.add_large_button(
            "Grid\nOn/Off", _I("gridline_icon.svg"),
            self.toggle_grid, checkable=True)
        g_grid.add_small_menu_button(
            "Grid Size", _I("gridline_icon.svg"), self._build_grid_size_menu())

        # --- Edit (Undo/Redo always accessible) ---
        g_edit = manage_page.add_group("Edit")
        g_edit.add_large_button(
            "Undo", _I("undo_icon.svg"),
            self.scene.undo, shortcut="Ctrl+Z")
        g_edit.add_large_button(
            "Redo", _I("redo_icon.svg"),
            self.scene.redo, shortcut="Ctrl+Y")

        # --- Panels (dock toggles) ---
        g_pan = manage_page.add_group("Panels")
        prop_btn = g_pan.add_small_button(
            "Properties", _I("info_icon.svg"), None, checkable=True)
        prop_btn.toggled.connect(self.dock.setVisible)
        self.dock.visibilityChanged.connect(prop_btn.setChecked)

        browser_btn = g_pan.add_small_button(
            "Browser",
            s.standardIcon(QStyle.StandardPixmap.SP_DirIcon),
            None, checkable=True)
        browser_btn.toggled.connect(self.browser_dock.setVisible)
        self.browser_dock.visibilityChanged.connect(browser_btn.setChecked)

        report_btn = g_pan.add_small_button(
            "Report Panel", _I("report_icon.svg"), None, checkable=True)
        report_btn.toggled.connect(
            lambda on: self.hydro_dock.show() if on else self.hydro_dock.hide())
        self.hydro_dock.visibilityChanged.connect(report_btn.setChecked)

        # ── Tab 2: Draw ──────────────────────────────────────────────────────
        draw_page = self.ribbon.add_page("Draw")

        # --- Geometry ---
        g_geom = draw_page.add_group("Geometry")
        g_geom.add_large_button(
            "Line", _I("line_icon.svg"),
            lambda: self.scene.set_mode("draw_line"))
        g_geom.add_large_button(
            "Rectangle", _I("rectangle_icon.svg"),
            lambda: self.scene.set_mode("draw_rectangle"))
        g_geom.add_large_button(
            "Circle", _I("circle_icon.svg"),
            lambda: self.scene.set_mode("draw_circle"))
        g_geom.add_large_button(
            "Polyline", _I("polyline_icon.svg"),
            lambda: self.scene.set_mode("polyline"))
        g_geom.add_large_button(
            "Grid\nLines", _I("gridline_icon.svg"),
            self._place_grid_lines)

        # --- Style ---
        g_style = draw_page.add_group("Style")
        self._draw_color_btn = g_style.add_small_button(
            "Colour", self._make_color_icon(self._draw_color),
            self._pick_draw_color)
        self._draw_lw_btn = g_style.add_small_menu_button(
            "LW 1.00",
            s.standardIcon(QStyle.StandardPixmap.SP_FileDialogListView),
            self._build_lineweight_menu())

        # --- Snap ---
        g_snap = draw_page.add_group("Snap")
        self._osnap_btn = g_snap.add_large_button(
            "OSNAP",
            s.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton),
            self._toggle_osnap, checkable=True, shortcut="F3")
        self._osnap_btn.setChecked(True)
        self._osnap_btn.setToolTip("Object Snap  [F3]")
        g_snap.add_small_button(
            "Snap to\nUnderlay",
            s.standardIcon(QStyle.StandardPixmap.SP_CommandLink),
            lambda checked: setattr(self.scene, "_snap_to_underlay", checked),
            checkable=True)
        g_snap.add_small_menu_button(
            "Angle Snap",
            s.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton),
            self._build_snap_angle_menu())

        # --- Annotations ---
        g_ann = draw_page.add_group("Annotations")
        g_ann.add_large_button(
            "Dimension", _I("dimension_icon.svg"),
            lambda: self.scene.set_mode("dimension"))
        g_ann.add_large_button(
            "Text", _I("text_icon.svg"),
            lambda: self.scene.set_mode("text"))

        # ── Tab 3: Build ─────────────────────────────────────────────────────
        build_page = self.ribbon.add_page("Build")

        # --- Place ---
        g_place = build_page.add_group("Place")
        g_place.add_large_button(
            "Pipe", _I("pipe_icon.svg"),
            lambda: self.scene.set_mode("pipe", self.current_pipe_template))
        g_place.add_large_button(
            "Sprinkler", _I("sprinkler_icon.svg"),
            lambda: self.scene.set_mode("sprinkler", self.current_sprinkler_template))

        # --- System ---
        g_sys = build_page.add_group("System")
        g_sys.add_large_button(
            "Water\nSupply", _I("supply_icon.svg"),
            lambda: self.scene.set_mode("water_supply"))
        g_sys.add_large_button(
            "Design\nArea", _I("design_area_icon.svg"),
            lambda: self.scene.set_mode("design_area"))
        self._coverage_btn = g_sys.add_small_button(
            "Coverage Overlay", _I("sprinkler_icon.svg"),
            self.toggle_coverage_overlay, checkable=True)

        # --- Library ---
        g_lib = build_page.add_group("Library")
        g_lib.add_large_button(
            "Sprinkler\nManager", _I("sprinkler_icon.svg"),
            self.open_sprinkler_manager)

        # ── Tab 4: Modify (always visible, auto-switches on selection) ────────
        modify_page = self.ribbon.add_page("Modify")
        self._modify_tab_idx = self.ribbon._tab_bar.count() - 1

        # --- Edit ---
        g_medit = modify_page.add_group("Edit")
        g_medit.add_large_button("Undo", _I("undo_icon.svg"), self.scene.undo)
        g_medit.add_large_button("Redo", _I("redo_icon.svg"), self.scene.redo)
        g_medit.add_small_button(
            "Cut", _I("cut_icon.svg"),
            lambda: (self.scene.copy_selected_items(), self.scene.delete_selected_items()))
        g_medit.add_small_button(
            "Copy", _I("copy_icon.svg"),
            lambda: self.scene.copy_selected_items())
        g_medit.add_small_button(
            "Paste", _I("paste_icon.svg"),
            lambda: self.scene.paste_items())
        g_medit.add_small_button(
            "Delete", _I("delete_icon.svg"),
            lambda: self.scene.delete_selected_items())

        # --- Transform ---
        g_xform = modify_page.add_group("Transform")
        g_xform.add_small_button(
            "Move", _I("move_icon.svg"),
            lambda: self.scene.set_mode("move"))
        g_xform.add_small_button(
            "Duplicate", _I("duplicate_icon.svg"),
            lambda: self.scene.duplicate_selected())
        g_xform.add_small_button(
            "Array", _I("array_icon.svg"),
            self._open_array_dialog)
        g_xform.add_small_button(
            "Rotate", _I("rotate_icon.svg"),
            lambda: self.scene.rotate_selected_items())
        g_xform.add_small_button(
            "Scale", _I("scale_icon.svg"),
            self.set_scale_dialog)
        g_xform.add_small_button(
            "Offset", _I("trim_icon.svg"),
            lambda: self.scene.set_mode("offset"))

        # Auto-switch to Modify tab when items are selected
        self.scene.selectionChanged.connect(self._on_selection_changed_modify)

        # ── Tab 5: Analyze ───────────────────────────────────────────────────
        analyze_page = self.ribbon.add_page("Analyze")

        # --- Hydraulics ---
        g_hyd = analyze_page.add_group("Hydraulics")
        g_hyd.add_large_button(
            "Run\nHydraulics", _I("hydraulics_icon.svg"),
            self.run_hydraulics, shortcut="F5")
        g_hyd.add_large_button(
            "Clear\nResults", _I("clear_icon.svg"),
            self.clear_hydraulics)

        # --- Export ---
        g_exp = analyze_page.add_group("Export")
        g_exp.add_large_button(
            "Export PDF", _I("export_icon.svg"),
            self.hydro_report._export_pdf)
        g_exp.add_large_button(
            "Export CSV", _I("report_icon.svg"),
            self.hydro_report._export_csv)

        # ── Tab 6: Draft ─────────────────────────────────────────────────────
        draft_page = self.ribbon.add_page("Draft")

        # --- Workspace ---
        g_ws = draft_page.add_group("Workspace")
        g_ws.add_large_button(
            "Model\nSpace",
            s.standardIcon(QStyle.StandardPixmap.SP_DesktopIcon),
            lambda: self.central_tabs.setCurrentIndex(0))
        g_ws.add_large_button(
            "Layout 1\nPaper",
            s.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView),
            lambda: self.central_tabs.setCurrentIndex(1))

        # --- Page ---
        g_pg = draft_page.add_group("Page")
        g_pg.add_large_menu_button(
            "Paper Size",
            s.standardIcon(QStyle.StandardPixmap.SP_FileIcon),
            self._build_paper_size_menu())
        g_pg.add_large_button(
            "Title Block",
            s.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            self.paper_space_widget.edit_title_block)

    # ── Ribbon helper menu builders ───────────────────────────────────────────

    def _build_units_menu(self) -> QMenu:
        m = QMenu(self)
        m.addAction("Imperial (ft-in)",
                    lambda: self.scene.set_display_unit(DisplayUnit.IMPERIAL))
        m.addAction("Metric (m)",
                    lambda: self.scene.set_display_unit(DisplayUnit.METRIC_M))
        m.addAction("Metric (mm)",
                    lambda: self.scene.set_display_unit(DisplayUnit.METRIC_MM))
        return m

    def _build_precision_menu(self) -> QMenu:
        m = QMenu(self)
        for p in range(4):
            label = f"{p} decimal place{'s' if p != 1 else ''}"
            m.addAction(label, lambda _, p=p: self._set_precision(p))
        return m

    def _build_paper_size_menu(self) -> QMenu:
        m = QMenu(self)
        for name in PAPER_SIZES:
            m.addAction(name,
                        lambda _, n=name: self.paper_space_widget.change_paper(n))
        return m

    def _build_grid_size_menu(self) -> QMenu:
        """Return a QMenu of common grid-size presets (scene units)."""
        m = QMenu(self)
        for size in (5, 10, 25, 50, 100):
            act = m.addAction(f"{size} units")
            # Use checked=False default so lambda works with 0-arg or 1-arg call
            act.triggered.connect(lambda checked=False, s=size: self._set_grid_size(s))
        return m

    def _build_snap_angle_menu(self) -> QMenu:
        """Return a QMenu of angle snap increments for Ctrl-constrain."""
        m = QMenu(self)
        for deg in (15, 30, 45, 90):
            act = m.addAction(f"{deg}°")
            act.triggered.connect(
                lambda checked=False, d=deg: setattr(self.scene, "_snap_angle_deg", float(d)))
        return m

    # ── Stub actions (filled in by later sprints) ─────────────────────────────

    # ── Draw tool helpers ─────────────────────────────────────────────────────

    def _make_color_icon(self, color: str, size: int = 16) -> QIcon:
        """Return a solid-colour square icon for the colour picker button."""
        pm = QPixmap(size, size)
        pm.fill(QColor(color))
        return QIcon(pm)

    def _pick_draw_color(self):
        """Open colour picker dialog and update draw colour."""
        color = QColorDialog.getColor(QColor(self._draw_color), self,
                                      "Select Draw Colour")
        if color.isValid():
            self._draw_color = color.name()
            self.scene._draw_color = self._draw_color
            if hasattr(self, "_draw_color_btn"):
                self._draw_color_btn.setIcon(self._make_color_icon(self._draw_color))

    def _set_draw_lineweight(self, lw: float):
        """Update draw lineweight and sync to scene."""
        self._draw_lineweight = lw
        self.scene._draw_lineweight = lw
        if hasattr(self, "_draw_lw_btn"):
            self._draw_lw_btn.setText(f"LW {lw:.2f}")

    def _build_lineweight_menu(self) -> QMenu:
        """Return a QMenu of standard drawing pen lineweights (mm)."""
        m = QMenu(self)
        for lw in (0.18, 0.25, 0.35, 0.50, 0.70, 1.00, 1.40, 2.00):
            act = m.addAction(f"{lw:.2f} mm")
            act.triggered.connect(lambda checked=False, w=lw: self._set_draw_lineweight(w))
        return m

    # ── OSNAP toggle (Sprint H) ───────────────────────────────────────────────

    def _toggle_osnap(self, checked: bool):
        """Called when the OSNAP ribbon button is toggled (or F3 pressed)."""
        self.scene.toggle_osnap(checked)

    # ── Mode label (Sprint N) ────────────────────────────────────────────────

    _MODE_INSTRUCTIONS = {
        "select":         "Select items to edit",
        "pipe":           "Click to place first node, then second node",
        "sprinkler":      "Click a node or pipe to place sprinkler",
        "draw_line":      "Click first point, then second point (Tab for exact input)",
        "draw_rectangle": "Click first corner, then opposite corner (Tab for exact input)",
        "draw_circle":    "Click center, then radius point (Tab for exact input)",
        "polyline":       "Click to add points, right-click to finish (Tab for exact input)",
        "dimension":      "Click first point, then second point to place dimension",
        "text":           "Click to place text",
        "set_scale":      "Click two known points, then enter real-world distance",
        "move":           "Click base point, then destination",
        "offset":         "Click geometry to offset, then enter distance",
        "offset_side":    "Click the side to offset towards",
        "design_area":    "Click two corners to define design area",
        "water_supply":   "Click to place water supply",
        "paste":          "Click to place pasted items",
    }

    def _update_mode_label(self, mode: str):
        text = self._MODE_INSTRUCTIONS.get(mode, mode.replace("_", " ").title())
        self.mode_label.setText(text)

    # ── Modify tab auto-switch (Sprint N) ──────────────────────────────────

    _DRAW_MODES = {"draw_line", "draw_rectangle", "draw_circle", "polyline",
                    "dimension", "text", "pipe", "sprinkler", "water_supply",
                    "design_area", "set_scale", "offset", "offset_side"}

    def _on_selection_changed_modify(self):
        """Auto-switch to Modify tab when items are selected (unless drawing)."""
        if self.scene.selectedItems() and self.scene.mode not in self._DRAW_MODES:
            self.ribbon._tab_bar.setCurrentIndex(self._modify_tab_idx)

    # ── Array / Multiply (Sprint J) ──────────────────────────────────────────

    def _open_array_dialog(self):
        """Open the Array dialog and execute the array on the current selection."""
        if not self.scene.selectedItems():
            return
        dlg = ArrayDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.scene.array_items(dlg.get_params())

    # ── Grid Lines ───────────────────────────────────────────────────────────

    def _place_grid_lines(self):
        """Open the Grid Lines dialog and place construction lines on the canvas."""
        dlg = GridLinesDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.scene.place_grid_lines(dlg.get_params())

    def toggle_grid(self, checked: bool):
        """Show/hide the dot grid overlay on the model-space view."""
        self.view.set_grid(checked)

    def _set_grid_size(self, size: int):
        """Update grid dot spacing and keep the toggle button checked."""
        self.view.set_grid(True, size)
        # Block toggled signal to prevent cascading toggle_grid calls
        self._grid_btn.blockSignals(True)
        self._grid_btn.setChecked(True)
        self._grid_btn.blockSignals(False)

    def toggle_coverage_overlay(self, checked: bool):
        """Show/hide translucent sprinkler coverage circles."""
        self.scene.set_coverage_overlay(checked)

    def open_sprinkler_manager(self):
        """Open the Sprinkler Manager database dialog."""
        from sprinkler_db import SprinklerManagerDialog, SprinklerDatabase
        if not hasattr(self, "_sprinkler_db"):
            self._sprinkler_db = SprinklerDatabase()
        dlg = SprinklerManagerDialog(db=self._sprinkler_db, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            record = dlg.selected_record()
            if record:
                self._apply_sprinkler_template_from_record(record)

    def _apply_sprinkler_template_from_record(self, record):
        """Apply a SprinklerRecord as the active sprinkler placement template."""
        from sprinkler import Sprinkler
        template = Sprinkler(None)
        template.set_property("K-Factor",      str(record.k_factor))
        template.set_property("Min Pressure",  str(record.min_pressure))
        template.set_property("Coverage Area", str(record.coverage_area))
        template.set_property("Temp Rating",   str(record.temp_rating))
        template.set_property("Type",          record.type)
        self.current_sprinkler_template = template
        self.scene.set_mode("sprinkler", template)
        self.statusBar().showMessage(
            f"Active template: {record.manufacturer} {record.model} "
            f"(K={record.k_factor:.1f}, {record.coverage_area:.0f} ft²)",
            5000
        )

    # ─────────────────────────────────────────────────────────────────────────
    # PROPERTY MANAGER
    # ─────────────────────────────────────────────────────────────────────────

    def init_property_manager_dock(self):
        self.dock.setObjectName("PropertiesDock")
        self.dock.setWidget(self.prop_manager)
        self.dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.setMinimumWidth(200)
        self.resizeDocks([self.dock], [300], Qt.Orientation.Horizontal)
        self.scene.selectionChanged.connect(self.update_property_manager)

    # ─────────────────────────────────────────────────────────────────────────
    # MENU BAR HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def save_file(self):
        file, _ = QFileDialog.getSaveFileName(self, "Save CAD Scene", "", "JSON Files (*.json)")
        if file:
            self.scene.save_to_file(file)

    def save_file_as(self):
        file, _ = QFileDialog.getSaveFileName(self, "Save CAD Scene", "", "JSON Files (*.json)")
        if file:
            self.scene.save_to_file(file)

    def open_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Load CAD Scene", "", "JSON Files (*.json)")
        if file:
            self.scene.load_from_file(file)

    def set_scale_dialog(self):
        self.scene.set_mode("set_scale")

    def open_pdf_import_dialog(self):
        dialog = ImportDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            opts = dialog.get_options()
            if opts["file"]:
                self.scene.import_pdf(
                    opts["file"], dpi=opts["dpi"], page=opts["page"]
                )

    def open_dxf_import_dialog(self):
        """Open the preview-first DXF import dialog."""
        dialog = DxfPreviewDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            params = dialog.get_import_params()
            if not params.geom_list:
                return
            # Switch to model space and enter place_import mode
            self.central_tabs.setCurrentWidget(self.view)
            self.scene.begin_place_import(params)

    def refresh_underlays(self):
        self.scene.refresh_all_underlays()

    def _set_precision(self, places: int):
        self.scene.scale_manager.precision = places
        self.scene._refresh_all_labels()

    # ─────────────────────────────────────────────────────────────────────────
    # HYDRAULICS HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def run_hydraulics(self):
        """Run the hydraulic solver and populate the report dock."""
        design = self.scene.design_area_sprinklers or None
        result = self.scene.run_hydraulics(design_sprinklers=design)
        self.hydro_report.populate(result, self.scene, self.scene.scale_manager)
        self.hydro_dock.show()
        self.hydro_dock.raise_()

    def clear_hydraulics(self):
        """Clear the hydraulic overlay and the report dock."""
        self.scene.clear_hydraulics()
        self.hydro_report.clear()

    # ─────────────────────────────────────────────────────────────────────────
    # PROPERTY MANAGER HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def update_property_manager(self):
        items = self.scene.selectedItems()
        if items:
            self.prop_manager.show_properties(items[0])
        else:
            self.prop_manager.show_properties(None)

    # ─────────────────────────────────────────────────────────────────────────
    # EVENT HANDLING
    # ─────────────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

    _STATE_VERSION = 2  # bump when dock layout changes between sprints

    def save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState(self._STATE_VERSION))
        self.settings.setValue("dock/properties", self.dock.isVisible())
        self.settings.setValue("dock/browser", self.browser_dock.isVisible())
        self.settings.setValue("dock/hydraulics", self.hydro_dock.isVisible())


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    # Apply global theme stylesheet before any widgets are created
    _t = th.detect()
    app.setStyleSheet(th.build_app_qss(_t))
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()