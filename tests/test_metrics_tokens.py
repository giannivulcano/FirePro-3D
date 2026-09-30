"""Metrics tokens: semantic-first, variant-independent, tuple margins."""
from firepro3d.theme import M


def test_margins_are_ltrb_tuples():
    for name in ("HEADER_MARGIN", "DIALOG_BODY_MARGIN", "PANEL_PAGE_MARGIN",
                 "FOOTER_MARGIN", "TOOLBAR_MARGIN", "SIDE_RAIL_MARGIN",
                 "STEP_ROW_MARGIN", "PILL_PADDING"):
        val = getattr(M, name)
        assert isinstance(val, tuple), f"{name} must be a tuple"


def test_canonical_values():
    assert M.HEADER_H == 34
    assert M.HEADER_MARGIN == (14, 4, 10, 4)
    assert M.HEADER_ICON == 24
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


def test_chrome_polish_tokens():
    from firepro3d import theme as th
    assert (M.TAB_GAP, M.TAB_SEP_LEN, M.TAB_SEP_W) == (2, 14, 1)
    assert (M.TOP_TAB_PT, M.LEFT_TAB_PT, M.LEFT_TAB_W) == (10, 8, 22)
    assert M.RIBBON_TAB_PAD == (6, 10, 2)
    assert M.CANVAS_TAB_PAD == (6, 8, 2, 8)
    assert M.LEFT_TAB_PAD == (8, 0, 8, 2)
    assert (M.RIBBON_STACK_H, M.RIBBON_GROUP_MARGIN, M.RIBBON_VLABEL_PT) == (88, (4, 2, 7, 0), 7.0)
    assert (M.RIBBON_LARGE_ICON, M.RIBBON_LARGE_H, M.RIBBON_SMALL_ICON, M.RIBBON_SMALL_H) == (40, 68, 18, 26)
    assert (M.HEADER_SEP_H, M.HEADER_ACTION_ICON, M.HEADER_ACTION_BTN, M.HEADER_TITLE_FS) == (18, 17, 26, 13)
    # colour roles are token NAMES that resolve on both themes
    for role in (th.TAB_SEP_ROLE, th.HEADER_SEP_ROLE, th.RIBBON_VLABEL_ROLE):
        assert getattr(th.DARK, role).startswith("#") and getattr(th.LIGHT, role).startswith("#")
