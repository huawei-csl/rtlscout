#!/usr/bin/env python3
"""Wrapper around ``python -m rtlscout.containers``, so this command keeps working from a checkout."""
import sys

from rtlscout.containers import main

if __name__ == "__main__":
    sys.exit(main())
