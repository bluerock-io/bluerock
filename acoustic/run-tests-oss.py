# Copyright (C) 2026 BlueRock Security, Inc.
# All rights reserved.

import argparse
import asyncio
import glob
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tempfile
from importlib.metadata import version

from sensor_tests.common import check_for_event
from sensor_tests.python import python_test_cases

DEFAULT_EVENT_LOGDIR = os.path.join(os.getcwd(), "bluepython_test_logs")

# Only tests in this allowlist are run against the OSS backend.
# Tests requiring remediation, or features not available for the OSS version, are excluded.
OSS_ALLOWLIST = {
    "test_import",
    "test_reload_import",
}


def check_for_internal_sensor_exceptions(events):
    return check_for_event(events, "python_internal_exception")


async def main():
    # Terminal escape codes to make the output more pretty/readable.
    fontBold = ""
    fontRed = ""
    fontGreen = ""
    fontRst = ""
    if os.isatty(sys.stdout.fileno()):
        fontBold = "\x1b[1m"
        fontRed = "\x1b[31m"
        fontGreen = "\x1b[32m"
        fontRst = "\x1b[0m"

    parser = argparse.ArgumentParser(prog="python3 ./run-tests-oss.py")
    parser.add_argument("-q", "--quiet", action="store_true", help="Do not print test case output")
    parser.add_argument("--without-bru", action="store_true", help="Run without bluepython module.")
    parser.add_argument("--skip-missing-deps", action="store_true", help="Skip tests that have missing dependencies")
    parser.add_argument("-s", "--select", help="Select what test case should be executed via regex")
    parser.add_argument(
        "--log-dir", default=DEFAULT_EVENT_LOGDIR, help="Directory to store event logs for each test case."
    )

    args = parser.parse_args()

    # Output file for subprocesses.
    output = sys.stdout.fileno()
    if args.quiet:
        output = subprocess.DEVNULL

    selected_test_cases = python_test_cases
    if args.select:
        selected_test_cases = [t for t in selected_test_cases if re.match(args.select, t.name)]

    if not os.path.exists(args.log_dir):
        os.makedirs(args.log_dir)

    failures = []
    for i, case in enumerate(selected_test_cases):
        missing_deps = []
        for pkg in case.extra_deps:
            try:
                version(pkg)
            except importlib.metadata.PackageNotFoundError:
                missing_deps.append(pkg)
        if args.skip_missing_deps and missing_deps:
            print(f"{fontBold}Skipping test case {case.name} due to missing dependencies {missing_deps}{fontRst}")
            continue

        if case.name not in OSS_ALLOWLIST:
            print(f"{fontBold}Skipping test case {case.name} (not supported by OSS backend){fontRst}")
            continue

        print(f"{fontBold}Running test case {case.name}{fontRst}")
        if not args.quiet:
            print("-" * 80, flush=True)

        test_name_in_logs = case.name.replace("/", "_")
        log_file = os.path.join(args.log_dir, f"{test_name_in_logs}.log")
        if os.path.exists(log_file):
            os.unlink(log_file)

        if not args.without_bru:
            # Clean up any existing OSS event files before the test.
            event_spool_dir = os.path.join(os.path.expanduser("~"), ".bluerock", "event-spool")
            for f in glob.glob(os.path.join(event_spool_dir, "python-*.ndjson")):
                os.unlink(f)

        with tempfile.TemporaryDirectory() as tmpdir_name:
            if not args.without_bru:
                oss_sensor_cfg = {
                    "enable": True,
                    "imports": {"enable": True, "fileslist": True},
                    "mcp": True,
                }
                with open(os.path.join(tmpdir_name, "bluerock-oss.json"), "w") as f:
                    json.dump(oss_sensor_cfg, f)

            pargs = [sys.executable]
            if not args.without_bru:
                pargs.extend(["-m", "bluepython", "--oss", "--cfg-dir", tmpdir_name])
                pargs.extend(case.extra_flags)
                pargs.extend(["--", f"{case.module}.py"])
            else:
                pargs.append(f"{case.module}.py")

            # run the test with a clean environment — keep PATH, HOME,
            # locale and similar basics, drop CI-runner-specific vars so
            # the test sees a shell-like environment, not the runner's.
            safe_env = {
                k: v
                for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "RUNNER_", "ACTIONS_", "INPUT_"))
                and k not in ("GH_TOKEN", "NODE_AUTH_TOKEN")
            }
            process = await asyncio.create_subprocess_exec(
                *pargs,
                cwd="tests/",
                stdout=output,
                stderr=output,
                env=safe_env,
            )
            await process.wait()
            returncode = process.returncode

        if not args.quiet:
            print("-" * 80)

        # Collect events from OSS NDJSON files.
        events = []
        event_parser_failed = False
        if not args.without_bru:
            new_files = glob.glob(os.path.join(event_spool_dir, "python-*.ndjson"))
            all_lines = []
            for f in new_files:
                with open(f, "r") as ndjson_file:
                    all_lines.extend(ndjson_file.readlines())
            if all_lines:
                try:
                    events = [json.loads(line)["event"] for line in all_lines if line.strip()]
                except json.JSONDecodeError:
                    print("Warning: could not decode JSON from OSS event files")
                    event_parser_failed = True

                if not event_parser_failed:
                    with open(log_file, "w") as lf:
                        for evt in events:
                            lf.write(json.dumps(evt) + "\n")

        if not event_parser_failed:
            if not case.tolerate_internal_exceptions:
                event_parser_failed = check_for_internal_sensor_exceptions(events)
            if case.event_parser and not event_parser_failed:
                event_parser_failed = not case.event_parser(events)

        if ((returncode != 0) == case.non_zero_exit) and not event_parser_failed:
            print(
                f"{fontBold}{fontGreen}SUCCESS{fontRst}: test case {case.name} exited with status {returncode} (should fail? {case.non_zero_exit})"
            )
        else:
            print(f"{fontBold}{fontRed}FAILURE{fontRst}")
            if event_parser_failed:
                print(f"Test case {case.name} did not produce the expected event or produced an exception")
            elif returncode >= 0:
                print(f"Test case {case.name} exited with status {returncode}")
            else:
                print(f"Test case {case.name} was killed by signal {-returncode}")
            failures.append(case.name)

        if i + 1 != len(selected_test_cases):
            print()

    if failures:
        print("Failure in test case(s): {}".format(", ".join(failures)))
        sys.exit(1)
    print("All tests succeeded")


if __name__ == "__main__":
    asyncio.run(main())
