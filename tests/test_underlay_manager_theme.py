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
