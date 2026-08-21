"""Tests for T9: title block non-selectable + module-level revisions dialog opener.

Concern 4 (part 1): the TitleBlockTemplateItem must not be selectable on the
paper canvas; its per-sheet property panel methods are removed; and the
revisions-dialog opener is relocated to a module-level function for Task 10.
"""
from PyQt6.QtWidgets import QGraphicsScene


def _scene_with_template():
    """Return a PaperScene that has a TitleBlockTemplateItem installed."""
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    from firepro3d.titleblock_template import make_default_template

    model = QGraphicsScene()

    class _PM:
        _views = {}

        def get(self, n):
            return None

    sheet = Sheet.create_default()          # ANSI D — matches make_default_template()
    scene = PaperScene(sheet, ViewResolver(model, _PM(), None, None))
    scene.set_template(make_default_template(), project_info={})
    return scene


def test_titleblock_not_selectable(qapp):
    """TitleBlockTemplateItem must have ItemIsSelectable cleared."""
    from PyQt6.QtWidgets import QGraphicsItem

    scene = _scene_with_template()
    tb = [it for it in scene.items()
          if type(it).__name__ == "TitleBlockTemplateItem"]
    assert tb, "expected a TitleBlockTemplateItem on the scene (template not installed?)"
    assert not (tb[0].flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable), (
        "TitleBlockTemplateItem must not be selectable"
    )


def test_open_revisions_dialog_is_module_level(qapp):
    """The relocated opener must be importable at module level (Task 10 will call it)."""
    from firepro3d import paper_space

    assert hasattr(paper_space, "open_revisions_dialog"), (
        "open_revisions_dialog not found at module level in firepro3d.paper_space"
    )
    assert callable(paper_space.open_revisions_dialog)


# ─────────────────────────────────────────────────────────────────────────────
# T10: Rev/Date/Edit-Revisions in SheetProperties (concern 4 part 2)
# ─────────────────────────────────────────────────────────────────────────────

def test_sheet_properties_exposes_rev_date_and_revisions(qapp):
    """SheetProperties.get_properties() must expose Rev, Date, and an Edit-Revisions button."""
    from firepro3d.paper_space import SheetProperties

    scene = _scene_with_template()
    sheet = scene._sheet
    sp = SheetProperties(sheet, None, scene_getter=lambda: scene)
    props = sp.get_properties()
    assert "Rev" in props, "Rev row missing from SheetProperties"
    assert "Date" in props, "Date row missing from SheetProperties"
    assert any(
        v.get("type") == "button" and "Revision" in str(v.get("value", ""))
        for v in props.values()
    ), "No Edit Revisions button found in SheetProperties"


def test_rev_edit_is_undoable(qapp):
    """Setting Rev via set_property must be undoable via the scene's undo stack."""
    from firepro3d.paper_space import SheetProperties

    scene = _scene_with_template()
    sheet = scene._sheet
    sp = SheetProperties(sheet, None, scene_getter=lambda: scene)
    sp.set_property("Rev", "B")
    assert sheet.title_block_fields.get("Rev") == "B", "Rev not written after set_property"
    scene.undo_stack.undo()
    assert sheet.title_block_fields.get("Rev") != "B", "Rev not reverted after undo"
