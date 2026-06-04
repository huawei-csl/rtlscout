import os
import re
import shlex
import shutil
import subprocess
from itertools import product
from multiprocessing import Pool
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Type, Union

from tech_eval.ppa_extract.core.template import (
    abc_constr,
    get_fa_ha_inference_cmds,
    get_tech_config,
    lef_paths_subst,
    lib_paths_subst,
    lib_paths,
    make_vcd_flags,
    lib_time_to_ps,
    ps_to_lib_time,
    sta_script_template,
    verilator_common_flags,
    verilator_directive_flags,
    verilator_netlist_flags,
    yosys_script_template,
)

from tech_eval.ppa_extract.core.template import target_delay_time_unit
PPA_REPORT_TIME_UNIT = "ps"


def _parse_sta_out(sta_out_path: str):
    """Parse delay / area / power / worst_slack / worst_timing_path from an
    OpenROAD STA log. Returns those five plus the raw ``lines`` (for diagnostics).
    Any value that didn't appear comes back as ``None``."""
    delay = area = power = worst_slack = None
    worst_timing_path = None
    with open(sta_out_path, "r") as f:
        lines = f.readlines()
    report_checks_lines = []
    in_report_checks = False
    for line in lines:
        stripped = line.strip()
        if stripped == "REPORT_CHECKS_BEGIN":
            in_report_checks = True
            continue
        if stripped == "REPORT_CHECKS_END":
            in_report_checks = False
            continue
        if in_report_checks:
            report_checks_lines.append(line)
            continue
        words = line.split()
        if len(words) > 0:
            if words[0] == "wns":
                # CRITICAL: we set 0.2 * 5 input delay in sta script
                delay = float(words[1])  # - 1
            if words[0] == "worst" and words[1] == "slack":
                worst_slack = float(words[-1])
            if words[0] == "design_area_precise":
                # High-precision area from `rsz::design_area` (Tcl double,
                # square meters → um^2). Overrides the integer-rounded value.
                area = float(words[1])
            elif words[0] == "Design" and area is None:
                # Fallback: integer-rounded `Design area <N> um^2 ...`.
                area = float(words[2])
            if words[0] == "Total":
                power = float(words[-2])
    if report_checks_lines:
        worst_timing_path = "".join(report_checks_lines).strip()
    return delay, area, power, worst_slack, worst_timing_path, lines

def parse_verilator_output(output: str, test_name: Optional[str] = None) -> None:
    if "Testbench completed successfully" not in output:
        print(output)
        last_1000_characters = output[-1000:] if len(output) > 1000 else output
        raise RuntimeError("Verilator testbench did not complete successfully, output:\n...\n" + last_1000_characters)

    match = re.search(r"Finished:\s+(\d+)\s+passed,\s+(\d+)\s+failed", output)
    if match:
        passed = int(match.group(1))
        failed = int(match.group(2))

        test_name = "" if test_name is None else test_name + " - "
        print(f"{test_name}Number of vectors: {passed+failed}, {failed} failures")

        if failed > 0 or passed == 0:
            raise RuntimeError(
                f"Verilator testbench failed with {failed} failed tests ({passed} passed)"
            )
    else:
        raise RuntimeError("Could not find test results in Verilator output")


def get_full_target_delay(bit_width):
    if bit_width == 8:
        return list(range(50, 1000, 10))
    elif bit_width == 16:
        return list(range(50, 2000, 20))
    elif bit_width == 32:
        return list(range(50, 3000, 20))
    else:
        return list(range(50, 4000, 20))


def get_target_delay(bit_width):
    if bit_width == 8:
        return [50, 250, 400, 650, 900]
    elif bit_width == 16:
        return [50, 200, 500, 1200, 1800, 2600]
    elif bit_width == 32:
        return [50, 300, 600, 2000, 2800]
    else:
        return [50, 600, 1500, 3000]


def _normalize_flags(flags: Union[Sequence[str], str, None]) -> List[str]:
    if not flags:
        return []
    if isinstance(flags, str):
        return shlex.split(flags)
    return [str(flag) for flag in flags]


def _normalize_verilog_files(rtl_path: Union[str, os.PathLike, Sequence[Union[str, os.PathLike]]]) -> List[str]:
    if isinstance(rtl_path, (str, os.PathLike)):
        files = [os.fspath(rtl_path)]
    elif isinstance(rtl_path, Sequence):
        files = [os.fspath(path) for path in rtl_path]
    else:
        raise TypeError("rtl_path must be a path string, PathLike, or a sequence of paths")

    files = [os.path.abspath(path) for path in files if path]
    if not files:
        raise ValueError("No RTL files provided")

    return files


