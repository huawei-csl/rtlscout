"""RTL Scout: an RTL design agent that creates and optimizes designs against a measured cost metric."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("rtlscout")
except PackageNotFoundError:    # a checkout that was never installed (`pip install -e .`)
    __version__ = "0.0.0+unknown"
