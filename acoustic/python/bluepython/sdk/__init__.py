# Copyright (C) 2026 BlueRock Security, Inc.
# All rights reserved.

from .. import backend
from ..backend import new_span as new_span


def event(name, attrs=None):
    if getattr(backend, "acousticBackend", None):
        backend.emit_event("sdk_event", {"name": name, "attrs": attrs})
