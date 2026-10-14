#!/usr/bin/env python3
"""Wrapper around ``python -m rtlscout.extract_pareto``, so this command keeps working from a checkout."""
from rtlscout.extract_pareto import *  # noqa: F401,F403
from rtlscout.extract_pareto import (  # noqa: F401  (names `import *` does not export)
    _find_local_deps, _normalized_score, _select_top_n, _uses_flowy, main)

if __name__ == "__main__":
    main()
