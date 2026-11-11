"""Sheet properties panel: the linked document rows through the real PropertyManager."""
from __future__ import annotations

import gc
import os
import shutil
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication

from firepro3d import linked_doc_service
from firepro3d.paper_space import (
    PaperScene, Sheet, SheetManager, SheetProperties, ViewResolver,
)
from firepro3d.property_manager import PropertyManager
from tests._linked_doc_helpers import (
    ONE_PAGE, TWO_PAGE, fixture_text, rewrite_by_rename, snapshot_text,
)


@pytest.fixture
def panel(qapp, tmp_path):
    mgr = SheetManager([Sheet.create_default()])
    scene = PaperScene(mgr.sheets[0], ViewResolver(None, None, None, None))
    msgs, changes, rejects = [], [], []
    svc = linked_doc_service.LinkedDocService(
        sheets_getter=lambda: mgr.sheets, scene_getter=lambda: scene,
        manager_getter=lambda: mgr,
        notify=lambda message, timeout_ms=6000: msgs.append(message))
    pm = PropertyManager()

    def show():
        pm.show_properties(SheetProperties(
            mgr.sheets[0], mgr, on_change=lambda: changes.append(1),
            on_reject=rejects.append, scene_getter=lambda: scene,
            linked_docs=svc))
        QApplication.processEvents()
        return pm._prop_widgets

    spec = tmp_path / "docs" / "spec.pdf"
    spec.parent.mkdir(parents=True)
    shutil.copyfile(TWO_PAGE, spec)
    yield SimpleNamespace(pm=pm, show=show, scene=scene, mgr=mgr, svc=svc,
                          msgs=msgs, changes=changes, rejects=rejects,
                          spec=spec, tmp=tmp_path)
    svc.shutdown()
    pm._refresh_timer.stop()
    pm.close()
    pm.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    gc.collect()


def _link(p, monkeypatch, path, choice=(1, False)):
    monkeypatch.setattr(linked_doc_service, "choose_linked_file",
                        lambda parent=None, start_dir="": str(path))
    monkeypatch.setattr(linked_doc_service, "pick_linked_page",
                        lambda parent, name, n: choice)
    p.show()["Linked Document"].click()


def test_unlinked_sheet_offers_link(panel):
    w = panel.show()
    assert w["Linked Document"].text() == "Link…"
    assert w["Linked Document"].isEnabled()
    assert "Linked Page" not in w and "Page Scale" not in w


def test_link_picks_a_page_and_creates_the_other_sheets(panel, monkeypatch):
    probe = SheetManager([Sheet.create_default()])      # suggest_number sequence
    expected = probe.create().number
    _link(panel, monkeypatch, panel.spec, choice=(1, True))
    first, *rest = panel.mgr.sheets
    assert first.linked_document.page == 1
    assert [s.number for s in rest] == [expected]
    assert rest[0].linked_document.page == 2
    assert fixture_text("ALPHA", 2) in snapshot_text(rest[0].linked_document)
    assert panel.scene.undo_stack.count() == 1
    w = panel.show()
    assert w["Linked Document"].text() == "spec.pdf, page 1"
    assert w["Scale Used"].text() == "2x"                # fit on ANSI D
    panel.scene.undo_stack.undo()
    assert first.linked_document is None
    assert len(panel.mgr.sheets) == 2                    # sheet ops not undoable


def test_page_row_changes_the_page_undoably(panel, monkeypatch):
    _link(panel, monkeypatch, panel.spec)
    panel.show()["Linked Page"].setCurrentText("2")
    ld = panel.mgr.sheets[0].linked_document
    assert ld.page == 2
    assert fixture_text("ALPHA", 2) in snapshot_text(ld)
    panel.scene.undo_stack.undo()
    assert panel.mgr.sheets[0].linked_document.page == 1


def test_scale_rows_fixed_and_custom(panel, monkeypatch):
    _link(panel, monkeypatch, panel.spec)
    panel.show()["Page Scale"].setCurrentText("1x")
    assert panel.mgr.sheets[0].linked_document.scale_mode == "1"
    assert panel.show()["Scale Used"].text() == "1x"
    monkeypatch.setattr(linked_doc_service, "ask_custom_scale",
                        lambda parent, initial: 1.5)
    panel.show()["Page Scale"].setCurrentText("Custom...")
    ld = panel.mgr.sheets[0].linked_document
    assert (ld.scale_mode, ld.scale_custom) == ("custom", 1.5)
    w = panel.show()
    assert w["Page Scale"].currentText() == "Custom (1.5x)"
    assert w["Scale Used"].text() == "1.5x"
    panel.scene.undo_stack.undo()
    panel.scene.undo_stack.undo()
    assert panel.mgr.sheets[0].linked_document.scale_mode == "fit"


def test_unlink_and_undo(panel, monkeypatch):
    _link(panel, monkeypatch, panel.spec)
    saved = panel.mgr.sheets[0].linked_document.to_dict()
    panel.show()["ld_unlink"].click()
    assert panel.mgr.sheets[0].linked_document is None
    panel.scene.undo_stack.undo()
    assert panel.mgr.sheets[0].linked_document.to_dict() == saved


def test_relink_keeps_the_page_within_the_new_file(panel, monkeypatch):
    _link(panel, monkeypatch, panel.spec, choice=(2, False))
    other = panel.tmp / "other.pdf"
    shutil.copyfile(ONE_PAGE, other)
    monkeypatch.setattr(linked_doc_service, "choose_linked_file",
                        lambda parent=None, start_dir="": str(other))
    panel.show()["ld_relink"].click()
    ld = panel.mgr.sheets[0].linked_document
    assert (os.path.normcase(ld.path), ld.page) == (
        os.path.normcase(str(other)), 1)
    panel.scene.undo_stack.undo()
    ld = panel.mgr.sheets[0].linked_document
    assert (os.path.normcase(ld.path), ld.page) == (
        os.path.normcase(str(panel.spec)), 2)


def test_open_button_opens_the_file_and_is_disabled_when_missing(panel,
                                                                  monkeypatch):
    opened = []
    monkeypatch.setattr(os, "startfile", lambda p: opened.append(p),
                        raising=False)
    _link(panel, monkeypatch, panel.spec)
    w = panel.show()
    assert w["ld_open"].text() == "Open PDF" and w["ld_open"].isEnabled()
    w["ld_open"].click()
    assert [os.path.normcase(p) for p in opened] == [
        os.path.normcase(str(panel.spec))]
    os.remove(panel.spec)
    w = panel.show()
    assert not w["ld_open"].isEnabled() and not w["ld_refresh"].isEnabled()


def test_open_in_word_label_for_a_docx(panel, monkeypatch):
    _link(panel, monkeypatch, panel.spec)
    docx = panel.tmp / "spec.docx"
    docx.write_bytes(b"stand-in")
    panel.mgr.sheets[0].linked_document.path = str(docx)
    assert panel.show()["ld_open"].text() == "Open in Word"


def test_refresh_button_takes_a_new_copy_without_an_undo_step(panel,
                                                              monkeypatch):
    _link(panel, monkeypatch, panel.spec)
    count = panel.scene.undo_stack.count()
    rewrite_by_rename(panel.spec, 2, "BETA-CHANGED")
    panel.show()["ld_refresh"].click()
    assert fixture_text("BETA-CHANGED", 1) in snapshot_text(
        panel.mgr.sheets[0].linked_document)
    assert panel.scene.undo_stack.count() == count
    assert "Updated spec.pdf on 1 sheet(s)" in panel.msgs
