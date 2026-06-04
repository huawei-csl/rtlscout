import json
from pathlib import Path

from tech_eval.ppa_extract.core.ppa_extraction import get_ppa

# assumes https://github.com/pulp-platform/ELAU is cloned at /prog/ELAU
ELAU_ROOT = Path("/prog/ELAU")
ELAU_SRC = ELAU_ROOT / "src"


def _resolve_elau_sources(relative_paths: list[str]) -> list[str]:
    if not ELAU_SRC.is_dir():
        raise FileNotFoundError(f"ELAU source directory not found: {ELAU_SRC}")

    resolved = []
    for rel in relative_paths:
        src = ELAU_SRC / rel
        if not src.is_file():
            raise FileNotFoundError(f"Required source not found: {src}")
        resolved.append(str(src.resolve()))
    return resolved


def _write_muluns16_wrapper(path: Path) -> None:
    path.write_text(
        """module MulUns16 (
    input  logic [15:0] X,
    input  logic [15:0] Y,
    output logic [31:0] P
);
    MulUns #(
        .widthX(16),
        .widthY(16)
    ) dut (
        .X(X),
        .Y(Y),
        .P(P)
    );
endmodule
""",
        encoding="ascii",
    )


def _write_mulppgen16_wrapper(path: Path) -> None:
    path.write_text(
        """module MulPPGenUns16 (
    input  logic [15:0] X,
    input  logic [15:0] Y,
    output logic [511:0] PP
);
    MulPPGenUns #(
        .widthX(16),
        .widthY(16)
    ) dut (
        .X(X),
        .Y(Y),
        .PP(PP)
    );
endmodule
""",
        encoding="ascii",
    )


def run_elau_mul16_ppa(target_delay: int = 1200) -> dict:
    muluns_worker = Path("worker_elau_muluns16")
    mulppgen_worker = Path("worker_elau_mulppgenuns16")
    muluns_worker.mkdir(parents=True, exist_ok=True)
    mulppgen_worker.mkdir(parents=True, exist_ok=True)

    muluns_wrapper = muluns_worker / "MulUns16_wrapper.sv"
    mulppgen_wrapper = mulppgen_worker / "MulPPGenUns16_wrapper.sv"
    _write_muluns16_wrapper(muluns_wrapper)
    _write_mulppgen16_wrapper(mulppgen_wrapper)

    muluns_sources = _resolve_elau_sources(
        [
            "arith_utils.sv",
            "FullAdder.sv",
            "Cpr.sv",
            "AddMopCsv.sv",
            "PrefixAndOr.sv",
            "Add.sv",
            "MulPPGenUns.sv",
            "MulUns.sv",
        ]
    ) + [str(muluns_wrapper.resolve())]
    mulppgen_sources = [
        str((ELAU_SRC / "MulPPGenUns.sv").resolve()),
        str(mulppgen_wrapper.resolve()),
    ]

    results = {
        "MulUns16": get_ppa(
            rtl_path=muluns_sources,
            target_delay=target_delay,
            worker_path=str(muluns_worker),
            top_module_name="MulUns16",
            run_verilator=False,
            use_fa_ha_inference=False,
        ),
        "MulPPGenUns16": get_ppa(
            rtl_path=mulppgen_sources,
            target_delay=target_delay,
            worker_path=str(mulppgen_worker),
            top_module_name="MulPPGenUns16",
            run_verilator=False,
            use_fa_ha_inference=False,
        ),
    }
    return results


def test_elau_mul16_ppa() -> None:
    results = run_elau_mul16_ppa()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    test_elau_mul16_ppa()
