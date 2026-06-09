"""Tests for the _sanitize_dxf clean-file bypass and skip_sanitize plumbing.

A clean DXF must pass through untouched (no whole-file rewrite, no temp
copy); only files with the defects the sanitiser repairs (BOM, bare CR,
trailing whitespace) take the slow path.
"""

import os

import pytest

import firepro3d.dxf_import_worker as diw
from firepro3d.dxf_import_worker import _dxf_needs_sanitize, _sanitize_dxf

CLEAN_LF = b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"
CLEAN_CRLF = CLEAN_LF.replace(b"\n", b"\r\n")


def _write(tmp_path, name, data: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


class TestNeedsSanitize:
    def test_clean_lf_file(self, tmp_path):
        path = _write(tmp_path, "clean.dxf", CLEAN_LF)
        assert _dxf_needs_sanitize(path) is False

    def test_clean_crlf_file(self, tmp_path):
        path = _write(tmp_path, "clean_crlf.dxf", CLEAN_CRLF)
        assert _dxf_needs_sanitize(path) is False

    def test_bom_detected(self, tmp_path):
        path = _write(tmp_path, "bom.dxf", b"\xef\xbb\xbf" + CLEAN_LF)
        assert _dxf_needs_sanitize(path) is True

    def test_cr_cr_lf_detected(self, tmp_path):
        path = _write(tmp_path, "crcrlf.dxf",
                      CLEAN_LF.replace(b"\n", b"\r\r\n"))
        assert _dxf_needs_sanitize(path) is True

    def test_bare_cr_detected(self, tmp_path):
        path = _write(tmp_path, "barecr.dxf",
                      CLEAN_LF.replace(b"\n", b"\r"))
        assert _dxf_needs_sanitize(path) is True

    def test_trailing_space_before_newline_detected(self, tmp_path):
        path = _write(tmp_path, "trailws.dxf",
                      b"0 \nSECTION\n0\nEOF\n")
        assert _dxf_needs_sanitize(path) is True

    def test_trailing_tab_before_crlf_detected(self, tmp_path):
        path = _write(tmp_path, "trailtab.dxf",
                      b"0\t\r\nSECTION\r\n0\r\nEOF\r\n")
        assert _dxf_needs_sanitize(path) is True

    def test_trailing_cr_at_eof_detected(self, tmp_path):
        path = _write(tmp_path, "eofcr.dxf", b"0\nEOF\r")
        assert _dxf_needs_sanitize(path) is True

    def test_trailing_space_at_eof_detected(self, tmp_path):
        path = _write(tmp_path, "eofws.dxf", b"0\nEOF ")
        assert _dxf_needs_sanitize(path) is True

    def test_missing_file_treated_as_needing_sanitize(self, tmp_path):
        # The sanitiser's own error handling covers unreadable files.
        assert _dxf_needs_sanitize(str(tmp_path / "ghost.dxf")) is True


class TestNeedsSanitizeChunkBoundaries:
    """Defects spanning a read-chunk boundary must still be detected."""

    def test_crlf_split_across_chunks_is_clean(self, tmp_path, monkeypatch):
        monkeypatch.setattr(diw, "_SCAN_CHUNK", 4)
        # 3 bytes then "\r" as 4th byte of chunk 1, "\n" opens chunk 2
        path = _write(tmp_path, "split.dxf", b"abc\r\ndef\n")
        assert _dxf_needs_sanitize(path) is False

    def test_space_newline_split_across_chunks_is_dirty(self, tmp_path,
                                                        monkeypatch):
        monkeypatch.setattr(diw, "_SCAN_CHUNK", 4)
        path = _write(tmp_path, "splitws.dxf", b"abc \ndef\n")
        assert _dxf_needs_sanitize(path) is True

    def test_bare_cr_split_across_chunks_is_dirty(self, tmp_path,
                                                  monkeypatch):
        monkeypatch.setattr(diw, "_SCAN_CHUNK", 4)
        path = _write(tmp_path, "splitcr.dxf", b"abc\rdef\n")
        assert _dxf_needs_sanitize(path) is True


class TestSanitizeBypass:
    def test_clean_file_returns_original_path(self, tmp_path):
        path = _write(tmp_path, "clean.dxf", CLEAN_LF)
        assert _sanitize_dxf(path) == path

    def test_clean_crlf_file_returns_original_path(self, tmp_path):
        path = _write(tmp_path, "clean_crlf.dxf", CLEAN_CRLF)
        assert _sanitize_dxf(path) == path

    def test_dirty_file_still_sanitised(self, tmp_path):
        path = _write(tmp_path, "bom.dxf", b"\xef\xbb\xbf" + CLEAN_LF)
        result = _sanitize_dxf(path)
        try:
            assert result != path
            cleaned = open(result, "rb").read()
            assert not cleaned.startswith(b"\xef\xbb\xbf")
            assert b"\r" not in cleaned
        finally:
            if result != path and os.path.exists(result):
                os.remove(result)


class TestSkipSanitize:
    def test_extract_file_sync_skips_sanitizer(self, tmp_path, monkeypatch):
        ezdxf = pytest.importorskip("ezdxf")
        doc = ezdxf.new()
        doc.modelspace().add_line((0, 0), (100, 100))
        dxf_path = str(tmp_path / "mini.dxf")
        doc.saveas(dxf_path)

        called = []
        monkeypatch.setattr(
            diw, "_sanitize_dxf",
            lambda p: (called.append(p), p)[1])

        from firepro3d.dxf_import_worker import DxfImportWorker
        geoms = DxfImportWorker.extract_file_sync(dxf_path,
                                                  skip_sanitize=True)
        assert called == [], "skip_sanitize=True must bypass _sanitize_dxf"
        assert len(geoms) == 1

    def test_extract_file_sync_default_sanitises(self, tmp_path, monkeypatch):
        ezdxf = pytest.importorskip("ezdxf")
        doc = ezdxf.new()
        doc.modelspace().add_line((0, 0), (100, 100))
        dxf_path = str(tmp_path / "mini.dxf")
        doc.saveas(dxf_path)

        called = []
        monkeypatch.setattr(
            diw, "_sanitize_dxf",
            lambda p: (called.append(p), p)[1])

        from firepro3d.dxf_import_worker import DxfImportWorker
        DxfImportWorker.extract_file_sync(dxf_path)
        assert called == [dxf_path]
