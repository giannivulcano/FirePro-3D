"""_tab_language_qss emits the shared tab states for any selector + edge."""
from firepro3d.theme import _tab_language_qss, detect


def test_fragment_emits_states_for_selector_and_edge():
    t = detect()
    qss = _tab_language_qss(t, "RibbonBar QTabBar::tab", edge="bottom")
    # base + hover + selected + disabled states, all scoped to the selector
    assert "RibbonBar QTabBar::tab {" in qss
    assert "RibbonBar QTabBar::tab:hover:!selected {" in qss
    assert "RibbonBar QTabBar::tab:selected {" in qss
    assert "RibbonBar QTabBar::tab:disabled {" in qss
    # accent bar rides the requested edge
    assert f"border-bottom: 2px solid {t.accent}" in qss


def test_edge_right_moves_accent_bar_and_rounds_left():
    t = detect()
    qss = _tab_language_qss(t, "QTabBar#leftTabsBar::tab", edge="right")
    assert f"border-right: 2px solid {t.accent}" in qss
    assert "border-bottom-left-radius: 5px" in qss   # rounds the edge away from content
