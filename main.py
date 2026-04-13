import sys, os
from PyQt6.QtWidgets import (QApplication, QMainWindow,
                              QFileDialog, QDockWidget, QInputDialog,
                              QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QSpinBox, QDialogButtonBox, QLineEdit,
                              QTabWidget, QMenu, QWidget, QMessageBox,
                              QComboBox, QDoubleSpinBox, QFormLayout,
                              QProgressBar, QToolButton, QProgressDialog)
from PyQt6.QtGui import QPainter, QIcon, QColor, QPixmap, QKeySequence, QShortcut, QFont
from PyQt6.QtCore import Qt, QSettings, QSize, QPointF, QTimer, pyqtSignal
from PyQt6.QtWidgets import QGraphicsTextItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.sprinkler import Sprinkler
from firepro3d.pipe import Pipe
from firepro3d.annotations import NoteAnnotation
from firepro3d.dxf_preview_dialog import UnderlayImportDialog
from firepro3d.property_manager import PropertyManager
from firepro3d.scale_manager import DisplayUnit
from firepro3d.hydraulic_report import HydraulicReportWidget
from firepro3d.thermal_radiation_report import ThermalRadiationReportWidget
from firepro3d.user_layer_manager import UserLayerManager, UserLayerWidget
from firepro3d.level_manager import LevelManager, PlanViewManager
from firepro3d.level_widget import LevelWidget
from firepro3d.paper_space import PaperSpaceWidget, PAPER_SIZES
from firepro3d.ribbon_bar import RibbonBar
# view_3d deferred — imports pyvista/VTK which is slow
from firepro3d.array_dialog import ArrayDialog
from firepro3d.project_browser import ProjectBrowser
from firepro3d.model_browser import ModelBrowser
from firepro3d.grid_lines_dialog import GridLinesDialog
from firepro3d.constants import DEFAULT_GRIDLINE_SPACING_IN, DEFAULT_GRIDLINE_LENGTH_IN
from firepro3d import theme as th


# ─────────────────────────────────────────────────────────────────────────────
# Splash / Loading Screen
# ─────────────────────────────────────────────────────────────────────────────

