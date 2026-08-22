from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter, QColor
from firepro3d.paper_space import PaperScene, Sheet, SheetViewData
from tests._paper_iso_helpers import build_isolation_fixture


def _render_sheet_to_image(scene, w=400, h=400):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), QRectF(0, 0, w, h))
    p.end()
    return img


def _nonwhite_count(img):
    white = QColor("white").rgb()
    return sum(img.pixel(x, y) != white
              for x in range(img.width()) for y in range(img.height()))


def test_level3_viewport_shows_level3_not_level1_when_level1_active(qapp):
    """A Level-3 plan viewport must render Level-3 geometry even when Level 1 is
    active on-screen. Walls w1/w3 share xy, so the ONLY difference is the level."""
    fx = build_isolation_fixture()
    scene_model = fx["scene"]

    # On-screen: Level 1 active (so w3 hidden, w1 shown) — the "wrong" state.
    fx["lm"].apply_to_scene(scene_model, "Level 1")
    scene_model.active_level = "Level 1"
    scene_model.active_view_key = "plan:Plan: Level 1"
    assert fx["w3"].isVisible() is False        # sanity: L3 wall hidden on-screen
    assert fx["w1"].isVisible() is True

    # Paper: a viewport bound to the Level-3 plan.
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Plan: Level 3", "L3", 0.02, 10, 10, 0, 0)
    paper = PaperScene(sheet, fx["resolver"])
    paper.add_viewport(data)

    img = _render_sheet_to_image(paper)
    assert _nonwhite_count(img) > 0

    # CRITICAL: the on-screen live scene is restored exactly — L1 shown, L3 hidden.
    assert fx["w1"].isVisible() is True
    assert fx["w3"].isVisible() is False
    assert scene_model.active_level == "Level 1"
    assert scene_model.active_view_key == "plan:Plan: Level 1"


def test_live_scene_restored_even_if_render_throws(qapp, monkeypatch):
    from PyQt6.QtGui import QImage, QPainter, QColor
    fx = build_isolation_fixture()
    scene_model = fx["scene"]
    fx["lm"].apply_to_scene(scene_model, "Level 1")
    scene_model.active_level = "Level 1"
    scene_model.active_view_key = "plan:Plan: Level 1"

    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Plan: Level 3", "L3", 0.02, 10, 10, 0, 0)
    paper = PaperScene(sheet, fx["resolver"])
    vp = paper.add_viewport(data)

    def boom(*a, **k):
        raise RuntimeError("render blew up")
    monkeypatch.setattr(scene_model, "render", boom)

    img = QImage(50, 50, QImage.Format.Format_RGB32); img.fill(QColor("white"))
    p = QPainter(img)
    try:
        vp.paint(p, None, None)
    except RuntimeError:
        pass
    p.end()

    assert scene_model.active_level == "Level 1"
    assert scene_model.active_view_key == "plan:Plan: Level 1"
    assert fx["w1"].isVisible() is True
    assert fx["w3"].isVisible() is False
