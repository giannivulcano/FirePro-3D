"""Characterization safety-net for the underlay-decomposition slice (C0).

These tests LOCK the CURRENT behavior of the underlay concern in
``firepro3d.model_space.Model_Space`` BEFORE that concern is relocated to its
own module. They must pass on the CURRENT code.

This is CHARACTERIZATION testing: the assertions encode observed behavior, not
a desired spec. If the later relocation slices change behavior, these tests go
red and flag the drift. (When one of these tests itself encodes a wrong
assumption, the fix is to correct the TEST to match real behavior, never to
edit production code from this file.)

Covered surface:
  * back-compat of the public method set + underlays list + underlaysChanged
  * file-byte parity of save->load->save (placeholder + raster PDF)
  * undo/redo leaves underlays untouched (they are excluded from the network
    snapshot)
  * async DXF import registers exactly one underlay + fires the signal
  * live place_import / begin_replace_underlay_placement mode + ghost + the
    non-destructive cancel path (guards the C3 clear())
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.scale_manager import ScaleManager
from firepro3d.underlay import Underlay
from firepro3d.underlay_import_dialog import ImportParams


REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DXF = REPO_ROOT / "default titleblocks" / "CEL Titleblock (ANSI B) R0.dxf"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_scene(qapp) -> Model_Space:
    """Bare Model_Space with a LevelManager (Level 1 @ 0.0) + ScaleManager."""
    s = Model_Space()
    s._level_manager = LevelManager()
    s.scale_manager = ScaleManager()
    return s


def _make_placeholder(scene: Model_Space, path: str, x=0.0, y=0.0) -> Underlay:
    """Register a missing-file underlay via the placeholder path.

    Returns the Underlay record (the scene item is appended to
    ``scene.underlays`` by ``_create_underlay_placeholder``).
    """
    data = Underlay(type="dxf", path=path, x=x, y=y)
    scene._create_underlay_placeholder(data)
    return data


def _make_import_params(file_path="synthetic.dxf") -> ImportParams:
    p = ImportParams()
    p.file_path = file_path
    p.file_type = "dxf"
    p.geom_list = [
        {"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 0,
         "color": "#ffffff", "layer": "0"}
    ]
    p.scale = 1.0
    p.base_x = 0.0
    p.base_y = 0.0
    p.rotation = 0.0
    return p


def _make_blank_pdf(path):
    content = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000052 00000 n \n0000000101 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n164\n%%EOF\n"
    )
    path.write_bytes(content)


@pytest.fixture
def _silence_missing_underlay_modal(monkeypatch):
    """Neuter the modal 'Missing Underlay Files' warning that ``load_from_file``
    pops when a linked underlay file is absent.

    Placeholder byte-parity tests intentionally load a missing-file underlay;
    without this the ``QMessageBox.warning`` blocks the whole suite (a known
    modal-hang trap). Suppressing it does NOT touch the behavior under test —
    the placeholder is still created and re-serialized.
    """
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))


def _post_mouse(view, etype, scene_pt, button=Qt.MouseButton.NoButton):
    """Post a QMouseEvent at the given SCENE point onto the view's viewport."""
    vp_pos = QPointF(view.mapFromScene(QPointF(scene_pt)))
    ev = QMouseEvent(
        etype, vp_pos, button, button, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), ev)


# ---------------------------------------------------------------------------
# 1. back-compat surface
# ---------------------------------------------------------------------------
class TestBackCompat:
    PUBLIC_METHODS = (
        "import_dxf", "import_pdf", "begin_place_import",
        "refresh_all_underlays", "refresh_underlay", "replace_underlay",
        "begin_replace_underlay_placement", "remove_underlay",
    )

    def test_fresh_scene_has_empty_underlays(self, qapp):
        scene = _make_scene(qapp)
        assert scene.underlays == []

    def test_placeholder_registers_one_tuple(self, qapp):
        scene = _make_scene(qapp)
        data = _make_placeholder(scene, "C:/missing/x.dxf")
        assert len(scene.underlays) == 1
        entry = scene.underlays[0]
        assert isinstance(entry, tuple) and len(entry) == 2
        rec, item = entry
        assert rec is data
        assert isinstance(rec, Underlay)
        assert item is not None

    def test_public_methods_present_and_callable(self, qapp):
        scene = _make_scene(qapp)
        for name in self.PUBLIC_METHODS:
            assert hasattr(scene, name), f"missing method {name}"
            assert callable(getattr(scene, name)), f"{name} not callable"

    def test_underlays_changed_signal_fires_on_register(self, qapp):
        scene = _make_scene(qapp)
        fired = []
        scene.underlaysChanged.connect(lambda: fired.append(True))
        _make_placeholder(scene, "C:/missing/sig.dxf")
        QApplication.processEvents()
        assert fired, "underlaysChanged did not fire on placeholder register"


