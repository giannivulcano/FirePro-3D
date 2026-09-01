def test_theme_tokens_and_qss(qapp):
    # The manager now reads the house theme (underlay_manager_theme.py retired);
    # DARK / Theme / the manager QSS builder all live in firepro3d.theme.
    from firepro3d.theme import DARK, Theme, build_underlay_manager_qss
    assert isinstance(DARK, Theme)
    # accent token is the house green
    assert DARK.accent.lower() == "#63be8b"
    c = DARK.color("accent")
    assert c.alpha() == 255
    c2 = DARK.color("accent", 128)
    assert c2.alpha() == 128
    qss = build_underlay_manager_qss(DARK)
    assert "#UnderlayManagerDialog" in qss
    assert "$accent" not in qss  # all tokens substituted


def test_generic_button_hover_uses_accent(qapp):
    """The generic QPushButton hover fills accent_soft + accent border (not grey).

    House convention: interactive hover uses the accent, never a neutral
    surface2/faint wash. This asserts against the resolved (detect()) theme.
    """
    from firepro3d.theme import build_underlay_manager_qss, detect

    t = detect()
    qss = build_underlay_manager_qss(t)

    # Isolate the generic :hover:enabled rule (exclude variant-specific ones).
    hover_lines = [
        ln for ln in qss.splitlines()
        if "QPushButton:hover:enabled" in ln and 'variant="' not in ln
    ]
    assert len(hover_lines) == 1, hover_lines
    rule = hover_lines[0]

    # Border uses the accent; fill uses accent_soft; grey tokens are gone.
    assert f"border-color: {t.accent}" in rule
    assert t.accent_soft in rule
    assert t.surface2 not in rule


def test_tree_qss_selector_retargeted_to_qtreeview(qapp):
    """The manager view is a QTreeView, so its QSS block must target
    ``QTreeView#underlayTable`` — Qt QSS does not match a QTableView selector to
    a QTreeView, which left the whole block (bg / accent hover / selection)
    inert. This asserts the selector was retargeted and fully resolves.
    """
    from firepro3d.theme import build_underlay_manager_qss, detect

    t = detect()
    qss = build_underlay_manager_qss(t)

    # Retargeted: tree selector present, stale table selector gone.
    assert "QTreeView#underlayTable" in qss
    assert "QTableView#underlayTable" not in qss

    # The accent hover rule now applies to the tree, with accent_soft resolved.
    hover_lines = [
        ln for ln in qss.splitlines()
        if "QTreeView#underlayTable::item:hover" in ln
    ]
    assert len(hover_lines) == 1, hover_lines
    assert t.accent_soft in hover_lines[0]
    assert "$accent" not in qss  # all tokens substituted
