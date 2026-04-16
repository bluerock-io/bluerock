# Copyright (C) 2025 BlueRock Security, Inc.
# All rights reserved.

import argparse
import enum
import json
import os
from pathlib import Path
import re
import string
import sys

from . import cfg

BRU_BEGIN = "\n# BEGIN bluepython\n"
BRU_END = "\n# END bluepython\n"

BRU_PTH_TEMPLATE = "import bluepython.common; bluepython.common.auto_setup(cfg_path=${cfg_path})\n"

BRU_SITECUSTOMIZE = BRU_BEGIN + """
# Copyright (C) 2025 BlueRock Security, Inc.
# All rights reserved.
try:
    import bluepython
    from bluepython import common
except ImportError:
    import sys

    print("Failed to import bluepython", file=sys.stderr)
    exit(1)
else:
    bluepython.common.auto_setup()
""" + BRU_END

# Version of the running Python interpreter. Part of the site-packages/ path.
PYTHON_VERSION = str(sys.version_info[0]) + "." + str(sys.version_info[1])

# .pth file installed by us.
# Note that the .pth mechanism supports venvs and the installation is currently per venv.
PTH_PATH = sys.exec_prefix + "/lib/python" + PYTHON_VERSION + "/site-packages/bluepython.pth"

# Debian / Ubuntu provide a sitecustomize module in /usr/lib/pythonX.Y/.
# Note that since the sitecustomize modile is in a global library directory,
# it is not overriden per venv (and we use sys.base_prefix, not sys.exec_prefix here).
# TODO: We currently only support the Debian / Ubuntu location.
#       It would be possible to chose the sitecustomize.py location in a smarter way to support more distros
#       (e.g., by searching for an existing sitecustomize module in the Python search path).
SITECUSTOMIZE_LINK = sys.base_prefix + "/lib/python" + PYTHON_VERSION + "/sitecustomize.py"

# On Debian / Ubuntu, SITECUSTIMIZE_LINK points to this path.
SITECUSTOMIZE_PATH = "/etc/python" + PYTHON_VERSION + "/sitecustomize.py"

# Determine the path to the config file.
# Outside of a venv, we pick the default config path (which is in /etc).
# In a venv, we pick the base directory of the venv.
CFG_PATH_OVERRIDE = None
if sys.exec_prefix != sys.base_exec_prefix:
    CFG_PATH_OVERRIDE = sys.exec_prefix + "/bluepython.cfg"


class Method(enum.Enum):
    PTH = 1
    SITECUSTOMIZE = 2


def is_bru_installed():
    if is_bru_pth_installed():
        return True

    if not os.path.exists(SITECUSTOMIZE_PATH):
        return False

    data = ""
    with open(SITECUSTOMIZE_PATH, mode="r") as sitecustomize:
        data = sitecustomize.read()

    return is_bru_sitecustomize_installed(data)


def is_bru_sitecustomize_installed(old_sc):
    return BRU_BEGIN in old_sc


def is_bru_pth_installed():
    return os.path.exists(PTH_PATH)


def determine_sitecustomize_support():
    # sitecustomize.py is not supported inside venvs.
    if sys.exec_prefix != sys.base_exec_prefix:
        return False

    if not os.path.islink(SITECUSTOMIZE_LINK):
        print(f"Detected no {SITECUSTOMIZE_LINK} symlink as on Debian/Ubuntu")
        return False

    try:
        target = os.readlink(SITECUSTOMIZE_LINK)
    except OSError:
        print(f"Failed to read {SITECUSTOMIZE_PATH} symlink")
        return False

    if target != SITECUSTOMIZE_PATH:
        print(
            f"sitecustomize.py symlink exists but does not point to the expected target:"
            f" {SITECUSTOMIZE_LINK} -> {target}, expected {SITECUSTOMIZE_PATH}"
        )
        return False

    print(f"Detected Debian/Ubuntu-like sitecustomize.py symlink: {SITECUSTOMIZE_LINK} -> {SITECUSTOMIZE_PATH}")
    return True


