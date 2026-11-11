"""Sheet.linked_document persistence through the real scene_io save / load."""
from __future__ import annotations

import json
import os

from firepro3d.paper_space import Sheet
from tests._linked_doc_helpers import (
    TWO_PAGE, build_fixture_pdf, fixture_text, make_link, snapshot_text,
)


def _model_space():
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    from firepro3d.scale_manager import ScaleManager
    scene = Model_Space()
    scene._level_manager = LevelManager()
    scene.scale_manager = ScaleManager()
    return scene


def _saved_link(path):
    with open(path) as fh:
        return json.load(fh)["sheets"][0].get("linked_document")


def test_sheet_dict_key_only_when_linked(qapp):
    s = Sheet.create_default()
    assert "linked_document" not in s.to_dict()
    assert Sheet.from_dict(s.to_dict()).linked_document is None
    s.linked_document = make_link(TWO_PAGE, 2)
    d = s.to_dict()
    back = Sheet.from_dict(d)
    assert back.linked_document == s.linked_document
    assert back.to_dict() == d


def test_save_load_save_is_byte_stable_and_relative(qapp, tmp_path):
    proj = tmp_path / "proj"
    src = build_fixture_pdf(proj / "docs" / "spec.pdf", 2)
    a = _model_space()
    sheet = Sheet.create_default()
    sheet.linked_document = make_link(src, 2)
    assert os.path.isabs(sheet.linked_document.path)   # unsaved: absolute
    a._sheets = [sheet]
    p1 = proj / "one.fpd"
    assert a.save_to_file(str(p1))
    b = _model_space()
    assert b.load_from_file(str(p1)) is not False
    assert b._sheets[0].linked_document.path == os.path.abspath(str(src))
    p2 = proj / "two.fpd"
    assert b.save_to_file(str(p2))
    ld1, ld2 = _saved_link(p1), _saved_link(p2)
    assert json.dumps(ld1, sort_keys=True) == json.dumps(ld2, sort_keys=True)
    assert ld1["path"] == os.path.relpath(str(src), str(proj))


def test_path_outside_the_tree_stays_absolute(qapp, tmp_path):
    src = build_fixture_pdf(tmp_path / "x" / "spec.pdf", 1)
    proj_dir = tmp_path / "a" / "b" / "c"
    proj_dir.mkdir(parents=True)
    a = _model_space()
    sheet = Sheet.create_default()
    sheet.linked_document = make_link(src, 1)
    a._sheets = [sheet]
    assert a.save_to_file(str(proj_dir / "p.fpd"))
    assert _saved_link(proj_dir / "p.fpd")["path"] == os.path.abspath(str(src))


def test_old_project_without_key_loads_none(qapp, tmp_path):
    a = _model_space()
    a._sheets = [Sheet.create_default()]
    assert a.save_to_file(str(tmp_path / "old.fpd"))
    assert _saved_link(tmp_path / "old.fpd") is None
    b = _model_space()
    assert b.load_from_file(str(tmp_path / "old.fpd")) is not False
    assert b._sheets[0].linked_document is None


def test_copy_survives_load_with_source_deleted(qapp, tmp_path):
    src = build_fixture_pdf(tmp_path / "spec.pdf", 2)
    a = _model_space()
    sheet = Sheet.create_default()
    sheet.linked_document = make_link(src, 1)
    saved = sheet.linked_document.snapshot_pdf
    a._sheets = [sheet]
    assert a.save_to_file(str(tmp_path / "p.fpd"))
    os.remove(src)
    b = _model_space()
    assert b.load_from_file(str(tmp_path / "p.fpd")) is not False
    ld = b._sheets[0].linked_document
    assert ld.snapshot_pdf == saved
    assert fixture_text("ALPHA", 1) in snapshot_text(ld)
