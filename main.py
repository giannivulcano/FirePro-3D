import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QMenuBar,
                              QFileDialog, QDockWidget, QInputDialog,
                              QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QSpinBox, QDialogButtonBox, QLineEdit,
                              QTabWidget, QMenu, QStyle, QWidget)
from PyQt6.QtGui import QAction, QPainter, QIcon
from PyQt6.QtCore import Qt, QSettings, QSize
from Model_Space import Model_Space
from Model_View import Model_View
from sprinkler import Sprinkler
from pipe import Pipe
from dxf_import_dialog import DxfImportDialog
from property_manager import PropertyManager
from scale_manager import DisplayUnit
from layer_manager import LayerManager
from hydraulic_report import HydraulicReportWidget
from user_layer_manager import UserLayerManager, UserLayerWidget
from paper_space import PaperSpaceWidget, PAPER_SIZES
from ribbon_bar import RibbonBar


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

        # User layer manager — shared between scene and UI
        self.user_layer_mgr = UserLayerManager()
        self.scene._user_layer_manager = self.user_layer_mgr   # for save/load

        # Central tab widget: Model Space | Layout 1 (Paper Space)
        self.paper_space_widget = PaperSpaceWidget(self.scene)
        self.central_tabs = QTabWidget()
        self.central_tabs.addTab(self.view, "Model Space")
        self.central_tabs.addTab(self.paper_space_widget, "Layout 1")

        # Ribbon bar + central tabs wrapped in a container widget
        self.ribbon = RibbonBar()
        _container = QWidget()
        _vlay = QVBoxLayout(_container)
        _vlay.setContentsMargins(0, 0, 0, 0)
        _vlay.setSpacing(0)
        _vlay.addWidget(self.ribbon)
        _vlay.addWidget(self.central_tabs)
        self.setCentralWidget(_container)

        # MENU BAR (kept for keyboard shortcuts and less-common options)
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)
        self.init_file_menu(menu_bar)
        self.init_project_menu(menu_bar)
        self.init_edit_menu(menu_bar)
        self.init_hydraulics_menu(menu_bar)
        self.init_view_menu(menu_bar)
        self.init_help_menu(menu_bar)

        # Property manager dock
        self.prop_manager = PropertyManager()
        self.scene.requestPropertyUpdate.connect(self.prop_manager.show_properties)
        self.dock = QDockWidget("Properties", self)
        self.init_property_manager_dock()

        # DXF layer manager dock
        self.layer_manager = LayerManager(self.scene)
        self.layer_dock = QDockWidget("DXF Layers", self)
        self.layer_dock.setObjectName("LayersDock")
        self.layer_dock.setWidget(self.layer_manager)
        self.layer_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.layer_dock)
        self.layer_dock.setMinimumWidth(160)

        # User layer dock
        self.user_layer_widget = UserLayerWidget(
            self.user_layer_mgr, scene=self.scene
        )
        self.user_layer_widget.activeLayerChanged.connect(
            lambda name: setattr(self.scene, "active_user_layer", name)
        )
        self.user_layer_widget.layersChanged.connect(
            lambda: self.user_layer_mgr.apply_to_scene(self.scene)
        )
        self.user_layer_dock = QDockWidget("User Layers", self)
        self.user_layer_dock.setObjectName("UserLayersDock")
        self.user_layer_dock.setWidget(self.user_layer_widget)
        self.user_layer_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.user_layer_dock)
        self.tabifyDockWidget(self.layer_dock, self.user_layer_dock)
        self.user_layer_dock.setMinimumWidth(200)

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

        # Now all docks exist — wire their toggles into the View menu and ribbon
        self._add_dock_toggles()
        self.init_ribbon()

        # Restore settings
        self.restore_settings()

    def restore_settings(self):
        self.restoreGeometry(self.settings.value("geometry", b""))
        self.restoreState(self.settings.value("windowState", b""))

    # ─────────────────────────────────────────────────────────────────────────
    # MENU BAR INITIALISATION
    # ─────────────────────────────────────────────────────────────────────────

    def init_file_menu(self, menu_bar):
        file_menu = menu_bar.addMenu("File")

        save_action = QAction(QIcon(r"graphics/File Menu/save_icon.svg"), "Save", self)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        save_as_action = QAction(QIcon(r"graphics/File Menu/save_icon.svg"), "Save As", self)
        save_as_action.triggered.connect(self.save_file_as)
        file_menu.addAction(save_as_action)

        open_action = QAction(QIcon(r"graphics/File Menu/load_icon.svg"), "Open", self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        export_pdf_action = QAction("Export Hydraulic Report (PDF)…", self)
        export_pdf_action.triggered.connect(lambda: self.hydro_report._export_pdf())
        file_menu.addAction(export_pdf_action)

        export_csv_action = QAction("Export Hydraulic Report (CSV)…", self)
        export_csv_action.triggered.connect(lambda: self.hydro_report._export_csv())
        file_menu.addAction(export_csv_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def init_project_menu(self, menu_bar):
        project_menu = menu_bar.addMenu("Project")

        project_settings_action = QAction("Project Information", self)
        project_menu.addAction(project_settings_action)

        project_menu.addSeparator()

        import_pdf = QAction("Import PDF Underlay…", self)
        import_pdf.triggered.connect(self.open_pdf_import_dialog)
        project_menu.addAction(import_pdf)

        import_dxf = QAction("Import DXF Underlay…", self)
        import_dxf.triggered.connect(self.open_dxf_import_dialog)
        project_menu.addAction(import_dxf)

        project_menu.addSeparator()

        refresh_underlays = QAction("Refresh All Underlays", self)
        refresh_underlays.triggered.connect(self.refresh_underlays)
        project_menu.addAction(refresh_underlays)

        project_menu.addSeparator()

        set_scale = QAction("Set Scale", self)
        set_scale.triggered.connect(self.set_scale_dialog)
        project_menu.addAction(set_scale)

        project_menu.addSeparator()

        # ── Label Precision submenu ──────────────────────────────────
        precision_menu = project_menu.addMenu("Label Precision")
        for places in (0, 1, 2, 3):
            act = QAction(f"{places} decimal place{'s' if places != 1 else ''}", self)
            act.triggered.connect(
                lambda checked, p=places: self._set_precision(p))
            precision_menu.addAction(act)

        project_menu.addSeparator()

        # ── Display Units submenu ─────────────────────────────────────
        units_menu = project_menu.addMenu("Display Units")

        unit_imperial = QAction("Imperial (ft-in)", self)
        unit_imperial.triggered.connect(
            lambda: self.scene.set_display_unit(DisplayUnit.IMPERIAL))
        units_menu.addAction(unit_imperial)

        unit_m = QAction("Metric (m)", self)
        unit_m.triggered.connect(
            lambda: self.scene.set_display_unit(DisplayUnit.METRIC_M))
        units_menu.addAction(unit_m)

        unit_mm = QAction("Metric (mm)", self)
        unit_mm.triggered.connect(
            lambda: self.scene.set_display_unit(DisplayUnit.METRIC_MM))
        units_menu.addAction(unit_mm)

    def init_hydraulics_menu(self, menu_bar):
        hyd_menu = menu_bar.addMenu("Hydraulics")

        place_ws = QAction("Place Water Supply…", self)
        place_ws.triggered.connect(lambda: self.scene.set_mode("water_supply"))
        hyd_menu.addAction(place_ws)

        design_area = QAction("Set Design Area…", self)
        design_area.triggered.connect(lambda: self.scene.set_mode("design_area"))
        hyd_menu.addAction(design_area)

        hyd_menu.addSeparator()

        run_action = QAction("Run Hydraulics", self)
        run_action.setShortcut("F5")
        run_action.triggered.connect(self.run_hydraulics)
        hyd_menu.addAction(run_action)

        clear_action = QAction("Clear Results", self)
        clear_action.triggered.connect(self.clear_hydraulics)
        hyd_menu.addAction(clear_action)

        hyd_menu.addSeparator()

        pdf_action = QAction("Export Report (PDF)…", self)
        pdf_action.triggered.connect(lambda: self.hydro_report._export_pdf())
        hyd_menu.addAction(pdf_action)

        csv_action = QAction("Export Report (CSV)…", self)
        csv_action.triggered.connect(lambda: self.hydro_report._export_csv())
        hyd_menu.addAction(csv_action)

    def init_edit_menu(self, menu_bar):
        edit_menu = menu_bar.addMenu("Edit")

        undo_action = QAction("Undo", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self.scene.undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(self.scene.redo)
        edit_menu.addAction(redo_action)

    def init_view_menu(self, menu_bar):
        view_menu = menu_bar.addMenu("View")
        self._view_menu = view_menu   # saved so _add_dock_toggles() can populate it later

        # Snap to underlay toggle
        self._snap_action = QAction("Snap to Underlay", self)
        self._snap_action.setCheckable(True)
        self._snap_action.setChecked(False)
        self._snap_action.toggled.connect(
            lambda checked: setattr(self.scene, "_snap_to_underlay", checked))
        view_menu.addAction(self._snap_action)

        view_menu.addSeparator()

        # Dock toggles are added later in _add_dock_toggles() once the docks exist.

        # Paper space shortcuts
        paper_action = QAction("Switch to Layout 1 (Paper Space)", self)
        paper_action.triggered.connect(
            lambda: self.central_tabs.setCurrentIndex(1)
        )
        view_menu.addAction(paper_action)

        model_action = QAction("Switch to Model Space", self)
        model_action.triggered.connect(
            lambda: self.central_tabs.setCurrentIndex(0)
        )
        view_menu.addAction(model_action)

    def _add_dock_toggles(self):
        """Append dock visibility toggles to the View menu.

        Must be called *after* all dock widgets have been created so that
        toggleViewAction() is available on each dock.
        """
        self._view_menu.addSeparator()
        self._view_menu.addAction(self.layer_dock.toggleViewAction())
        self._view_menu.addAction(self.user_layer_dock.toggleViewAction())
        self._view_menu.addAction(self.hydro_dock.toggleViewAction())

    def init_help_menu(self, menu_bar):
        help_menu = menu_bar.addMenu("Help")

    # ─────────────────────────────────────────────────────────────────────────
    # RIBBON INITIALISATION
    # ─────────────────────────────────────────────────────────────────────────

    def init_ribbon(self):
        """Build all four ribbon tabs and wire every button to existing actions.

        Must be called *after* all dock widgets are created so that dock
        visibility toggles can be wired correctly.
        """
        s = self.style()

        # ── Tab 1: Model ─────────────────────────────────────────────────────
        model_page = self.ribbon.add_page("Model")

        g_file = model_page.add_group("File")
        g_file.add_large_button(
            "Open", QIcon(r"graphics/File Menu/load_icon.svg"), self.open_file)
        g_file.add_large_button(
            "Save", QIcon(r"graphics/File Menu/save_icon.svg"), self.save_file)

        g_draw = model_page.add_group("Draw")
        g_draw.add_large_button(
            "Pipe", QIcon(r"graphics/Toolbar/pipe_icon.svg"),
            lambda: self.scene.set_mode("pipe", self.current_pipe_template))
        g_draw.add_large_button(
            "Dimension", QIcon(r"graphics/Toolbar/dimension_icon.svg"),
            lambda: self.scene.set_mode("dimension"))

        g_edit = model_page.add_group("Edit")
        g_edit.add_large_button(
            "Undo",
            s.standardIcon(QStyle.StandardPixmap.SP_ArrowBack),
            self.scene.undo, shortcut="Ctrl+Z")
        g_edit.add_large_button(
            "Redo",
            s.standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
            self.scene.redo, shortcut="Ctrl+Y")
        g_edit.add_small_button(
            "Copy", QIcon(r"graphics/Toolbar/copy_icon.svg"),
            lambda: self.scene.copy_selected_items())
        g_edit.add_small_button(
            "Move", QIcon(r"graphics/Toolbar/move_icon.svg"),
            lambda: self.scene.set_mode("move"))
        g_edit.add_small_button(
            "Delete",
            s.standardIcon(QStyle.StandardPixmap.SP_TrashIcon),
            lambda: self.scene.delete_selected_items())

        g_ulay = model_page.add_group("Underlay")
        g_ulay.add_large_button(
            "Import DXF",
            s.standardIcon(QStyle.StandardPixmap.SP_FileIcon),
            self.open_dxf_import_dialog)
        g_ulay.add_large_button(
            "Import PDF",
            s.standardIcon(QStyle.StandardPixmap.SP_FileLinkIcon),
            self.open_pdf_import_dialog)
        g_ulay.add_small_button(
            "Refresh All",
            s.standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
            self.refresh_underlays)

        g_set = model_page.add_group("Settings")
        g_set.add_large_button(
            "Set Scale",
            s.standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView),
            self.set_scale_dialog)
        g_set.add_small_menu_button(
            "Units", s.standardIcon(QStyle.StandardPixmap.SP_FileDialogListView),
            self._build_units_menu())
        g_set.add_small_menu_button(
            "Precision", s.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            self._build_precision_menu())

        # ── Tab 2: Sprinkler ─────────────────────────────────────────────────
        spr_page = self.ribbon.add_page("Sprinkler")

        g_place = spr_page.add_group("Place")
        g_place.add_large_button(
            "Sprinkler", QIcon(r"graphics/Toolbar/sprinkler_icon.svg"),
            lambda: self.scene.set_mode("sprinkler", self.current_sprinkler_template))

        g_sys = spr_page.add_group("System")
        g_sys.add_large_button(
            "Water Supply", QIcon(r"graphics/Toolbar/supply_icon.svg"),
            lambda: self.scene.set_mode("water_supply"))
        g_sys.add_large_button(
            "Design Area", QIcon(r"graphics/Toolbar/design_area_icon.svg"),
            lambda: self.scene.set_mode("design_area"))

        g_view2 = spr_page.add_group("View")
        snap_btn = g_view2.add_large_button(
            "Snap to\nUnderlay",
            s.standardIcon(QStyle.StandardPixmap.SP_CommandLink),
            lambda checked: setattr(self.scene, "_snap_to_underlay", checked),
            checkable=True)
        # Keep ribbon button and menu action in sync
        self._snap_action.toggled.connect(snap_btn.setChecked)
        snap_btn.toggled.connect(self._snap_action.setChecked)

        # ── Tab 3: Analysis ──────────────────────────────────────────────────
        ana_page = self.ribbon.add_page("Analysis")

        g_hyd = ana_page.add_group("Hydraulics")
        g_hyd.add_large_button(
            "Run\nHydraulics", QIcon(r"graphics/Toolbar/hydraulics_icon.svg"),
            self.run_hydraulics, shortcut="F5")
        g_hyd.add_large_button(
            "Clear\nResults",
            s.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton),
            self.clear_hydraulics)

        g_exp = ana_page.add_group("Export")
        g_exp.add_large_button(
            "Export PDF", QIcon(r"graphics/Toolbar/report_icon.svg"),
            self.hydro_report._export_pdf)
        g_exp.add_large_button(
            "Export CSV",
            s.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            self.hydro_report._export_csv)

        g_pan = ana_page.add_group("Panels")
        report_toggle = g_pan.add_large_button(
            "Report\nPanel",
            s.standardIcon(QStyle.StandardPixmap.SP_FileDialogListView),
            None, checkable=True)
        report_toggle.toggled.connect(
            lambda on: self.hydro_dock.show() if on else self.hydro_dock.hide())
        self.hydro_dock.visibilityChanged.connect(report_toggle.setChecked)

        # ── Tab 4: Draft ─────────────────────────────────────────────────────
        draft_page = self.ribbon.add_page("Draft")

        g_ws = draft_page.add_group("Workspace")
        g_ws.add_large_button(
            "Model\nSpace",
            s.standardIcon(QStyle.StandardPixmap.SP_DesktopIcon),
            lambda: self.central_tabs.setCurrentIndex(0))
        g_ws.add_large_button(
            "Layout 1\nPaper",
            s.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView),
            lambda: self.central_tabs.setCurrentIndex(1))

        g_pg = draft_page.add_group("Page")
        g_pg.add_large_menu_button(
            "Paper Size",
            s.standardIcon(QStyle.StandardPixmap.SP_FileIcon),
            self._build_paper_size_menu())
        g_pg.add_large_button(
            "Title Block",
            s.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            self.paper_space_widget.edit_title_block)

        g_ann = draft_page.add_group("Annotations")
        g_ann.add_large_button(
            "Dimension", QIcon(r"graphics/Toolbar/dimension_icon.svg"),
            lambda: self.scene.set_mode("dimension"))

        g_pan2 = draft_page.add_group("Panels")
        prop_btn = g_pan2.add_small_button(
            "Properties",
            s.standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView),
            None, checkable=True)
        prop_btn.toggled.connect(self.dock.setVisible)
        self.dock.visibilityChanged.connect(prop_btn.setChecked)

        dxf_btn = g_pan2.add_small_button(
            "DXF Layers",
            s.standardIcon(QStyle.StandardPixmap.SP_DirIcon),
            None, checkable=True)
        dxf_btn.toggled.connect(self.layer_dock.setVisible)
        self.layer_dock.visibilityChanged.connect(dxf_btn.setChecked)

        ul_btn = g_pan2.add_small_button(
            "User Layers",
            s.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
            None, checkable=True)
        ul_btn.toggled.connect(self.user_layer_dock.setVisible)
        self.user_layer_dock.visibilityChanged.connect(ul_btn.setChecked)

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
        dialog = DxfImportDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            file_path = dialog.get_file_path()
            if not file_path:
                return
            colour = dialog.get_colour()
            line_weight = dialog.get_line_weight()
            layers = dialog.get_selected_layers()
            self.scene.import_dxf(
                file_path,
                color=colour,
                line_weight=line_weight,
                layers=layers,
            )

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

    def save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())

    def restore_settings(self):
        self.restoreGeometry(self.settings.value("geometry", b""))
        self.restoreState(self.settings.value("windowState", b""))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()