"""ThemedMessageDialog helpers: return-semantics parity with native dialogs.
exec() is monkeypatched to return Accepted/Rejected so no modal blocks."""
from firepro3d import themed_message as tm


def test_confirm_returns_bool(qapp, monkeypatch):
    monkeypatch.setattr(tm.ThemedMessageDialog, "exec",
                        lambda self: tm.QDialog.DialogCode.Accepted, raising=False)
    assert tm.themed_confirm(None, "T", "Sure?") is True


def test_confirm_cancel_returns_false(qapp, monkeypatch):
    monkeypatch.setattr(tm.ThemedMessageDialog, "exec",
                        lambda self: tm.QDialog.DialogCode.Rejected, raising=False)
    assert tm.themed_confirm(None, "T", "?") is False


def test_info_warn_error_return_none(qapp, monkeypatch):
    monkeypatch.setattr(tm.ThemedMessageDialog, "exec",
                        lambda self: tm.QDialog.DialogCode.Accepted, raising=False)
    assert tm.themed_info(None, "T", "i") is None
    assert tm.themed_warn(None, "T", "w") is None
    assert tm.themed_error(None, "T", "e") is None


def test_input_text_returns_tuple(qapp, monkeypatch):
    monkeypatch.setattr(tm.ThemedMessageDialog, "exec",
                        lambda self: tm.QDialog.DialogCode.Accepted, raising=False)
    val, ok = tm.themed_input_text(None, "T", "Name", initial="abc")
    assert ok is True and val == "abc"


def test_input_text_cancel(qapp, monkeypatch):
    monkeypatch.setattr(tm.ThemedMessageDialog, "exec",
                        lambda self: tm.QDialog.DialogCode.Rejected, raising=False)
    val, ok = tm.themed_input_text(None, "T", "Name", initial="abc")
    assert ok is False


def test_input_number_dimension(qapp, monkeypatch):
    monkeypatch.setattr(tm.ThemedMessageDialog, "exec",
                        lambda self: tm.QDialog.DialogCode.Accepted, raising=False)
    val, ok = tm.themed_input_number(None, "T", "Len", initial=100.0, dimension=True)
    assert ok is True and isinstance(val, float)


def test_input_number_plain(qapp, monkeypatch):
    monkeypatch.setattr(tm.ThemedMessageDialog, "exec",
                        lambda self: tm.QDialog.DialogCode.Accepted, raising=False)
    val, ok = tm.themed_input_number(None, "T", "Factor", initial=2.5, dimension=False)
    assert ok is True and abs(val - 2.5) < 1e-9


def test_input_choice_returns_current(qapp, monkeypatch):
    monkeypatch.setattr(tm.ThemedMessageDialog, "exec",
                        lambda self: tm.QDialog.DialogCode.Accepted, raising=False)
    val, ok = tm.themed_input_choice(None, "T", "Pick", ["x", "y", "z"], current=1)
    assert ok is True and val == "y"


def test_confirm_custom_labels_and_danger(qapp, monkeypatch):
    monkeypatch.setattr(tm.ThemedMessageDialog, "exec",
                        lambda self: tm.QDialog.DialogCode.Accepted, raising=False)
    assert tm.themed_confirm(None, "T", "Delete?", danger=True,
                             ok_label="Delete", cancel_label="Cancel") is True
