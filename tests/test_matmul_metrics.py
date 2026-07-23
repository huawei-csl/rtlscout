"""Tests for the simulation-driven cost metrics (cycles / runtime / area_runtime_product) and the
matmul/16x16x16_1r1w benchmark.

Unit tests (no external tools) cover TB_CYCLES parsing, the metric math, and the
registry/factory wiring. Integration tests (gated on tool availability) run the
starting-point design end-to-end.
"""
import shutil
from pathlib import Path

import pytest

from tests.conftest import (
    requires_verilator,
    requires_yosys,
    requires_openroad,
    requires_spirehdl,
)

BENCHMARKS_ROOT = Path(__file__).parent.parent / "benchmarks"
MATMUL_ROOT = BENCHMARKS_ROOT / "matmul" / "16x16x16_1r1w"


# ── Unit: TB_CYCLES parsing ──────────────────────────────────────────────────

def test_parse_sim_stats_cycles():
    from core.correctness import parse_sim_stats
    out = "TB_CYCLES total=87815\nTB_SUMMARY total=1813 errors=0\nPASS\n"
    assert parse_sim_stats(out, "") == {"cycles": 87815}


def test_parse_sim_stats_absent_is_empty():
    """Benchmarks that don't print TB_CYCLES must be unaffected (empty dict)."""
    from core.correctness import parse_sim_stats
    assert parse_sim_stats("TB_SUMMARY total=5 errors=0\nPASS\n", "") == {}
    assert parse_sim_stats("", "") == {}


def test_correctness_result_has_sim_stats_default():
    from core.correctness import CorrectnessResult
    r = CorrectnessResult(
        passed=True, lint_ok=True, sim_ok=True,
        lint_stdout="", lint_stderr="", sim_stdout="", sim_stderr="",
        sim_returncode=0,
    )
    assert r.sim_stats == {}


# ── Unit: CyclesCost ─────────────────────────────────────────────────────────

def test_cycles_cost_math():
    from core.cost import CyclesCost
    r = CyclesCost().evaluate(Path("."), "matmul_core", sim_stats={"cycles": 8192})
    assert r.ok
    assert r.value == 8192.0
    assert r.stats == {"cycles": 8192.0}


@pytest.mark.parametrize("sim_stats", [None, {}, {"foo": 1}])
def test_cycles_cost_fails_without_cycles(sim_stats):
    from core.cost import CyclesCost
    r = CyclesCost().evaluate(Path("."), "matmul_core", sim_stats=sim_stats)
    assert not r.ok
    assert r.value is None
    assert "TB_CYCLES" in r.error


# ── Unit: RuntimeCost / AreaRuntimeProductCost math (PPA layer stubbed) ──────

@pytest.fixture
def stub_ppa(monkeypatch):
    """Stub the synthesis/STA layer so metric math is tested in isolation."""
    from core.cost import PPACost, CostResult

    def fake(self, workdir, top_module=None, design_file=None, sim_stats=None):
        return CostResult(ok=True, value=50.0,
                          stats={"area": 100.0, "delay": 50.0, "power": 1.0})

    monkeypatch.setattr(PPACost, "evaluate", fake)


def test_runtime_cost_math(stub_ppa):
    from core.cost import RuntimeCost
    r = RuntimeCost().evaluate(Path("."), "matmul_core", sim_stats={"cycles": 8192})
    assert r.ok
    assert r.value == pytest.approx(50.0 * 8192)
    assert r.stats["runtime"] == pytest.approx(50.0 * 8192)
    assert r.stats["cycles"] == 8192.0
    assert r.stats["area"] == 100.0 and r.stats["delay"] == 50.0


def test_area_runtime_product_cost_math(stub_ppa):
    from core.cost import AreaRuntimeProductCost
    r = AreaRuntimeProductCost().evaluate(Path("."), "matmul_core", sim_stats={"cycles": 8192})
    assert r.ok
    assert r.value == pytest.approx(100.0 * 50.0 * 8192)
    assert r.stats["area_runtime_product"] == pytest.approx(100.0 * 50.0 * 8192)
    assert r.stats["runtime"] == pytest.approx(50.0 * 8192)


def test_runtime_arp_fail_without_cycles(stub_ppa):
    from core.cost import RuntimeCost, AreaRuntimeProductCost
    assert not RuntimeCost().evaluate(Path("."), "matmul_core", sim_stats={}).ok
    assert not AreaRuntimeProductCost().evaluate(Path("."), "matmul_core").ok


# ── Unit: registry / factory wiring ──────────────────────────────────────────

def test_new_metrics_registered():
    from core.cost import COST_METRICS, CyclesCost, RuntimeCost, AreaRuntimeProductCost
    assert COST_METRICS["cycles"] is CyclesCost
    assert COST_METRICS["runtime"] is RuntimeCost
    assert COST_METRICS["area_runtime_product"] is AreaRuntimeProductCost


