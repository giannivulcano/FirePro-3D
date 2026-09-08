from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget

from firepro3d.model_space import Model_Space
from firepro3d.block_editor import BlockEditorManager, BlockEditorWidget
from firepro3d.construction_geometry import LineItem


def test_open_new_adds_isolated_level_less_editor_tab(qapp):
    project = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    assert isinstance(w, BlockEditorWidget)
    assert tabs.indexOf(w) != -1
    assert tabs.currentWidget() is w
    assert w.editor_scene is not project          # isolated scene
    assert isinstance(w.editor_scene, Model_Space)
    assert w.editor_scene._level_manager is None   # level-less
    assert w.editor_scene._plan_view_manager is None
    assert w._edit_block_id is None


def test_open_new_twice_makes_two_independent_tabs(qapp):
    project = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w1 = mgr.open_new()
    w2 = mgr.open_new()
    assert w1 is not w2
    assert tabs.count() == 2


def test_open_for_definition_focuses_existing(qapp):
    project = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    a = LineItem(QPointF(0, 0), QPointF(10, 0))
    defn = project.commit_block_definition(
        block_id=None, name="Corner", library="L", series="S",
        primitives=[a.to_dict()], origin=(0.0, 0.0), place_instance=False)
    w1 = mgr.open_for_definition(defn.id)
    assert w1._edit_block_id == defn.id
    n = tabs.count()
    w2 = mgr.open_for_definition(defn.id)   # same id -> focus, no new tab
    assert w2 is w1
    assert tabs.count() == n
    assert tabs.currentWidget() is w1


def test_close_removes_tab_and_untracks(qapp):
    project = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    mgr.close(w)
    assert tabs.indexOf(w) == -1
    # a fresh open still works after close
    w2 = mgr.open_new()
    assert tabs.indexOf(w2) != -1


# ---------------------------------------------------------------------------
# BE2.2a: seeding + headless Save core + dirty tracking
# ---------------------------------------------------------------------------

def _seed_dicts(qapp_unused=None):
    a = LineItem(QPointF(0, 0), QPointF(100, 0))
    b = LineItem(QPointF(100, 0), QPointF(100, 50))
    return [a.to_dict(), b.to_dict()]


def test_seed_from_dicts_populates_editor_scene(qapp):
    project = Model_Space(); tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    w.seed_from_dicts(_seed_dicts())
    assert len(w.gather_primitives()) == 2
    assert w.is_dirty() is False          # seeding is not a user edit


def test_commit_new_blank_registers_without_instance(qapp):
    project = Model_Space(); tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    w.seed_from_dicts(_seed_dicts())      # blank editor, drew geometry (no source)
    defn = w.commit_block("Sym", "Lib", "Ser")
    assert defn is not None and defn.id in project._block_definitions
    assert project.instance_count(defn.id) == 0     # blank new: no auto-instance
    assert w._edit_block_id == defn.id              # subsequent save = edit-in-place


def test_commit_seeded_create_replaces_source_with_instance(qapp):
    project = Model_Space(); tabs = QTabWidget()
    # source items live in the PROJECT scene
    from firepro3d.construction_geometry import LineItem as LI
    s1 = LI(QPointF(0, 0), QPointF(100, 0)); project.addItem(s1); project._draw_lines.append(s1)
    s2 = LI(QPointF(100, 0), QPointF(100, 50)); project.addItem(s2); project._draw_lines.append(s2)
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    w.seed_from_dicts([s1.to_dict(), s2.to_dict()], source_items=[s1, s2])
    defn = w.commit_block("Sym", "Lib", "Ser", replace_source=True)
    assert defn is not None
    assert s1 not in project._draw_lines and s2 not in project._draw_lines  # consumed
    assert project.instance_count(defn.id) == 1                              # placed


def test_commit_edit_in_place_updates_same_id(qapp):
    project = Model_Space(); tabs = QTabWidget()
    a = LineItem(QPointF(0, 0), QPointF(10, 0))
    defn = project.commit_block_definition(
        block_id=None, name="B", library="L", series="S",
        primitives=[a.to_dict()], origin=(0.0, 0.0), place_instance=True)
    v0 = defn.version
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_for_definition(defn.id)
    w.seed_from_definition(defn)
    w.seed_from_dicts(_seed_dicts())      # add more geometry
    ret = w.commit_block("B2", "L2", "S2")
    assert ret is defn and defn.version > v0
    assert (defn.name, defn.library, defn.series) == ("B2", "L2", "S2")


def test_commit_empty_editor_returns_none(qapp):
    project = Model_Space(); tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    assert w.commit_block("X", "L", "S") is None


