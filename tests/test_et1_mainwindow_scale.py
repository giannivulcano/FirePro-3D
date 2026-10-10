"""ET1 G1 (MainWindow half) -- a project drawing-scale change reaches an
open block editor through the units sync, a freshly opened editor is seeded
with it, and a schematic editor follows it too (smoke ruling 2026-10-10). Runs in its OWN
pytest process (module-scoped MainWindow)."""
from tests.test_constraint_pick_ribbon import mw, win_with_editor  # noqa: F401


def test_g1_project_scale_change_reaches_open_editor(win_with_editor, qapp):
    mw = win_with_editor
    ed = mw._test_editor
    old = mw.scene.scale_manager.drawing_scale
    try:
        mw.scene.scale_manager.drawing_scale = 200.0
        mw._on_project_settings_changed()
        qapp.processEvents()
        assert ed.editor_scene.scale_manager.drawing_scale == 200.0
        ed2 = mw.block_editor_manager.open_new()
        qapp.processEvents()
        assert ed2.editor_scene.scale_manager.drawing_scale == 200.0
    finally:
        mw.scene.scale_manager.drawing_scale = old
        mw._on_project_settings_changed()
        qapp.processEvents()


def test_scale_change_re_prepares_editor_ends(win_with_editor, qapp):
    """Seam fix 4 (path coverage, not RED-able: ``editor_scene.update()``
    already repaints the whole NoIndex scene): the sync re-prepares the
    editor's styled items, whose Drafting end bounds follow the new scale."""
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    from tests.lt5_support import arrow, set_ends
    mw = win_with_editor
    es = mw._test_editor.editor_scene
    old = mw.scene.scale_manager.drawing_scale
    a = arrow(length=3.0, half=1.0)
    es.register_block_definition(a)
    ln = LineItem(QPointF(0.0, 0.0), QPointF(2000.0, 0.0))
    set_ends(ln, finish=a.id)
    es.addItem(ln)
    es._draw_lines.append(ln)
    prepared = []
    orig = ln.prepareGeometryChange
    ln.prepareGeometryChange = lambda: (prepared.append(1), orig())
    try:
        mw.scene.scale_manager.drawing_scale = 100.0
        mw._on_project_settings_changed()
        h1 = ln.boundingRect().height()
        mw.scene.scale_manager.drawing_scale = 400.0
        mw._on_project_settings_changed()
        qapp.processEvents()
        assert prepared, "the scale sync did not re-prepare the editor line"
        assert ln.boundingRect().height() > 3.0 * h1, (h1, ln.boundingRect())
    finally:
        es._draw_lines.remove(ln)
        es.removeItem(ln)
        mw.scene.scale_manager.drawing_scale = old
        mw._on_project_settings_changed()
        qapp.processEvents()


def test_g1_schematic_editor_follows_project_scale_change(win_with_editor, qapp):
    """Smoke ruling 2026-10-10 (retires Q2): a schematic editor follows the
    project drawing scale like a block editor."""
    mw = win_with_editor
    ed = mw._test_editor
    old = mw.scene.scale_manager.drawing_scale
    s = None
    try:
        mw.scene.scale_manager.drawing_scale = 75.0
        mw._on_project_settings_changed()
        qapp.processEvents()
        s = mw.block_editor_manager.open_new(kind="schematic")
        qapp.processEvents()
        assert s.editor_scene.scale_manager.drawing_scale == 75.0    # seeded on open
        mw.scene.scale_manager.drawing_scale = 250.0
        mw._on_project_settings_changed()
        qapp.processEvents()
        assert s.editor_scene.scale_manager.drawing_scale == 250.0   # follows a change
        assert ed.editor_scene.scale_manager.drawing_scale == 250.0  # block editor alongside too
    finally:
        if s is not None:
            try:
                mw.block_editor_manager.close(s)
            except RuntimeError:
                pass
        mw.scene.scale_manager.drawing_scale = old
        mw._on_project_settings_changed()
        qapp.processEvents()
