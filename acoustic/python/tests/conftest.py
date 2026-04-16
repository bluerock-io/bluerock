import json
import os
import ctypes
import pytest

# Sensor config written to bluerock-oss.json for smoke tests.
# import + mcp hooks only. expand as more hooks ship.
OSS_SENSOR_CONFIG = {
    "enable": True,
    "imports": {"enable": True, "fileslist": True},
    "mcp": True,
}


@pytest.fixture(scope="session")
def acoustic_oss_dso():
    """Load the acoustic-oss shared library.

    Resolution order:
      1. ACOUSTIC_OSS_DSO env var (CI / manual override)
      2. Installed bluerock-oss package (pip install bluerock-oss)
    """
    dso_path = os.environ.get("ACOUSTIC_OSS_DSO")
    if not dso_path:
        try:
            import bluerock_oss

            dso_path = bluerock_oss.get_dso_path()
        except (ImportError, RuntimeError):
            pytest.skip("ACOUSTIC_OSS_DSO not set and bluerock-oss not installed")
    if not os.path.isfile(dso_path):
        pytest.skip(f"DSO not found at {dso_path}")
    return ctypes.CDLL(dso_path)


@pytest.fixture(scope="session")
def acoustic_oss_initialized(acoustic_oss_dso, tmp_path_factory):
    """Initialize the DSO with a bluerock-oss.json sensor config.

    Creates a temp directory containing bluerock-oss.json, then calls
    acoustic_init_forksafe with metadata pointing to that directory.
    OnceLock ensures the config is set exactly once per process.
    """
    config_dir = tmp_path_factory.mktemp("oss_config")
    (config_dir / "bluerock-oss.json").write_text(json.dumps(OSS_SENSOR_CONFIG))

    init_fn = acoustic_oss_dso.acoustic_init_forksafe
    init_fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    init_fn.restype = ctypes.c_int

    metadata = json.dumps({"sensor_type": "Python", "config_dir": str(config_dir)}).encode("utf-8")
    result = init_fn(b"/tmp/sensor.sock", metadata)
    assert result == 0, f"acoustic_init_forksafe returned {result}"

    return acoustic_oss_dso
