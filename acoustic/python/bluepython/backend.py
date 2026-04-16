# Copyright (C) 2025 BlueRock Security, Inc.
# All rights reserved.

import copy
import ctypes
import json
import os
import platform
import signal
import sys
import time
import threading
import traceback
from pathlib import Path
import uuid
from . import cfg

FORK_SAFE = True


# Either get the component ID from BRace or generate a new one.
def get_component_id():
    env = os.environ.get("BRU_COMPONENT_ID")
    if env:
        return uuid.UUID(env)
    return uuid.uuid4()


component_id = str(get_component_id())


# Yields incrementing integers in a thread-safe way.
def atomic_range():
    n = 1
    lock = threading.Lock()

    while True:
        with lock:
            cur = n
            n += 1
        yield cur


source_event_id_iter = atomic_range()


# Exception that is raised when a "block" remediation happens.
class Remediation(Exception):
    pass


# Exception that is raised when a "modify" remediation happens.
class ModifyRemediation(Exception):
    def __init__(self, modification):
        super().__init__()

        self.modification = modification


# Compose an event in a Gyro-compatible format.
def compose_event(name, attrs=None, *, actionable=True):
    event_type = "event" if actionable else "nonactionable"
    evt = {
        "meta": {
            "name": "python_" + name,
            "type": event_type,
            "origin": "bluepython",
            "sensor_id": acousticBackend.sensor_id,
            "source_event_id": next(source_event_id_iter),
            "uuid": component_id,
        },
        "context": {
            "process": {
                "pid": os.getpid(),
            }
        },
    }
    if name in {"trace_module", "trace_function"}:
        evt["context"]["runtime"] = {
            "name": platform.python_implementation(),
            "version": platform.python_version(),
        }
    if attrs is not None:
        evt.update(attrs)
    return evt


# Acoustic errors.
ACOUSTIC_UNINITIALIZED = 1
ACOUSTIC_INVALID_ARGS = 2
ACOUSTIC_GYRO_FAILURE = 3
ACOUSTIC_IO_ERROR = 4

# Acoustic log levels.
ACOUSTIC_LOG_TRACE = 0
ACOUSTIC_LOG_DEBUG = 1
ACOUSTIC_LOG_INFO = 2
ACOUSTIC_LOG_WARN = 3
ACOUSTIC_LOG_ERROR = 4

# Sensor remediations.
ACOUSTIC_REMEDIATE_NONE = 0
ACOUSTIC_REMEDIATE_BLOCK = 1
ACOUSTIC_REMEDIATE_MODIFY = 2

HandleConfigUpdateFn = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_ubyte),
    ctypes.c_ulong,
)

HandlePolicyRevokedFn = ctypes.CFUNCTYPE(None)


