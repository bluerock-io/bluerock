# Copyright (C) 2025 BlueRock Security, Inc.
# All rights reserved.

import json
import sys
import os
from types import SimpleNamespace

CFG_FILE_NAME = "/etc/bru/bru.cfg"


class Config:
    __slots__ = ("acoustic_dso", "acoustic_socket", "cfg_dir", "instrumentation", "oss", "timeout")

    def __init__(self):
        self.acoustic_dso = "/opt/bluerock/lib/"
        self.acoustic_socket = "/run/bluerock/"
        self.cfg_dir = None
        self.instrumentation = True
        self.oss = False
        self.timeout = 10

    def to_dict(self):
        return {k.replace("_", "-"): getattr(self, k) for k in self.__slots__}

    def __repr__(self):
        return self.to_dict().__repr__()


class CfgOption(SimpleNamespace):
    def __bool__(self):
        is_enabled = getattr(self, "enable", False)
        return is_enabled

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not hasattr(self, "enable"):
            self.enable = False


class SensorConfig:
    # Keep this list sorted to avoid conflicts.
    __slots__ = (
        "enable",
        "a2a",
        "aiohttp",
        "anthropic",
        "crewai",
        "debug",
        "django",
        "execs",
        "flask",
        "gemini",
        "http_requests_monitor",
        "httpx",
        "imports",
        "langchain",
        "litellm",
        "loads",
        "log_file",
        "log_stderr",
        "mcp",
        "openai",
        "opentelemetry",
        "pathjoin",
        "pathtraversal",
        "pickle",
        "profiling",
        "sql_injection",
        "symlink",
        "tracing",
        "urllib",
        "uvicorn",
        "web_server",
        "zip_slip",
    )

    def __init__(self):
        # Disable everything by default.
        self.set_all_to(False)

    def set_all_to(self, b):
        for k in SensorConfig.__slots__:
            setattr(self, k, b)

    def load(self, obj):
        enable = obj.get("enable")
        if not enable:
            self.set_all_to(False)
            return
        for k, v in obj.items():
            if k not in self.__slots__:
                print(f"Config field {k} is not known from the sensor")
                sys.exit(1)
            if isinstance(v, dict):
                sno = CfgOption(**v)
                setattr(self, k, sno)
            else:
                # bool
                setattr(self, k, v)

    def __repr__(self):
        return ", ".join(f"{k}: {getattr(self, k)}" for k in SensorConfig.__slots__)

    def enabled(self, feature) -> bool:
        if self.enable is False:
            return False
        e = getattr(self, feature)
        if e is None:
            return False
        return bool(e)


config = Config()
sensor_config = SensorConfig()


def load_cfg(path):
    if path is None:
        path = CFG_FILE_NAME
    try:
        with open(path, "r") as f:
            allowed = set(k.replace("_", "-") for k in Config.__slots__)
            for k, v in json.load(f).items():
                if k not in allowed:
                    print(f"Key {k} is not allowed in config file")
                    sys.exit(1)
                setattr(config, k.replace("-", "_"), v)
    except OSError as e:
        print(f"Failed to open BRU configuration {path!r}: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Failed to parse BRU configuration: {e}", file=sys.stderr)
        sys.exit(1)
    if config.cfg_dir is None:
        config.cfg_dir = os.path.dirname(os.path.realpath(path))


def add_config_args(parser):
    parser.add_argument("--debug", action="store_true", help="Print debugging logs to stderr")
    parser.add_argument("--acoustic-dso", type=str, help="Directory containing libacoustic.so")
    parser.add_argument("--acoustic-socket", type=str, help="Directory containing sensor.sock")
    parser.add_argument("--oss", action="store_true", help="Use OSS (bluerock_oss) DSO instead of libacoustic.so")
    parser.add_argument("--cfg-dir", type=str, help="Directory containing bluerock-oss.json sensor config")
    parser.add_argument(
        "--tracing-stderr",
        action="store_true",
        help="Enable acoustic tracing to stderr",
    )
    parser.add_argument("--tracing-file", type=str, help="Enable acoustic tracing to a file")


def load_cfg_from_args(args):
    if args.acoustic_dso is not None:
        config.acoustic_dso = os.path.realpath(args.acoustic_dso)
    if args.acoustic_socket is not None:
        config.acoustic_socket = os.path.realpath(args.acoustic_socket)
    if args.oss:
        config.oss = True
    if args.cfg_dir is not None:
        config.cfg_dir = os.path.realpath(args.cfg_dir)
    elif config.oss and config.cfg_dir is None:
        # auto-discover ~/.bluerock/bluerock-oss.json for oss users
        default_oss_dir = os.path.expanduser("~/.bluerock")
        if os.path.exists(os.path.join(default_oss_dir, "bluerock-oss.json")):
            config.cfg_dir = default_oss_dir
