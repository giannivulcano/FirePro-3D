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
         mock.patch("os.path.isfile", return_value=True), \
         mock.patch("firepro3d.dwg_converter._oda_path_from_settings",
                    return_value=None):
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
                    return_value=subprocess.CompletedProcess([], 1,
                                                            stdout="", stderr="error")):
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


def test_underlay_dwg_type_roundtrip():
    """Underlay with type='dwg' and layout field serializes correctly."""
    from firepro3d.underlay import Underlay

    u = Underlay(type="dwg", path="test.dwg", layout="Sheet 1")
    d = u.to_dict()
    assert d["type"] == "dwg"
    assert d["layout"] == "Sheet 1"

    u2 = Underlay.from_dict(d)
    assert u2.type == "dwg"
    assert u2.layout == "Sheet 1"


def test_underlay_layout_default_empty():
    """Underlay layout defaults to empty string (backward compat)."""
    from firepro3d.underlay import Underlay

    u = Underlay(type="dxf", path="test.dxf")
    assert u.layout == ""
    d = u.to_dict()
    assert d["layout"] == ""


def test_underlay_from_dict_missing_layout():
    """Old project files without layout field load cleanly."""
    from firepro3d.underlay import Underlay

    d = {"type": "dxf", "path": "test.dxf"}
    u = Underlay.from_dict(d)
    assert u.layout == ""


def test_underlay_dwg_properties_show_layout():
    """get_properties() shows Layout for DWG underlays."""
    from firepro3d.underlay import Underlay

    u = Underlay(type="dwg", path="test.dwg", layout="Level 1 Plan")
    props = u.get_properties()
    assert "Layout" in props
    assert props["Layout"]["value"] == "Level 1 Plan"


def test_cache_key_includes_layout():
    """compute_cache_key() produces different keys for different layouts."""
    from firepro3d.underlay_cache import compute_cache_key

    key_model = compute_cache_key("test.dwg", layout="Model")
    key_sheet = compute_cache_key("test.dwg", layout="Sheet 1")
    key_none = compute_cache_key("test.dwg", layout="")

    assert key_model != key_sheet
    assert key_model != key_none


def test_cache_key_backward_compat():
    """compute_cache_key() with default layout matches old behavior."""
    from firepro3d.underlay_cache import compute_cache_key

    key_new = compute_cache_key("test.dxf", page=0, layout="")
    key_old = compute_cache_key("test.dxf", page=0)
    assert key_new == key_old


def test_import_params_dwg_layout():
    """ImportParams carries DWG layout through to Underlay record."""
    from firepro3d.dxf_preview_dialog import ImportParams
    from firepro3d.underlay import Underlay

    p = ImportParams()
    p.file_path = r"C:\drawings\floor.dwg"
    p.file_type = "dwg"
    p.layout = "Sheet 1"
    p.scale = 1.0
    p.geom_list = [{"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 0, "layer": "0"}]

    # Simulate what _commit_place_import does
    record = Underlay(
        type=p.file_type, path=p.file_path,
        import_scale=p.scale,
        layout=p.layout,
    )
    assert record.type == "dwg"
    assert record.layout == "Sheet 1"

    # Verify cache key differs from same file with different layout
    record2 = Underlay(
        type=p.file_type, path=p.file_path,
        import_scale=p.scale,
        layout="Model",
    )
    assert record.cache_key() != record2.cache_key()


def test_underlay_dwg_serialization_roundtrip():
    """Full DWG underlay serialize -> deserialize round-trip."""
    from firepro3d.underlay import Underlay

    original = Underlay(
        type="dwg",
        path=r"C:\drawings\floor.dwg",
        x=100.0, y=200.0,
        scale=0.5,
        rotation=90.0,
        layout="24x36 Sheet",
        import_scale=25.4,
        import_base_x=10.0,
        import_base_y=20.0,
        selected_layers=["0", "Walls"],
        colour="#ff0000",
    )
    d = original.to_dict()
    restored = Underlay.from_dict(d)

    assert restored.type == "dwg"
    assert restored.path == original.path
    assert restored.layout == "24x36 Sheet"
    assert restored.import_scale == 25.4
    assert restored.selected_layers == ["0", "Walls"]
    assert restored.x == 100.0
    assert restored.rotation == 90.0
