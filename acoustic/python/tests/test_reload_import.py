# Copyright (C) 2025 BlueRock Security, Inc.
# All rights reserved.

import sys

prev_sys_path = sys.path
sys.path = []
try:
    import yaml  # noqa: E402
except ImportError:
    pass  # this should fail
    print("import yaml failed as expected")
else:
    print("import yaml should have failed!")
    sys.exit(1)

sys.path = prev_sys_path
import yaml  # noqa: F401, E402