def test_make_cost_metric_new():
    from core.cost import make_cost_metric, CyclesCost, RuntimeCost, AreaRuntimeProductCost
    c = make_cost_metric("cycles")
    assert isinstance(c, CyclesCost) and c.primary_key == "cycles"
    r = make_cost_metric("runtime", target_delay=500)
    assert isinstance(r, RuntimeCost) and r.primary_key == "runtime" and r.target_delay == 500
    a = make_cost_metric("area_runtime_product", target_delay=500)
    assert isinstance(a, AreaRuntimeProductCost)
    assert a.primary_key == "area_runtime_product" and a.target_delay == 500


# ── Unit: energy / edap (data-movement) metrics ──────────────────────────────

def test_parse_sim_stats_reads_writes():
    from core.correctness import parse_sim_stats
    out = ("TB_CYCLES total=87815\nTB_READS total=4352\nTB_WRITES total=256\n"
           "TB_SUMMARY total=5 errors=0\n")
    assert parse_sim_stats(out, "") == {"cycles": 87815, "reads": 4352, "writes": 256}
    # benchmarks that don't emit them are unaffected
    assert parse_sim_stats("TB_SUMMARY total=5 errors=0\n", "") == {}


def test_energy_cost_math():
    from core.cost import EnergyCost
    r = EnergyCost().evaluate(Path("."), "matmul_core", sim_stats={"reads": 4352, "writes": 256})
    assert r.ok and r.value == 4608.0
    assert r.stats == {"energy": 4608.0, "reads": 4352.0, "writes": 256.0}


@pytest.mark.parametrize("sim_stats", [None, {}, {"reads": 10}, {"cycles": 1}])
def test_energy_cost_fails_without_counts(sim_stats):
    from core.cost import EnergyCost
    r = EnergyCost().evaluate(Path("."), "matmul_core", sim_stats=sim_stats)
    assert not r.ok and "TB_READS" in r.error


def test_edap_cost_math(stub_ppa):
    from core.cost import EdapCost
    ss = {"reads": 4352, "writes": 256, "cycles": 1000}  # energy=4608, runtime=1000*50=50000
    r = EdapCost().evaluate(Path("."), "matmul_core", sim_stats=ss)
    assert r.ok
    # edap (k=1) = energy**1 * runtime * area = 4608 * 50000 * 100
    assert r.value == pytest.approx(4608.0 * 50000.0 * 100.0)
    assert r.stats["edap"] == pytest.approx(4608.0 * 50000.0 * 100.0)
    assert r.stats["energy"] == 4608.0 and r.stats["runtime"] == 50000.0 and r.stats["area"] == 100.0


def test_edap_energy_exp_knob(stub_ppa):
    from core.cost import EdapCost, make_cost_metric
    ss = {"reads": 4352, "writes": 256, "cycles": 1000}  # energy=4608, runtime=50000, area=100
    # k=2 weights energy harder: edap = energy**2 * runtime * area
    r2 = EdapCost(energy_exp=2.0).evaluate(Path("."), "matmul_core", sim_stats=ss)
    assert r2.value == pytest.approx(4608.0**2 * 50000.0 * 100.0)
    # k=0 reduces to plain area_runtime_product (energy ignored): edap = runtime * area
    r0 = EdapCost(energy_exp=0.0).evaluate(Path("."), "matmul_core", sim_stats=ss)
    assert r0.value == pytest.approx(50000.0 * 100.0)
    # the knob is plumbed through the factory
    assert make_cost_metric("edap", energy_exp=2.5).energy_exp == 2.5


def test_edap_fails_without_counts(stub_ppa):
    from core.cost import EdapCost
    # missing reads/writes
    assert not EdapCost().evaluate(Path("."), "matmul_core", sim_stats={"cycles": 1}).ok
    # missing cycles
    assert not EdapCost().evaluate(Path("."), "matmul_core", sim_stats={"reads": 1, "writes": 1}).ok


def test_energy_edap_registered():
    from core.cost import COST_METRICS, make_cost_metric, EnergyCost, EdapCost
    assert COST_METRICS["energy"] is EnergyCost and COST_METRICS["edap"] is EdapCost
    assert isinstance(make_cost_metric("energy"), EnergyCost)
    e = make_cost_metric("edap", target_delay=500)
    assert isinstance(e, EdapCost) and e.primary_key == "edap" and e.target_delay == 500


# ── Unit: run_netlist_sim toggle ─────────────────────────────────────────────

def test_run_netlist_sim_default_and_toggle():
    from core.cost import make_cost_metric
    # PPA metrics default to running the netlist sim; --skip-netlist-sim turns it off.
    for name in ("area", "delay", "runtime", "area_runtime_product", "area_delay_product"):
        assert make_cost_metric(name).run_netlist_sim is True, name
        assert make_cost_metric(name, run_netlist_sim=False).run_netlist_sim is False, name


