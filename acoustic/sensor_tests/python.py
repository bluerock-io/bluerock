# Copyright (C) 2026 BlueRock Security, Inc.
# All rights reserved.

from ctypes import util
from importlib.metadata import version
import sys

from sensor_tests.common import TestCase, check_for_event


class PythonTestCase(TestCase):
    def __init__(self, name, **kwargs):
        super(PythonTestCase, self).__init__(name, **kwargs)

        self.language = "python"


def check_for_pickle_find_class_exec(events):
    return check_for_event(events, "python_pickle_find_class", {"module": "builtins", "function": "exec"})


def check_for_pickle_find_class_socket(events):
    return check_for_event(events, "python_pickle_find_class", {"module": "socket", "function": "socket"})


def check_for_marshal_code(events):
    return check_for_event(events, "python_marshal_load", {"names": ["getpass", "getuser"]})


def check_dlopen_events(events):
    libc_path = util.find_library("c")
    return check_for_event(events, "python_ctypes_dlopen", {"name": libc_path}) and check_for_event(
        events, "python_ctypes_dlsym", {"library": libc_path, "name": "getpid"}
    )


def check_for_exec(events):
    return check_for_event(
        events, "python_builtins_exec", {"names": ["eval", "exec", "l_not"], "filename": "test_eval.py"}
    )


def check_for_process_events(events):
    all_event_names = [
        "python_os_system",
        "python_os_posix_spawn",
        # currently disabled: "python_os_exec",
        "python_subprocess_Popen",
        # currently disabled: "python_pty_spawn",
    ]
    for e in all_event_names:
        if not check_for_event(events, e, {"exec": "ls"}):
            return False

    return True


def check_import_events(events):
    # Note: urllib3 is a dep of requests
    all_package_names = ["numpy", "requests", "urllib3", "PyYAML"]
    for p in all_package_names:
        if not check_for_event(events, "python_import", {"pkg": p, "version": version(p)}):
            return False

    return True


def check_realod_import_events(events):
    return check_for_event(events, "python_import", {"pkg": "PyYAML", "version": version("PyYAML")})


def check_urllib_events(events):
    return check_for_event(events, "python_urllib_urlopen")


def check_for_pickle_numpy(events):
    # accout for some version differences
    return check_for_event(
        events, "python_pickle_reduce", {"module": "numpy._core.multiarray", "function": "_reconstruct"}
    ) or check_for_event(
        events, "python_pickle_reduce", {"module": "numpy.core.multiarray", "function": "_reconstruct"}
    )


def check_no_unknown_opcode(events):
    return not check_for_event(events, "python_pickle_unknown_opcode")


def check_for_all_path_suspicious(events):
    files = ["/etc/passwd"]
    for file in files:
        if not check_for_event(events, "python_open", {"path": file}):
            return False
        if not check_for_event(events, "python_os_path_normalization_suspicious", {"path": file}):
            return False

    abspaths = ["/absolute1", "/absolute2"]
    for abspath in abspaths:
        if not check_for_event(events, "python_path_join_abs", {"abspath": abspath}):
            return False

    return True


def check_for_url_get(events):
    return check_for_event(
        events,
        "python_url_get",
        {
            "url": {
                "fragment": "",
                "netloc": "",
                "params": "",
                "path": "/static/../../../../../../../../../../../../etc/passwd",
                "query": "query1=/tmp/../../../../../../../../../../../../../../../etc/shadow",
                "scheme": "",
            }
        },
    )


def check_mcp_tool_events(events):
    if not check_for_event(events, "python_mcp_event", {"event": "client_send_request"}):
        return False
    if not check_for_event(events, "python_mcp_event", {"event": "server_received_request"}):
        return False
    if not check_for_event(events, "python_mcp_event", {"event": "server_send_response"}):
        return False
    if not check_for_event(events, "python_mcp_event", {"event": "client_received_response"}):
        return False
    return True


def check_sqlite_event(events):
    return check_for_event(
        events,
        "python_sql_injection",
        {"reason": "WHERE clause trivially evaluates to true", "context": "id = 2 OR 1 = 1"},
    ) and check_for_event(
        events,
        "python_sql_injection",
        {"reason": "WHERE clause trivially evaluates to true", "context": "id = 2 OR true"},
    )


