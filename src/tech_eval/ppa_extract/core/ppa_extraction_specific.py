import os
from multiprocessing import Pool
import secrets
from enum import Enum
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from tech_eval.int_tb_sim import run_component_with_vectors
from tech_eval.ppa_extract.core.ppa_configs import InstanceConfig
from tech_eval.ppa_extract.core.ppa_extraction import get_ppa, remove_worker_path
from spirehdl.spirehdl_module import Module, Component
from spirehdl.helpers import get_yosys_metrics, refactor_module_to_aig

from spirehdl.helpers import sim_and_switch_count

# if TYPE_CHECKING:
#     from tech_eval.ppa_extract.ppa_extraction_mp_plot_exended import AdderConfig, MultConfig


def _try_get_export_value(cfg: Any, attr_path: str) -> Any:
    try:
        value = attrgetter(attr_path)(cfg)
    except AttributeError:
        return None
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.name
    return getattr(value, "__name__", str(value))


def _inject_marked_config_fields(res: Dict[str, Any], cfg: Any) -> None:
    export_map = getattr(cfg, "json_export_fields", None)
    if not isinstance(export_map, dict):
        return

    for attr_path, out_key in export_map.items():
        if not isinstance(attr_path, str) or not isinstance(out_key, str):
            continue
        value = _try_get_export_value(cfg, attr_path)
        res[out_key] = value


def _worker_settings() -> Tuple[str, str, str]:
    prefix = "ppa_worker_"
    rtl_filename = "design.v"
    design_prefix = "Design"
    return prefix, rtl_filename, design_prefix


def _build_args(
    configs: Sequence[Any],
    delays: Sequence[int],
    worker_base_path: Optional[str],
    keep_files: bool,
    vectors: Optional[List[Any]] = None,
    save_vcd: bool = True,
    technology: str = "asap7",
) -> List[Tuple[Any, int, Optional[str], bool, Optional[List[Any]], bool, str]]:
    return [
        (config, delay, worker_base_path, keep_files, vectors, save_vcd, technology) for config in configs for delay in delays
    ]


def _run_single(
    config: Any,
    delay: int,
    worker_base_path: Optional[str],
    keep_files: bool,
    vectors: Optional[List[Any]],
    save_vcd: bool = False,
    technology: str = "asap7",
) -> Dict[str, Union[str, int, float, bool, Any]]:
    config: InstanceConfig

    import tempfile

    worker_prefix, rtl_filename, design_prefix = _worker_settings()
    #combo_name = combo_name(config, delay=delay) 
    # # or use secrets.token_hex(8), with import secrets
    combo_name = secrets.token_hex(8)

    worker_path = (
        os.path.join(worker_base_path, combo_name)
        if worker_base_path
        else tempfile.mkdtemp(prefix=worker_prefix)
    )

    os.makedirs(worker_path, exist_ok=True)
    
    # generate one instance of the design
    impl : Component = config.gen_instance()
    module = impl.to_module(f"{design_prefix}", with_clock=True)
    
    basic = vectors is None
    if basic:


        rtl_path = os.path.join(worker_path, rtl_filename)
        module.to_verilog_file(rtl_path)
        top_module_name = module.name

        res = get_ppa(
            rtl_path=rtl_path,
            target_delay=delay,
            worker_path=worker_path,
            top_module_name=top_module_name,
            technology=technology,
        )
        
    else:
        
        # convert to aig and do some optimizations on it, optional
        # module = refactor_module_to_aig(module, optimize=True)
        
        sim_result = run_component_with_vectors(
            module.to_component(),
            vectors,
            module_name=module.name,
            tb_from_data=True,
            worker_path=worker_path,
            save_vcd=save_vcd,
        )
        
        
        use_vcd_for_power = save_vcd  # set to True to use VCD for power estimation, False to skip VCD generation and use a placeholder value
        
        res = get_ppa(
            rtl_path=sim_result["verilog_filename"],
            target_delay=delay,
            worker_path=worker_path,
            top_module_name=sim_result["module_name"],
            run_verilator=True,
            tb_filename=sim_result["tb_filename"],
            tb_name=sim_result["tb_name"],
            use_vcd_for_power=use_vcd_for_power,
            save_vcd=use_vcd_for_power,
            technology=technology,
        )
        
        yosys_metrics = get_yosys_metrics(module)
        res['estimated_num_transistors'] = yosys_metrics['estimated_num_transistors']
        
        switches = sim_and_switch_count(module, vectors)
        res['switch_count'] = switches
        

    if not keep_files:
        remove_worker_path(worker_path)

    res["config"] = config
    res["target_delay"] = delay
    res["impl_cls_name"] = getattr(config.impl_cls, "__name__", str(config.impl_cls))

    cfg = config.config
    _inject_marked_config_fields(res, cfg)

    # Backward-compatible fallback for older flat configs
    for attr, key in [("ppa_cls", "ppa_cls_name"), ("fsa_cls", "fsa_cls_name")]:
        if key in res:
            continue
        cls = getattr(cfg, attr, None)
        if cls is not None:
            res[key] = getattr(cls, "__name__", str(cls))

    return res


def _run_single_tuple(
    args: Tuple[Any, int, Optional[str], bool, Optional[List[Any]], bool, str]
) -> Dict[str, Union[str, int, float, bool, Any]]:
    return _run_single(*args)


def run_configs(
    configs: Sequence[Any], # e.g., MultConfig or AdderConfig
    target_delays: Iterable[float],
    worker_base_path: Optional[str],
    keep_files: bool,
    processes: Optional[int],
    vectors: Optional[List[Any]] = None,
    save_vcd: bool = True,
    technology: str = "asap7",
) -> List[Dict]:
    delays = list(target_delays)
    if not delays:
        return []

    configs = list(configs)
    if not configs:
        return []

    if worker_base_path:
        os.makedirs(worker_base_path, exist_ok=True)

    args = _build_args(configs, delays, worker_base_path, keep_files, vectors, save_vcd, technology)

    with Pool(processes=processes) as pool:
        results = pool.map(_run_single_tuple, args)

    return results
