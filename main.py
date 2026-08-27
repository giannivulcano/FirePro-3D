import sys, os
import tempfile
import traceback
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QToolBar,
                              QFileDialog, QDockWidget, QInputDialog,
                              QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QSpinBox, QDialogButtonBox, QLineEdit,
                              QTabWidget, QMenu, QWidget, QMessageBox,
                              QComboBox, QDoubleSpinBox, QFormLayout,
                              QProgressBar, QToolButton, QProgressDialog)
from PyQt6.QtGui import QPainter, QIcon, QColor, QPixmap, QKeySequence, QShortcut, QFont, QAction
from PyQt6.QtCore import Qt, QSettings, QSize, QPointF, QTimer, pyqtSignal
from PyQt6.QtWidgets import QGraphicsTextItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.sprinkler import Sprinkler
from firepro3d.pipe import Pipe
from firepro3d.annotations import NoteAnnotation
from firepro3d.dxf_preview_dialog import UnderlayImportDialog
from firepro3d.property_manager import PropertyManager
from firepro3d.sprinkler_db import SprinklerDatabase
from firepro3d.scale_manager import DisplayUnit
from firepro3d.hydraulic_report import HydraulicReportWidget
from firepro3d.thermal_radiation_report import ThermalRadiationReportWidget
from firepro3d.level_manager import LevelManager, PlanViewManager
from firepro3d.level_widget import LevelWidget
from firepro3d.paper_space import (
    PaperSpaceWidget, Sheet, SheetManager, SheetProperties, ViewResolver,
    PAPER_SIZES, TextAnnotationData, TextAnnotationItem,
    text_template_to_settings, apply_template_settings,
    native_orientation_from_dims, sheet_page_mm,
)
from firepro3d.ribbon_bar import RibbonBar
# view_3d deferred — imports pyvista/VTK which is slow
from firepro3d.array_dialog import ArrayDialog
from firepro3d.project_browser import ProjectBrowser
from firepro3d.model_browser import ModelBrowser
from firepro3d.feature_browser import FeatureBrowser
from firepro3d.constants import DEFAULT_GRIDLINE_SPACING_MM, DEFAULT_GRIDLINE_LENGTH_MM
from firepro3d.feature import DEFAULT_FEATURE_FOR_TYPE
from firepro3d.wall_opening import WallOpening
from firepro3d import theme as th


# ─────────────────────────────────────────────────────────────────────────────
# Unhandled-exception guard
# ─────────────────────────────────────────────────────────────────────────────

ERROR_LOG_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
    "FirePro3D", "error.log")


def _log_unhandled_exception(exc_type, exc_value, exc_tb):
    """Log an unhandled exception instead of letting PyQt6 kill the app.

    With the default ``sys.excepthook``, PyQt6 escalates any Python
    exception that escapes Qt-invoked code (slots, timer handlers, virtual
    overrides such as ``boundingRect``) to ``qFatal()``, aborting the
    process silently (0xC0000409 fail-fast in Qt6Core — no traceback, no
    dialog). Installing a custom hook disables that escalation; the
    traceback goes to stderr and is appended to ``ERROR_LOG_PATH`` so
    field crashes stay diagnosable.
    """
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    sys.stderr.write(msg)
    try:
        os.makedirs(os.path.dirname(ERROR_LOG_PATH), exist_ok=True)
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                     f"Unhandled exception:\n{msg}\n")
    except OSError:
        pass  # never let the guard itself crash the app


def install_excepthook():
    """Install the global exception guard (call before the event loop)."""
    sys.excepthook = _log_unhandled_exception


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
        bar_container.setStyleSheet("background: #ffffff; border-radius: 4px;")
        stack = QStackedLayout(bar_container)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.setContentsMargins(0, 0, 0, 0)

        from firepro3d.loading_bar import _BAR_STYLE
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(_BAR_STYLE)

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


