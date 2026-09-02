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


def test_tree_branch_strip_keeps_base_background(qapp):
    """The ``::branch`` strip (indent / disclosure area to the left of the
    first column) must paint the base row background — not the selection/hover
    accent — so a hovered/selected CHILD (layer) row's highlight does not bleed
    leftward past the row content into the indentation. Regression guard for the
    child-row highlight overhang.
    """
    from firepro3d.theme import build_underlay_manager_qss, detect

    t = detect()
    qss = build_underlay_manager_qss(t)

    branch_lines = [
        ln for ln in qss.splitlines()
        if "QTreeView#underlayTable::branch" in ln and "background" in ln
    ]
    assert branch_lines, "expected a ::branch background rule"
    # The branch strip uses the base table background, not an accent.
    for ln in branch_lines:
        assert t.table in ln
        assert t.accent_soft not in ln
    assert "$table" not in qss  # all tokens substituted


def test_tree_branch_disclosure_arrows_via_image(qapp):
    """Styling ``::branch`` disables Qt's native expand/collapse arrows, so the
    manager QSS must supply explicit chevron ``image:`` rules for the
    has-children closed AND open states — otherwise parent (underlay) rows lose
    their disclosure arrows entirely. Regression guard for that.
    """
    import os
    import re

    from firepro3d.theme import build_underlay_manager_qss, detect

    t = detect()
    qss = build_underlay_manager_qss(detect())

    # Closed and open has-children branch states both carry an image rule.
    assert re.search(r"::branch:.*closed[\s\S]*?image:\s*url", qss), \
        "closed has-children branch is missing a chevron image"
    assert re.search(r"::branch:open[\s\S]*?image:\s*url", qss), \
        "open has-children branch is missing a chevron image"

    # Every referenced url() path resolves to a real file on disk.
    urls = re.findall(r'url\("([^"]+)"\)', qss)
    assert urls, "expected chevron url() paths in the branch rules"
    for u in urls:
        assert os.path.exists(u), f"chevron asset missing: {u}"
        assert "\\" not in u, f"url() path must use forward slashes: {u}"

    # No unresolved $tokens anywhere (asset paths included).
    assert not re.findall(r"\$[a-z_]+", qss), "unresolved $tokens remain"
