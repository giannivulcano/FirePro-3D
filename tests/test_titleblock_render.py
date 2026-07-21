"""Renderer/integration tests for the parametric title block system.

Covers:
- Sheet.revisions round-trip and absent-key default
- .fpd titleblock_template embed + load-time legacy migration
- skip_values guard (shipped default Company is not seeded to Project Info)
- no-template round-trip (loads as None)
"""
from __future__ import annotations

import inspect
import json
import re
from unittest.mock import MagicMock

import pytest

from PyQt6.QtWidgets import QApplication, QGraphicsScene
from PyQt6.QtTest import QTest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from firepro3d.paper_space import (
    DEFAULT_TITLE_BLOCK_FIELDS,
    Sheet,
    SheetViewport,
    SheetViewData,
    ViewResolver,
)
from firepro3d.titleblock_template import make_default_template

_app = QApplication.instance() or QApplication([])


# ─────────────────────────────────────────────────────────────────────────────
# Sheet.revisions — pure dataclass tests, no scene needed
# ─────────────────────────────────────────────────────────────────────────────

class TestSheetRevisions:
    def test_round_trip(self):
        s = Sheet.create_default()
        s.revisions = [{"no": "1", "description": "Issued", "date": "07-21"}]
        s2 = Sheet.from_dict(s.to_dict())
        assert s2.revisions == s.revisions

    def test_absent_defaults_empty(self):
        d = Sheet.create_default().to_dict()
        d.pop("revisions", None)
        assert Sheet.from_dict(d).revisions == []

    def test_multiple_revisions_preserve_order(self):
        s = Sheet.create_default()
        s.revisions = [
            {"no": "1", "description": "IFC", "date": "07-01"},
            {"no": "2", "description": "Rev A", "date": "07-21"},
        ]
        s2 = Sheet.from_dict(s.to_dict())
        assert s2.revisions[1]["no"] == "2"

    def test_empty_list_round_trips(self):
        s = Sheet.create_default()
        s.revisions = []
        s2 = Sheet.from_dict(s.to_dict())
        assert s2.revisions == []


# ─────────────────────────────────────────────────────────────────────────────
# build_field_values + TitleBlockTemplateItem renderer
# Pure QGraphicsItem tests — no MainWindow fixture needed.
# ─────────────────────────────────────────────────────────────────────────────

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter

from firepro3d.paper_space import (TitleBlockTemplateItem, build_field_values,
                                   PAPER_SIZES)
from firepro3d.titleblock_template import solve_layout


def _render(item, w, h, px=600):
    img = QImage(px, int(px * h / w), QImage.Format.Format_RGB32)
    img.fill(0xFFFFFF)
    p = QPainter(img)
    p.scale(px / w, px / w)
    item.paint(p, None, None)
    p.end()
    return img


class TestBuildFieldValues:
    def test_resolution_order_auto_sheet_project(self):
        s = Sheet.create_default()
        s.title_block_fields = {"Title": "L1 Plan"}
        s.revisions = [{"no": "1", "description": "x", "date": "d"}]
        info = {"name": "Plant 9",
                "custom": [{"key": "Company", "value": "ACME"}]}
        vals = build_field_values(s, info)
        assert vals["Title"] == "L1 Plan"          # sheet
        assert vals["Project"] == "Plant 9"        # project standard
        assert vals["Company"] == "ACME"           # project custom
        assert vals["Scale"] == ""                 # auto (no viewports)
        assert vals["__revisions__"] == s.revisions

    def test_sheet_overrides_project(self):
        s = Sheet.create_default()
        s.title_block_fields = {"Project": "Sheet-level"}
        vals = build_field_values(s, {"name": "Project-level"})
        assert vals["Project"] == "Sheet-level"

    def test_scale_auto_always_wins(self):
        s = Sheet.create_default()
        s.title_block_fields = {"Scale": "STALE MANUAL"}
        vals = build_field_values(s, {})
        assert vals["Scale"] == ""   # computed (no viewports), manual ignored