class _SnapIndicatorLabel(QLabel):
    """Clickable status-bar label for the SNAP state indicator."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("SNAP", parent)
        self.setToolTip("Select Nearest Anchor Point (SNAP)  [F3]")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(80)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("snapOn", True)
        self._apply_style()

    def setSnapOn(self, on: bool) -> None:
        self.setProperty("snapOn", bool(on))
        self._apply_style()

    def _apply_style(self) -> None:
        on = bool(self.property("snapOn"))
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


class _GuidesIndicatorLabel(QLabel):
    """Clickable status-bar label for the alignment-guides state indicator.

    Mirrors _SnapIndicatorLabel — enabled = bold green pill, disabled = grey.
    """

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("ALIGN", parent)
        self.setToolTip("Toggle ALIGN (F11)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(80)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("guidesOn", True)
        self._apply_style()

    def setGuidesOn(self, on: bool) -> None:
        self.setProperty("guidesOn", bool(on))
        self._apply_style()

    def _apply_style(self) -> None:
        on = bool(self.property("guidesOn"))
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


class _SnapToolbar(QToolBar):
    """Dockable toolbar of one-click toggles for the 8 SNAP snap types.

    The 8 ``SnapEngine.snap_*`` booleans are the single source of truth;
    this toolbar and the Snap Settings dialog both read/write them. Per-type
    state persists under the existing ``snap/{attr}`` QSettings keys.
    """

    # (abbreviation, full-name tooltip, SnapEngine attribute, icon filename)
    _SNAP_TYPES = [
        ("END", "Endpoint",      "snap_endpoint",      "snap_endpoint.svg"),
        ("MID", "Midpoint",      "snap_midpoint",      "snap_midpoint.svg"),
        ("INT", "Intersection",  "snap_intersection",  "snap_intersection.svg"),
        ("CEN", "Center",        "snap_center",        "snap_center.svg"),
        ("QUA", "Quadrant",      "snap_quadrant",      "snap_quadrant.svg"),
        ("NEA", "Nearest",       "snap_nearest",       "snap_nearest.svg"),
        ("PER", "Perpendicular", "snap_perpendicular", "snap_perpendicular.svg"),
        ("TAN", "Tangent",       "snap_tangent",       "snap_tangent.svg"),
    ]

    def __init__(self, engine, main_window):
        # Do NOT pass main_window as the Qt parent — addToolBar() reparents
        # this widget, and tests use a non-QWidget stub window.
        super().__init__("SNAP")
        self.setObjectName("SnapToolbar")  # required for save/restoreState
        self._engine = engine
        self._main_window = main_window
        self._actions: dict[str, QAction] = {}
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setStyleSheet(
            # Transparent 1px border on every button so checked/unchecked have
            # the same box size — toggling no longer reflows the toolbar.
            "QToolButton { padding: 2px 4px; border: 1px solid transparent;"
            " border-radius: 3px; }"
            "QToolButton:checked { background: #2a5a8a; border-color: #44aaff; }"
            "QToolButton:disabled { color: #888; }"
            # Dimmed-but-checked must stay legible (F3 master-off state).
            "QToolButton:checked:disabled { background: #243a4e;"
            " border-color: #3a607e; color: #99bbdd; }"
        )
        from firepro3d.assets import asset_path
        for abbr, tip, attr, icon_file in self._SNAP_TYPES:
            act = QAction(QIcon(asset_path("Ribbon", icon_file)), abbr, self)
            act.setToolTip(tip)
            act.setCheckable(True)
            act.setChecked(bool(getattr(self._engine, attr)))
            act.toggled.connect(
                lambda checked, a=attr: self._on_toggle(a, checked))
            self.addAction(act)
            self._actions[attr] = act

    def _on_toggle(self, attr: str, checked: bool) -> None:
        setattr(self._engine, attr, checked)
        self._main_window.settings.setValue(f"snap/{attr}", checked)

    def _set_all(self, value: bool) -> None:
        for attr in self._actions:
            setattr(self._engine, attr, value)
            self._main_window.settings.setValue(f"snap/{attr}", value)
        self.refresh_from_engine()

    def refresh_from_engine(self) -> None:
        """Sync button checked states to the current engine attributes
        without re-triggering the toggle handler."""
        for attr, act in self._actions.items():
            act.blockSignals(True)
            act.setChecked(bool(getattr(self._engine, attr)))
            act.blockSignals(False)

    def _on_snap_toggled(self, enabled: bool) -> None:
        """F3 / status-bar pill master override: dim (but preserve) buttons."""
        for act in self._actions.values():
            act.setEnabled(bool(enabled))

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("Enable All", lambda: self._set_all(True))
        menu.addAction("Disable All", lambda: self._set_all(False))
        menu.addSeparator()
        menu.addAction("Snap Settings…",
                       self._main_window._open_snap_tolerance_dialog)
        menu.exec(event.globalPos())


class MainWindow(QMainWindow):
    # ── Contextual-tab catalog ─────────────────────────────────────────────────
    # Maps entity-family key → human-readable ribbon tab title.
    # Used by _init_contextual_tabs() to build _contextual_registry.
    _CONTEXTUAL_TABS: dict[str, str] = {
        "geo2d":        "2D Geometry",
        "geo3d":        "3D Geometry",
        "annotation":   "Annotation",
        "wall":         "Wall",
        "floor":        "Floor",
        "roof":         "Roof",
        "room":         "Room",
        "opening":      "Opening",
        "detail":       "Detail",
        "pipe":         "Pipe",
        "sprinkler":    "Sprinkler",
        "water_supply": "Water Supply",
        "design_area":  "Design Area",
        "gridline":     "Gridline",
        "level":        "Level",
        "viewport":     "Viewport",
        "sheet_text":   "Sheet Text",
        "mixed":        "Modify",
    }

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
        self.current_opening_template = WallOpening(wall=None, feature_id="door_914")
        self._current_file: str | None = None
        self._modified: bool = False
        self._MAX_RECENT = 8
        self._recent_files: list[str] = self.settings.value("recent_files", [], type=list)
        self._last_feature: dict[str, str] = {}  # type_ → last-used feature id

        # Auto-save every 2 minutes for crash recovery
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(2 * 60 * 1000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

        # Scene + View
        self._splash_progress(10, "Initialising scene...")
        # One shared sprinkler database, owned here and injected into every
        # consumer (scene/auto-populate, property panel, manager dialog).
        self._sprinkler_db = SprinklerDatabase()
        self.scene = Model_Space()
        self.scene.set_sprinkler_db(self._sprinkler_db)
        # Give templates a scene reference so they can always find the
        # *current* scale_manager (survives _clear_scene resets).
        self.current_pipe_template._scene_ref = self.scene
        self.current_sprinkler_template._scene_ref = self.scene
        self.current_opening_template._scene_ref = self.scene
        self.view = Model_View(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Drag-drop import
        self.view.drop_import_requested.connect(self._on_drop_import)

        # Draw tool style defaults (white pen in dark theme, 1px cosmetic)
        _t = th.detect()
        # Level manager — shared between scene and UI
        self.level_mgr = LevelManager()
        self.scene._level_manager = self.level_mgr
        self.plan_view_mgr = PlanViewManager()
        self.scene._plan_view_manager = self.plan_view_mgr

        # Central tab widget: Model Space | 3D View | Paper Space
        self._splash_progress(35, "Building 3D viewport...")
        # Paper space widget created after managers are initialised (see below)
        self.paper_space_widget = None  # placeholder — set after ViewResolver
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
        self.prop_manager.set_sprinkler_db(self._sprinkler_db)
        self.prop_manager.set_level_manager(self.level_mgr)
        self.scene.requestPropertyUpdate.connect(self.prop_manager.show_properties)
        self.view_3d.entitySelected.connect(self.prop_manager.show_properties)
        self.scene.selectionChanged.connect(self.update_property_manager)

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
        self.project_browser.createPaperSheet.connect(self._create_sheet)
        self.project_browser.deletePaperSheet.connect(self._delete_sheet)
        self.project_browser.sheetSelected.connect(
            self._on_browser_sheet_selected)
        self.project_browser.sheetOrderChanged.connect(self._reorder_sheets)
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

        # Paper space — ViewResolver + Sheet + widget
        self.scene._sheets = [Sheet.create_default()]
        self.sheet_mgr = SheetManager(self.scene._sheets)
        self._sheet = self.sheet_mgr.sheets[0]
        self._view_resolver = ViewResolver(
            self.scene, self.plan_view_mgr,
            self.detail_manager, self.elevation_manager,
            level_manager=self.level_mgr,
        )
        self.paper_space_widget = PaperSpaceWidget(
            self._sheet, self._view_resolver)
        self.paper_space_widget.navigate_to_view.connect(
            self._navigate_to_source_view)

        # Sheet-text template (pipe/sprinkler pattern) + paper selection wiring
        self.current_text_template = TextAnnotationItem(TextAnnotationData())
        self.current_text_template._scale_manager_ref = self.scene.scale_manager
        self.paper_space_widget.paper_scene.text_template = \
            self.current_text_template.data
        self.paper_space_widget.paper_scene.selectionChanged.connect(
            self.update_paper_property_manager)
        self.paper_space_widget.paper_scene.undo_stack.indexChanged.connect(
            lambda _=0: self.update_paper_property_manager())
        self.paper_space_widget.add_text_mode_toggled.connect(
            self._on_add_text_mode_toggled)
        self.paper_space_widget.add_text_mode_toggled.connect(
            self._sync_add_text_ribbon_btn)
        self.paper_space_widget.add_text_mode_toggled.connect(
            lambda _on: self._update_font_group_context())
        self.paper_space_widget.paper_scene.selectionChanged.connect(
            self._update_font_group_context)
        self.paper_space_widget.paper_scene.undo_stack.indexChanged.connect(
            lambda _=0: self._update_font_group_context())

        self.model_browser = ModelBrowser()
        self.model_browser.set_scene(self.scene)
        self.model_browser.entitySelected.connect(self.prop_manager.show_properties)
        self.scene.selectionChanged.connect(self.model_browser.sync_from_scene)
        self.scene.sceneModified.connect(self.model_browser.refresh)

        self.feature_browser = FeatureBrowser()
        self.feature_browser.featureActivated.connect(self._on_feature_activated)

        self._left_tabs = QTabWidget()
        self._left_tabs.setTabPosition(QTabWidget.TabPosition.West)
        self._left_tabs.addTab(self.project_browser, "Project")
        self._left_tabs.addTab(self.model_browser, "Model")
        self._left_tabs.addTab(self.feature_browser, "Features")

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

        # Keyboard shortcuts to toggle dock visibility (B = browser, / = properties).
        # NOTE: "/" (not "P") toggles Properties — P is the Polygon tool shortcut.
        QShortcut(QKeySequence("B"), self,
                  lambda: self.browser_dock.setVisible(not self.browser_dock.isVisible()),
                  context=Qt.ShortcutContext.ApplicationShortcut)
        QShortcut(QKeySequence("/"), self,
                  lambda: self.prop_dock.setVisible(not self.prop_dock.isVisible()),
                  context=Qt.ShortcutContext.ApplicationShortcut)

        # Hydraulic report dock (tabbed: Summary | Node Summary Table | Graph)
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
        # SNAP status-bar indicator (snap-spec §9.5 / §12 item 11).
        # Added BEFORE coord_label so it sits to the left of the
        # coordinate readout, clear of the QSizeGrip at the far right.
        self.snap_indicator = _SnapIndicatorLabel(self)
        self.snap_indicator.clicked.connect(self.scene.toggle_snap)
        status_bar.addPermanentWidget(self.snap_indicator)
        self.scene.snapToggled.connect(self._update_snap_indicator)
        self._update_snap_indicator(self.scene._snap_enabled)
        # ALIGN status-bar indicator — mirrors SNAP pill for ALIGN state.
        self.guides_indicator = _GuidesIndicatorLabel(self)
        self.guides_indicator.clicked.connect(self.scene.set_align_enabled)
        status_bar.addPermanentWidget(self.guides_indicator)
        self.scene.alignToggled.connect(self._update_guides_indicator)
        self._update_guides_indicator(self.scene._align_enabled)
        # Pipe-mode node snap readout (between SNAP and coordinates)
        self.node_snap_label = QLabel("")
        self.node_snap_label.setStyleSheet(
            "color: #ffcc44; padding: 2px 8px; "
            "border: 1px solid #665522; border-radius: 3px;"
        )
        self.node_snap_label.setMinimumWidth(0)
        self.node_snap_label.hide()  # only visible in pipe mode with candidates
        status_bar.addPermanentWidget(self.node_snap_label)
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
        self.scene.pipeNodeHighlight.connect(self._update_node_snap_readout)
        self.scene.modeChanged.connect(self._update_mode_label)
        self.scene.modeChanged.connect(self._sync_mode_buttons)
        self.scene.modeChanged.connect(self._on_mode_changed_template)
        self.scene.sceneModified.connect(self._on_scene_modified)
        self.paper_space_widget.paper_scene.sheetModified.connect(
            self._on_paper_modified)
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

        # SNAP toolbar — per-type snap toggles (snap-toolbar spec).
        # Must be created before restore_settings() so restoreState() can
        # place it; refresh_from_engine() is called there once QSettings
        # have been applied.
        self.snap_toolbar = _SnapToolbar(self.scene._snap_engine, self)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, self.snap_toolbar)
        self.scene.snapToggled.connect(self.snap_toolbar._on_snap_toggled)
        self.snap_toolbar._on_snap_toggled(self.scene._snap_enabled)
        # Hidden on first launch; the Snap-group "SNAP Bar" button toggles it.
        # restoreState() (in restore_settings, below) re-applies the user's
        # saved visibility, and visibilityChanged keeps the button in sync.
        self.snap_toolbar.hide()
        self.snap_toolbar.visibilityChanged.connect(self._snap_bar_btn.setChecked)
        self._snap_bar_btn.setChecked(self.snap_toolbar.isVisible())

        # Global keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.save_file)

        # F3 global SNAP toggle — a window-level shortcut so it fires from any
        # ribbon tab (a QToolButton shortcut only fires when its ribbon page is
        # the visible one). toggle_snap() flips state; snapToggled then syncs
        # the ribbon button, status-bar pill, and SNAP toolbar.
        self._f3_shortcut = QShortcut(QKeySequence("F3"), self)
        self._f3_shortcut.activated.connect(self.scene.toggle_snap)
        # F11 global ALIGN toggle — mirrors F3 / SNAP pattern.
        self._f11_shortcut = QShortcut(QKeySequence("F11"), self)
        self._f11_shortcut.activated.connect(self.scene.set_align_enabled)
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
        # Align on Shift+A (its old "A, L" chord was retired so bare A is the Arc
        # tool shortcut; Ctrl+A is Select All, so Shift+A keeps the A mnemonic).
        QShortcut(QKeySequence("Shift+A"), self,
                  lambda: self.scene.set_mode("align"))

        # Restore settings
        self._splash_progress(90, "Restoring settings...")
        self.restore_settings()
        self._splash_progress(100, "Ready")

        # New-project setup — mirrors new_file() without the save prompt
        self.scene._clear_scene()
        self.level_widget.populate()
        pass  # level indicator removed
        self._place_default_gridlines()
        self._create_elevation_markers()
        from firepro3d.display_manager import apply_default_display_settings
        apply_default_display_settings(self.scene)
        self._apply_persistent_unit_prefs()

        # Reset undo stack so the seeded template gridlines are the baseline
        # (index 0) and cannot be undone away. Without this, place_grid_lines
        # pushed an EMPTY-scene snapshot before adding the gridlines, so the
        # first Ctrl+Z after any edit reverted to the empty pre-seed scene and
        # wiped the whole default grid. Mirrors new_file() (see that method).
        self.scene._undo_stack = []
        self.scene._undo_pos = -1
        self.scene.push_undo_state()

        self._current_file = None
        self._modified = False
        self._update_title()
        self._initial_fit_done = False  # fit_to_screen deferred to showEvent

        self._push_sheet_list()
        self._recompute_placed_views()

        # Defer recovery check until after the window is fully shown
        QTimer.singleShot(500, self._check_recovery)

    def _splash_progress(self, value: int, message: str = ""):
        """Update the splash screen progress bar if present."""
        if self._splash is not None:
            self._splash.set_progress(value, message)

    def _migrate_inference_to_align(self) -> None:
        """One-time QSettings rename inference/* → align/* (behavior-neutral).

        Copies any legacy inference/* key to align/* when the new key is absent,
        then reads align/* everywhere. Safe to run every startup: it only writes
        when the new key is missing and the old one exists.
        """
        s = self.settings
        legacy = {"inference/alignment_guides": "align/enabled"}
        for old, new in legacy.items():
            if s.contains(old) and not s.contains(new):
                s.setValue(new, s.value(old, type=bool))

    def restore_settings(self):
        geom = self.settings.value("geometry", b"")
        if geom:
            self.restoreGeometry(geom)
        state = self.settings.value("windowState", b"")
        if state:
            self.restoreState(state, self._STATE_VERSION)
        # Panels open in FIXED startup defaults (NOT persisted from the previous
        # session): Project Browser + Properties always open, Hydraulic Report
        # always closed.  All remain toggleable during the session.  Applied
        # after restoreState() so it overrides any dock visibility the saved
        # window-state would otherwise re-apply.
        self.browser_dock.setVisible(True)
        self.prop_dock.setVisible(True)
        self.hydro_dock.setVisible(False)
        # Restore snap settings
        if self.settings.contains("snap/grid_size"):
            grid = self.settings.value("snap/grid_size", 10, type=float)
            self.view.set_grid(self.view._grid_visible, grid)
        if self.settings.contains("snap/angle_deg"):
            self.scene._snap_angle_deg = self.settings.value("snap/angle_deg", 45, type=float)
        if self.settings.contains("snap/tolerance_px"):
            from firepro3d import snap_engine
            snap_engine.SNAP_TOLERANCE_PX = self.settings.value("snap/tolerance_px", 15, type=int)
        if self.settings.contains("snap/hysteresis_px"):
            from firepro3d import snap_engine
            snap_engine.SNAP_HYSTERESIS_PX = self.settings.value("snap/hysteresis_px", 3, type=int)
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
        # Reflect the just-restored per-type snap state on the toolbar.
        self.snap_toolbar.refresh_from_engine()
        # Restore ALIGN toggle (migrating legacy inference/* key if present)
        self._migrate_inference_to_align()
        align_on = self.settings.value(
            "align/enabled", True, type=bool)
        self.scene.set_align_enabled(align_on)
        # Restore the ALIGN tunables (path-tol / dwell / max-points / per-
        # direction toggles), mirroring the SNAP per-type restore above. Push
        # each into the live Model_Space + its AlignController so a saved
        # preference is in effect immediately (not just on next Preferences open).
        from firepro3d.constants import (
            ALIGN_PATH_TOL_PX, ALIGN_DWELL_MS, ALIGN_MAX_POINTS,
            ALIGN_DIR_HV_DEFAULT, ALIGN_DIR_EXTENSION_DEFAULT,
            ALIGN_DIR_PARALLEL_DEFAULT,
        )
        self.scene._align_path_tol_px = float(self.settings.value(
            "align/path_tol_px", int(ALIGN_PATH_TOL_PX), type=int))
        _ctrl = self.scene._align_controller
        _ctrl.dwell_ms = self.settings.value(
            "align/dwell_ms", ALIGN_DWELL_MS, type=int)
        _ctrl.max_points = self.settings.value(
            "align/max_points", ALIGN_MAX_POINTS, type=int)
        _ctrl.set_direction_flags(
            hv=self.settings.value("align/dir_hv",
                                   ALIGN_DIR_HV_DEFAULT, type=bool),
            extension=self.settings.value("align/dir_extension",
                                          ALIGN_DIR_EXTENSION_DEFAULT, type=bool),
            parallel=self.settings.value("align/dir_parallel",
                                         ALIGN_DIR_PARALLEL_DEFAULT, type=bool))
        # Restore display unit and precision from user preference
        self._apply_persistent_unit_prefs()
        # Restore pipe and sprinkler template settings
        if self.settings.contains("template/pipe"):
            pipe_props = self.settings.value("template/pipe", {})
            if isinstance(pipe_props, dict):
                for k, v in pipe_props.items():
                    self.current_pipe_template.set_property(k, v)
        if self.settings.contains("template/sprinkler"):
            spr_props = self.settings.value("template/sprinkler", {})
            if isinstance(spr_props, dict):
                for k, v in spr_props.items():
                    self.current_sprinkler_template.set_property(k, v)
        if self.settings.contains("template/text"):
            raw = self.settings.value("template/text", {})
            if isinstance(raw, dict):
                apply_template_settings(self.current_text_template.data, raw)
        if self.settings.contains("template/opening"):
            op = self.settings.value("template/opening", {})
            if isinstance(op, dict):
                tmpl = self.current_opening_template
                fid = op.get("feature_id")
                if fid:
                    tmpl.apply_feature(str(fid))   # resets dims to feature defaults
                # Restore user-authored overrides ON TOP of the feature defaults.
                if "sill_mm" in op:
                    tmpl.sill_mm = float(op["sill_mm"])
                if "width_mm" in op:
                    tmpl.width_mm = float(op["width_mm"])
                if "height_mm" in op:
                    tmpl.height_mm = float(op["height_mm"])
                if "alignment" in op:
                    tmpl.alignment = str(op["alignment"])
                if "mirror_hinge" in op:
                    mh = op["mirror_hinge"]
                    tmpl.mirror_hinge = (mh if isinstance(mh, bool)
                                         else str(mh).lower() in ("true", "1"))
                if "mirror_facing" in op:
                    mf = op["mirror_facing"]
                    tmpl.mirror_facing = (mf if isinstance(mf, bool)
                                          else str(mf).lower() in ("true", "1"))

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

    def _switch_sheet(self, sheet):
        """Make *sheet* the active sheet and rebind the canonical widget.

        set_sheet → update_from_sheet clears the paper undo stack (grill:
        undo history does not survive a sheet switch) and suppresses
        sheetModified during the rebuild (§17.7).
        """
        self._sheet = sheet
        self.paper_space_widget.set_sheet(sheet, self._view_resolver)
        self._push_sheet_list()
        self.update_paper_property_manager()

    def _paper_tab_title(self) -> str:
        return f"{self._sheet.number} - {self._sheet.name}"

    def _push_sheet_list(self):
        """Push the authoritative sheet list to the browser + tab title."""
        self.project_browser.set_sheets(
            [(s.number, f"{s.number} - {s.name}")
             for s in self.sheet_mgr.sheets])
        idx = self.central_tabs.indexOf(self.paper_space_widget)
        if idx != -1:
            self.central_tabs.setTabText(idx, self._paper_tab_title())

    def _recompute_placed_views(self):
        """Italics source-of-truth: every sheet's sheet_views (§19.5)."""
        placed = {(sv.source_view_type, sv.source_view_name)
                  for s in self.sheet_mgr.sheets for sv in s.sheet_views}
        self.project_browser.set_placed_views(placed)

    def _create_sheet(self):
        """Instant create (grill): auto number, default name, becomes active."""
        sheet = self.sheet_mgr.create()
        self._switch_sheet(sheet)
        self._on_paper_modified()

    def _delete_sheet(self, number: str):
        sheet = self.sheet_mgr.get(number)
        if sheet is None:
            return
        if len(self.sheet_mgr.sheets) <= 1:
            self.statusBar().showMessage("Cannot delete the last sheet.", 4000)
            return
        resp = QMessageBox.question(
            self, "Delete Sheet",
            f"Delete sheet {sheet.number} - {sheet.name}?\n"
            f"{len(sheet.sheet_views)} view(s) and {len(sheet.annotations)} "
            f"annotation(s) will be removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if resp != QMessageBox.StandardButton.Yes:
            return
        neighbor = self.sheet_mgr.delete(sheet)
        if sheet is self._sheet:
            self._switch_sheet(neighbor)
        self._on_paper_modified()
        # Reset the panel unconditionally: when the deleted sheet was NOT active
        # the _switch_sheet branch is skipped and the panel may still hold a
        # SheetProperties adapter wrapping the now-deleted sheet (stale adapter).
        self.update_paper_property_manager()

    def _reorder_sheets(self, numbers: list):
        if self.sheet_mgr.reorder([str(n) for n in numbers]):
            self._on_paper_modified()
        # Always reconcile the tree — rejected orders push the truth back.
        self._push_sheet_list()

    def _on_browser_sheet_selected(self, number: str):
        """Sheet row single-click → sheet properties in the panel (spec §19.4)."""
        # Add-Text mode owns the panel (shows the text template — §9.6).
        if self.paper_space_widget.view._add_text_mode:
            return
        sheet = self.sheet_mgr.get(number)
        if sheet is not None:
            self.prop_manager.show_properties(self._sheet_props_adapter(sheet))

    def _sheet_props_adapter(self, sheet: "Sheet") -> "SheetProperties":
        """Build a SheetProperties adapter wired to this MainWindow's callbacks.

        Args:
            sheet: The Sheet to adapt.

        Returns:
            A SheetProperties instance whose on_change fires _on_sheet_meta_changed
            and whose on_reject posts a transient status-bar message.
        """
        return SheetProperties(
            sheet, self.sheet_mgr,
            on_change=self._on_sheet_meta_changed,
            on_reject=lambda msg: self.statusBar().showMessage(msg, 4000),
            scene_getter=lambda: self.paper_space_widget.paper_scene)

    def _on_sheet_meta_changed(self):
        """Rename/renumber committed: refresh titleblock Sheet No + UI + dirty.

        Known: double-panel-rebuild harmless — browser push fires selectionChanged
        AND the 50ms refresh timer both repopulate the panel; follow-up filed.
        """
        self.paper_space_widget.paper_scene._refresh_titleblock()
        self._on_paper_modified()

    def _activate_paper_sheet(self, number: str | None = None):
        """Open/switch the canonical paper tab; optionally switch sheets.

        Args:
            number: Sheet number to activate; None keeps the current sheet
                (ribbon call sites just open the tab).
        """
        w = self.paper_space_widget
        sheet = self.sheet_mgr.get(number) if number else None
        if sheet is not None and sheet is not self._sheet:
            self._switch_sheet(sheet)
        idx = self.central_tabs.indexOf(w)
        if idx == -1:
            idx = self.central_tabs.addTab(w, self._paper_tab_title())
        else:
            self.central_tabs.setTabText(idx, self._paper_tab_title())
        self.central_tabs.setCurrentIndex(idx)

    def _navigate_to_source_view(self, view_type: str, view_name: str):
        """Navigate to a source view from a paper space viewport."""
        if view_type == "plan":
            level_name = view_name.replace("Plan: ", "", 1)
            self._activate_plan_view(level_name)
        elif view_type == "detail":
            self.detail_manager.open_detail(view_name)
        elif view_type == "elevation":
            self.elevation_manager.open_elevation(view_name.lower())

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
        # A placement belongs to the view it was started in.  Every plan tab
        # shares one Model_Space, so the preview items render in all of them
        # while the committed geometry is level-filtered into one — and the
        # HUD would be left parented to a view that is no longer visible.
        # set_mode is the same teardown Escape uses; re-implementing its
        # per-mode guards here would be a mirror waiting to drift.
        if self.scene.get_placement_anchor() is not None \
                or self.scene.is_input_mode():
            self.scene.set_mode("select")
        tab_text = self.central_tabs.tabText(index)
        if tab_text.startswith("Plan: "):
            level_name = tab_text[len("Plan: "):]
            self._apply_plan_level(level_name)
        elif tab_text.startswith("Detail: "):
            detail_name = tab_text[len("Detail: "):]
            self._apply_detail_level(detail_name)
        # Route the property panel to the active tab's selection context
        w = self.central_tabs.widget(index)
        if isinstance(w, PaperSpaceWidget):
            self.update_paper_property_manager()
        else:
            self.update_property_manager()
        # Leaving the paper tab cancels add-text mode; context follows the tab
        if not isinstance(w, PaperSpaceWidget) and \
                self.paper_space_widget.view._add_text_mode:
            self.paper_space_widget.set_add_text_mode(False)
        self._update_font_group_context()

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
        self.scene.active_view_key = f"plan:Plan: {level_name}"
        self.scene.active_level = level_name
        resolver = getattr(self, "_view_resolver", None)
        ctx = resolver.resolve_level_context(
            "plan", f"Plan: {level_name}") if resolver is not None else None
        if ctx is not None:
            _lvl, vh, vd = ctx
            self.level_mgr.apply_to_scene(self.scene, level_name,
                                          view_height=vh, view_depth=vd)
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
        self.scene.active_view_key = f"detail:{detail_name}"
        level_name = marker.level_name
        self.scene.active_level = level_name
        resolver = getattr(self, "_view_resolver", None)
        ctx = resolver.resolve_level_context(
            "detail", detail_name) if resolver is not None else None
        if ctx is not None:
            _lvl, vh, vd = ctx
            self.level_mgr.apply_to_scene(self.scene, level_name,
                                          view_height=vh, view_depth=vd)
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
            dlg = QDialog(self)
            dlg.setWindowTitle(title)
            dlg.setWindowFlags(
                Qt.WindowType.Dialog
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.CustomizeWindowHint)
            lay = QVBoxLayout(dlg)
            lbl = QLabel(message)
            lbl.setWordWrap(True)
            lay.addWidget(lbl)
            _result = ["match"]
            for text, val in (("Create Riser", "riser"),
                              ("Use Template Elevation", "template"),
                              ("Use Start Node Elevation", "match")):
                btn = QPushButton(text)
                btn.clicked.connect(
                    lambda _c=False, v=val: (_result.__setitem__(0, v),
                                             dlg.accept()))
                lay.addWidget(btn)
            dlg.exec()
            result = _result[0]
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
        """Build the seven base workflow ribbon tabs and wire every button.

        Tabs:
          1. Manage             — file I/O, import, preferences, undo/redo, snap
          2. View               — fit, display manager, dock panels
          3. Create             — geometry tools, blocks
          4. Architecture       — walls/floors/roofs/rooms, datums (levels, gridlines)
          5. Sprinkler Systems  — pipe/sprinkler layout, tools, hydraulics
          6. Analyze            — thermal radiation
          7. Draft              — annotate, font, page, plot

        Must be called *after* all dock widgets are created so that dock
        visibility toggles can be wired correctly.
        """
        from firepro3d.icons import themed_icon, LIGHT, DARK
        from firepro3d import theme as _th
        _theme = DARK if _th.detect().name == DARK else LIGHT
        _I = lambda name: themed_icon(name, _theme)

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
        self._init_view_tab(_I, _btn)
        self._init_create_tab(_I, _btn, _mode_btn)
        self._init_architecture_tab(_I, _btn, _mode_btn)
        self._init_sprinkler_systems_tab(_I, _btn, _mode_btn)
        self._init_analyze_tab(_I, _btn)
        self._init_draft_tab(_I, _btn, _mode_btn)

        # Build the contextual-tab registry (catalog only; no tab inserted yet).
        self._init_contextual_tabs()

        # Contextual Edit-tab handler (real logic added in a later task).
        self.scene.selectionChanged.connect(self._on_selection_changed_contextual)

    # ── Per-tab ribbon helpers ───────────────────────────────────────────────

    def _init_manage_tab(self, _I, _btn):
        """Build Tab 1: Manage — file I/O, import, preferences, undo/redo, snap."""
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

        # --- Settings ---
        g_set = manage_page.add_group("Settings")
        _btn = g_set.add_large_button(
            "Preferences", _I("info_icon.svg"),
            self._open_preferences)
        _btn.setToolTip("Open application preferences")

        # --- Edit (Undo/Redo always accessible) ---
        g_edit = manage_page.add_group("Edit")
        self._btn_undo = g_edit.add_large_button(
            "Undo", _I("undo_icon.svg"),
            self._dispatch_undo, shortcut="Ctrl+Z")
        self._btn_undo.setToolTip("Undo last action [Ctrl+Z]")
        self._btn_redo = g_edit.add_large_button(
            "Redo", _I("redo_icon.svg"),
            self._dispatch_redo, shortcut="Ctrl+Y")
        self._btn_redo.setToolTip("Redo last undone action [Ctrl+Y]")

        # --- Snap (moved from Draw tab) ---
        g_snap = manage_page.add_group("Snap")
        self._snap_btn = g_snap.add_large_button(
            "SNAP",
            _I("placeholder_icon.svg"),
            self._toggle_snap, checkable=True)
        self._snap_btn.setChecked(True)
        self._snap_btn.setToolTip("Select Nearest Anchor Point (SNAP)  [F3]")
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
        # Toggle for the SNAP snap-type toolbar (hidden on first launch).
        self._snap_bar_btn = g_snap.add_small_button(
            "SNAP\nBar",
            _I("placeholder_icon.svg"),
            self._toggle_snap_bar, checkable=True)
        self._snap_bar_btn.setToolTip("Show/hide the SNAP snap-type toolbar")

    def _init_view_tab(self, _I, _btn):
        """Build Tab 2: View — fit, display manager, dock panels."""
        view_page = self.ribbon.add_page("View")

        # --- Navigate ---
        g_nav = view_page.add_group("Navigate")
        _btn = g_nav.add_large_button(
            "Fit to\nScreen", _I("placeholder_icon.svg"),
            self._fit_active_plan_view)
        _btn.setToolTip("Zoom to fit all content [F]")

        # --- Underlay (moved from Manage → Import) ---
        g_ul = view_page.add_group("Underlay")
        _btn = g_ul.add_large_button(
            "Underlay\nManager", _I("import_icon.svg"), self.open_import_dialog)
        _btn.setToolTip("Import/manage PDF, DXF, or DWG underlays")
        _btn = g_ul.add_small_button(
            "Refresh All",
            _I("placeholder_icon.svg"),
            self.refresh_underlays)
        _btn.setToolTip("Re-import all underlays from disk")

        # --- Display ---
        g_disp = view_page.add_group("Display")
        _btn = g_disp.add_large_button(
            "Display\nManager", _I("placeholder_icon.svg"),
            self._open_display_manager)
        _btn.setToolTip("Configure visibility, colour, scale and opacity for model items")

        # --- Panels (dock toggles) ---
        g_pan = view_page.add_group("Panels")
        prop_btn = g_pan.add_small_button(
            "Properties", _I("info_icon.svg"),
            None, checkable=True)
        prop_btn.setToolTip("Show/hide Properties dock (/)")
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

    def _init_create_tab(self, _I, _btn, _mode_btn):
        """Build Tab 3: Create — geometry tools, blocks."""
        # ── Tab 3: Create ────────────────────────────────────────────────────
        draw_page = self.ribbon.add_page("Create")

        # --- 2D Geometry ---
        g_geom = draw_page.add_group("2D Geometry")
        _mode_btn(g_geom, "Line", _I("line_icon.svg"), "draw_line").setToolTip(
            "Draw a line (L)")
        # Plain Rectangle button — corner vs centre is chosen on-canvas with the
        # ←/→ variant cycle (consistent with Arc), superseding the old dropdown.
        _mode_btn(g_geom, "Rectangle", _I("rectangle_icon.svg"),
                  "draw_rectangle").setToolTip(
            "Draw a rectangle (R) — ←/→ toggles corner/centre")
        _mode_btn(g_geom, "Circle", _I("circle_icon.svg"), "draw_circle").setToolTip("Draw a circle (C)")
        _mode_btn(g_geom, "Polyline", _I("polyline_icon.svg"), "polyline").setToolTip("Draw a polyline (multi-segment) (K — placeholder)")
        _mode_btn(g_geom, "Arc", _I("arc_icon.svg"), "draw_arc").setToolTip("Draw an arc (3-click) (A) — ←/→ toggles start point")
        _mode_btn(g_geom, "Polygon", _I("polygon_icon.svg"), "polygon").setToolTip(
            "Draw a regular polygon — ↑/↓ sides, ←/→ inscribed/circumscribed (P)")

        # --- Blocks ---
        g_blocks = draw_page.add_group("Blocks")
        g_blocks.add_small_button(
            "Insert\nBlock", _I("placeholder_icon.svg"), self._insert_block)
        g_blocks.add_small_button(
            "Create\nBlock", _I("placeholder_icon.svg"), self._create_block)

    def _init_architecture_tab(self, _I, _btn, _mode_btn):
        """Build Tab 4: Architecture — building elements + datums."""
        # ── Tab 4: Architecture ──────────────────────────────────────────────
        build_page = self.ribbon.add_page("Architecture")

        # --- Building ---
        g_3d = build_page.add_group("Building")
        _wall_btn = g_3d.add_large_button(
            "Wall", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("wall"),
            checkable=True)
        _wall_btn.setToolTip("Draw a wall  (W) — ←/→ Line/Polyline/Rectangle, Space aligns")
        self._mode_buttons["wall"] = _wall_btn
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
            lambda: self._enter_opening_mode("door"),
            checkable=True)
        _door_btn.setToolTip("Place a door opening in a wall")
        self._mode_buttons["door"] = _door_btn
        _window_btn = g_3d.add_small_button(
            "Window", _I("placeholder_icon.svg"),
            lambda: self._enter_opening_mode("window"),
            checkable=True)
        _window_btn.setToolTip("Place a window opening in a wall")
        self._mode_buttons["window"] = _window_btn
        _blank_btn = g_3d.add_small_button(
            "Blank", _I("placeholder_icon.svg"),
            lambda: self._enter_opening_mode("blank"),
            checkable=True)
        _blank_btn.setToolTip("Place a blank (frameless) opening in a wall")
        self._mode_buttons["blank"] = _blank_btn
        _detail_btn = g_3d.add_small_button(
            "Detail", _I("placeholder_icon.svg"),
            lambda: self.scene.set_mode("detail"),
            checkable=True)
        _detail_btn.setToolTip("Draw a detail view crop boundary")
        self._mode_buttons["detail"] = _detail_btn

        # --- Datums ---
        g_datum = build_page.add_group("Datums")
        _btn = g_datum.add_large_button(
            "Levels", _I("placeholder_icon.svg"),
            self._open_level_dialog)
        _btn.setToolTip("Open Level Manager dialog")
        _mode_btn(g_datum, "Gridline", _I("gridline_icon.svg"), "draw_gridline").setToolTip(
            "Draw gridlines on canvas (2-click) (G)")

    def _init_sprinkler_systems_tab(self, _I, _btn, _mode_btn):
        """Build Tab 5: Sprinkler Systems — layout, tools, hydraulics."""
        # ── Tab 5: Sprinkler Systems ─────────────────────────────────────────
        sys_page = self.ribbon.add_page("Sprinkler Systems")

        # --- Layout ---
        g_sys = sys_page.add_group("Layout")
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

        # --- Tools ---
        g_tools = sys_page.add_group("Tools")
        g_tools.add_small_button(
            "Auto-Populate", _I("placeholder_icon.svg"),
            self._auto_populate_sprinklers)
        self._coverage_btn = g_tools.add_small_button(
            "Coverage Overlay", _I("placeholder_icon.svg"),
            self.toggle_coverage_overlay, checkable=True)
        self._coverage_btn.setToolTip("Show/hide sprinkler coverage circles")
        _sm_btn = g_tools.add_large_button(
            "Sprinkler\nManager", _I("sprinkler_manager_icon.svg"),
            self.open_sprinkler_manager)
        _sm_btn.setToolTip("Open sprinkler database manager")

        # --- Hydraulics ---
        g_hyd = sys_page.add_group("Hydraulics")
        _btn = g_hyd.add_large_button(
            "Run\nHydraulics", _I("hydraulics_icon.svg"),
            self.run_hydraulics, shortcut="F5")
        _btn.setToolTip("Run hydraulic calculation [F5]")
        _btn = g_hyd.add_large_button(
            "Clear\nResults", _I("clear_icon.svg"),
            self.clear_hydraulics)
        _btn.setToolTip("Clear hydraulic overlay and results")
        _ref_btn = g_hyd.add_large_button(
            "Equiv.\nLengths", _I("report_icon.svg"),
            self.show_equiv_length_ref)
        _ref_btn.setToolTip("NFPA 13 Table 22.4.3.1.1 — Equivalent pipe lengths")
        _btn = g_hyd.add_large_button(
            "Export PDF", _I("export_icon.svg"),
            self.hydro_report._export_pdf)
        _btn.setToolTip("Export hydraulic report to PDF")
        _btn = g_hyd.add_large_button(
            "Export CSV", _I("report_icon.svg"),
            self.hydro_report._export_csv)
        _btn.setToolTip("Export hydraulic results to CSV")

    def _init_analyze_tab(self, _I, _btn):
        """Build Tab 6: Analyze — thermal radiation."""
        # ── Tab 6: Analyze ───────────────────────────────────────────────────
        analyze_page = self.ribbon.add_page("Analyze")

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

    def _init_draft_tab(self, _I, _btn, _mode_btn):
        """Build Tab 7: Draft — annotate, font, page, plot."""
        # ── Tab 7: Draft ─────────────────────────────────────────────────────
        draft_page = self.ribbon.add_page("Draft")

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
            self._open_titleblock_editor)
        _btn.setToolTip("Edit title block template / fields")

        _btn = g_pg.add_small_button(
            "Refresh\nViewports",
            _I("placeholder_icon.svg"),
            self.paper_space_widget.refresh_viewport)
        _btn.setToolTip("Repaint the model-space previews")
        _btn = g_pg.add_small_button(
            "Fit Sheet",
            _I("placeholder_icon.svg"),
            self.paper_space_widget.fit_sheet)
        _btn.setToolTip("Zoom to fit the whole sheet")

        # --- Annotate (model + sheet) ---
        g_annotate = draft_page.add_group("Annotate")
        _mode_btn(g_annotate, "Dimension", _I("dimension_icon.svg"), "dimension").setToolTip("Place a dimension annotation")
        _mode_btn(g_annotate, "Text", _I("text_icon.svg"), "text").setToolTip("Place a text note")
        self._add_text_ribbon_btn = g_annotate.add_large_button(
            "Add\nText", _I("text_icon.svg"),
            self._on_ribbon_add_text_toggled, checkable=True)
        self._add_text_ribbon_btn.setToolTip(
            "Place a text annotation on the sheet")

        # --- Font (Word-style, sheet text) ---
        from firepro3d.font_group import FontGroupController
        g_font = draft_page.add_group("Font")
        self.font_group = FontGroupController(
            get_targets=self._font_group_targets, parent=self)
        g_font.add_widget(self.font_group.container)
        self.font_group.set_enabled(False)

        # --- Plot ---
        g_plot = draft_page.add_group("Plot")
        _btn = g_plot.add_large_button(
            "Export\nPDF",
            _I("placeholder_icon.svg"),
            self._export_paper_pdf)
        _btn.setToolTip("Export the current sheet to a vector PDF")
        _btn = g_plot.add_large_button(
            "Print",
            _I("placeholder_icon.svg"),
            self._print_paper)
        _btn.setToolTip("Print the current sheet")

    # ── Paper-space plot (PDF export / print) ─────────────────────────────────

    def _export_paper_pdf(self):
        """Export selected sheets to PDF (batch — spec §19.6)."""
        from PyQt6.QtWidgets import QDialog, QMessageBox
        from firepro3d import paper_export
        from firepro3d.paper_export_dialog import PaperExportDialog

        dlg = PaperExportDialog(self.sheet_mgr.sheets, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        sel = dlg.selection()
        tmpl, proj_info = self._current_template()
        if sel.separate_files:
            existing = [paper_export.default_pdf_filename(s)
                        for s in sel.sheets
                        if os.path.exists(os.path.join(
                            sel.path, paper_export.default_pdf_filename(s)))]
            if existing:
                resp = QMessageBox.question(
                    self, "Overwrite Files?",
                    f"{len(existing)} file(s) already exist and will be "
                    "overwritten:\n" + "\n".join(existing[:8])
                    + ("\n…" if len(existing) > 8 else ""),
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if resp != QMessageBox.StandardButton.Yes:
                    return
            for sheet in sel.sheets:
                fname = paper_export.default_pdf_filename(sheet)
                out = os.path.join(sel.path, fname)
                try:
                    paper_export.export_pdf(
                        [sheet], self._view_resolver, out, sel.dpi,
                        template=tmpl, project_info=proj_info)
                except (OSError, ValueError) as exc:
                    QMessageBox.critical(
                        self, "Export Failed",
                        f"Could not write {fname}:\n{exc}\n"
                        "Files exported before this one remain on disk.")
                    return
            done = f"Exported {len(sel.sheets)} PDF file(s)"
        else:
            path = sel.path
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            try:
                paper_export.export_pdf(
                    sel.sheets, self._view_resolver, path, sel.dpi,
                    template=tmpl, project_info=proj_info)
            except (OSError, ValueError) as exc:
                QMessageBox.critical(
                    self, "Export Failed",
                    f"Could not write {os.path.basename(path)}:\n{exc}")
                return
            done = f"Exported {os.path.basename(path)}"
        self.statusBar().showMessage(done, 5000)

    def _print_paper(self):
        """Print selected sheets via the system print dialog (batch)."""
        from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
        from PyQt6.QtWidgets import QDialog, QMessageBox
        from firepro3d import paper_export
        from firepro3d.paper_export_dialog import PaperExportDialog

        dlg = PaperExportDialog(self.sheet_mgr.sheets, self, print_mode=True)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        sel = dlg.selection()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        pdlg = QPrintDialog(printer, self)
        if pdlg.exec() != QPrintDialog.DialogCode.Accepted:
            return
        tmpl, proj_info = self._current_template()
        try:
            paper_export.print_sheets(sel.sheets, self._view_resolver, printer,
                                      template=tmpl, project_info=proj_info)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Print Failed", str(exc))
            return
        self.statusBar().showMessage("Sent to printer", 5000)

    # ── Title Block editor entry point ────────────────────────────────────────

    def _open_titleblock_editor(self) -> None:
        """Open the template editor; apply 'Use for this project' on accept.

        DD-2: when a template is applied (accepted + project_template_result set),
        the sheet's paper_size and orientation are updated to match the template
        BEFORE the push so PaperScene rebuilds at the correct dimensions.

        Orientation storage convention: "" means native (PAPER_SIZES dims unchanged),
        so only non-native orientations are stored as "portrait"/"landscape".
        Sheet.to_dict() always serialises the orientation field, so "" preserves
        the rendering semantics (native dims) without needing a non-empty value.
        """
        from firepro3d.titleblock_editor import TitleBlockEditorDialog
        from firepro3d.titleblock_template import TitleBlockTemplate
        import logging
        raw = getattr(self.scene, "_titleblock_template", None)
        try:
            current = TitleBlockTemplate.from_dict(raw) if raw else None
        except Exception:
            logging.getLogger(__name__).warning(
                "Embedded title block template unreadable — proceeding with None")
            current = None
        dlg = TitleBlockEditorDialog(
            current, parent=self,
            project_info=getattr(self.scene, "_project_info", {}))
        dlg.templateSaved.connect(self._on_titleblock_saved_live)
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        result = dlg.project_template_result
        # A saved use-intent survives Close (grill 2026-08-04 follow-up):
        # Use-for-project + Save writes the library AND captures the saved
        # copy; rejecting afterwards discards only post-save edits.
        if result is not None and (accepted or dlg.result_saved):
            self._apply_titleblock_template(result)

    def _apply_paper_size_result(self, result) -> None:
        """Apply paper size + orientation from *result* to ALL sheets (spec §19.1).

        Computes the stored orientation using the same native-orientation logic
        as ``_apply_titleblock_template``: "" for the native orientation, the
        explicit string otherwise.  Delegates to ``SheetManager.set_paper_all``
        so every sheet in the project gets the uniform size.

        Args:
            result: Any object with ``paper_size`` (str) and ``orientation``
                (str, e.g. "portrait"/"landscape") attributes.
        """
        nat = native_orientation_from_dims(result.paper_size)
        stored_orientation = ("" if result.orientation == nat
                              else result.orientation)
        self.sheet_mgr.set_paper_all(result.paper_size, stored_orientation)

    def _apply_titleblock_template(self, result) -> None:
        """Apply *result* as the project template (DD-2: template drives sheet).

        Extracted from _open_titleblock_editor so the mid-session Save path
        (templateSaved) and the accept path share one implementation.

        DD-2: template drives sheet — update size/orientation BEFORE push.
        Direct assignment bypasses PaperScene.paper_size setter intentionally:
        the setter would call _setup() at pre-template state, but the push
        immediately below rebuilds the scene with the new template applied.
        May run twice on Save & Close (live-refresh then accept-path); must
        stay idempotent.
        """
        # Apply size + orientation to ALL sheets (spec §19.1 uniform-size rule).
        self._apply_paper_size_result(result)
        self.scene._titleblock_template = result.to_dict()
        self._push_titleblock_template()
        self._on_paper_modified()          # project dirty (§17.7)
        # Fit the view after the template (possibly a different paper size)
        # has been applied — mirrors the ribbon's change_paper() + _fit() path.
        self.paper_space_widget.fit_sheet()

    def _on_titleblock_saved_live(self, tmpl) -> None:
        """Mid-session Save: refresh the project iff it uses this template.

        uuid match against the embedded template — a Save of an unrelated
        library template must not touch the project (grill 2026-08-04 item 1).
        isinstance guard: a hand-corrupted .fpd can hold a non-dict embed,
        and this runs in a Qt signal handler where an AttributeError would
        be a silent qFatal (same guard as _current_template /
        _push_titleblock_template).
        """
        raw = getattr(self.scene, "_titleblock_template", None)
        if isinstance(raw, dict) and raw.get("uuid") == tmpl.uuid:
            self._apply_titleblock_template(tmpl)

    def _current_template(self):
        """Return the parsed TitleBlockTemplate embedded in the scene, or None.

        Applies the same corrupt-guard as ``_push_titleblock_template``.
        Returns ``(template_or_None, project_info_dict)`` so callers can
        forward both to ``export_pdf`` / ``print_sheets``.
        """
        import logging
        from firepro3d.titleblock_template import TitleBlockTemplate
        raw = getattr(self.scene, "_titleblock_template", None)
        try:
            t = TitleBlockTemplate.from_dict(raw) if raw else None
        except Exception:
            logging.getLogger(__name__).warning(
                "Embedded title block template unreadable — treating as None.")
            t = None
        return t, getattr(self.scene, "_project_info", {})

    def _push_titleblock_template(self) -> None:
        """Install the scene's embedded template into the live PaperScene.

        Passes the CURRENT Model_Space._project_info dict by reference; callers
        must re-push whenever _project_info is REPLACED (e.g. Project Info dialog
        replaces the entire dict — see _open_project_info).
        """
        t, project_info = self._current_template()
        if t is None:
            # Warn only when a raw dict was present but un-parseable; otherwise
            # None is expected (no template assigned yet).
            raw = getattr(self.scene, "_titleblock_template", None)
            if raw is not None:
                import logging
                logging.getLogger(__name__).warning(
                    "Embedded title block template unreadable — using built-in title block.")
                self.statusBar().showMessage(
                    "Embedded title block template unreadable — using built-in title block.",
                    8000)
        ps = self.paper_space_widget.paper_scene
        ps.set_template(t, project_info=project_info)
        if ps.titleblock_warning:
            self.statusBar().showMessage(ps.titleblock_warning, 8000)

    def _maybe_offer_template_push(self) -> None:
        """Show the library-divergence notice (three-way: Push / Pull / Keep Both).

        Per spec DD-5:
          Yes   → Push to Library: write the embedded copy over the library copy.
          No    → Pull from Library: replace the embedded copy with the library copy
                  and dirty the project (pulling changes the project bytes, §17.7).
          Cancel → Keep Both: no-op (the project renders from its embedded copy).

        Factored out of _apply_loaded_file so tests can monkeypatch it
        (the modal QMessageBox would hang headless test runs).  When there
        is no embedded template, or the library copy matches, this is a no-op.
        """
        from firepro3d.titleblock_template import (
            TitleBlockTemplate, library_diverges, save_to_library, load_library,
        )
        raw = getattr(self.scene, "_titleblock_template", None)
        if not raw:
            return
        try:
            embedded = TitleBlockTemplate.from_dict(raw)
            diverges = library_diverges(embedded)
        except Exception:
            return
        if not diverges:
            return
        resp = QMessageBox.question(
            self, "Title Block Template",
            f"The library copy of '{embedded.name}' differs from this "
            "project's embedded copy.\n\n"
            "Yes = Push to Library (overwrite library with project version)\n"
            "No  = Pull from Library (replace project copy with library version)\n"
            "Cancel = Keep Both (project continues to render its own embedded copy)",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if resp == QMessageBox.StandardButton.Yes:
            # Push: write embedded copy to library.
            save_to_library(embedded)
        elif resp == QMessageBox.StandardButton.No:
            # Pull: find the library copy and install it as the embedded template.
            lib_copies = [t for t in load_library() if t.uuid == embedded.uuid]
            if lib_copies:
                self.scene._titleblock_template = lib_copies[0].to_dict()
                self._push_titleblock_template()
                self._on_paper_modified()   # pulling changes project bytes → dirty (§17.7)

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
            ("Project Name",           "name"),
            ("Project Number",         "number"),
            ("Address Line 1",         "address1"),
            ("Address Line 2",         "address2"),
            ("Address Line 3",         "address3"),
            ("Client",                 "client"),
            ("Client Address Line 1",  "client_address1"),
            ("Client Address Line 2",  "client_address2"),
            ("Client Address Line 3",  "client_address3"),
            ("Designer",               "designer"),
            ("Description",            "description"),
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
            # _project_info dict was REPLACED (not mutated) — re-push so the paper
            # scene renders with the new dict reference (set_template stores it by
            # value; stale reference would show old project data).
            self._push_titleblock_template()

    # ── Unified Preferences dialog ────────────────────────────────────────────

    def _get_project_info(self) -> dict:
        """Return a shallow copy of the current project-info dict.

        Used as the ``get_info`` callback for ``ProjectInfoPane``.
        """
        return dict(getattr(self.scene, "_project_info", {}) or {})

    def _set_project_info(self, edited: dict) -> None:
        """Replace ``scene._project_info`` and re-push the titleblock template.

        Used as the ``set_info`` callback for ``ProjectInfoPane``.  Mirrors
        what ``_open_project_info`` does on OK: replace the dict reference
        (so ``_push_titleblock_template`` picks up the new values) then push.

        Args:
            edited: The updated project-info dict from ``ProjectInfoPane.apply()``.
        """
        self.scene._project_info = edited
        self._push_titleblock_template()

    def _build_preferences_dialog(self):
        """Construct a ``PreferencesDialog`` with all 5 panes wired to live targets.

        This is a factory (non-exec); call ``dlg.exec()`` yourself — or use
        ``_open_preferences()`` for the normal open-and-block path.

        Returns:
            A fully wired :class:`~firepro3d.preferences_dialog.PreferencesDialog`.
        """
        from firepro3d.preferences_dialog import (
            PreferencesDialog,
            SnappingPane,
            UnitsPane,
            ImportPane,
            GeneralPane,
            ProjectInfoPane,
        )
        panes = [
            SnappingPane(
                scene=getattr(self, "scene", None),
                view=getattr(self, "view", None),
                snap_toolbar=getattr(self, "snap_toolbar", None),
            ),
            UnitsPane(
                scale_manager=getattr(getattr(self, "scene", None), "scale_manager", None),
                on_changed=getattr(self, "scene", None) and self.scene._refresh_all_labels,
            ),
            ImportPane(),
            GeneralPane(),
            ProjectInfoPane(
                get_info=self._get_project_info,
                set_info=self._set_project_info,
            ),
        ]
        return PreferencesDialog(panes, parent=self)

    def _open_preferences(self) -> None:
        """Open the unified Preferences dialog and block until closed."""
        self._build_preferences_dialog().exec()

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

    def _open_snap_tolerance_dialog(self, modal: bool = True):
        """Live-adjustable snap settings dialog with per-type toggles.

        Args:
            modal: When True (default), shows the dialog via exec() and blocks.
                When False, builds and returns the dialog without calling exec()
                (test seam — mirrors how other dialogs expose a non-modal path).

        Returns:
            The QDialog instance (always).  In modal mode the dialog has
            already been exec()'d and closed before the return.
        """
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout,
                                      QDialogButtonBox, QGroupBox, QCheckBox,
                                      QTabWidget, QWidget, QLabel)
        from firepro3d import snap_engine

        eng = self.scene._snap_engine

        dlg = QDialog(self)
        dlg.setWindowTitle("Snap Settings")
        dlg.setMinimumWidth(340)
        outer = QVBoxLayout(dlg)

        tabs = QTabWidget()
        outer.addWidget(tabs)

        # ── Tab 1: SNAP ──────────────────────────────────────────────
        snap_tab = QWidget()
        snap_layout = QVBoxLayout(snap_tab)

        # Tolerance
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
        snap_layout.addWidget(tol_group)

        # Snap types
        types_group = QGroupBox("Snap Types")
        types_layout = QVBoxLayout(types_group)

        snap_types = [
            ("Endpoint",      "snap_endpoint"),
            ("Midpoint",      "snap_midpoint"),
            ("Intersection",  "snap_intersection"),
            ("Center",        "snap_center"),
            ("Quadrant",      "snap_quadrant"),
            ("Nearest",       "snap_nearest"),
            ("Perpendicular", "snap_perpendicular"),
            ("Tangent",       "snap_tangent"),
        ]

        checkboxes: list[tuple[QCheckBox, str]] = []
        for label, attr in snap_types:
            cb = QCheckBox(label)
            cb.setChecked(getattr(eng, attr, True))
            cb.toggled.connect(
                lambda v, a=attr: setattr(eng, a, v))  # a=attr captures per-iter
            types_layout.addWidget(cb)
            checkboxes.append((cb, attr))

        snap_layout.addWidget(types_group)
        tabs.addTab(snap_tab, "SNAP")

        # ── Tab 2: ALIGN ─────────────────────────────────────────────
        inf_tab = QWidget()
        inf_layout = QVBoxLayout(inf_tab)

        align_cb = QCheckBox("ALIGN")
        align_cb.setObjectName("align_enabled")
        align_cb.setChecked(self.scene._align_enabled)
        align_cb.toggled.connect(
            lambda checked: (
                self.scene.set_align_enabled(checked),
                QSettings().setValue("align/enabled", checked),
            )
        )
        inf_layout.addWidget(align_cb)

        coming_soon_group = QGroupBox("Dynamic Input · Equal Spacing")
        coming_soon_group.setEnabled(False)
        cs_layout = QVBoxLayout(coming_soon_group)
        cs_label = QLabel("Coming soon")
        cs_label.setStyleSheet("color: #888;")
        cs_layout.addWidget(cs_label)
        inf_layout.addWidget(coming_soon_group)
        inf_layout.addStretch()

        tabs.addTab(inf_tab, "ALIGN")

        # ── Buttons ──────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        outer.addWidget(buttons)

        if not modal:
            return dlg

        # Snapshot for cancel
        old_tol = snap_engine.SNAP_TOLERANCE_PX
        old_grip = getattr(self.scene, "_grip_tolerance_px", 200)
        old_flags = {attr: getattr(eng, attr) for _, attr in checkboxes}
        old_align_enabled = self.scene._align_enabled

        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Persist SNAP settings
            self.settings.setValue("snap/tolerance_px", snap_engine.SNAP_TOLERANCE_PX)
            self.settings.setValue("snap/grip_tolerance_px",
                                  getattr(self.scene, "_grip_tolerance_px", 200))
            for _, attr in checkboxes:
                self.settings.setValue(f"snap/{attr}", getattr(eng, attr))
            # ALIGN setting already saved live via the checkbox toggled signal
        else:
            # Revert SNAP
            snap_engine.SNAP_TOLERANCE_PX = old_tol
            self.scene._grip_tolerance_px = old_grip
            for attr, val in old_flags.items():
                setattr(eng, attr, val)
            # Revert ALIGN
            self.scene.set_align_enabled(old_align_enabled)
            QSettings().setValue("align/enabled", old_align_enabled)

        # Keep the SNAP toolbar in sync with whatever the dialog left set.
        self.snap_toolbar.refresh_from_engine()
        return dlg

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
                        lambda _, n=name: self._change_paper_with_warning(n))
        return m

    def _change_paper_with_warning(self, size: str) -> None:
        """Change the paper size and surface any template-mismatch warning.

        After ``change_paper`` the PaperScene rebuilds (_setup runs) and sets
        ``titleblock_warning`` when the active template no longer matches the
        new sheet size.  This method reads that warning and shows it in the
        status bar — mirroring the ``_push_titleblock_template`` pattern.

        Edge case — same-size ribbon press with a stored orientation override:
        The ``PaperScene.paper_size`` setter no-ops when size == active
        sheet.paper_size, so it neither clears the orientation override nor
        rebuilds the scene.  ``set_paper_all(size, "")`` then writes
        ``orientation=""`` into the active sheet's DATA only — the rendered
        page keeps the old orientation until a sheet switch.  We detect this by
        comparing the scene's rendered paper rect (_bg_item) against
        sheet_page_mm after set_paper_all runs; a mismatch means the setter
        skipped the rebuild, so we call _setup() + fit_sheet() directly (the
        same actions the setter takes on a real size change).  We deliberately
        do NOT call set_sheet/update_from_sheet because those clear the paper
        undo stack — §17.5 preserves the stack on the size-change path.
        """
        self.paper_space_widget.change_paper(size)
        # Propagate to all other sheets (spec §19.1 uniform-size rule).
        # change_paper() resets the active sheet's orientation to "" (native);
        # set_paper_all syncs every other sheet to the same size + "" orientation.
        # Even when the active-sheet setter no-ops (size unchanged), non-active
        # sheets may still be mutated — dirty the project in that case (§19.3).
        if self.sheet_mgr.set_paper_all(size, ""):
            self._on_paper_modified()
        sc = self.paper_space_widget.paper_scene
        # Force a scene rebuild when set_paper_all changed the active sheet's
        # orientation without the setter having done so (same-size no-op path).
        w_mm, h_mm = sheet_page_mm(self._sheet)
        bg = sc._bg_item
        if bg is not None and (
            abs(bg.rect().width() - w_mm) > 0.05
            or abs(bg.rect().height() - h_mm) > 0.05
        ):
            sc._setup()
            self.paper_space_widget.fit_sheet()
        if sc.titleblock_warning:
            self.statusBar().showMessage(sc.titleblock_warning, 8000)

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

    def _on_mode_changed_template(self, mode: str):
        """Show pre-placement template properties when entering wall/floor/geometry mode."""
        if mode == "wall":
            template = self.scene._get_wall_template()
            template._alignment = self.scene._wall_alignment
            self.prop_manager.show_properties(template)
        elif mode in ("floor", "floor_rect"):
            template = self.scene._get_floor_template()
            self.prop_manager.show_properties(template)
        elif mode in ("roof", "roof_rect"):
            template = self.scene._get_roof_template()
            self.prop_manager.show_properties(template)
        elif mode in ("draw_line", "draw_rectangle",
                       "draw_circle", "draw_arc", "polyline"):
            template = self.scene._get_geometry_template()
            self.prop_manager.show_properties(template)
        else:
            # Exiting a template mode — clear stale template properties
            self.prop_manager.show_properties(None)

    # ── SNAP toggle (Sprint H) ────────────────────────────────────────────────

    def _toggle_snap(self, checked: bool):
        """Called when the SNAP ribbon button is toggled (or F3 pressed)."""
        self.scene.toggle_snap(checked)

    def _toggle_snap_bar(self, checked: bool):
        """Show/hide the SNAP snap-type toolbar (hidden by default)."""
        self.snap_toolbar.setVisible(checked)

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

    def _update_snap_indicator(self, enabled: bool) -> None:
        self.snap_indicator.setSnapOn(enabled)
        # Keep the ribbon SNAP button in sync with external toggles (pill /
        # F3) without re-entering _toggle_snap. Guarded: this runs once during
        # __init__ before init_ribbon() creates the button.
        btn = getattr(self, "_snap_btn", None)
        if btn is not None:
            btn.blockSignals(True)
            btn.setChecked(enabled)
            btn.blockSignals(False)

    def _update_guides_indicator(self, enabled: bool) -> None:
        """Restyle the ALIGN status-bar pill. Mirrors _update_snap_indicator."""
        self.guides_indicator.setGuidesOn(enabled)

    def _update_node_snap_readout(self, text: str):
        """Update the pipe-mode node snap readout in the status bar."""
        if text:
            self.node_snap_label.setText(text)
            self.node_snap_label.show()
        else:
            self.node_snap_label.hide()

    def _update_mode_label(self, mode: str):
        text = self._MODE_INSTRUCTIONS.get(mode, mode.replace("_", " ").title())
        self.mode_label.setText(text)
        # Update prominent mode name badge
        pretty = mode.replace("_", " ").title() if mode else "Select"
        self.mode_name_label.setText(pretty)

    def _last_feature_for(self, type_: str) -> str:
        """Return the last-used Feature id for *type_*, falling back to the default.

        Args:
            type_: Opening type key — ``"door"``, ``"window"``, or ``"blank"``.

        Returns:
            A Feature id string (e.g. ``"door_914"``).
        """
        return self._last_feature.get(type_, DEFAULT_FEATURE_FOR_TYPE[type_])

    def _enter_opening_mode(self, type_: str) -> None:
        """Enter opening placement carrying the persistent template (§7.6).

        Applies the last-used feature for *type_* to
        ``self.current_opening_template`` (only when the feature actually
        changes, so a user's pre-placement Sill/size edits survive a re-click of
        the same button), then enters "opening" mode with the template object so
        the property panel surfaces it for pre-placement editing.

        Args:
            type_: Opening type key — ``"door"``, ``"window"``, or ``"blank"``.
        """
        feature_id = self._last_feature_for(type_)
        tmpl = self.current_opening_template
        if tmpl.feature_id != feature_id:
            tmpl.apply_feature(feature_id)
        self.scene.set_mode("opening", template=tmpl)

    def _on_feature_activated(self, feature_id: str) -> None:
        """Handle a leaf activation from the Feature Browser (§7.13).

        Args:
            feature_id: The FeatureDef.id emitted by FeatureBrowser.featureActivated.
        """
        from firepro3d.feature import get_feature
        try:
            fdef = get_feature(feature_id)
        except KeyError:
            return
        self._last_feature[fdef.type] = feature_id
        tmpl = self.current_opening_template
        if tmpl.feature_id != feature_id:
            tmpl.apply_feature(feature_id)
        self.scene.set_mode("opening", template=tmpl)

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

    # ── Contextual tab catalog + shared Edit group ─────────────────────────

    # ── Geo2D contextual builders ──────────────────────────────────────────────

    def _build_geo2d_context(self, page) -> None:
        """Build the '2D Geometry' contextual tab: Placement + Fill + Edit.

        Args:
            page: :class:`~firepro3d.ribbon_bar.RibbonPage` to populate.
        """
        self._build_placement_group(page)
        self._build_fill_group(page)
        self._build_contextual_edit_group(page)

    def _build_opening_context(self, page) -> None:
        """Build the 'Opening' contextual tab: Placement + Orientation + Edit.

        Groups:
            Placement  — Level combo (reused from :meth:`_build_placement_group`).
            Orientation — Alignment combo, Flip Hinge button, Flip Facing button.
            Edit        — Standard clipboard/delete actions.

        Args:
            page: :class:`~firepro3d.ribbon_bar.RibbonPage` to populate.
        """
        from PyQt6.QtWidgets import QComboBox, QLabel, QWidget, QVBoxLayout
        from firepro3d.constants import OPENING_ALIGNMENTS
        from firepro3d.wall_opening import WallOpening
        from firepro3d.icons import themed_icon, LIGHT, DARK
        from firepro3d import theme as _th
        _theme = DARK if _th.detect().name == DARK else LIGHT
        _I = lambda name: themed_icon(name, _theme)

        self._build_placement_group(page)

        # ── Orientation group ─────────────────────────────────────────────────
        g = page.add_group("Orientation")

        # Alignment combo
        align_container = QWidget()
        al_lay = QVBoxLayout(align_container)
        al_lay.setContentsMargins(2, 2, 2, 0)
        al_lay.setSpacing(1)
        lbl_al = QLabel("Alignment")
        lbl_al.setMaximumWidth(110)
        align_combo = QComboBox()
        align_combo.setMaximumWidth(110)
        align_combo.addItems(list(OPENING_ALIGNMENTS))
        al_lay.addWidget(lbl_al)
        al_lay.addWidget(align_combo)

        # Seed combo from current selection
        _openings = [it for it in self.scene.selectedItems()
                     if isinstance(it, WallOpening)]
        if _openings:
            vals = {it.alignment for it in _openings}
            cur = next(iter(vals)) if len(vals) == 1 else None
            align_combo.blockSignals(True)
            if cur is not None and align_combo.findText(cur) >= 0:
                align_combo.setCurrentText(cur)
            else:
                align_combo.setCurrentIndex(-1)
            align_combo.blockSignals(False)

        def _on_alignment_changed(index):
            new_val = align_combo.currentText()
            targets = [it for it in self.scene.selectedItems()
                       if isinstance(it, WallOpening)
                       and it.alignment != new_val]
            if not targets:
                return
            self.scene.push_undo_state()
            for t in targets:
                t.set_property("Alignment", new_val)

        align_combo.activated.connect(_on_alignment_changed)
        g.add_widget(align_container)

        # Flip Hinge button
        g.add_small_button(
            "Flip Hinge", None,
            lambda: self._opening_flip("Hinge Flip"),
        )
        # Flip Facing button
        g.add_small_button(
            "Flip Facing", None,
            lambda: self._opening_flip("Facing Flip"),
        )

        self._build_contextual_edit_group(page)

    def _opening_flip(self, prop_key: str) -> None:
        """Toggle a bool property on all selected WallOpenings with undo snapshot.

        Args:
            prop_key: ``"Hinge Flip"`` or ``"Facing Flip"``.
        """
        from firepro3d.wall_opening import WallOpening
        targets = [it for it in self.scene.selectedItems()
                   if isinstance(it, WallOpening)]
        if not targets:
            return
        self.scene.push_undo_state()
        for t in targets:
            current = getattr(t, "mirror_hinge" if prop_key == "Hinge Flip"
                              else "mirror_facing", False)
            t.set_property(prop_key, not current)

    def _build_placement_group(self, page) -> None:
        """Add a 'Placement' group (Level combo + Level Offset field) to *page*.

        Writes are routed through ``item.set_property()`` then
        ``scene.push_undo_state()``.  A no-op gesture (value unchanged)
        does NOT push an undo step.

        Args:
            page: :class:`~firepro3d.ribbon_bar.RibbonPage` to populate.
        """
        from PyQt6.QtWidgets import QComboBox, QLabel, QWidget, QVBoxLayout
        from firepro3d.dimension_edit import DimensionEdit

        g = page.add_group("Placement")

        # ── Level combo ────────────────────────────────────────────────────────
        level_container = QWidget()
        lvl_lay = QVBoxLayout(level_container)
        lvl_lay.setContentsMargins(2, 2, 2, 0)
        lvl_lay.setSpacing(1)
        lbl_lvl = QLabel("Level")
        lbl_lvl.setMaximumWidth(110)
        level_combo = QComboBox()
        level_combo.setMaximumWidth(110)
        lvl_lay.addWidget(lbl_lvl)
        lvl_lay.addWidget(level_combo)

        def _refresh_level_combo():
            lm = getattr(self.scene, "_level_manager", None)
            current_names = [level_combo.itemText(i) for i in range(level_combo.count())]
            new_names = [lvl.name for lvl in lm.levels] if lm else ["Level 1"]
            if new_names != current_names:
                level_combo.blockSignals(True)
                level_combo.clear()
                level_combo.addItems(new_names)
                level_combo.blockSignals(False)
            # Reflect selection
            items = self.scene.selectedItems()
            geo = [it for it in items if hasattr(it, "level")]
            if geo:
                vals = {it.level for it in geo}
                lvl_val = next(iter(vals)) if len(vals) == 1 else None
                level_combo.blockSignals(True)
                if lvl_val is not None and level_combo.findText(lvl_val) >= 0:
                    level_combo.setCurrentText(lvl_val)
                else:
                    level_combo.setCurrentIndex(-1)
                level_combo.blockSignals(False)

        _refresh_level_combo()

        def _on_level_changed(index):
            new_val = level_combo.currentText()
            targets = [it for it in self.scene.selectedItems()
                       if hasattr(it, "set_property")]
            apply = [t for t in targets if getattr(t, "level", None) != new_val]
            if not apply:
                return
            self.scene.push_undo_state()
            for t in apply:
                t.set_property("Level", new_val)

        level_combo.activated.connect(_on_level_changed)
        g.add_widget(level_container)

        # ── Level Offset field ─────────────────────────────────────────────────
        offset_container = QWidget()
        off_lay = QVBoxLayout(offset_container)
        off_lay.setContentsMargins(2, 2, 2, 0)
        off_lay.setSpacing(1)
        lbl_off = QLabel("Level Offset")
        lbl_off.setMaximumWidth(110)
        sm = getattr(self.scene, "scale_manager", None)
        offset_edit = DimensionEdit(sm, initial_mm=0.0)
        offset_edit.setMaximumWidth(110)
        offset_edit.setToolTip("Vertical offset from floor-level elevation (mm)")
        off_lay.addWidget(lbl_off)
        off_lay.addWidget(offset_edit)

        # Seed with current selection value
        items = self.scene.selectedItems()
        geo = [it for it in items if hasattr(it, "_level_offset_mm")]
        if geo:
            vals = {it._level_offset_mm for it in geo}
            if len(vals) == 1:
                offset_edit.set_value_mm(next(iter(vals)))

        def _on_offset_committed(new_mm: float):
            targets = [it for it in self.scene.selectedItems()
                       if hasattr(it, "set_property")
                       and hasattr(it, "_level_offset_mm")]
            apply = [t for t in targets
                     if abs(t._level_offset_mm - new_mm) > 1e-6]
            if not apply:
                return
            self.scene.push_undo_state()
            for t in apply:
                t.set_property("Level Offset", new_mm)

        offset_edit.valueChanged.connect(_on_offset_committed)
        g.add_widget(offset_container)

    def _build_fill_group(self, page) -> None:
        """Add a 'Fill' group (Fill type + Pattern + Colour + Opacity) to *page*.

        The group is enabled only when ≥1 selected item returns True for
        ``is_fillable()``.  All writes route through ``set_property()`` +
        ``push_undo_state()``.  No-op gestures push NO undo step.

        Args:
            page: :class:`~firepro3d.ribbon_bar.RibbonPage` to populate.
        """
        from PyQt6.QtWidgets import (
            QComboBox, QLabel, QToolButton, QLineEdit,
            QWidget, QVBoxLayout, QHBoxLayout,
        )
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QColorDialog
        from firepro3d import theme as _th
        from firepro3d.hatch_patterns import PATTERN_NAMES

        _syncing_fill = [False]  # mutable flag inside closures

        g = page.add_group("Fill")

        # ── Row 1: Fill type + Pattern ─────────────────────────────────────────
        row1 = QWidget()
        r1_lay = QHBoxLayout(row1)
        r1_lay.setContentsMargins(2, 2, 2, 0)
        r1_lay.setSpacing(4)

        fill_combo = QComboBox()
        fill_combo.addItems(["none", "solid", "hatch"])
        fill_combo.setMaximumWidth(70)
        fill_combo.setToolTip("Fill type")

        pattern_combo = QComboBox()
        pattern_combo.addItems(list(PATTERN_NAMES))
        pattern_combo.setMaximumWidth(90)
        pattern_combo.setToolTip("Hatch pattern")

        r1_lay.addWidget(QLabel("Fill:"))
        r1_lay.addWidget(fill_combo)
        r1_lay.addWidget(QLabel("Pat:"))
        r1_lay.addWidget(pattern_combo)

        # ── Row 2: Colour swatch + Opacity ────────────────────────────────────
        row2 = QWidget()
        r2_lay = QHBoxLayout(row2)
        r2_lay.setContentsMargins(2, 0, 2, 2)
        r2_lay.setSpacing(4)

        t = _th.detect()
        color_btn = QToolButton()
        color_btn.setToolTip("Fill colour")
        color_btn.setFixedSize(28, 26)
        color_btn.setStyleSheet(
            f"QToolButton {{ border: 1px solid {t.border_strong}; background: #888888; }}"
            f"QToolButton:hover {{ border-color: {t.accent_primary}; }}")
        _fill_swatch = ["#888888"]  # store last colour

        opacity_edit = QLineEdit("45")
        opacity_edit.setMaximumWidth(40)
        opacity_edit.setToolTip("Fill opacity 0–100 %")
        r2_lay.addWidget(QLabel("Col:"))
        r2_lay.addWidget(color_btn)
        r2_lay.addWidget(QLabel("Opa%:"))
        r2_lay.addWidget(opacity_edit)

        # Pack both rows into the group
        outer = QWidget()
        out_lay = QVBoxLayout(outer)
        out_lay.setContentsMargins(0, 0, 0, 0)
        out_lay.setSpacing(2)
        out_lay.addWidget(row1)
        out_lay.addWidget(row2)
        g.add_widget(outer)

        # ── Helpers ────────────────────────────────────────────────────────────

        def _fillable_targets():
            return [it for it in self.scene.selectedItems()
                    if callable(getattr(it, "is_fillable", None))
                    and it.is_fillable()
                    and hasattr(it, "set_property")]

        def _set_swatch(hex_color: str):
            _fill_swatch[0] = hex_color
            t2 = _th.detect()
            color_btn.setStyleSheet(
                f"QToolButton {{ border: 1px solid {t2.border_strong}; "
                f"background: {hex_color}; }}"
                f"QToolButton:hover {{ border-color: {t2.accent_primary}; }}")

        def _sync_fill_group():
            """Reflect current selection state into fill widgets."""
            _syncing_fill[0] = True
            try:
                targets = _fillable_targets()
                has_fill = bool(targets)
                g.setEnabled(has_fill)
                if not has_fill:
                    return

                def uniform(getter):
                    vals = {getter(it) for it in targets}
                    return vals.pop() if len(vals) == 1 else None

                ft = uniform(lambda it: it.fill_type)
                fill_combo.setCurrentText(ft if ft is not None else "")

                pat = uniform(lambda it: it.fill_pattern)
                pattern_combo.setCurrentText(pat if pat is not None else "")

                col = uniform(lambda it: getattr(it, "_display_fill_color", None) or "#888888")
                if col:
                    _set_swatch(col)

                opa = uniform(lambda it: round(it.fill_opacity * 100))
                opacity_edit.setText("" if opa is None else str(opa))
            finally:
                _syncing_fill[0] = False

        # Initial enable/sync
        _sync_fill_group()

        # ── Write handlers ─────────────────────────────────────────────────────

        def _on_fill_type(index):
            if _syncing_fill[0]:
                return
            new_val = fill_combo.currentText()
            targets = _fillable_targets()
            apply = [t for t in targets if t.fill_type != new_val]
            if not apply:
                _sync_fill_group()
                return
            self.scene.push_undo_state()
            for t in apply:
                t.set_property("Fill", new_val)
            _sync_fill_group()

        def _on_pattern(index):
            if _syncing_fill[0]:
                return
            new_val = pattern_combo.currentText()
            targets = _fillable_targets()
            apply = [t for t in targets if t.fill_pattern != new_val]
            if not apply:
                return
            self.scene.push_undo_state()
            for t in apply:
                t.set_property("Pattern", new_val)

        def _on_colour():
            targets = _fillable_targets()
            if not targets:
                return
            existing = (
                getattr(targets[0], "_display_fill_color", None) or "#888888"
            )
            c = QColorDialog.getColor(QColor(existing), page, "Fill Colour")
            if c.isValid():
                hex_val = c.name()
                apply = [t for t in targets
                         if (getattr(t, "_display_fill_color", None) or "#888888")
                         != hex_val]
                if not apply:
                    return
                self.scene.push_undo_state()
                for t in apply:
                    t.set_property("Fill Colour", hex_val)
                _set_swatch(hex_val)

        def _on_opacity():
            if _syncing_fill[0]:
                return
            try:
                pct = float(opacity_edit.text())
            except (ValueError, TypeError):
                return
            pct = max(0.0, min(100.0, pct))
            targets = _fillable_targets()
            apply = [t for t in targets
                     if abs(t.fill_opacity * 100 - pct) > 0.5]
            if not apply:
                return
            self.scene.push_undo_state()
            for t in apply:
                t.set_property("Fill Opacity", pct)

        fill_combo.activated.connect(_on_fill_type)
        pattern_combo.activated.connect(_on_pattern)
        color_btn.clicked.connect(_on_colour)
        opacity_edit.editingFinished.connect(_on_opacity)

    def _build_contextual_edit_group(self, page) -> None:
        """Add a shared "Edit" group to *page* with 5 action buttons.

        Every contextual tab calls this method to get the standard clipboard
        and delete actions.  The callbacks are identical to the shortcuts
        wired in ``__init__`` (Delete, Copy, Cut, Paste, Duplicate).

        Args:
            page: A :class:`~firepro3d.ribbon_bar.RibbonPage` to populate.
        """
        from firepro3d.icons import themed_icon, LIGHT, DARK
        from firepro3d import theme as _th
        _theme = DARK if _th.detect().name == DARK else LIGHT
        _I = lambda name: themed_icon(name, _theme)

        g = page.add_group("Edit")
        _btn = g.add_small_button(
            "Delete", _I("delete_icon.svg"),
            lambda: self.scene.delete_selected_items())
        _btn.setToolTip("Delete selected items [Del]")
        _btn = g.add_small_button(
            "Copy", _I("copy_icon.svg"),
            lambda: self.scene.copy_selected_items())
        _btn.setToolTip("Copy selected items [Ctrl+C]")
        _btn = g.add_small_button(
            "Cut", _I("cut_icon.svg"),
            lambda: (self.scene.copy_selected_items(),
                     self.scene.delete_selected_items()))
        _btn.setToolTip("Cut selected items [Ctrl+X]")
        _btn = g.add_small_button(
            "Paste", _I("paste_icon.svg"),
            lambda: self.scene.paste_items())
        _btn.setToolTip("Paste items [Ctrl+V]")
        _btn = g.add_small_button(
            "Duplicate", _I("duplicate_icon.svg"),
            lambda: self.scene.duplicate_selected())
        _btn.setToolTip("Duplicate selected items [Ctrl+D]")

    def _init_contextual_tabs(self) -> None:
        """Build the contextual-tab registry and initialise state variables.

        The registry maps each entity-family key to a ``(tab_title,
        page_builder)`` tuple.  No tab is inserted into the ribbon here —
        insertion is deferred to the C2 task (selection-driven show/hide).

        Post-conditions:
            ``self._contextual_registry`` — catalog of all contextual tabs.
            ``self._contextual_index``    — fixed insert slot (= 7, one past
                                           the last base tab).
            ``self._active_contextual_key`` — ``None`` (no tab shown yet).
            ``self._pre_contextual_tab``    — ``0`` (default saved-tab index).
        """
        self._contextual_registry: dict[str, tuple[str, callable]] = {
            key: (title, self._build_contextual_edit_group)
            for key, title in self._CONTEXTUAL_TABS.items()
        }
        # Override geo2d with its richer builder (Placement + Fill + Edit).
        self._contextual_registry["geo2d"] = (
            self._CONTEXTUAL_TABS["geo2d"],
            self._build_geo2d_context,
        )
        # Override opening with its richer builder (Placement + Orientation + Edit).
        self._contextual_registry["opening"] = (
            self._CONTEXTUAL_TABS["opening"],
            self._build_opening_context,
        )
        # Fixed slot immediately after the 7 base tabs.
        self._contextual_index: int = 7
        # Tracks which contextual family is currently shown (None = hidden).
        self._active_contextual_key: str | None = None
        # Remembers the previously selected base tab so C2 can restore it
        # when the contextual tab is dismissed.
        self._pre_contextual_tab: int = 0

    # ── Contextual tab handler ─────────────────────────────────────────────

    def _family_key_for(self, item) -> "str | None":
        """Map a scene item to its contextual-tab family key.

        Returns the string key used in ``_contextual_registry``, or ``None``
        for items that belong to no contextual family (underlays, badges,
        helper child-items, etc.).

        Subclass-before-base ordering is observed where inheritance exists
        (DoorOpening/WindowOpening before WallOpening; Sprinkler before Node
        is moot since they don't share a base, but the order is kept
        consistent with the taxonomy).
        """
        from firepro3d.construction_geometry import (
            PolylineItem, LineItem,
            RectangleItem, CircleItem, ArcItem,
            RegularPolygonItem,
        )
        from firepro3d.annotations import (
            DimensionAnnotation,
        )
        from firepro3d.wall import WallSegment
        from firepro3d.floor_slab import FloorSlab
        from firepro3d.roof import RoofItem
        from firepro3d.room import Room
        from firepro3d.wall_opening import WallOpening  # covers Door/WindowOpening
        from firepro3d.detail_view import DetailMarker
        from firepro3d.node import Node
        from firepro3d.water_supply import WaterSupply
        from firepro3d.design_area import DesignArea
        from firepro3d.gridline import GridlineItem

        # 2-D geometry family
        if isinstance(item, (PolylineItem, LineItem,
                              RectangleItem, CircleItem, ArcItem,
                              RegularPolygonItem)):
            return "geo2d"
        # Annotation family
        if isinstance(item, (NoteAnnotation, DimensionAnnotation)):
            return "annotation"
        # Structural / architectural families
        if isinstance(item, WallSegment):
            return "wall"
        if isinstance(item, FloorSlab):
            return "floor"
        if isinstance(item, RoofItem):
            return "roof"
        if isinstance(item, Room):
            return "room"
        # WallOpening covers DoorOpening and WindowOpening (both subclass it)
        if isinstance(item, WallOpening):
            return "opening"
        if isinstance(item, DetailMarker):
            return "detail"
        # Fire-protection families — Sprinkler first (doesn't share base with
        # Node, but ordering is explicit for taxonomy clarity)
        if isinstance(item, Sprinkler):
            return "sprinkler"
        # Pipe and Node both fold into the "pipe" context
        if isinstance(item, (Pipe, Node)):
            return "pipe"
        if isinstance(item, WaterSupply):
            return "water_supply"
        if isinstance(item, DesignArea):
            return "design_area"
        if isinstance(item, GridlineItem):
            return "gridline"
        return None

    def _resolve_selection_context(self, items) -> "str | None":
        """Derive the contextual-tab key for a list of selected items.

        Returns:
            ``None``    — nothing selected (or no mappable items).
            A family key — all selected items map to the same family.
            ``"mixed"`` — items span more than one family.
        """
        if not items:
            return None
        keys = {self._family_key_for(it) for it in items}
        keys.discard(None)
        if not keys:
            return None
        return next(iter(keys)) if len(keys) == 1 else "mixed"

    def _on_selection_changed_contextual(self):
        """Show, swap, or hide the contextual ribbon tab on selection change.

        Transitions:
            no-selection / unknown → hide contextual tab, restore saved base tab.
            single-family          → show that family's contextual tab.
            multi-family           → show the "Modify" (``"mixed"``) tab.
            same key as before     → no-op (avoids redundant rebuild).

        The ``_pre_contextual_tab`` index is captured only on the
        None → contextual transition so that contextual → contextual switches
        (e.g. wall → pipe) never overwrite the original base-tab position.
        """
        items = self.scene.selectedItems()
        key = self._resolve_selection_context(items)
        if key == self._active_contextual_key:
            return
        had_contextual = self._active_contextual_key is not None
        if not had_contextual:
            # Remember the base tab that was active before any contextual tab
            self._pre_contextual_tab = self.ribbon._tab_bar.currentIndex()
        if had_contextual:
            self.ribbon.remove_page(self._contextual_index)
            self._active_contextual_key = None
        if key is None:
            self.ribbon._tab_bar.setCurrentIndex(self._pre_contextual_tab)
            return
        entry = self._contextual_registry.get(key)
        if entry is None:
            return
        title, builder = entry
        page = self.ribbon.insert_page(title, self._contextual_index, contextual=True)
        builder(page)
        self._active_contextual_key = key
        self.ribbon._tab_bar.setCurrentIndex(self._contextual_index)

    def _require_selection(self, action):
        """Run *action* only if something is selected; otherwise show message."""
        if not self.scene.selectedItems():
            self.statusBar().showMessage("Select an item first", 3000)
            return
        action()

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

    def _place_default_gridlines(self):
        """Place a default 3 V × 3 H grid for a new project."""
        sm = self.scene.scale_manager
        # Convert a sensible display-unit spacing to scene units
        if sm:
            spacing = sm.display_to_scene(DEFAULT_GRIDLINE_SPACING_MM)  # 288 in / 24 ft
            length  = sm.display_to_scene(DEFAULT_GRIDLINE_LENGTH_MM)   # 864 in / 72 ft
        else:
            spacing = DEFAULT_GRIDLINE_SPACING_MM
            length  = DEFAULT_GRIDLINE_LENGTH_MM

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
        from firepro3d.paper_space import PaperSpaceWidget
        ctx = "paper" if isinstance(self.central_tabs.currentWidget(),
                                     PaperSpaceWidget) else "model"
        dlg = DisplayManager(self.scene, parent=self, active_context=ctx)
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
        from firepro3d.sprinkler_db import SprinklerManagerDialog
        dlg = SprinklerManagerDialog(db=self._sprinkler_db, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            record = dlg.selected_record()
            if record:
                self._apply_sprinkler_template_from_record(record)

    def _apply_sprinkler_template_from_record(self, record):
        """Apply a SprinklerRecord as the active sprinkler placement template."""
        from firepro3d.sprinkler import Sprinkler
        template = Sprinkler(None)
        template.set_property("Manufacturer",  record.manufacturer)
        template.set_property("Model",         record.model)
        template.set_property("K-Factor",      str(record.k_factor))
        template.set_property("Min Pressure",  str(record.min_pressure))
        template.set_property("Coverage Area", str(record.coverage_area))
        template.set_property("Temperature",   f"{record.temp_rating}°F")
        template.set_property("Orientation",   record.type)
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
        self._apply_loaded_file(file)
        # Clear dirty flag before the divergence prompt so the autosave timer
        # cannot fire during the modal (autosave is gated on _modified).
        self._modified = False
        self._update_title()
        self._add_recent_file(file)
        # Offer to push embedded template to library after the project is clean.
        # Called here (not in _apply_loaded_file) so _modified is already False
        # and so recovery can skip the prompt (recovery stays dirty by design;
        # the user has enough dialogs during recovery — divergence re-offers on
        # the next normal File→Open).
        self._maybe_offer_template_push()

    def _apply_loaded_file(self, file: str):
        """Shared post-load restore — used by open AND crash recovery.

        Everything a loaded file needs to become the live session: scene,
        levels, display settings, markers, browser, active plan view, unit
        prefs, and the paper sheet/resolver rebind. Callers own _current_file,
        _modified, title, and recent-files bookkeeping (recovery deliberately
        keeps _current_file=None and _modified=True).
        """
        # Record whether the paper tab was current before the load.  The sheet
        # rebind at the end of this method must refresh the panel with the new
        # sheet's adapter when paper was showing — but _activate_plan_view (called
        # below) may switch the tab away before that happens, so we note it now.
        _paper_was_current = isinstance(
            self.central_tabs.currentWidget(), PaperSpaceWidget)
        self.scene.load_from_file(file)
        self.level_widget.populate()
        # Apply display settings: prefer project-embedded settings, fall back to QSettings
        project_ds = getattr(self.scene, '_loaded_display_settings', None)
        if project_ds:
            from firepro3d.display_manager import apply_project_display_settings
            apply_project_display_settings(self.scene, project_ds)
        else:
            from firepro3d.display_manager import apply_saved_display_settings
            apply_saved_display_settings(self.scene)
        # Apply paper-space display settings from project file
        from firepro3d.paper_display import apply_paper_display_from_project
        paper_ds = getattr(self.scene, '_loaded_paper_display', None)
        apply_paper_display_from_project(paper_ds)
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
        # Restore sheet from loaded project, resolver first so rebuilt
        # viewports capture it (resolver-rebind fix).
        self._view_resolver = ViewResolver(
            self.scene, self.plan_view_mgr,
            self.detail_manager, self.elevation_manager,
            level_manager=self.level_mgr,
        )
        # scene.load_from_file replaced scene._sheets with a NEW list —
        # rebind the manager over it (empty list → manager seeds a default
        # into that same list). Active sheet = first (§19.1); never persisted.
        self.sheet_mgr = SheetManager(self.scene._sheets)
        self._sheet = self.sheet_mgr.sheets[0]
        self.paper_space_widget.set_sheet(self._sheet, self._view_resolver)
        # Push the project-embedded template into the live PaperScene (§17.7
        # parity: all three load paths — open, crash-recovery, new — reach here
        # or the new_file() equivalent below).
        self._push_titleblock_template()
        # NOTE: _maybe_offer_template_push is intentionally NOT called here.
        # The open path calls it from _load_project (after _modified=False).
        # The recovery path skips it entirely (user has enough recovery dialogs;
        # divergence re-offers on the next normal File→Open).
        self._push_sheet_list()
        self._recompute_placed_views()
        # Refresh the property panel so it wraps the post-load active sheet, not
        # the pre-load detached Sheet (stale adapter bug: §19.4).
        # If the paper tab is current now, the guard in update_paper_property_manager
        # will fire normally.  If paper was current at load-start but _activate_plan_view
        # switched the tab away, the panel now holds PlanViewInfo (correct for the plan
        # tab), so we explicitly push a fresh SheetProperties adapter so that switching
        # back to the paper tab later — or a direct panel read — uses the new sheet.
        if isinstance(self.central_tabs.currentWidget(), PaperSpaceWidget):
            self.update_paper_property_manager()
        elif _paper_was_current:
            # The load switched away from paper; proactively seed the panel with
            # the new sheet so any immediate switch back shows the right adapter.
            self.prop_manager.show_properties(
                self._sheet_props_adapter(self._sheet))

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
            # Full open parity (grill 2026-07-20): recovery differs from
            # File→Open only in _current_file (None → first Save prompts
            # Save-As), _modified (True — unsaved by definition), and no
            # recent-files entry.
            self._apply_loaded_file(path)
            self._modified = True
            self._update_title()
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

    def _dispatch_undo(self):
        """Route undo to the active tab's undo stack.

        Paper-space sheets own a per-scene QUndoStack; every other tab shares
        the model-space scene's undo system. Dispatching on the current central
        tab keeps the ribbon Undo button tab-aware without disturbing
        model-space behaviour.
        """
        w = self.central_tabs.currentWidget()
        if isinstance(w, PaperSpaceWidget):
            w.paper_scene.undo_stack.undo()
        else:
            self.scene.undo()

    def _dispatch_redo(self):
        """Route redo to the active tab's undo stack.

        Mirror of :meth:`_dispatch_undo` for the ribbon Redo button.
        """
        w = self.central_tabs.currentWidget()
        if isinstance(w, PaperSpaceWidget):
            w.paper_scene.undo_stack.redo()
        else:
            self.scene.redo()

    def new_file(self):
        """Clear the scene and start a fresh project."""
        if not self._ask_save_changes("starting a new project"):
            return
        self._current_file = None
        self.detail_manager.clear()
        self.project_browser.refresh_details(self.detail_manager.detail_names)
        self.scene._clear_scene()
        self.level_widget.populate()
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

        # Reset the paper sheet to a blank default and rebuild the paper scene
        # (same swap mechanism as _load_project). update_from_sheet() clears the
        # paper-space undo stack, so the fresh sheet starts with no history.
        self.scene._sheets = [Sheet.create_default()]
        self.sheet_mgr = SheetManager(self.scene._sheets)
        self._sheet = self.sheet_mgr.sheets[0]
        self.paper_space_widget.set_sheet(self._sheet, self._view_resolver)
        # Push the template (None after _clear_scene → restores legacy chain).
        self._push_titleblock_template()
        self._push_sheet_list()
        self._recompute_placed_views()
        # Refresh the property panel so it wraps the fresh default sheet, not
        # any pre-new-file detached Sheet adapter (stale adapter bug: §19.4).
        if isinstance(self.central_tabs.currentWidget(), PaperSpaceWidget):
            self.update_paper_property_manager()
        elif (self.prop_manager._targets
              and isinstance(self.prop_manager._targets[0], SheetProperties)):
            self.prop_manager.show_properties(
                self._sheet_props_adapter(self._sheet))

        self._modified = False
        self._update_title()
        QTimer.singleShot(100, self._fit_active_plan_view)

    def _update_title(self):
        name = os.path.basename(self._current_file) if self._current_file else "Untitled"
        star = " *" if self._modified else ""
        self.setWindowTitle(f"FirePro 3D \u2014 {name}{star}")

    def _on_paper_modified(self):
        """A paper mutation dirties the project (save prompt + autosave)."""
        self._modified = True
        self._update_title()
        self._push_sheet_list()
        self._recompute_placed_views()

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
        # Paper tab: Esc = deselect → panel falls back to sheet properties
        # (§19.4). Never touches the model scene from the paper tab.
        w = self.central_tabs.currentWidget()
        if isinstance(w, PaperSpaceWidget):
            w.paper_scene.clearSelection()
            self.update_paper_property_manager()
            return
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
        """Open the unified underlay import dialog (PDF, DXF, DWG)."""
        # Default browse directory = project file directory
        default_dir = ""
        if self._current_file:
            default_dir = os.path.dirname(self._current_file)
        dialog = UnderlayImportDialog(
            self, file_path=file_path,
            scale_manager=self.scene.scale_manager,
            default_dir=default_dir,
            levels=[l.name for l in self.level_mgr.levels],
            current_level=self.scene.active_level,
        )
        try:
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
            params = dialog.get_import_params() if accepted else None
        finally:
            # The dialog is parented to this window — without an explicit
            # deleteLater() every import leaks the dialog (geometry list,
            # preview scene) until the window closes.
            dialog.deleteLater()
        if params is None:
            return
        # Route the import to the chosen level (defaults to the current one),
        # switching to its plan view so the underlay record is tagged with it.
        self._activate_plan_view(params.level or self.scene.active_level)
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
                import_mode=params.import_mode,
            )
            self.scene.import_pdf(
                params.file_path,
                dpi=params.pdf_dpi,
                page=params.pdf_page,
                _record=record,
                import_mode=params.import_mode,
            )
            return
        if not params.geom_list:
            return
        # (Plan view already activated for the chosen level above.)
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
                "No design area defined — hydraulic calculation requires one.", 5000)
        result = self.scene.run_hydraulics(design_sprinklers=design)
        self.hydro_report.populate(result, self.scene, self.scene.scale_manager)
        self.hydro_dock.show()
        self.hydro_dock.raise_()

    def clear_hydraulics(self):
        """Clear the hydraulic overlay and the report dock."""
        self.scene.clear_hydraulics()
        self.hydro_report.clear()

    def show_equiv_length_ref(self):
        """Show the NFPA 13 equivalent length reference dialog."""
        from firepro3d.hydraulic_report import EquivalentLengthDialog
        dlg = EquivalentLengthDialog(self)
        dlg.show()

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

    def update_paper_property_manager(self):
        """Populate the panel from the paper scene's text selection.

        Only acts while the paper tab is current, so model-space selection
        handling keeps sole ownership of the panel everywhere else. Also
        re-runs after every undo/redo (undo_stack.indexChanged) so the panel
        never shows stale formatting.
        """
        w = self.central_tabs.currentWidget()
        if not isinstance(w, PaperSpaceWidget):
            return
        # In add-text mode the template is the live target; don't overwrite it.
        if w.view._add_text_mode:
            self.prop_manager.show_properties(self.current_text_template)
            return
        try:
            # T9: TitleBlockTemplateItem is now non-selectable; this filter
            # already excluded it, so no change needed here.
            items = [it for it in w.paper_scene.selectedItems()
                     if isinstance(it, TextAnnotationItem)]
        except RuntimeError:
            return
        # §19.4: the paper panel is never blank — empty selection falls back
        # to the active sheet's properties.
        self.prop_manager.show_properties(
            items if items else self._sheet_props_adapter(self._sheet))

    def _on_add_text_mode_toggled(self, checked: bool):
        """Show the text template pre-placement; restore selection view after."""
        if checked:
            self.prop_manager.show_properties(self.current_text_template)
        else:
            self.update_paper_property_manager()

    def _on_ribbon_add_text_toggled(self, checked: bool):
        """Ribbon Add Text: auto-switch to the paper tab, then enter mode."""
        if checked and not isinstance(
                self.central_tabs.currentWidget(), PaperSpaceWidget):
            self._activate_paper_sheet()
        self.paper_space_widget.set_add_text_mode(checked)

    def _sync_add_text_ribbon_btn(self, on: bool):
        """Keep the ribbon Add Text button in step with the view mode."""
        btn = getattr(self, "_add_text_ribbon_btn", None)
        if btn is not None and btn.isChecked() != on:
            btn.blockSignals(True)
            btn.setChecked(on)
            btn.blockSignals(False)

    def _font_group_targets(self):
        """Targets for the ribbon Font group: selection, else the template."""
        w = self.central_tabs.currentWidget()
        if not isinstance(w, PaperSpaceWidget):
            return []
        if w.view._add_text_mode:
            return [self.current_text_template]
        try:
            return [it for it in w.paper_scene.selectedItems()
                    if isinstance(it, TextAnnotationItem)]
        except RuntimeError:
            return []

    def _update_font_group_context(self):
        """Enable the Font group only when it has live targets; then sync."""
        fg = getattr(self, "font_group", None)
        if fg is None:
            return
        targets = self._font_group_targets()
        fg.set_enabled(bool(targets))
        if targets:
            fg.sync()

    def update_property_manager(self):
        # Guard against the scene's C++ object being deleted during shutdown
        try:
            # Don't override template properties during placement modes
            if self.scene.mode in ("pipe", "sprinkler", "wall",
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
        # Child widgets don't receive closeEvent; release the 3D view's VTK
        # render window explicitly so its GL context doesn't leak past teardown.
        if hasattr(self, "view_3d"):
            self.view_3d.cleanup()
        super().closeEvent(event)

    _STATE_VERSION = 5  # bump when dock layout changes between sprints

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
            self.settings.setValue("template/pipe", pipe_props)
        if self.current_sprinkler_template:
            spr_props = {k: v["value"]
                         for k, v in self.current_sprinkler_template._properties.items()}
            self.settings.setValue("template/sprinkler", spr_props)
        if self.current_text_template is not None:
            self.settings.setValue(
                "template/text",
                text_template_to_settings(self.current_text_template.data))
        if getattr(self, "current_opening_template", None) is not None:
            t = self.current_opening_template
            self.settings.setValue("template/opening", {
                "feature_id":   t.feature_id,
                "sill_mm":      t.sill_mm,
                "width_mm":     t.width_mm,
                "height_mm":    t.height_mm,
                "alignment":    t.alignment,
                "mirror_hinge": t.mirror_hinge,
                "mirror_facing": t.mirror_facing,
            })


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    install_excepthook()
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