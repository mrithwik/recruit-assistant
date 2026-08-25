#!/usr/bin/env python3
"""
Thin CLI wrapper — the actual generator lives at
backend/app/dev_tools/sample_data_generator.py, importable from there so the
in-app "Generate Sample Data" feature (Scan Sources tab) can call the exact
same code a backend route uses. This script exists for the command-line
workflow described in HOW_TO_RUN.md.

Usage:
    python scripts/generate_sample_data.py [--out sample_data] [--seed 42]
                                            [--initial 7000] [--followups 2200]
                                            [--upskill 1400]

Requires `make setup` to have been run at least once (editable install makes
`app` importable from anywhere in the venv).
"""

from app.dev_tools.sample_data_generator import main

if __name__ == "__main__":
    main()