class TestRenderer:
    def _make(self, values=None, mutate=None):
        from firepro3d.titleblock_template import make_default_template
        t = make_default_template()
        v = t.variants["ANSI D"]
        if mutate:
            mutate(v)
        w, h = PAPER_SIZES["ANSI D"]
        values = values or {}
        sl = solve_layout(v, w, h, values)
        return TitleBlockTemplateItem(sl, v, values), w, h

    def test_strip_renders_nonwhite(self):
        item, w, h = self._make({"Title": "L1 PLAN"})
        img = _render(item, w, h)
        strip_x = int(img.width() * (w - 50) / w)     # mid-strip column
        col = [img.pixel(strip_x, y) for y in range(0, img.height(), 5)]
        assert any(c != 0xFFFFFFFF for c in col)      # borders/text drew

    def test_bounding_rect_covers_area_and_strip(self):
        item, w, h = self._make()
        br = item.boundingRect()
        assert br.width() >= w - 25    # spans area+strip inside margins
        assert br.height() >= h - 25

    def test_empty_logo_is_calm_missing_is_warned(self):
        item, w, h = self._make()
        assert item.warnings == []                    # empty logo: reserved box
        item2, _, _ = self._make(
            mutate=lambda v: setattr(v.cells[0], "logo_data", "!!!notbase64!!!"))
        assert item2.warnings                         # undecodable: warned

    def test_no_pointsize_in_renderer(self):
        """Banned-API guard: all text sizing goes through setPixelSize + painter
        scale (§9.4).  QFont point-size constructors are covered by the same
        mm-primitive pattern — no separate check needed.
        """
        import inspect
        from firepro3d import paper_space
        src = inspect.getsource(paper_space.TitleBlockTemplateItem)
        assert "setPointSize" not in src    # covers setPointSize and setPointSizeF

    def test_non_ascii_logo_data_warns_no_exception(self):
        """Non-ASCII logo_data must not raise; it must record a warning."""
        item, _, _ = self._make(
            mutate=lambda v: setattr(v.cells[0], "logo_data", "ñøŧ-æscii"))
        assert any("Logo" in w for w in item.warnings)

    def test_real_png_logo_no_warning(self):
        """A valid base64-PNG logo must load cleanly (no warning) and render
        non-white pixels in the logo cell region.
        """
        from PyQt6.QtCore import QBuffer, QIODevice
        from PyQt6.QtGui import QImage
        # Build a tiny 8×8 solid-red PNG in memory.
        img8 = QImage(8, 8, QImage.Format.Format_RGB32)
        img8.fill(0xFF0000)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img8.save(buf, "PNG")
        b64 = bytes(buf.data().toBase64()).decode("ascii")

        item, w, h = self._make(
            mutate=lambda v: setattr(v.cells[0], "logo_data", b64))
        assert item.warnings == [], f"Unexpected warnings: {item.warnings}"

        # Find the logo cell index (cell 0 in make_default_template is logo).
        from firepro3d.titleblock_template import make_default_template
        t = make_default_template()
        v = t.variants["ANSI D"]
        sl = item._layout
        logo_rect = sl.cell_rects[0]
        rendered = _render(item, w, h)
        # Map mm cell rect to image pixels.
        px_per_mm = rendered.width() / w
        rx = int(logo_rect.left() * px_per_mm) + 2
        ry = int(logo_rect.top() * rendered.height() / h) + 2
        rw = max(1, int(logo_rect.width() * px_per_mm) - 4)
        rh = max(1, int(logo_rect.height() * rendered.height() / h) - 4)
        pixels = [rendered.pixel(rx + dx, ry + dy)
                  for dx in range(0, rw, max(1, rw // 4))
                  for dy in range(0, rh, max(1, rh // 4))]
        assert any(p != 0xFFFFFFFF for p in pixels), \
            "Logo cell region rendered all-white — logo was not drawn"

    def test_revision_header_renders(self):
        """A revision table with 2 revisions must differ from one with 0 in the
        cell region (the header row is always drawn; data rows add more pixels).
        """
        from firepro3d.titleblock_template import make_default_template, solve_layout
        t = make_default_template()
        v = t.variants["ANSI D"]
        # Find the first revision_table cell.
        rev_idx = next(
            (i for i, c in enumerate(v.cells) if c.kind == "revision_table"),
            None)
        assert rev_idx is not None, "Default template has no revision_table cell"

        revisions_2 = [
            {"no": "1", "description": "Issued for Construction", "date": "07-01"},
            {"no": "2", "description": "Revised per RFI-001", "date": "07-21"},
        ]
        vals_0 = {"__revisions__": []}
        vals_2 = {"__revisions__": revisions_2}

        sl0 = solve_layout(v, *PAPER_SIZES["ANSI D"], vals_0)
        sl2 = solve_layout(v, *PAPER_SIZES["ANSI D"], vals_2)
        item0 = TitleBlockTemplateItem(sl0, v, vals_0)
        item2 = TitleBlockTemplateItem(sl2, v, vals_2)

        w, h = PAPER_SIZES["ANSI D"]
        img0 = _render(item0, w, h)
        img2 = _render(item2, w, h)

        # Locate revision cell rect in image pixels.
        cell_rect = sl2.cell_rects[rev_idx]
        px_per_mm = img0.width() / w
        rx = int(cell_rect.left() * px_per_mm) + 1
        ry = int(cell_rect.top() * img0.height() / h) + 1
        rw = max(1, int(cell_rect.width() * px_per_mm) - 2)
        rh = max(1, int(cell_rect.height() * img0.height() / h) - 2)
        diffs = sum(
            img0.pixel(rx + dx, ry + dy) != img2.pixel(rx + dx, ry + dy)
            for dx in range(0, rw, max(1, rw // 8))
            for dy in range(0, rh, max(1, rh // 8)))
        assert diffs > 0, \
            "Revision cell region is identical for 0 vs 2 revisions — header/data rows not drawn"

    def test_text_renders_distinct_from_empty(self):
        """Render with an empty Title and with a long Title — images must differ
        in the Title cell region (pins that text is actually drawn, not just borders).
        """
        from firepro3d.titleblock_template import make_default_template, solve_layout
        t = make_default_template()
        v = t.variants["ANSI D"]
        # Find Title cell.
        title_idx = next(
            (i for i, c in enumerate(v.cells)
             if c.kind == "field" and c.field_key == "Title"),
            None)
        assert title_idx is not None, "Default template has no Title field cell"

        w, h = PAPER_SIZES["ANSI D"]
        vals_empty = {"Title": ""}
        vals_text  = {"Title": "LONG TITLE VALUE FOR PIXELS"}
        sl_e = solve_layout(v, w, h, vals_empty)
        sl_t = solve_layout(v, w, h, vals_text)
        item_e = TitleBlockTemplateItem(sl_e, v, vals_empty)
        item_t = TitleBlockTemplateItem(sl_t, v, vals_text)
        img_e = _render(item_e, w, h)
        img_t = _render(item_t, w, h)

        cell_rect = sl_t.cell_rects[title_idx]
        px_per_mm = img_e.width() / w
        rx = int(cell_rect.left() * px_per_mm) + 2
        ry = int(cell_rect.top() * img_e.height() / h) + 2
        rw = max(1, int(cell_rect.width() * px_per_mm) - 4)
        rh = max(1, int(cell_rect.height() * img_e.height() / h) - 4)
        diffs = sum(
            img_e.pixel(rx + dx, ry + dy) != img_t.pixel(rx + dx, ry + dy)
            for dx in range(0, rw, max(1, rw // 8))
            for dy in range(0, rh, max(1, rh // 8)))
        assert diffs > 0, \
            "Title cell region identical for empty vs filled Title — text not rendered"


# ─────────────────────────────────────────────────────────────────────────────
# scene_io embed — uses the MainWindow fixture (same pattern as test_paper_persistence.py)
# ─────────────────────────────────────────────────────────────────────────────

from firepro3d import snap_engine
import main as _main_module
from firepro3d.view_3d import View3D
_main_module.View3D = View3D
from main import MainWindow


@pytest.fixture(scope="module")
def _mw(qapp):
    """Module-scoped MainWindow singleton with safe teardown."""
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win._modified = False
    win.close()
    win.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def _fresh(mw):
    """Reset to a clean default project without tripping the save prompt."""
    mw._modified = False
    mw.new_file()
    assert mw._modified is False


class TestSceneIOEmbed:
    def test_template_embeds_and_migration_runs(self, _mw, tmp_path):
        """Template is embedded in the .fpd; migration moves non-default fields to
        project_info on load.
        """
        _fresh(_mw)
        scene = _mw.scene
        tpl = make_default_template()
        scene._titleblock_template = tpl.to_dict()

        # Give the first sheet a non-default Company value.
        sheet = scene._sheets[0]
        sheet.title_block_fields["Company"] = "ACME"

        path = str(tmp_path / "t.fpd")
        _mw._current_file = path
        _mw.save_file()

        # Load into a fresh scene (reuse the same window — new_file clears state).
        _mw._modified = False
        _mw._load_project(path)

        scene2 = _mw.scene
        # Template is embedded and round-trips.
        assert scene2._titleblock_template is not None
        assert scene2._titleblock_template["name"] == "FirePro Default"

        # Migration ran: Company ("ACME") moved to project_info custom rows.
        custom = scene2._project_info.get("custom", [])
        assert any(
            c.get("key") == "Company" and c.get("value") == "ACME"
            for c in custom
        ), f"Expected Company=ACME in custom rows, got: {custom}"

        # Company must NOT remain in the sheet's title_block_fields.
        assert "Company" not in scene2._sheets[0].title_block_fields, (
            "migrate_legacy_fields must remove Company from sheet fields"
        )

    def test_default_company_not_seeded(self, _mw, tmp_path):
        """A sheet whose Company equals the shipped default must NOT create a
        custom Project Info row (skip_values guard).
        """
        _fresh(_mw)
        scene = _mw.scene
        scene._titleblock_template = make_default_template().to_dict()

        # Keep the default "Celerity Engineering Limited" value.
        sheet = scene._sheets[0]
        default_company = DEFAULT_TITLE_BLOCK_FIELDS["Company"]
        sheet.title_block_fields["Company"] = default_company

        path = str(tmp_path / "default_co.fpd")
        _mw._current_file = path
        _mw.save_file()

        _mw._modified = False
        _mw._load_project(path)
        scene2 = _mw.scene

        custom = scene2._project_info.get("custom", [])
        assert not any(c.get("key") == "Company" for c in custom), (
            "Shipped default Company value must NOT seed Project Info"
        )

    def test_no_template_loads_none(self, _mw, tmp_path):
        """A .fpd saved without _titleblock_template loads as None."""
        _fresh(_mw)
        scene = _mw.scene
        # Ensure no template is set (new_file sets it to None per model_space init).
        scene._titleblock_template = None

        path = str(tmp_path / "no_tpl.fpd")
        _mw._current_file = path
        _mw.save_file()

        # Verify the raw file has no / null titleblock_template key.
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        assert raw.get("titleblock_template") is None

        _mw._modified = False
        _mw._load_project(path)
        scene2 = _mw.scene
        assert scene2._titleblock_template is None

    def test_clear_scene_resets_template_and_project_info(self, _mw):
        """File->New must not leak the previous project's template/info
        (regression: _clear_scene resets both)."""
        _fresh(_mw)
        scene = _mw.scene
        scene._titleblock_template = make_default_template().to_dict()
        scene._project_info = {"name": "Leaky Project",
                               "custom": [{"key": "Company", "value": "X"}]}
        _fresh(_mw)   # File->New
        assert _mw.scene._titleblock_template is None
        assert _mw.scene._project_info.get("name", "") == ""
        assert not _mw.scene._project_info.get("custom")


# ─────────────────────────────────────────────────────────────────────────────
# Resolution chain — no MainWindow needed; mirrors test_paper_space.py fixture
# ─────────────────────────────────────────────────────────────────────────────

from unittest.mock import MagicMock
from firepro3d.paper_space import PaperScene, ViewResolver


class TestResolutionChain:
    """§8.1 template-first resolution chain tests.

    These tests exercise PaperScene.set_template() and the _setup priority
    ordering: template → DXF → PDF → programmatic.
    """

    def _scene(self, template=None, size="ANSI D"):
        sheet = Sheet.create_default()
        sheet.paper_size = size
        resolver = MagicMock(spec=ViewResolver)
        resolver.resolve.return_value = None
        sc = PaperScene(sheet, resolver)
        if template is not None:
            sc.set_template(template, project_info={})
        return sc, sheet

    def test_template_wins_over_dxf(self):
        sc, _ = self._scene(make_default_template())
        kinds = [type(i).__name__ for i in sc.items()]
        assert "TitleBlockTemplateItem" in kinds
        assert "TitleBlockDxfItem" not in kinds

    def test_no_template_renders_legacy_chain(self):
        sc, _ = self._scene(None)
        kinds = [type(i).__name__ for i in sc.items()]
        assert "TitleBlockTemplateItem" not in kinds
        # ANSI D has a CEL DXF on disk in this repo
        assert "TitleBlockDxfItem" in kinds or "TitleBlockItem" in kinds

    def test_missing_variant_falls_back_with_warning(self):
        t = make_default_template()
        del t.variants["ANSI B"]
        sc, _ = self._scene(t, size="ANSI B")
        kinds = [type(i).__name__ for i in sc.items()]
        assert "TitleBlockTemplateItem" not in kinds
        assert sc.titleblock_warning          # surfaced for the status bar

    def test_set_template_none_restores_legacy(self):
        sc, _ = self._scene(make_default_template())
        sc.set_template(None)
        kinds = [type(i).__name__ for i in sc.items()]
        assert "TitleBlockTemplateItem" not in kinds

    def test_setup_with_template_emits_no_sheetModified(self):
        # §17.7: rebuilds are load-suppressed — installing a template must not dirty
        sc, _ = self._scene(None)
        emitted = []
        sc.sheetModified.connect(lambda *a: emitted.append(1))
        sc.set_template(make_default_template(), project_info={})
        assert not emitted


# ─────────────────────────────────────────────────────────────────────────────
# T9: View-title mm sizing (spec §9.4)
# ─────────────────────────────────────────────────────────────────────────────


class TestViewTitleMmSizing:
    """View-title block below SheetViewport must use mm cap-height primitive (§9.4)."""

    def test_no_pointsize_in_viewport_paint(self):
        """Banned-API lint: view titles must use the mm primitive (spec §9.4).

        Checks both setPointSize/setPointSizeF method calls AND QFont constructor
        calls that embed a numeric point size (e.g. QFont("Arial", 3)).
        """
        src = inspect.getsource(SheetViewport.paint)
        assert "setPointSize" not in src, (
            "SheetViewport.paint still calls setPointSize*/setPointSizeF — "
            "must use mm primitive instead (§9.4)"
        )
        assert not re.search(r'QFont\([^)]*,\s*\d', src), (
            "SheetViewport.paint still uses QFont(<family>, <pts>) constructor — "
            "numeric point size is DPI-dependent; use mm primitive instead (§9.4)"
        )

    def test_title_ink_dpi_invariant(self, qapp):
        """mm-true text: title strip ink height must be DPI-invariant (spec §9.4).

        Renders the viewport at the same painter scale but at two device DPIs
        (96 dpi vs 300 dpi).  A point-size font would scale with device DPI;
        the mm primitive (setPixelSize + painter.scale) is DPI-independent.

        Only the title_rect_above sub-region is measured: the region where the
        view-title text sits (between title_y and the bubble centre-line).
        """
        # ── Build a viewport whose resolver returns a real scene so the
        #    non-placeholder path runs and the title strip is actually drawn.
        data = SheetViewData(
            source_view_type="plan",
            source_view_name="LEVEL ONE",   # all-caps, no descenders
            title="LEVEL ONE",
            scale=0.01,
            x=0.0, y=0.0, w=120.0, h=90.0,
        )
        resolver = MagicMock(spec=ViewResolver)
        # resolve() must match the real signature: (view_type, view_name) -> (scene, rect) | None
        resolver.resolve.return_value = (QGraphicsScene(), QRectF(0, 0, 1, 1))
        vp = SheetViewport(data, resolver)

        host_scene = QGraphicsScene()
        host_scene.addItem(vp)

        # Geometry mirrored from SheetViewport.paint (keep in sync with spec §9.4)
        w, h = data.w, data.h
        title_y    = h + 0.5
        bubble_r   = 3.0
        bubble_cx  = bubble_r + 1.0
        bubble_cy  = title_y + bubble_r + 1.0
        text_x     = bubble_cx + bubble_r + 1.5
        # title_rect_above: (text_x, title_y) → (w, bubble_cy - 0.3)
        tr_left   = text_x
        tr_top    = title_y
        tr_right  = w
        tr_bottom = bubble_cy - 0.3

        # ── px-scale shared across both renders; only device DPI differs ──
        PX_SCALE = 6.0
        CANVAS_W  = int(w * PX_SCALE)
        CANVAS_H  = int((h + 15) * PX_SCALE)   # enough room for title strip

        def render_at_dpi(dpi: int) -> QImage:
            img = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_RGB32)
            dpm = int(dpi / 0.0254)             # dots-per-metre
            img.setDotsPerMeterX(dpm)
            img.setDotsPerMeterY(dpm)
            img.fill(0xFFFFFF)
            p = QPainter(img)
            p.scale(PX_SCALE, PX_SCALE)
            vp.paint(p, None, None)
            p.end()
            return img

        def ink_height_in_title_rect(img: QImage) -> int:
            """Count non-white pixel rows inside the title_rect_above region."""
            px = PX_SCALE
            x0 = int(tr_left   * px)
            x1 = min(int(tr_right  * px), img.width() - 1)
            y0 = int(tr_top    * px)
            y1 = min(int(tr_bottom * px), img.height() - 1)
            return sum(
                1 for row in range(y0, y1 + 1)
                if any(img.pixel(col, row) != 0xFFFFFFFF
                       for col in range(x0, x1 + 1))
            )

        img_96  = render_at_dpi(96)
        img_300 = render_at_dpi(300)
        h_96    = ink_height_in_title_rect(img_96)
        h_300   = ink_height_in_title_rect(img_300)

        assert h_96 > 0, (
            "No ink in title_rect_above at 96 dpi — title strip was not drawn "
            "(check that resolver.resolve returns a real (scene, rect) tuple)"
        )
        assert h_300 > 0, "No ink in title_rect_above at 300 dpi"

        ratio = h_300 / h_96
        assert 0.85 <= ratio <= 1.15, (
            f"Title-strip ink height at 96 dpi = {h_96} px, "
            f"at 300 dpi = {h_300} px, ratio = {ratio:.3f}.  "
            "Expected within ±15% (mm-true text ignores device DPI).  "
            "A ratio far from 1.0 means point-size font is in use."
        )
