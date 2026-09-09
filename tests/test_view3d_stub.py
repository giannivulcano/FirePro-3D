"""Guard: the opt-in stub_view3d fixture (#367) makes MainWindow construct a
windowless _StubView3D instead of the real VTK-backed View3D."""


def _make_mainwindow():
    # Ensure the lazy `global View3D` import in main has run, then build a window.
    import firepro3d.view_3d  # noqa: F401  (populate module)
    import main as _main
    if not hasattr(_main, "View3D"):
        from firepro3d.view_3d import View3D as _V
        _main.View3D = _V
    return _main.MainWindow()


def test_stub_view3d_is_installed(qapp, stub_view3d):
    win = _make_mainwindow()
    try:
        assert isinstance(win.view_3d, stub_view3d)
        assert win.view_3d._plotter is None  # no VTK plotter allocated
    finally:
        win._modified = False
        win.close()
