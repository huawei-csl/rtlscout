#!/usr/bin/env python3
"""Generate a benchmark from spire-hdl's arithmetic_generator.

Uses the Python API to generate test vectors, a data-driven testbench (with
TB_SUMMARY), and optional context files (spire-hdl source files that produced
the reference design, placed in context/ for the agent).

Usage examples:

  # 8-bit unsigned multiplier benchmark
  python add_benchmark.py multiplier --n-bits 8 --encoding unsigned

  # 16-bit signed adder benchmark
  python add_benchmark.py adder --n-bits 16 --encoding twos_complement

  # MAC benchmark
  python add_benchmark.py mac --n-bits 8 --c-bits 16 --encoding twos_complement

  # Integer matmul-accumulate benchmark
  python add_benchmark.py matmulacc --dim-m 4 --dim-n 4 --dim-k 4 --a-width 4

  # Floating-point multiplier benchmark (bfloat16)
  python add_benchmark.py fpmul --exponent-width 8 --fraction-width 7

  # Floating-point matmul-accumulate benchmark
  python add_benchmark.py fpmatmulacc --dim-m 2 --dim-n 2 --dim-k 2 \
      --exponent-width 5 --fraction-width 10

  # Fused integer matmul-accumulate
  python add_benchmark.py matmulacc-fused --dim-m 4 --dim-n 4 --dim-k 4 --a-width 8
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# spire-hdl imports
# ---------------------------------------------------------------------------
from spirehdl.arithmetic.arithmetic_generator import (
    AdderGeneratorConfig,
    FpAdderGeneratorConfig,
    FpMatmulAccumulateGeneratorConfig,
    FpMultiplierGeneratorConfig,
    GenerationActions,
    GenerationResult,
    MacGeneratorConfig,
    MatmulAccumulateGeneratorConfig,
    MatmulAccumulateFusedGeneratorConfig,
    MultiplierGeneratorConfig,
    generate_adder,
    generate_fp_adder,
    generate_fp_matmul_accumulate,
    generate_fp_multiplier,
    generate_mac,
    generate_matmul_accumulate,
    generate_matmul_accumulate_fused,
    generate_multiplier,
)
from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
    FSAOption,
    MultiplierOption,
    PPAOption,
    PPGOption,
)
from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import Encoding
from spirehdl.spirehdl_verilog_testbench import write_vector_data_file

BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"

SPIREHDL_SRC = Path("/workspaces/rtl_scout/deps/spire-hdl/src/spirehdl")


# ---------------------------------------------------------------------------
# Context file registry: maps generator type -> list of source files to copy
# ---------------------------------------------------------------------------
# Each entry is (source_path_relative_to_spirehdl_src, dest_filename).
# Only the highest-level files are included as starting-point references.

_COMMON_CONTEXT = [
    ("arithmetic/int_arithmetic_config.py", "int_arithmetic_config.py"),
]

CONTEXT_FILES: Dict[str, List[Tuple[str, str]]] = {
    "multiplier": _COMMON_CONTEXT + [
        ("arithmetic/int_multipliers/multipliers/mutipliers_ext.py", "mutipliers_ext.py"),
    ],
    "adder": _COMMON_CONTEXT + [
        ("arithmetic/prefix_adders/adders.py", "adders.py"),
        ("arithmetic/prefix_adders/prefix_adder_clean.py", "prefix_adder_clean.py"),
    ],
    "mac": _COMMON_CONTEXT + [
        ("arithmetic/int_mac_fused.py", "int_mac_fused.py"),
    ],
    "matmulacc": _COMMON_CONTEXT + [
        ("cores/matmul_accumulate/matmul_accumulate_core.py", "matmul_accumulate_core.py"),
    ],
    "matmulacc-fused": _COMMON_CONTEXT + [
        ("cores/matmul_accumulate/matmul_accumulate_core_fused.py", "matmul_accumulate_core_fused.py"),
    ],
    "fpmul": [
        ("arithmetic/floating_point/spire_hdl_float_mult_sn.py", "spire_hdl_float_mult_sn.py"),
    ],
    "fpadd": [
        ("arithmetic/floating_point/spire_hdl_float_add.py", "spire_hdl_float_add.py"),
    ],
    "fpmatmulacc": [
        ("arithmetic/floating_point/spire_hdl_float_mult_sn.py", "spire_hdl_float_mult_sn.py"),
        ("cores/matmul_accumulate/matmul_accumulate_core_float.py", "matmul_accumulate_core_float.py"),
    ],
}


# ---------------------------------------------------------------------------
# Module port helpers (Module stores ports in _ports with .kind attribute)
# ---------------------------------------------------------------------------

def _get_inputs(module):
    """Return input port signals from a spirehdl Module."""
    return [s for s in module._ports if s.kind == "input"]


def _get_outputs(module):
    """Return output port signals from a spirehdl Module."""
    return [s for s in module._ports if s.kind == "output"]


def _signal_width(module, name: str) -> int:
    """Get the bit-width of a port signal by name."""
    for s in _get_inputs(module) + _get_outputs(module):
        if s.name == name:
            return s.typ.width
    raise ValueError(f"Signal '{name}' not found in module")


def _write_data_driven_tb_sv(
    module_name: str,
    input_names: List[str],
    input_widths: List[int],
    output_names: List[str],
    output_widths: List[int],
    dat_filename: str,
    num_vectors: int,
    tb_path: Path,
) -> None:
    """Write a Verilator-compatible data-driven testbench that reads from a .dat file.

    Output format matches core expectations:
      - module name is 'tb'
      - outputs TB_SUMMARY total=N errors=M
      - outputs PASS on success
    """
    lines = []
    lines.append("module tb;")
    lines.append("  int total_checks;")
    lines.append("  int total_errors;")
    lines.append("")

    # Declare input regs and output wires
    for name, w in zip(input_names, input_widths):
        if w == 1:
            lines.append(f"  logic {name};")
        else:
            lines.append(f"  logic [{w-1}:0] {name};")

    for name, w in zip(output_names, output_widths):
        if w == 1:
            lines.append(f"  logic {name};")
        else:
            lines.append(f"  logic [{w-1}:0] {name};")

    # Expected output regs
    for name, w in zip(output_names, output_widths):
        if w == 1:
            lines.append(f"  logic expected_{name};")
        else:
            lines.append(f"  logic [{w-1}:0] expected_{name};")

    lines.append("")

    # DUT instantiation
    port_list = ", ".join(
        [f".{n}({n})" for n in input_names + output_names]
    )
    lines.append(f"  {module_name} dut ({port_list});")
    lines.append("")

    # File reading variables
    lines.append("  integer fd, rc, line_num;")
    lines.append("  string line_buf;")
    lines.append("")

    # initial block
    lines.append("  initial begin")
    lines.append("    total_checks = 0;")
    lines.append("    total_errors = 0;")
    lines.append(f'    fd = $fopen("{dat_filename}", "r");')
    lines.append("    if (fd == 0) begin")
    lines.append(f'      $display("ERROR: cannot open {dat_filename}");')
    lines.append("      $fatal(1);")
    lines.append("    end")
    lines.append("    line_num = 0;")
    lines.append("    while (!$feof(fd)) begin")
    lines.append("      line_num = line_num + 1;")
    lines.append("      void'($fgets(line_buf, fd));")
    lines.append("      if (line_buf.len() == 0) continue;")
    lines.append('      if (line_buf.substr(0, 0) == "#") continue;')

    # Build sscanf format and lvalue list
    all_names = input_names + [f"expected_{n}" for n in output_names]
    fmt = " ".join(["%d"] * len(all_names))
    lvals = ", ".join(all_names)
    lines.append(f'      rc = $sscanf(line_buf, "{fmt}", {lvals});')
    lines.append(f"      if (rc != {len(all_names)}) continue;")
    lines.append("      #1;")
    lines.append("      total_checks = total_checks + 1;")

    # Check each output
    for name in output_names:
        lines.append(f"      if ({name} !== expected_{name}) begin")
        lines.append(f'        $display("TB_ERROR line=%0d expected_{name}=%0d actual_{name}=%0d", line_num, expected_{name}, {name});')
        lines.append("        total_errors = total_errors + 1;")
        lines.append("      end")

    lines.append("    end")
    lines.append("    $fclose(fd);")
    lines.append('    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);')
    lines.append("    if (total_errors != 0) $fatal(1, \"FAIL\");")
    lines.append('    $display("PASS");')
    lines.append("    $finish;")
    lines.append("  end")
    lines.append("endmodule")

    tb_path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Description generators
# ---------------------------------------------------------------------------

def _enc_label(enc: Encoding) -> str:
    if enc == Encoding.unsigned:
        return "unsigned"
    elif enc == Encoding.twos_complement:
        return "signed (two's complement)"
    elif enc == Encoding.sign_magnitude:
        return "sign-magnitude"
    return enc.name


_FP_FORMAT_ALIASES = {
    (5, 10): "f16",
    (8, 7): "bf16",
    (8, 23): "f32",
    (11, 52): "f64",
}


def _fp_bench_name(prefix: str, ew: int, fw: int) -> str:
    alias = _FP_FORMAT_ALIASES.get((ew, fw))
    return f"{prefix}_{alias}" if alias else f"{prefix}_e{ew}f{fw}"


def _multiplier_description(cfg: MultiplierGeneratorConfig, module_name: str, y_width: int) -> str:
    return (
        f"Design a module named {module_name} that takes two "
        f"{_enc_label(cfg.input_encoding)} {cfg.n_bits}-bit inputs a and b "
        f"and produces a {y_width}-bit output y. "
        f"The output should be the {_enc_label(cfg.input_encoding)} product of a and b."
    )


def _adder_description(cfg: AdderGeneratorConfig, module_name: str, y_width: int) -> str:
    return (
        f"Design a module named {module_name} that takes two "
        f"{_enc_label(cfg.input_encoding)} {cfg.n_bits}-bit inputs a and b "
        f"and produces a {y_width}-bit output y. "
        f"The output should be the {_enc_label(cfg.input_encoding)} sum of a and b."
    )


def _mac_description(cfg: MacGeneratorConfig, module_name: str,
                     a_w: int, b_w: int, c_w: int, y_width: int) -> str:
    return (
        f"Design a module named {module_name} that computes "
        f"y = a * b + c. "
        f"Inputs: {_enc_label(cfg.input_encoding)} {a_w}-bit a, {b_w}-bit b, "
        f"and {c_w}-bit c. "
        f"Output: {y_width}-bit y."
    )


def _matmul_description(cfg, module_name: str, result: GenerationResult) -> str:
    m = result.module
    inputs_desc = ", ".join(
        f"{s.name} ({s.typ.width}-bit)" for s in _get_inputs(m)
    )
    outputs_desc = ", ".join(
        f"{s.name} ({s.typ.width}-bit)" for s in _get_outputs(m)
    )
    return (
        f"Design a module named {module_name} that computes "
        f"Y = A @ B + C (matrix multiply-accumulate). "
        f"Dimensions: M={cfg.dim_m}, N={cfg.dim_n}, K={cfg.dim_k}, "
        f"element width={cfg.a_width}-bit ({_enc_label(cfg.input_encoding)}). "
        f"Inputs: {inputs_desc}. "
        f"Outputs: {outputs_desc}. "
        f"Matrix elements are packed into flat bit vectors in row-major order."
    )


def _matmul_fused_description(cfg, module_name: str, result: GenerationResult) -> str:
    m = result.module
    inputs_desc = ", ".join(
        f"{s.name} ({s.typ.width}-bit)" for s in _get_inputs(m)
    )
    outputs_desc = ", ".join(
        f"{s.name} ({s.typ.width}-bit)" for s in _get_outputs(m)
    )
    return (
        f"Design a module named {module_name} that computes "
        f"Y = A @ B + C (fused matrix multiply-accumulate). "
        f"Dimensions: M={cfg.dim_m}, N={cfg.dim_n}, K={cfg.dim_k}, "
        f"element width={cfg.a_width}-bit ({_enc_label(cfg.input_encoding)}). "
        f"Inputs: {inputs_desc}. "
        f"Outputs: {outputs_desc}. "
        f"Matrix elements are packed into flat bit vectors in row-major order."
    )


def _fpmul_description(cfg: FpMultiplierGeneratorConfig, module_name: str) -> str:
    total_w = 1 + cfg.exponent_width + cfg.fraction_width
    return (
        f"Design a module named {module_name} that multiplies "
        f"two floating-point numbers. "
        f"Format: {total_w}-bit (1 sign + {cfg.exponent_width} exponent + "
        f"{cfg.fraction_width} fraction). "
        f"Inputs: a and b ({total_w}-bit each). "
        f"Output: y ({total_w}-bit). "
        + ("Subnormal numbers must be supported. " if cfg.subnormals else
           "Flush-to-zero mode (no subnormal support). ")
    )


def _fpadd_description(cfg: FpAdderGeneratorConfig, module_name: str) -> str:
    total_w = 1 + cfg.exponent_width + cfg.fraction_width
    return (
        f"Design a module named {module_name} that adds "
        f"two floating-point numbers. "
        f"Format: {total_w}-bit (1 sign + {cfg.exponent_width} exponent + "
        f"{cfg.fraction_width} fraction). "
        f"Inputs: a and b ({total_w}-bit each). "
        f"Output: y ({total_w}-bit). "
        + ("Subnormal numbers must be supported. " if cfg.subnormals else
           "Flush-to-zero mode (no subnormal support). ")
    )


def _fpmatmulacc_description(cfg: FpMatmulAccumulateGeneratorConfig,
                             module_name: str, result: GenerationResult) -> str:
    m = result.module
    total_w = 1 + cfg.exponent_width + cfg.fraction_width
    inputs_desc = ", ".join(
        f"{s.name} ({s.typ.width}-bit)" for s in _get_inputs(m)
    )
    outputs_desc = ", ".join(
        f"{s.name} ({s.typ.width}-bit)" for s in _get_outputs(m)
    )
    return (
        f"Design a module named {module_name} that computes "
        f"Y = A @ B + C (floating-point matrix multiply-accumulate). "
        f"Dimensions: M={cfg.dim_m}, N={cfg.dim_n}, K={cfg.dim_k}. "
        f"Element format: {total_w}-bit float (1 sign + {cfg.exponent_width} exponent + "
        f"{cfg.fraction_width} fraction). "
        f"Inputs: {inputs_desc}. "
        f"Outputs: {outputs_desc}. "
        f"Matrix elements are packed into flat bit vectors in row-major order."
    )


# ---------------------------------------------------------------------------
# Core: generate benchmark from a GenerationResult
# ---------------------------------------------------------------------------

def _cfg_to_dict(cfg: object) -> dict:
    """Serialize a generator config dataclass to a JSON-friendly dict."""
    from dataclasses import fields, asdict
    try:
        d = asdict(cfg)
    except TypeError:
        return {}
    # Convert enums to their name strings
    for k, v in d.items():
        if hasattr(v, "name") and hasattr(v, "value"):
            d[k] = v.name
    return d


def _create_benchmark(
    bench_name: str,
    gen_type: str,
    module_name: str,
    description: str,
    result: GenerationResult,
    num_vectors: int,
    benchmarks_dir: Path,
    force: bool = False,
    cfg: object = None,
) -> Path:
    bench_dir = benchmarks_dir / bench_name
    if bench_dir.exists() and not force:
        print(f"Benchmark '{bench_name}' already exists. Use --force to overwrite.")
        sys.exit(1)
    if bench_dir.exists():
        shutil.rmtree(bench_dir)
    bench_dir.mkdir(parents=True)

    m = result.module
    input_names = [s.name for s in _get_inputs(m)]
    input_widths = [s.typ.width for s in _get_inputs(m)]
    output_names = [s.name for s in _get_outputs(m)]
    output_widths = [s.typ.width for s in _get_outputs(m)]

    # Write .dat file
    dat_path = bench_dir / "vectors.dat"
    write_vector_data_file(result.vectors, dat_path)

    # Write tb.sv
    tb_path = bench_dir / "tb.sv"
    _write_data_driven_tb_sv(
        module_name=module_name,
        input_names=input_names,
        input_widths=input_widths,
        output_names=output_names,
        output_widths=output_widths,
        dat_filename="vectors.dat",
        num_vectors=num_vectors,
        tb_path=tb_path,
    )

    # Write description.txt (append starting-point note if context files exist)
    context_entries = CONTEXT_FILES.get(gen_type, [])
    if context_entries:
        description += (
            "\n\nA working starting point is provided: run `starting_point.py` "
            "(SpireHDL mode) to generate a correct reference design (design.v). "
            "Study the context files in your workspace for implementation details, "
            "then optimize from there."
        )
    (bench_dir / "description.txt").write_text(description + "\n")

    # Write metadata.json
    metadata = {
        "name": bench_name,
        "module_name": module_name,
        "tb_module": "tb",
        "generator": {
            "type": gen_type,
            "module_name": module_name,
            "num_vectors": num_vectors,
            "config": _cfg_to_dict(cfg) if cfg is not None else {},
            "command": sys.argv,
        },
    }
    (bench_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")

    # Write reference Verilog (the generated design)
    verilog_str = m.to_verilog()
    (bench_dir / f"{module_name}.v").write_text(verilog_str)

    # Copy context files
    context_entries = CONTEXT_FILES.get(gen_type, [])
    if context_entries:
        ctx_dir = bench_dir / "context"
        ctx_dir.mkdir()
        for src_rel, dest_name in context_entries:
            src_path = SPIREHDL_SRC / src_rel
            if src_path.exists():
                shutil.copy2(src_path, ctx_dir / dest_name)
            else:
                print(f"  Warning: context file not found: {src_path}")

        # Write a working starting-point .py that produces a correct design
        _write_starting_point_py(ctx_dir, gen_type, module_name, result, cfg)

    print(f"Benchmark created: {bench_dir}")
    print(f"  description.txt, metadata.json, tb.sv, vectors.dat")
    print(f"  reference design: {module_name}.v")
    if context_entries:
        print(f"  context/: {', '.join(d for _, d in context_entries)}")
    return bench_dir


def _write_starting_point_py(ctx_dir: Path, gen_type: str,
                              module_name: str, result: GenerationResult,
                              cfg: object = None) -> None:
    """Write a working starting-point .py that produces a correct design.

    The script imports from local context files (copied into the workspace)
    and writes Verilog via m.to_verilog_file("design.v").
    Running this script should immediately pass evaluation.
    """
    script = _build_starting_point_script(gen_type, module_name, cfg)
    (ctx_dir / "starting_point.py").write_text(script)


def _build_starting_point_script(gen_type: str, module_name: str, cfg: object) -> str:
    """Generate the starting_point.py source code for the given generator type."""

    if gen_type == "fpmul":
        return textwrap.dedent(f"""\
            # Starting point for {module_name} — floating-point multiplier.
            # This script produces a correct design. Modify to optimize.
            #
            # The FpMulSN component is in spire_hdl_float_mult_sn.py (same directory).
            # Edit that file to change the multiplier architecture.
            from spire_hdl_float_mult_sn import FpMulSN

            component = FpMulSN(
                EW={cfg.exponent_width},
                FW={cfg.fraction_width},
                subnormals={cfg.subnormals},
            )
            m = component.to_module("{module_name}", with_clock=False, with_reset=False)
            m.to_verilog_file("design.v")
        """)

    if gen_type == "fpadd":
        return textwrap.dedent(f"""\
            # Starting point for {module_name} — floating-point adder.
            # This script produces a correct design. Modify to optimize.
            #
            # The FpAdd component is in spire_hdl_float_add.py (same directory).
            # Edit that file to change the adder architecture.
            from spire_hdl_float_add import FpAdd

            component = FpAdd(
                EW={cfg.exponent_width},
                FW={cfg.fraction_width},
                subnormals={cfg.subnormals},
            )
            m = component.to_module("{module_name}", with_clock=False, with_reset=False)
            m.to_verilog_file("design.v")
        """)

    if gen_type == "fpmatmulacc":
        use_op = getattr(cfg, "use_operator", False)
        sub = getattr(cfg, "subnormal_support", False)
        asr = getattr(cfg, "always_subnormal_rounding", False)
        if use_op:
            return textwrap.dedent(f"""\
                # Starting point for {module_name} — FP matrix multiply-accumulate.
                # This script produces a correct design. Modify to optimize.
                from spirehdl.aggregate.aggregate_floating_point import FloatingPointType
                from spirehdl.cores.matmul_accumulate.matmul_accumulate_core_float import (
                    FpMMAcCfg, FpMMAcDims, FpMatmulAccumulateComponent,
                )

                ft = FloatingPointType(
                    exponent_width={cfg.exponent_width},
                    fraction_width={cfg.fraction_width},
                    subnormal_support={sub},
                    always_subnormal_rounding={asr},
                )
                core_cfg = FpMMAcCfg(
                    dims=FpMMAcDims(dim_m={cfg.dim_m}, dim_n={cfg.dim_n}, dim_k={cfg.dim_k}),
                    ftype=ft,
                    adder_cfg=None,
                    mult_cfg=None,
                )
                component = FpMatmulAccumulateComponent(core_cfg)
                m = component.to_module("{module_name}", with_clock=False, with_reset=False)
                m.to_verilog_file("design.v")
            """)
        else:
            return textwrap.dedent(f"""\
                # Starting point for {module_name} — FP matrix multiply-accumulate.
                # This script produces a correct design. Modify to optimize.
                from spirehdl.aggregate.aggregate_floating_point import FloatingPointType
                from spirehdl.arithmetic.int_arithmetic_config import (
                    AdderConfig, MultiplierConfig,
                )
                from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
                    FSAOption, MultiplierOption, PPAOption, PPGOption, TwoInputAritEncodings,
                )
                from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import Encoding
                from spirehdl.cores.matmul_accumulate.matmul_accumulate_core_float import (
                    FpMMAcCfg, FpMMAcDims, FpMatmulAccumulateComponent,
                )

                ft = FloatingPointType(
                    exponent_width={cfg.exponent_width},
                    fraction_width={cfg.fraction_width},
                    subnormal_support={sub},
                    always_subnormal_rounding={asr},
                )
                mult_cfg = MultiplierConfig(
                    use_operator=False,
                    multiplier_opt=MultiplierOption.{cfg.multiplier_opt.name},
                    encodings=TwoInputAritEncodings.with_enc(Encoding.unsigned),
                    ppg_opt=PPGOption.{cfg.ppg_opt.name},
                    ppa_opt=PPAOption.{cfg.ppa_opt.name},
                    fsa_opt=FSAOption.{cfg.fsa_opt.name},
                    optim_type="{cfg.optim_type}",
                )
                adder_cfg = AdderConfig(
                    use_operator=False,
                    encoding=Encoding.unsigned,
                    optim_type="{cfg.optim_type}",
                    fsa_opt=FSAOption.{cfg.fsa_opt.name},
                    full_output_bit=True,
                )
                core_cfg = FpMMAcCfg(
                    dims=FpMMAcDims(dim_m={cfg.dim_m}, dim_n={cfg.dim_n}, dim_k={cfg.dim_k}),
                    ftype=ft,
                    adder_cfg=adder_cfg,
                    mult_cfg=mult_cfg,
                )
                component = FpMatmulAccumulateComponent(core_cfg)
                m = component.to_module("{module_name}", with_clock=False, with_reset=False)
                m.to_verilog_file("design.v")
            """)

    if gen_type == "matmulacc":
        use_op = getattr(cfg, "use_operator", False)
        enc_name = cfg.input_encoding.name
        if use_op:
            return textwrap.dedent(f"""\
                # Starting point for {module_name} — integer matrix multiply-accumulate.
                # This script produces a correct design. Modify to optimize.
                from spirehdl.arithmetic.int_arithmetic_config import AdderConfig, MultiplierConfig
                from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import Encoding
                from spirehdl.cores.matmul_accumulate.matmul_accumulate_core import (
                    MMAcCfg, MMAcDims, MMAcWidths, MatmulAccumulateComponent, max_y_width_unsigned,
                )

                c_width = max_y_width_unsigned({cfg.a_width}, {cfg.a_width}, {cfg.dim_k}, include_carry_from_add=False)
                core_cfg = MMAcCfg(
                    dims=MMAcDims(dim_m={cfg.dim_m}, dim_n={cfg.dim_n}, dim_k={cfg.dim_k}),
                    widths=MMAcWidths(a_width={cfg.a_width}, b_width={cfg.a_width}, c_width=c_width),
                    mult_cfg=MultiplierConfig(use_operator=True),
                    add_cfg=AdderConfig(use_operator=True, encoding=Encoding.{enc_name}),
                )
                component = MatmulAccumulateComponent(core_cfg, signed_io_type=True)
                m = component.to_module("{module_name}", with_clock=False, with_reset=False)
                m.to_verilog_file("design.v")
            """)
        else:
            return textwrap.dedent(f"""\
                # Starting point for {module_name} — integer matrix multiply-accumulate.
                # This script produces a correct design. Modify to optimize.
                from spirehdl.arithmetic.int_arithmetic_config import AdderConfig, MultiplierConfig
                from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
                    FSAOption, MultiplierOption, PPAOption, PPGOption, TwoInputAritEncodings,
                )
                from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import Encoding
                from spirehdl.cores.matmul_accumulate.matmul_accumulate_core import (
                    MMAcCfg, MMAcDims, MMAcWidths, MatmulAccumulateComponent, max_y_width_unsigned,
                )

                c_width = max_y_width_unsigned({cfg.a_width}, {cfg.a_width}, {cfg.dim_k}, include_carry_from_add=False)
                encodings = TwoInputAritEncodings.with_enc(Encoding.{enc_name})
                mult_cfg = MultiplierConfig(
                    use_operator=False,
                    multiplier_opt=MultiplierOption.{cfg.multiplier_opt.name},
                    encodings=encodings,
                    ppg_opt=PPGOption.{cfg.ppg_opt.name},
                    ppa_opt=PPAOption.{cfg.ppa_opt.name},
                    fsa_opt=FSAOption.{cfg.fsa_opt.name},
                    optim_type="{cfg.optim_type}",
                )
                adder_cfg = AdderConfig(
                    use_operator=False,
                    encoding=Encoding.{enc_name},
                    optim_type="{cfg.optim_type}",
                    fsa_opt=FSAOption.{cfg.fsa_opt.name},
                    full_output_bit=True,
                )
                core_cfg = MMAcCfg(
                    dims=MMAcDims(dim_m={cfg.dim_m}, dim_n={cfg.dim_n}, dim_k={cfg.dim_k}),
                    widths=MMAcWidths(a_width={cfg.a_width}, b_width={cfg.a_width}, c_width=c_width),
                    mult_cfg=mult_cfg,
                    add_cfg=adder_cfg,
                )
                component = MatmulAccumulateComponent(core_cfg, signed_io_type=False)
                m = component.to_module("{module_name}", with_clock=False, with_reset=False)
                m.to_verilog_file("design.v")
            """)

    if gen_type == "matmulacc-fused":
        enc_name = cfg.input_encoding.name
        return textwrap.dedent(f"""\
            # Starting point for {module_name} — fused integer matrix multiply-accumulate.
            # This script produces a correct design. Modify to optimize.
            from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
                FSAOption, PPAOption, PPGOption,
            )
            from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import Encoding
            from spirehdl.cores.matmul_accumulate.matmul_accumulate_core import (
                MMAcDims, MMAcWidths, max_y_width_unsigned,
            )
            from spirehdl.cores.matmul_accumulate.matmul_accumulate_core_fused import (
                MMAcFusedCfg,
                MatmulAccumulateComponent as MatmulAccumulateFusedComponent,
                MultiplierConfig as FusedMultiplierConfig,
            )

            c_width = max_y_width_unsigned({cfg.a_width}, {cfg.a_width}, {cfg.dim_k}, include_carry_from_add=False)
            mult_cfg = FusedMultiplierConfig(
                ppg_opt=PPGOption.{cfg.ppg_opt.name},
                ppa_opt=PPAOption.{cfg.ppa_opt.name},
                fsa_opt=FSAOption.{cfg.fsa_opt.name},
                optim_type="{cfg.optim_type}",
            )
            core_cfg = MMAcFusedCfg(
                dims=MMAcDims(dim_m={cfg.dim_m}, dim_n={cfg.dim_n}, dim_k={cfg.dim_k}),
                widths=MMAcWidths(a_width={cfg.a_width}, b_width={cfg.a_width}, c_width=c_width),
                mult_cfg=mult_cfg,
                encoding=Encoding.{enc_name},
            )
            component = MatmulAccumulateFusedComponent(core_cfg)
            m = component.to_module("{module_name}", with_clock=False, with_reset=False)
            m.to_verilog_file("design.v")
        """)

    # For multiplier, adder, mac — use the generator API (simplest working approach)
    if gen_type == "multiplier":
        return textwrap.dedent(f"""\
            # Starting point for {module_name} — integer multiplier.
            # This script produces a correct design. Modify to optimize.
            from spirehdl.arithmetic.arithmetic_generator import (
                MultiplierGeneratorConfig, generate_multiplier,
            )
            from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
                FSAOption, MultiplierOption, PPAOption, PPGOption,
            )
            from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import Encoding

            cfg = MultiplierGeneratorConfig(
                n_bits={cfg.n_bits},
                multiplier_opt=MultiplierOption.{cfg.multiplier_opt.name},
                ppg_opt=PPGOption.{cfg.ppg_opt.name},
                ppa_opt=PPAOption.{cfg.ppa_opt.name},
                fsa_opt=FSAOption.{cfg.fsa_opt.name},
                input_encoding=Encoding.{cfg.input_encoding.name},
            )
            result = generate_multiplier(cfg)
            result.module.to_verilog_file("design.v")
        """)

    if gen_type == "adder":
        return textwrap.dedent(f"""\
            # Starting point for {module_name} — integer adder.
            # This script produces a correct design. Modify to optimize.
            from spirehdl.arithmetic.arithmetic_generator import (
                AdderGeneratorConfig, generate_adder,
            )
            from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import FSAOption
            from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import Encoding

            cfg = AdderGeneratorConfig(
                n_bits={cfg.n_bits},
                fsa_opt=FSAOption.{cfg.fsa_opt.name},
                input_encoding=Encoding.{cfg.input_encoding.name},
                full_output_bit=True,
            )
            result = generate_adder(cfg)
            result.module.to_verilog_file("design.v")
        """)

    if gen_type == "mac":
        c_bits_str = str(cfg.c_bits) if cfg.c_bits is not None else "None"
        return textwrap.dedent(f"""\
            # Starting point for {module_name} — multiply-accumulate (y = a*b + c).
            # This script produces a correct design. Modify to optimize.
            from spirehdl.arithmetic.arithmetic_generator import (
                MacGeneratorConfig, generate_mac,
            )
            from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
                FSAOption, PPAOption, PPGOption,
            )
            from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import Encoding

            cfg = MacGeneratorConfig(
                n_bits={cfg.n_bits},
                c_bits={c_bits_str},
                ppg_opt=PPGOption.{cfg.ppg_opt.name},
                ppa_opt=PPAOption.{cfg.ppa_opt.name},
                fsa_opt=FSAOption.{cfg.fsa_opt.name},
                input_encoding=Encoding.{cfg.input_encoding.name},
            )
            result = generate_mac(cfg)
            result.module.to_verilog_file("design.v")
        """)

    # Fallback: generic stub (shouldn't happen for known types)
    return textwrap.dedent(f"""\
        # Starting point for {module_name}.
        # Replace this with a working implementation.
        raise NotImplementedError("No starting point for gen_type={gen_type}")
    """)


# ---------------------------------------------------------------------------
# Generator dispatch
# ---------------------------------------------------------------------------

def _parse_encoding(s: str) -> Encoding:
    mapping = {
        "unsigned": Encoding.unsigned,
        "twos_complement": Encoding.twos_complement,
        "sign_magnitude": Encoding.sign_magnitude,
    }
    if s not in mapping:
        raise argparse.ArgumentTypeError(
            f"Invalid encoding: '{s}'. Valid: {', '.join(mapping)}"
        )
    return mapping[s]


def _parse_fsa(s: str) -> FSAOption:
    try:
        return FSAOption[s]
    except KeyError:
        valid = ", ".join(o.name for o in FSAOption)
        raise argparse.ArgumentTypeError(f"Invalid FSA option: '{s}'. Valid: {valid}")


def _parse_ppa(s: str) -> PPAOption:
    try:
        return PPAOption[s]
    except KeyError:
        valid = ", ".join(o.name for o in PPAOption)
        raise argparse.ArgumentTypeError(f"Invalid PPA option: '{s}'. Valid: {valid}")


def _parse_ppg(s: str) -> PPGOption:
    try:
        return PPGOption[s]
    except KeyError:
        valid = ", ".join(o.name for o in PPGOption)
        raise argparse.ArgumentTypeError(f"Invalid PPG option: '{s}'. Valid: {valid}")


def _parse_mult_opt(s: str) -> MultiplierOption:
    try:
        return MultiplierOption[s]
    except KeyError:
        valid = ", ".join(o.name for o in MultiplierOption)
        raise argparse.ArgumentTypeError(f"Invalid multiplier option: '{s}'. Valid: {valid}")


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--num-vectors", type=int, default=2000,
                        help="Number of test vectors (default: 2000)")
    parser.add_argument("--name", type=str, default=None,
                        help="Benchmark name (default: auto-generated)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing benchmark")
    parser.add_argument("--benchmarks-dir", type=str, default=str(BENCHMARKS_DIR),
                        help="Benchmarks directory")


def _add_stage_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ppg-opt", type=_parse_ppg, default=PPGOption.AND,
                        help="Partial product generation (default: AND)")
    parser.add_argument("--ppa-opt", type=_parse_ppa, default=PPAOption.ACCUMULATOR_TREE,
                        help="Partial product addition (default: ACCUMULATOR_TREE)")
    parser.add_argument("--fsa-opt", type=_parse_fsa, default=FSAOption.RIPPLE_CARRY,
                        help="Final stage adder (default: RIPPLE_CARRY)")


def gen_multiplier(args: argparse.Namespace) -> None:
    cfg = MultiplierGeneratorConfig(
        n_bits=args.n_bits,
        multiplier_opt=args.multiplier_opt,
        ppg_opt=args.ppg_opt,
        ppa_opt=args.ppa_opt,
        fsa_opt=args.fsa_opt,
        input_encoding=args.encoding,
    )
    actions = GenerationActions(simulate=True, num_vectors=args.num_vectors, targeted_test_vectors=True)
    result = generate_multiplier(cfg, actions=actions)

    module_name = result.module.name
    bench_name = args.name or f"mult{args.n_bits}"
    y_width = _signal_width(result.module, "y")
    description = _multiplier_description(cfg, module_name, y_width)

    _create_benchmark(
        bench_name, "multiplier", module_name, description, result,
        args.num_vectors, Path(args.benchmarks_dir), args.force, cfg=cfg,
    )


def gen_adder(args: argparse.Namespace) -> None:
    cfg = AdderGeneratorConfig(
        n_bits=args.n_bits,
        fsa_opt=args.fsa_opt,
        input_encoding=args.encoding,
        full_output_bit=True,
    )
    actions = GenerationActions(simulate=True, num_vectors=args.num_vectors, targeted_test_vectors=True)
    result = generate_adder(cfg, actions=actions)

    module_name = result.module.name
    bench_name = args.name or f"add{args.n_bits}"
    y_width = _signal_width(result.module, "y")
    description = _adder_description(cfg, module_name, y_width)

    _create_benchmark(
        bench_name, "adder", module_name, description, result,
        args.num_vectors, Path(args.benchmarks_dir), args.force, cfg=cfg,
    )


def gen_mac(args: argparse.Namespace) -> None:
    cfg = MacGeneratorConfig(
        n_bits=args.n_bits,
        c_bits=args.c_bits,
        ppg_opt=args.ppg_opt,
        ppa_opt=args.ppa_opt,
        fsa_opt=args.fsa_opt,
        input_encoding=args.encoding,
    )
    actions = GenerationActions(simulate=True, num_vectors=args.num_vectors, targeted_test_vectors=True)
    result = generate_mac(cfg, actions=actions)

    module_name = result.module.name
    m = result.module
    a_w = _signal_width(m, "a")
    b_w = _signal_width(m, "b")
    c_w = _signal_width(m, "c")
    y_w = _signal_width(m, "y")
    bench_name = args.name or f"mac{args.n_bits}"
    description = _mac_description(cfg, module_name, a_w, b_w, c_w, y_w)

    _create_benchmark(
        bench_name, "mac", module_name, description, result,
        args.num_vectors, Path(args.benchmarks_dir), args.force, cfg=cfg,
    )


def gen_matmulacc(args: argparse.Namespace) -> None:
    cfg = MatmulAccumulateGeneratorConfig(
        dim_m=args.dim_m,
        dim_n=args.dim_n,
        dim_k=args.dim_k,
        a_width=args.a_width,
        ppg_opt=args.ppg_opt,
        ppa_opt=args.ppa_opt,
        fsa_opt=args.fsa_opt,
        input_encoding=args.encoding,
        use_operator=args.use_operator,
    )
    actions = GenerationActions(simulate=True, num_vectors=args.num_vectors, targeted_test_vectors=True)
    result = generate_matmul_accumulate(cfg, actions=actions)

    module_name = result.module.name
    bench_name = args.name or f"matmulacc{args.dim_m}x{args.dim_n}x{args.dim_k}_{args.a_width}b"
    description = _matmul_description(cfg, module_name, result)

    _create_benchmark(
        bench_name, "matmulacc", module_name, description, result,
        args.num_vectors, Path(args.benchmarks_dir), args.force, cfg=cfg,
    )


def gen_matmulacc_fused(args: argparse.Namespace) -> None:
    cfg = MatmulAccumulateFusedGeneratorConfig(
        dim_m=args.dim_m,
        dim_n=args.dim_n,
        dim_k=args.dim_k,
        a_width=args.a_width,
        ppg_opt=args.ppg_opt,
        ppa_opt=args.ppa_opt,
        fsa_opt=args.fsa_opt,
        input_encoding=args.encoding,
    )
    actions = GenerationActions(simulate=True, num_vectors=args.num_vectors, targeted_test_vectors=True)
    result = generate_matmul_accumulate_fused(cfg, actions=actions)

    module_name = result.module.name
    bench_name = args.name or f"matmulacc_fused{args.dim_m}x{args.dim_n}x{args.dim_k}_{args.a_width}b"
    description = _matmul_fused_description(cfg, module_name, result)

    _create_benchmark(
        bench_name, "matmulacc-fused", module_name, description, result,
        args.num_vectors, Path(args.benchmarks_dir), args.force, cfg=cfg,
    )


def gen_fpmul(args: argparse.Namespace) -> None:
    cfg = FpMultiplierGeneratorConfig(
        exponent_width=args.exponent_width,
        fraction_width=args.fraction_width,
        subnormals=args.subnormal_support,
    )
    actions = GenerationActions(simulate=True, num_vectors=args.num_vectors, targeted_test_vectors=True)
    result = generate_fp_multiplier(cfg, actions=actions)

    module_name = result.module.name
    bench_name = args.name or _fp_bench_name("fpmul", args.exponent_width, args.fraction_width)
    description = _fpmul_description(cfg, module_name)

    _create_benchmark(
        bench_name, "fpmul", module_name, description, result,
        args.num_vectors, Path(args.benchmarks_dir), args.force, cfg=cfg,
    )


def gen_fpadd(args: argparse.Namespace) -> None:
    cfg = FpAdderGeneratorConfig(
        exponent_width=args.exponent_width,
        fraction_width=args.fraction_width,
        subnormals=args.subnormal_support,
    )
    actions = GenerationActions(simulate=True, num_vectors=args.num_vectors, targeted_test_vectors=True)
    result = generate_fp_adder(cfg, actions=actions)

    module_name = result.module.name
    bench_name = args.name or _fp_bench_name("fpadd", args.exponent_width, args.fraction_width)
    description = _fpadd_description(cfg, module_name)

    _create_benchmark(
        bench_name, "fpadd", module_name, description, result,
        args.num_vectors, Path(args.benchmarks_dir), args.force, cfg=cfg,
    )


def gen_fpmatmulacc(args: argparse.Namespace) -> None:
    cfg = FpMatmulAccumulateGeneratorConfig(
        dim_m=args.dim_m,
        dim_n=args.dim_n,
        dim_k=args.dim_k,
        exponent_width=args.exponent_width,
        fraction_width=args.fraction_width,
        subnormal_support=args.subnormal_support,
        use_operator=args.use_operator,
        ppg_opt=args.ppg_opt,
        ppa_opt=args.ppa_opt,
        fsa_opt=args.fsa_opt,
    )
    actions = GenerationActions(simulate=True, num_vectors=args.num_vectors, targeted_test_vectors=True)
    result = generate_fp_matmul_accumulate(cfg, actions=actions)

    module_name = result.module.name
    bench_name = (args.name or
                  f"fpmatmulacc{args.dim_m}x{args.dim_n}x{args.dim_k}_e{args.exponent_width}f{args.fraction_width}")
    description = _fpmatmulacc_description(cfg, module_name, result)

    _create_benchmark(
        bench_name, "fpmatmulacc", module_name, description, result,
        args.num_vectors, Path(args.benchmarks_dir), args.force, cfg=cfg,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate an core benchmark from spire-hdl generators",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python add_benchmark.py multiplier --n-bits 8
              python add_benchmark.py adder --n-bits 16 --encoding twos_complement
              python add_benchmark.py mac --n-bits 8 --c-bits 16
              python add_benchmark.py matmulacc --dim-m 4 --dim-n 4 --dim-k 4 --a-width 4
              python add_benchmark.py fpmul --exponent-width 8 --fraction-width 7
              python add_benchmark.py fpmatmulacc --dim-m 2 --dim-n 2 --dim-k 2 --exponent-width 5 --fraction-width 10
              python add_benchmark.py matmulacc-fused --dim-m 4 --dim-n 4 --dim-k 4 --a-width 8
        """),
    )
    subparsers = parser.add_subparsers(dest="type", required=True)

    # --- multiplier ---
    p_mul = subparsers.add_parser("multiplier", help="Integer multiplier")
    p_mul.add_argument("--n-bits", type=int, required=True)
    p_mul.add_argument("--encoding", type=_parse_encoding, default=Encoding.unsigned)
    p_mul.add_argument("--multiplier-opt", type=_parse_mult_opt,
                       default=MultiplierOption.STAGE_BASED_MULTIPLIER)
    _add_stage_args(p_mul)
    _add_common_args(p_mul)
    p_mul.set_defaults(func=gen_multiplier)

    # --- adder ---
    p_add = subparsers.add_parser("adder", help="Integer adder")
    p_add.add_argument("--n-bits", type=int, required=True)
    p_add.add_argument("--encoding", type=_parse_encoding, default=Encoding.unsigned)
    p_add.add_argument("--fsa-opt", type=_parse_fsa, default=FSAOption.RIPPLE_CARRY)
    _add_common_args(p_add)
    p_add.set_defaults(func=gen_adder)

    # --- mac ---
    p_mac = subparsers.add_parser("mac", help="Multiply-accumulate (y = a*b + c)")
    p_mac.add_argument("--n-bits", type=int, required=True)
    p_mac.add_argument("--c-bits", type=int, default=None)
    p_mac.add_argument("--encoding", type=_parse_encoding, default=Encoding.unsigned)
    _add_stage_args(p_mac)
    _add_common_args(p_mac)
    p_mac.set_defaults(func=gen_mac)

    # --- matmulacc ---
    p_mm = subparsers.add_parser("matmulacc", help="Integer matrix multiply-accumulate")
    p_mm.add_argument("--dim-m", type=int, required=True)
    p_mm.add_argument("--dim-n", type=int, required=True)
    p_mm.add_argument("--dim-k", type=int, required=True)
    p_mm.add_argument("--a-width", type=int, required=True)
    p_mm.add_argument("--encoding", type=_parse_encoding, default=Encoding.unsigned)
    p_mm.add_argument("--use-operator", action="store_true")
    _add_stage_args(p_mm)
    _add_common_args(p_mm)
    p_mm.set_defaults(func=gen_matmulacc)

    # --- matmulacc-fused ---
    p_mmf = subparsers.add_parser("matmulacc-fused", help="Fused integer matrix multiply-accumulate")
    p_mmf.add_argument("--dim-m", type=int, required=True)
    p_mmf.add_argument("--dim-n", type=int, required=True)
    p_mmf.add_argument("--dim-k", type=int, required=True)
    p_mmf.add_argument("--a-width", type=int, required=True)
    p_mmf.add_argument("--encoding", type=_parse_encoding, default=Encoding.unsigned)
    _add_stage_args(p_mmf)
    _add_common_args(p_mmf)
    p_mmf.set_defaults(func=gen_matmulacc_fused)

    # --- fpmul ---
    p_fpmul = subparsers.add_parser("fpmul", help="Floating-point multiplier")
    p_fpmul.add_argument("--exponent-width", type=int, required=True)
    p_fpmul.add_argument("--fraction-width", type=int, required=True)
    p_fpmul.add_argument("--subnormal-support", action="store_true")
    _add_common_args(p_fpmul)
    p_fpmul.set_defaults(func=gen_fpmul)

    # --- fpadd ---
    p_fpadd = subparsers.add_parser("fpadd", help="Floating-point adder")
    p_fpadd.add_argument("--exponent-width", type=int, required=True)
    p_fpadd.add_argument("--fraction-width", type=int, required=True)
    p_fpadd.add_argument("--subnormal-support", action="store_true")
    _add_common_args(p_fpadd)
    p_fpadd.set_defaults(func=gen_fpadd)

    # --- fpmatmulacc ---
    p_fpmm = subparsers.add_parser("fpmatmulacc", help="FP matrix multiply-accumulate")
    p_fpmm.add_argument("--dim-m", type=int, required=True)
    p_fpmm.add_argument("--dim-n", type=int, required=True)
    p_fpmm.add_argument("--dim-k", type=int, required=True)
    p_fpmm.add_argument("--exponent-width", type=int, required=True)
    p_fpmm.add_argument("--fraction-width", type=int, required=True)
    p_fpmm.add_argument("--subnormal-support", action="store_true")
    p_fpmm.add_argument("--use-operator", action="store_true")
    _add_stage_args(p_fpmm)
    _add_common_args(p_fpmm)
    p_fpmm.set_defaults(func=gen_fpmatmulacc)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
