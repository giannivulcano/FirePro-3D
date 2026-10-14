"""The suite's autouse in-memory clipboard (tests/conftest.py).

Copy / cut / paste tests must not depend on the OS clipboard, which refuses
writes whenever another process holds it.
"""
import json

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from tests._modify_tools_helpers import add_primitive
from tests._snap_polish_helpers import click, close_view, make_view
from tests.conftest import FakeClipboard


def test_copy_then_paste_round_trips_through_the_fake(qapp):
    """The app's real Copy -> Paste path lands and reads back with no OS clipboard."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        n0 = len(scene._draw_lines)
        scene._modify_ctl.start("copy")
        click(view, QPointF(400, 300))
        payload = json.loads(QApplication.clipboard().text())
        assert len(payload["items"]) == 1
        assert scene.clipboard_data() is not None
        scene.paste_items(QPointF(0, 0))
        assert len(scene._draw_lines) == n0 + 1
    finally:
        close_view(view, scene)


def test_each_test_starts_with_an_empty_clipboard_a(qapp):
    assert QApplication.clipboard().text() == ""
    QApplication.clipboard().setText("left behind")


def test_each_test_starts_with_an_empty_clipboard_b(qapp):
    """Runs after _a: the previous test's text must not leak."""
    assert QApplication.clipboard().text() == ""


def test_fake_emits_data_changed(qapp):
    clip = QApplication.clipboard()
    hits = []
    clip.dataChanged.connect(lambda: hits.append(1))
    clip.setText("x")
    clip.clear()
    assert hits == [1, 1]
    assert clip.text() == ""


@pytest.mark.real_clipboard
def test_real_clipboard_marker_opts_out(qapp):
    """The one opt-in smoke test: the marker leaves the real accessor alone."""
    assert not isinstance(QApplication.clipboard(), FakeClipboard)
