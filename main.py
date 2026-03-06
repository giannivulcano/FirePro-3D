import sys, os
from PyQt6.QtWidgets import (QApplication, QMainWindow,
                              QFileDialog, QDockWidget, QInputDialog,
                              QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QSpinBox, QDialogButtonBox, QLineEdit,
                              QTabWidget, QMenu, QWidget,
                              QComboBox)
from PyQt6.QtGui import QPainter, QIcon, QColor, QPixmap, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QSettings, QSize, QPointF
from PyQt6.QtWidgets import QGraphicsTextItem
from Model_Space import Model_Space
from Model_View import Model_View
from sprinkler import Sprinkler
from pipe import Pipe
from dxf_import_dialog import DxfImportDialog
from Annotations import NoteAnnotation
from dxf_preview_dialog import DxfPreviewDialog
from property_manager import PropertyManager
from scale_manager import DisplayUnit
from layer_manager import LayerManager
from hydraulic_report import HydraulicReportWidget
from user_layer_manager import UserLayerManager, UserLayerWidget
from level_manager import LevelManager, LevelWidget
from paper_space import PaperSpaceWidget, PAPER_SIZES
from ribbon_bar import RibbonBar
from view_3d import View3D
from array_dialog import ArrayDialog
from project_browser import ProjectBrowser
from model_browser import ModelBrowser
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
        self.setWindowTitle("FireFlow Pro \u2014 Untitled")

        # Settings
        self.settings = QSettings("GV", "SprinklerAPP")
        self.current_sprinkler_template = Sprinkler(None)
        self.current_pipe_template = Pipe(None, None)
        self._current_file: str | None = None
        self._modified: bool = False

        # Scene + View
        self.scene = Model_Space()
        self.view = Model_View(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Draw tool style defaults (white pen in dark theme, 1px cosmetic)
        _t = th.detect()
        # Draw colour / lineweight now driven entirely by the active layer
        # (no per-item overrides — see Fix 2 Sprint V)

        # User layer manager — shared between scene and UI
        self.user_layer_mgr = UserLayerManager()
        self.scene._user_layer_manager = self.user_layer_mgr   # for save/load

        # Level manager — shared between scene and UI
        self.level_mgr = LevelManager()
        self.scene._level_manager = self.level_mgr

        # Central tab widget: Model Space | 3D View | Layout 1 (Paper Space)
        self.paper_space_widget = PaperSpaceWidget(self.scene)
        self.view_3d = View3D(self.scene, self.level_mgr, self.scene.scale_manager)
        self.central_tabs = QTabWidget()
        self.central_tabs.addTab(self.view, "Model Space")
        self.central_tabs.addTab(self.view_3d, "3D View")
        self.central_tabs.addTab(self.paper_space_widget, "Layout 1")

        # Ribbon spans full window width (above docks) via setMenuWidget
        self.ribbon = RibbonBar()
        self.setMenuWidget(self.ribbon)
        self.setCentralWidget(self.central_tabs)

        # Property manager (will be added as tab in browser dock)
        self.prop_manager = PropertyManager()
        self.prop_manager.set_level_manager(self.level_mgr)
        self.scene.requestPropertyUpdate.connect(self.prop_manager.show_properties)
        self.view_3d.entitySelected.connect(self.prop_manager.show_properties)
        self.scene.selectionChanged.connect(self.update_property_manager)

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
        self.user_layer_widget.layersChanged.connect(
            self._refresh_modify_layer_combo
        )
        self.user_layer_widget.layersChanged.connect(
            self._refresh_draw_layer_combo
        )

        # Level widget (floor levels)
        self.level_widget = LevelWidget(self.level_mgr, scene=self.scene)
        self.level_widget.activeLevelChanged.connect(self._on_active_level_changed)
        self.level_widget.levelsChanged.connect(
            lambda: self.level_mgr.apply_to_scene(self.scene)
        )
        # (Level combo removed from ribbon — levels managed via Levels tab)
        self.level_widget.duplicateLevel.connect(self.scene.duplicate_level_entities)

        self.project_browser = ProjectBrowser()
        self.project_browser.activateModelSpace.connect(
            lambda: self.central_tabs.setCurrentWidget(self.view)
        )
        self.project_browser.activatePaperSheet.connect(
            self._activate_paper_sheet
        )

        self.model_browser = ModelBrowser()
        self.model_browser.set_scene(self.scene)
        self.model_browser.entitySelected.connect(self.prop_manager.show_properties)

        self._left_tabs = QTabWidget()
        self._left_tabs.setTabPosition(QTabWidget.TabPosition.West)
        self._left_tabs.addTab(self.project_browser, "Project")
        self._left_tabs.addTab(self.model_browser, "Model")
        self._left_tabs.addTab(self.layer_manager, "Underlay")
        self._left_tabs.addTab(self.user_layer_widget, "User Layers")
        self._left_tabs.addTab(self.level_widget, "Levels")

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

        # Properties dock (right side — always visible)
        self.prop_dock = QDockWidget("Properties", self)
        self.prop_dock.setObjectName("PropertiesDock")
        self.prop_dock.setTitleBarWidget(QWidget())   # hide default title bar
        self.prop_dock.setWidget(self.prop_manager)
        self.prop_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.prop_dock)
        self.prop_dock.setMinimumWidth(200)

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
        self.level_label = QLabel("Level: Level 1")
        self.level_label.setMinimumWidth(150)
        status_bar.addPermanentWidget(self.level_label)
        self.scene.cursorMoved.connect(self.coord_label.setText)
        self.scene.modeChanged.connect(self._update_mode_label)
        self.scene.modeChanged.connect(self._sync_mode_buttons)
        self.scene.modeChanged.connect(self._on_mode_changed_template)
        self.scene.sceneModified.connect(self._on_scene_modified)
        self.scene.instructionChanged.connect(
            lambda text: self.mode_label.setText(text)
        )

        self.init_ribbon()

        # Global keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.save_file)
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self.open_file)
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.new_file)
        QShortcut(QKeySequence("Delete"), self).activated.connect(
            self._delete_if_not_editing)
        QShortcut(QKeySequence("Escape"), self).activated.connect(
            lambda: self.scene.set_mode("select"))

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
        _I = lambda name: QIcon(f"graphics/Ribbon/{name}")

        # ── Tab 1: Manage ────────────────────────────────────────────────────
        manage_page = self.ribbon.add_page("Manage")

        # --- File ---
        g_file = manage_page.add_group("File")
        _btn = g_file.add_large_button("Open", _I("load_icon.svg"), self.open_file)
        _btn.setToolTip("Open a saved project [Ctrl+O]")
        _btn = g_file.add_large_button("Save", _I("save_icon.svg"), self.save_file)
        _btn.setToolTip("Save the current project [Ctrl+S]")
        _btn = g_file.add_large_button("Save As", _I("saveas_icon.svg"), self.save_file_as)
        _btn.setToolTip("Save as a new file")

        # --- Import (split menu: PDF / DXF) ---
        g_imp = manage_page.add_group("Import")
        import_menu = QMenu(self)
        import_menu.addAction("PDF Underlay\u2026", self.open_pdf_import_dialog)
        import_menu.addAction("DXF Underlay\u2026", self.open_dxf_import_dialog)
        _btn = g_imp.add_large_menu_button(
            "Import\nUnderlay", _I("import_icon.svg"), import_menu)
        _btn.setToolTip("Import a PDF or DXF underlay")
        _btn = g_imp.add_small_button(
            "Refresh All",
            _I("placeholder_icon.svg"),
            self.refresh_underlays)
        _btn.setToolTip("Re-import all underlays from disk")

        # --- Export (placeholder) ---
        g_exp = manage_page.add_group("Export")
        _exp_btn = g_exp.add_large_button(
            "Export", _I("export_icon.svg"), lambda: None)
        _exp_btn.setEnabled(False)
        _exp_btn.setToolTip("Export functionality — coming soon")

        # --- Project ---
        g_proj = manage_page.add_group("Project")
        _btn = g_proj.add_large_button(
            "Project\nInfo", _I("info_icon.svg"),
            self._open_project_info)
        _btn.setToolTip("View/edit project metadata")

        # --- Settings ---
        g_set = manage_page.add_group("Settings")
        _btn = g_set.add_small_menu_button(
            "Units", _I("info_icon.svg"), self._build_units_menu())
        _btn.setToolTip("Set display units (Imperial/Metric)")
        _btn = g_set.add_small_menu_button(
            "Precision", _I("info_icon.svg"), self._build_precision_menu())
        _btn.setToolTip("Set decimal precision")

        # --- Edit (Undo/Redo always accessible) ---
        g_edit = manage_page.add_group("Edit")
        _btn = g_edit.add_large_button(
            "Undo", _I("undo_icon.svg"),
            self.scene.undo, shortcut="Ctrl+Z")
        _btn.setToolTip("Undo last action [Ctrl+Z]")
        _btn = g_edit.add_large_button(
            "Redo", _I("redo_icon.svg"),
            self.scene.redo, shortcut="Ctrl+Y")
        _btn.setToolTip("Redo last undone action [Ctrl+Y]")

        # --- View ---
        g_view = manage_page.add_group("View")
        _btn = g_view.add_large_button(
            "Fit to\nScreen", _I("placeholder_icon.svg"),
            self.view.fit_to_screen)
        _btn.setToolTip("Zoom to fit all content [F]")

        # --- Panels (dock toggles) ---
        g_pan = manage_page.add_group("Panels")
        prop_btn = g_pan.add_small_button(
            "Properties", _I("info_icon.svg"),
            lambda: self.prop_dock.show())
        prop_btn.setToolTip("Show/hide Properties dock")

        browser_btn = g_pan.add_small_button(
            "Browser",
            _I("placeholder_icon.svg"),
            None, checkable=True)
        browser_btn.setToolTip("Toggle Browser panel")
        browser_btn.toggled.connect(self.browser_dock.setVisible)
        self.browser_dock.visibilityChanged.connect(browser_btn.setChecked)

        report_btn = g_pan.add_small_button(
            "Report Panel", _I("report_icon.svg"), None, checkable=True)
        report_btn.setToolTip("Toggle Hydraulic Report panel")
        report_btn.toggled.connect(
            lambda on: self.hydro_dock.show() if on else self.hydro_dock.hide())
        self.hydro_dock.visibilityChanged.connect(report_btn.setChecked)

        # ── Tab 2: Draw ──────────────────────────────────────────────────────
        draw_page = self.ribbon.add_page("Draw")

        # --- Geometry ---
        g_geom = draw_page.add_group("Geometry")
        # Draw-mode buttons are checkable so the active tool stays highlighted
        self._mode_buttons = {}  # mode_name → QToolButton
        def _mode_btn(group, label, icon, mode_name, large=True):
            """Create a checkable draw-mode button."""
            cb = lambda: self.scene.set_mode(mode_name)
            if large:
                btn = group.add_large_button(label, icon, cb, checkable=True)
            else:
                btn = group.add_small_button(label, icon, cb, checkable=True)
            self._mode_buttons[mode_name] = btn
            return btn
        _mode_btn(g_geom, "Line", _I("line_icon.svg"), "draw_line").setToolTip("Draw a line segment")
        # Rectangle split-menu: main click → draw_rectangle, dropdown → Corner/Center mode
        _rect_btn = g_geom.add_large_button(
            "Rectangle", _I("rectangle_icon.svg"),
            lambda: self.scene.set_mode("draw_rectangle"), checkable=True)
        _rect_btn.setToolTip("Draw a rectangle")
        _rect_menu = QMenu(_rect_btn)
        _rect_corner_act = _rect_menu.addAction("Corner Mode")
        _rect_center_act = _rect_menu.addAction("Center Mode")
        _rect_corner_act.triggered.connect(lambda: self._set_rect_mode(False))
        _rect_center_act.triggered.connect(lambda: self._set_rect_mode(True))
        _rect_btn.setMenu(_rect_menu)
        from PyQt6.QtWidgets import QToolButton
        _rect_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._mode_buttons["draw_rectangle"] = _rect_btn
        _mode_btn(g_geom, "Circle", _I("circle_icon.svg"), "draw_circle").setToolTip("Draw a circle")
        _mode_btn(g_geom, "Polyline", _I("polyline_icon.svg"), "polyline").setToolTip("Draw a polyline (multi-segment)")
        _mode_btn(g_geom, "Arc", _I("arc_icon.svg"), "draw_arc").setToolTip("Draw an arc (3-click)")
        _mode_btn(g_geom, "Gridlines", _I("gridline_icon.svg"), "gridline").setToolTip("Place construction gridlines")
        self._single_place_btn = g_geom.add_small_button(
            "Single\nPlace", _I("placeholder_icon.svg"), None, checkable=True)
        self._single_place_btn.setToolTip("Return to Select mode after placing one item")
        self._single_place_btn.setChecked(False)
        self._single_place_btn.toggled.connect(
            lambda on: setattr(self.scene, 'single_place_mode', on))

        # --- Layer (assigns new geometry to selected layer) ---
        g_draw_layer = draw_page.add_group("Layer")
        self._draw_layer_combo = QComboBox()
        self._draw_layer_combo.setMinimumWidth(130)
        self._draw_layer_combo.addItems([l.name for l in self.user_layer_mgr.layers])
        idx = self._draw_layer_combo.findText(self.scene.active_user_layer)
        if idx >= 0:
            self._draw_layer_combo.setCurrentIndex(idx)
        self._draw_layer_combo.currentTextChanged.connect(self._set_active_draw_layer)
        g_draw_layer._btn_row.addWidget(self._draw_layer_combo)

        # --- Snap ---
        g_snap = draw_page.add_group("Snap")
        self._osnap_btn = g_snap.add_large_button(
            "OSNAP",
            _I("placeholder_icon.svg"),
            self._toggle_osnap, checkable=True, shortcut="F3")
        self._osnap_btn.setChecked(True)
        self._osnap_btn.setToolTip("Object Snap  [F3]")
        _btn = g_snap.add_small_button(
            "Snap to\nUnderlay",
            _I("placeholder_icon.svg"),
            lambda checked: setattr(self.scene, "_snap_to_underlay", checked),
            checkable=True)
        _btn.setToolTip("Snap to DXF underlay geometry")
        _btn = g_snap.add_small_menu_button(
            "Angle Snap",
            _I("placeholder_icon.svg"),
            self._build_snap_angle_menu())
        _btn.setToolTip("Set Ctrl-drag angle snap increment")

        # --- Annotations ---
        g_ann = draw_page.add_group("Annotations")
        _mode_btn(g_ann, "Dimension", _I("dimension_icon.svg"), "dimension").setToolTip("Place a dimension annotation")
        _mode_btn(g_ann, "Text", _I("text_icon.svg"), "text").setToolTip("Place a text note")
        _mode_btn(g_ann, "Hatch", _I("placeholder_icon.svg"), "hatch").setToolTip(
            "Add hatching to a closed object")

        # ── Tab 3: Build ─────────────────────────────────────────────────────
        build_page = self.ribbon.add_page("Build")

        # --- 3D Modeling ---
        g_3d = build_page.add_group("3D Modeling")
        _wall_btn = g_3d.add_large_button(
            "Wall", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("wall"),
            checkable=True)
        _wall_btn.setToolTip("Draw a wall segment")
        self._mode_buttons["wall"] = _wall_btn
        _floor_btn = g_3d.add_large_button(
            "Floor", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("floor"),
            checkable=True)
        _floor_btn.setToolTip("Draw a floor slab boundary")
        _floor_menu = QMenu(_floor_btn)
        _floor_poly_act = _floor_menu.addAction("Floor (Polygon)")
        _floor_rect_act = _floor_menu.addAction("Floor (Rectangle)")
        _floor_poly_act.triggered.connect(lambda: self.scene.set_mode("floor"))
        _floor_rect_act.triggered.connect(lambda: self.scene.set_mode("floor_rect"))
        from PyQt6.QtWidgets import QToolButton
        _floor_btn.setMenu(_floor_menu)
        _floor_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._mode_buttons["floor"] = _floor_btn
        self._mode_buttons["floor_rect"] = _floor_btn  # same button shows checked for both
        _door_btn = g_3d.add_small_button(
            "Door", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("door"),
            checkable=True)
        _door_btn.setToolTip("Place a door opening in a wall")
        self._mode_buttons["door"] = _door_btn
        _window_btn = g_3d.add_small_button(
            "Window", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("window"),
            checkable=True)
        _window_btn.setToolTip("Place a window opening in a wall")
        self._mode_buttons["window"] = _window_btn

        # --- Fire Suppression Systems ---
        g_sys = build_page.add_group("Fire Suppression Systems")
        _pipe_btn = g_sys.add_large_button(
            "Pipe", _I("pipe_icon.svg"),
            lambda: self.scene.set_mode("pipe", self.current_pipe_template),
            checkable=True)
        _pipe_btn.setToolTip("Draw a pipe between two nodes")
        self._mode_buttons["pipe"] = _pipe_btn
        _sprinkler_btn = g_sys.add_large_button(
            "Sprinkler", _I("sprinkler_icon.svg"),
            lambda: self.scene.set_mode("sprinkler", self.current_sprinkler_template),
            checkable=True)
        _sprinkler_btn.setToolTip("Place a sprinkler on a node or pipe")
        self._mode_buttons["sprinkler"] = _sprinkler_btn
        _ws_btn = g_sys.add_large_button(
            "Water\nSupply", _I("supply_icon.svg"),
            lambda: self.scene.set_mode("water_supply"),
            checkable=True)
        _ws_btn.setToolTip("Place the water supply point")
        self._mode_buttons["water_supply"] = _ws_btn
        _da_btn = g_sys.add_large_button(
            "Design\nArea", _I("design_area_icon.svg"),
            lambda: self.scene.set_mode("design_area"),
            checkable=True)
        _da_btn.setToolTip("Define the design area for hydraulic calc")
        self._mode_buttons["design_area"] = _da_btn
        self._coverage_btn = g_sys.add_small_button(
            "Coverage Overlay", _I("sprinkler_icon.svg"),
            self.toggle_coverage_overlay, checkable=True)
        self._coverage_btn.setToolTip("Show/hide sprinkler coverage circles")

        # --- Library ---
        g_lib = build_page.add_group("Library")
        _btn = g_lib.add_large_button(
            "Sprinkler\nManager", _I("sprinkler_manager_icon.svg"),
            self.open_sprinkler_manager)
        _btn.setToolTip("Open sprinkler database manager")

        # ── Tab 4: Modify (always visible, auto-switches on selection) ────────
        modify_page = self.ribbon.add_page("Modify")
        self._modify_tab_idx = self.ribbon._tab_bar.count() - 1

        # --- Edit ---
        g_medit = modify_page.add_group("Edit")
        _btn = g_medit.add_large_button("Undo", _I("undo_icon.svg"), self.scene.undo)
        _btn.setToolTip("Undo last action [Ctrl+Z]")
        _btn = g_medit.add_large_button("Redo", _I("redo_icon.svg"), self.scene.redo)
        _btn.setToolTip("Redo last undone action [Ctrl+Y]")
        _btn = g_medit.add_large_button(
            "Delete", _I("delete_icon.svg"),
            lambda: self.scene.delete_selected_items())
        _btn.setToolTip("Delete selected items [Del]")
        _btn = g_medit.add_small_button(
            "Cut", _I("cut_icon.svg"),
            lambda: (self.scene.copy_selected_items(), self.scene.delete_selected_items()))
        _btn.setToolTip("Cut selected items")
        _btn = g_medit.add_small_button(
            "Copy", _I("copy_icon.svg"),
            lambda: self.scene.copy_selected_items())
        _btn.setToolTip("Copy selected items")
        _btn = g_medit.add_small_button(
            "Paste", _I("paste_icon.svg"),
            lambda: self.scene.paste_items())
        _btn.setToolTip("Paste items")

        # --- Transform ---
        g_xform = modify_page.add_group("Transform")
        _btn = g_xform.add_small_button(
            "Move", _I("move_icon.svg"),
            lambda: self._require_selection(lambda: self.scene.set_mode("move")),
            checkable=True)
        _btn.setToolTip("Move selected items (pick base + dest)")
        self._mode_buttons["move"] = _btn
        _btn = g_xform.add_small_button(
            "Duplicate", _I("duplicate_icon.svg"),
            lambda: self._require_selection(lambda: self.scene.duplicate_selected()))
        _btn.setToolTip("Duplicate selected items in place")
        _btn = g_xform.add_small_button(
            "Array", _I("array_icon.svg"),
            lambda: self._require_selection(self._open_array_dialog))
        _btn.setToolTip("Create linear/radial array of selected items")
        _btn = g_xform.add_small_button(
            "Rotate", _I("rotate_icon.svg"),
            lambda: self._require_selection(lambda: self.scene.set_mode("rotate")),
            checkable=True)
        _btn.setToolTip("Rotate selected items interactively (pick pivot, then angle)")
        self._mode_buttons["rotate"] = _btn
        _btn = g_xform.add_small_button(
            "Scale", _I("scale_icon.svg"),
            lambda: self._require_selection(lambda: self.scene.set_mode("scale")),
            checkable=True)
        _btn.setToolTip("Scale selected items interactively (pick base, Tab for factor)")
        self._mode_buttons["scale"] = _btn
        _btn = g_xform.add_small_button(
            "Mirror", _I("placeholder_icon.svg"),
            lambda: self._require_selection(lambda: self.scene.set_mode("mirror")),
            checkable=True)
        _btn.setToolTip("Mirror selected items across an axis (2 clicks)")
        self._mode_buttons["mirror"] = _btn
        _btn = g_xform.add_small_button(
            "Offset", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("offset"),
            checkable=True)
        _btn.setToolTip("Offset geometry by a distance")
        self._mode_buttons["offset"] = _btn
        _mode_btn(g_xform, "Stretch", _I("placeholder_icon.svg"), "stretch", large=False).setToolTip(
            "Stretch items using crossing selection")
        _mode_btn(g_xform, "Trim", _I("trim_icon.svg"), "trim", large=False).setToolTip(
            "Trim geometry at intersection")
        _mode_btn(g_xform, "Extend", _I("placeholder_icon.svg"), "extend", large=False).setToolTip(
            "Extend geometry to boundary")
        _mode_btn(g_xform, "Fillet", _I("placeholder_icon.svg"), "fillet", large=False).setToolTip(
            "Round corner between two lines (Tab for radius)")
        _mode_btn(g_xform, "Chamfer", _I("placeholder_icon.svg"), "chamfer", large=False).setToolTip(
            "Bevel corner between two lines (Tab for distance)")
        _mode_btn(g_xform, "Break", _I("placeholder_icon.svg"), "break", large=False).setToolTip(
            "Break object between two points")
        _mode_btn(g_xform, "Break at\nPoint", _I("placeholder_icon.svg"), "break_at_point", large=False).setToolTip(
            "Split object at a single point")
        _btn = g_xform.add_small_button(
            "Join", _I("placeholder_icon.svg"),
            lambda: self._require_selection(lambda: self.scene.join_selected_items()))
        _btn.setToolTip("Join connected lines/polylines into one polyline")
        _btn = g_xform.add_small_button(
            "Explode", _I("placeholder_icon.svg"),
            lambda: self._require_selection(lambda: self.scene.explode_selected_items()))
        _btn.setToolTip("Explode polylines/rectangles into individual lines")
        _mode_btn(g_xform, "Merge\nPoints", _I("placeholder_icon.svg"), "merge_points", large=False).setToolTip(
            "Merge two endpoints")

        # --- Constraints ---
        g_constraint = modify_page.add_group("Constraints")
        _mode_btn(g_constraint, "Concentric", _I("placeholder_icon.svg"),
                  "constraint_concentric", large=False).setToolTip(
            "Make two circles share the same center")
        _mode_btn(g_constraint, "Distance", _I("placeholder_icon.svg"),
                  "constraint_dimensional", large=False).setToolTip(
            "Fix the distance between two points")

        # --- Layer ---
        g_layer = modify_page.add_group("Layer")
        self._modify_layer_combo = QComboBox()
        self._modify_layer_combo.setMinimumWidth(120)
        self._modify_layer_combo.addItems([l.name for l in self.user_layer_mgr.layers])
        self._modify_layer_combo.currentTextChanged.connect(self._assign_layer_to_selection)
        g_layer._btn_row.addWidget(self._modify_layer_combo)

        # --- Text Formatting (shown when text is selected) ---
        g_text = modify_page.add_group("Text")
        self._text_format_group = g_text

        self._text_size_spin = QSpinBox()
        self._text_size_spin.setRange(4, 200)
        self._text_size_spin.setValue(12)
        self._text_size_spin.setSuffix(" pt")
        self._text_size_spin.setFixedWidth(80)
        self._text_size_spin.valueChanged.connect(self._set_text_size)

        self._text_bold_btn = QPushButton("B")
        self._text_bold_btn.setCheckable(True)
        self._text_bold_btn.setFixedSize(28, 28)
        self._text_bold_btn.setStyleSheet("font-weight: bold;")
        self._text_bold_btn.toggled.connect(self._toggle_text_bold)

        self._text_italic_btn = QPushButton("I")
        self._text_italic_btn.setCheckable(True)
        self._text_italic_btn.setFixedSize(28, 28)
        self._text_italic_btn.setStyleSheet("font-style: italic;")
        self._text_italic_btn.toggled.connect(self._toggle_text_italic)

        self._text_align_combo = QComboBox()
        self._text_align_combo.addItems(["Left", "Center", "Right"])
        self._text_align_combo.setFixedWidth(80)
        self._text_align_combo.currentTextChanged.connect(self._set_text_alignment)

        # Add widgets into the group layout
        text_row1 = QHBoxLayout()
        text_row1.addWidget(QLabel("Size:"))
        text_row1.addWidget(self._text_size_spin)
        text_row1.addWidget(self._text_bold_btn)
        text_row1.addWidget(self._text_italic_btn)
        text_row2 = QHBoxLayout()
        text_row2.addWidget(QLabel("Align:"))
        text_row2.addWidget(self._text_align_combo)

        text_container = QVBoxLayout()
        text_container.setSpacing(2)
        text_container.addLayout(text_row1)
        text_container.addLayout(text_row2)

        # Insert into the group's outer layout (before the label row)
        g_text.layout().insertLayout(0, text_container)
        g_text.setVisible(False)  # hidden until text is selected

        # Auto-switch to Modify tab when items are selected
        self.scene.selectionChanged.connect(self._on_selection_changed_modify)

        # ── Tab 5: Analyze ───────────────────────────────────────────────────
        analyze_page = self.ribbon.add_page("Analyze")

        # --- Hydraulics ---
        g_hyd = analyze_page.add_group("Hydraulics")
        _btn = g_hyd.add_large_button(
            "Run\nHydraulics", _I("hydraulics_icon.svg"),
            self.run_hydraulics, shortcut="F5")
        _btn.setToolTip("Run hydraulic calculation [F5]")
        _btn = g_hyd.add_large_button(
            "Clear\nResults", _I("clear_icon.svg"),
            self.clear_hydraulics)
        _btn.setToolTip("Clear hydraulic overlay and results")

        # --- Export ---
        g_exp = analyze_page.add_group("Export")
        _btn = g_exp.add_large_button(
            "Export PDF", _I("export_icon.svg"),
            self.hydro_report._export_pdf)
        _btn.setToolTip("Export hydraulic report to PDF")
        _btn = g_exp.add_large_button(
            "Export CSV", _I("report_icon.svg"),
            self.hydro_report._export_csv)
        _btn.setToolTip("Export hydraulic results to CSV")

        # ── Tab 6: Draft ─────────────────────────────────────────────────────
        draft_page = self.ribbon.add_page("Draft")

        # --- Workspace ---
        g_ws = draft_page.add_group("Workspace")
        _btn = g_ws.add_large_button(
            "Model\nSpace",
            _I("placeholder_icon.svg"),
            lambda: self.central_tabs.setCurrentIndex(0))
        _btn.setToolTip("Switch to Model Space view")
        _btn = g_ws.add_large_button(
            "Layout 1\nPaper",
            _I("placeholder_icon.svg"),
            lambda: self.central_tabs.setCurrentIndex(1))
        _btn.setToolTip("Switch to Paper Space layout")

        # --- Page ---
        g_pg = draft_page.add_group("Page")
        _btn = g_pg.add_large_menu_button(
            "Paper Size",
            _I("placeholder_icon.svg"),
            self._build_paper_size_menu())
        _btn.setToolTip("Change paper sheet size")
        _btn = g_pg.add_large_button(
            "Title Block",
            _I("placeholder_icon.svg"),
            self.paper_space_widget.edit_title_block)
        _btn.setToolTip("Edit title block fields")

    # ── Project Information dialog ────────────────────────────────────────────

    def _open_project_info(self):
        """Open a dialog to view/edit project metadata."""
        info = getattr(self.scene, "_project_info", {})
        dlg = QDialog(self)
        dlg.setWindowTitle("Project Information")
        dlg.setMinimumWidth(400)
        form = QVBoxLayout(dlg)

        fields = [
            ("Project Name", "name"),
            ("Project Number", "number"),
            ("Address", "address"),
            ("City", "city"),
            ("State / Province", "state"),
            ("Client", "client"),
            ("Designer", "designer"),
            ("Description", "description"),
        ]
        editors = {}
        for label, key in fields:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{label}:"))
            le = QLineEdit(info.get(key, ""))
            editors[key] = le
            row.addWidget(le)
            form.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addWidget(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_info = {k: le.text() for k, le in editors.items()}
            self.scene._project_info = new_info

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

    def _set_active_draw_layer(self, layer_name: str):
        """Set the active layer for new geometry from the Draw tab combo."""
        self.scene.active_user_layer = layer_name

    def _refresh_draw_layer_combo(self):
        """Re-populate the Draw ribbon's layer dropdown after layers change."""
        combo = self._draw_layer_combo
        combo.blockSignals(True)
        current = combo.currentText()
        combo.clear()
        combo.addItems([l.name for l in self.user_layer_mgr.layers])
        idx = combo.findText(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    # ── Level helpers ──────────────────────────────────────────────────────────

    def _on_active_level_changed(self, name: str):
        """Handle active level change from widget or ribbon combo."""
        self.scene.active_level = name
        self.level_mgr.active_level = name
        self.level_mgr.apply_to_scene(self.scene)
        self.level_label.setText(f"Level: {name}")

    # ── Template workflow helpers ─────────────────────────────────────────────

    def _set_rect_mode(self, from_center: bool):
        """Switch rectangle drawing between corner and center mode."""
        self.scene._draw_rect_from_center = from_center
        self.scene.set_mode("draw_rectangle")

    def _on_mode_changed_template(self, mode: str):
        """Show pre-placement template properties when entering wall/floor/geometry mode."""
        if mode == "wall":
            template = self.scene._get_wall_template()
            template._alignment = self.scene._wall_alignment
            self.prop_manager.show_properties(template)
        elif mode in ("floor", "floor_rect"):
            template = self.scene._get_floor_template()
            self.prop_manager.show_properties(template)
        elif mode in ("draw_line", "draw_rectangle", "draw_circle", "draw_arc",
                       "polyline"):
            template = self.scene._get_geometry_template()
            self.prop_manager.show_properties(template)

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
        "draw_arc":       "Click center, then start angle, then end angle",
        "polyline":       "Click to add points, right-click to finish (Tab for exact input)",
        "dimension":      "Click P1 \u2192 P2 \u2192 drag offset, click to finalize",
        "text":           "Click first corner, then drag to define text area",
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

    def _sync_mode_buttons(self, mode: str):
        """Keep draw-mode buttons checked/unchecked to match the active mode."""
        for m, btn in self._mode_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(m == mode)
            btn.blockSignals(False)

    # ── Modify tab auto-switch (Sprint N) ──────────────────────────────────

    _DRAW_MODES = {"draw_line", "draw_rectangle", "draw_circle", "draw_arc",
                    "polyline", "dimension", "text", "pipe", "sprinkler",
                    "water_supply", "design_area", "set_scale", "offset",
                    "offset_side", "wall", "floor", "floor_rect", "door", "window"}

    def _on_selection_changed_modify(self):
        """Auto-switch to Modify tab when items are selected (unless drawing)."""
        sel = self.scene.selectedItems()
        if sel and self.scene.mode not in self._DRAW_MODES:
            self.ribbon._tab_bar.setCurrentIndex(self._modify_tab_idx)
            # Update layer combo to show selected item's layer
            if hasattr(sel[0], "user_layer"):
                layer = getattr(sel[0], "user_layer", "0")
                idx = self._modify_layer_combo.findText(layer)
                if idx >= 0:
                    self._modify_layer_combo.blockSignals(True)
                    self._modify_layer_combo.setCurrentIndex(idx)
                    self._modify_layer_combo.blockSignals(False)
            # Show/hide text formatting group
            has_text = any(isinstance(i, NoteAnnotation) for i in sel)
            self._text_format_group.setVisible(has_text)
            if has_text:
                txt = next(i for i in sel if isinstance(i, NoteAnnotation))
                props = txt.get_properties()
                self._text_size_spin.blockSignals(True)
                self._text_size_spin.setValue(
                    int(props.get("FontSize", {}).get("value", "12")))
                self._text_size_spin.blockSignals(False)
                self._text_bold_btn.blockSignals(True)
                self._text_bold_btn.setChecked(
                    props.get("Bold", {}).get("value", "Off") == "On")
                self._text_bold_btn.blockSignals(False)
                self._text_italic_btn.blockSignals(True)
                self._text_italic_btn.setChecked(
                    props.get("Italic", {}).get("value", "Off") == "On")
                self._text_italic_btn.blockSignals(False)
                self._text_align_combo.blockSignals(True)
                self._text_align_combo.setCurrentText(
                    props.get("Alignment", {}).get("value", "Left"))
                self._text_align_combo.blockSignals(False)
        else:
            self._text_format_group.setVisible(False)

    def _require_selection(self, action):
        """Run *action* only if something is selected; otherwise show message."""
        if not self.scene.selectedItems():
            self.statusBar().showMessage("Select an item first", 3000)
            return
        action()

    def _refresh_modify_layer_combo(self):
        """Re-populate the Modify ribbon's layer dropdown after layers change."""
        combo = self._modify_layer_combo
        combo.blockSignals(True)
        current = combo.currentText()
        combo.clear()
        combo.addItems([l.name for l in self.user_layer_mgr.layers])
        idx = combo.findText(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def _assign_layer_to_selection(self, layer_name: str):
        """Assign a user layer to all selected items."""
        for item in self.scene.selectedItems():
            if hasattr(item, "user_layer"):
                item.user_layer = layer_name

    # ── Text formatting handlers ──────────────────────────────────────────

    def _set_text_size(self, size: int):
        for item in self.scene.selectedItems():
            if isinstance(item, NoteAnnotation):
                item.set_property("FontSize", str(size))
        self.scene.push_undo_state()

    def _toggle_text_bold(self, checked: bool):
        for item in self.scene.selectedItems():
            if isinstance(item, NoteAnnotation):
                item.set_property("Bold", "On" if checked else "Off")
        self.scene.push_undo_state()

    def _toggle_text_italic(self, checked: bool):
        for item in self.scene.selectedItems():
            if isinstance(item, NoteAnnotation):
                item.set_property("Italic", "On" if checked else "Off")
        self.scene.push_undo_state()

    def _set_text_alignment(self, alignment: str):
        for item in self.scene.selectedItems():
            if isinstance(item, NoteAnnotation):
                item.set_property("Alignment", alignment)
        self.scene.push_undo_state()

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

    # init_property_manager_dock removed — Properties is now a tab in browser dock

    # ─────────────────────────────────────────────────────────────────────────
    # MENU BAR HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def save_file(self):
        if self._current_file:
            if self.scene.save_to_file(self._current_file):
                self._modified = False
                self._update_title()
        else:
            self.save_file_as()

    def save_file_as(self):
        file, _ = QFileDialog.getSaveFileName(self, "Save CAD Scene", "", "JSON Files (*.json)")
        if file:
            self._current_file = file
            if self.scene.save_to_file(file):
                self._modified = False
                self._update_title()

    def open_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Load CAD Scene", "", "JSON Files (*.json)")
        if file:
            self._current_file = file
            self.scene.load_from_file(file)
            self.level_widget.populate()

            self.user_layer_widget.populate()
            self.level_label.setText(f"Level: {self.level_mgr.active_level}")
            self._modified = False
            self._update_title()

    def new_file(self):
        """Clear the scene and start a fresh project."""
        self._current_file = None
        self.scene._clear_scene()
        self.level_widget.populate()
        self.user_layer_widget.populate()
        self.level_label.setText("Level: Level 1")
        self._modified = False
        self._update_title()

    def _update_title(self):
        name = os.path.basename(self._current_file) if self._current_file else "Untitled"
        star = " *" if self._modified else ""
        self.setWindowTitle(f"FireFlow Pro \u2014 {name}{star}")

    def _on_scene_modified(self):
        self._modified = True
        self._update_title()

    def _delete_if_not_editing(self):
        """Delete selected items unless a text item is being edited."""
        focus = self.scene.focusItem()
        if isinstance(focus, QGraphicsTextItem) and focus.hasFocus():
            return  # let the text editor handle Delete
        self.scene.delete_selected_items()

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
            # Switch to model space
            self.central_tabs.setCurrentWidget(self.view)
            if params.insert_at_origin:
                # Place immediately at scene origin
                self.scene._place_import_params = params
                self.scene._commit_place_import(QPointF(0, 0))
            else:
                # Enter interactive placement mode (ghost follows cursor)
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
            self.prop_manager.show_properties(items)
        else:
            self.prop_manager.show_properties(None)

    # ─────────────────────────────────────────────────────────────────────────
    # EVENT HANDLING
    # ─────────────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._modified:
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                self.save_file()
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        self.save_settings()
        super().closeEvent(event)

    _STATE_VERSION = 3  # bump when dock layout changes between sprints

    def save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState(self._STATE_VERSION))
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