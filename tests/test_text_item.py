"""Tests for firepro3d.text_item — the shared TextAnnotationData dataclass (C5)."""
from firepro3d.text_item import TextAnnotationData


def _stub_resolver():
    """A ViewResolver with all-None managers (safe for sheets with no views)."""
    from firepro3d.paper_space import ViewResolver
    return ViewResolver(None, None, None, None)


def _make_text(scene, height_mm=2.5):
    from firepro3d.text_item import TextItem
    d = TextAnnotationData(text="Ag", x=0.0, y=0.0, height_mm=height_mm)
    t = TextItem(d)
    scene.addItem(t)
    return t


def test_data_defaults_and_rotation_roundtrip():
    d = TextAnnotationData(text="Hi", x=1.0, y=2.0, height_mm=2.5)
    assert d.angle == 0.0
    d.angle = 30.0
    d2 = TextAnnotationData.from_dict(d.to_dict())
    assert d2.angle == 30.0
    assert d2.text == "Hi"
    assert d2.height_mm == 2.5
    for f in ("font_family", "bold", "italic", "underline",
              "opaque_bg", "align", "wrap_width_mm", "box_height_mm", "color"):
        assert hasattr(d2, f)


# ─────────────────────────────────────────────────────────────────────────────
# TextItem — unified scene-context-sized text primitive (C5.3)
# ─────────────────────────────────────────────────────────────────────────────

def test_model_scene_text_scales_with_scene(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    t = _make_text(s, height_mm=10.0)
    br = t.mapToScene(t.boundingRect()).boundingRect()
    assert br.height() >= 10.0


def test_paper_scene_text_is_device_independent(qapp):
    from firepro3d.paper_space import PaperScene, Sheet
    p = PaperScene(Sheet.create_default(), _stub_resolver())
    t = _make_text(p, height_mm=2.5)
    assert t.is_device_independent() is True


def test_model_scene_text_is_not_device_independent(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    t = _make_text(s, height_mm=2.5)
    assert t.is_device_independent() is False


def test_text_item_to_dict_from_dict_roundtrip(qapp):
    from firepro3d.text_item import TextItem
    d = TextAnnotationData(text="Hi", x=3.0, y=4.0, height_mm=2.5)
    d.angle = 15.0
    t = TextItem(d)
    t2 = TextItem.from_dict(t.to_dict())
    assert t2.data.text == "Hi" and abs(t2.data.angle - 15.0) < 1e-6
    assert t2.get_closed_path() is None
    assert t.to_dict()["type"] == "text"
    assert abs(t2.data.x - 3.0) < 1e-6 and abs(t2.data.y - 4.0) < 1e-6


def test_text_item_capabilities_drop_scale_when_rotated(qapp):
    from firepro3d.text_item import TextItem
    d = TextAnnotationData(text="X", height_mm=2.5)
    t = TextItem(d)
    assert t.manip_capabilities() == {"translate", "scale", "rotate"}
    t.set_angle(30.0)
    assert t.manip_capabilities() == {"translate", "rotate"}


def test_text_item_fill_rows_suppressed(qapp):
    from firepro3d.text_item import TextItem
    d = TextAnnotationData(text="X", height_mm=2.5)
    t = TextItem(d)
    assert t.is_fillable() is False
    props = t.get_properties()
    assert "Fill" not in props


def test_text_item_has_no_level_properties(qapp):
    from firepro3d.text_item import TextItem, TextAnnotationData
    t = TextItem(TextAnnotationData(text="x"))
    props = t.get_properties()
    keys = set(props.keys()) if isinstance(props, dict) else {p.get("name") if isinstance(p, dict) else p for p in props}
    assert "Level" not in keys
    assert "Level Offset" not in keys
    assert "Elevation" not in keys


# ─────────────────────────────────────────────────────────────────────────────
# render_outline_path — glyph-outline path for block-content compile (C5.4)
# ─────────────────────────────────────────────────────────────────────────────

def test_outline_path_nonempty_and_positive_height(qapp):
    from firepro3d.text_item import TextItem, TextAnnotationData
    t = TextItem(TextAnnotationData(text="A", x=0.0, y=0.0, height_mm=10.0))
    path = t.render_outline_path()
    assert not path.isEmpty()
    assert path.boundingRect().height() > 0.0


def test_empty_text_outline_is_empty(qapp):
    from firepro3d.text_item import TextItem, TextAnnotationData
    t = TextItem(TextAnnotationData(text="", height_mm=10.0))
    assert t.render_outline_path().isEmpty()


# ─────────────────────────────────────────────────────────────────────────────
# Model_Space wiring (containment C5.5 + C5.6) — collector + dual serialization
# ─────────────────────────────────────────────────────────────────────────────

def test_text_placed_via_press_lands_in_texts(qapp):
    from firepro3d.model_space import Model_Space
    from PyQt6.QtCore import QPointF
    s = Model_Space(scene_role="block_editor")
    s.set_mode("text")
    # _press_text(self, event, pos, snapped, item_under, node_under, pipe_under)
    # two-click place: first click anchors, second commits the box.
    s._press_text(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    s._press_text(None, QPointF(50, 20), QPointF(50, 20), None, None, None)
    texts = [i for i in s._texts if type(i).__name__ == "TextItem"]
    assert len(texts) == 1


def test_text_survives_undo_capture_restore(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.text_item import TextItem, TextAnnotationData
    s = Model_Space(scene_role="block_editor")
    t = TextItem(TextAnnotationData(text="Zed", x=3.0, y=4.0, height_mm=2.5))
    s.addItem(t); s._texts.append(t)
    snap = s._capture_network()
    s._restore_network(snap)
    assert any(getattr(i, "data", None) and i.data.text == "Zed" for i in s._texts)


def test_text_survives_file_roundtrip(qapp, tmp_path):
    from firepro3d.model_space import Model_Space
    from firepro3d.text_item import TextItem, TextAnnotationData
    s = Model_Space(scene_role="block_editor")
    t = TextItem(TextAnnotationData(text="Zed", x=3.0, y=4.0, height_mm=2.5))
    s.addItem(t); s._texts.append(t)
    f = tmp_path / "p.fpd"; s.save_to_file(str(f))
    s2 = Model_Space(scene_role="block_editor"); s2.load_from_file(str(f))
    assert any(getattr(i, "data", None) and i.data.text == "Zed" for i in s2._texts)
