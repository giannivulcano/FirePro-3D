"""Anti-drift: the house-dialog base + kit + simple migrated dialogs must not
hard-code layout literals in setContentsMargins/setFixedHeight/setFixedWidth/
setSpacing — they read from theme.M (see docs/specs/ui-design-system.md). Zero
resets (0,0,0,0) are allowed. The complex managers/import dialog are NOT guarded:
their bodies carry legitimate CONTENT sizing (column widths, filter widths) that
is domain sizing, not shared chrome tokens; their chrome is delegated to
HouseDialog (guarded here)."""
import pathlib
import re

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "firepro3d"
GUARDED = ["house_dialog.py", "ui_kit.py", "make_block_dialog.py",
           "themed_message.py"]

_CALL = re.compile(r"set(?:ContentsMargins|FixedHeight|FixedWidth|Spacing)\s*\(([^)]*)\)")
_NUMERIC = re.compile(r"\b\d+\b")


@pytest.mark.parametrize("fname", GUARDED)
def test_no_raw_layout_literals(fname):
    text = (SRC / fname).read_text(encoding="utf-8")
    offenders = []
    for m in _CALL.finditer(text):
        args = m.group(1)
        # allow 0/0/0/0 resets and *M.X splats; flag bare non-zero integers.
        stripped = args.replace("0", "").replace(",", "").replace(" ", "")
        if _NUMERIC.search(args) and stripped and "M." not in args:
            offenders.append(m.group(0)[:80])
    assert not offenders, f"{fname}: raw layout literal — use theme.M: {offenders}"
