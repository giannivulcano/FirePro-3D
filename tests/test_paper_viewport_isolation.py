from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter, QColor
from firepro3d.paper_space import PaperScene, Sheet, SheetViewData
from tests._paper_iso_helpers import build_isolation_fixture


def _render_sheet_to_image(scene, w=400, h=400):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), QRectF(0, 0, w, h))
    p.end()
    return img


def _nonwhite_count(img):
    white = QColor("white").rgb()
    return sum(img.pixel(x, y) != white
              for x in range(img.width()) for y in range(img.height()))


def test_level3_viewport_shows_level3_not_level1_when_level1_active(qapp):
    """A Level-3 plan viewport must render Level-3 geometry even when Level 1 is
    active on-screen. Walls w1/w3 share xy, so the ONLY difference is the level."""
    fx = build_isolation_fixture()
    scene_model = fx["scene"]

    # On-screen: Level 1 active (so w3 hidden, w1 shown) — the "wrong" state.
    fx["lm"].apply_to_scene(scene_model, "Level 1")
    scene_model.active_level = "Level 1"
    scene_model.active_view_key = "plan:Plan: Level 1"
    assert fx["w3"].isVisible() is False        # sanity: L3 wall hidden on-screen
    assert fx["w1"].isVisible() is True

    # Paper: a viewport bound to the Level-3 plan.
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Plan: Level 3", "L3", 0.02, 10, 10, 0, 0)
    paper = PaperScene(sheet, fx["resolver"])
    paper.add_viewport(data)

    # NOTE: no _nonwhite_count(img) assertion here — the sheet border + title
    # block flood a full-PaperScene render non-white regardless of which level
    # rendered, so such a check is NON-DISCRIMINATING for isolation. This test's
    # point is the RESTORE assertions below; the durable RENDER proof (that L3,
    # not L1, actually rasterized) lives in
    # test_level3_viewport_renders_l3_row_not_l1_row, which probes the viewport
    # directly in pixels.
    _render_sheet_to_image(paper)

    # CRITICAL: the on-screen live scene is restored exactly — L1 shown, L3 hidden.
    assert fx["w1"].isVisible() is True
    assert fx["w3"].isVisible() is False
    assert scene_model.active_level == "Level 1"
    assert scene_model.active_view_key == "plan:Plan: Level 1"


def _row_interior_nonwhite(img, y, lo, hi):
    """Count nonwhite pixels in row *y* over the half-open x-range [lo, hi).

    The viewport border/frame inks the box's left (x==0) and right (x==box_w)
    columns on every row; a real horizontal wall inks the full interior span.
    Probing strictly inside the box border columns distinguishes a wall from the
    frame.
    """
    white = QColor("white").rgb()
    return sum(img.pixel(x, y) != white for x in range(lo, hi))


def test_level3_viewport_renders_l3_row_not_l1_row(qapp):
    """DURABLE pixel proof: a Level-3 plan viewport rendered while Level 1 is the
    on-screen active level shows the Level-3 wall's pixel row (it rendered) and
    NOT the Level-1 wall's pixel row (it did not). Renders the VIEWPORT directly
    (not the full PaperScene) so the sheet frame / title block can't flood rows.

    The two walls sit at DIFFERENT model-space y (distinct_y fixture), so they map
    to DIFFERENT pixel rows — the only way the L3 row is inked and the L1 row is
    blank is if the level isolation swapped visibility to Level 3 before render.
    """
    fx = build_isolation_fixture(distinct_y=True)
    scene_model = fx["scene"]

    # On-screen: Level 1 active — the "wrong" state we must override for paper.
    fx["lm"].apply_to_scene(scene_model, "Level 1")
    scene_model.active_level = "Level 1"
    scene_model.active_view_key = "plan:Plan: Level 1"
    assert fx["w1"].isVisible() is True
    assert fx["w3"].isVisible() is False

    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Plan: Level 3", "L3", 0.02, 10, 10, 0, 0)
    paper = PaperScene(sheet, fx["resolver"])
    vp = paper.add_viewport(data)

    # Render the viewport box into its own image (box == crop×scale).
    w, h = int(vp.data.w), int(vp.data.h)
    pad = 8
    img = QImage(w + pad, h + pad, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    vp.paint(p, None, None)
    p.end()

    # Map each wall's model-space y to a pixel row via the crop->box fit used by
    # paint(): scene.render(painter, fitted=box, crop). box fills the vp for
    # scale>0, so paper_y = (model_y - crop.top) * scale. Wall thickness spreads
    # the fill a few rows off the centerline, so probe a BAND around each row and
    # take the peak interior count.
    crop = vp._effective_crop()
    scale = data.scale

    def row_of(model_y):
        return int(round((model_y - crop.top()) * scale))

    # Probe strictly INSIDE the box's left/right border columns (x==0 and x==w).
    ix_lo, ix_hi = 6, w - 6
    interior_w = ix_hi - ix_lo

    def band_peak(center, half=8):
        lo = max(0, center - half)
        hi = min(img.height(), center + half + 1)
        return max((_row_interior_nonwhite(img, y, ix_lo, ix_hi)
                    for y in range(lo, hi)), default=0)

    l3_row = row_of(fx["y3"])
    l1_row = row_of(fx["y1"])
    l3_peak = band_peak(l3_row)
    l1_peak = band_peak(l1_row)

    # Diagnostics.
    per_row = [(y, _row_interior_nonwhite(img, y, ix_lo, ix_hi))
               for y in range(img.height())]
    inked = [(y, c) for y, c in per_row if c > 0]
    print(f"[diag] box={w}x{h} img={img.width()}x{img.height()} "
          f"crop=({crop.top():.1f},{crop.bottom():.1f}) scale={scale}")
    print(f"[diag] probe x=[{ix_lo},{ix_hi}) interior_w={interior_w}")
    print(f"[diag] l1_row={l1_row} peak={l1_peak}  l3_row={l3_row} peak={l3_peak}")
    print(f"[diag] interior-inked rows (y,count): {inked}")

    # L3 wall rendered: a big span of its band's interior is inked.
    assert l3_peak > interior_w // 2, (
        f"Level-3 wall row band around {l3_row} is blank (peak={l3_peak}) — "
        f"L3 did NOT render. interior-inked rows: {inked}")
    # L1 wall did NOT render: its band's interior is blank.
    assert l1_peak == 0, (
        f"Level-1 wall row band around {l1_row} is inked (peak={l1_peak}) — "
        f"L1 rendered into the L3 viewport. interior-inked rows: {inked}")


def test_live_scene_restored_even_if_render_throws(qapp, monkeypatch):
    from PyQt6.QtGui import QImage, QPainter, QColor
    fx = build_isolation_fixture()
    scene_model = fx["scene"]
    fx["lm"].apply_to_scene(scene_model, "Level 1")
    scene_model.active_level = "Level 1"
    scene_model.active_view_key = "plan:Plan: Level 1"

    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Plan: Level 3", "L3", 0.02, 10, 10, 0, 0)
    paper = PaperScene(sheet, fx["resolver"])
    vp = paper.add_viewport(data)

    def boom(*a, **k):
        raise RuntimeError("render blew up")
    monkeypatch.setattr(scene_model, "render", boom)

    img = QImage(50, 50, QImage.Format.Format_RGB32); img.fill(QColor("white"))
    p = QPainter(img)
    try:
        vp.paint(p, None, None)
    except RuntimeError:
        pass
    p.end()

    assert scene_model.active_level == "Level 1"
    assert scene_model.active_view_key == "plan:Plan: Level 1"
    assert fx["w1"].isVisible() is True
    assert fx["w3"].isVisible() is False
