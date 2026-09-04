"""BlocksBrowser tree + activation signal (Block S2 T2)."""
from firepro3d.block_definition import BlockDefinition
from firepro3d.blocks_browser import BlocksBrowser


def _def(name, library, series):
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=[], origin=(0.0, 0.0))


def test_browser_builds_library_series_tree(model_space):
    model_space.register_block_definition(_def("Corner", "Typical Detail", "Wall Joints"))
    model_space.register_block_definition(_def("Chair", "Furniture", "Chairs"))
    b = BlocksBrowser(model_space)
    b.refresh()
    roots = [b._tree.topLevelItem(i).text(0) for i in range(b._tree.topLevelItemCount())]
    assert set(roots) == {"Typical Detail", "Furniture"}


def test_browser_emits_block_id_on_leaf_activation(model_space, qapp):
    d = _def("Corner", "Typical Detail", "Wall Joints")
    model_space.register_block_definition(d)
    b = BlocksBrowser(model_space)
    b.refresh()
    got = []
    b.blockActivated.connect(got.append)
    lib = b._tree.topLevelItem(0)
    series = lib.child(0)
    leaf = series.child(0)
    b._on_item_activated(leaf, 0)
    assert got == [d.id]


def test_register_emits_change_signal(model_space, qapp):
    fired = []
    model_space.blockDefinitionsChanged.connect(lambda: fired.append(1))
    model_space.register_block_definition(_def("X", "L", "S"))
    assert fired == [1]