def install(*, method=None):
    if method is None:
        # Pick one of the installation methods.
        # The default may change in the future.
        if determine_sitecustomize_support():
            method = Method.SITECUSTOMIZE
        else:
            method = Method.PTH

    _install_cfg()
    if method == Method.PTH:
        _install_pth()
    elif method == Method.SITECUSTOMIZE:
        _install_sitecustomize()
    else:
        raise ValueError("Bad method for install()")
    print("BRU Python sensor installed")


def _install_pth():
    print("Performing installation using .pth method")

    template = string.Template(BRU_PTH_TEMPLATE)
    # We must use repr() here since the value will be evaluated by Python when the .pth is read.
    pth_line = template.substitute(
        cfg_path=repr(CFG_PATH_OVERRIDE),
    )
    with open(PTH_PATH, "w") as f:
        f.write(pth_line)


def _install_sitecustomize():
    print("Performing installation using sitecustomize.py method")

    old_data = ""
    try:
        with open(SITECUSTOMIZE_PATH, mode="r") as sitecustomize:
            if sitecustomize is not None:
                old_data = sitecustomize.read()
            if is_bru_sitecustomize_installed(old_data):
                print("BRU Python sensor is already installed")
                return
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Failed to open {SITECUSTOMIZE_PATH}: {e}")
        return

    with open(SITECUSTOMIZE_PATH + ".tmp", mode="w") as sitecustomize_tmp:
        sitecustomize_tmp.write(old_data + BRU_SITECUSTOMIZE)
        Path(sitecustomize_tmp.name).rename(SITECUSTOMIZE_PATH)


def _install_cfg():
    if CFG_PATH_OVERRIDE is not None:
        cfg_path = CFG_PATH_OVERRIDE
    else:
        cfg_path = cfg.CFG_FILE_NAME

    dir = os.path.dirname(cfg_path)
    try:
        os.makedirs(dir, exist_ok=True)
    except Exception as e:
        print(f"Failed to create directories for configuration file: {e}")
        return

    with open(cfg_path, mode="w") as cfg_file:
        cfg_file.write(json.dumps(cfg.config.to_dict(), indent=4))


def uninstall():
    _uninstall_pth()
    _uninstall_sitecustomize()
    _uninstall_cfg()
    print("BRU Python sensor uninstalled")


def _uninstall_pth():
    Path(PTH_PATH).unlink(missing_ok=True)


def _uninstall_sitecustomize():
    data = ""
    with open(SITECUSTOMIZE_PATH, mode="r") as sitecustomize:
        data = sitecustomize.read()
        if not is_bru_sitecustomize_installed(data):
            return

    # remove BRU section
    regex_pattern = re.compile(re.escape(BRU_BEGIN) + r".*?" + re.escape(BRU_END), re.DOTALL)
    data = regex_pattern.sub("", data)
    with open(SITECUSTOMIZE_PATH + ".tmp", mode="w") as sitecustomize_tmp:
        sitecustomize_tmp.write(data)
        Path(sitecustomize_tmp.name).rename(SITECUSTOMIZE_PATH)


def _uninstall_cfg():
    if CFG_PATH_OVERRIDE is not None:
        cfg_path = CFG_PATH_OVERRIDE
    else:
        cfg_path = cfg.CFG_FILE_NAME

    Path(cfg_path).unlink(missing_ok=True)
    cfg_dir = Path(os.path.dirname(cfg_path))
    if not any(cfg_dir.iterdir()):
        cfg_dir.rmdir()


def main():
    parser = _build_parser()
    cfg.add_config_args(parser)
    args = parser.parse_args()
    cfg.load_cfg_from_args(args)

    if args.command == "install":
        method = None
        if args.sitecustomize:
            method = Method.SITECUSTOMIZE
        cfg.config.oss = args.oss
        install(method=method)
    elif args.command == "uninstall":
        uninstall()
    else:
        parser.error(f"invalid command: {args.command}")


def _build_parser():
    parser = argparse.ArgumentParser(prog="python3 -m bluepython.installer")
    sub = parser.add_subparsers(dest="command", required=True)

    install_parser = sub.add_parser("install")
    install_parser.add_argument("--sitecustomize", action="store_true")
    install_parser.add_argument("--oss", action="store_true")

    sub.add_parser("uninstall")

    return parser


if __name__ == "__main__":
    main()
