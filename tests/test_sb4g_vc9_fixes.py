"""SB4g VC9 seam fixes: I1 (no Symbol-row library walk on serialize / undo /
signature / clipboard / save paths) and I2 (placement template keeps its
symbol across restart and catalog pick)."""
import pytest

import main as _main_module
from firepro3d.view_3d import View3D          # heavy import required before MainWindow
_main_module.View3D = View3D
from main import MainWindow                   # noqa: E402
from tests._mainwindow_helpers import dispose_main_window  # noqa: E402
from tests._sb4g_helpers import SPR_IDS, head, scene, water_supply  # noqa: E402

N_HEADS = 12


@pytest.fixture
def choice_calls(monkeypatch):
    from firepro3d import annotation_choices as ac
    calls = []
    real = ac.symbol_choices

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(ac, "symbol_choices", counting)
    return calls


def test_serialize_paths_never_walk_the_symbol_library(qapp, real_system_library, choice_calls, tmp_path):
    from firepro3d.network_codec import SYMBOL_KEY
    ms = scene()
    sprs = [head(ms, i * 1000.0, 0.0)[1] for i in range(N_HEADS)]
    sprs[0].set_symbol_block(SPR_IDS[1])
    water_supply(ms).set_symbol_block("system-symbols-watersupply")
    choice_calls.clear()                      # count only the paths below

    nodes, _pipes, _ws, _da = ms._network_records()
    ms._network_signature()
    ms.push_undo_state()
    data = ms._clipboard_item_dicts(list(ms.sprinkler_system.nodes))
    ms.save_to_file(str(tmp_path / "p.fpd"), backup=False)
    assert choice_calls == []                 # 0 library walks

    spr_recs = [n["sprinkler"] for n in nodes if n.get("sprinkler")]
    assert len(spr_recs) == N_HEADS
    withsym = [r for r in spr_recs if r.get(SYMBOL_KEY)]
    assert [r[SYMBOL_KEY] for r in withsym] == [SPR_IDS[1]]
    assert all("Symbol" not in r for r in spr_recs)
    assert any((d.get("sprinkler") or {}).get(SYMBOL_KEY) == SPR_IDS[1] for d in data)
    assert SPR_IDS[1] in (tmp_path / "p.fpd").read_text(encoding="utf-8")


def test_panel_default_still_builds_the_symbol_row(qapp, real_system_library):
    from firepro3d.system_blocks import SYMBOL_ROW_KEY
    ms = scene()
    spr = head(ms)[1]
    assert SYMBOL_ROW_KEY in spr.get_properties()
    assert SYMBOL_ROW_KEY not in spr.get_properties(with_symbol_row=False)
    ws = water_supply(ms)
    assert SYMBOL_ROW_KEY in ws.get_properties()
    assert SYMBOL_ROW_KEY not in ws.get_properties(with_symbol_row=False)


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    monkeypatch.setattr(MainWindow, "_maybe_offer_template_push", lambda self: None)
    w = MainWindow()
    yield w
    dispose_main_window(w)


def test_template_symbol_survives_save_and_restore(main_window):
    w = main_window
    w.current_sprinkler_template.set_symbol_block(SPR_IDS[1])
    w.save_settings()
    w.current_sprinkler_template.set_symbol_block(None)
    w.restore_settings()
    assert w.current_sprinkler_template.symbol_block == SPR_IDS[1]


def test_default_template_symbol_is_not_written(main_window):
    w = main_window
    w.current_sprinkler_template.set_symbol_block(None)
    w.save_settings()
    assert "symbol_block" not in w.settings.value("template/sprinkler", {})


def test_catalog_pick_keeps_the_template_symbol(main_window):
    from firepro3d.sprinkler_db import _DEFAULTS
    w = main_window
    w.current_sprinkler_template.set_symbol_block(SPR_IDS[2])
    w._apply_sprinkler_template_from_record(_DEFAULTS[0])
    assert w.current_sprinkler_template.symbol_block == SPR_IDS[2]
