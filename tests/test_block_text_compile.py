"""Guard tests: BlockDefinition compiles a TextItem primitive into a FILLED
outlined-glyph render op (containment C5.4)."""
from firepro3d.block_definition import BlockDefinition
from firepro3d.text_item import TextItem, TextAnnotationData


def _text_prim():
    """A minimal 'text' primitive dict (TextItem.to_dict / TextAnnotationData)."""
    return TextItem(TextAnnotationData(text="A", x=0.0, y=0.0, height_mm=10.0)).to_dict()


def test_definition_compiles_text_into_filled_render_op(qapp):
    definition = BlockDefinition.new(
        name="Label", library="L", series="S",
        primitives=[_text_prim()], origin=(0.0, 0.0),
    )
    ops = definition.render_ops()
    text_ops = [op for op in ops if op.kind == "text"]
    assert text_ops, "expected at least one filled (text) render op"
    assert not text_ops[0].path.isEmpty()


def test_text_primitive_type_is_registered(qapp):
    """_PRIMITIVE_FACTORY must map 'text' -> TextItem so _compile can rebuild it."""
    from firepro3d.block_definition import _PRIMITIVE_FACTORY
    assert _PRIMITIVE_FACTORY.get("text") is TextItem
