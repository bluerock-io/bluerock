# Copyright (C) 2026 BlueRock Security, Inc.
# All rights reserved.

"""Example test runner for BlueRock examples.

Runs each example script under ``python -m bluepython --oss``, collects NDJSON
events from ~/.bluerock/event-spool/, and validates that the expected events were
emitted.  Follows the same pattern as acoustic/run-tests-oss.py.

Usage:
    python examples/run-examples.py
    python examples/run-examples.py --quiet
    python examples/run-examples.py --select core
"""

import argparse
import glob
import importlib.util
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

ACOUSTIC_OSS_EVENT_DIR = os.path.join(os.path.expanduser("~"), ".bluerock", "event-spool")


def wait_for_port(port, host="127.0.0.1", timeout=15):
    """Wait until a TCP port is accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


class TestCase:
    def __init__(self, name, *, script_path, event_checker=None, requires=None, no_internal_exceptions=True,
                 server_script=None, server_port=None):
        self.name = name
        self.script_path = script_path  # relative to examples/ dir
        self.event_checker = event_checker
        self.requires = requires  # pip package name, or None for stdlib-only
        self.no_internal_exceptions = no_internal_exceptions
        self.server_script = server_script  # if set, start this server before running script_path
        self.server_port = server_port  # port to wait for before running client


def check_for_event(events, name, attributes=None):
    for data in events:
        if data.get("meta", {}).get("name") == name:
            if attributes is None:
                return True
            if all(k in data and data[k] == v for k, v in attributes.items()):
                return True
    return False


class EventChecker:
    """Composable multi-event checker: all listed events must be present with matching attributes."""

    def __init__(self, *checks):
        # Each check is (event_name, attributes_dict_or_None)
        self.checks = checks

    def __call__(self, events):
        return all(check_for_event(events, name, attrs) for name, attrs in self.checks)


def validate_event_meta(events):
    """Validate that every event has the required meta-field structure."""
    valid_types = {"event", "nonactionable", "sensor_lifecycle", "block_confirmation", "log"}
    for evt in events:
        meta = evt.get("meta")
        if not meta:
            return False, "event missing 'meta' field"
        for field in ("name", "type", "origin", "sensor_id", "source_event_id"):
            if field not in meta:
                return False, f"meta missing '{field}' in event {meta.get('name', '?')}"
        if meta["type"] not in valid_types:
            return False, f"unexpected meta.type={meta['type']!r} in event {meta['name']}"
        if meta["origin"] != "bluepython":
            return False, f"unexpected meta.origin={meta['origin']!r} in event {meta['name']}"
        if meta["type"] != "sensor_lifecycle":
            ctx = evt.get("context", {})
            if "process" not in ctx:
                return False, f"missing context.process in event {meta['name']}"
    return True, None


# ── Test cases ──────────────────────────────────────────────────────────────

# MCP examples
test_cases = []

optional_test_cases = [
    TestCase(
        "ai-mcp-monitoring",
        script_path="ai-hooks/mcp-monitoring/mcp_client.py",
        event_checker=EventChecker(
            ("python_mcp_server_init", None),
            ("python_mcp_server_add", None),
            ("python_mcp_event", None),
            ("python_mcp_session_created", None),
            ("python_mcp_session_terminated", None),
            ("python_mcp_client_connect", None),
        ),
        requires="mcp",
    ),
    # HTTP transport (file server on port 8001)
    TestCase(
        "ai-mcp-http",
        script_path="ai-hooks/mcp-monitoring/mcp_http_client.py",
        server_script="mcp/mcp_file_server.py",
        server_port=8001,
        event_checker=EventChecker(
            ("python_mcp_client_connect", None),
            ("python_mcp_event", None),
        ),
        requires="mcp",
    ),
    # SSE transport (linux admin on port 8002)
    TestCase(
        "ai-mcp-sse",
        script_path="ai-hooks/mcp-monitoring/mcp_sse_client.py",
        server_script="mcp/mcp_linux_admin.py",
        server_port=8002,
        event_checker=EventChecker(
            ("python_mcp_client_connect", None),
            ("python_mcp_event", None),
        ),
        requires="mcp",
    ),
]


# ── Runner ──────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(prog="run-examples.py")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress subprocess output")
    parser.add_argument("-s", "--select", help="Run only test cases matching this prefix")
    args = parser.parse_args()

    output = sys.stdout.fileno()
    if args.quiet:
        output = subprocess.DEVNULL

    all_cases = test_cases + optional_test_cases
    selected = all_cases
    if args.select:
        selected = [t for t in selected if t.name.startswith(args.select)]

    # filter out tests whose optional deps are missing
    runnable = []
    skipped = []
    for t in selected:
        if t.requires and importlib.util.find_spec(t.requires) is None:
            skipped.append(t.name)
        else:
            runnable.append(t)

    if skipped:
        print(f"Skipping (missing deps): {', '.join(skipped)}")
        print()

    selected = runnable
    examples_dir = os.path.dirname(os.path.abspath(__file__))
    failures = []

    # Write config to ~/.bluerock/ so both the client process and any server
    # subprocesses it spawns can auto-discover it via --oss mode.
    cfg_dir = os.path.join(os.path.expanduser("~"), ".bluerock")
    os.makedirs(cfg_dir, exist_ok=True)
    oss_sensor_cfg = {
        "enable": True,
        "mcp": True,
    }
    with open(os.path.join(cfg_dir, "bluerock-oss.json"), "w") as f:
        json.dump(oss_sensor_cfg, f)

    for i, case in enumerate(selected):
        print(f"\033[1mRunning: {case.name}\033[0m")
        if not args.quiet:
            print("-" * 60, flush=True)

        # clean event-spool dir so we only see events from this test
        if os.path.isdir(ACOUSTIC_OSS_EVENT_DIR):
            shutil.rmtree(ACOUSTIC_OSS_EVENT_DIR)

        # start background server if needed (HTTP/SSE tests)
        server_proc = None
        if case.server_script:
            server_args = [
                sys.executable, "-m", "bluepython", "--oss", "--cfg-dir", cfg_dir,
                "--", case.server_script,
            ]
            server_proc = subprocess.Popen(server_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=examples_dir)
            if not wait_for_port(case.server_port):
                print(f"  server failed to start on port {case.server_port}")
                if server_proc.poll() is None:
                    server_proc.kill()
                failures.append(case.name)
                continue

        pargs = [
            sys.executable,
            "-m",
            "bluepython",
            "--oss",
            "--cfg-dir",
            cfg_dir,
            "--",
            case.script_path,
        ]

        try:
            proc = subprocess.run(pargs, stdout=output, stderr=output, cwd=examples_dir, timeout=120)
        finally:
            if server_proc and server_proc.poll() is None:
                server_proc.terminate()
                try:
                    server_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server_proc.kill()

        # parse NDJSON events from event-spool output dir
        events = []
        for ndjson_file in glob.glob(os.path.join(ACOUSTIC_OSS_EVENT_DIR, "*.ndjson")):
            with open(ndjson_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line)["event"])
                        except json.JSONDecodeError:
                            pass

        if not args.quiet:
            print("-" * 60)

        # verify result
        exit_ok = proc.returncode == 0
        event_ok = True
        if case.event_checker:
            event_ok = case.event_checker(events)

        # check for unexpected sensor exceptions
        exception_ok = True
        if case.no_internal_exceptions and check_for_event(events, "python_internal_exception"):
            exception_ok = False

        # validate event meta-field structure
        meta_ok, meta_err = validate_event_meta(events)

        if not event_ok or not exception_ok:
            print(f"  Events collected: {len(events)}")
            for evt in events:
                meta = evt.get("meta", {})
                print(f"    {meta.get('name', '?')}: {meta.get('type', '?')}")
                if meta.get("name") == "python_internal_exception":
                    print(f"      exception: {evt.get('type', '?')}")

        if exit_ok and event_ok and exception_ok and meta_ok:
            print(f"\033[1;32mPASS\033[0m: {case.name} (exit={proc.returncode}, events={len(events)})")
        else:
            reason = []
            if not exit_ok:
                reason.append(f"exit={proc.returncode} (expected 0)")
            if not event_ok:
                reason.append("expected events not found")
            if not exception_ok:
                reason.append("unexpected python_internal_exception")
            if not meta_ok:
                reason.append(f"meta validation: {meta_err}")
            print(f"\033[1;31mFAIL\033[0m: {case.name} ({', '.join(reason)})")
            failures.append(case.name)

        if i + 1 != len(selected):
            print()

    print()
    if failures:
        print(f"Failed: {', '.join(failures)}")
        sys.exit(1)
    print(f"All {len(selected)} examples passed")


if __name__ == "__main__":
    main()
