"""Guard: the autouse QSettings isolation fixture (#312) redirects the
("GV","FirePro3D") scope to a temp INI so tests never touch the real registry."""
from PyQt6.QtCore import QSettings


def test_write_lands_in_temp_not_registry(qapp, real_qsettings):
    # A plain org/app QSettings (the ~90 in-tree form) is intercepted by the
    # isolated subclass and rerouted to a per-test temp INI.
    s = QSettings("GV", "FirePro3D")
    s.setValue("test312/probe", "isolated")
    s.sync()
    assert s.value("test312/probe") == "isolated"
    assert "HKEY" not in s.fileName()   # redirected to an INI, not the registry

    # A handle built from the UNPATCHED class reads the REAL registry — must NOT see it.
    real = real_qsettings(real_qsettings.Format.NativeFormat,
                          real_qsettings.Scope.UserScope, "GV", "FirePro3D")
    assert real.value("test312/probe") is None


def test_fresh_scope_per_test(qapp):
    # The key written by the previous test must not leak into this one
    # (per-test fresh temp dir).
    s = QSettings("GV", "FirePro3D")
    assert s.value("test312/probe") is None
