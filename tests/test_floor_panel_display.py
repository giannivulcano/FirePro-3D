"""Data-level tests for FloorSlab's mode-conditional property panel adapter.

Task 6: FloorSlab.get_properties()/set_property() expose the two-boundary
elevation model with rows that CHANGE per boundary mode. The property panel
re-queries get_properties() after every edit, so returning mode-conditional
key sets is what drives dynamic show/hide.

Reuses the _FakeLM/_FakeScene z-range harness from test_floor_elevation_model.
"""

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.floor_slab import FloorSlab
from firepro3d.constants import MIN_FLOOR_THICKNESS_MM


# ── Fake level-manager / scene harness (mirrors test_floor_elevation_model) ──

class _FakeLevel:
    def __init__(self, elevation):
        self.elevation = elevation


class _FakeLM:
    def __init__(self, elevs):
        self._e = {k: _FakeLevel(v) for k, v in elevs.items()}

    def get(self, name):
        return self._e.get(name)


class _FakeScene:
    def __init__(self, lm):
        self._level_manager = lm


LM = _FakeLM({"Level 1": 0.0, "Level 2": 3048.0})


def _square():
    return [QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1000), QPointF(0, 1000)]


def _slab(scene=False, **kw):
    s = FloorSlab(points=_square())
    for k, v in kw.items():
        setattr(s, k, v)
    if scene:
        s._scene = _FakeScene(LM)
    return s


# ── get_properties(): mode-conditional rows ──────────────────────────────────

def test_no_colour_row(qapp):
    """Appearance moved to Display Manager — no Colour row on the panel."""
    props = _slab().get_properties()
    assert "Colour" not in props
    assert "Color" not in props


def test_level_mode_shows_level_and_offset(qapp):
    """Top level mode → Top Reference enum + Top Level + Top Offset, no Top Z."""
    props = _slab(_top_mode="level").get_properties()
    assert props["Top Reference"]["type"] == "enum"
    assert "Top Level" in props
    assert "Top Offset" in props
    assert "Top Z" not in props


def test_absolute_mode_shows_abs_z_only(qapp):
    """Top absolute mode → Top Z present, Top Level/Top Offset absent."""
    props = _slab(_top_mode="absolute").get_properties()
    assert "Top Z" in props
    assert "Top Level" not in props
    assert "Top Offset" not in props


def test_thickness_mode_shows_thickness_input(qapp):
    """Bottom thickness mode → Thickness dimension with the min clamp."""
    props = _slab(_bottom_mode="thickness").get_properties()
    assert props["Thickness"]["type"] == "dimension"
    assert props["Thickness"]["minimum"] == MIN_FLOOR_THICKNESS_MM


def test_derived_thickness_readout_when_not_thickness_mode(qapp):
    """Bottom non-thickness mode → Thickness (derived) is a read-only label."""
    props = _slab(
        scene=True,
        _top_mode="level", _top_level="Level 2", _top_offset_mm=0.0,
        _bottom_mode="level", _bottom_level="Level 1", _bottom_offset_mm=0.0,
    ).get_properties()
    assert props["Thickness (derived)"]["type"] == "label"
    # No editable Thickness input when not in thickness mode
    assert "Thickness" not in props


def test_inversion_emits_warning_row(qapp):
    """Top at 0, bottom at 200 (resolvable via scene) → warning row present."""
    props = _slab(
        scene=True,
        _top_mode="absolute", _top_abs_z_mm=0.0,
        _bottom_mode="absolute", _bottom_abs_z_mm=200.0,
    ).get_properties()
    warnings = [m for m in props.values() if m.get("type") == "warning"]
    assert warnings, "expected an inversion warning row"


def test_no_inversion_no_warning(qapp):
    """Healthy floor (top above bottom) → no warning row."""
    props = _slab(
        scene=True,
        _top_mode="absolute", _top_abs_z_mm=500.0,
        _bottom_mode="absolute", _bottom_abs_z_mm=100.0,
    ).get_properties()
    warnings = [m for m in props.values() if m.get("type") == "warning"]
    assert not warnings


# ── set_property(): mode switch, values, guards ──────────────────────────────

def test_set_property_mode_switch_and_values(qapp):
    s = _slab()
    s.set_property("Top Reference", "Absolute")
    assert s._top_mode == "absolute"
    s.set_property("Top Z", 500.0)
    assert s._top_abs_z_mm == pytest.approx(500.0)


def test_set_property_bad_mode_label_noops(qapp):
    """An out-of-options label leaves the mode unchanged and does not crash."""
    s = _slab(_top_mode="level")
    s.set_property("Top Reference", "Nonsense")
    assert s._top_mode == "level"


def test_set_property_thickness_clamps_min(qapp):
    s = _slab(_bottom_mode="thickness")
    s.set_property("Thickness", -5)
    assert s._thickness_mm == pytest.approx(MIN_FLOOR_THICKNESS_MM)


