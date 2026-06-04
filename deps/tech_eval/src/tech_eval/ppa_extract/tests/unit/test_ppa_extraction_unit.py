from pathlib import Path

import pytest

from tech_eval.ppa_extract.core import ppa_extraction


def test_parse_verilator_output_success() -> None:
    output = "\n".join(
        [
            "Testbench completed successfully",
            "Finished: 10 passed, 0 failed",
        ]
    )
    ppa_extraction.parse_verilator_output(output)


def test_parse_verilator_output_rejects_missing_completion_banner() -> None:
    with pytest.raises(RuntimeError, match="did not complete successfully"):
        ppa_extraction.parse_verilator_output("Finished: 1 passed, 0 failed")


def test_parse_verilator_output_rejects_failed_vectors() -> None:
    output = "\n".join(
        [
            "Testbench completed successfully",
            "Finished: 9 passed, 1 failed",
        ]
    )
    with pytest.raises(RuntimeError, match="1 failed tests"):
        ppa_extraction.parse_verilator_output(output)


def test_normalize_flags_handles_none_string_and_sequence() -> None:
    assert ppa_extraction._normalize_flags(None) == []
    assert ppa_extraction._normalize_flags("-Wall -O3") == ["-Wall", "-O3"]
    assert ppa_extraction._normalize_flags(["-Werror", 123]) == ["-Werror", "123"]


def test_normalize_verilog_files_returns_absolute_paths(tmp_path: Path) -> None:
    rtl = tmp_path / "simple.v"
    rtl.write_text("module simple; endmodule\n", encoding="ascii")
    paths = ppa_extraction._normalize_verilog_files(rtl)
    assert paths == [str(rtl.resolve())]


def test_normalize_verilog_files_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="No RTL files provided"):
        ppa_extraction._normalize_verilog_files([])
    with pytest.raises(TypeError, match="rtl_path must be a path string"):
        ppa_extraction._normalize_verilog_files(42)  # type: ignore[arg-type]


def test_run_verilator_generic_rejects_missing_source(tmp_path: Path) -> None:
    missing = tmp_path / "missing.v"
    with pytest.raises(FileNotFoundError, match="Verilator sources not found"):
        ppa_extraction._run_verilator_generic(
            sources=[str(missing)],
            tb_top_module="tb",
            build_dir=str(tmp_path / "out"),
            log_path=str(tmp_path / "verilator.log"),
        )


def test_get_ppa_requires_run_verilator_for_vcd_power(tmp_path: Path) -> None:
    rtl = tmp_path / "dut.v"
    rtl.write_text("module DUT; endmodule\n", encoding="ascii")
    with pytest.raises(ValueError, match="run_verilator=True"):
        ppa_extraction.get_ppa(
            rtl_path=str(rtl),
            target_delay=100,
            worker_path=str(tmp_path / "worker"),
            top_module_name="DUT",
            run_verilator=False,
            tb_name="tb",
            use_vcd_for_power=True,
            save_vcd=True,
        )


def test_get_ppa_requires_tb_name_when_running_verilator(tmp_path: Path) -> None:
    rtl = tmp_path / "dut.v"
    rtl.write_text("module DUT; endmodule\n", encoding="ascii")
    with pytest.raises(ValueError, match="tb_name is required"):
        ppa_extraction.get_ppa(
            rtl_path=str(rtl),
            target_delay=100,
            worker_path=str(tmp_path / "worker"),
            top_module_name="DUT",
            run_verilator=True,
        )


def test_get_ppa_requires_save_vcd_for_vcd_power(tmp_path: Path) -> None:
    rtl = tmp_path / "dut.v"
    rtl.write_text("module DUT; endmodule\n", encoding="ascii")
    with pytest.raises(ValueError, match="write_vcd must be True"):
        ppa_extraction.get_ppa(
            rtl_path=str(rtl),
            target_delay=100,
            worker_path=str(tmp_path / "worker"),
            top_module_name="DUT",
            run_verilator=True,
            tb_name="tb",
            use_vcd_for_power=True,
            save_vcd=False,
        )


def test_remove_worker_path_deletes_directory(tmp_path: Path) -> None:
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / "artifact.txt").write_text("x", encoding="ascii")
    ppa_extraction.remove_worker_path(str(worker))
    assert not worker.exists()

