"""Tests for paper-space PDF export / print (firepro3d/paper_export.py)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtCore import QRectF

from firepro3d.paper_space import (
    Sheet, SheetViewData, SheetViewport, PaperScene, ViewResolver,
)


def _real_source_resolver():
    """Resolver returning a real model QGraphicsScene + rect (for rendering)."""
    model_scene = QGraphicsScene()
    model_scene.addRect(0, 0, 10000, 8000)
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.return_value = (model_scene, QRectF(0, 0, 10000, 8000))
    return resolver, model_scene


class TestLifecycleTeardown:
    def test_viewport_disconnect_source_drops_connection(self, qapp):
        resolver, model_scene = _real_source_resolver()
        data = SheetViewData("plan", "L1", "L1", 0.01, 50, 50, 400, 300)
        vp = SheetViewport(data, resolver)
        assert vp._source_scene is model_scene
        vp.disconnect_source()
        assert vp._source_scene is None
        # Mutating the (now-disconnected) source must not call mark_dirty.
        with patch.object(vp, "update") as mock_update:
            model_scene.addRect(0, 0, 1, 1)
            qapp.processEvents()
            mock_update.assert_not_called()

    def test_paper_scene_dispose_disconnects_all_viewports(self, qapp):
        resolver, _ = _real_source_resolver()
        sheet = Sheet.create_default()
        sheet.sheet_views = [
            SheetViewData("plan", "L1", "L1", 0.01, 50, 50, 400, 300),
        ]
        scene = PaperScene(sheet, resolver)
        assert len(scene.get_viewports()) == 1
        scene.dispose()
        assert all(vp._source_scene is None for vp in scene.get_viewports())


try:
    from PyQt6.QtPdf import QPdfDocument
    _HAVE_QTPDF = True
except ImportError:
    _HAVE_QTPDF = False


class TestDefaultFilename:
    def test_basic(self):
        from firepro3d import paper_export
        sheet = Sheet("FP-1.0", "Level 1 Plan", "ANSI D", {}, [])
        assert paper_export.default_pdf_filename(sheet) == "FP-1.0 - Level 1 Plan.pdf"

    def test_sanitizes_invalid_chars(self):
        from firepro3d import paper_export
        sheet = Sheet("FP/1", "A:B*C?", "ANSI D", {}, [])
        name = paper_export.default_pdf_filename(sheet)
        for ch in '<>:"/\\|?*':
            assert ch not in name[:-4]  # ".pdf" suffix excluded from the check
        assert name.endswith(".pdf")

    def test_empty_number_and_name(self):
        from firepro3d import paper_export
        sheet = Sheet("", "", "ANSI D", {}, [])
        assert paper_export.default_pdf_filename(sheet) == "sheet.pdf"


class TestExportPdf:
    def test_export_creates_valid_pdf(self, qapp, tmp_path):
        from firepro3d import paper_export
        from firepro3d.paper_space import PAPER_SIZES
        resolver, _ = _real_source_resolver()
        sheet = Sheet.create_default()  # ANSI D, no viewports
        out = tmp_path / "out.pdf"

        paper_export.export_pdf([sheet], resolver, str(out), dpi=150)

        assert out.exists()
        assert out.stat().st_size > 0
        if _HAVE_QTPDF:
            doc = QPdfDocument(None)
            doc.load(str(out))
            assert doc.pageCount() == 1
            pts = doc.pagePointSize(0)
            w_mm, h_mm = PAPER_SIZES["ANSI D"]
            assert pts.width() == pytest.approx(w_mm / 25.4 * 72, abs=4)
            assert pts.height() == pytest.approx(h_mm / 25.4 * 72, abs=4)

    def test_export_runs_override_path_when_viewport_present(
            self, qapp, tmp_path, monkeypatch):
        """A sheet with a viewport must drive apply_paper_overrides during export."""
        import firepro3d.paper_display as pd
        from firepro3d import paper_export
        calls = {"n": 0}
        orig = pd.apply_paper_overrides

        def spy(scene, rect, paper_scale=1.0):
            calls["n"] += 1
            return orig(scene, rect, paper_scale=paper_scale)

        monkeypatch.setattr(pd, "apply_paper_overrides", spy)

        resolver, _ = _real_source_resolver()
        sheet = Sheet.create_default()
        sheet.sheet_views = [
            SheetViewData("plan", "L1", "L1", 0.01, 50, 50, 400, 300),
        ]
        out = tmp_path / "vp.pdf"
        paper_export.export_pdf([sheet], resolver, str(out), dpi=150)
        assert calls["n"] >= 1

    def test_export_empty_list_raises(self, qapp, tmp_path):
        from firepro3d import paper_export
        resolver, _ = _real_source_resolver()
        with pytest.raises(ValueError):
            paper_export.export_pdf([], resolver, str(tmp_path / "x.pdf"))

    def test_export_unwritable_path_raises_no_partial_file(self, qapp, tmp_path):
        from firepro3d import paper_export
        resolver, _ = _real_source_resolver()
        sheet = Sheet.create_default()
        bad = tmp_path / "nope" / "deep" / "x.pdf"  # parent dirs do not exist
        with pytest.raises(OSError):
            paper_export.export_pdf([sheet], resolver, str(bad), dpi=150)
        assert not bad.exists()

    def test_export_multipage_mixed_sizes(self, qapp, tmp_path):
        """Pipeline accepts list[Sheet]; pages adopt each sheet's size."""
        from firepro3d import paper_export
        from firepro3d.paper_space import PAPER_SIZES
        resolver, _ = _real_source_resolver()
        s1 = Sheet.create_default()              # ANSI D
        s2 = Sheet("FP-2", "B", "ANSI B", dict(s1.title_block_fields), [])
        out = tmp_path / "multi.pdf"
        paper_export.export_pdf([s1, s2], resolver, str(out), dpi=150)
        assert out.exists()
        if _HAVE_QTPDF:
            doc = QPdfDocument(None)
            doc.load(str(out))
            assert doc.pageCount() == 2
            d_w, _ = PAPER_SIZES["ANSI D"]
            b_w, _ = PAPER_SIZES["ANSI B"]
            assert doc.pagePointSize(0).width() == pytest.approx(d_w / 25.4 * 72, abs=4)
            assert doc.pagePointSize(1).width() == pytest.approx(b_w / 25.4 * 72, abs=4)