def test_user_draw_marks_dirty(qapp):
    project = Model_Space(); tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    w.editor_scene.sceneModified.emit()   # simulate a user edit
    assert w.is_dirty() is True


def test_seed_populates_tracking_list(qapp):
    project = Model_Space(); tabs = QTabWidget()
    w = BlockEditorManager(tabs, project).open_new()
    w.seed_from_dicts(_seed_dicts())
    assert len(w.editor_scene._draw_lines) == 2       # in the tracking list, not just items()


def test_gather_includes_directly_added_drawn_primitive(qapp):
    # simulate a live draw: an item appended to a tracking list (as the draw tools do)
    project = Model_Space(); tabs = QTabWidget()
    w = BlockEditorManager(tabs, project).open_new()
    from firepro3d.construction_geometry import CircleItem as CI
    c = CI(QPointF(0, 0), 5); w.editor_scene.addItem(c); w.editor_scene._draw_circles.append(c)
    w.seed_from_dicts(_seed_dicts())                  # plus 2 seeded lines
    kinds = sorted(p.to_dict()["type"] for p in w.gather_primitives())
    assert kinds == ["draw_circle", "draw_line", "draw_line"]   # drawn + seeded both gathered


# ---------------------------------------------------------------------------
# BE2.2b: BlockSaveDialog + widget.save()
# ---------------------------------------------------------------------------

from firepro3d.block_editor import BlockSaveDialog


def test_save_dialog_values_and_validation(qapp):
    dlg = BlockSaveDialog(None, libraries=["L1"], series=["S1"], context="new")
    assert dlg.validation_error() is not None          # all blank
    dlg.name_edit.setText("N"); dlg.library_combo.setCurrentText("L1")
    dlg.series_combo.setCurrentText("S1")
    assert dlg.validation_error() is None
    v = dlg.values()
    assert v["name"] == "N" and v["library"] == "L1" and v["series"] == "S1"
    assert v["replace_source"] is True                 # non-seeded => True


def test_save_dialog_seeded_has_replace_checkbox(qapp):
    dlg = BlockSaveDialog(None, context="seeded")
    assert dlg.replace_source_cb.isChecked() is True
    dlg.replace_source_cb.setChecked(False)
    assert dlg.values()["replace_source"] is False


def test_save_dialog_validator_blocks_duplicate(qapp):
    def val(n, l, s):
        return "dup" if (n, l, s) == ("X", "L", "S") else None
    dlg = BlockSaveDialog(None, context="new", validator=val)
    dlg.name_edit.setText("X"); dlg.library_combo.setCurrentText("L")
    dlg.series_combo.setCurrentText("S")
    assert dlg.validation_error() == "dup"


def test_widget_save_commits_via_monkeypatched_dialog(qapp, monkeypatch):
    project = Model_Space(); tabs = QTabWidget()
    from firepro3d import block_editor as be
    w = be.BlockEditorManager(tabs, project).open_new()
    w.seed_from_dicts(_seed_dicts())

    class _FakeDlg:
        def __init__(self, *a, **k): pass
        def exec(self):
            from PyQt6.QtWidgets import QDialog
            return QDialog.DialogCode.Accepted
        def values(self):
            return {"name": "N", "library": "L", "series": "S",
                    "save_to_library": False, "replace_source": True}
    monkeypatch.setattr(be, "BlockSaveDialog", _FakeDlg)
    defn = w.save()
    assert defn is not None and defn.id in project._block_definitions
    assert (defn.name, defn.library, defn.series) == ("N", "L", "S")


def test_widget_save_empty_returns_none(qapp, monkeypatch):
    project = Model_Space(); tabs = QTabWidget()
    from firepro3d import block_editor as be
    import firepro3d.themed_message as tm
    monkeypatch.setattr(tm, "themed_info", lambda *a, **k: None)
    w = be.BlockEditorManager(tabs, project).open_new()
    assert w.save() is None   # no geometry


# ---------------------------------------------------------------------------
# BE2.3a: editor toolbar strip with Save button
# ---------------------------------------------------------------------------

# Editor verbs (Save / Set Origin / Import / Edit Attributes) live in the
# contextual "Block Editor" ribbon (MainWindow-built, live-only), not on a widget
# strip. The headless-testable Save core is exercised by the widget-save tests above.


# ---------------------------------------------------------------------------
# BE2.3b/c: app-shell integration — open_for_definition + seed if empty
# ---------------------------------------------------------------------------

