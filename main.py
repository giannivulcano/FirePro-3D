import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QToolBar, QMenuBar,
                              QFileDialog, QDockWidget, QInputDialog,
                              QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QSpinBox, QDialogButtonBox, QLineEdit)
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
        self.setCentralWidget(self.view)

        # MENU BAR
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)
        self.init_file_menu(menu_bar)
        self.init_project_menu(menu_bar)
        self.init_edit_menu(menu_bar)
        self.init_view_menu(menu_bar)
        self.init_help_menu(menu_bar)

        # Toolbar
        toolbar = QToolBar("Tools")
        self.addToolBar(toolbar)
        self.init_toolbar(toolbar)

        # Property manager dock
        self.prop_manager = PropertyManager()
        self.scene.requestPropertyUpdate.connect(self.prop_manager.show_properties)
        self.dock = QDockWidget("Properties", self)
        self.init_property_manager_dock()

        # Layer manager dock
        self.layer_manager = LayerManager(self.scene)
        self.layer_dock = QDockWidget("Layers", self)
        self.layer_dock.setObjectName("LayersDock")
        self.layer_dock.setWidget(self.layer_manager)
        self.layer_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.layer_dock)
        self.layer_dock.setMinimumWidth(160)

        # Status bar with cursor coordinates
        status_bar = self.statusBar()
        self.coord_label = QLabel("X: —   Y: —")
        self.coord_label.setMinimumWidth(280)
        status_bar.addPermanentWidget(self.coord_label)
        self.mode_label = QLabel("Mode: —")
        status_bar.addWidget(self.mode_label)
        self.scene.cursorMoved.connect(self.coord_label.setText)

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

        # Snap to underlay toggle
        self._snap_action = QAction("Snap to Underlay", self)
        self._snap_action.setCheckable(True)
        self._snap_action.setChecked(False)
        self._snap_action.toggled.connect(
            lambda checked: setattr(self.scene, "_snap_to_underlay", checked))
        view_menu.addAction(self._snap_action)

        view_menu.addSeparator()

        # Layer dock toggle
        view_menu.addAction(self.layer_dock.toggleViewAction())

    def init_help_menu(self, menu_bar):
        help_menu = menu_bar.addMenu("Help")

    # ─────────────────────────────────────────────────────────────────────────
    # TOOLBAR INITIALISATION
    # ─────────────────────────────────────────────────────────────────────────

    def init_toolbar(self, toolbar):
        toolbar.setObjectName("SprinklerToolbar")
        toolbar.setIconSize(QSize(64, 64))
        toolbar.setContentsMargins(5, 5, 5, 5)

        sprinkler_action = QAction(QIcon(r"graphics/Toolbar/sprinkler_icon.svg"), "Sprinkler", self)
        sprinkler_action.triggered.connect(
            lambda: self.scene.set_mode("sprinkler", self.current_sprinkler_template))
        toolbar.addAction(sprinkler_action)

        pipe_action = QAction(QIcon(r"graphics/Toolbar/pipe_icon.svg"), "Pipe", self)
        pipe_action.triggered.connect(
            lambda: self.scene.set_mode("pipe", self.current_pipe_template))
        toolbar.addAction(pipe_action)

        move_action = QAction(QIcon(r"graphics/Toolbar/move_icon.svg"), "Move", self)
        move_action.triggered.connect(lambda: self.scene.sprinkler_system.report())
        toolbar.addAction(move_action)

        copy_action = QAction(QIcon(r"graphics/Toolbar/copy_icon.svg"), "Copy", self)
        copy_action.triggered.connect(lambda: self.scene.sprinkler_system.report())
        toolbar.addAction(copy_action)

        report_action = QAction(QIcon(r"graphics/Toolbar/report_icon.svg"), "Report", self)
        report_action.triggered.connect(lambda: self.scene.sprinkler_system.report())
        toolbar.addAction(report_action)

        dimension_action = QAction(QIcon(r"graphics/Toolbar/dimension_icon.svg"), "Dimension", self)
        dimension_action.triggered.connect(lambda: self.scene.set_mode("dimension"))
        toolbar.addAction(dimension_action)

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