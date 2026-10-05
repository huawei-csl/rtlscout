"""Where rtlscout finds what is not part of the installed package.

The package runs from a source checkout (plain, or ``pip install -e .``) and from site-packages. Nothing in it may
assume that the directory above the package is the repository, so every such lookup goes through this module:

``RTLSCOUT_HOME``            workspace root: holds ``.env``, ``benchmarks/`` and ``deps/``. Default: the checkout the
                             package runs from, else the current directory.
``RTLSCOUT_ENV_FILE``        the ``.env`` with the provider API keys. Default: ``<workspace root>/.env``.
``RTLSCOUT_BENCHMARKS``      benchmark trees. Default: ``<workspace root>/benchmarks`` and, if present,
                             ``<workspace root>/internal/benchmarks``.
``RTLSCOUT_CACHE_DIR``       derived files. Default: ``<checkout>/.cache`` in a checkout, else ``~/.cache/rtlscout``.
``RTLSCOUT_SPIRE_HDL_DIR``   spire-hdl source tree. Default: ``<workspace root>/deps/spire-hdl``, else the tree an
                             editable spire-hdl is installed from.

``RTLSCOUT_BENCHMARKS`` holds one or more roots separated by ``os.pathsep``. A checkout needs none of the
variables: its defaults are the paths that were hard-wired before the package was installable.
"""

import importlib.util
import os
from pathlib import Path
from typing import List, Optional

_PACKAGE_DIR = Path(__file__).resolve().parent

#: Benchmarks shipped inside the package, so a fake-model smoke run needs no benchmark tree.
SMOKE_BENCHMARKS_ROOT = _PACKAGE_DIR / "smoke_benchmarks"

#: What to tell the user when a Spire flow needs the spire-hdl source tree and :func:`spire_hdl_root` found none.
SPIRE_HDL_MISSING = (
    "Spire HDL prompts quote the spire-hdl documentation and examples, which are not part of the spire-hdl wheel. "
    "Run from an rtlscout checkout with the deps/spire-hdl submodule, or set RTLSCOUT_SPIRE_HDL_DIR to a spire-hdl "
    "source tree of the installed version (https://github.com/huawei-csl/spire-hdl).")

#: The devcontainer mounts the checkout here; its .env is the last place looked at.
_DEVCONTAINER_ENV_FILE = Path("/workspaces/rtl_scout/.env")


def _env_path(name: str) -> Optional[Path]:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else None


def source_checkout() -> Optional[Path]:
    """The repository the package is running from (plain checkout or editable install), else None."""
    root = _PACKAGE_DIR.parent
    return root if (root / "pyproject.toml").is_file() else None


def workspace_root() -> Path:
    """The directory that holds ``.env``, ``benchmarks/`` and ``deps/``, and that container sandboxes mount."""
    return _env_path("RTLSCOUT_HOME") or source_checkout() or Path.cwd()


def env_file() -> Optional[Path]:
    """The ``.env`` to load, or None if there is none."""
    explicit = _env_path("RTLSCOUT_ENV_FILE")
    if explicit is not None:
        if not explicit.is_file():
            raise FileNotFoundError(f"RTLSCOUT_ENV_FILE points at {explicit}, which does not exist")
        return explicit
    for candidate in (workspace_root() / ".env", _DEVCONTAINER_ENV_FILE):
        if candidate.is_file():
            return candidate
    return None


def load_env() -> Optional[Path]:
    """Load the provider keys from :func:`env_file` into the environment; returns the file used."""
    from dotenv import load_dotenv
    path = env_file()
    if path is not None:
        load_dotenv(path)
    return path


def benchmark_roots() -> List[Path]:
    """The benchmark trees scanned when no ``--benchmarks-root`` is given.

    The packaged smoke set is added only for benchmarks that no other root provides, so a checkout scans exactly
    its own ``benchmarks/`` (and ``internal/benchmarks/``) as before.
    """
    value = os.environ.get("RTLSCOUT_BENCHMARKS")
    if value:
        roots = [Path(p).expanduser().resolve() for p in value.split(os.pathsep) if p]
        missing = [str(r) for r in roots if not r.is_dir()]
        if missing:
            raise FileNotFoundError(f"RTLSCOUT_BENCHMARKS: no such directory: {', '.join(missing)}")
    else:
        root = workspace_root()
        roots = [d for d in (root / "benchmarks", root / "internal" / "benchmarks") if d.is_dir()]
    smoke = [d.name for d in sorted(SMOKE_BENCHMARKS_ROOT.iterdir()) if (d / "metadata.json").is_file()]
    if any(not any((r / name / "metadata.json").is_file() for r in roots) for name in smoke):
        roots.append(SMOKE_BENCHMARKS_ROOT)
    return roots


def cache_dir() -> Path:
    """Directory for derived files that are expensive to rebuild (e.g. the merged ASAP7 liberty)."""
    explicit = _env_path("RTLSCOUT_CACHE_DIR")
    if explicit is not None:
        return explicit
    checkout = source_checkout()
    return checkout / ".cache" if checkout is not None else Path.home() / ".cache" / "rtlscout"


def spire_hdl_root() -> Optional[Path]:
    """The spire-hdl *source tree* (``docs/``, ``testing/``, ``src/spire/``), or None.

    The Spire prompts quote its documentation and examples, which the spire-hdl wheel does not ship. A plain
    ``pip install spire-hdl`` is therefore enough for every Verilog and Amaranth flow, but not for a Spire run.
    """
    explicit = _env_path("RTLSCOUT_SPIRE_HDL_DIR")
    if explicit is not None:
        if not (explicit / "docs").is_dir():
            raise FileNotFoundError(f"RTLSCOUT_SPIRE_HDL_DIR points at {explicit}, which has no docs/ directory")
        return explicit
    submodule = workspace_root() / "deps" / "spire-hdl"
    if (submodule / "docs").is_dir():
        return submodule
    spec = importlib.util.find_spec("spire")
    if spec is not None and spec.origin:            # editable install: <tree>/src/spire/__init__.py
        tree = Path(spec.origin).resolve().parents[2]
        if (tree / "docs" / "hints.md").is_file():
            return tree
    return None
