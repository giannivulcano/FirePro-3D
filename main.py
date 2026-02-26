import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QToolBar, QMenuBar, QFileDialog,QDockWidget, QInputDialog
from PyQt6.QtGui import QAction, QPainter, QIcon
from PyQt6.QtCore import Qt, QSettings, QSize
from Model_Space import Model_Space
from Model_View import Model_View
from sprinkler import Sprinkler
from pipe import Pipe

from property_manager import PropertyManager

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FireFlow Pro - Sprinkler Design Software")

        # Settings
        self.settings = QSettings("GV", "SprinklerAPP")
        self.current_sprinkler_template = Sprinkler(None)  # not attached to a node yet
        self.current_pipe_template = Pipe(None, None)  # not attached to a node yet

        # Scene + View (only once)
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

        
        # --- property manager dock ---
        self.prop_manager = PropertyManager()
        self.scene.requestPropertyUpdate.connect(self.prop_manager.show_properties)
        self.dock = QDockWidget("Properties", self)
        self.init_property_manager_dock()

        # --- Restore Settings ---
        self.restore_settings()

    def restore_settings(self):
        self.restoreGeometry(self.settings.value("geometry", b""))
        self.restoreState(self.settings.value("windowState", b""))

    #-------------------------------------
    # MENU BAR INITIALIZATOIN ------------
    #-------------------------------------

    def init_file_menu(self, menu_bar):
        file_menu = menu_bar.addMenu("File")

        save_action = QAction(QIcon(r"graphics\File Menu\save_icon.svg"),"Save", self)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        save_as_action = QAction(QIcon(r"graphics\File Menu\save_icon.svg"), "Save As", self)
        save_as_action.triggered.connect(self.save_file_as)
        file_menu.addAction(save_as_action)
    
        open_action = QAction(QIcon(r"graphics\File Menu\load_icon.svg"), "Open", self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def init_project_menu(self, menu_bar):
        file_menu = menu_bar.addMenu("Project")

        project_settings_action = QAction("Project Information", self)
        file_menu.addAction(project_settings_action)

        import_PDF = QAction("Import PDF", self)
        import_PDF.triggered.connect(self.open_pdf_import_dialog)
        file_menu.addAction(import_PDF)

        import_DXF = QAction("Import DXF", self)
        import_DXF.triggered.connect(self.open_dxf_import_dialog)
        file_menu.addAction(import_DXF)                

        set_scale = QAction("Set Scale", self)
        set_scale.triggered.connect(self.set_scale_dialog)
        file_menu.addAction(set_scale)


    def init_edit_menu(self, menu_bar):
        edit_menu = menu_bar.addMenu("Edit")
    
    def init_view_menu(self, menu_bar):
        view_menu = menu_bar.addMenu("View")
    
    def init_help_menu(self, menu_bar):
        view_menu = menu_bar.addMenu("Help")

    #-------------------------------------
    # TOOL BAR INITIALIZATION ------------
    #-------------------------------------       

    def init_toolbar(self, toolbar):
        toolbar.setObjectName("SprinklerToolbar")
        toolbar.setIconSize(QSize(64, 64))  # bigger icons -> bigger toolbar
        toolbar.setContentsMargins(5, 5, 5, 5) 


        sprinkler_action = QAction(QIcon(r"graphics\Toolbar\sprinkler_icon.svg"),"Sprinkler", self)
        sprinkler_action.triggered.connect(
            lambda: self.scene.set_mode(r"sprinkler",self.current_sprinkler_template))
        toolbar.addAction(sprinkler_action)

        pipe_action = QAction(QIcon(r"graphics\Toolbar\pipe_icon.svg"),"Pipe", self)
        pipe_action.triggered.connect(
            lambda: self.scene.set_mode("pipe", self.current_pipe_template))
        toolbar.addAction(pipe_action)

        move_action = QAction(QIcon(r"graphics\Toolbar\move_icon.svg"),"Move", self)
        move_action.triggered.connect(lambda: self.scene.sprinkler_system.report())
        toolbar.addAction(move_action)

        copy_action = QAction(QIcon(r"graphics\Toolbar\copy_icon.svg"),"Copy", self)
        copy_action.triggered.connect(lambda: self.scene.sprinkler_system.report())
        toolbar.addAction(copy_action)

        report_action = QAction(QIcon(r"graphics\Toolbar\report_icon.svg"),"Report", self)
        report_action.triggered.connect(lambda: self.scene.sprinkler_system.report())
        toolbar.addAction(report_action)

        dimension_action = QAction(QIcon(r"graphics\Toolbar\dimension_icon.svg"),"Dimension", self)
        dimension_action.triggered.connect(lambda: self.scene.set_mode("dimension"))
        toolbar.addAction(dimension_action)

    #-------------------------------------
    # PROPERTY MANAGER INITIALIZATION ----
    #-------------------------------------  

    def init_property_manager_dock(self):
        self.dock.setObjectName("PropertiesDock")
        self.dock.setWidget(self.prop_manager)
        self.dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | 
                                  Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.setMinimumWidth(200) 
        self.resizeDocks([self.dock], [300], Qt.Orientation.Horizontal)
        # --- hook up scene selection ---
        self.scene.selectionChanged.connect(self.update_property_manager)

    #-------------------------------------
    # MENU BAR HELPERS -------------------
    #-------------------------------------

    def save_file(self):
        print("Save triggered")
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
        val, ok = QInputDialog.getDouble(self, "Drawing Scale",
                                        "Units per meter:", 
                                        self.scene.units_per_meter, 1, 10000, 0)
        if ok:
            self.scene.units_per_meter = val

    def open_dxf_import_dialog(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select DXF", "", "DXF Files (*.dxf)")
        if file:
            self.scene.import_dxf(file)

    def open_pdf_import_dialog(self):
        dialog = ImportDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            opts = dialog.get_options()
            print("Importing:", opts)

            # Example: hand off to scene
            self.scene.import_pdf(opts["file"], dpi=opts["dpi"], page=opts["page"])
            
    #-------------------------------------
    # PROPERTY MANAGER HELPERS -----------
    #-------------------------------------

    def update_property_manager(self):
        items = self.scene.selectedItems()
        if items:
            self.prop_manager.show_properties(items[0])
        else:
            self.prop_manager.show_properties(None)

    #-------------------------------------
    # EVENT HANDLING ---------------------
    #-------------------------------------
    def closeEvent(self, event):
        # save geometry and dock state before quit
        self.save_settings()
        super().closeEvent(event)

    #-------------------------------------
    # SAVE AND LOAD SETTINGS -------------
    #-------------------------------------
    def save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())

    def restore_settings(self):
        self.restoreGeometry(self.settings.value("geometry", b""))
        self.restoreState(self.settings.value("windowState", b""))


#-------------------------------------
# USER FORMS             -------------

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QSpinBox, QDialogButtonBox, QLineEdit

class ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Underlay")
        
        layout = QVBoxLayout(self)

        # File picker row
        file_layout = QHBoxLayout()
        self.file_edit = QLineEdit()
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_file)
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
        self.page_spin.setRange(0, 999)  # you can cap it later
        self.page_spin.setValue(0)
        page_layout.addWidget(QLabel("Page:"))
        page_layout.addWidget(self.page_spin)
        layout.addLayout(page_layout)

        # OK/Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF Files (*.pdf)")
        if file:
            self.file_edit.setText(file)

    def get_options(self):
        return {
            "file": str(self.file_edit.text()),
            "dpi": self.dpi_spin.value(),
            "page": self.page_spin.value()
        }



#---------------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())
if __name__ == "__main__":
    main()