def test_manager_open_in_editor_uses_editor_manager(qapp):
    from firepro3d.model_space import Model_Space
    from PyQt6.QtWidgets import QTabWidget
    from firepro3d.block_editor import BlockEditorManager
    from firepro3d.construction_geometry import LineItem
    from PyQt6.QtCore import QPointF
    project = Model_Space()
    a = LineItem(QPointF(0, 0), QPointF(10, 0))
    defn = project.commit_block_definition(block_id=None, name="B", library="L",
        series="S", primitives=[a.to_dict()], origin=(0.0, 0.0), place_instance=False)
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)

    # emulate _open_in_editor's core (open_for_definition + seed if empty)
    w = mgr.open_for_definition(defn.id)
    if not w.gather_primitives():
        w.seed_from_definition(defn)
    assert w._edit_block_id == defn.id
    assert len(w.gather_primitives()) == 1   # seeded from the def


# ---------------------------------------------------------------------------
# BE3a: Set-Origin core — pinned origin + persistent marker
# ---------------------------------------------------------------------------

def test_origin_defaults_to_bbox_top_left(qapp):
    project = Model_Space(); tabs = QTabWidget()
    w = BlockEditorManager(tabs, project).open_new()
    w.seed_from_dicts(_seed_dicts())     # lines spanning (0,0)-(100,50)
    o = w.origin_point()
    assert (round(o.x()), round(o.y())) == (0, 0)


def test_set_origin_point_pins_and_marks(qapp):
    project = Model_Space(); tabs = QTabWidget()
    w = BlockEditorManager(tabs, project).open_new()
    w.seed_from_dicts(_seed_dicts())
    w.set_origin_point(QPointF(100, 50))
    o = w.origin_point()
    assert (round(o.x()), round(o.y())) == (100, 50)
    assert w._origin_marker is not None
    assert w._origin_marker.pos() == QPointF(100, 50)
    assert w._origin_marker.scene() is w.editor_scene


def test_commit_uses_pinned_origin(qapp):
    project = Model_Space(); tabs = QTabWidget()
    w = BlockEditorManager(tabs, project).open_new()
    w.seed_from_dicts(_seed_dicts())
    w.set_origin_point(QPointF(25, 10))
    defn = w.commit_block("N", "L", "S")
    assert defn is not None
    assert (round(defn.origin[0]), round(defn.origin[1])) == (25, 10)


def test_seed_from_definition_restores_origin_marker(qapp):
    project = Model_Space(); tabs = QTabWidget()
    a = LineItem(QPointF(0, 0), QPointF(10, 0))
    defn = project.commit_block_definition(block_id=None, name="B", library="L",
        series="S", primitives=[a.to_dict()], origin=(7.0, 3.0), place_instance=False)
    w = BlockEditorManager(tabs, project).open_for_definition(defn.id)
    w.seed_from_definition(defn)
    o = w.origin_point()
    assert (round(o.x()), round(o.y())) == (7, 3)
    assert w._origin_marker is not None


# ---------------------------------------------------------------------------
# BE3b: live snapped Set-Origin pick + ribbon button
# ---------------------------------------------------------------------------

def test_begin_set_origin_enters_scene_mode(qapp):
    project = Model_Space(); tabs = QTabWidget()
    w = BlockEditorManager(tabs, project).open_new()
    w.begin_set_origin()
    # Reuses the scene's placement pipeline (snap + align + live marker).
    assert w.editor_scene.mode == "set_origin"


def test_origin_picked_signal_pins_and_shows_marker(qapp):
    project = Model_Space(); tabs = QTabWidget()
    w = BlockEditorManager(tabs, project).open_new()
    # The scene emits originPicked with the snapped+aligned point on click.
    w.editor_scene.originPicked.emit(QPointF(42, 17))
    assert w._origin is not None
    o = w.origin_point()
    assert (round(o.x()), round(o.y())) == (42, 17)
    assert w._origin_marker is not None
    assert w._origin_marker.scene() is w.editor_scene


def test_set_origin_press_emits_snapped_point(qapp):
    # The scene's set_origin press handler emits the (already snap/align-resolved)
    # point and returns to select mode.
    project = Model_Space(); tabs = QTabWidget()
    w = BlockEditorManager(tabs, project).open_new()
    got = []
    w.editor_scene.originPicked.connect(lambda p: got.append(p))
    w.begin_set_origin()
    w.editor_scene._press_set_origin(None, QPointF(9, 9), QPointF(3, 4),
                                     None, None, None)
    assert got and (round(got[0].x()), round(got[0].y())) == (3, 4)
    assert w.editor_scene.mode == "select"
    assert (round(w.origin_point().x()), round(w.origin_point().y())) == (3, 4)
