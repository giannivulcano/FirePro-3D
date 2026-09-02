"""Anti-drift: migrated chrome files must not hard-code hex in setStyleSheet()
unless the call is explicitly annotated `# theme-exempt: <reason>` (for fixed
paper/preview backdrops). Prevents future raw-hex chrome from silently ignoring
the theme."""
import pathlib
import re

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "firepro3d"

GUARDED = [
    "loading_bar.py", "wall_dialog.py", "roof_dialog.py",
    "titleblock_arrange.py", "titleblock_editor.py",
    "auto_populate_dialog.py", "underlay_import_dialog.py", "view_3d.py",
]

_HEX = re.compile(r"#[0-9a-fA-F]{3,6}\b")


def _stylesheet_calls(text):
    """Yield the source span of each setStyleSheet(...) call, paren-balanced."""
    marker = "setStyleSheet("
    i = 0
    while True:
        j = text.find(marker, i)
        if j == -1:
            return
        p = j + len(marker) - 1  # index of the opening '('
        depth = 0
        while p < len(text):
            ch = text[p]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            p += 1
        yield text[j:p + 1]
        i = p + 1


@pytest.mark.parametrize("fname", GUARDED)
def test_no_unexempt_hex_in_setstylesheet(fname):
    text = (SRC / fname).read_text(encoding="utf-8")
    offenders = [
        call.replace("\n", " ")[:140]
        for call in _stylesheet_calls(text)
        if _HEX.search(call) and "theme-exempt" not in call
    ]
    assert not offenders, (
        f"{fname}: raw hex in setStyleSheet — derive from theme tokens or mark "
        f"'# theme-exempt: <reason>': {offenders}"
    )
