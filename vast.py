#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

"""Backward-compatibility shim. All logic now lives in the vast_cli package."""

from vast_cli.main import main

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        pass