# Helper class that provides an ergonomic wrapper around libacoustic.so.
class AcousticLib:
    __slots__ = (
        "_acoustic_tracing_stderr",
        "_acoustic_tracing_file",
        "_acoustic_tracing_log",
        "_acoustic_init",
        "_acoustic_init_forksafe",
        "_acoustic_reset",
        "_acoustic_run",
        "_acoustic_poll",
        "_acoustic_event",
        "_acoustic_get_sensor_id",
        "_acoustic_get_sensor_config",
        "_acoustic_last_error_msg",
        "_acoustic_last_sensor_config",
        "_acoustic_last_modification",
    )

    def __init__(self, *, oss):
        dso_path = os.path.join(cfg.config.acoustic_dso, "libacoustic.so")
        if oss:
            import bluerock_oss

            dso_path = bluerock_oss.get_dso_path()
        cdll = ctypes.CDLL(dso_path)

        self._acoustic_tracing_stderr = cdll["acoustic_tracing_stderr"]
        self._acoustic_tracing_stderr.argtypes = []
        self._acoustic_tracing_stderr.restype = ctypes.c_int

        self._acoustic_tracing_file = cdll["acoustic_tracing_file"]
        self._acoustic_tracing_file.argtypes = [ctypes.c_char_p]
        self._acoustic_tracing_file.restype = ctypes.c_int

        self._acoustic_tracing_log = cdll["acoustic_tracing_log"]
        self._acoustic_tracing_log.argtypes = [ctypes.c_int, ctypes.c_char_p]
        self._acoustic_tracing_log.restype = ctypes.c_int

        self._acoustic_init = cdll["acoustic_init"]
        self._acoustic_init.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self._acoustic_init.restype = ctypes.c_int

        self._acoustic_init_forksafe = cdll["acoustic_init_forksafe"]
        self._acoustic_init_forksafe.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self._acoustic_init_forksafe.restype = ctypes.c_int

        self._acoustic_reset = cdll["acoustic_reset"]
        self._acoustic_reset.argtypes = []
        self._acoustic_reset.restype = ctypes.c_int

        self._acoustic_run = cdll["acoustic_run"]
        self._acoustic_run.argtypes = [HandleConfigUpdateFn, HandlePolicyRevokedFn]
        self._acoustic_run.restype = ctypes.c_int

        self._acoustic_poll = cdll["acoustic_poll"]
        self._acoustic_poll.argtypes = [HandleConfigUpdateFn, HandlePolicyRevokedFn]
        self._acoustic_poll.restype = ctypes.c_int

        self._acoustic_event = cdll["acoustic_event"]
        self._acoustic_event.argtypes = [ctypes.c_char_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_int)]
        self._acoustic_event.restype = ctypes.c_int

        self._acoustic_get_sensor_id = cdll["acoustic_get_sensor_id"]
        self._acoustic_get_sensor_id.argtypes = [ctypes.POINTER(ctypes.c_uint64)]
        self._acoustic_get_sensor_id.restype = ctypes.c_int

        self._acoustic_get_sensor_config = cdll["acoustic_get_sensor_config"]
        self._acoustic_get_sensor_config.argtypes = []
        self._acoustic_get_sensor_config.restype = ctypes.c_int

        self._acoustic_last_error_msg = cdll["acoustic_last_error_msg"]
        self._acoustic_last_error_msg.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
        self._acoustic_last_error_msg.restype = None

        self._acoustic_last_sensor_config = cdll["acoustic_last_sensor_config"]
        self._acoustic_last_sensor_config.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
        self._acoustic_last_sensor_config.restype = None

        self._acoustic_last_modification = cdll["acoustic_last_modification"]
        self._acoustic_last_modification.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
        self._acoustic_last_modification.restype = None

    def tracing_stderr(self):
        res = self._acoustic_tracing_stderr()
        if res:
            msg = self._last_error_msg()
            raise RuntimeError(f"Failed to set up tracing to stderr (code {res}): {msg}")

    def tracing_file(self, path):
        res = self._acoustic_tracing_file(path.encode("utf-8"))
        if res:
            msg = self._last_error_msg()
            raise RuntimeError(f"Failed to set up tracing to file (code {res}): {msg}")

    def tracing_log(self, level, msg):
        res = self._acoustic_tracing_log(level, msg)
        if res:
            msg = self._last_error_msg()
            raise RuntimeError(f"Failed to log tracing message (code {res}): {msg}")

    def init(self):

        sensor_path = os.path.join(cfg.config.acoustic_socket, "sensor.sock").encode("utf-8")
        metadata = json.dumps(
            {
                "sensor_type": "Python",
                "config_dir": cfg.config.cfg_dir,
            }
        ).encode("utf-8")

        # Retry logic for connection issues (e.g., "Connection reset by peer")
        delay = 1  # 1s delay between attempts
        max_retries = cfg.config.timeout  # / delay
        for attempt in range(max_retries):
            try:
                if FORK_SAFE:
                    res = self._acoustic_init_forksafe(sensor_path, metadata)
                else:
                    res = self._acoustic_init(sensor_path, metadata)
                if res:
                    msg = self._last_error_msg()
                    # Only retry on connection-related errors (code 4 = ACOUSTIC_IO_ERROR)
                    if res == ACOUSTIC_IO_ERROR and attempt < max_retries - 1:
                        time.sleep(delay)
                        continue
                    raise RuntimeError(f"Failed to initialize libacoustic (code {res}): {msg}")
                break  # Success, exit retry loop
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(delay)
                else:
                    print(
                        f"libacoustic initialization exception {e}. Failed after {max_retries} attempts.",
                        file=sys.stderr,
                    )
                    raise

    def reset(self):
        res = self._acoustic_reset()
        if res:
            msg = self._last_error_msg()
            raise RuntimeError(f"Failed to reset libacoustic (code {res}): {msg}")

    def run(self, *, handle_config_update, handle_policy_revoked):
        def handle_config_update_trampoline(ptr, size):
            buffer = ctypes.string_at(ptr, size)
            return handle_config_update(json.loads(buffer))

        res = self._acoustic_run(
            HandleConfigUpdateFn(handle_config_update_trampoline),
            HandlePolicyRevokedFn(handle_policy_revoked),
        )
        if res:
            msg = self._last_error_msg()
            raise RuntimeError(f"Failed to run libacoustic engine (code {res}): {msg}")

    def poll(self, *, handle_config_update, handle_policy_revoked):
        def handle_config_update_trampoline(ptr, size):
            buffer = ctypes.string_at(ptr, size)
            return handle_config_update(json.loads(buffer))

        res = self._acoustic_poll(
            HandleConfigUpdateFn(handle_config_update_trampoline),
            HandlePolicyRevokedFn(handle_policy_revoked),
        )
        if res:
            msg = self._last_error_msg()
            raise RuntimeError(f"Failed to poll libacoustic engine (code {res}): {msg}")

    def event(self, evt):
        in_str = json.dumps(evt).encode("utf8")
        block_event = ctypes.c_int()
        res = self._acoustic_event(in_str, len(in_str), ctypes.byref(block_event))
        if res:
            msg = self._last_error_msg()
            raise RuntimeError(f"Failed to emit event using libacoustic (code {res}): {msg}")
        modification = None
        if block_event.value == ACOUSTIC_REMEDIATE_MODIFY:
            modification = json.loads(self._last_modification())
        return block_event.value, modification

    def get_sensor_id(self):
        sensor_id = ctypes.c_uint64()
        res = self._acoustic_get_sensor_id(ctypes.byref(sensor_id))
        if res:
            msg = self._last_error_msg()
            raise RuntimeError(f"Failed to obtain sensor id from libacoustic (code {res}): {msg}")
        return sensor_id.value

    def get_sensor_config(self):
        res = self._acoustic_get_sensor_config()
        if res:
            msg = self._last_error_msg()
            raise RuntimeError(f"Failed to obtain sensor config from libacoustic (code {res}): {msg}")
        return json.loads(self._last_sensor_config())

    def _last_error_msg(self):
        ptr = ctypes.c_char_p()
        self._acoustic_last_error_msg(ctypes.byref(ptr))
        if not ptr:
            return None
        return ctypes.string_at(ptr).decode("utf8")

    def _last_sensor_config(self):
        ptr = ctypes.c_char_p()
        self._acoustic_last_sensor_config(ctypes.byref(ptr))
        if not ptr:
            return None
        return ctypes.string_at(ptr).decode("utf8")

    def _last_modification(self):
        ptr = ctypes.c_char_p()
        self._acoustic_last_modification(ctypes.byref(ptr))
        if not ptr:
            return None
        return ctypes.string_at(ptr).decode("utf8")


