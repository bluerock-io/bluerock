# Copyright (C) 2026 BlueRock Security, Inc.
# All rights reserved.

"""Import monitoring example.

BlueRock emits a ``python_import`` event for each module loaded at runtime,
including the fully-qualified module name, the on-disk SHA-256 hash of the
module file, and the installed package version (when available).

Run:
    python -m bluepython --oss import_monitoring.py

Events written to ~/.bluerock/event-spool/*.ndjson
"""

import requests

print(f"requests version: {requests.__version__}")
