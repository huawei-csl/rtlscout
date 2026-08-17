"""Shim: the implementation lives in benchmarks/rtl_rewriter/_tools/augment_vectors.py
(it maintains the benchmark trees, not this run). Kept so run_all.py's
`import augment_vectors; augment_vectors.run()` continues to work, with the
run profile staying authoritative for scale/seed/interpreter."""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rr_config as cfg  # noqa: E402

_impl_path = cfg.REPO / "benchmarks" / "rtl_rewriter" / "_tools" / "augment_vectors.py"
_spec = importlib.util.spec_from_file_location("_augment_vectors_impl", _impl_path)
_impl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_impl)

_impl.VEC_TARGET = cfg.VEC_TARGET
_impl.VEC_SEED = cfg.VEC_SEED
_impl.PYTHON = str(cfg.VENV_PYTHON)

run = _impl.run
materialize_spirehdl_baselines = _impl.materialize_spirehdl_baselines
augment_dir = _impl.augment_dir

if __name__ == "__main__":
    run()
