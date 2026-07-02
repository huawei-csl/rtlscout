import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

requires_verilator = pytest.mark.skipif(
    shutil.which("verilator") is None,
    reason="Verilator not installed",
)

requires_yosys = pytest.mark.skipif(
    shutil.which("yosys") is None,
    reason="Yosys not installed",
)

requires_yosys_abc = pytest.mark.skipif(
    shutil.which("yosys-abc") is None,
    reason="yosys-abc not installed",
)

requires_openroad = pytest.mark.skipif(
    shutil.which("openroad") is None,
    reason="OpenROAD not installed (needed for PPA / runtime / adp metrics)",
)

requires_spirehdl = pytest.mark.skipif(
    importlib.util.find_spec("spire") is None,
    reason="spire not installed",
)
