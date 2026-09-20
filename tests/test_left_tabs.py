"""LeftTabs — drop-in vertical (West) tab widget mirroring TopTabs' API."""
from PyQt6.QtWidgets import QLabel, QTabBar
from firepro3d.ui_kit import LeftTabs


def test_add_switch_and_signal(qapp):
    lt = LeftTabs()
    p0, p1 = QLabel("zero"), QLabel("one")
    lt.addTab(p0, "Project")
    lt.addTab(p1, "Model")
    seen = []
    lt.tabSelected.connect(seen.append)

    assert lt.count() == 2
    assert lt.tabText(0) == "Project"
    lt.setCurrentWidget(p1)
    assert lt.currentWidget() is p1
    assert lt.current() == "Model"          # key defaults to the label
    assert seen[-1] == "Model"

    lt.set_current("Project")
    assert lt.currentWidget() is p0


def test_bar_is_west_oriented(qapp):
    lt = LeftTabs()
    lt.addTab(QLabel("x"), "X")
    assert lt.tabBar().shape() in (
        QTabBar.Shape.RoundedWest, QTabBar.Shape.TriangularWest)
