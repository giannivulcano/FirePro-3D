"""SetLinkedDocumentCommand on the paper undo stack (design D6)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from firepro3d.linked_document import refresh_from_pdf
from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
from tests._linked_doc_helpers import (
    MM_PER_PT, PAGE_W_PT, TWO_PAGE, build_fixture_pdf, fixture_text, make_link,
    pdf_bytes, snapshot_text,
)


def _scene(sheet):
    return PaperScene(sheet, ViewResolver(None, None, None, None))


def _state(sheet):
    ld = sheet.linked_document
    return None if ld is None else ld.to_dict()


def _page_items(scene):
    from firepro3d.paper_space import LinkedPageItem
    return [i for i in scene.items() if isinstance(i, LinkedPageItem)]


def _badges(scene):
    from firepro3d.paper_space import LinkedPageBadge
    return [i for i in scene.items() if isinstance(i, LinkedPageBadge)]


def test_link_page_scale_unlink_each_undo_and_redo(qapp):
    from firepro3d.paper_commands import SetLinkedDocumentCommand
    sheet = Sheet.create_default()
    scene = _scene(sheet)
    stack = scene.undo_stack
    a = make_link(TWO_PAGE, 1)
    b = make_link(TWO_PAGE, 2)
    c = replace(b, scale_mode="1")
    steps = [(a, "Link Document"), (b, "Change Linked Page"),
             (c, "Change Linked Scale"), (None, "Unlink Document")]
    states = [None]
    for data, text in steps:
        stack.push(SetLinkedDocumentCommand(scene, sheet, data, text))
        states.append(_state(sheet))
    assert states[1:] == [a.to_dict(), b.to_dict(), c.to_dict(), None]
    assert stack.count() == 4 and stack.undoText() == "Unlink Document"
    for i in range(4, 0, -1):
        stack.undo()
        assert _state(sheet) == states[i - 1]
        assert len(_page_items(scene)) == (0 if states[i - 1] is None else 1)
    assert sheet.linked_document is None
    for i in range(1, 5):
        stack.redo()
        assert _state(sheet) == states[i]
        assert len(_page_items(scene)) == (0 if states[i] is None else 1)
        if i == 2:
            assert fixture_text("ALPHA", 2) in snapshot_text(sheet.linked_document)
        if i == 3:                                   # 1x: page width on the sheet
            rect = _page_items(scene)[0].placement_rect()
            assert rect.width() == pytest.approx(PAGE_W_PT * MM_PER_PT)
    stack.undo()                                     # undo the unlink
    assert fixture_text("ALPHA", 2) in snapshot_text(sheet.linked_document)


def test_undo_keeps_a_newer_refresh(qapp, tmp_path):
    from firepro3d.paper_commands import SetLinkedDocumentCommand
    src = build_fixture_pdf(tmp_path / "spec.pdf", 2)
    sheet = Sheet.create_default()
    scene = _scene(sheet)
    a = make_link(src, 1)
    scene.undo_stack.push(SetLinkedDocumentCommand(scene, sheet, a))
    scene.undo_stack.push(SetLinkedDocumentCommand(
        scene, sheet, replace(a, scale_mode="1"), "Change Linked Scale"))
    refresh_from_pdf(sheet.linked_document, pdf_bytes(2, "BETA"), 9.0, 99)
    scene.undo_stack.undo()
    assert sheet.linked_document.scale_mode == "fit"
    assert fixture_text("BETA", 1) in snapshot_text(sheet.linked_document)
    refresh_from_pdf(sheet.linked_document, pdf_bytes(2, "GAMMA"), 10.0, 100)
    scene.undo_stack.redo()                      # a later redo keeps it too
    assert sheet.linked_document.scale_mode == "1"
    assert fixture_text("GAMMA", 1) in snapshot_text(sheet.linked_document)


def test_relink_same_file_and_page_keeps_the_new_copy(qapp, tmp_path):
    from firepro3d.paper_commands import SetLinkedDocumentCommand
    src = build_fixture_pdf(tmp_path / "spec.pdf", 2)
    sheet = Sheet.create_default()
    scene = _scene(sheet)
    a = make_link(src, 1)
    scene.undo_stack.push(SetLinkedDocumentCommand(scene, sheet, a))
    fresh = replace(a)
    refresh_from_pdf(fresh, pdf_bytes(2, "BETA"), 9.0, 99)
    scene.undo_stack.push(SetLinkedDocumentCommand(
        scene, sheet, fresh, "Relink Document"))
    assert fixture_text("BETA", 1) in snapshot_text(sheet.linked_document)


def test_command_on_another_sheet_leaves_the_live_scene_alone(qapp):
    from firepro3d.paper_commands import SetLinkedDocumentCommand
    shown, other = Sheet.create_default(), Sheet.create_default()
    shown.linked_document = make_link(TWO_PAGE, 1)
    scene = _scene(shown)
    item = scene.linked_page_item()
    assert item is not None
    scene.undo_stack.push(SetLinkedDocumentCommand(scene, other,
                                                   make_link(TWO_PAGE, 2)))
    assert other.linked_document is not None
    assert scene.linked_page_item() is item      # live scene not rebuilt
    assert len(_page_items(scene)) == 1
    scene.undo_stack.undo()
    assert other.linked_document is None
    assert scene.linked_page_item() is item


def test_refresh_twice_one_item_one_badge_and_unlink_removes_both(qapp):
    from firepro3d.paper_commands import SetLinkedDocumentCommand
    sheet = Sheet.create_default()
    scene = _scene(sheet)
    stack = scene.undo_stack
    stack.push(SetLinkedDocumentCommand(scene, sheet, make_link(TWO_PAGE, 1)))
    scene.refresh_linked_page()
    scene.refresh_linked_page()
    assert len(_page_items(scene)) == 1
    assert len(_badges(scene)) == 1
    stack.push(SetLinkedDocumentCommand(scene, sheet, None, "Unlink Document"))
    assert len(_page_items(scene)) == 0
    assert len(_badges(scene)) == 0
    stack.undo()
    assert len(_page_items(scene)) == 1
    assert len(_badges(scene)) == 1