def test_set_property_bottom_values(qapp):
    s = _slab(_bottom_mode="absolute")
    s.set_property("Bottom Reference", "Level")
    assert s._bottom_mode == "level"
    s.set_property("Bottom Level", "Level 2")
    assert s._bottom_level == "Level 2"
    s.set_property("Bottom Offset", -100.0)
    assert s._bottom_offset_mm == pytest.approx(-100.0)


def test_set_name(qapp):
    s = _slab()
    s.set_property("Name", "Ground Floor")
    assert s.name == "Ground Floor"


# ── Live re-query show/hide proof (data-level) ───────────────────────────────

def test_mode_switch_changes_key_set(qapp):
    """Proving the panel's re-query will show/hide: the key set differs after
    a mode switch — Top Level/Offset drop out and Top Z appears."""
    s = _slab(_top_mode="level")
    before = set(s.get_properties().keys())
    assert "Top Level" in before and "Top Z" not in before

    s.set_property("Top Reference", "Absolute")
    after = set(s.get_properties().keys())
    assert "Top Z" in after
    assert "Top Level" not in after
    assert "Top Offset" not in after


def test_get_properties_no_level_key(qapp):
    """The retired flat 'Level' row must be gone (replaced by Top/Bottom Level)."""
    props = _slab().get_properties()
    assert "Level" not in props


# ── Live PropertyManager re-query show/hide proof ────────────────────────────

def _flush_deletes(qapp):
    """Force pending deleteLater() (DeferredDelete events) to run now.

    Plain processEvents() does NOT dispatch DeferredDelete, so cleared form
    rows would linger as findChildren() ghosts in a headless test.
    """
    from PyQt6.QtCore import QEvent
    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    qapp.processEvents()


def _row_labels(pm):
    """Field-label texts currently rendered in the panel's form."""
    from PyQt6.QtWidgets import QLabel
    return {w.text() for w in pm.findChildren(QLabel)}


def test_live_panel_mode_switch_drops_and_adds_rows(qapp):
    """Drive the real PropertyManager: switching Top Reference to Absolute and
    re-querying (as the panel does after every edit) drops the Top Level row
    and adds the Top Z row."""
    from firepro3d.property_manager import PropertyManager

    class _LMWithLevels:
        class _Lvl:
            def __init__(self, name, elevation):
                self.name = name
                self.elevation = elevation

        def __init__(self):
            self.levels = [self._Lvl("Level 1", 0.0), self._Lvl("Level 2", 3048.0)]

        def get(self, name):
            for lv in self.levels:
                if lv.name == name:
                    return lv
            return None

    slab = _slab(_top_mode="level", _top_level="Level 1")
    pm = PropertyManager()
    pm.set_level_manager(_LMWithLevels())

    pm.show_properties(slab)
    _flush_deletes(qapp)  # flush deferred deleteLater from any prior render
    before = _row_labels(pm)
    assert "Top Level" in before
    assert "Top Z" not in before

    # Simulate the edit + the panel's re-query (show_properties re-runs
    # get_properties, which now returns a different key set).
    slab.set_property("Top Reference", "Absolute")
    pm.show_properties(slab)
    _flush_deletes(qapp)  # let the old "Top Level" field widget be destroyed
    after = _row_labels(pm)
    assert "Top Z" in after
    assert "Top Level" not in after


class _LMWithLevels:
    """Real-ish level manager for live PropertyManager tests."""

    class _Lvl:
        def __init__(self, name, elevation):
            self.name = name
            self.elevation = elevation

    def __init__(self):
        self.levels = [self._Lvl("Level 1", 0.0), self._Lvl("Level 2", 3048.0)]

    def get(self, name):
        for lv in self.levels:
            if lv.name == name:
                return lv
        return None


@pytest.mark.parametrize(
    "top_mode, bottom_mode",
    [
        ("absolute", "thickness"),
        ("absolute", "absolute"),
    ],
)
def test_no_spurious_level_combo_in_absolute_modes(qapp, top_mode, bottom_mode):
    """A two-boundary floor in a NON-level mode (neither boundary emits a
    level_ref row) still carries a vestigial `.level` attr. The panel's legacy
    Level-combo fallback must NOT fire for it — the floor owns its elevation via
    Top/Bottom Reference rows, so a legacy 'Level' combo would resurrect the
    retired `.level` coupling and lie about how its elevation is computed.
    """
    from firepro3d.property_manager import PropertyManager

    slab = _slab(scene=True, _top_mode=top_mode, _bottom_mode=bottom_mode)
    # Precondition: no level_ref row is emitted in these modes (so the legacy
    # fallback's `has_level_ref` guard alone would NOT stop the combo).
    props = slab.get_properties()
    assert not [k for k, m in props.items() if m.get("type") == "level_ref"]
    assert hasattr(slab, "level")  # the vestigial attr that baits the fallback

    pm = PropertyManager()
    pm.set_level_manager(_LMWithLevels())
    pm.show_properties(slab)
    _flush_deletes(qapp)

    labels = _row_labels(pm)
    assert "Level" not in labels, (
        f"spurious legacy Level combo leaked in {top_mode}/{bottom_mode} mode; "
        f"labels={sorted(labels)}"
    )
