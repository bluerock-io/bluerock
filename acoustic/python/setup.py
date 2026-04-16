# Copyright (C) 2025 BlueRock Security, Inc.
# Licensed under the Apache License, Version 2.0 (see LICENSE at the
# repo root). PEP 517 build metadata lives in pyproject.toml; this
# shim only exists so the project remains installable via tools that
# still reach for setup.py directly.

from setuptools import setup

if __name__ == "__main__":
    setup()