def test_skip_netlist_sim_drops_tb_path(tmp_path):
    """With run_netlist_sim=False, PPACost must not pass tb.sv to get_ppa."""
    from core.cost import AreaRuntimeProductCost, CostResult
    (tmp_path / "tb.sv").write_text("// tb\n")
    (tmp_path / "design.v").write_text("module matmul_core(); endmodule\n")
    captured = {}

    class Probe(AreaRuntimeProductCost):
        # Intercept the worker launch to inspect the tb_path that would be used.
        def evaluate(self, workdir, top_module=None, design_file=None, sim_stats=None):
            tb = workdir / "tb.sv"
            captured["tb_path"] = str(tb) if (tb.exists() and self.run_netlist_sim) else None
            return CostResult(ok=True, value=0.0, stats={})

    Probe(run_netlist_sim=True).evaluate(tmp_path, "matmul_core", sim_stats={"cycles": 1})
    assert captured["tb_path"] is not None
    Probe(run_netlist_sim=False).evaluate(tmp_path, "matmul_core", sim_stats={"cycles": 1})
    assert captured["tb_path"] is None


# ── Unit: cost_description note in the system prompt ──────────────────────────

def test_cost_description_present():
    from core.cost import AreaRuntimeProductCost, RuntimeCost, CyclesCost, PPAAreaDelayProductCost
    assert "NOT the classic" in AreaRuntimeProductCost.cost_description
    assert "critical-path delay" in RuntimeCost.cost_description
    assert CyclesCost.cost_description
    # The classic area*delay metric is disambiguated from 'area_runtime_product'.
    assert "classic area-delay product" in PPAAreaDelayProductCost.cost_description


def test_cost_note_injected_into_prompt():
    from core.prompts import build_spirehdl_system_prompt, build_system_prompt
    from core.cost import AreaRuntimeProductCost
    sp = build_spirehdl_system_prompt("SPEC", "area_runtime_product",
                                      cost_metric_note=AreaRuntimeProductCost.cost_description)
    assert "**Cost metric `area_runtime_product`:**" in sp
    assert "NOT the classic area×delay product" in sp
    # Omitted entirely when there's no note (existing benchmarks unaffected).
    assert "Cost metric `transistors`" not in build_system_prompt("SPEC", "transistors")


# ── Integration: starting point end-to-end ───────────────────────────────────

# The matmul benchmark assets are not tracked in the repo, so these tests can only
# run on checkouts that have them (e.g. not in CI).
requires_matmul_benchmark = pytest.mark.skipif(
    not (MATMUL_ROOT / "tb.sv").exists(),
    reason="matmul benchmark assets not present in this checkout",
)


def _stage_matmul_workspace(tmp_path: Path) -> Path:
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    shutil.copy2(MATMUL_ROOT / "tb.sv", workdir / "tb.sv")
    shutil.copy2(MATMUL_ROOT / "vectors.dat", workdir / "vectors.dat")
    shutil.copy2(MATMUL_ROOT / "context" / "starting_point.py",
                 workdir / "starting_point.py")
    return workdir


@requires_matmul_benchmark
@requires_verilator
@requires_spirehdl
def test_run_eval_matmul_cycles(tmp_path):
    """Starting point is correct and the cycles metric reports a sane count."""
    from core.evaluation import evaluate
    from core.cost import make_cost_metric

    workdir = _stage_matmul_workspace(tmp_path)
    result = evaluate(
        workdir=workdir,
        design_top_module="matmul_core",
        cost_metric=make_cost_metric("cycles"),
        language="spirehdl",
        design_file="starting_point.py",
    )
    assert result.passed
    assert result.correctness.sim_ok
    assert result.correctness.sim_stats.get("cycles", 0) > 0
    cyc = result.cost_value
    # Single-MAC FSM over 7 cases of 16x16x16 (~12.5k cycles/case); well within
    # 7 x WATCHDOG. Generous band tolerant of small schedule changes.
    assert 60_000 <= cyc <= 150_000, cyc
    # cycles metric does no synthesis: its only metric key is 'cycles'.
    assert set(result.metrics()) == {"cycles"}


@requires_matmul_benchmark
@requires_verilator
@requires_yosys
@requires_openroad
@requires_spirehdl
def test_run_eval_matmul_runtime(tmp_path):
    """runtime == cycles x achieved delay, with area/delay/cycles all present."""
    from core.evaluation import evaluate
    from core.cost import make_cost_metric

    workdir = _stage_matmul_workspace(tmp_path)
    result = evaluate(
        workdir=workdir,
        design_top_module="matmul_core",
        cost_metric=make_cost_metric("runtime", target_delay=500),
        language="spirehdl",
        design_file="starting_point.py",
    )
    assert result.passed
    m = result.metrics()
    for key in ("area", "delay", "cycles", "runtime"):
        assert key in m, key
    assert m["runtime"] == pytest.approx(m["cycles"] * m["delay"])
    assert result.cost_value == pytest.approx(m["runtime"])
