"""SB3 AC11 -- the retired room-label machinery is gone from the code and the tests
(the deliverable IS the text: a source sweep is the right guard here)."""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RETIRED = ("label_scene_rect", "ROOM_LABEL_PAPER_CAP_MM", "_RoundedRectBgItem",
           "_label_font_size", "_label_font_color", "_apply_room_label_paper_height")
_SELF = os.path.abspath(__file__)


def _py_files(sub):
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, sub)):
        if "__pycache__" in dirpath:
            continue
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)


@pytest.mark.parametrize("sub", ["firepro3d", "tests", "main.py"])
def test_retired_strings_absent(sub):
    paths = [os.path.join(ROOT, sub)] if sub.endswith(".py") else list(_py_files(sub))
    hits = []
    pat = re.compile("|".join(map(re.escape, RETIRED)))
    for p in paths:
        if os.path.abspath(p) == _SELF:
            continue
        with open(p, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                if pat.search(line):
                    hits.append(f"{os.path.relpath(p, ROOT)}:{n}: {line.strip()}")
    assert not hits, "\n".join(hits)


def test_display_manager_room_row_has_no_font_key(qapp):
    from firepro3d.display_manager import _CATEGORY_MAP, _category_has_font
    assert _CATEGORY_MAP["Room"]["font"] is None and not _category_has_font("Room")
