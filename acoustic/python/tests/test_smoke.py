"""Smoke tests for acoustic-oss DSO integration via ctypes."""

import ctypes
import json
import os


def test_dso_loads(acoustic_oss_dso):
    assert acoustic_oss_dso is not None


def test_tracing_stderr(acoustic_oss_dso):
    func = acoustic_oss_dso.acoustic_tracing_stderr
    func.restype = ctypes.c_int
    assert func() == 0


def test_event_call(acoustic_oss_dso):
    os.makedirs(os.path.join(os.path.expanduser("~"), ".bluerock", "event-spool"), exist_ok=True)
    func = acoustic_oss_dso.acoustic_event
    func.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_int)]
    func.restype = ctypes.c_int
    payload = b'{"type":"test","data":"staging-smoke"}'
    block = ctypes.c_int(0)
    result = func(payload, len(payload), ctypes.byref(block))
    assert result == 0, f"acoustic_event returned {result}"


def test_get_sensor_config(acoustic_oss_initialized):
    """Verify sensor config JSON includes expected feature keys.

    Requires acoustic_oss_initialized because sensor config is now loaded
    from bluerock-oss.json during acoustic_init (not hardcoded).
    """
    dso = acoustic_oss_initialized
    func = dso.acoustic_get_sensor_config
    func.restype = ctypes.c_int
    assert func() == 0

    ptr = ctypes.c_char_p()
    dso.acoustic_last_sensor_config(ctypes.byref(ptr))
    config = json.loads(ctypes.string_at(ptr).decode("utf-8"))

    assert config["enable"] is True
    assert config["mcp"] is True
    # imports is a nested config object, not a plain boolean
    assert "imports" in config, "missing sensor config key: imports"
    assert config["imports"]["enable"] is True


def test_get_sensor_id(acoustic_oss_dso):
    """Verify acoustic_get_sensor_id returns success and a non-zero ID."""
    sensor_id = ctypes.c_uint64()
    func = acoustic_oss_dso.acoustic_get_sensor_id
    func.argtypes = [ctypes.POINTER(ctypes.c_uint64)]
    func.restype = ctypes.c_int
    assert func(ctypes.byref(sensor_id)) == 0
    assert sensor_id.value != 0, "sensor_id should be non-zero"


def test_init_reset_cycle(acoustic_oss_dso):
    """Verify acoustic_init + acoustic_reset completes without error."""
    init_fn = acoustic_oss_dso.acoustic_init
    init_fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    init_fn.restype = ctypes.c_int
    assert init_fn(b"/tmp/sensor.sock", b'{"sensor_type":"test"}') == 0

    reset_fn = acoustic_oss_dso.acoustic_reset
    reset_fn.argtypes = []
    reset_fn.restype = ctypes.c_int
    assert reset_fn() == 0
