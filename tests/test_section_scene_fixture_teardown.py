"""SB4b D1: ``section_scene_for`` frees its SectionScenes at teardown, so no
live C++ scene survives into a later test where an automatic GC pass could
collect it while Qt is inside one of its Python virtuals (a fatal abort,
0xC0000409). Test order matters: the first test records a weakref, the second
asserts the C++ scene is already gone WITHOUT any collect or event flush of
its own."""
import weakref

from PyQt6 import sip
from PyQt6.QtWidgets import QApplication

from firepro3d.elevation_view import SectionView

_refs = []


def test_a_section_scene_with_a_shown_view(qapp, section_scene_for):
    _ms, elev = section_scene_for("north")
    view = SectionView(elev)
    view.show()
    QApplication.processEvents()
    _refs.append(weakref.ref(elev))


def test_b_previous_section_scene_is_already_freed(qapp):
    assert _refs
    elev = _refs[0]()
    assert elev is None or sip.isdeleted(elev), \
        "section_scene_for left its SectionScene alive past teardown"
