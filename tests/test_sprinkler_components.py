"""tests/test_sprinkler_components.py — Unit tests for sprinkler system components.

Covers: SprinklerDatabase, SprinklerRecord, Pipe, Node, Fitting, Sprinkler.
"""

from __future__ import annotations

import json
import math
import os
import tempfile

import pytest
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtCore import QPointF

from firepro3d.sprinkler_db import SprinklerRecord, SprinklerDatabase
from firepro3d.node import Node
from firepro3d.pipe import Pipe
from firepro3d.fitting import Fitting
from firepro3d.sprinkler import Sprinkler
from firepro3d.constants import DEFAULT_LEVEL, DEFAULT_CEILING_OFFSET_MM


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def scene(qapp):
    """Provide a bare QGraphicsScene for items that need one."""
    return QGraphicsScene()


@pytest.fixture
def two_nodes(qapp, scene):
    """Two nodes placed on a scene, 1000 mm apart horizontally."""
    n1 = Node(0, 0)
    n2 = Node(1000, 0)
    scene.addItem(n1)
    scene.addItem(n2)
    return n1, n2


def _tmp_db_path() -> str:
    """Return a unique temp file path for a SprinklerDatabase."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)  # let SprinklerDatabase create it fresh
    return path


# ─────────────────────────────────────────────────────────────────────────────
# 1. SprinklerRecord
# ─────────────────────────────────────────────────────────────────────────────

class TestSprinklerRecord:

    def test_create_record(self):
        rec = SprinklerRecord(
            id="test_1", manufacturer="Acme", model="X100",
            type="Pendent", k_factor=5.6, min_pressure=7.0,
            coverage_area=130.0, temp_rating=155, orifice='1/2"',
        )
        assert rec.id == "test_1"
        assert rec.manufacturer == "Acme"
        assert rec.k_factor == 5.6
        assert rec.type == "Pendent"

    def test_to_dict_roundtrip(self):
        rec = SprinklerRecord(
            id="rt_1", manufacturer="Viking", model="VK100",
            type="Upright", k_factor=8.0, min_pressure=10.0,
            coverage_area=196.0, temp_rating=200, orifice='3/4"',
            notes="test note",
        )
        d = rec.to_dict()
        restored = SprinklerRecord.from_dict(d)
        assert restored.id == rec.id
        assert restored.manufacturer == rec.manufacturer
        assert restored.model == rec.model
        assert restored.type == rec.type
        assert restored.k_factor == rec.k_factor
        assert restored.min_pressure == rec.min_pressure
        assert restored.coverage_area == rec.coverage_area
        assert restored.temp_rating == rec.temp_rating
        assert restored.orifice == rec.orifice
        assert restored.notes == rec.notes

    def test_from_dict_defaults(self):
        """from_dict with empty dict should produce sensible defaults."""
        rec = SprinklerRecord.from_dict({})
        assert rec.id == ""
        assert rec.k_factor == 5.6
        assert rec.min_pressure == 7.0
        assert rec.coverage_area == 130.0
        assert rec.temp_rating == 155
        assert rec.orifice == '1/2"'

    def test_to_dict_contains_all_fields(self):
        rec = SprinklerRecord(
            id="f", manufacturer="M", model="Mo", type="Sidewall",
            k_factor=1.0, min_pressure=2.0, coverage_area=3.0,
            temp_rating=100, orifice="x", notes="n",
        )
        d = rec.to_dict()
        for key in ("id", "manufacturer", "model", "type", "k_factor",
                     "min_pressure", "coverage_area", "temp_rating",
                     "orifice", "notes"):
            assert key in d


# ─────────────────────────────────────────────────────────────────────────────
# 2. SprinklerDatabase
# ─────────────────────────────────────────────────────────────────────────────

class TestSprinklerDatabase:

    def test_new_db_seeds_defaults(self):
        path = _tmp_db_path()
        try:
            db = SprinklerDatabase(path)
            lib = db.library
            assert len(lib) > 0, "Default library should not be empty"
            # Verify a known default record is present
            ids = [r.id for r in lib]
            assert "tyco_ty315" in ids
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_add_to_library(self):
        path = _tmp_db_path()
        try:
            db = SprinklerDatabase(path)
            initial_count = len(db.library)
            rec = SprinklerRecord(
                id="custom_1", manufacturer="Custom", model="C1",
                type="Pendent", k_factor=5.6, min_pressure=7.0,
                coverage_area=130.0, temp_rating=155, orifice='1/2"',
            )
            db.add_to_library(rec)
            assert len(db.library) == initial_count + 1
            assert db.library[-1].id == "custom_1"
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_delete_from_library(self):
        path = _tmp_db_path()
        try:
            db = SprinklerDatabase(path)
            initial_count = len(db.library)
            db.delete_from_library(0)
            assert len(db.library) == initial_count - 1
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_delete_out_of_range_is_noop(self):
        path = _tmp_db_path()
        try:
            db = SprinklerDatabase(path)
            count = len(db.library)
            db.delete_from_library(9999)
            assert len(db.library) == count
            db.delete_from_library(-1)
            assert len(db.library) == count
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_update_in_library(self):
        path = _tmp_db_path()
        try:
            db = SprinklerDatabase(path)
            updated = SprinklerRecord(
                id="updated", manufacturer="Updated", model="U1",
                type="Concealed", k_factor=11.2, min_pressure=10.0,
                coverage_area=200.0, temp_rating=200, orifice='3/4"',
            )
            db.update_in_library(0, updated)
            assert db.library[0].id == "updated"
            assert db.library[0].manufacturer == "Updated"
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_find_records_by_manufacturer(self):
        path = _tmp_db_path()
        try:
            db = SprinklerDatabase(path)
            results = db.find_records(manufacturer="Viking")
            assert len(results) > 0
            assert all(r.manufacturer == "Viking" for r in results)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_find_records_by_type(self):
        path = _tmp_db_path()
        try:
            db = SprinklerDatabase(path)
            results = db.find_records(type_="Sidewall")
            assert len(results) > 0
            assert all(r.type == "Sidewall" for r in results)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_find_records_combined_filter(self):
        path = _tmp_db_path()
        try:
            db = SprinklerDatabase(path)
            results = db.find_records(manufacturer="Tyco / JCI", type_="Pendent")
            assert len(results) > 0
            assert all(r.manufacturer == "Tyco / JCI" and r.type == "Pendent"
                       for r in results)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_get_unique_manufacturers(self):
        path = _tmp_db_path()
        try:
            db = SprinklerDatabase(path)
            mfgs = db.get_unique_manufacturers()
            assert isinstance(mfgs, list)
            assert "Viking" in mfgs
            assert mfgs == sorted(mfgs), "Manufacturers should be sorted"
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_get_models_for_manufacturer(self):
        path = _tmp_db_path()
        try:
            db = SprinklerDatabase(path)
            models = db.get_models_for("Viking")
            assert len(models) > 0
            assert models == sorted(models)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_get_types_for_manufacturer(self):
        path = _tmp_db_path()
        try:
            db = SprinklerDatabase(path)
            types = db.get_types_for("Viking")
            assert len(types) > 0
            assert types == sorted(types)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_templates_add_and_remove(self):
        path = _tmp_db_path()
        try:
            db = SprinklerDatabase(path)
            rec = db.library[0]
            db.add_to_templates(rec)
            assert len(db.templates) == 1
            assert db.templates[0].id == rec.id

            # Adding same record again should be a no-op (duplicate by id)
            db.add_to_templates(rec)
            assert len(db.templates) == 1

            db.delete_from_templates(0)
            assert len(db.templates) == 0
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_persistence_across_instances(self):
        path = _tmp_db_path()
        try:
            db1 = SprinklerDatabase(path)
            rec = SprinklerRecord(
                id="persist_test", manufacturer="P", model="P1",
                type="Pendent", k_factor=5.6, min_pressure=7.0,
                coverage_area=130.0, temp_rating=155, orifice='1/2"',
            )
            db1.add_to_library(rec)
            count = len(db1.library)

            # Create a second instance reading the same file
            db2 = SprinklerDatabase(path)
            assert len(db2.library) == count
            assert db2.library[-1].id == "persist_test"
        finally:
            if os.path.exists(path):
                os.remove(path)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Pipe diameter / schedule lookup
# ─────────────────────────────────────────────────────────────────────────────

class TestPipeDiameterSchedule:

    def test_internal_diameter_keys(self):
        expected = ['¾"Ø', '1"Ø', '1-¼"Ø', '1-½"Ø', '2"Ø', '2-½"Ø', '3"Ø', '4"Ø', '5"Ø', '6"Ø', '8"Ø']
        assert Pipe._INTERNAL_DIAMETERS == expected

    def test_od_table_covers_all_internal_keys(self):
        for key in Pipe._INTERNAL_DIAMETERS:
            assert key in Pipe.NOMINAL_OD_IN, f"OD table missing {key}"

    def test_od_values_are_positive(self):
        for key, val in Pipe.NOMINAL_OD_IN.items():
            assert val > 0, f"OD for {key} should be positive"

    def test_inner_diameter_schedules(self):
        """Every schedule should have entries for all internal diameter keys."""
        for schedule, table in Pipe.INNER_DIAMETER_IN.items():
            for key in Pipe._INTERNAL_DIAMETERS:
                assert key in table, f"{schedule} missing {key}"

    def test_inner_diameter_less_than_od(self):
        """ID must be less than OD for every combination."""
        for schedule, table in Pipe.INNER_DIAMETER_IN.items():
            for key in Pipe._INTERNAL_DIAMETERS:
                od = Pipe.NOMINAL_OD_IN[key]
                inner = table[key]
                assert inner < od, (
                    f"{schedule} {key}: ID={inner} should be < OD={od}"
                )

    def test_display_to_internal_mapping(self):
        """Imperial and metric display strings should map back to internal keys."""
        for imp, internal in zip(Pipe._IMPERIAL_DIAMETERS, Pipe._INTERNAL_DIAMETERS):
            assert Pipe._DISPLAY_TO_INT[imp] == internal
        for met, internal in zip(Pipe._METRIC_DIAMETERS, Pipe._INTERNAL_DIAMETERS):
            assert Pipe._DISPLAY_TO_INT[met] == internal

    def test_int_to_imperial_mapping(self):
        for internal, imperial in zip(Pipe._INTERNAL_DIAMETERS, Pipe._IMPERIAL_DIAMETERS):
            assert Pipe._INT_TO_IMPERIAL[internal] == imperial

    def test_int_to_metric_mapping(self):
        for internal, metric in zip(Pipe._INTERNAL_DIAMETERS, Pipe._METRIC_DIAMETERS):
            assert Pipe._INT_TO_METRIC[internal] == metric


# ─────────────────────────────────────────────────────────────────────────────
# 4. Pipe C-Factor and inner diameter lookup
# ─────────────────────────────────────────────────────────────────────────────

class TestPipeCFactor:

    def test_default_c_factor(self, qapp, two_nodes):
        n1, n2 = two_nodes
        pipe = Pipe(n1, n2)
        assert pipe._properties["C-Factor"]["value"] == "120"

    def test_get_inner_diameter_default(self, qapp, two_nodes):
        """Default pipe is 1 inch Sch 40 -> 1.049 in."""
        n1, n2 = two_nodes
        pipe = Pipe(n1, n2)
        assert pipe.get_inner_diameter() == pytest.approx(1.049)

    def test_get_inner_diameter_2inch_sch10(self, qapp, two_nodes):
        n1, n2 = two_nodes
        pipe = Pipe(n1, n2)
        pipe._properties["Diameter"]["value"] = '2"Ø'
        pipe._properties["Schedule"]["value"] = "Sch 10"
        assert pipe.get_inner_diameter() == pytest.approx(2.157)

    def test_get_inner_diameter_fallback(self, qapp, two_nodes):
        """Unknown schedule/diameter should fall back to 2.067 (2 in Sch 40)."""
        n1, n2 = two_nodes
        pipe = Pipe(n1, n2)
        pipe._properties["Diameter"]["value"] = "bogus"
        pipe._properties["Schedule"]["value"] = "bogus"
        # Fallback schedule is Sch 40, fallback nominal is 2.067
        assert pipe.get_inner_diameter() == pytest.approx(2.067)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Pipe serialization (scene_io save/load format)
# ─────────────────────────────────────────────────────────────────────────────

class TestPipeSerialization:

    def test_properties_dict_keys(self, qapp, two_nodes):
        """Pipe _properties should contain the expected keys."""
        n1, n2 = two_nodes
        pipe = Pipe(n1, n2)
        expected_keys = {
            "Diameter", "Schedule", "C-Factor", "Material",
            "Line Type",
            "Colour", "Phase", "Show Label", "Label Size",
        }
        actual = {k for k in pipe._properties if not k.startswith("──")}
        assert expected_keys.issubset(actual)

    def test_raw_properties_serializable(self, qapp, two_nodes):
        """Property values should survive JSON roundtrip."""
        n1, n2 = two_nodes
        pipe = Pipe(n1, n2)
        raw = {k: v["value"] for k, v in pipe._properties.items()}
        dumped = json.dumps(raw)
        restored = json.loads(dumped)
        assert restored["Diameter"] == '1"Ø'
        assert restored["Schedule"] == "Sch 40"
        assert restored["C-Factor"] == "120"

    def test_set_property_diameter_updates_line_type(self, qapp, two_nodes):
        """Setting diameter >= 3 inch should auto-assign Main line type."""
        n1, n2 = two_nodes
        pipe = Pipe(n1, n2)
        pipe.set_property("Diameter", '3"Ø')
        assert pipe._properties["Line Type"]["value"] == "Main"

    def test_set_property_diameter_branch(self, qapp, two_nodes):
        """Setting diameter < 3 inch should auto-assign Branch line type."""
        n1, n2 = two_nodes
        pipe = Pipe(n1, n2)
        pipe.set_property("Diameter", '3"Ø')
        assert pipe._properties["Line Type"]["value"] == "Main"
        pipe.set_property("Diameter", '2"Ø')
        assert pipe._properties["Line Type"]["value"] == "Branch"

    def test_display_width_main_vs_branch(self, qapp, two_nodes):
        n1, n2 = two_nodes
        pipe = Pipe(n1, n2)
        assert pipe.display_width_mm() == Pipe.BRANCH_WIDTH_MM
        pipe._properties["Line Type"]["value"] = "Main"
        assert pipe.display_width_mm() == Pipe.MAIN_WIDTH_MM


# ─────────────────────────────────────────────────────────────────────────────
# 6. Node creation and position
# ─────────────────────────────────────────────────────────────────────────────

class TestNodeCreation:

    def test_basic_creation(self, qapp):
        node = Node(100, 200)
        assert node.x_pos == 100
        assert node.y_pos == 200
        assert node.z_pos == 0

    def test_creation_with_z(self, qapp):
        node = Node(50, 60, z=3048.0)
        assert node.z_pos == 3048.0

    def test_default_ceiling_properties(self, qapp):
        node = Node(0, 0)
        assert node.ceiling_level == DEFAULT_LEVEL
        assert node.ceiling_offset == DEFAULT_CEILING_OFFSET_MM

    def test_scene_position(self, qapp, scene):
        node = Node(300, 400)
        scene.addItem(node)
        pos = node.scenePos()
        assert pos.x() == pytest.approx(300)
        assert pos.y() == pytest.approx(400)

    def test_z_range_mm(self, qapp):
        node = Node(0, 0, z=1500.0)
        zr = node.z_range_mm()
        assert zr == (1500.0, 1500.0)

    def test_radius_constant(self, qapp):
        assert Node.RADIUS == 13

    def test_initial_pipes_empty(self, qapp):
        node = Node(0, 0)
        assert node.pipes == []

    def test_initial_sprinkler_none(self, qapp):
        node = Node(0, 0)
        assert node.sprinkler is None
        assert node.has_sprinkler() is False

    def test_initial_fitting_exists(self, qapp):
        node = Node(0, 0)
        assert node.fitting is not None
        assert node.has_fitting() is True


# ─────────────────────────────────────────────────────────────────────────────
# 7. Node serialization
# ─────────────────────────────────────────────────────────────────────────────

class TestNodeSerialization:

    def test_get_properties_returns_ceiling_keys(self, qapp):
        node = Node(0, 0)
        props = node.get_properties()
        assert "Ceiling Level" in props
        assert "Ceiling Offset" in props

    def test_set_ceiling_level(self, qapp):
        node = Node(0, 0)
        node.set_property("Ceiling Level", "Level 2")
        assert node.ceiling_level == "Level 2"
        assert node._properties["Ceiling Level"]["value"] == "Level 2"

    def test_set_ceiling_offset_numeric(self, qapp):
        node = Node(0, 0)
        # Without a scene/scale manager, set_property parses float strings
        node.set_property("Ceiling Offset", "-101.6")
        assert node.ceiling_offset == pytest.approx(-101.6)

    def test_node_save_format(self, qapp, scene):
        """Verify the dict structure matches scene_io save format."""
        node = Node(100, 200, z=1000)
        scene.addItem(node)
        node.ceiling_level = "Level 2"
        node.ceiling_offset = -76.2
        entry = {
            "x": node.scenePos().x(),
            "y": node.scenePos().y(),
            "elevation": node.z_pos,
            "ceiling_level": node.ceiling_level,
            "ceiling_offset_mm": node.ceiling_offset,
        }
        assert entry["x"] == pytest.approx(100)
        assert entry["y"] == pytest.approx(200)
        assert entry["elevation"] == 1000
        assert entry["ceiling_level"] == "Level 2"
        assert entry["ceiling_offset_mm"] == pytest.approx(-76.2)

    def test_add_remove_sprinkler(self, qapp, scene):
        node = Node(0, 0)
        scene.addItem(node)
        node.add_sprinkler()
        assert node.has_sprinkler() is True
        assert node.sprinkler is not None
        node.delete_sprinkler()
        assert node.has_sprinkler() is False


# ─────────────────────────────────────────────────────────────────────────────
# 8. Fitting type assignment
# ─────────────────────────────────────────────────────────────────────────────

class TestFittingType:

    def _make_pipe_pair(self, scene, n1, n2):
        """Create a pipe between two on-scene nodes and return it."""
        pipe = Pipe(n1, n2)
        scene.addItem(pipe)
        return pipe

    def test_zero_pipes_no_fitting(self, qapp, scene):
        node = Node(0, 0)
        scene.addItem(node)
        fitting = node.fitting
        result = fitting.determine_type([])
        assert result == "no fitting"

    def test_one_pipe_cap(self, qapp, scene):
        n1 = Node(0, 0)
        n2 = Node(1000, 0)
        scene.addItem(n1)
        scene.addItem(n2)
        pipe = self._make_pipe_pair(scene, n1, n2)
        result = n1.fitting.determine_type([pipe])
        assert result == "cap"

    def test_two_pipes_collinear_no_fitting(self, qapp, scene):
        """Two collinear pipes (180 degrees) produce no fitting."""
        n1 = Node(-1000, 0)
        n2 = Node(0, 0)
        n3 = Node(1000, 0)
        for n in (n1, n2, n3):
            scene.addItem(n)
        p1 = self._make_pipe_pair(scene, n1, n2)
        p2 = self._make_pipe_pair(scene, n2, n3)
        result = n2.fitting.determine_type([p1, p2])
        assert result == "no fitting"

    def test_two_pipes_90_degree_elbow(self, qapp, scene):
        """Two pipes at 90 degrees produce a 90 degree elbow."""
        n1 = Node(0, 0)
        n2 = Node(1000, 0)
        n3 = Node(0, 1000)
        for n in (n1, n2, n3):
            scene.addItem(n)
        p1 = self._make_pipe_pair(scene, n1, n2)
        p2 = self._make_pipe_pair(scene, n1, n3)
        result = n1.fitting.determine_type([p1, p2])
        assert result == "90elbow"

    def test_three_pipes_tee(self, qapp, scene):
        """Three pipes with a 90-degree branch produce a tee."""
        center = Node(0, 0)
        left = Node(-1000, 0)
        right = Node(1000, 0)
        top = Node(0, -1000)
        for n in (center, left, right, top):
            scene.addItem(n)
        p1 = self._make_pipe_pair(scene, left, center)
        p2 = self._make_pipe_pair(scene, center, right)
        p3 = self._make_pipe_pair(scene, center, top)
        result = center.fitting.determine_type([p1, p2, p3])
        assert result == "tee"

    def test_four_pipes_cross(self, qapp, scene):
        """Four pipes in a + pattern produce a cross."""
        center = Node(0, 0)
        left = Node(-1000, 0)
        right = Node(1000, 0)
        top = Node(0, -1000)
        bottom = Node(0, 1000)
        for n in (center, left, right, top, bottom):
            scene.addItem(n)
        p1 = self._make_pipe_pair(scene, left, center)
        p2 = self._make_pipe_pair(scene, center, right)
        p3 = self._make_pipe_pair(scene, center, top)
        p4 = self._make_pipe_pair(scene, center, bottom)
        result = center.fitting.determine_type([p1, p2, p3, p4])
        assert result == "cross"

    def test_fitting_initial_type(self, qapp):
        node = Node(0, 0)
        assert node.fitting.type == "no fitting"

    def test_fitting_symbols_dict_keys(self):
        """All fitting types should have a symbol path defined."""
        expected = {
            "no fitting", "cap", "45elbow", "90elbow", "tee",
            "wye", "cross", "tee_up", "tee_down", "elbow_up", "elbow_down",
        }
        assert expected.issubset(set(Fitting.SYMBOLS.keys()))


# ─────────────────────────────────────────────────────────────────────────────
# 9. Sprinkler properties
# ─────────────────────────────────────────────────────────────────────────────

class TestSprinklerProperties:

    def test_sprinkler_default_properties(self, qapp, scene):
        node = Node(0, 0)
        scene.addItem(node)
        spr = Sprinkler(node)
        props = spr._properties
        assert props["Manufacturer"]["value"] == "Tyco"
        assert props["Orientation"]["value"] == "Upright"
        assert props["K-Factor"]["value"] == "5.6"
        assert props["Coverage Area"]["value"] == "130"
        assert props["Min Pressure"]["value"] == "7"

    def test_sprinkler_set_property(self, qapp, scene):
        node = Node(0, 0)
        scene.addItem(node)
        spr = Sprinkler(node)
        spr.set_property("Manufacturer", "Viking")
        assert spr._properties["Manufacturer"]["value"] == "Viking"

    def test_sprinkler_set_unknown_property_noop(self, qapp, scene):
        node = Node(0, 0)
        scene.addItem(node)
        spr = Sprinkler(node)
        spr.set_property("NonExistent", "value")
        assert "NonExistent" not in spr._properties

    def test_sprinkler_graphic_options(self, qapp):
        """All graphic options should have a file path in GRAPHICS."""
        for name in ("Sprinkler0", "Sprinkler1", "Sprinkler2"):
            assert name in Sprinkler.GRAPHICS

    def test_sprinkler_ceiling_offset_syncs_to_node(self, qapp, scene):
        node = Node(0, 0)
        scene.addItem(node)
        spr = Sprinkler(node)
        spr.set_property("Ceiling Offset", -101.6)
        assert node.ceiling_offset == pytest.approx(-101.6)

    def test_sprinkler_ceiling_level_syncs_to_node(self, qapp, scene):
        node = Node(0, 0)
        scene.addItem(node)
        spr = Sprinkler(node)
        spr.set_property("Ceiling Level", "Level 2")
        assert node.ceiling_level == "Level 2"

    def test_sprinkler_get_properties_includes_ceiling(self, qapp, scene):
        node = Node(0, 0)
        scene.addItem(node)
        spr = Sprinkler(node)
        props = spr.get_properties()
        assert "Ceiling Level" in props
        assert "Ceiling Offset" in props

    def test_sprinkler_scale_constants(self):
        assert Sprinkler.SVG_NATURAL_PX == 30.0
        assert Sprinkler.TARGET_MM == pytest.approx(24.0 * 25.4)
        assert Sprinkler.SCALE == pytest.approx(Sprinkler.TARGET_MM / Sprinkler.SVG_NATURAL_PX)

    def test_template_sprinkler_no_node(self, qapp):
        """A Sprinkler with node=None should not crash (template mode)."""
        spr = Sprinkler(None)
        assert spr.node is None
        props = spr.get_properties()
        assert "Ceiling Offset" in props
