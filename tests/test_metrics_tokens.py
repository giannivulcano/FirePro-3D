"""Metrics tokens: semantic-first, variant-independent, tuple margins."""
from firepro3d.theme import M


def test_margins_are_ltrb_tuples():
    for name in ("HEADER_MARGIN", "DIALOG_BODY_MARGIN", "PANEL_PAGE_MARGIN",
                 "FOOTER_MARGIN", "TOOLBAR_MARGIN", "SIDE_RAIL_MARGIN",
                 "STEP_ROW_MARGIN", "PILL_PADDING"):
        val = getattr(M, name)
        assert isinstance(val, tuple), f"{name} must be a tuple"


def test_canonical_values():
    assert M.HEADER_H == 40
    assert M.HEADER_MARGIN == (14, 7, 10, 7)
    assert M.HEADER_ICON == 22
    assert M.DIALOG_BODY_MARGIN == (20, 18, 20, 18)
    assert M.PANEL_PAGE_MARGIN == (14, 14, 14, 14)
    assert M.FOOTER_MARGIN == (14, 9, 14, 9)
    assert M.PANEL_W == 268
    assert M.PANEL_W_WIDE == 324
    assert M.SEAM == 1
    assert (M.RADIUS_INPUT, M.RADIUS_CARD, M.RADIUS_PILL, M.RADIUS_CHIP) == (6, 7, 11, 8)


def test_metrics_are_variant_independent():
    from firepro3d import theme as th
    assert not hasattr(th.DARK, "HEADER_H")
    assert not hasattr(th.LIGHT, "HEADER_H")
