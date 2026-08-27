"""Test that _activate_paper_sheet always uses the canonical PaperSpaceWidget.

Regression guard for the duplicate-widget bug: previously _activate_paper_sheet
constructed a fresh PaperSpaceWidget on first call, so self.paper_space_widget
(the load/export/title-block target) was never the object visible in the tab.
"""

from __future__ import annotations

import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication
from PyQt6 import sip

from firepro3d import snap_engine

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from main import MainWindow


@pytest.fixture(scope="module")
def _mw(qapp):
    """Module-scoped MainWindow singleton with safe teardown.

    Saves and restores module-level constants written by MainWindow.__init__
    via QSettings (snap tolerance) so this module's construction does not
    bleed into other test modules.
    """
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win.close()
    win.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def test_activate_paper_sheet_uses_canonical_widget(_mw):
    """_activate_paper_sheet must add/show self.paper_space_widget in the tab bar.

    The visible current widget must be the exact same object as
    mw.paper_space_widget, sharing the same paper_scene instance, so that
    load, export, title-block edits, and (later) the undo stack all bind to
    the one live scene.
    """
    mw = _mw
    mw._activate_paper_sheet("Layout 1")

    current = mw.central_tabs.currentWidget()
    assert current is mw.paper_space_widget, (
        "central_tabs current widget must be the canonical paper_space_widget, "
        f"got {type(current).__name__!r} instead"
    )
    assert current.paper_scene is mw.paper_space_widget.paper_scene, (
        "paper_scene on the visible tab must be the same object as on "
        "mw.paper_space_widget (no duplicate scene)"
    )


def test_activate_paper_sheet_idempotent(_mw):
    """Calling _activate_paper_sheet twice must not add a second tab."""
    mw = _mw
    mw._activate_paper_sheet("Layout 1")
    count_first = mw.central_tabs.count()

    mw._activate_paper_sheet("Layout 1")
    count_second = mw.central_tabs.count()

    assert count_second == count_first, (
        "A second call to _activate_paper_sheet must not create an additional tab"
    )
    assert mw.central_tabs.currentWidget() is mw.paper_space_widget


def test_closing_paper_tab_preserves_singleton_widget(_mw):
    """Closing the paper tab must NOT destroy the canonical paper widget.

    Regression for RuntimeError('wrapped C/C++ object of type
    PaperSpaceWidget has been deleted'): _on_tab_close_requested
    unconditionally called widget.deleteLater(), destroying the persistent
    self.paper_space_widget when its tab was closed. The next paper access
    (_push_sheet_list → central_tabs.indexOf) then raised.
    """
    mw = _mw
    mw._activate_paper_sheet("Layout 1")
    idx = mw.central_tabs.indexOf(mw.paper_space_widget)
    assert idx != -1

    mw._on_tab_close_requested(idx)
    # The real crash happened once the event loop processed the scheduled
    # DeferredDelete, not synchronously at close — force it here so a
    # regression bites deterministically.
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    assert not sip.isdeleted(mw.paper_space_widget), (
        "paper_space_widget was destroyed on tab close; it is a persistent "
        "singleton (like the 3D Model tab) and must survive close/reopen"
    )
    # The exact call that raised in the field must now succeed.
    mw._push_sheet_list()
    # And the paper tab must be re-openable.
    mw._activate_paper_sheet("Layout 1")
    assert mw.central_tabs.currentWidget() is mw.paper_space_widget
