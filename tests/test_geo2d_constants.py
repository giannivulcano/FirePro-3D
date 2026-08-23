from firepro3d import constants

def test_construction_category_wins_over_node_at_equal_elevation():
    assert constants.Z_CAT_CONSTRUCTION > constants.Z_CAT_NODE
    assert constants.Z_CAT_CONSTRUCTION < constants.Z_WATER_SUPPLY
