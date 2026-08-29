def test_theme_tokens_and_qss(qapp):
    from firepro3d.underlay_manager_theme import DARK, Theme, build_qss
    assert isinstance(DARK, Theme)
    # accent token is the prototype green
    assert DARK.accent.lower() == "#63be8b"
    c = DARK.color("accent")
    assert c.alpha() == 255
    c2 = DARK.color("accent", 128)
    assert c2.alpha() == 128
    qss = build_qss(DARK)
    assert "#UnderlayManagerDialog" in qss
    assert "$accent" not in qss  # all tokens substituted
