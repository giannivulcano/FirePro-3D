"""Tests for T9: title block non-selectable + module-level revisions dialog opener.

Concern 4 (part 1): the TitleBlockTemplateItem must not be selectable on the
paper canvas; its per-sheet property panel methods are removed; and the
revisions-dialog opener is relocated to a module-level function for Task 10.
"""
from PyQt6.QtWidgets import QGraphicsScene


def _scene_with_template():
    """Return a PaperScene that has a TitleBlockTemplateItem installed."""
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    from firepro3d.titleblock_template import make_default_template

    model = QGraphicsScene()

    class _PM:
        _views = {}

        def get(self, n):
            return None

    sheet = Sheet.create_default()          # ANSI D — matches make_default_template()
    scene = PaperScene(sheet, ViewResolver(model, _PM(), None, None))
    scene.set_template(make_default_template(), project_info={})
    return scene


def test_titleblock_not_selectable(qapp):
    """TitleBlockTemplateItem must have ItemIsSelectable cleared."""
    from PyQt6.QtWidgets import QGraphicsItem

    scene = _scene_with_template()
    tb = [it for it in scene.items()
          if type(it).__name__ == "TitleBlockTemplateItem"]
    assert tb, "expected a TitleBlockTemplateItem on the scene (template not installed?)"
    assert not (tb[0].flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable), (
        "TitleBlockTemplateItem must not be selectable"
    )


def test_open_revisions_dialog_is_module_level(qapp):
    """The relocated opener must be importable at module level (Task 10 will call it)."""
    from firepro3d import paper_space

    assert hasattr(paper_space, "open_revisions_dialog"), (
        "open_revisions_dialog not found at module level in firepro3d.paper_space"
    )
    assert callable(paper_space.open_revisions_dialog)


# ─────────────────────────────────────────────────────────────────────────────
# T10: Rev/Date/Edit-Revisions in SheetProperties (concern 4 part 2)
# ─────────────────────────────────────────────────────────────────────────────

def test_sheet_properties_exposes_rev_date_and_revisions(qapp):
    """SheetProperties.get_properties() must expose Rev, Date, and an Edit-Revisions button."""
    from firepro3d.paper_space import SheetProperties

    scene = _scene_with_template()
    sheet = scene._sheet
    sp = SheetProperties(sheet, None, scene_getter=lambda: scene)
    props = sp.get_properties()
    assert "Rev" in props, "Rev row missing from SheetProperties"
    assert "Date" in props, "Date row missing from SheetProperties"
    assert any(
        v.get("type") == "button" and "Revision" in str(v.get("value", ""))
        for v in props.values()
    ), "No Edit Revisions button found in SheetProperties"


def test_rev_edit_is_undoable(qapp):
    """Setting Rev via set_property must be undoable via the scene's undo stack."""
    from firepro3d.paper_space import SheetProperties

    scene = _scene_with_template()
    sheet = scene._sheet
    sp = SheetProperties(sheet, None, scene_getter=lambda: scene)
    sp.set_property("Rev", "B")
    assert sheet.title_block_fields.get("Rev") == "B", "Rev not written after set_property"
    scene.undo_stack.undo()
    assert sheet.title_block_fields.get("Rev") != "B", "Rev not reverted after undo"


def test_sheet_properties_exposes_drawn_and_checked_by(qapp):
    """Drawn By / Checked By must be editable per-sheet rows in the panel."""
    from firepro3d.paper_space import SheetProperties

    scene = _scene_with_template()
    sp = SheetProperties(scene._sheet, None, scene_getter=lambda: scene)
    props = sp.get_properties()
    for key in ("Drawn By", "Checked By"):
        assert key in props, f"{key} row missing from SheetProperties"
        assert props[key]["type"] == "string", f"{key} must be an editable string"


def test_drawn_by_edit_is_undoable_and_written(qapp):
    """Drawn By writes to title_block_fields (feeding the @[Drawn By] token) and undoes."""
    from firepro3d.paper_space import SheetProperties

    scene = _scene_with_template()
    sheet = scene._sheet
    sp = SheetProperties(sheet, None, scene_getter=lambda: scene)
    sp.set_property("Drawn By", "GV")
    assert sheet.title_block_fields.get("Drawn By") == "GV"
    scene.undo_stack.undo()
    assert sheet.title_block_fields.get("Drawn By") != "GV"


def test_checked_by_edit_is_undoable(qapp):
    from firepro3d.paper_space import SheetProperties

    scene = _scene_with_template()
    sheet = scene._sheet
    sp = SheetProperties(sheet, None, scene_getter=lambda: scene)
    sp.set_property("Checked By", "AB")
    assert sheet.title_block_fields.get("Checked By") == "AB"
    scene.undo_stack.undo()
    assert sheet.title_block_fields.get("Checked By") != "AB"


def test_sheet_properties_types_are_string_button_or_label(qapp):
    from firepro3d.paper_space import SheetProperties
    scene = _scene_with_template()
    sp = SheetProperties(scene._sheet, None, scene_getter=lambda: scene)
    for key, meta in sp.get_properties().items():
        t = meta.get("type", "string")
        assert t in {"string", "button", "label"}, f"bad type {t!r} for {key!r}"


def test_sheet_properties_unknown_key_ignored(qapp):
    from firepro3d.paper_space import SheetProperties
    scene = _scene_with_template()
    sheet = scene._sheet
    before = dict(sheet.title_block_fields)
    SheetProperties(sheet, None, scene_getter=lambda: scene).set_property("NotAKey", "X")
    assert sheet.title_block_fields == before


