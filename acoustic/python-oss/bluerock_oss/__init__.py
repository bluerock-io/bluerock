# Copyright (C) 2026 BlueRock Security, Inc.
# All rights reserved.

import importlib.machinery
import os


def get_dso_path():
    pkg_dir = os.path.dirname(__file__)
    for suffix in importlib.machinery.EXTENSION_SUFFIXES:
        dso_path = os.path.join(pkg_dir, "libacoustic_oss" + suffix)
        if os.path.isfile(dso_path):
            return dso_path
    raise RuntimeError("libacoustic_oss shared library not found")
