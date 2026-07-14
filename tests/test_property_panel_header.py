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


class _WideFields:
    """Worst-case rows: a very long enum option list + a long button face."""

    def get_properties(self):
        long_opt = ("Combustible unobstructed - exposed members < 3ft "
                    "(910 mm) O/C — extra long option for width test")
        return {
            "Ceiling Type": {"type": "enum", "value": long_opt,
                             "options": [long_opt,
                                         "Noncombustible unobstructed"]},
            "Design Point": {"type": "button",
                             "value": "1500 sq ft @ 0.10 gpm/ft² "
                                      "(N/A — storage criteria follow-up)",
                             "callback": lambda: None},
        }

    def set_property(self, key, value):
        pass


def test_panel_min_width_capped_by_long_fields(qapp):
    """The form must shrink below the dock width: combos are capped via
    setMinimumContentsLength, buttons via an Ignored size policy.  Before
    the fix the inner scroll widget's minimumSizeHint was ~980px (silently
    clipped by the ScrollBarAlwaysOff scroll area); after, ~370px."""
    pm = PropertyManager()
    pm.show_properties(_WideFields())
    assert pm._form_container.minimumSizeHint().width() < 500


class _WarningField:
    """Entity with a long warning string — must not widen the form."""

    _WARNING = "A" * 300   # 300-char single-line worst case

    def get_properties(self):
        return {"Warnings": {"type": "warning", "value": self._WARNING}}

    def set_property(self, key, value):
        pass


def test_warning_type_renders_without_widening_form(qapp):
    """A 300-char warning must word-wrap inside the dock width — the form
    container's minimumSizeHint must stay < 500px (same threshold as the
    wide-fields test so the dock never forces a wider minimum)."""
    pm = PropertyManager()
    pm.show_properties(_WarningField())
    assert pm._form_container.minimumSizeHint().width() < 500


def test_warning_type_produces_no_editor_widget(qapp):
    """Warning rows are display-only — no QLineEdit or QComboBox is created."""
    from PyQt6.QtWidgets import QLineEdit, QComboBox
    pm = PropertyManager()
    pm.show_properties(_WarningField())
    assert pm.findChildren(QLineEdit) == []
    assert pm.findChildren(QComboBox) == []
