#!/usr/bin/env bash
# install rustup with a pinned rust toolchain. invoked from the
# cibuildwheel pre-install hook so every wheel build uses the same
# rustc regardless of what the default stable channel points at on
# the day of the build.
#
# RUST_VERSION pins the toolchain. override via env var for local
# testing of a different release.

set -euo pipefail

RUST_VERSION="${RUST_VERSION:-1.92}"

curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- \
  -y \
  --default-toolchain "${RUST_VERSION}" \
  --profile minimal

echo "install-rustup: installed rust toolchain ${RUST_VERSION}"
