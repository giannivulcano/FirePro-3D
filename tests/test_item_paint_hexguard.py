"""R8 anti-drift (HF1): item paint modules must not construct a colour from a
raw hex literal -- stored colours go through colour_tokens.resolve_colour and
chrome through theme tokens. A deliberate literal carries
``# theme-exempt: <reason>`` on the same line."""
import pathlib
import re

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "firepro3d"

GUARDED = [
    "geometry_2d.py", "text_item.py", "block_instance.py", "block_definition.py",
    "hatch_render.py", "selection_manipulator.py", "linetype_render.py",
    "crisp_stroke.py",
]

_RAW = re.compile(r"QColor\(\s*[\"']#[0-9a-fA-F]{3,8}")


def violations(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines()
            if _RAW.search(ln) and "# theme-exempt:" not in ln]


@pytest.mark.parametrize("name", GUARDED)
def test_no_raw_hex_qcolor(name):
    bad = violations((SRC / name).read_text(encoding="utf-8"))
    assert not bad, f"{name}: raw QColor(\"#hex\") without # theme-exempt: {bad}"


def test_guard_catches_a_new_literal():
    assert violations('pen = QPen(QColor("#ff0000"))')
    assert not violations('c = QColor("#808080")  # theme-exempt: fallback')
