"""Model Browser shows placed block instances (C3 — blocks are first-class
level-scoped model entities, so they belong in the entity tree)."""
from __future__ import annotations

from firepro3d.model_browser import ModelBrowser, _ROLE_ENTITY
from firepro3d.block_instance import BlockInstance


def _find_row(browser, ent_id):
    def walk(item):
        for i in range(item.childCount()):
            c = item.child(i)
            if c.data(0, _ROLE_ENTITY) == ent_id:
                return c
            found = walk(c)
            if found is not None:
                return found
        return None
    return walk(browser._tree.invisibleRootItem())


def _blocks_root(browser):
    root = browser._tree.invisibleRootItem()
    for i in range(root.childCount()):
        if root.child(i).text(0).startswith("Blocks ("):
            return root.child(i)
    return None


def test_block_instance_appears_in_browser(model_space):
    scene = model_space
    inst = BlockInstance(block_id="B1", resolver=lambda _id: None, level="Level 1")
    scene.addItem(inst)
    scene._block_instances.append(inst)

    b = ModelBrowser()
    b.set_scene(scene)
    b.refresh()

    assert _blocks_root(b) is not None, "no 'Blocks' category in the tree"
    row = _find_row(b, id(inst))
    assert row is not None, "block instance row not found"


def test_block_row_resolves_for_selection_sync(model_space):
    scene = model_space
    inst = BlockInstance(block_id="B1", resolver=lambda _id: None, level="Level 1")
    scene.addItem(inst)
    scene._block_instances.append(inst)

    b = ModelBrowser()
    b.set_scene(scene)
    assert b._find_entity_by_id(id(inst)) is inst


def test_no_blocks_category_when_empty(model_space):
    b = ModelBrowser()
    b.set_scene(model_space)
    b.refresh()
    assert _blocks_root(b) is None
