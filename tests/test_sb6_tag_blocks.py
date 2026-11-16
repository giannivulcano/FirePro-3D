"""SB6 D12 / D13 -- the four shipped tag blocks and their category registrations.

Raw sources: the four files under firepro3d/system_blocks/Tags/ (id, host_category,
scale mode, the @[Mark] text, keep_upright) and the design's D13 table (each
category's label field is Mark; the System default is the shipped file's id)."""
import pytest

from firepro3d import block_library
from firepro3d import system_blocks as sb
from firepro3d.assets import system_blocks_path
from firepro3d.bound_label import eligible_definition

SHIPPED = [("Wall", "WallTag.fpdb", "system-tags-walltag"),
           ("Door", "DoorTag.fpdb", "system-tags-doortag"),
           ("Window", "WindowTag.fpdb", "system-tags-windowtag"),
           ("Opening", "OpeningTag.fpdb", "system-tags-openingtag")]


@pytest.mark.parametrize("cat,fname,bid", SHIPPED, ids=[s[0] for s in SHIPPED])
def test_shipped_tag_block_is_an_eligible_annotative_tag(qapp, cat, fname, bid):
    d = block_library.load_block_file(system_blocks_path("Tags", fname))
    assert d is not None and d.id == bid
    assert d.host_category == cat
    assert eligible_definition(d, cat)                    # annotative + Scale with zoom + category
    texts = [p for p in d.primitives if p.get("type") == "text"]
    assert [t["text"] for t in texts] == ["@[Mark]"]
    assert texts[0].get("keep_upright") is True           # D5: Aligned tags read upright


def test_registries_carry_the_four_categories():
    assert sb.ANNOTATION_CATEGORIES[-4:] == ("Wall", "Door", "Window", "Opening")
    for cat, _fname, bid in SHIPPED:
        assert sb.LABEL_FIELD[cat] == "Mark"
        assert sb.SYSTEM_DEFAULTS[cat] == bid


def _scene():
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    ms._level_manager = LevelManager()
    return ms


@pytest.mark.parametrize("cat,fname,bid", SHIPPED, ids=[s[0] for s in SHIPPED])
def test_project_default_resolves_to_the_shipped_tag(qapp, real_system_library, cat, fname, bid):
    ms = _scene()
    try:
        d = ms.annotation_block(cat)
        assert d is not None and d.id == bid
    finally:
        ms.cleanup()


def test_annotation_pane_lists_the_four_rows(qapp, real_system_library):
    from firepro3d.settings.panes import AnnotationPane
    ms = _scene()
    try:
        pane = AnnotationPane(scene=ms)
        pane.load()
        for cat, _fname, bid in SHIPPED:
            combo = pane._combos[cat]
            assert bid in [combo.itemData(i) for i in range(combo.count())], cat
    finally:
        ms.cleanup()
