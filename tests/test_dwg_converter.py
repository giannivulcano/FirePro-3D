"""Tests for DWG -> DXF conversion via ODA File Converter."""
import os
import subprocess
from unittest import mock

import pytest


def test_find_oda_returns_none_when_missing():
    """find_oda_converter() returns None when ODA is not installed."""
    from firepro3d.dwg_converter import find_oda_converter
    with mock.patch("shutil.which", return_value=None), \
         mock.patch("os.path.isfile", return_value=False), \
         mock.patch("firepro3d.dwg_converter._oda_path_from_settings",
                    return_value=None):
        assert find_oda_converter() is None


def test_find_oda_from_path():
    """find_oda_converter() finds ODA on PATH via shutil.which."""
    from firepro3d.dwg_converter import find_oda_converter
    sentinel = r"C:\Program Files\ODA\ODAFileConverter.exe"
    with mock.patch("shutil.which", return_value=sentinel), \
         mock.patch("os.path.isfile", return_value=True):
        assert find_oda_converter() == sentinel


def test_find_oda_from_settings():
    """find_oda_converter() finds ODA from QSettings."""
    from firepro3d.dwg_converter import find_oda_converter
    sentinel = r"D:\Tools\ODAFileConverter.exe"
    with mock.patch("shutil.which", return_value=None), \
         mock.patch("os.path.isfile", side_effect=lambda p: p == sentinel), \
         mock.patch("firepro3d.dwg_converter._oda_path_from_settings",
                    return_value=sentinel):
        assert find_oda_converter() == sentinel


def test_find_oda_from_common_install_path():
    """find_oda_converter() searches common install directories."""
    from firepro3d.dwg_converter import find_oda_converter, _COMMON_ODA_DIRS
    assert len(_COMMON_ODA_DIRS) > 0
    fake_path = os.path.join(_COMMON_ODA_DIRS[0], "ODAFileConverter.exe")
    with mock.patch("shutil.which", return_value=None), \
         mock.patch("firepro3d.dwg_converter._oda_path_from_settings",
                    return_value=None), \
         mock.patch("os.path.isfile",
                    side_effect=lambda p: p == fake_path):
        assert find_oda_converter() == fake_path


def test_convert_dwg_success(tmp_path):
    """convert_dwg_to_dxf() produces a temp DXF path on success."""
    from firepro3d.dwg_converter import convert_dwg_to_dxf

    dwg_file = tmp_path / "test.dwg"
    dwg_file.write_bytes(b"fake dwg content")

    def fake_run(cmd, **kwargs):
        out_dir = cmd[2]
        out_dxf = os.path.join(out_dir, "test.dxf")
        with open(out_dxf, "w") as f:
            f.write("fake dxf")
        return subprocess.CompletedProcess(cmd, 0)

    with mock.patch("subprocess.run", side_effect=fake_run):
        result = convert_dwg_to_dxf(r"C:\oda.exe", str(dwg_file))
        assert result is not None
        assert result.endswith(".dxf")
        assert os.path.isfile(result)


def test_convert_dwg_oda_failure(tmp_path):
    """convert_dwg_to_dxf() returns None when ODA fails."""
    from firepro3d.dwg_converter import convert_dwg_to_dxf

    dwg_file = tmp_path / "test.dwg"
    dwg_file.write_bytes(b"fake dwg content")

    with mock.patch("subprocess.run",
                    side_effect=subprocess.CalledProcessError(1, "oda")):
        result = convert_dwg_to_dxf(r"C:\oda.exe", str(dwg_file))
        assert result is None


def test_convert_dwg_no_output(tmp_path):
    """convert_dwg_to_dxf() returns None when ODA produces no DXF."""
    from firepro3d.dwg_converter import convert_dwg_to_dxf

    dwg_file = tmp_path / "test.dwg"
    dwg_file.write_bytes(b"fake dwg content")

    with mock.patch("subprocess.run",
                    return_value=subprocess.CompletedProcess([], 0)):
        result = convert_dwg_to_dxf(r"C:\oda.exe", str(dwg_file))
        assert result is None


def test_convert_dwg_source_missing():
    """convert_dwg_to_dxf() returns None for nonexistent source."""
    from firepro3d.dwg_converter import convert_dwg_to_dxf
    result = convert_dwg_to_dxf(r"C:\oda.exe", r"C:\no\such\file.dwg")
    assert result is None


def test_list_layouts_model_only():
    """list_dwg_layouts() returns ['Model'] for single-layout DXF."""
    from firepro3d.dwg_converter import list_dwg_layouts

    mock_doc = mock.MagicMock()
    mock_doc.layouts.names.return_value = ["Model"]

    with mock.patch("ezdxf.readfile", return_value=mock_doc):
        result = list_dwg_layouts("/tmp/test.dxf")
        assert result == ["Model"]


def test_list_layouts_multiple():
    """list_dwg_layouts() returns all layout names, Model first."""
    from firepro3d.dwg_converter import list_dwg_layouts

    mock_doc = mock.MagicMock()
    mock_doc.layouts.names.return_value = ["Model", "Sheet 1", "24x36 Plan"]

    with mock.patch("ezdxf.readfile", return_value=mock_doc):
        result = list_dwg_layouts("/tmp/test.dxf")
        assert result[0] == "Model"
        assert set(result) == {"Model", "Sheet 1", "24x36 Plan"}


def test_list_layouts_error():
    """list_dwg_layouts() returns ['Model'] on read failure."""
    from firepro3d.dwg_converter import list_dwg_layouts

    with mock.patch("ezdxf.readfile", side_effect=Exception("corrupt")):
        result = list_dwg_layouts("/tmp/test.dxf")
        assert result == ["Model"]
