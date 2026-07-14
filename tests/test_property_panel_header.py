"""tests/test_property_panel_header.py — section-header property type."""
from PyQt6.QtWidgets import QLabel
from firepro3d.property_manager import PropertyManager


class _Sectioned:
    def get_properties(self):
        return {
            "Room Info": {"type": "header"},
            "Name": {"type": "string", "value": "R1"},
        }

    def set_property(self, key, value):
        pass


def test_header_renders_section_label(qapp):
    pm = PropertyManager()
    pm.show_properties(_Sectioned())
    labels = [w.text() for w in pm.findChildren(QLabel)]
    assert "── Room Info ──" in labels


def test_header_has_no_editor_row(qapp):
    pm = PropertyManager()
    pm.show_properties(_Sectioned())
    # the header key must not fall through to the string-editor branch
    from PyQt6.QtWidgets import QLineEdit
    edits = pm.findChildren(QLineEdit)
    assert len(edits) == 1  # only "Name"