class _SplashScreen(QWidget):
    """Frameless loading screen with logo and blue progress bar."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._splash_w = 480
        self._splash_h = 320
        self.setFixedSize(self._splash_w, self._splash_h)

        # Centre on screen
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.x() + (geo.width() - self._splash_w) // 2,
                geo.y() + (geo.height() - self._splash_h) // 2,
            )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(6)

        # Logo
        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_lbl.setStyleSheet(
            "background: #f1f7f7; border-radius: 6px; padding: 8px;"
        )
        from firepro3d.assets import asset_path as _asset_path
        logo_path = _asset_path("Program Icon", "Logo.png")
        if os.path.isfile(logo_path):
            from PyQt6.QtCore import QSize
            logo_pm = QPixmap(logo_path).scaled(
                QSize(464, 240),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_lbl.setPixmap(logo_pm)
        else:
            # Fallback text if logo file is missing
            logo_lbl.setText("FirePro 3D")
            f = QFont("Segoe UI", 22)
            f.setBold(True)
            logo_lbl.setFont(f)
        layout.addWidget(logo_lbl)

        layout.addStretch()

        # Combined progress bar with overlaid status text
        from PyQt6.QtWidgets import QStackedLayout

        bar_container = QWidget()
        bar_container.setFixedHeight(28)
        stack = QStackedLayout(bar_container)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.setContentsMargins(0, 0, 0, 0)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet("""
            QProgressBar {
                background: #e0e0e0;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: #3399ff;
                border-radius: 4px;
            }
        """)

        self._status = QLabel("Loading...")
        self._status.setFont(QFont("Segoe UI", 8))
        self._status.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._status.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._status.setObjectName("splashStatus")
        self._status.setStyleSheet(
            "#splashStatus { color: #555555; background: transparent;"
            " padding-left: 8px; border: none; outline: none; }"
        )

        # Bar first (bottom of stack), then text on top
        stack.addWidget(self._bar)
        stack.addWidget(self._status)
        self._status.raise_()

        layout.addWidget(bar_container)

        # Scope stylesheet to _SplashScreen only so it doesn't cascade
        self.setObjectName("splashRoot")
        self.setStyleSheet(
            "#splashRoot { background: #ffffff; border: 1px solid #cccccc; border-radius: 8px; }"
        )

    # ── Public helpers ─────────────────────────────────────────────────────────

    def set_progress(self, value: int, message: str = ""):
        self._bar.setValue(value)
        if message:
            self._status.setText(message)
        QApplication.processEvents()


# ─────────────────────────────────────────────────────────────────────────────
# Main Window
# ─────────────────────────────────────────────────────────────────────────────


class _OsnapIndicatorLabel(QLabel):
    """Clickable status-bar label for the OSNAP state indicator."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("OSNAP", parent)
        self.setToolTip("Toggle Object Snap (F3)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(80)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("osnapOn", True)
        self._apply_style()

    def setOsnapOn(self, on: bool) -> None:
        self.setProperty("osnapOn", bool(on))
        self._apply_style()

    def _apply_style(self) -> None:
        on = bool(self.property("osnapOn"))
        if on:
            self.setStyleSheet(
                "font-weight: bold; color: #44ff88; "
                "background: #1a3a24; padding: 2px 10px; "
                "border: 1px solid #44ff88; border-radius: 3px;"
            )
        else:
            self.setStyleSheet(
                "font-weight: bold; color: #888; "
                "background: transparent; padding: 2px 10px; "
                "border: 1px solid #555; border-radius: 3px;"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, splash: _SplashScreen | None = None):
        super().__init__()
        self.setWindowTitle("FirePro 3D \u2014 Untitled")
        # Window icon from logo
        from firepro3d.assets import asset_path as _asset_path
        _logo = _asset_path("Program Icon", "Logo.png")
        if os.path.isfile(_logo):
            self.setWindowIcon(QIcon(_logo))
        self._splash = splash

        # Settings
        self.settings = QSettings("GV", "FirePro3D")
        self.current_sprinkler_template = Sprinkler(None)
        self.current_pipe_template = Pipe(None, None)
        self._current_file: str | None = None
        self._modified: bool = False
        self._MAX_RECENT = 8
        self._recent_files: list[str] = self.settings.value("recent_files", [], type=list)

        # Auto-save every 2 minutes for crash recovery
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(2 * 60 * 1000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

        # Scene + View
        self._splash_progress(10, "Initialising scene...")
        self.scene = Model_Space()
        # Give templates a scene reference so they can always find the
        # *current* scale_manager (survives _clear_scene resets).
        self.current_pipe_template._scene_ref = self.scene
        self.current_sprinkler_template._scene_ref = self.scene
        self.view = Model_View(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Drag-drop import
        self.view.drop_import_requested.connect(self._on_drop_import)

        # Draw tool style defaults (white pen in dark theme, 1px cosmetic)
        _t = th.detect()
        # Draw colour / lineweight now driven entirely by the active layer
        # (no per-item overrides — see Fix 2 Sprint V)

        # User layer manager — shared between scene and UI
        self._splash_progress(25, "Setting up layers...")
        self.user_layer_mgr = UserLayerManager()
        self.scene._user_layer_manager = self.user_layer_mgr   # for save/load

        # Level manager — shared between scene and UI
        self.level_mgr = LevelManager()
        self.scene._level_manager = self.level_mgr
        self.plan_view_mgr = PlanViewManager()
        self.scene._plan_view_manager = self.plan_view_mgr

        # Central tab widget: Model Space | 3D View | Layout 1 (Paper Space)
        self._splash_progress(35, "Building 3D viewport...")
        self.paper_space_widget = PaperSpaceWidget(self.scene)
        self.view_3d = View3D(self.scene, self.level_mgr, self.scene.scale_manager)
        self.central_tabs = QTabWidget()
        self.central_tabs.setTabsClosable(True)
        self.central_tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        # White close-button icon for dark theme
        self._setup_tab_close_icon()
        self.central_tabs.addTab(self.view_3d, "3D Model")
        # Protect core tabs from being closed (hide their close buttons)
        for i in range(self.central_tabs.count()):
            self.central_tabs.tabBar().setTabButton(
                i, self.central_tabs.tabBar().ButtonPosition.RightSide, None)

        # Ribbon spans full window width (above docks) via setMenuWidget
        self._splash_progress(55, "Building ribbon toolbar...")
        self.ribbon = RibbonBar()
        self.setMenuWidget(self.ribbon)
        self.setCentralWidget(self.central_tabs)
        self.central_tabs.currentChanged.connect(self._on_tab_changed)
        # Right-click context menu on plan tabs (View Range)
        self.central_tabs.tabBar().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.central_tabs.tabBar().customContextMenuRequested.connect(
            self._on_tab_context_menu)

        # Property manager (will be added as tab in browser dock)
        self._splash_progress(65, "Setting up panels...")
        self.prop_manager = PropertyManager()
        self.prop_manager.set_level_manager(self.level_mgr)
        self.prop_manager.set_user_layer_manager(self.user_layer_mgr)
        self.scene.requestPropertyUpdate.connect(self.prop_manager.show_properties)
        self.view_3d.entitySelected.connect(self.prop_manager.show_properties)
        self.scene.selectionChanged.connect(self.update_property_manager)

        # Combined left-side dock: User Layers | Project Browser | Model Browser
        self.user_layer_widget = UserLayerWidget(
            self.user_layer_mgr, scene=self.scene
        )
        self.user_layer_widget.activeLayerChanged.connect(
            lambda name: setattr(self.scene, "active_user_layer", name)
        )
        self.user_layer_widget.layersChanged.connect(
            lambda: self.level_mgr.apply_to_scene(self.scene)
        )
        self.user_layer_widget.layersChanged.connect(
            self._refresh_modify_layer_combo
        )
        # (Layer group removed — layer assignment is via item properties panel)

        # Level widget (floor levels)
        self.level_widget = LevelWidget(self.level_mgr, scene=self.scene)
        self.level_widget.activeLevelChanged.connect(self._on_active_level_changed)
        self.level_widget.levelsChanged.connect(
            lambda: self.level_mgr.apply_to_scene(self.scene)
        )
        self.level_widget.levelsChanged.connect(self.update_property_manager)
        # (Level combo removed from ribbon — levels managed via Levels tab)
        self.level_widget.duplicateLevel.connect(self.scene.duplicate_level_entities)

        self.project_browser = ProjectBrowser(level_manager=self.scene._level_manager,
                                                     scale_manager=self.scene.scale_manager)
        self.project_browser.activateModelSpace.connect(
            lambda: self._activate_plan_view(self.scene.active_level)
        )
        self.project_browser.activatePaperSheet.connect(
            self._activate_paper_sheet
        )
        self.project_browser.createPaperSheet.connect(
            self._activate_paper_sheet
        )
        self.project_browser.activateElevation.connect(self._activate_elevation)
        self.project_browser.activatePlanView.connect(self._activate_plan_view)
        self.project_browser.activateDetailView.connect(self._activate_detail_view)
        self.project_browser.deleteDetailView.connect(self._delete_detail_view)
        self.level_widget.levelsChanged.connect(self.project_browser.refresh_levels)

        # Elevation Manager — QGraphicsScene-based elevation views
        # (connect after elevation_manager is created below)
        from firepro3d.elevation_manager import ElevationManager
        self.elevation_manager = ElevationManager(
            self.scene, self.level_mgr, self.scene.scale_manager,
            self.central_tabs,
        )
        # Expose on the scene so the Display Manager can trigger rebuilds
        self.scene._elevation_manager = self.elevation_manager
        self.level_widget.levelsChanged.connect(self.elevation_manager.rebuild_all)

        # Detail View Manager
        from firepro3d.detail_view import DetailViewManager
        self.detail_manager = DetailViewManager(
            self.scene, self.level_mgr, self.scene.scale_manager,
            self.central_tabs,
        )
        self.scene._detail_manager = self.detail_manager
        self.scene._on_detail_created = self._refresh_detail_browser

        self.model_browser = ModelBrowser()
        self.model_browser.set_scene(self.scene)
        self.model_browser.entitySelected.connect(self.prop_manager.show_properties)
        self.scene.selectionChanged.connect(self.model_browser.sync_from_scene)
        self.scene.sceneModified.connect(self.model_browser.refresh)

        self._left_tabs = QTabWidget()
        self._left_tabs.setTabPosition(QTabWidget.TabPosition.West)
        self._left_tabs.addTab(self.project_browser, "Project")
        self._left_tabs.addTab(self.model_browser, "Model")
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

        # Thermal Radiation report dock
        self.radiation_report = ThermalRadiationReportWidget()
        self.radiation_dock = QDockWidget("Thermal Radiation Report", self)
        self.radiation_dock.setObjectName("RadiationDock")
        self.radiation_dock.setWidget(self.radiation_report)
        self.radiation_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea |
            Qt.DockWidgetArea.TopDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.radiation_dock)
        self.radiation_dock.hide()

        # Radiation selection state
        self._radiation_step = 0
        self._radiation_emitters = None
        self._radiation_receivers = None

        # Status bar with cursor coordinates
        status_bar = self.statusBar()
        # OSNAP status-bar indicator (snap-spec §9.5 / §12 item 11).
        # Added BEFORE coord_label so it sits to the left of the
        # coordinate readout, clear of the QSizeGrip at the far right.
        self.osnap_indicator = _OsnapIndicatorLabel(self)
        self.osnap_indicator.clicked.connect(self.scene.toggle_osnap)
        status_bar.addPermanentWidget(self.osnap_indicator)
        self.scene.osnapToggled.connect(self._update_osnap_indicator)
        self._update_osnap_indicator(self.scene._osnap_enabled)
        self.coord_label = QLabel("X: —   Y: —")
        self.coord_label.setMinimumWidth(280)
        status_bar.addPermanentWidget(self.coord_label)
        # Mode name badge — prominent indicator of active mode
        self.mode_name_label = QLabel("Select")
        self.mode_name_label.setStyleSheet(
            "font-weight: bold; color: #44aaff; padding: 2px 8px; "
            "border: 1px solid #44aaff; border-radius: 3px;"
        )
        self.mode_name_label.setMinimumWidth(100)
        status_bar.addWidget(self.mode_name_label)
        self.mode_label = QLabel("")
        status_bar.addWidget(self.mode_label)
        # Level indicator removed — active level is now implicit from the plan tab
        self.scene.cursorMoved.connect(self.coord_label.setText)
        self.scene.modeChanged.connect(self._update_mode_label)
        self.scene.modeChanged.connect(self._sync_mode_buttons)
        self.scene.modeChanged.connect(self._on_mode_changed_template)
        self.scene.sceneModified.connect(self._on_scene_modified)
        self.scene.radiationConfirm.connect(self._radiation_on_confirm)
        self.scene.radiationCancel.connect(self._radiation_on_cancel)
        self.scene.instructionChanged.connect(
            lambda text: self.mode_label.setText(text)
        )
        self.scene.openViewRequested.connect(self._on_open_view_requested)
        self.scene.numericInputRequested.connect(self._on_numeric_input_requested)
        self.scene.warningIssued.connect(self._on_warning_issued)
        self.scene.confirmRequested.connect(self._on_confirm_requested)

        self._splash_progress(80, "Wiring up controls...")
        self.init_ribbon()

        # Global keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.save_file)

        # F3 global OSNAP toggle is bound via the existing ribbon OSNAP
        # QAction (see init_ribbon / _toggle_osnap). The status-bar
        # indicator stays in sync via the osnapToggled signal.
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self.open_file)
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.new_file)
        QShortcut(QKeySequence("Delete"), self).activated.connect(
            self._delete_if_not_editing)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._on_escape)
        QShortcut(QKeySequence("Ctrl+C"), self).activated.connect(
            self.scene.copy_selected_items)
        QShortcut(QKeySequence("Ctrl+V"), self).activated.connect(
            lambda: self.scene.set_mode("paste"))
        QShortcut(QKeySequence("Ctrl+A"), self).activated.connect(
            self.view._select_all_items)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(
            lambda: self.scene.set_mode("duplicate"))

        # Restore settings
        self._splash_progress(90, "Restoring settings...")
        self.restore_settings()
        self._splash_progress(100, "Ready")

        # New-project setup — mirrors new_file() without the save prompt
        self.scene._clear_scene()
        self.level_widget.populate()
        self.user_layer_widget.populate()
        pass  # level indicator removed
        self._place_default_gridlines()
        self._create_elevation_markers()
        from firepro3d.display_manager import apply_default_display_settings
        apply_default_display_settings(self.scene)
        self._apply_persistent_unit_prefs()
        self._current_file = None
        self._modified = False
        self._update_title()
        self._initial_fit_done = False  # fit_to_screen deferred to showEvent

        # Defer recovery check until after the window is fully shown
        QTimer.singleShot(500, self._check_recovery)

    def _splash_progress(self, value: int, message: str = ""):
        """Update the splash screen progress bar if present."""
        if self._splash is not None:
            self._splash.set_progress(value, message)

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
        # Properties panel defaults to visible; honour saved preference only
        # when the user explicitly hid it (saved as False).
        self.prop_dock.setVisible(self.settings.value("dock/properties", True, type=bool))
        if self.settings.contains("dock/hydraulics"):
            self.hydro_dock.setVisible(self.settings.value("dock/hydraulics", False, type=bool))
        # Restore snap settings
        if self.settings.contains("snap/grid_size"):
            grid = self.settings.value("snap/grid_size", 10, type=float)
            self.view.set_grid(self.view._grid_visible, grid)
        if self.settings.contains("snap/angle_deg"):
            self.scene._snap_angle_deg = self.settings.value("snap/angle_deg", 45, type=float)
        if self.settings.contains("snap/tolerance_px"):
            from firepro3d import snap_engine
            snap_engine.SNAP_TOLERANCE_PX = self.settings.value("snap/tolerance_px", 40, type=int)
        if self.settings.contains("snap/grip_tolerance_px"):
            self.scene._grip_tolerance_px = self.settings.value(
                "snap/grip_tolerance_px", 200, type=int)
        # Restore per-type snap toggles
        _snap_attrs = ["snap_endpoint", "snap_midpoint", "snap_intersection",
                       "snap_center", "snap_quadrant", "snap_nearest",
                       "snap_perpendicular", "snap_tangent"]
        for attr in _snap_attrs:
            if self.settings.contains(f"snap/{attr}"):
                val = self.settings.value(f"snap/{attr}", True)
                if isinstance(val, str):
                    val = val.lower() not in ("false", "0")
                setattr(self.scene._snap_engine, attr, bool(val))
        # Restore display unit and precision from user preference
        self._apply_persistent_unit_prefs()
        # Restore pipe and sprinkler template settings
        if self.settings.contains("template/pipe"):
            pipe_props = self.settings.value("template/pipe", {})
            if isinstance(pipe_props, dict):
                for k, v in pipe_props.items():
                    if k == "Ceiling Offset":
                        # Value is stored as raw mm — bypass set_property
                        # which would re-parse through parse_dimension and
                        # misinterpret the bare number as display units.
                        try:
                            raw_mm = float(v)
                            # Sanity: ceiling offsets beyond ±10 m are almost
                            # certainly corrupted by the old double-parse bug.
                            if abs(raw_mm) > 10000:
                                raw_mm = -50.8  # reset to default -2"
                            self.current_pipe_template.ceiling_offset = raw_mm
                            self.current_pipe_template._properties["Ceiling Offset"]["value"] = str(raw_mm)
                        except (ValueError, TypeError):
                            pass
                        continue
                    self.current_pipe_template.set_property(k, v)
        if self.settings.contains("template/sprinkler"):
            spr_props = self.settings.value("template/sprinkler", {})
            if isinstance(spr_props, dict):
                for k, v in spr_props.items():
                    self.current_sprinkler_template.set_property(k, v)

    def _apply_persistent_unit_prefs(self):
        """Override the scale manager's display unit and precision with the
        user's persistent QSettings preference.  Called after project load
        so the file's stored units don't override the user's choice."""
        if self.settings.contains("display/unit"):
            unit_str = self.settings.value("display/unit", "mm", type=str)
            try:
                self.scene.scale_manager.display_unit = DisplayUnit(unit_str)
            except ValueError:
                pass
        if self.settings.contains("display/precision"):
            self.scene.scale_manager.precision = self.settings.value(
                "display/precision", 3, type=int)

    def showEvent(self, event):
        """Fit the view after the window is fully shown for the first time."""
        super().showEvent(event)
        if not self._initial_fit_done:
            self._initial_fit_done = True
            # Open Plan: Level 1 as the default view
            from firepro3d.constants import DEFAULT_LEVEL
            self._activate_plan_view(DEFAULT_LEVEL)

    def _activate_paper_sheet(self, name: str):
        """Open or switch to a paper space tab matching *name*.

        If the tab already exists, switch to it.  Otherwise create a new one.
        """
        for i in range(self.central_tabs.count()):
            if self.central_tabs.tabText(i) == name:
                self.central_tabs.setCurrentIndex(i)
                return
        # Create a new paper space tab
        from firepro3d.paper_space import PaperSpaceWidget
        ps = PaperSpaceWidget(self.scene)
        idx = self.central_tabs.addTab(ps, name)
        self.central_tabs.setCurrentIndex(idx)

    def _activate_plan_view(self, level_name: str):
        """Open or switch to a Plan: <level> tab.

        If a tab named 'Plan: <level>' already exists, switch to it.
        Otherwise create a new one.  All plan tabs share the same
        Model_Space scene — switching between them changes the active level.
        """
        tab_name = f"Plan: {level_name}"

        # Ensure a PlanView object exists for this tab
        self.plan_view_mgr.create(level_name, self.level_mgr)

        # Check if tab already exists
        for i in range(self.central_tabs.count()):
            if self.central_tabs.tabText(i) == tab_name:
                self.central_tabs.setCurrentIndex(i)
                self._apply_plan_level(level_name)
                return

        # Create a new plan tab sharing the same scene + view
        from firepro3d.model_view import Model_View
        plan_view = Model_View(self.scene)
        plan_view.setObjectName(f"plan_view_{level_name}")
        plan_view.plan_view_name = tab_name  # link widget to PlanView
        idx = self.central_tabs.addTab(plan_view, tab_name)
        self.central_tabs.setCurrentIndex(idx)
        self._apply_plan_level(level_name)

        # Fit to screen after widget is shown
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(50, plan_view.fit_to_screen)

    def _on_tab_changed(self, index: int):
        """Auto-switch active level when switching to a Plan or Detail tab."""
        tab_text = self.central_tabs.tabText(index)
        if tab_text.startswith("Plan: "):
            level_name = tab_text[len("Plan: "):]
            self._apply_plan_level(level_name)
        elif tab_text.startswith("Detail: "):
            detail_name = tab_text[len("Detail: "):]
            self._apply_detail_level(detail_name)
        # Update property panel with view info when nothing is selected
        self.update_property_manager()

    def _on_tab_close_requested(self, index: int):
        """Close a view tab (Plan/Elevation). Core tabs are protected."""
        tab_text = self.central_tabs.tabText(index)
        # Never close the 3D Model tab
        if tab_text == "3D Model":
            return
        widget = self.central_tabs.widget(index)
        self.central_tabs.removeTab(index)
        # Clean up elevation manager tracking
        if tab_text.startswith("Elevation: "):
            direction = tab_text[len("Elevation: "):].lower()
            self.elevation_manager._views.pop(direction, None)
        if widget is not None:
            widget.deleteLater()

    def _apply_plan_level(self, level_name: str):
        """Set the active level and refresh visibility for a plan view."""
        self.scene.active_level = level_name
        pv = self.plan_view_mgr.get(f"Plan: {level_name}")
        if pv is not None:
            self.level_mgr.apply_to_scene(
                self.scene, level_name,
                view_height=pv.view_height, view_depth=pv.view_depth)
        else:
            self.level_mgr.apply_to_scene(self.scene, level_name)

    def _on_tab_context_menu(self, pos):
        """Show context menu when right-clicking a plan or detail tab header."""
        tab_bar = self.central_tabs.tabBar()
        index = tab_bar.tabAt(pos)
        if index < 0:
            return
        tab_text = self.central_tabs.tabText(index)

        if tab_text.startswith("Plan: "):
            self._tab_context_plan(tab_text, tab_bar, pos)
        elif tab_text.startswith("Detail: "):
            self._tab_context_detail(tab_text, tab_bar, pos)

    def _tab_context_plan(self, tab_text, tab_bar, pos):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        view_range_action = menu.addAction("View Range\u2026")
        action = menu.exec(tab_bar.mapToGlobal(pos))
        if action == view_range_action:
            level_name = tab_text[len("Plan: "):]
            pv = self.plan_view_mgr.get(tab_text)
            if pv is None:
                pv = self.plan_view_mgr.create(level_name, self.level_mgr)
            from firepro3d.view_range_dialog import ViewRangeDialog
            dlg = ViewRangeDialog(
                pv, self.level_mgr, self.plan_view_mgr,
                self.scene.scale_manager, parent=self)
            if dlg.exec() == dlg.DialogCode.Accepted:
                vh, vd = dlg.get_values()
                pv.view_height = vh
                pv.view_depth = vd
                current_text = self.central_tabs.tabText(
                    self.central_tabs.currentIndex())
                if current_text == tab_text:
                    self._apply_plan_level(level_name)

    def _tab_context_detail(self, tab_text, tab_bar, pos):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        view_range_action = menu.addAction("View Range\u2026")
        action = menu.exec(tab_bar.mapToGlobal(pos))
        if action == view_range_action:
            detail_name = tab_text[len("Detail: "):]
            marker = self.detail_manager.get_marker(detail_name)
            if marker is None:
                return
            # Create a temporary PlanView to drive the dialog
            from firepro3d.level_manager import PlanView
            pv = PlanView(
                name=tab_text,
                level_name=marker.level_name,
                view_height=marker.view_height or 0.0,
                view_depth=marker.view_depth or 0.0,
            )
            from firepro3d.view_range_dialog import ViewRangeDialog
            dlg = ViewRangeDialog(
                pv, self.level_mgr, self.plan_view_mgr,
                self.scene.scale_manager, parent=self)
            if dlg.exec() == dlg.DialogCode.Accepted:
                vh, vd = dlg.get_values()
                marker.view_height = vh
                marker.view_depth = vd
                # Refresh masking if this detail tab is active
                current_text = self.central_tabs.tabText(
                    self.central_tabs.currentIndex())
                if current_text == tab_text:
                    self._apply_detail_level(detail_name)

    def _get_active_plan_view(self):
        """Return the currently visible plan view, falling back to self.view."""
        w = self.central_tabs.currentWidget()
        from firepro3d.model_view import Model_View
        if isinstance(w, Model_View):
            return w
        # Find any plan tab
        for i in range(self.central_tabs.count()):
            if self.central_tabs.tabText(i).startswith("Plan: "):
                return self.central_tabs.widget(i)
        return self.view

    def _fit_active_plan_view(self):
        """Fit the active plan view to screen."""
        v = self._get_active_plan_view()
        v.fit_to_screen()

    def _setup_tab_close_icon(self):
        """Create a white close-button icon for tabs (dark theme)."""
        from PyQt6.QtGui import QPixmap, QPainter, QPen, QIcon
        from PyQt6.QtWidgets import QStyle, QStyleFactory
        import os, tempfile

        size = 16
        pix = QPixmap(size, size)
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#ffffff"), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        m = 4  # margin
        p.drawLine(m, m, size - m, size - m)
        p.drawLine(size - m, m, m, size - m)
        p.end()

        icon_path = os.path.join(tempfile.gettempdir(), "fp3d_tab_close.png")
        pix.save(icon_path)
        # Apply via stylesheet (path needs forward slashes for QSS on Windows)
        css_path = icon_path.replace("\\", "/")
        self.central_tabs.tabBar().setStyleSheet(
            f'QTabBar::close-button {{ image: url("{css_path}"); }}'
        )

    def _activate_elevation(self, direction: str):
        """Open or switch to an elevation view tab from the project browser."""
        already_open = direction.lower() in self.elevation_manager.open_directions
        view = self.elevation_manager.open_elevation(direction)
        if not already_open:
            # Wire signals only once on first open
            scene = view.scene()
            if scene is not None:
                scene.entitySelected.connect(self.prop_manager.show_properties)
            view.cursorMoved.connect(self.coord_label.setText)

    def _create_elevation_markers(self):
        """Create N/S/E/W elevation markers in the 2D plan view."""
        from firepro3d.view_marker import ViewMarkerManager
        from firepro3d.display_manager import apply_category_defaults
        self._view_marker_mgr = ViewMarkerManager(self.scene)
        self._view_marker_mgr.create_elevation_markers()
        # Apply user's saved display defaults to the new markers
        for marker in self._view_marker_mgr._markers.values():
            apply_category_defaults(marker)

    def _on_open_view_requested(self, view_type: str, name: str):
        """Handle double-click on a view marker — open the corresponding view."""
        if view_type == "elevation":
            self._activate_elevation(name)
        elif view_type == "detail":
            self._activate_detail_view(name)

    def _activate_detail_view(self, name: str):
        """Open or switch to a detail view tab."""
        self.detail_manager.open_detail(name)
        self._apply_detail_level(name)

    def _apply_detail_level(self, detail_name: str):
        """Apply view range from a detail marker to the scene."""
        marker = self.detail_manager.get_marker(detail_name)
        if marker is None:
            return
        level_name = marker.level_name
        self.scene.active_level = level_name
        vh = marker.view_height
        vd = marker.view_depth
        if vh is not None and vd is not None:
            self.level_mgr.apply_to_scene(
                self.scene, level_name, view_height=vh, view_depth=vd)
        else:
            # Inherit from the plan view for this level
            pv = self.plan_view_mgr.get(f"Plan: {level_name}")
            if pv is not None:
                self.level_mgr.apply_to_scene(
                    self.scene, level_name,
                    view_height=pv.view_height, view_depth=pv.view_depth)
            else:
                self.level_mgr.apply_to_scene(self.scene, level_name)

    def _delete_detail_view(self, name: str):
        """Delete a detail view (marker + tab)."""
        self.detail_manager.delete_detail(name)
        self._refresh_detail_browser()

    def _refresh_detail_browser(self):
        """Update the project browser's Details section."""
        self.project_browser.refresh_details(self.detail_manager.detail_names)

    # ─────────────────────────────────────────────────────────────────────────
    # Dialog signal handlers (dialogs moved out of Model_Space)
    # ─────────────────────────────────────────────────────────────────────────

    def _on_numeric_input_requested(self, mode: str, title: str, label: str,
                                     default: float, min_val: float, max_val: float):
        val, ok = QInputDialog.getDouble(self, title, label, default, min_val, max_val, 3)
        self.scene.complete_numeric_input(mode, val, ok)

    def _on_warning_issued(self, title: str, message: str):
        QMessageBox.warning(self, title, message)

    def _on_confirm_requested(self, action_id: str, title: str, message: str):
        if action_id.startswith("elev_mismatch"):
            box = QMessageBox(self)
            box.setWindowTitle(title)
            box.setText(message)
            box.setWindowFlags(
                Qt.WindowType.Dialog
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.CustomizeWindowHint)
            btn_riser = box.addButton(
                "Create Riser", QMessageBox.ButtonRole.YesRole)
            btn_match = box.addButton(
                "Use Existing Elevation", QMessageBox.ButtonRole.NoRole)
            btn_template = box.addButton(
                "Use Specified Elevation", QMessageBox.ButtonRole.AcceptRole)
            box.setDefaultButton(btn_riser)
            box.exec()
            clicked = box.clickedButton()
            if clicked is btn_riser:
                result = "riser"
            elif clicked is btn_template:
                result = "template"
            else:
                result = "match"
            self.scene.complete_confirmation(action_id, result)
        else:
            reply = QMessageBox.question(
                self, title, message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes)
            result = "accepted" if reply == QMessageBox.StandardButton.Yes else "rejected"
            self.scene.complete_confirmation(action_id, result)

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
        from firepro3d.assets import asset_path
        _I = lambda name: QIcon(asset_path("Ribbon", name))

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

        def _btn(group, label, icon, callback, *, tip=None, large=True, checkable=False):
            """Create a button with optional tooltip. Returns the button."""
            if large:
                b = group.add_large_button(label, icon, callback, checkable=checkable)
            else:
                b = group.add_small_button(label, icon, callback, checkable=checkable)
            if tip:
                b.setToolTip(tip)
            return b

        self._init_manage_tab(_I, _btn)
        self._init_draw_tab(_I, _btn, _mode_btn)
        self._init_build_tab(_I, _btn, _mode_btn)
        self._init_modify_tab(_I, _btn, _mode_btn)
        self._init_analyze_tab(_I, _btn)
        self._init_draft_tab(_I, _btn)

        # Auto-switch to Modify tab when items are selected
        self.scene.selectionChanged.connect(self._on_selection_changed_modify)

    # ── Per-tab ribbon helpers ───────────────────────────────────────────────

    def _init_manage_tab(self, _I, _btn):
        """Build Tab 1: Manage — file I/O, import, settings, grid, undo/redo, panels."""
        manage_page = self.ribbon.add_page("Manage")

        # --- File ---
        g_file = manage_page.add_group("File")
        _btn(g_file, "New",     _I("placeholder_icon.svg"), self.new_file, tip="Start a new project [Ctrl+N]")
        _btn(g_file, "Open",    _I("load_icon.svg"),        self.open_file, tip="Open a saved project [Ctrl+O]")
        _btn(g_file, "Save",    _I("save_icon.svg"),        self.save_file, tip="Save the current project [Ctrl+S]")
        _btn(g_file, "Save As", _I("saveas_icon.svg"),      self.save_file_as, tip="Save as a new file")
        self._recent_menu = QMenu(self)
        _btn = g_file.add_small_menu_button("Recent", _I("load_icon.svg"), self._recent_menu)
        _btn.setToolTip("Recently opened files")
        self._rebuild_recent_menu()

        # --- Import ---
        g_imp = manage_page.add_group("Import")
        _btn = g_imp.add_large_button(
            "Import\nUnderlay", _I("import_icon.svg"), self.open_import_dialog)
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
        _btn = g_set.add_large_button(
            "Display\nManager", _I("placeholder_icon.svg"),
            self._open_display_manager)
        _btn.setToolTip("Configure visibility, colour, scale and opacity for model items")
        _btn = g_set.add_small_menu_button(
            "Units", _I("info_icon.svg"), self._build_units_menu())
        _btn.setToolTip("Set display units (Imperial/Metric)")
        _btn = g_set.add_small_menu_button(
            "Precision", _I("info_icon.svg"), self._build_precision_menu())
        _btn.setToolTip("Set decimal precision")
        _btn = g_set.add_small_button(
            "Snaps", _I("info_icon.svg"), self._open_snap_settings)
        _btn.setToolTip("Configure grid spacing and angle snap")

        # --- Snap (moved from Draw tab) ---
        g_snap = manage_page.add_group("Snap")
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
        _btn = g_snap.add_small_button(
            "Snap\nSettings",
            _I("placeholder_icon.svg"),
            self._open_snap_tolerance_dialog)
        _btn.setToolTip("Adjust snap tolerance and type settings")

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

        # --- Project Tools ---
        g_proj = manage_page.add_group("Project Tools")
        _btn = g_proj.add_large_button(
            "Gridlines", _I("gridline_icon.svg"),
            self._place_grid_lines)
        _btn.setToolTip("Open gridline placement dialog")
        _btn = g_proj.add_large_button(
            "Levels", _I("placeholder_icon.svg"),
            self._open_level_dialog)
        _btn.setToolTip("Open Level Manager dialog")

        # --- View ---
        g_view = manage_page.add_group("View")
        _btn = g_view.add_large_button(
            "Fit to\nScreen", _I("placeholder_icon.svg"),
            self._fit_active_plan_view)
        _btn.setToolTip("Zoom to fit all content [F]")

        # --- Panels (dock toggles) ---
        g_pan = manage_page.add_group("Panels")
        prop_btn = g_pan.add_small_button(
            "Properties", _I("info_icon.svg"),
            None, checkable=True)
        prop_btn.setToolTip("Show/hide Properties dock")
        prop_btn.setChecked(True)  # visible by default
        prop_btn.toggled.connect(self.prop_dock.setVisible)
        self.prop_dock.visibilityChanged.connect(prop_btn.setChecked)

        browser_btn = g_pan.add_small_button(
            "Browser",
            _I("placeholder_icon.svg"),
            None, checkable=True)
        browser_btn.setToolTip("Toggle Browser panel")
        browser_btn.toggled.connect(self.browser_dock.setVisible)
        self.browser_dock.visibilityChanged.connect(browser_btn.setChecked)

        report_btn = g_pan.add_small_button(
            "Hydraulic\nReport", _I("report_icon.svg"), None, checkable=True)
        report_btn.setToolTip("Toggle Hydraulic Report panel")
        report_btn.toggled.connect(
            lambda on: self.hydro_dock.show() if on else self.hydro_dock.hide())
        self.hydro_dock.visibilityChanged.connect(report_btn.setChecked)

        rad_report_btn = g_pan.add_small_button(
            "Radiation\nReport", _I("report_icon.svg"), None, checkable=True)
        rad_report_btn.setToolTip("Toggle Thermal Radiation Report panel")
        rad_report_btn.toggled.connect(
            lambda on: self.radiation_dock.show() if on else self.radiation_dock.hide())
        self.radiation_dock.visibilityChanged.connect(rad_report_btn.setChecked)

    def _init_draw_tab(self, _I, _btn, _mode_btn):
        """Build Tab 2: Draw — geometry tools, style, snap, annotations."""
        # ── Tab 2: Draw ──────────────────────────────────────────────────────
        draw_page = self.ribbon.add_page("Draw")

        # --- Geometry ---
        g_geom = draw_page.add_group("Geometry")
        # Line split-menu: main click → draw_line, dropdown → Line / Construction Line
        _line_btn = g_geom.add_large_button(
            "Line", _I("line_icon.svg"),
            lambda: self.scene.set_mode("draw_line"), checkable=True)
        _line_btn.setToolTip("Draw a line or construction line")
        _line_menu = QMenu(_line_btn)
        _line_menu.addAction("Line").triggered.connect(
            lambda: self.scene.set_mode("draw_line"))
        _line_menu.addAction("Construction Line").triggered.connect(
            lambda: self.scene.set_mode("construction_line"))
        _line_btn.setMenu(_line_menu)
        _line_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._mode_buttons["draw_line"] = _line_btn
        self._mode_buttons["construction_line"] = _line_btn
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
        _rect_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._mode_buttons["draw_rectangle"] = _rect_btn
        _mode_btn(g_geom, "Circle", _I("circle_icon.svg"), "draw_circle").setToolTip("Draw a circle")
        _mode_btn(g_geom, "Polyline", _I("polyline_icon.svg"), "polyline").setToolTip("Draw a polyline (multi-segment)")
        _mode_btn(g_geom, "Arc", _I("arc_icon.svg"), "draw_arc").setToolTip("Draw an arc (3-click)")
        self._single_place_btn = g_geom.add_small_button(
            "Single\nPlace", _I("placeholder_icon.svg"), None, checkable=True)
        self._single_place_btn.setToolTip("Return to Select mode after placing one item")
        self._single_place_btn.setChecked(False)
        self._single_place_btn.toggled.connect(
            lambda on: setattr(self.scene, 'single_place_mode', on))

        # --- Blocks ---
        g_blocks = draw_page.add_group("Blocks")
        g_blocks.add_small_button(
            "Insert\nBlock", _I("placeholder_icon.svg"), self._insert_block)
        g_blocks.add_small_button(
            "Create\nBlock", _I("placeholder_icon.svg"), self._create_block)

        # --- Annotations ---
        g_ann = draw_page.add_group("Annotations")
        _mode_btn(g_ann, "Dimension", _I("dimension_icon.svg"), "dimension").setToolTip("Place a dimension annotation")
        _mode_btn(g_ann, "Text", _I("text_icon.svg"), "text").setToolTip("Place a text note")
        _mode_btn(g_ann, "Hatch", _I("placeholder_icon.svg"), "hatch").setToolTip(
            "Add hatching to a closed object")

    def _init_build_tab(self, _I, _btn, _mode_btn):
        """Build Tab 3: Build — pipe/sprinkler placement, system, library."""
        # ── Tab 3: Build ─────────────────────────────────────────────────────
        build_page = self.ribbon.add_page("Build")

        # --- 3D Modeling ---
        g_3d = build_page.add_group("3D Modeling")
        _wall_btn = g_3d.add_large_button(
            "Wall", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("wall_rect"),
            checkable=True)
        _wall_btn.setToolTip("Draw a wall segment")
        _wall_menu = QMenu(_wall_btn)
        _wall_rect_act = _wall_menu.addAction("Wall (Rectangle)")
        _wall_poly_act = _wall_menu.addAction("Wall (Polyline)")
        _wall_rect_act.triggered.connect(lambda: self.scene.set_mode("wall_rect"))
        _wall_poly_act.triggered.connect(lambda: self.scene.set_mode("wall"))
        _wall_btn.setMenu(_wall_menu)
        _wall_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._mode_buttons["wall"] = _wall_btn
        self._mode_buttons["wall_rect"] = _wall_btn
        _floor_btn = g_3d.add_large_button(
            "Floor", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("floor_rect"),
            checkable=True)
        _floor_btn.setToolTip("Draw a floor slab boundary")
        _floor_menu = QMenu(_floor_btn)
        _floor_rect_act = _floor_menu.addAction("Floor (Rectangle)")
        _floor_poly_act = _floor_menu.addAction("Floor (Polygon)")
        _floor_rect_act.triggered.connect(lambda: self.scene.set_mode("floor_rect"))
        _floor_poly_act.triggered.connect(lambda: self.scene.set_mode("floor"))
        _floor_btn.setMenu(_floor_menu)
        _floor_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._mode_buttons["floor"] = _floor_btn
        self._mode_buttons["floor_rect"] = _floor_btn
        _roof_btn = g_3d.add_large_button(
            "Roof", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("roof_rect"),
            checkable=True)
        _roof_btn.setToolTip("Draw a roof boundary")
        _roof_menu = QMenu(_roof_btn)
        _roof_rect_act = _roof_menu.addAction("Roof (Rectangle)")
        _roof_poly_act = _roof_menu.addAction("Roof (Polygon)")
        _roof_rect_act.triggered.connect(lambda: self.scene.set_mode("roof_rect"))
        _roof_poly_act.triggered.connect(lambda: self.scene.set_mode("roof"))
        _roof_btn.setMenu(_roof_menu)
        _roof_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._mode_buttons["roof"] = _roof_btn
        self._mode_buttons["roof_rect"] = _roof_btn
        _room_btn = g_3d.add_large_button(
            "Room", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("room"),
            checkable=True)
        _room_btn.setToolTip("Define a room boundary")
        _room_menu = QMenu(_room_btn)
        _room_auto_act = _room_menu.addAction("Room (Auto-detect)")
        _room_manual_act = _room_menu.addAction("Room (Manual)")
        _room_auto_act.triggered.connect(lambda: self.scene.set_mode("room"))
        _room_manual_act.triggered.connect(lambda: self.scene.set_mode("room_manual"))
        _room_btn.setMenu(_room_menu)
        _room_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._mode_buttons["room"] = _room_btn
        self._mode_buttons["room_manual"] = _room_btn
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
        _detail_btn = g_3d.add_small_button(
            "Detail", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("detail"),
            checkable=True)
        _detail_btn.setToolTip("Draw a detail view crop boundary")
        self._mode_buttons["detail"] = _detail_btn
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
            "Coverage Overlay", _I("placeholder_icon.svg"),
            self.toggle_coverage_overlay, checkable=True)
        self._coverage_btn.setToolTip("Show/hide sprinkler coverage circles")
        g_sys.add_small_button(
            "Display", _I("placeholder_icon.svg"),
            self._open_display_manager)
        g_sys.add_small_button(
            "Auto-Populate", _I("placeholder_icon.svg"),
            self._auto_populate_sprinklers)

        # --- Library ---
        g_lib = build_page.add_group("Library")
        _btn = g_lib.add_large_button(
            "Sprinkler\nManager", _I("sprinkler_manager_icon.svg"),
            self.open_sprinkler_manager)
        _btn.setToolTip("Open sprinkler database manager")

    def _init_modify_tab(self, _I, _btn, _mode_btn):
        """Build Tab 4: Modify — edit/transform/scale tools (auto-switches on selection)."""
        # ── Tab 4: Modify (always visible, auto-switches on selection) ────────
        modify_page = self.ribbon.add_page("Modify")
        self._modify_tab_idx = self.ribbon._tab_bar.count() - 1

        # --- Edit ---
        g_medit = modify_page.add_group("Edit")
        _btn = g_medit.add_large_button("Undo", _I("undo_icon.svg"), self.scene.undo)
        _btn.setToolTip("Undo last action [Ctrl+Z]")
        _btn = g_medit.add_large_button("Redo", _I("redo_icon.svg"), self.scene.redo)
        _btn.setToolTip("Redo last undone action [Ctrl+Y / Ctrl+Shift+Z]")
        self._btn_delete = g_medit.add_large_button(
            "Delete", _I("delete_icon.svg"),
            lambda: self.scene.delete_selected_items())
        self._btn_delete.setToolTip("Delete selected items [Del]")
        self._btn_cut = g_medit.add_small_button(
            "Cut", _I("cut_icon.svg"),
            lambda: (self.scene.copy_selected_items(), self.scene.delete_selected_items()))
        self._btn_cut.setToolTip("Cut selected items [Ctrl+X]")
        self._btn_copy = g_medit.add_small_button(
            "Copy", _I("copy_icon.svg"),
            lambda: self.scene.copy_selected_items())
        self._btn_copy.setToolTip("Copy selected items [Ctrl+C]")
        self._btn_paste = g_medit.add_small_button(
            "Paste", _I("paste_icon.svg"),
            lambda: self.scene.paste_items())
        self._btn_paste.setToolTip("Paste items [Ctrl+V]")

        # --- Transform ---
        g_xform = modify_page.add_group("Transform")
        self._btn_move = g_xform.add_small_button(
            "Move", _I("move_icon.svg"),
            lambda: self._require_selection(lambda: self.scene.set_mode("move")),
            checkable=True)
        self._btn_move.setToolTip("Move selected items [Ctrl+M]")
        self._mode_buttons["move"] = self._btn_move
        self._btn_duplicate = g_xform.add_small_button(
            "Duplicate", _I("duplicate_icon.svg"),
            lambda: self._require_selection(lambda: self.scene.duplicate_selected()))
        self._btn_duplicate.setToolTip("Duplicate selected items [Ctrl+D]")
        self._btn_array = g_xform.add_small_button(
            "Array", _I("array_icon.svg"),
            lambda: self._require_selection(self._open_array_dialog))
        self._btn_array.setToolTip("Create linear/radial array of selected items")
        self._btn_rotate = g_xform.add_small_button(
            "Rotate", _I("rotate_icon.svg"),
            lambda: self._require_selection(lambda: self.scene.set_mode("rotate")),
            checkable=True)
        self._btn_rotate.setToolTip("Rotate selected items interactively (pick pivot, then angle)")
        self._mode_buttons["rotate"] = self._btn_rotate
        self._btn_scale = g_xform.add_small_button(
            "Scale", _I("scale_icon.svg"),
            lambda: self._require_selection(lambda: self.scene.set_mode("scale")),
            checkable=True)
        self._btn_scale.setToolTip("Scale selected items interactively (pick base, Tab for factor)")
        self._mode_buttons["scale"] = self._btn_scale
        _btn = g_xform.add_small_button(
            "Mirror", _I("mirror_icon.svg"),
            lambda: self._require_selection(lambda: self.scene.set_mode("mirror")),
            checkable=True)
        _btn.setToolTip("Mirror selected items across an axis (2 clicks)")
        self._mode_buttons["mirror"] = _btn
        _btn = g_xform.add_small_button(
            "Offset", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("offset"),
            checkable=True)
        _btn.setToolTip("Offset geometry (Tab for exact distance)")
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

        # Selection-dependent button enable/disable
        self._selection_buttons = [
            self._btn_delete, self._btn_cut, self._btn_copy,
            self._btn_move, self._btn_duplicate, self._btn_array,
            self._btn_rotate, self._btn_scale,
        ]
        for btn in self._selection_buttons:
            btn.setEnabled(False)
        self._btn_paste.setEnabled(False)

    def _init_analyze_tab(self, _I, _btn):
        """Build Tab 5: Analyze — hydraulics, export."""
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

        # --- Thermal Radiation ---
        g_rad = analyze_page.add_group("Thermal Radiation")
        _rad_btn = g_rad.add_large_button(
            "Run\nRadiation", _I("placeholder_icon.svg"),
            lambda: self._radiation_step1_start(), shortcut="F6",
            checkable=True)
        _rad_btn.setToolTip("Run thermal radiation analysis [F6]")
        self._mode_buttons["radiation_emitter"] = _rad_btn
        self._mode_buttons["radiation_receiver"] = _rad_btn
        _btn = g_rad.add_large_button(
            "Clear\nRadiation", _I("clear_icon.svg"),
            self._clear_radiation)
        _btn.setToolTip("Clear radiation overlay and results")

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

    def _init_draft_tab(self, _I, _btn):
        """Build Tab 6: Draft — workspace switching, page setup."""
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
            lambda: self._activate_paper_sheet("Layout 1"))
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
        """Open a tabular dialog to view/edit project metadata with custom rows."""
        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        info = getattr(self.scene, "_project_info", {})
        dlg = QDialog(self)
        dlg.setWindowTitle("Project Information")
        dlg.setMinimumSize(480, 420)
        layout = QVBoxLayout(dlg)

        _STANDARD_FIELDS = [
            ("Project Name",      "name"),
            ("Project Number",    "number"),
            ("Address",           "address"),
            ("City",              "city"),
            ("State / Province",  "state"),
            ("Client",            "client"),
            ("Designer",          "designer"),
            ("Description",       "description"),
        ]
        custom = info.get("custom", [])  # [{"key": ..., "value": ...}, ...]

        table = QTableWidget(len(_STANDARD_FIELDS) + len(custom), 2)
        table.setHorizontalHeaderLabels(["Property", "Value"])
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)

        # Populate standard fields (property name is read-only)
        for row, (label, key) in enumerate(_STANDARD_FIELDS):
            prop_item = QTableWidgetItem(label)
            prop_item.setFlags(prop_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 0, prop_item)
            table.setItem(row, 1, QTableWidgetItem(info.get(key, "")))

        # Populate custom fields (both columns editable)
        for i, entry in enumerate(custom):
            row = len(_STANDARD_FIELDS) + i
            table.setItem(row, 0, QTableWidgetItem(entry.get("key", "")))
            table.setItem(row, 1, QTableWidgetItem(entry.get("value", "")))

        layout.addWidget(table)

        # Add / Remove row buttons
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add Property")
        remove_btn = QPushButton("- Remove Property")

        def _add_row():
            r = table.rowCount()
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(""))
            table.setItem(r, 1, QTableWidgetItem(""))
            table.editItem(table.item(r, 0))

        def _remove_row():
            row = table.currentRow()
            if row >= len(_STANDARD_FIELDS):
                table.removeRow(row)

        add_btn.clicked.connect(_add_row)
        remove_btn.clicked.connect(_remove_row)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_info = {}
            for row, (_, key) in enumerate(_STANDARD_FIELDS):
                item = table.item(row, 1)
                new_info[key] = item.text() if item else ""
            new_custom = []
            for row in range(len(_STANDARD_FIELDS), table.rowCount()):
                k_item = table.item(row, 0)
                v_item = table.item(row, 1)
                k = k_item.text().strip() if k_item else ""
                v = v_item.text().strip() if v_item else ""
                if k:
                    new_custom.append({"key": k, "value": v})
            if new_custom:
                new_info["custom"] = new_custom
            self.scene._project_info = new_info

    # ── Snap Settings ────────────────────────────────────────────────────────

    def _open_snap_settings(self):
        """Open dialog to configure grid spacing and angle snap increment."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Snap Settings")
        dlg.setMinimumWidth(300)
        layout = QFormLayout(dlg)

        grid_spin = QDoubleSpinBox()
        grid_spin.setRange(1, 1000)
        grid_spin.setDecimals(1)
        grid_spin.setValue(self.view._grid_size)
        grid_spin.setSuffix(" mm")
        layout.addRow("Grid spacing:", grid_spin)

        angle_spin = QDoubleSpinBox()
        angle_spin.setRange(1, 90)
        angle_spin.setDecimals(1)
        angle_spin.setValue(self.scene._snap_angle_deg)
        angle_spin.setSuffix("°")
        layout.addRow("Angle snap:", angle_spin)

        # Angle presets
        preset_combo = QComboBox()
        preset_combo.addItems(["15", "30", "45", "90"])
        idx = preset_combo.findText(str(int(self.scene._snap_angle_deg)))
        if idx >= 0:
            preset_combo.setCurrentIndex(idx)
        preset_combo.currentTextChanged.connect(
            lambda t: angle_spin.setValue(float(t)))
        layout.addRow("Angle preset:", preset_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_grid = grid_spin.value()
            new_angle = angle_spin.value()
            self.view.set_grid(self.view._grid_visible, new_grid)
            self.scene._snap_angle_deg = new_angle
            # Persist
            self.settings.setValue("snap/grid_size", new_grid)
            self.settings.setValue("snap/angle_deg", new_angle)

    def _open_snap_tolerance_dialog(self):
        """Live-adjustable snap settings dialog with per-type toggles."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout,
                                      QDialogButtonBox, QGroupBox, QCheckBox)
        from firepro3d import snap_engine

        eng = self.scene._snap_engine

        dlg = QDialog(self)
        dlg.setWindowTitle("Snap Settings")
        dlg.setMinimumWidth(300)
        outer = QVBoxLayout(dlg)

        # ── Tolerance ────────────────────────────────────────────────
        tol_group = QGroupBox("Tolerance")
        tol_layout = QFormLayout(tol_group)
        tol_spin = QSpinBox()
        tol_spin.setRange(5, 1000)
        tol_spin.setSingleStep(5)
        tol_spin.setValue(snap_engine.SNAP_TOLERANCE_PX)
        tol_spin.setSuffix(" px")
        tol_spin.valueChanged.connect(
            lambda v: setattr(snap_engine, "SNAP_TOLERANCE_PX", v))
        tol_layout.addRow("Snap radius:", tol_spin)

        grip_spin = QSpinBox()
        grip_spin.setRange(100, 1000)
        grip_spin.setSingleStep(50)
        grip_spin.setValue(int(getattr(self.scene, "_grip_tolerance_px", 200)))
        grip_spin.setSuffix(" px")
        grip_spin.valueChanged.connect(
            lambda v: setattr(self.scene, "_grip_tolerance_px", v))
        tol_layout.addRow("Grip handle radius:", grip_spin)

        outer.addWidget(tol_group)

        # ── Snap types ───────────────────────────────────────────────
        types_group = QGroupBox("Snap Types")
        types_layout = QVBoxLayout(types_group)

        snap_types = [
            ("Endpoint",      "snap_endpoint"),
            ("Midpoint",      "snap_midpoint"),
            ("Intersection",  "snap_endpoint"),  # intersections use endpoint flag gate
            ("Center",        "snap_center"),
            ("Quadrant",      "snap_quadrant"),
            ("Nearest",       "snap_nearest"),
            ("Perpendicular", "snap_perpendicular"),
            ("Tangent",       "snap_tangent"),
        ]

        # Intersection has its own toggle — add a dedicated attribute
        if not hasattr(eng, "snap_intersection"):
            eng.snap_intersection = True

        checkboxes: list[tuple[QCheckBox, str]] = []
        for label, attr in snap_types:
            cb = QCheckBox(label)
            if label == "Intersection":
                cb.setChecked(getattr(eng, "snap_intersection", True))
            else:
                cb.setChecked(getattr(eng, attr, True))

            # Live update
            if label == "Intersection":
                cb.toggled.connect(
                    lambda v: setattr(eng, "snap_intersection", v))
            else:
                _attr = attr  # capture
                cb.toggled.connect(
                    lambda v, a=_attr: setattr(eng, a, v))

            types_layout.addWidget(cb)
            checkboxes.append((cb, attr if label != "Intersection" else "snap_intersection"))

        outer.addWidget(types_group)

        # ── Buttons ──────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        outer.addWidget(buttons)

        # Snapshot for cancel
        old_tol = snap_engine.SNAP_TOLERANCE_PX
        old_grip = getattr(self.scene, "_grip_tolerance_px", 200)
        old_flags = {attr: getattr(eng, attr) for _, attr in checkboxes}
        if not hasattr(eng, "snap_intersection"):
            old_flags["snap_intersection"] = True

        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Persist
            self.settings.setValue("snap/tolerance_px", snap_engine.SNAP_TOLERANCE_PX)
            self.settings.setValue("snap/grip_tolerance_px",
                                  getattr(self.scene, "_grip_tolerance_px", 200))
            for _, attr in checkboxes:
                self.settings.setValue(f"snap/{attr}", getattr(eng, attr))
        else:
            # Revert
            snap_engine.SNAP_TOLERANCE_PX = old_tol
            self.scene._grip_tolerance_px = old_grip
            for attr, val in old_flags.items():
                setattr(eng, attr, val)

    # ── Ribbon helper menu builders ───────────────────────────────────────────

    def _build_units_menu(self) -> QMenu:
        m = QMenu(self)
        m.addAction("Imperial (ft-in)",
                    lambda: self._set_display_unit(DisplayUnit.IMPERIAL))
        m.addAction("Metric (m)",
                    lambda: self._set_display_unit(DisplayUnit.METRIC_M))
        m.addAction("Metric (mm)",
                    lambda: self._set_display_unit(DisplayUnit.METRIC_MM))
        return m

    def _set_display_unit(self, unit):
        self.scene.set_display_unit(unit)
        self.settings.setValue("display/unit", unit.value)

    def _build_precision_menu(self) -> QMenu:
        m = QMenu(self)
        _frac_labels = {0: "Whole inch", 1: '1/2"', 2: '1/4"',
                        3: '1/8"', 4: '1/16"', 5: '1/32"'}
        for p in range(6):
            frac = _frac_labels.get(p, "")
            label = f"{p} — {frac}" if frac else f"{p} decimal places"
            m.addAction(label, lambda p=p: self._set_precision(p))
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

    # ── Block helpers ──────────────────────────────────────────────────────────

    def _insert_block(self):
        """Open a file dialog to select a saved block JSON, then place it."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from firepro3d.block_item import BlockItem
        from firepro3d.construction_geometry import (
            LineItem, RectangleItem, CircleItem, PolylineItem, ArcItem,
            ConstructionLine,
        )
        import json

        path, _ = QFileDialog.getOpenFileName(
            self, "Insert Block", "", "Block Files (*.json)")
        if not path:
            return
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "Insert Block", f"Failed to load block:\n{e}")
            return

        def _factory(d):
            t = d.get("type", "")
            if t == "draw_line":
                return LineItem.from_dict(d)
            elif t == "draw_rectangle":
                return RectangleItem.from_dict(d)
            elif t == "draw_circle":
                return CircleItem.from_dict(d)
            elif t == "polyline":
                return PolylineItem.from_dict(d)
            elif t == "arc":
                return ArcItem.from_dict(d)
            elif t == "construction_line":
                return ConstructionLine.from_dict(d)
            elif t == "block_item":
                return BlockItem.from_dict(d, _factory)
            return None

        blk = BlockItem.from_dict(data, _factory)
        self.scene.addItem(blk)
        blk.setSelected(True)
        self.scene.sceneModified.emit()

    def _create_block(self):
        """Group selected items into a BlockItem and optionally save to file."""
        from PyQt6.QtWidgets import QInputDialog, QFileDialog, QMessageBox
        from firepro3d.block_item import BlockItem
        import json

        selected = list(self.scene.selectedItems())
        if not selected:
            QMessageBox.information(self, "Create Block",
                                    "Select items first, then click Create Block.")
            return

        name, ok = QInputDialog.getText(self, "Create Block", "Block name:")
        if not ok or not name.strip():
            return
        name = name.strip()

        # Remove items from scene, wrap in BlockItem, re-add
        for item in selected:
            self.scene.removeItem(item)
        blk = BlockItem(selected, block_name=name)
        blk.user_layer = self.scene.active_user_layer
        self.scene.addItem(blk)
        blk.setSelected(True)

        # Offer to save to file
        reply = QMessageBox.question(
            self, "Save Block",
            f"Save block '{name}' to file for reuse?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Block", f"{name}.json", "Block Files (*.json)")
            if path:
                try:
                    with open(path, "w") as f:
                        json.dump(blk.to_dict(), f, indent=2)
                except Exception as e:
                    QMessageBox.warning(self, "Save Block",
                                        f"Failed to save block:\n{e}")

        self.scene.sceneModified.emit()

    # ── Level helpers ──────────────────────────────────────────────────────────

    def _on_active_level_changed(self, name: str):
        """Handle active level change from widget — opens the plan tab."""
        self._activate_plan_view(name)

    # ── Template workflow helpers ─────────────────────────────────────────────

    def _set_rect_mode(self, from_center: bool):
        """Switch rectangle drawing between corner and center mode."""
        self.scene._draw_rect_from_center = from_center
        self.scene.set_mode("draw_rectangle")

    def _on_mode_changed_template(self, mode: str):
        """Show pre-placement template properties when entering wall/floor/geometry mode."""
        if mode in ("wall", "wall_rect"):
            template = self.scene._get_wall_template()
            template._alignment = self.scene._wall_alignment
            self.prop_manager.show_properties(template)
        elif mode in ("floor", "floor_rect"):
            template = self.scene._get_floor_template()
            self.prop_manager.show_properties(template)
        elif mode in ("roof", "roof_rect"):
            template = self.scene._get_roof_template()
            self.prop_manager.show_properties(template)
        elif mode in ("draw_line", "construction_line", "draw_rectangle",
                       "draw_circle", "draw_arc", "polyline"):
            template = self.scene._get_geometry_template()
            self.prop_manager.show_properties(template)
        else:
            # Exiting a template mode — clear stale template properties
            self.prop_manager.show_properties(None)

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
        "offset":         "Click geometry to offset (Tab for exact distance)",
        "offset_side":    "Click the side to offset towards",
        "design_area":    "Click two corners to define design area",
        "room":           "Click inside a closed wall region to define a room",
        "water_supply":   "Click to place water supply",
        "paste":          "Click to place pasted items",
        "radiation_emitter":  "Select EMITTING surfaces (walls / roofs), then press Enter",
        "radiation_receiver": "Select RECEIVING surfaces, then press Enter",
    }

    def _update_osnap_indicator(self, enabled: bool) -> None:
        self.osnap_indicator.setOsnapOn(enabled)

    def _update_mode_label(self, mode: str):
        text = self._MODE_INSTRUCTIONS.get(mode, mode.replace("_", " ").title())
        self.mode_label.setText(text)
        # Update prominent mode name badge
        pretty = mode.replace("_", " ").title() if mode else "Select"
        self.mode_name_label.setText(pretty)

    def _sync_mode_buttons(self, mode: str):
        """Keep draw-mode buttons checked/unchecked to match the active mode."""
        active_btn = self._mode_buttons.get(mode)
        seen: set[int] = set()
        for m, btn in self._mode_buttons.items():
            btn_id = id(btn)
            if btn_id in seen:
                continue
            seen.add(btn_id)
            btn.blockSignals(True)
            btn.setChecked(btn is active_btn)
            btn.blockSignals(False)

    # ── Modify tab auto-switch (Sprint N) ──────────────────────────────────

    _DRAW_MODES = {"draw_line", "construction_line", "draw_rectangle",
                    "draw_circle", "draw_arc",
                    "polyline", "dimension", "text", "pipe", "sprinkler",
                    "water_supply", "design_area", "set_scale", "offset",
                    "offset_side", "wall", "wall_rect", "floor", "floor_rect",
                    "roof", "roof_rect", "room", "room_manual", "door", "window"}

    def _on_selection_changed_modify(self):
        """Auto-switch to Modify tab when items are selected (unless drawing)."""
        try:
            sel = self.scene.selectedItems()
        except RuntimeError:
            return  # scene already deleted during shutdown
        # Enable/disable selection-dependent buttons
        has_sel = bool(sel)
        for btn in self._selection_buttons:
            btn.setEnabled(has_sel)
        self._btn_paste.setEnabled(bool(self.scene.clipboard_data()))
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
        dlg = ArrayDialog(self, scale_manager=self.scene.scale_manager,
                          scene=self.scene,
                          selected_items=self.scene.selectedItems())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.scene.array_items(dlg.get_params())

    # ── Grid Lines ───────────────────────────────────────────────────────────

    def _place_grid_lines(self):
        """Open the Grid Lines dialog, populated with current gridlines."""
        dlg = GridLinesDialog(
            self,
            scale_manager=self.scene.scale_manager,
            existing_gridlines=list(self.scene._gridlines),
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Remove existing gridlines before placing the updated set
            self.scene.push_undo_state()
            for gl in list(self.scene._gridlines):
                if gl.scene() is self.scene:
                    self.scene.removeItem(gl)
            self.scene._gridlines.clear()
            self.scene.place_grid_lines(dlg.get_params())

    def _place_default_gridlines(self):
        """Place a default 3 V × 3 H grid for a new project."""
        sm = self.scene.scale_manager
        # Convert a sensible display-unit spacing to scene units
        if sm:
            spacing = sm.display_to_scene(DEFAULT_GRIDLINE_SPACING_IN)  # 288 in / 24 ft
            length  = sm.display_to_scene(DEFAULT_GRIDLINE_LENGTH_IN)   # 864 in / 72 ft
        else:
            spacing = DEFAULT_GRIDLINE_SPACING_IN
            length  = DEFAULT_GRIDLINE_LENGTH_IN

        specs: list[dict] = []
        # 3 vertical gridlines: labels 1, 2, 3
        for i, lbl in enumerate(["1", "2", "3"]):
            specs.append({
                "label": lbl,
                "offset": i * spacing,
                "length": length,
                "angle_deg": 90.0,
            })
        # 3 horizontal gridlines: labels A, B, C
        for i, lbl in enumerate(["A", "B", "C"]):
            specs.append({
                "label": lbl,
                "offset": i * spacing,
                "length": length,
                "angle_deg": 0.0,
            })
        self.scene.place_grid_lines({"gridlines": specs})

    def toggle_coverage_overlay(self, checked: bool):
        """Show/hide translucent sprinkler coverage circles."""
        self.scene.set_coverage_overlay(checked)

    def _open_display_manager(self):
        """Open the Display Manager dialog (replaces FSVisibilityDialog)."""
        from firepro3d.display_manager import DisplayManager
        dlg = DisplayManager(self.scene, parent=self)
        dlg.exec()  # live preview handles apply/revert internally

    def _open_level_dialog(self):
        """Open the Level Manager dialog."""
        from firepro3d.level_dialog import LevelDialog
        dlg = LevelDialog(self.level_mgr, scene=self.scene, parent=self)
        dlg.activeLevelChanged.connect(self._on_active_level_changed)
        dlg.levelsChanged.connect(
            lambda: self.level_mgr.apply_to_scene(self.scene))
        dlg.levelsChanged.connect(self.update_property_manager)
        dlg.levelsChanged.connect(self.project_browser.refresh_levels)
        dlg.levelsChanged.connect(self.elevation_manager.rebuild_all)
        dlg.duplicateLevel.connect(self.scene.duplicate_level_entities)
        dlg.exec()

    def open_sprinkler_manager(self):
        """Open the Sprinkler Manager database dialog."""
        from firepro3d.sprinkler_db import SprinklerManagerDialog, SprinklerDatabase
        if not hasattr(self, "_sprinkler_db"):
            self._sprinkler_db = SprinklerDatabase()
        dlg = SprinklerManagerDialog(db=self._sprinkler_db, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            record = dlg.selected_record()
            if record:
                self._apply_sprinkler_template_from_record(record)

    def _apply_sprinkler_template_from_record(self, record):
        """Apply a SprinklerRecord as the active sprinkler placement template."""
        from firepro3d.sprinkler import Sprinkler
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

    def _auto_populate_sprinklers(self):
        """Open auto-populate dialog for the currently selected room."""
        from firepro3d.room import Room
        selected = self.scene.selectedItems()
        rooms = [i for i in selected if isinstance(i, Room)]
        if not rooms:
            # No room selected — prompt user to pick one
            if not self.scene._rooms:
                QMessageBox.information(self, "No Rooms",
                                        "No rooms exist. Create a room first.")
                return
            if len(self.scene._rooms) == 1:
                # Only one room — use it automatically
                room = self.scene._rooms[0]
            else:
                # Multiple rooms — show a picker dialog
                from PyQt6.QtWidgets import QInputDialog
                names = [r.name or f"Room {i+1}" for i, r in enumerate(self.scene._rooms)]
                choice, ok = QInputDialog.getItem(
                    self, "Select Room",
                    "Choose a room to auto-populate with sprinklers:",
                    names, 0, False)
                if not ok:
                    return
                room = self.scene._rooms[names.index(choice)]
        else:
            room = rooms[0]
        self.scene._auto_populate_room_dialog(room)

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
                self._cleanup_autosave()
        else:
            self.save_file_as()

    def save_file_as(self):
        file, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "FirePro 3D Files (*.FPD)")
        if file:
            self._current_file = file
            if self.scene.save_to_file(file):
                self._modified = False
                self._update_title()
                self._add_recent_file(file)

    def open_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "FirePro 3D Files (*.FPD);;JSON Files (*.json)")
        if file:
            self._load_project(file)

    def _load_project(self, file: str):
        """Load a project file and update all UI state."""
        self._current_file = file
        self.scene.load_from_file(file)
        self.level_widget.populate()
        self.user_layer_widget.populate()
        pass  # level indicator removed
        self._modified = False
        self._update_title()
        self._add_recent_file(file)
        # Apply display settings: prefer project-embedded settings, fall back to QSettings
        project_ds = getattr(self.scene, '_loaded_display_settings', None)
        if project_ds:
            from firepro3d.display_manager import apply_project_display_settings
            apply_project_display_settings(self.scene, project_ds)
        else:
            from firepro3d.display_manager import apply_saved_display_settings
            apply_saved_display_settings(self.scene)
        # Rebuild elevation markers (cleared during scene load)
        self._create_elevation_markers()
        # Refresh detail views in project browser
        self._refresh_detail_browser()
        # Re-apply level visibility — activate the saved level's plan tab
        # so view_height/view_depth are applied from the loaded PlanView data.
        active = getattr(self.scene, "active_level", None)
        if active:
            self._activate_plan_view(active)
        # Override display unit and precision with user's persistent preference
        self._apply_persistent_unit_prefs()

    # ── Recent files ──────────────────────────────────────────────────────

    def _add_recent_file(self, path: str):
        path = os.path.normpath(path)
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:self._MAX_RECENT]
        self.settings.setValue("recent_files", self._recent_files)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        for path in self._recent_files:
            name = os.path.basename(path)
            self._recent_menu.addAction(name, lambda p=path: self._open_recent(p))
        if not self._recent_files:
            self._recent_menu.addAction("(No recent files)").setEnabled(False)

    def _open_recent(self, path: str):
        if not os.path.isfile(path):
            QMessageBox.warning(self, "File Not Found", f"Cannot find:\n{path}")
            if path in self._recent_files:
                self._recent_files.remove(path)
            self.settings.setValue("recent_files", self._recent_files)
            self._rebuild_recent_menu()
            return
        self._load_project(path)

    # ── Auto-save / crash recovery ────────────────────────────────────────

    @staticmethod
    def _autosave_path() -> str:
        return os.path.join(os.path.expanduser("~"), ".firepro3d",
                            "autosave", "recovery.FPD")

    def _autosave(self):
        if not self._modified:
            return
        path = self._autosave_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.scene.save_to_file(path)

    def _check_recovery(self):
        path = self._autosave_path()
        if not os.path.isfile(path):
            return
        reply = QMessageBox.question(
            self, "Recover Unsaved Work",
            "An auto-save recovery file was found.\n"
            "Would you like to restore it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.scene.load_from_file(path)
            self.level_widget.populate()
            self.user_layer_widget.populate()
            self._modified = True
            self._update_title()
            self._apply_persistent_unit_prefs()
        self._cleanup_autosave()

    def _cleanup_autosave(self):
        path = self._autosave_path()
        if os.path.isfile(path):
            os.remove(path)

    def _ask_save_changes(self, action="proceeding"):
        """Show unsaved-changes dialog. Returns True to proceed, False to cancel."""
        if not self._modified:
            return True
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            f"You have unsaved changes. Save before {action}?",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Save:
            self.save_file()
        elif reply == QMessageBox.StandardButton.Cancel:
            return False
        return True

    def new_file(self):
        """Clear the scene and start a fresh project."""
        if not self._ask_save_changes("starting a new project"):
            return
        self._current_file = None
        self.scene._clear_scene()
        self.level_widget.populate()
        self.user_layer_widget.populate()
        pass  # level indicator removed

        # Place a default 3 × 3 grid (3 vertical + 3 horizontal)
        self._place_default_gridlines()
        self._create_elevation_markers()

        # Apply saved display defaults to the new project
        from firepro3d.display_manager import apply_default_display_settings
        apply_default_display_settings(self.scene)
        self._apply_persistent_unit_prefs()

        # Reset undo stack so the template gridlines cannot be undone
        self.scene._undo_stack = []
        self.scene._undo_pos = -1
        self.scene.push_undo_state()

        self._modified = False
        self._update_title()
        QTimer.singleShot(100, self._fit_active_plan_view)

    def _update_title(self):
        name = os.path.basename(self._current_file) if self._current_file else "Untitled"
        star = " *" if self._modified else ""
        self.setWindowTitle(f"FirePro 3D \u2014 {name}{star}")

    def _on_scene_modified(self):
        self._modified = True
        self._update_title()
        # Debounce view rebuilds — 200ms so rapid edits don't stall the UI
        if not hasattr(self, "_view_refresh_timer"):
            self._view_refresh_timer = QTimer(self)
            self._view_refresh_timer.setSingleShot(True)
            self._view_refresh_timer.setInterval(200)
            self._view_refresh_timer.timeout.connect(self._refresh_all_views)
        if not self._view_refresh_timer.isActive():
            self._view_refresh_timer.start()

    def _refresh_all_views(self):
        """Rebuild all views to reflect property / geometry changes."""
        # Re-apply plan-level visibility & section-cut flags
        active = getattr(self.scene, "active_level", None)
        if active:
            self._apply_plan_level(active)
        # Elevation views
        if hasattr(self, "elevation_manager"):
            self.elevation_manager.rebuild_all()
        # 3D view
        if hasattr(self, "view_3d") and hasattr(self.view_3d, "rebuild"):
            self.view_3d.rebuild()

    def _on_escape(self):
        """Escape: cancel current chain in pipe mode, else reset mode."""
        # Pipe mode mid-chain: cancel the chain but stay in pipe mode
        if self.scene.mode == "pipe" and self.scene.node_start_pos is not None:
            # Remove the orphan start node if it was newly created and has no pipes
            if (self.scene._pipe_node_was_new
                    and self.scene.node_start_pos is not None
                    and not self.scene.node_start_pos.pipes):
                self.scene.remove_node(self.scene.node_start_pos)
            self.scene.node_start_pos = None
            self.scene._pipe_node_was_new = False
            self.scene.preview_pipe.hide()
            self.scene.preview_node.hide()
            self.scene.instructionChanged.emit("Pick start node")
            return
        self.scene.set_mode("select")
        self.scene.clearSelection()
        self.view_3d._on_escape()

    def _delete_if_not_editing(self):
        """Delete selected items unless a text item is being edited."""
        focus = self.scene.focusItem()
        if isinstance(focus, QGraphicsTextItem) and focus.hasFocus():
            return  # let the text editor handle Delete
        # Check 3D-only selection first
        if self.view_3d.get_3d_selected():
            self.view_3d.delete_selected()
            return
        self.scene.delete_selected_items()

    def open_import_dialog(self, file_path: str = ""):
        """Open the unified underlay import dialog (PDF + DXF)."""
        dialog = UnderlayImportDialog(
            self, file_path=file_path,
            user_layer_manager=self.user_layer_mgr,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            params = dialog.get_import_params()
            # PDF with no vectors → raster fallback
            if (not params.geom_list
                    and params.file_type == "pdf"
                    and not params.has_vectors):
                from firepro3d.underlay import Underlay
                record = Underlay(
                    type="pdf", path=params.file_path,
                    dpi=params.pdf_dpi, page=params.pdf_page,
                    rotation=params.rotation,
                    scale=params.scale,
                    user_layer=params.user_layer,
                )
                self.scene.import_pdf(
                    params.file_path,
                    dpi=params.pdf_dpi,
                    page=params.pdf_page,
                    _record=record,
                )
                return
            if not params.geom_list:
                return
            # Switch to model space (plan view)
            self._activate_plan_view(self.scene.active_level)
            if params.insert_at_origin:
                self.scene._place_import_params = params
                self.scene._commit_place_import(QPointF(0, 0))
            else:
                self.scene.begin_place_import(params)

    def _on_drop_import(self, path: str):
        """Handle a file dropped onto the canvas."""
        self.open_import_dialog(file_path=path)

    def refresh_underlays(self):
        self.scene.refresh_all_underlays()

    def _set_precision(self, places: int):
        self.scene.scale_manager.precision = places
        self.scene._refresh_all_labels()
        self.settings.setValue("display/precision", places)

    # ─────────────────────────────────────────────────────────────────────────
    # HYDRAULICS HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def run_hydraulics(self):
        """Run the hydraulic solver and populate the report dock."""
        design = self.scene.design_area_sprinklers or None
        if design:
            self.statusBar().showMessage(
                f"Running hydraulics with {len(design)} design-area sprinkler(s)...", 5000)
        else:
            self.statusBar().showMessage(
                "Running hydraulics on ALL sprinklers (no design area set)...", 5000)
        result = self.scene.run_hydraulics(design_sprinklers=design)
        self.hydro_report.populate(result, self.scene, self.scene.scale_manager)
        self.hydro_dock.show()
        self.hydro_dock.raise_()

    def clear_hydraulics(self):
        """Clear the hydraulic overlay and the report dock."""
        self.scene.clear_hydraulics()
        self.hydro_report.clear()

    # ─────────────────────────────────────────────────────────────────────────
    # THERMAL RADIATION HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _radiation_step1_start(self):
        """Begin two-step radiation surface selection."""
        self.scene.clearSelection()
        self.scene._radiation_selecting = True
        self._radiation_step = 1
        self._radiation_emitters = None
        self._radiation_receivers = None
        self.scene.set_mode("radiation_emitter")

    def _radiation_on_confirm(self):
        """Called when user presses Enter during radiation selection."""
        from firepro3d.wall import WallSegment
        from firepro3d.roof import RoofItem
        from firepro3d.floor_slab import FloorSlab

        surface_types = (WallSegment, RoofItem, FloorSlab)

        if self._radiation_step == 1:
            items = [i for i in self.scene.selectedItems()
                     if isinstance(i, surface_types)]
            if not items:
                self.statusBar().showMessage(
                    "No surfaces selected. Select at least one wall, roof, "
                    "or floor slab, then press Enter.")
                return
            self._radiation_emitters = items
            self.scene.clearSelection()
            self._radiation_step = 2
            self.scene.set_mode("radiation_receiver")

        elif self._radiation_step == 2:
            items = [i for i in self.scene.selectedItems()
                     if isinstance(i, surface_types)]
            if not items:
                self.statusBar().showMessage(
                    "No surfaces selected. Select at least one receiving "
                    "surface, then press Enter.")
                return
            self._radiation_receivers = items
            self._radiation_step = 0
            self.scene._radiation_selecting = False
            self.scene.set_mode(None)
            self._open_radiation_dialog()

    def _open_radiation_dialog(self):
        from firepro3d.thermal_radiation_dialog import ThermalRadiationDialog
        dlg = ThermalRadiationDialog(
            self,
            scale_manager=self.scene.scale_manager,
            num_emitters=len(self._radiation_emitters),
            num_receivers=len(self._radiation_receivers),
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._run_radiation(dlg.get_params())
        else:
            self.statusBar().showMessage("Radiation analysis cancelled.", 3000)

    def _run_radiation(self, params):
        from firepro3d.thermal_radiation_solver import (
            StandardSurfaceRadiationModel, extract_surface_mesh,
        )
        lm = self.scene._level_manager
        sm = self.scene.scale_manager

        # Show progress dialog
        progress = QProgressDialog(
            "Running thermal radiation analysis...", None, 0, 0, self)
        progress.setWindowTitle("Thermal Radiation")
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            progress.setLabelText("Extracting surface meshes...")
            QApplication.processEvents()

            emitter_meshes = [
                (e, extract_surface_mesh(e, lm, sm))
                for e in self._radiation_emitters
            ]
            receiver_meshes = [
                (e, extract_surface_mesh(e, lm, sm))
                for e in self._radiation_receivers
            ]

            # Collect blocking geometry from OTHER surfaces not in analysis
            from firepro3d.wall import WallSegment
            from firepro3d.roof import RoofItem
            from firepro3d.floor_slab import FloorSlab
            selected_ids = set(
                id(e) for e in self._radiation_emitters + self._radiation_receivers
            )
            blocking_meshes = []
            all_surfaces = (
                list(getattr(self.scene, '_walls', []))
                + list(getattr(self.scene, '_roofs', []))
                + list(getattr(self.scene, '_floor_slabs', []))
            )
            for surf in all_surfaces:
                if id(surf) not in selected_ids:
                    mesh = extract_surface_mesh(surf, lm, sm)
                    if mesh is not None:
                        blocking_meshes.append(mesh)
            params["blocking_meshes"] = blocking_meshes

            progress.setLabelText("Computing radiation view factors...")
            QApplication.processEvents()

            model = StandardSurfaceRadiationModel()
            result = model.compute(emitter_meshes, receiver_meshes, params)

            progress.setLabelText("Generating results...")
            QApplication.processEvents()

            self.radiation_report.populate(result, self.scene, sm)
            self.radiation_dock.show()
            self.radiation_dock.raise_()

            # Show heatmap in 3D view
            self.view_3d.show_radiation_heatmap(result)

            if result.passed:
                self.statusBar().showMessage(
                    f"Radiation PASS \u2014 Max {result.max_radiation:.2f} kW/m\u00b2",
                    10000)
            else:
                self.statusBar().showMessage(
                    f"Radiation FAIL \u2014 Max {result.max_radiation:.2f} kW/m\u00b2 "
                    f"exceeds {result.threshold:.1f} kW/m\u00b2", 10000)
        except Exception as exc:
            self.statusBar().showMessage(
                f"Radiation analysis error: {exc}", 10000)
            import traceback
            traceback.print_exc()
        finally:
            progress.close()

    def _radiation_on_cancel(self):
        """Called when user presses Escape during radiation selection."""
        self._radiation_step = 0
        self._radiation_emitters = None
        self._radiation_receivers = None
        self.scene._radiation_selecting = False
        self.scene.set_mode(None)
        self.statusBar().showMessage("Radiation analysis cancelled.", 3000)

    def _clear_radiation(self):
        """Clear the radiation overlay and report dock."""
        self.radiation_report.clear()
        self.view_3d.clear_radiation_heatmap()
        self._radiation_step = 0
        self._radiation_emitters = None
        self._radiation_receivers = None
        self.scene._radiation_selecting = False
        self.statusBar().clearMessage()

    # ─────────────────────────────────────────────────────────────────────────
    # PROPERTY MANAGER HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def update_property_manager(self):
        # Guard against the scene's C++ object being deleted during shutdown
        try:
            # Don't override template properties during placement modes
            if self.scene.mode in ("pipe", "sprinkler", "wall", "wall_rect",
                                    "floor", "floor_rect", "roof", "roof_rect",
                                    "set_scale", "design_area"):
                return
            items = self.scene.selectedItems()
        except RuntimeError:
            return
        if items:
            self.prop_manager.show_properties(items)
        else:
            # Nothing selected — show plan/detail view info if applicable
            info = self._get_active_view_info()
            self.prop_manager.show_properties(info)

    def _get_active_view_info(self):
        """Return a PlanViewInfo for the active plan/detail tab, or None."""
        tab_text = self.central_tabs.tabText(self.central_tabs.currentIndex())
        if tab_text.startswith("Plan: "):
            level_name = tab_text[len("Plan: "):]
            pv = self.plan_view_mgr.get(tab_text)
            if pv is not None:
                from firepro3d.level_manager import PlanViewInfo
                return PlanViewInfo(
                    pv, self.level_mgr, self.scene.scale_manager,
                    on_view_range=lambda: self._open_plan_view_range(tab_text))
        elif tab_text.startswith("Detail: "):
            detail_name = tab_text[len("Detail: "):]
            marker = self.detail_manager.get_marker(detail_name)
            if marker is not None:
                marker._on_view_range = lambda: self._open_detail_view_range(
                    detail_name)
                return marker
        return None

    def _open_plan_view_range(self, tab_text: str):
        """Open view range dialog for a plan view tab."""
        level_name = tab_text[len("Plan: "):]
        pv = self.plan_view_mgr.get(tab_text)
        if pv is None:
            pv = self.plan_view_mgr.create(level_name, self.level_mgr)
        from firepro3d.view_range_dialog import ViewRangeDialog
        dlg = ViewRangeDialog(
            pv, self.level_mgr, self.plan_view_mgr,
            self.scene.scale_manager, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            vh, vd = dlg.get_values()
            pv.view_height = vh
            pv.view_depth = vd
            current_text = self.central_tabs.tabText(
                self.central_tabs.currentIndex())
            if current_text == tab_text:
                self._apply_plan_level(level_name)
            self.update_property_manager()

    def _open_detail_view_range(self, detail_name: str):
        """Open view range dialog for a detail view."""
        marker = self.detail_manager.get_marker(detail_name)
        if marker is None:
            return
        from firepro3d.level_manager import PlanView
        pv = PlanView(
            name=f"Detail: {detail_name}",
            level_name=marker.level_name,
            view_height=marker.view_height or 0.0,
            view_depth=marker.view_depth or 0.0,
        )
        from firepro3d.view_range_dialog import ViewRangeDialog
        dlg = ViewRangeDialog(
            pv, self.level_mgr, self.plan_view_mgr,
            self.scene.scale_manager, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            vh, vd = dlg.get_values()
            marker.view_height = vh
            marker.view_depth = vd
            self._apply_detail_level(detail_name)
            self.update_property_manager()

    # ─────────────────────────────────────────────────────────────────────────
    # EVENT HANDLING
    # ─────────────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if not self._ask_save_changes("closing"):
            event.ignore()
            return
        self.save_settings()
        self._cleanup_autosave()
        super().closeEvent(event)

    _STATE_VERSION = 4  # bump when dock layout changes between sprints

    def save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState(self._STATE_VERSION))
        self.settings.setValue("dock/browser", self.browser_dock.isVisible())
        self.settings.setValue("dock/properties", self.prop_dock.isVisible())
        self.settings.setValue("dock/hydraulics", self.hydro_dock.isVisible())
        self.settings.setValue("dock/radiation", self.radiation_dock.isVisible())
        # Persist pipe and sprinkler template settings (raw internal values,
        # not display-formatted, so they round-trip regardless of unit prefs).
        if self.current_pipe_template:
            pipe_props = {k: v["value"]
                          for k, v in self.current_pipe_template._properties.items()}
            pipe_props["Ceiling Offset"] = str(self.current_pipe_template.ceiling_offset)
            self.settings.setValue("template/pipe", pipe_props)
        if self.current_sprinkler_template:
            spr_props = {k: v["value"]
                         for k, v in self.current_sprinkler_template._properties.items()}
            self.settings.setValue("template/sprinkler", spr_props)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)

    # Show splash IMMEDIATELY — before heavy 3D imports
    splash = _SplashScreen()
    splash.show()
    splash.set_progress(5, "Applying theme...")
    QApplication.processEvents()

    _t = th.detect()
    app.setStyleSheet(th.build_app_qss(_t))

    # Defer the heavy pyvista/VTK import until after splash is visible
    splash.set_progress(20, "Loading 3D engine...")
    QApplication.processEvents()
    global View3D
    from firepro3d.view_3d import View3D

    splash.set_progress(50, "Building UI...")
    window = MainWindow(splash=splash)
    window.resize(800, 600)
    splash.close()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()