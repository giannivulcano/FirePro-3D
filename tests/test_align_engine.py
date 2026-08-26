# tests/test_align_engine.py
from firepro3d.align_engine import AlignEngine, ReferenceFeature

def _ref(x, y, label="endpoint"):
    return ReferenceFeature(kind="point", x=x, y=y, source_id=id((x, y)), label=label)

def test_vertical_guide_when_cursor_shares_x():
    eng = AlignEngine()
    refs = [_ref(100.0, 0.0)]
    res = eng.resolve(cursor=(101.0, 500.0), refs=refs, tol=5.0)
    assert res.snapped == (100.0, 500.0)          # X pulled to reference, Y free
    assert any(g.orientation == "v" for g in res.guides)
    assert not any(g.orientation == "h" for g in res.guides)

def test_hv_intersection_snaps_both_axes():
    eng = AlignEngine()
    refs = [_ref(100.0, 0.0), _ref(0.0, 200.0)]
    res = eng.resolve(cursor=(102.0, 198.0), refs=refs, tol=5.0)
    assert res.snapped == (100.0, 200.0)          # intersection of V(x=100) and H(y=200)
    assert {g.orientation for g in res.guides} == {"h", "v"}
    assert res.priority == "guide-intersection"

def test_no_refs_returns_free_cursor():
    eng = AlignEngine()
    res = eng.resolve(cursor=(5.0, 6.0), refs=[], tol=5.0)
    assert res.snapped == (5.0, 6.0)
    assert res.guides == []
    assert res.priority == "free"

def test_out_of_tolerance_no_guide():
    eng = AlignEngine()
    refs = [_ref(100.0, 0.0)]
    res = eng.resolve(cursor=(120.0, 500.0), refs=refs, tol=5.0)
    assert res.snapped == (120.0, 500.0)
    assert res.guides == []