class TestPrintSheets:
    def test_print_routes_through_render(self, qapp, tmp_path):
        """Drive print_sheets via a QPrinter set to PDF output (headless-safe)."""
        from PyQt6.QtPrintSupport import QPrinter
        from firepro3d import paper_export
        resolver, _ = _real_source_resolver()
        sheet = Sheet.create_default()
        out = tmp_path / "printed.pdf"

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(out))

        paper_export.print_sheets([sheet], resolver, printer)

        assert out.exists()
        assert out.stat().st_size > 0

    def test_print_empty_list_raises(self, qapp):
        from PyQt6.QtPrintSupport import QPrinter
        from firepro3d import paper_export
        resolver, _ = _real_source_resolver()
        printer = QPrinter()
        with pytest.raises(ValueError):
            paper_export.print_sheets([], resolver, printer)


class TestTemplatedExport:
    def test_templated_sheet_exports_pdf(self, qapp, tmp_path):
        """export_pdf with a TitleBlockTemplate produces a non-empty PDF."""
        from firepro3d.titleblock_template import make_default_template
        from firepro3d import paper_export
        resolver, _ = _real_source_resolver()
        sheet = Sheet.create_default()
        sheet.title_block_fields["Title"] = "TEMPLATED EXPORT"
        out = str(tmp_path / "out.pdf")
        paper_export.export_pdf(
            [sheet], resolver, out, dpi=150,
            template=make_default_template(),
            project_info={},
        )
        import os
        assert os.path.isfile(out) and os.path.getsize(out) > 2000

    def test_combined_cell_template_exports_pdf(self, qapp, tmp_path,
                                                tiny_png_b64):
        """A template cell with BOTH text and image_data exports to a 1-page PDF.

        Rev-3 combined cells (DD-15: label / image band / text band) must
        survive the full export path — solver sub-rects + renderer image
        decode + QPdfWriter — without exceptions.
        """
        from firepro3d.titleblock_template import make_default_template
        from firepro3d import paper_export
        resolver, _ = _real_source_resolver()
        sheet = Sheet.create_default()

        template = make_default_template()
        first = template.layout.fields[0]      # Logo field: first strip row
        first.text = "Acme"
        first.image_data = tiny_png_b64

        out = str(tmp_path / "combined.pdf")
        paper_export.export_pdf(
            [sheet], resolver, out, dpi=150,
            template=template, project_info={},
        )
        import os
        assert os.path.isfile(out) and os.path.getsize(out) > 2000
        if _HAVE_QTPDF:
            doc = QPdfDocument(None)
            doc.load(out)
            assert doc.pageCount() == 1

    def test_templated_vs_plain_both_produce_pdf(self, qapp, tmp_path):
        """Template-rendered and plain-rendered sheets both produce valid PDFs.

        The PDFs may differ in size (template renders additional vector content),
        but both must be > 2 kB.  A strict size-diff assertion is avoided because
        the headless renderer may produce byte-identical blanks in some CI configs.
        """
        from firepro3d.titleblock_template import make_default_template
        from firepro3d import paper_export
        resolver, _ = _real_source_resolver()

        sheet = Sheet.create_default()
        sheet.title_block_fields["Title"] = "COMPARE"

        out_plain = str(tmp_path / "plain.pdf")
        out_tmpl = str(tmp_path / "templated.pdf")

        paper_export.export_pdf([sheet], resolver, out_plain, dpi=150)
        paper_export.export_pdf(
            [sheet], resolver, out_tmpl, dpi=150,
            template=make_default_template(),
            project_info={},
        )

        import os
        assert os.path.isfile(out_plain) and os.path.getsize(out_plain) > 2000
        assert os.path.isfile(out_tmpl) and os.path.getsize(out_tmpl) > 2000
