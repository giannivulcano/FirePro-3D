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


def test_m2_tags_follow_a_retargeted_system_copy(qapp, make_model_space, real_system_library,
                                                  tmp_path):
    """User ruling (VC9 M2): editing a System tag in Block Manager and saving it as a project
    copy re-points the placed tags, and the next committed step (repose_tag ->
    hosted_tag.resolve) keeps the copy instead of snapping back to the System default.
    The copy is built as ``block_editor.run_duplicate_dialog`` / ``BlockManager
    ._duplicate_and_retarget`` do (file copy under a new id, loaded, retargeted)."""
    import uuid
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.level_manager import LevelManager
    from tests._sb6_helpers import add_wall, place_tag, tags_of
    ms = make_model_space()
    ms._level_manager = LevelManager()
    w = add_wall(ms)
    ms.push_undo_state()
    tag = place_tag(ms, w)
    src = ms.get_block_definition(tag.block_id)
    copy = BlockDefinition.from_dict(src.to_dict())
    copy.id, copy.version, copy.base_version = uuid.uuid4().hex, 1, None
    copy.name, copy.library, copy.series = "Wall tag copy", "Mine", "Tags"
    written = block_library.save_to_library(copy, root=str(tmp_path),
                                            bundled=ms.block_registry.bundle_for(src.id))
    assert copy.id in ms.load_blocks_outside_history([written], root=str(tmp_path))
    assert eligible_definition(ms.get_block_definition(copy.id), "Wall")  # the copy is a valid tag
    assert ms.retarget_block_refs(src.id, copy.id) >= 1
    ms.push_undo_state()                                                  # re-poses every bound tag
    (t,) = tags_of(ms)
    assert t.block_id == copy.id                                          # [RED: tag["block"] write]
    assert t.tag["block"] == copy.id
