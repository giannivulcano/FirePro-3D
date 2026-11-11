"""Real solved scenes for the SB4e node-badge guards (VC3: real Model_Space,
real solver through Model_Space.run_hydraulics)."""
from tests._sb4d_helpers import dispose, plan_scene   # noqa: F401  (re-export dispose)


def tree_scene():
    """``(ms, sec, tabs, nodes)``: supply at the origin feeding a tee.

    n0 (0, 0) supply node -> n1 (3000, 0) tee -> n2 (6000, 0) sprinkler
                                           \\-> n3 (3000, 3000) -> n4 (6000, 3000) top
                                                                   n5 (6000, 3000) drop, 1000 mm lower, sprinkler
    n4 / n5 share a plan XY (the R8 stack). add_node dedups within SNAP_RADIUS,
    so n5 is created at (6000, 3600) and moved onto n4's XY."""
    from firepro3d.water_supply import WaterSupply
    ms, sec, _det, tabs = plan_scene()
    ws = WaterSupply(0.0, 0.0)
    ms.addItem(ws)
    ms.water_supply_node = ws
    ms.sprinkler_system.supply_node = ws
    n0 = ms.add_node(0.0, 0.0)
    n1 = ms.add_node(3000.0, 0.0)
    n2 = ms.add_node(6000.0, 0.0)
    n3 = ms.add_node(3000.0, 3000.0)
    n4 = ms.add_node(6000.0, 3000.0)
    assert 600.0 > ms.SNAP_RADIUS          # add_node dedups inside SNAP_RADIUS (10 mm)
    n5 = ms.add_node(6000.0, 3600.0)       # outside SNAP_RADIUS: a new node
    n5.setPos(n4.pos())                    # same plan XY as n4 (the R8 stack)
    for a, b in ((n0, n1), (n1, n2), (n1, n3), (n3, n4), (n4, n5)):
        ms.add_pipe(a, b)
    # after the pipes: a template-less add_pipe resets both end nodes' ceiling
    n5.ceiling_offset = n4.ceiling_offset - 1000.0
    n5._recompute_z_pos()
    ms.add_sprinkler(n2)
    ms.add_sprinkler(n5)
    return ms, sec, tabs, (n0, n1, n2, n3, n4, n5)


def solve(ms):
    """Run the real solve the Calculate command runs; return the result."""
    return ms.run_hydraulics(
        [n.sprinkler for n in ms.sprinkler_system.nodes if n.has_sprinkler()])
