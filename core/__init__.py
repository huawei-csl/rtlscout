"""Deprecated alias of the ``rtlscout`` package, which was called ``core`` before 0.2.0.

Importing a submodule through this name returns the very same module object as importing it from ``rtlscout``
(no second copy, so classes and registries stay shared), and ``python -m`` works through it too. The alias is kept
for one release; new code imports ``rtlscout``.
"""

import importlib
import importlib.abc
import importlib.util
import sys
import warnings

_NEW = "rtlscout"

warnings.warn(f"the '{__name__}' package was renamed to '{_NEW}'; '{__name__}' is a compatibility alias that will be "
              "removed in the next release", DeprecationWarning, stacklevel=2)


class _AliasFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Maps ``<old>.<x>`` onto the module ``<new>.<x>``."""

    def __init__(self):
        self._specs = {}

    @staticmethod
    def _target(fullname):
        return _NEW + fullname[len(__name__):]

    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(__name__ + "."):
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def create_module(self, spec):
        module = importlib.import_module(self._target(spec.name))
        self._specs[spec.name] = module.__spec__    # the import system overwrites __spec__ with the alias spec
        return module

    def exec_module(self, module):
        for alias, real_spec in list(self._specs.items()):
            if sys.modules.get(alias) is module:
                module.__spec__ = real_spec
                del self._specs[alias]

    def get_code(self, fullname):                   # `python -m <old>.<x>`
        real_spec = importlib.util.find_spec(self._target(fullname))
        return real_spec.loader.get_code(real_spec.name)


sys.meta_path.insert(0, _AliasFinder())