python_test_cases = [
    #### Pickle ####
    # Just check that the fuzzer doesn't crash
    PythonTestCase("pickle_fuzz_bytecode_parser"),
    PythonTestCase("test_pickle_coverage", event_parser=check_no_unknown_opcode),
    PythonTestCase("test_pickle_opcodes", event_parser=check_no_unknown_opcode),
    # These cases invoke remediation behavior (specifics depend on sensor config).
    PythonTestCase("exec_pickle", non_zero_exit=True, event_parser=check_for_pickle_find_class_exec),
    PythonTestCase("pickle_non_seekable", non_zero_exit=True, event_parser=check_for_pickle_find_class_exec),
    # unpickle the socket exfiltration logic by default. Also will fail due to connection refused as expected.
    PythonTestCase("unpickle_file", non_zero_exit=True, event_parser=check_for_pickle_find_class_socket),
    PythonTestCase("test_pickle_memoryview"),
    PythonTestCase("test_scikit_learn", event_parser=check_for_pickle_numpy),
    PythonTestCase("python2/inst_opcode", event_parser=check_no_unknown_opcode),
    PythonTestCase("persid", event_parser=check_no_unknown_opcode),
    PythonTestCase(
        "test_dill",
        extra_deps=["dill"],
        event_parser=lambda events: (
            check_for_event(events, "python_pickle_reduce", {"module": "dill._dill", "function": "_create_code"})
            and check_for_event(
                events, "python_pickle_reduce", {"module": "dill._dill", "function": "_create_function"}
            )
        ),
    ),
    # Check that for malformed pickle data, we still detect events up to the point
    # where we reach a stop opcode.
    PythonTestCase("pickle_early_stop", non_zero_exit=True, event_parser=check_for_pickle_find_class_exec),
    PythonTestCase("test_pathtraversal", extra_flags=["-p"], event_parser=check_for_all_path_suspicious),
    PythonTestCase("test_process", event_parser=check_for_process_events),
    PythonTestCase(
        "test_spawn_python",
        tolerate_internal_exceptions=True,
        event_parser=lambda events: (
            check_for_event(
                events,
                "python_internal_exception",
                {"type": "Spawning a Python process without BluePython installled. Events will be missed."},
            )
        ),
    ),
    PythonTestCase("test_eval", event_parser=check_for_exec),
    PythonTestCase("test_marshal", event_parser=check_for_marshal_code),
    PythonTestCase(
        "test_fork",
        tolerate_internal_exceptions=True,
        event_parser=lambda events: (
            check_for_event(
                events,
                "python_builtins_exec",
                {"names": ["fork_event"]},
            )
            and check_for_event(
                events,
                "python_builtins_exec",
                {"names": ["forkpty_event"]},
            )
        ),
    ),
    PythonTestCase("test_ctypes", event_parser=check_dlopen_events),
    PythonTestCase("test_import", extra_deps=["numpy", "requests", "PyYAML"], event_parser=check_import_events),
    PythonTestCase("test_reload_import", extra_deps=["PyYAML"], event_parser=check_realod_import_events),
    PythonTestCase("test_urllib", event_parser=check_urllib_events),
    PythonTestCase("test_aiohttp", extra_flags=["-p"], event_parser=check_for_url_get),
    PythonTestCase(
        "test_ssrf_aiohttp",
        extra_deps=["aiohttp"],
        event_parser=lambda events: (check_for_event(events, "python_aiohttp_client_request")),
    ),
    PythonTestCase(
        "test_flask_call",
        extra_deps=["flask"],
        event_parser=lambda events: (check_for_event(events, "python_flask_call")),
    ),
    PythonTestCase(
        "test_tar",
        non_zero_exit=True,
        event_parser=lambda events: (check_for_event(events, "python_zip_slip")),
    ),
    PythonTestCase(
        "test_zip",
        non_zero_exit=True,
        event_parser=lambda events: (check_for_event(events, "python_zip_slip")),
    ),
    PythonTestCase(
        "test_py7zr",
        extra_deps=["py7zr"],
        non_zero_exit=True,
        event_parser=lambda events: (check_for_event(events, "python_zip_slip")),
    ),
    PythonTestCase(
        "test_symlink",
        non_zero_exit=True,
        event_parser=lambda events: (check_for_event(events, "python_symlink")),
    ),
    PythonTestCase(
        "test_httpx",
        extra_deps=["httpx"],
        non_zero_exit=False,
        event_parser=lambda events: (check_for_event(events, "python_http_request")),
    ),
    PythonTestCase(
        "test_aiohttp_legacy_tracer",
        module="test_ssrf_aiohttp",
        policy="python/legacy-tracer/python.json",
        event_parser=lambda events: (check_for_event(events, "python_trace_module")),
    ),
    # Disable libarchive tests. It requires libarchive.so from libarchive-dev
    # PythonTestCase(
    #    "test_libarchive",
    #    extra_deps=["libarchive", "python-libarchive"],
    #    non_zero_exit=False,
    #    event_parser=lambda events: (check_for_event(events, "python_zip_slip")),
    # ),
    # Disable flask test. It respawns a process and looses brusensor
    # PythonTestCase("test_flask_server", extra_flags=["-p"], event_parser=check_for_url_get),
    PythonTestCase(
        "test_sdk_event",
        event_parser=lambda events: (
            check_for_event(events, "python_sdk_event", {"name": "test_event", "attrs": {"key": "value"}})
        ),
    ),
    PythonTestCase(
        "test_anthropic",
        # extra_deps=["anthropic"],
        module="test_anthropic",
        event_parser=lambda events: (
            check_for_event(events, "python_llm_call"),
            check_for_event(events, "python_llm_reply"),
        ),
    ),
    PythonTestCase(
        "test_openai",
        extra_deps=["openai"],
        module="test_openai",
        event_parser=lambda events: (
            check_for_event(events, "python_llm_call", attributes={"raw": {"test": "test2"}}),
            check_for_event(events, "python_llm_reply", attributes={"raw": {"test": "test2"}}),
        ),
    ),
    PythonTestCase(
        "test_openai_api",
        extra_deps=["openai"],
        module="test_openai_api",
        event_parser=lambda events: (
            check_for_event(events, "python_llm_call"),
            check_for_event(events, "python_llm_reply"),
        ),
    ),
    PythonTestCase(
        "test_openai_async_api",
        extra_deps=["openai"],
        module="test_openai_async_api",
        event_parser=lambda events: (
            check_for_event(events, "python_llm_call"),
            check_for_event(events, "python_llm_reply"),
        ),
    ),
    PythonTestCase(
        "test_opentelemetry",
        extra_deps=["opentelemetry-api", "opentelemetry-sdk"],
        event_parser=lambda events: (check_for_event(events, "python_otel_span", {"name": "test-span"})),
    ),
    PythonTestCase(
        "test_opentelemetry_hooks",
        extra_deps=["opentelemetry-api", "opentelemetry-sdk"],
        event_parser=lambda events: (check_for_event(events, "python_otel_span", {"name": "auto-hook-span"})),
    ),
    PythonTestCase(
        "test_mcp_tool",
        extra_deps=["mcp"],
        event_parser=check_mcp_tool_events,
    ),
]

# Python test cases that require higher Python versions.

if sys.version_info.major >= 3 and sys.version_info.minor >= 9:
    python_test_cases.extend(
        [
            PythonTestCase(
                "test_litellm_client_api",
                extra_deps=["litellm"],
                module="test_litellm_client_api",
                event_parser=lambda events: (
                    check_for_event(events, "python_llm_call"),
                    check_for_event(events, "python_llm_reply"),
                ),
            ),
        ]
    )

if sys.version_info.major >= 3 and sys.version_info.minor >= 13:
    python_test_cases.extend(
        [
            PythonTestCase(
                "test_gemini",
                module="test_gemini",
                event_parser=lambda events: (
                    check_for_event(events, "python_llm_call"),
                    check_for_event(events, "python_llm_reply"),
                ),
            ),
        ]
    )
