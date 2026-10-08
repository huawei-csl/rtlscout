#!/usr/bin/env python3
"""Wrapper around ``python -m rtlscout.run_pipeline``, so this command keeps working from a checkout."""
from rtlscout.run_pipeline import main

if __name__ == "__main__":
    main()