def _run_verilator_generic(
    sources: Sequence[str],
    tb_top_module: str,
    build_dir: str,
    log_path: str,
    *,
    flags: Union[Sequence[str], str] = (),
    test_name: Optional[str] = None,
    output_parser: Optional[Any] = None,
    run_cwd: Optional[str] = None,
) -> str:
    sources = [os.path.abspath(src) for src in sources if src]
    if not sources:
        raise ValueError("No Verilog sources provided for Verilator run")
    if not tb_top_module:
        raise ValueError("tb_top_module is required for Verilator run")

    missing_sources = [src for src in sources if not os.path.exists(src)]
    if missing_sources:
        raise FileNotFoundError(f"Verilator sources not found: {', '.join(missing_sources)}")

    build_dir = os.path.abspath(build_dir)
    log_path = os.path.abspath(log_path)
    os.makedirs(build_dir, exist_ok=True)
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    cmd = [
        "verilator",
        "--Mdir",
        build_dir,
        "--top-module",
        tb_top_module,
    ]

    cmd += _normalize_flags(flags)
    cmd += sources

    compile_proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    compile_output = compile_proc.stdout + "\n" + compile_proc.stderr

    with open(log_path, "w") as log_f:
        log_f.write(compile_output)

    if compile_proc.returncode != 0:
        raise RuntimeError(f"Verilator compile failed; see {log_path}")

    binary_path = os.path.join(build_dir, f"V{tb_top_module}")
    if not os.path.exists(binary_path):
        raise RuntimeError(f"Expected Verilator binary not found: {binary_path}")

    run_proc = subprocess.run(
        [binary_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=run_cwd,
    )
    run_output = run_proc.stdout + "\n" + run_proc.stderr

    with open(log_path, "a") as log_f:
        log_f.write(run_output)

    if run_proc.returncode != 0:
        raise RuntimeError(f"Verilator simulation failed; see {log_path}")

    combined_output = compile_output + run_output
    if output_parser is not None:
        output_parser(combined_output)
    else:
        parse_verilator_output(combined_output, test_name=test_name or tb_top_module)

    return binary_path


def get_ppa(
    rtl_path,
    target_delay: float,
    worker_path: Optional[str],
    top_module_name="MUL",
    run_verilator: bool = False,
    tb_filename: Optional[str] = None,
    tb_name: Optional[str] = None,
    save_vcd: bool = False,
    use_vcd_for_power: bool = False,
    use_fa_ha_inference: bool = False,
    output_parser: Optional[Any] = None,
    data_files: Optional[Sequence[Union[str, "os.PathLike[str]"]]] = None,
    run_in_worker_path: bool = False,
    technology: str = "asap7",
):
    
    # Resolve technology config (overrides module-level defaults when not asap7)
    cfg = get_tech_config(technology)
    _lib_paths = cfg.lib_paths
    _lef_paths_subst = " ".join(cfg.lef_paths)
    _lib_paths_subst = " ".join(cfg.lib_paths)
    _abc_constr = cfg.abc_constr
    _verilator_netlist_flags = cfg.verilator_netlist_flags

    if worker_path is None:
        # create a temporary folder using tempfile
        import tempfile
        worker_path = tempfile.mkdtemp()

    verilog_files = _normalize_verilog_files(rtl_path)
    if tb_filename:
        tb_filename = os.path.abspath(tb_filename)

    # validation checks on verilator vcd usage
    if use_vcd_for_power and not run_verilator:
        raise ValueError("use_verilator_vcd requires run_verilator=True")
    if (run_verilator or use_vcd_for_power) and not tb_name:
        raise ValueError("tb_name is required when running Verilator")
    if use_vcd_for_power and not save_vcd:
        raise ValueError("write_vcd must be True when use_verilator_vcd is True")

    os.makedirs(worker_path, exist_ok=True)
    worker_path = os.path.abspath(worker_path)

    # Copy auxiliary data files (e.g. vectors.dat for data-driven testbenches)
    # into the worker directory so relative $fopen paths resolve correctly.
    if data_files:
        for df in data_files:
            df = os.path.abspath(os.fspath(df))
            dest = os.path.join(worker_path, os.path.basename(df))
            if not os.path.exists(dest):
                shutil.copy2(df, dest)

    yosys_script_path = os.path.join(worker_path, "yosys.ys")
    sta_script_path = os.path.join(worker_path, "sta.tcl")
    netlist_path = os.path.join(worker_path, "netlist.v")
    constr_path = os.path.join(worker_path, "constr.sdc")
    yosys_out_path = os.path.join(worker_path, "yosys_out.log")
    sta_out_path = os.path.join(worker_path, "sta_out.log")
 
    verilator_vcd_path = os.path.join(worker_path, f"{tb_name.lower()}_sim_netlist.vcd") if use_vcd_for_power else None
    
    tb_scope_name = tb_name
    
    if use_vcd_for_power:
        power_activity_cmd = f"read_vcd  -scope {tb_scope_name} {{{verilator_vcd_path}}}"
    else:
        power_activity_cmd = "set_power_activity -input -activity 0.5" # generic input activity of 0.5

    liberty_args = " ".join(f"-liberty {p}" for p in _lib_paths)
    fa_ha_inference_cmds = get_fa_ha_inference_cmds(use_fa_ha_inference, cfg)

    read_cmds = []
    for vf in verilog_files:
        read_cmds.append(f"read_verilog -sv {vf}")
    
    yosys_script = yosys_script_template.format(
        read_verilog_cmds="\n".join(read_cmds),
        liberty_args=liberty_args,
        target_delay=target_delay,
        constr_path=constr_path,
        netlist_path=netlist_path,
        top_module_name=top_module_name,
        fa_ha_inference_cmds=fa_ha_inference_cmds,
    )
    with open(yosys_script_path, "w") as f:
        f.write(yosys_script)
    sta_script = sta_script_template.format(
        lef_paths_subst=_lef_paths_subst,
        lib_paths_subst=_lib_paths_subst,
        verilog_path=netlist_path,
        top_module_name=top_module_name,
        power_activity_cmd=power_activity_cmd,
        sta_target_delay=ps_to_lib_time(target_delay, cfg),
    )
    with open(sta_script_path, "w") as f:
        f.write(sta_script)
    with open(constr_path, "w") as f:
        f.write(_abc_constr)

    os.system(f"yosys {yosys_script_path} > {yosys_out_path}")

    if run_verilator:
        verilator_build_dir = os.path.abspath(os.path.join(worker_path, "out"))
        verilator_log_path = os.path.join(worker_path, "verilator_netlist_out.log")

        flags = list(verilator_directive_flags) + list(verilator_common_flags) + list(
            _verilator_netlist_flags
        )
        if save_vcd:
            flags += make_vcd_flags(verilator_vcd_path)
        
        sources = [netlist_path]
        if tb_filename:
            sources.append(tb_filename)

        _run_verilator_generic(
            sources=sources,
            tb_top_module=tb_name,
            build_dir=verilator_build_dir,
            log_path=verilator_log_path,
            flags=flags,
            test_name="Verilator Netlist Simulation",
            output_parser=output_parser,
            run_cwd=worker_path if run_in_worker_path else None, # set to worker path to be able to open files in the same directory (e.g. dat stimuli files)
        )

    os.system(f"openroad -exit {sta_script_path} > {sta_out_path}")

    delay, area, power, worst_slack, worst_timing_path, lines = _parse_sta_out(sta_out_path)

    missing = [name for name, val in [("delay", delay), ("area", area), ("power", power), ("worst_slack", worst_slack)] if val is None]

    if missing:
        try:
            with open(yosys_out_path, "r") as f:
                yosys_lines = f.readlines()
            yosys_tail = "".join(yosys_lines[-30:]) if yosys_lines else "(empty)"
        except OSError:
            yosys_tail = "(could not read file)"
        print(f"[ppa_extraction] Yosys output ({yosys_out_path}) — last 30 lines:\n{yosys_tail}")
        sta_tail = "".join(lines[-30:]) if lines else "(empty)"
        print(f"[ppa_extraction] STA output ({sta_out_path}) — last 30 lines:\n{sta_tail}")
        raise RuntimeError(f"Could not parse {missing} from STA output; see above")

    # if target_delay_time_unit does not equal PPA_REPORT_TIME_UNIT, raise error
    if target_delay_time_unit != PPA_REPORT_TIME_UNIT:
        raise ValueError(f"target_delay_time_unit ({target_delay_time_unit}) does not match PPA_REPORT_TIME_UNIT ({PPA_REPORT_TIME_UNIT})")
    
    return {
        "delay": lib_time_to_ps(delay, cfg),
        "area": area,
        "power": power,
        "worst_slack": worst_slack,
        "target_delay": target_delay,
        "worker_path": worker_path,
        "delay_time_unit": PPA_REPORT_TIME_UNIT,
        "worst_timing_path": worst_timing_path,
    }
    
def remove_worker_path(worker_path: str) -> None:
    """Remove the worker path directory and its contents."""
    if os.path.isdir(worker_path):
        shutil.rmtree(worker_path)

def _get_ppa_mp(args):
    return get_ppa(*args)


def get_ppa_multiprocess(
    rtl_path: Union[str, Sequence[str]],
    target_delays: Iterable[int],
    worker_base_path: Optional[str] = None,
    keep_files: bool = False,
    top_module_name: str = "MUL",
    processes: Optional[int] = None,
    run_verilator: bool = False,
    verilator_tb_path: Optional[str] = None,
    verilator_top_module: Optional[str] = None,
) -> List[dict]:
    """Run multiple get_ppa calls concurrently with different delay targets."""

    delays = list(target_delays)
    if not delays:
        return []

    if worker_base_path:
        os.makedirs(worker_base_path, exist_ok=True)

    args = []
    for delay in delays:
        worker_path = None
        if worker_base_path:
            worker_path = os.path.join(worker_base_path, f"delay_{delay}")
        args.append(
            (
                rtl_path,
                delay,
                worker_path,
                keep_files,
                top_module_name,
                run_verilator,
                verilator_tb_path,
                verilator_top_module,
            )
        )

    with Pool(processes=processes) as pool:
        results = pool.map(_get_ppa_mp, args)

    return results