def test_edit_revisions_via_callback_updates_and_undoable(qapp, monkeypatch):
    from firepro3d.paper_space import SheetProperties
    scene = _scene_with_template()
    sheet = scene._sheet
    sheet.revisions = []
    new_revs = [{"no": "1", "description": "IFC", "date": "07-21"}]

    class _FakeRevDlg:
        def __init__(self, revisions, parent=None, *, project_info=None): pass
        def exec(self): return 1  # Accepted
        def result_revisions(self): return list(new_revs)
        def selected_date_format(self): return "MM/DD/YYYY"

    monkeypatch.setattr("firepro3d.paper_space.RevisionsDialog", _FakeRevDlg)

    sp = SheetProperties(sheet, None, scene_getter=lambda: scene)
    btn = sp.get_properties().get("")
    assert btn is not None and btn.get("type") == "button"
    btn["callback"]()                       # invoke the Edit Revisions… callback
    assert sheet.revisions == new_revs
    scene.undo_stack.undo()
    assert sheet.revisions == []


def test_edit_revisions_no_change_guard(qapp, monkeypatch):
    from firepro3d.paper_space import SheetProperties
    scene = _scene_with_template()
    sheet = scene._sheet
    existing = [{"no": "1", "description": "IFC", "date": "07-21"}]
    sheet.revisions = list(existing)
    count_before = scene.undo_stack.count()

    class _FakeRevDlgIdentical:
        def __init__(self, revisions, parent=None, *, project_info=None):
            self._r = list(revisions)
        def exec(self): return 1
        def result_revisions(self): return list(self._r)
        def selected_date_format(self): return "MM/DD/YYYY"

    monkeypatch.setattr("firepro3d.paper_space.RevisionsDialog", _FakeRevDlgIdentical)

    sp = SheetProperties(sheet, None, scene_getter=lambda: scene)
    sp.get_properties()[""]["callback"]()
    assert scene.undo_stack.count() == count_before, "no-op revisions must not push undo"


# ─────────────────────────────────────────────────────────────────────────────
# Task C: date picker + project-scoped date format
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_date_to_iso():
    from firepro3d.paper_space import parse_date_to_iso
    assert parse_date_to_iso("2026-09-15") == "2026-09-15"
    assert parse_date_to_iso("09/15/2026") == "2026-09-15"
    assert parse_date_to_iso("") == ""
    assert parse_date_to_iso("not a date") is None       # → caller preserves raw


def test_format_date_display():
    from firepro3d.paper_space import format_date_display
    assert format_date_display("2026-09-15", "MM/DD/YYYY") == "09/15/2026"
    assert format_date_display("2026-09-15", "DD MMM YYYY") == "15 Sep 2026"
    assert format_date_display("", "MM/DD/YYYY") == ""
    assert format_date_display("Q3-2026", "MM/DD/YYYY") == "Q3-2026"   # legacy kept


def test_build_field_values_formats_revision_dates_display_only(qapp):
    from firepro3d.paper_space import build_field_values, Sheet
    sheet = Sheet.create_default()
    sheet.revisions = [{"no": "1", "description": "IFC", "date": "2026-09-15"}]
    vals = build_field_values(sheet, {"date_format": "DD MMM YYYY"})
    assert vals["__revisions__"][0]["date"] == "15 Sep 2026"   # display formatted
    assert sheet.revisions[0]["date"] == "2026-09-15"          # storage untouched


def test_revisions_dialog_date_picker_stores_iso(qapp):
    from firepro3d.paper_space import RevisionsDialog
    dlg = RevisionsDialog([{"no": "1", "description": "IFC", "date": "2026-09-15"}],
                          project_info={"date_format": "MM/DD/YYYY"})
    out = dlg.result_revisions()
    assert out[0]["date"] == "2026-09-15"      # ISO storage regardless of display


def test_revisions_dialog_empty_date_defaults_today(qapp):
    from firepro3d.paper_space import RevisionsDialog
    from PyQt6.QtCore import QDate
    dlg = RevisionsDialog([{"no": "1", "description": "IFC", "date": ""}],
                          project_info={})
    today = QDate.currentDate().toString("yyyy-MM-dd")
    assert dlg.result_revisions()[0]["date"] == today   # empty → today (Task D)


def test_revisions_dialog_preserves_legacy_unparseable_date(qapp):
    from firepro3d.paper_space import RevisionsDialog
    dlg = RevisionsDialog([{"no": "1", "description": "IFC", "date": "Q3-2026"}],
                          project_info={})
    assert dlg.result_revisions()[0]["date"] == "Q3-2026"     # untouched → kept


def test_revisions_dialog_reports_selected_format(qapp):
    from firepro3d.paper_space import RevisionsDialog
    dlg = RevisionsDialog([], project_info={"date_format": "DD MMM YYYY"})
    assert dlg.selected_date_format() == "DD MMM YYYY"


def test_open_revisions_dialog_format_only_change_writes_project_info(qapp, monkeypatch):
    from firepro3d import paper_space
    scene = _scene_with_template()
    sheet = scene._sheet
    sheet.revisions = [{"no": "1", "description": "IFC", "date": "2026-09-15"}]

    class _FakeFmtDlg:
        def __init__(self, revisions, parent=None, *, project_info=None):
            self._r = list(revisions)
        def exec(self): return 1
        def result_revisions(self): return list(self._r)     # revisions unchanged
        def selected_date_format(self): return "DD MMM YYYY"

    monkeypatch.setattr(paper_space, "RevisionsDialog", _FakeFmtDlg)
    paper_space.open_revisions_dialog(scene, sheet, None)
    assert scene._scene_project_info.get("date_format") == "DD MMM YYYY"