class AcousticBackend:
    __slots__ = ("_lib", "_thread", "sensor_id")

    def __init__(self):
        self._lib = AcousticLib(oss=cfg.config.oss)
        self._lib.init()

        self.sensor_id = self._lib.get_sensor_id()

        config_obj = self._lib.get_sensor_config()
        cfg.sensor_config.load(config_obj)

        if not FORK_SAFE:
            self._thread = threading.Thread(target=self._run)
            self._thread.daemon = True
            self._thread.start()

        self._lifecycle_startup()

    def reset(self):
        self._lib.reset()

    def emit_event(self, evt):
        sensor_remediation, modification = self._lib.event(evt)
        if sensor_remediation:
            if sensor_remediation == ACOUSTIC_REMEDIATE_MODIFY:
                raise ModifyRemediation(modification)
            raise Remediation()

    def tracing_stderr(self):
        self._lib.tracing_stderr()

    def tracing_file(self, path):
        self._lib.tracing_file(path)

    def tracing_log(self, level, msg):
        self._lib.tracing_log(level, msg.encode("utf-8"))

    def _handle_policy_revoked(self):
        print(
            "Policy revoked by server. The currently selected policy may have been removed by a policy update. Terminating.",
            file=sys.stderr,
        )
        signal.raise_signal(signal.SIGKILL)

    def _run(self):
        self._lib.run(
            handle_config_update=self._handle_config_update,
            handle_policy_revoked=self._handle_policy_revoked,
        )

    def poll(self):
        if not FORK_SAFE:
            return
        self._lib.poll(
            handle_config_update=self._handle_config_update,
            handle_policy_revoked=self._handle_policy_revoked,
        )

    def _lifecycle_startup(self):
        evt = {
            "meta": {
                "name": "sensor_startup",
                "type": "sensor_lifecycle",
                "origin": "bluepython",
                "sensor_id": self.sensor_id,
                "source_event_id": 0,
                "uuid": component_id,
            },
            "pid": os.getpid(),
            "file_path": sys.argv[0],
        }
        self.emit_event(evt)

    def _handle_config_update(self, config_obj):
        try:
            cfg.sensor_config.load(config_obj)
        except Exception:
            return ACOUSTIC_IO_ERROR
        return 0


