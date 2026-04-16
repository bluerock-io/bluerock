#!/usr/bin/env bash
# generate a hash-pinned requirements.lock from test_oss_requirements.txt
# for reproducible CI builds.
#
# usage:
#   .github/scripts/lock-deps.sh           — regenerate acoustic/python/requirements.lock
#   .github/scripts/lock-deps.sh --verify  — fail if the lockfile is out of date (used in CI)
#
# test_oss_requirements.txt uses editable paths like `-e .` and `-e ../python-oss`
# which pip-compile resolves against its current working directory, not the
# requirements file's directory. so we cd into acoustic/python/ first.
set -euo pipefail

# resolve the repo root from the script's own location so the script works
# regardless of where it's invoked from.
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
WORK_DIR="$REPO_ROOT/acoustic/python"
REQUIREMENTS_IN="test_oss_requirements.txt"     # relative to WORK_DIR
REQUIREMENTS_LOCK="requirements.lock"           # relative to WORK_DIR

# resolve pip-compile at the version CI uses (.github/requirements/lint.txt).
# hitting system pip without a version pin fails two ways: PEP 668 blocks
# the install on modern debian/ubuntu, and an unpinned `pip install pip-tools`
# drifts to latest (7.5.x has a --generate-hashes regression with editable
# paths that we depend on here). prefer uvx, then a reusable /tmp venv.
LINT_REQS="$REPO_ROOT/.github/requirements/lint.txt"
PIP_TOOLS_VER=$(grep -E '^pip-tools==' "$LINT_REQS" | head -1 | sed 's/.*==//')
if [ -z "$PIP_TOOLS_VER" ]; then
    echo "lock-deps: could not read pip-tools pin from $LINT_REQS" >&2
    exit 1
fi

# always use a private venv, pinning pip<25 in the
# venv catches this without touching the runner's global pip.
if command -v uvx &>/dev/null; then
    PIP_COMPILE=(uvx --from "pip-tools==${PIP_TOOLS_VER}" pip-compile)
else
    VENV="${TMPDIR:-/tmp}/lock-deps-venv"
    if [ ! -x "$VENV/bin/pip-compile" ]; then
        python3 -m venv "$VENV"
        "$VENV/bin/pip" install -q "pip<25" "pip-tools==${PIP_TOOLS_VER}"
    fi
    PIP_COMPILE=("$VENV/bin/pip-compile")
fi

cd "$WORK_DIR"

# normalize the machine-specific bits pip-compile bakes into lockfile
# output, so the same pyproject resolves to byte-identical output on
# any host. without this, two sources of drift:
#   - absolute file:// paths for editable installs (-e .) get written
#     as the generating machine's absolute path. different on local
#     vs github CI vs elsewhere.
#   - --output-file=<path> gets written into the header comment, so
#     the generate path (requirements.lock) and verify path (mktemp)
#     produce different headers even when content matches.
normalize_lockfile() {
    local f="$1"
    sed -i -E \
        -e 's|(--output-file=)[^[:space:]]+|\1requirements.lock|' \
        -e 's|^-e file://[^[:space:]]*/acoustic/python$|-e .|' \
        -e 's|^-e file://[^[:space:]]*/acoustic/python-oss$|-e ../python-oss|' \
        -e 's|^(    #   )file://[^[:space:]]*/acoustic/python$|\1.|' \
        -e 's|^(    #   )file://[^[:space:]]*/acoustic/python-oss$|\1../python-oss|' \
        "$f"
}

if [[ "${1:-}" == "--verify" ]]; then
    echo "lock-deps: verifying $WORK_DIR/$REQUIREMENTS_LOCK is up to date..."
    TMPLOCK=$(mktemp)
    TMPERR=$(mktemp)
    # seed the tmp with the committed lockfile so pip-compile treats
    # already-pinned versions as "don't upgrade" (its default behaviour
    # when the output file exists). without seeding, verify always
    # picks pypi-latest and drifts past the pin on every pypi release.
    cp "$REQUIREMENTS_LOCK" "$TMPLOCK"
    # capture stderr for pip-compile so failures surface in the log
    if ! "${PIP_COMPILE[@]}" --generate-hashes --strip-extras \
            --output-file="$TMPLOCK" \
            "$REQUIREMENTS_IN" -q 2>"$TMPERR"; then
        echo "lock-deps: pip-compile failed (new dep added?). run: .github/scripts/lock-deps.sh"
        echo "---- pip-compile stderr ----"
        cat "$TMPERR"
        echo "----------------------------"
        rm -f "$TMPLOCK" "$TMPERR"
        exit 1
    fi
    rm -f "$TMPERR"
    normalize_lockfile "$TMPLOCK"
    if ! diff -q "$REQUIREMENTS_LOCK" "$TMPLOCK" &>/dev/null; then
        echo "lock-deps: $REQUIREMENTS_LOCK is stale. run: .github/scripts/lock-deps.sh"
        diff "$REQUIREMENTS_LOCK" "$TMPLOCK" || true
        rm -f "$TMPLOCK"
        exit 1
    fi
    rm -f "$TMPLOCK"
    echo "lock-deps: $REQUIREMENTS_LOCK is up to date"
else
    echo "lock-deps: generating $WORK_DIR/$REQUIREMENTS_LOCK from $REQUIREMENTS_IN..."
    "${PIP_COMPILE[@]}" --generate-hashes --strip-extras \
        --output-file="$REQUIREMENTS_LOCK" \
        "$REQUIREMENTS_IN"
    normalize_lockfile "$REQUIREMENTS_LOCK"
    echo "lock-deps: written $REQUIREMENTS_LOCK"
    echo "lock-deps: commit this file to ensure reproducible CI builds"
fi
