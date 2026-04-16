# Copyright (C) 2025 BlueRock Security, Inc.
# All rights reserved.

from collections import OrderedDict
import threading


class LruCache:
    def __init__(self, max_size):
        self._max_size = max_size
        self._dict = OrderedDict()
        self._lock = threading.Lock()

    def add(self, key, value):
        with self._lock:
            if key not in self._dict:
                if len(self._dict) >= self._max_size:
                    self._dict.popitem(last=False)  # Remove the oldest item
                self._dict[key] = set()
            else:
                self._dict.move_to_end(key)  # Mark as recently used
            self._dict[key].add(value)

    def get(self, key):
        with self._lock:
            try:
                self._dict.move_to_end(key)  # Mark as recently used
                return self._dict[key]
            except KeyError:
                return set()

    def find_key(self, functor, arg):
        with self._lock:
            for key in self._dict:
                try:
                    vals = self._dict[key]
                    for val in vals:
                        if functor(val, arg):
                            return key
                except KeyError:
                    continue
            return None

    def keys(self) -> list:
        with self._lock:
            return list(self._dict.keys())

    def __getitem__(self, key):
        with self._lock:
            return self._dict[key]

    def __contains__(self, key):
        with self._lock:
            if key in self._dict:
                self._dict.move_to_end(key)  # Mark as recently used
                return True
            return False

    def __len__(self):
        return len(self._dict)

    def __iter__(self):
        return iter(self._dict)

    def __repr__(self):
        return f"LruCache: len = '{len(self._dict)}' '{self._dict}'"
