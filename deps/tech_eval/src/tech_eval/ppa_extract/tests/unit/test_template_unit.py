import pytest

from tech_eval.ppa_extract.core import template


def test_make_vcd_flags_returns_empty_for_empty_path() -> None:
    assert template.make_vcd_flags("") == []


def test_make_vcd_flags_builds_expected_define() -> None:
    flags = template.make_vcd_flags("/tmp/test.vcd")
    assert flags[:3] == template.verilator_vcd_flag
    assert flags[-1] == f"-D{template.verilator_vcd_define}=/tmp/test.vcd"


def test_lib_time_to_ps_with_ns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(template, "lib_time_unit", "ns")
    assert template.lib_time_to_ps(1.25) == 1250.0


def test_lib_time_to_ps_raises_for_unknown_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(template, "lib_time_unit", "fs")
    with pytest.raises(ValueError, match="Unknown library time unit"):
        template.lib_time_to_ps(10.0)


def test_get_fa_ha_inference_cmds_disabled() -> None:
    cmd = template.get_fa_ha_inference_cmds(False)
    assert cmd == "# FA/HA inference disabled"


def test_get_fa_ha_inference_cmds_raises_without_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(template, "ADDER_MAP_FILE", None)
    with pytest.raises(ValueError, match="ADDER_MAP_FILE"):
        template.get_fa_ha_inference_cmds(True)

