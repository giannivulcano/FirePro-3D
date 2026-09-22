"""todo #70 convention guard: the native QColorDialog is retired app-wide —
every colour pick goes through firepro3d.colour_picker.pick_colour (see
docs/specs/ui-design-system.md). Lint-style, like the hexguard."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_no_qcolordialog_in_app_code():
    files = [ROOT / "main.py", *sorted((ROOT / "firepro3d").rglob("*.py"))]
    offenders = [str(f.relative_to(ROOT)) for f in files
                 if "QColorDialog" in f.read_text(encoding="utf-8")]
    assert offenders == [], f"native QColorDialog still referenced in: {offenders}"
