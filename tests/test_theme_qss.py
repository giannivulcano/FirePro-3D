"""QSS output tests for firepro3d/theme.py.

Checks that the built stylesheet string contains every widget rule that
must be explicit to work on the dark theme (where Qt replaces native
painting with QSS, so any state without a rule renders as the base state
and becomes invisible).
"""
from PyQt6.QtWidgets import QApplication

import firepro3d.theme as th

_app = QApplication.instance() or QApplication([])


class TestRadioButtonIndicatorQSS:
    """build_app_qss must style QRadioButton::indicator for all key states."""

    def _qss(self) -> str:
        return th.build_app_qss(th.DARK)

    def test_radio_indicator_base_rule_present(self):
        """QSS must include a QRadioButton::indicator base rule."""
        qss = self._qss()
        assert "QRadioButton::indicator" in qss, (
            "build_app_qss() does not contain 'QRadioButton::indicator' — "
            "radio buttons will be invisible on the dark theme"
        )

    def test_radio_indicator_checked_rule_present(self):
        """QSS must include QRadioButton::indicator:checked."""
        qss = self._qss()
        assert "QRadioButton::indicator:checked" in qss, (
            "build_app_qss() missing 'QRadioButton::indicator:checked' — "
            "checked state will render identically to unchecked on dark theme"
        )

    def test_radio_indicator_hover_rule_present(self):
        """QSS must include QRadioButton::indicator:hover."""
        qss = self._qss()
        assert "QRadioButton::indicator:hover" in qss, (
            "build_app_qss() missing 'QRadioButton::indicator:hover'"
        )

    def test_radio_indicator_disabled_rule_present(self):
        """QSS must include QRadioButton::indicator:disabled."""
        qss = self._qss()
        assert "QRadioButton::indicator:disabled" in qss, (
            "build_app_qss() missing 'QRadioButton::indicator:disabled'"
        )

    def test_radio_indicator_is_circular(self):
        """The indicator rule must set border-radius: 7px (circular for 14 px size)."""
        qss = self._qss()
        # Verify the circle rule appears somewhere after the base selector
        base_pos = qss.find("QRadioButton::indicator {")
        if base_pos == -1:
            # whitespace variant
            base_pos = qss.find("QRadioButton::indicator{")
        assert base_pos != -1, "QRadioButton::indicator base block not found"
        block_end = qss.find("}", base_pos)
        block = qss[base_pos:block_end]
        assert "border-radius" in block, (
            "QRadioButton::indicator block must set border-radius to make it circular"
        )

    def test_radio_rules_apply_to_both_themes(self):
        """Radio indicator rules must appear for both LIGHT and DARK builds."""
        for theme in (th.LIGHT, th.DARK):
            qss = th.build_app_qss(theme)
            assert "QRadioButton::indicator:checked" in qss, (
                f"QRadioButton::indicator:checked missing from {theme.name} QSS"
            )
