"""SB4a AC8 -- the HTML pipe label, Label Size and set_label_position are gone."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1] / "firepro3d"


def test_pipe_label_retired_strings_are_gone():
    src = (ROOT / "pipe.py").read_text(encoding="utf-8")
    for s in ("Label Size", "set_label_position", "setHtml", "QGraphicsTextItem(",
              "#00aaff", "#ffaa00"):
        assert s not in src, s
    for f in ("display_manager.py", "pipe_network_controller.py"):
        assert "Label Size" not in (ROOT / f).read_text(encoding="utf-8"), f
