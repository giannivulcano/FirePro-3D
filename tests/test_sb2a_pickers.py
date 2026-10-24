"""SB2a G-B2 + AC5: Host category row and host-key dropdowns (E9, E10)."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QTabWidget

from firepro3d import theme as th
from firepro3d.block_attributes import normalise_attr
from firepro3d.block_attributes_editor import COLUMNS, AttributesEditorDialog
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorManager
from firepro3d.block_properties_info import BlockPropertiesInfo
from firepro3d.model_space import Model_Space
from firepro3d.property_manager import PropertyManager

WARN = "⚠"
DASH = "—"

# Door host-key combo, by hand from the spec key table (tier headers disabled).
DOOR_ITEMS = [
    ("", True), ("Stored", False),
    ("Mark (Mark)", True), ("Family (Family)", True), ("Type (Type)", True),
    ("Width (Width)", True), ("Height (Height)", True), ("Sill (Sill)", True),
    ("Related", False),
    ("Wall.Mark (Wall.Mark)", True), ("Wall.Name (Wall.Name)", True),
    ("Room.Name (Room.Name)", True), ("Room.Mark (Room.Mark)", True),
    ("Level.Name (Level.Name)", True), ("Level.Number (Level.Number)", True),
]


def _editor(category, attrs):
    project = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    w._keepalive = (tabs, mgr, project)
    w.editor_scene.set_block_meta({**w.editor_scene.block_meta,
                                   "host_category": category, "attributes": attrs})
    return w


def _box(dlg, row):
    return dlg.table.cellWidget(row, COLUMNS.index("host_key"))


def _items(box):
    m = box.model()
    return [(box.itemText(i), m.item(i).isEnabled()) for i in range(box.count())]


def test_host_key_items_grouped_by_tier(qapp):
    w = _editor("Door", [normalise_attr({"key": "W", "source": "host",
                                         "host_key": "Width"})])
    dlg = AttributesEditorDialog(w)
    box = _box(dlg, 0)
    assert _items(box) == DOOR_ITEMS
    assert box.currentText() == "Width (Width)" and box.isEnabled()
    assert dlg.row_record(0)["host_key"] == "Width"
    dlg.set_cell(0, "host_key", "Room.Name")
    assert dlg.row_record(0)["host_key"] == "Room.Name"
    dlg.set_cell(0, "source", "instance")                    # instance source -> disabled
    assert not box.isEnabled()
    assert dlg.row_record(0)["host_key"] == "Room.Name"      # value still stored


def test_gridline_combo_has_no_related_header(qapp):
    w = _editor("Gridline", [normalise_attr({"key": "G", "source": "host"})])
    texts = [t for t, _ in _items(_box(AttributesEditorDialog(w), 0))]
    assert texts == ["", "Stored", "Mark (Mark)", "Geometry", "Length (Length)",
                     "Angle (Angle)"]


def test_no_category_disables_host_key(qapp):
    w = _editor("", [normalise_attr({"key": "A", "source": "host", "host_key": "Width"})])
    dlg = AttributesEditorDialog(w)
    box = _box(dlg, 0)
    assert not box.isEnabled()
    assert box.currentText() == "Width"                      # plain: no key table, no warning
    assert dlg.row_record(0)["host_key"] == "Width"          # kept


def test_unknown_key_kept_warned_and_saved(qapp):
    w = _editor("Door", [normalise_attr({"key": "K", "source": "host",
                                         "host_key": "KFactor"})])
    dlg = AttributesEditorDialog(w)
    box = _box(dlg, 0)
    label = f"{WARN} KFactor {DASH} unknown key"
    assert box.currentText() == label
    fg = box.itemData(box.currentIndex(), Qt.ItemDataRole.ForegroundRole)
    assert fg == th.detect().color("warn")
    assert dlg.try_accept()
    assert w.editor_scene.block_meta["attributes"][0]["host_key"] == "KFactor"


def test_host_category_row_enum_and_unknown(qapp):
    w = _editor("Door", [])
    info = BlockPropertiesInfo(w.editor_scene, "B", editor=w)
    row = info.get_properties()["Host category"]
    assert row["type"] == "enum" and row["value"] == "Door"
    assert row["options"] == ["(none)", "Room", "Pipe", "Sprinkler", "Wall", "Door",
                              "Window", "Opening", "Gridline"]
    info.set_property("Host category", "(none)")
    assert w.editor_scene.block_meta["host_category"] == ""
    w.editor_scene.set_block_meta({**w.editor_scene.block_meta, "host_category": "Foo"})
    row = info.get_properties()["Host category"]
    bad = f"{WARN} Foo {DASH} unknown category"
    assert row["value"] == bad and row["options"][-1] == bad
    assert row["warn_options"] == [bad]
    info.set_property("Host category", bad)                  # re-selecting keeps it
    assert w.editor_scene.block_meta["host_category"] == "Foo"
    # the real panel paints the unknown entry in the warn colour (E10)
    pm = PropertyManager()
    pm.show_properties(info)
    QApplication.processEvents()
    from firepro3d.ui_kit import Selector
    sel = [s for s in pm.findChildren(Selector) if s.findText(bad) >= 0]
    assert sel, "Host category Selector not built"
    fg = sel[0].itemData(sel[0].findText(bad), Qt.ItemDataRole.ForegroundRole)
    assert fg == th.detect().color("warn")


def test_unknown_category_and_key_round_trip_definition():
    d = BlockDefinition.new(name="T", library="", series="", origin=(0.0, 0.0),
                            primitives=[])
    d.host_category = "Foo"
    d.attributes = [normalise_attr({"key": "K", "source": "host", "host_key": "KFactor"})]
    back = BlockDefinition.from_dict(d.to_dict())
    assert back.host_category == "Foo"
    assert back.attributes[0]["host_key"] == "KFactor"
