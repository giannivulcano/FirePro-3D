from firepro3d.text_item import TextAnnotationData, TextItem

LEADER = {"edge": "R", "t": 0.5, "shoulder_mm": 6.0, "tip_x": 40.0, "tip_y": 30.0,
          "end": "system-endtypes-arrow", "weight": "Light"}


def test_leader_round_trips(qapp):
    d = TextAnnotationData(text="n", leader=dict(LEADER))
    back = TextAnnotationData.from_dict(d.to_dict())
    assert back.leader == LEADER


def test_no_leader_stays_off_the_record(qapp):
    assert "leader" not in TextAnnotationData(text="n").to_dict()


def test_corrupt_leader_loads_as_none(qapp):
    rec = TextAnnotationData(text="n").to_dict()
    rec["leader"] = {"edge": "nope"}
    assert TextAnnotationData.from_dict(rec).leader is None


def test_paper_template_does_not_carry_a_leader():
    from firepro3d.paper_space import _TEMPLATE_FIELDS
    assert "leader" not in _TEMPLATE_FIELDS