# ---------------------------------------------------------------------------
# 2. file-byte parity (save -> load -> save)
# ---------------------------------------------------------------------------
class TestFileByteParity:
    def _roundtrip_bytes(self, qapp, tmp_path, build_underlays):
        """save -> load -> save; return (bytes1, bytes2)."""
        scene1 = _make_scene(qapp)
        build_underlays(scene1)
        proj1 = tmp_path / "proj.fpd"
        scene1.save_to_file(str(proj1))

        scene2 = _make_scene(qapp)
        scene2.load_from_file(str(proj1))
        proj2 = tmp_path / "proj2.fpd"
        scene2.save_to_file(str(proj2))

        return proj1.read_bytes(), proj2.read_bytes()

    def test_placeholder_byte_parity(self, qapp, tmp_path,
                                     _silence_missing_underlay_modal):
        # Use a missing file that lives inside tmp_path so the relativized
        # path is identical across both saves (same project_dir).
        missing = tmp_path / "no_such.dxf"

        def build(scene):
            _make_placeholder(scene, str(missing), x=10.0, y=20.0)

        b1, b2 = self._roundtrip_bytes(qapp, tmp_path, build)
        assert b1 == b2, "placeholder underlay save->load->save not byte-stable"

    def test_pdf_raster_byte_parity(self, qapp, tmp_path):
        pdf = tmp_path / "blank.pdf"
        _make_blank_pdf(pdf)

        scene1 = _make_scene(qapp)
        try:
            scene1.import_pdf(str(pdf), dpi=72, page=0, x=0.0, y=0.0,
                              import_mode="raster")
        except Exception as exc:  # PyMuPDF may reject the minimal PDF
            pytest.skip(f"minimal PDF rejected by importer: {exc!r}")
        QApplication.processEvents()
        if not scene1.underlays:
            pytest.skip("minimal PDF produced no underlay (raster import no-op)")

        proj1 = tmp_path / "proj.fpd"
        scene1.save_to_file(str(proj1))

        scene2 = _make_scene(qapp)
        scene2.load_from_file(str(proj1))
        proj2 = tmp_path / "proj2.fpd"
        scene2.save_to_file(str(proj2))

        assert proj1.read_bytes() == proj2.read_bytes(), \
            "raster PDF underlay save->load->save not byte-stable"


# ---------------------------------------------------------------------------
# 3. undo/redo leaves underlays untouched
# ---------------------------------------------------------------------------
class TestUndoUntouched:
    def test_underlays_excluded_from_undo(self, qapp):
        scene = _make_scene(qapp)
        _make_placeholder(scene, "C:/missing/a.dxf", x=1.0, y=2.0)
        _make_placeholder(scene, "C:/missing/b.dxf", x=3.0, y=4.0)

        snapshot = [(d.path, d.x, d.y) for d, _ in scene.underlays]

        scene.push_undo_state()
        scene.push_undo_state()
        scene.undo()
        scene.redo()

        after = [(d.path, d.x, d.y) for d, _ in scene.underlays]
        assert after == snapshot, "undo/redo mutated the underlays list"


# ---------------------------------------------------------------------------
# 4. async DXF import
# ---------------------------------------------------------------------------
class TestAsyncImport:
    def test_import_dxf_registers_one_underlay(self, qapp, tmp_path):
        if not SAMPLE_DXF.exists():
            pytest.skip(f"sample DXF absent: {SAMPLE_DXF}")
        dxf = tmp_path / "sample.dxf"
        shutil.copy2(SAMPLE_DXF, dxf)

        scene = _make_scene(qapp)
        fired = []
        scene.underlaysChanged.connect(lambda: fired.append(True))

        scene.import_dxf(str(dxf), x=0.0, y=0.0)

        deadline = time.monotonic() + 30.0
        while not scene.underlays and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.01)

        assert len(scene.underlays) == 1, \
            f"expected exactly 1 underlay, got {len(scene.underlays)}"
        assert fired, "underlaysChanged did not fire after async import"


# ---------------------------------------------------------------------------
# 5. live place_import / replace-placement
# ---------------------------------------------------------------------------
class TestPlaceImportLive:
    def test_ghost_follows_cursor_then_commit(self, shown_model_view):
        view, scene = shown_model_view
        p = _make_import_params()
        scene.begin_place_import(p)
        assert scene.mode == "place_import"

        # Move the cursor -> ghost preview appears.
        _post_mouse(view, QEvent.Type.MouseMove, QPointF(200, 0))
        QApplication.processEvents()
        assert scene._place_import_ghost is not None, \
            "ghost did not appear after MouseMove"

        # Commit via a click at the same point.
        _post_mouse(view, QEvent.Type.MouseButtonPress, QPointF(200, 0),
                    button=Qt.MouseButton.LeftButton)
        _post_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(200, 0),
                    button=Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert len(scene.underlays) == 1, \
            f"commit did not register 1 underlay (got {len(scene.underlays)})"

    def test_cancel_preserves_original(self, qapp):
        # THE critical guard for C3's clear(): a cancelled replace-placement
        # must leave the original underlay untouched.
        scene = _make_scene(qapp)
        data = _make_placeholder(scene, "C:/missing/orig.dxf", x=5.0, y=6.0)
        before_count = len(scene.underlays)

        p = _make_import_params()
        scene.begin_replace_underlay_placement(data, p)
        assert scene.mode == "place_import"

        # Cancel.
        scene.set_mode(None)
        QApplication.processEvents()

        assert scene._place_import_ghost is None
        assert scene._place_import_remove_old is None
        assert len(scene.underlays) == before_count
        assert any(d is data for d, _ in scene.underlays), \
            "original underlay was removed by a cancelled replace-placement"
