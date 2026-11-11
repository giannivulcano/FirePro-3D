"""AC3 parity scene (paper-as-authored): one scene, three legacy modes,
rendered through the real paper pass. Runs unchanged at the base SHA and on
the branch: it only uses APIs that exist at both (apply_paper_display_from_project,
QSettings, apply_paper_overrides / restore_model_display)."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import paper_display as pd
from firepro3d.geometry_2d import LineItem
from firepro3d.text_item import TextAnnotationData, TextItem
from firepro3d.wall import WallSegment
from tests.test_underlay_display import _geoms, _record
from tests.wm3_support import OVR, composite_scene

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "paper_parity"
MODES = ("bw", "custom", "full_color")
SCALE = 0.02
CROP = QRectF(-2500.0, -2500.0, 5000.0, 5000.0)

# Base-SHA Model factory hexes (display_manager._CATEGORIES at e7ac8f15) --
# what an existing user's QSettings hold after any startup
# (apply_default_display_settings writes them). Pinned so D3m's new factory
# tokens cannot leak into a parity render.
BASE_MODEL = {
    "Pipe": ("#4488ff", None), "Sprinkler": ("#ff4444", "#000000"),
    "Wall": ("#666666", "#999999"), "Node": ("#888888", None),
    "Water Supply": ("#00cccc", "#2b2b2e"),
    "Hydraulic Badge": ("#ffffff", "#2b2b2b"),
}

# Custom: distinct, non-black row colours so a wrongly-ON row shows.
CUSTOM_ROWS = {"Pipe": "#00aa00", "Sprinkler": "#aa5500", "Wall": "#0000aa",
               "Construction": "#aa00aa", "Blocks": "#008888",
               "Node": "#550055"}


def pin_model_colours(settings: QSettings | None = None) -> None:
    s = settings or QSettings("GV", "FirePro3D")
    for key, (col, fill) in BASE_MODEL.items():
        s.setValue(f"display/{key}/color", col)
        if fill is not None:
            s.setValue(f"display/{key}/fill", fill)
    s.sync()


def legacy_categories(mode: str) -> dict:
    """The project-file categories a legacy file of *mode* carries (base-SHA
    factory hexes; Custom overrides CUSTOM_ROWS). No as_authored key."""
    cats = {}
    for key in ("Pipe", "Sprinkler", "Fitting", "Water Supply", "Node",
                "Hydraulic Badge", "Wall", "Construction", "Blocks"):
        cats[key] = {"color": "#000000"}
        if key in ("Sprinkler", "Water Supply", "Hydraulic Badge", "Wall"):
            cats[key]["fill"] = "#ffffff"
        if key == "Wall":
            cats[key]["section_color"] = "#000000"
    if mode in ("custom", "full_color"):
        for key, col in CUSTOM_ROWS.items():
            cats[key]["color"] = col
    return cats


def build_scene(shipped_hatches):
    """Composite block (authored red / blue + placement OVR), a By Category
    placement, a pipe with a sprinkler, a wall, a white and a #ff00ff
    construction line, a hex text, and an underlay with a red layer."""
    ms, _ = composite_scene(shipped_hatches, {"colour": OVR})
    n1, n2 = ms.add_node(-2000.0, 1500.0), ms.add_node(2000.0, 1500.0)
    ms.add_pipe(n1, n2)
    ms.add_sprinkler(n2)
    ms.addItem(WallSegment(QPointF(-2000.0, -1500.0), QPointF(2000.0, -1500.0),
                           thickness_mm=200))
    for y, col in ((-2000.0, "#ffffff"), (-2200.0, "#ff00ff")):
        ln = LineItem(QPointF(-2000.0, y), QPointF(2000.0, y), col)
        ms.addItem(ln)
    ms.addItem(TextItem(TextAnnotationData(text="P", x=1800.0, y=-2300.0,
                                           height_mm=250.0, color="#ff8800")))
    rec = _record(layer_overrides={"A-WALL": {"colour": "#ff0000"}})
    group, _ = ms._build_batched_underlay_group(_geoms(), rec)
    ms.underlays.append((rec, group))
    return ms


def render(ms) -> QImage:
    """The scene inside a real paper pass on white paper (what a sheet
    viewport paints), 500 x 500 px."""
    img = QImage(500, 500, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    saved = pd.apply_paper_overrides(ms, CROP, paper_scale=SCALE)
    try:
        p = QPainter(img)
        ms.render(p, QRectF(0, 0, 500, 500), CROP)
        p.end()
    finally:
        pd.restore_model_display(saved)
    return img


def load_mode_via_project(mode: str) -> None:
    pd.apply_paper_display_from_project({"color_mode": mode,
                                         "categories": legacy_categories(mode)})


def load_mode_via_qsettings(mode: str) -> None:
    """An existing user's settings: categories (no as_authored) plus the
    legacy key -- written raw, exactly as the base build stored them."""
    s = QSettings("GV", "FirePro3D")
    for key, props in legacy_categories(mode).items():
        for prop, val in props.items():
            s.setValue(f"paper/categories/{key}/{prop}", val)
    s.setValue("paper/color_mode", mode)
    s.sync()