# Helper class to emit debugging logs (to stderr).
class DebugLogging:
    __slots__ = ("enable",)

    def __init__(self):
        self.enable = False

    def emit(self, level, msg):
        if not self.enable:
            return
        if not acousticBackend:
            return
        acousticBackend.tracing_log(level, msg)


# This is configured by the initialization code before instrumented code runs.
acousticBackend = None
debugLogging = DebugLogging()


def reset_after_fork():
    if not acousticBackend:
        return
    acousticBackend.reset()


os.register_at_fork(after_in_child=reset_after_fork)


def to_str_recursive(data):
    if isinstance(data, dict):
        return {k: to_str_recursive(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [to_str_recursive(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(to_str_recursive(item) for item in data)
    elif isinstance(data, Path):
        return str(data)
    elif isinstance(data, bytes):
        # if we are given a byte array, decode it.
        return data.decode(errors="backslashreplace")
    else:
        return data


def to_bytes_recursive(data):
    if isinstance(data, dict):
        return {k: to_bytes_recursive(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [to_bytes_recursive(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(to_bytes_recursive(item) for item in data)
    elif isinstance(data, str):
        return data.encode(errors="backslashreplace")
    else:
        return data


def emit_event(name, attrs=None):
    if not acousticBackend:
        print("bluepython is not initialized properly", file=sys.stderr)
        signal.raise_signal(signal.SIGKILL)

    # Note: PrePostWrapper already calls into poll().
    # TODO: We can remove this call if we add it to all callers (other than PrePostWrapper).
    acousticBackend.poll()

    evt = compose_event(name, to_str_recursive(attrs))

    try:
        acousticBackend.emit_event(evt)
    except ModifyRemediation as e:
        confirmation = {
            "meta": copy.deepcopy(evt["meta"]),
            "stack": [],
        }
        confirmation["meta"]["type"] = "block_confirmation"
        confirmation["modification"] = e.modification

        stack = traceback.extract_stack()
        for frame in stack:
            confirmation["stack"].append(
                {
                    "file": frame.filename,
                    "line": frame.lineno,
                    "function": frame.name,
                }
            )

        acousticBackend.emit_event(confirmation)

        raise
    except Remediation:
        confirmation = {
            "meta": copy.deepcopy(evt["meta"]),
            "stack": [],
        }
        confirmation["meta"]["type"] = "block_confirmation"

        stack = traceback.extract_stack()
        for frame in stack:
            confirmation["stack"].append(
                {
                    "file": frame.filename,
                    "line": frame.lineno,
                    "function": frame.name,
                }
            )

        acousticBackend.emit_event(confirmation)

        raise


def emit_info_event(name, attrs=None):
    if not acousticBackend:
        print("bluepython is not initialized properly", file=sys.stderr)
        signal.raise_signal(signal.SIGKILL)

    # Note: PrePostWrapper already calls into poll().
    # TODO: We can remove this call if we add it to all callers (other than PrePostWrapper).
    acousticBackend.poll()

    evt = compose_event(name, to_str_recursive(attrs), actionable=False)

    try:
        acousticBackend.emit_event(evt)
    except Exception as e:
        exception(e)


def want_debug():
    return debugLogging.enable


def debug(msg):
    debugLogging.emit(ACOUSTIC_LOG_DEBUG, msg)


def error(msg):
    debugLogging.emit(ACOUSTIC_LOG_ERROR, msg)


def warning(msg):
    debugLogging.emit(ACOUSTIC_LOG_WARN, msg)


def exception(e):
    # In Python 3.10+, format_exception accepts a single exception object
    # In older versions, it requires type, value, and traceback. Newer versions
    # of python also accept the old calling convention
    tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    error("Exception in instrumentation:\n" + tb)
    emit_event("internal_exception", {"type": repr(type(e))})
