"""Paper pass protocol (paper-space.md s6.2): the driver's unwind and the
guarded enter (design D2 / D6). Per-family round trips land with Tasks 3-14."""
import pytest

from firepro3d import paper_pass as pp


class _Fake:
    def __init__(self, log, name, boom=False):
        self.log, self.name, self.boom = log, name, boom

    def exit_paper_pass(self, token):
        self.log.append(self.name)
        if self.boom:
            raise RuntimeError(self.name)


def test_unwind_runs_in_reverse_and_tolerates_a_raise():
    log = []
    a, b, c = _Fake(log, "a"), _Fake(log, "b", boom=True), _Fake(log, "c")
    saved = pp.PassTokens()
    for o in (a, b, c):
        saved.push(o, o.exit_paper_pass, object())
    with pytest.raises(RuntimeError, match="b"):
        pp.unwind(saved)
    assert log == ["c", "b", "a"]
    assert not saved, "every token is consumed, so a second unwind is a no-op"


def test_unwind_reraises_the_first_error_after_the_full_unwind():
    log = []
    a, b = _Fake(log, "a", boom=True), _Fake(log, "b", boom=True)
    saved = pp.PassTokens()
    for o in (a, b):
        saved.push(o, o.exit_paper_pass, None)
    with pytest.raises(RuntimeError, match="b"):      # b exits first (reverse)
        pp.unwind(saved)
    assert log == ["b", "a"]


def test_enter_guarded_unwinds_a_partly_entered_item():
    log = []

    def write():
        log.append("write")
        raise ValueError("mid")

    with pytest.raises(ValueError):
        pp.enter_guarded(lambda tok: log.append(("exit", tok)), "T", write)
    assert log == ["write", ("exit", "T")]
