# Copyright (C) 2025 BlueRock Security, Inc.
# All rights reserved.

import base64
import builtins
import hashlib
import os
import sys
import importlib.abc
import importlib.metadata
from . import backend
from . import wrapper
from . import cfg

try:
    from . import pathtraversal_hooks

    _builtin_open = pathtraversal_hooks.builtins_open
except ImportError:
    _builtin_open = builtins.open


def calculate_sha256(filepath):
    if filepath is None:
        return None
    try:
        with _builtin_open(filepath, "rb") as f:
            data = f.read()
            sha256_hash = hashlib.sha256(data).hexdigest()
            return sha256_hash
    except Exception as e:
        backend.debug(f"calculate_file_sha256: Error reading file {filepath}: {e}")
        return None


def get_module_filepath(module_name, paths):
    # Avoid a call to importlib.util.find_spec. it can cause a recursion.
    if paths is None:
        paths = sys.path

    name_parts = module_name.split(".")
    base_name = name_parts[-1]
    for path in paths:
        # 1. Check for a regular .py file
        filepath = os.path.join(path, f"{base_name}.py")
        if os.path.exists(filepath) and os.path.isfile(filepath):
            return filepath

        # 2. Check for a package directory (with __init__.py)
        package_path = os.path.join(path, base_name)
        init_path = os.path.join(package_path, "__init__.py")
        if os.path.exists(init_path) and os.path.isfile(init_path):
            return init_path

        # 3. Check for extension modules (.so, .pyd, etc.)
        for ext in importlib.machinery.EXTENSION_SUFFIXES:
            extension_path = os.path.join(path, f"{base_name}{ext}")
            if os.path.exists(extension_path) and os.path.isfile(extension_path):
                return extension_path


class ModuleInfo:
    def __init__(self, name):
        self.name = name
        self.paths = []
        self.filepath = None
        self.sha256 = None

    def update_paths(self, paths):
        self.paths = paths if paths is not None else []  # or sys.path ?

    def set_file_path(self, filepath):
        self.filepath = filepath

    def update_hash(self, hash_256):
        if self.sha256 is None:
            self.sha256 = hash_256
            return False
        if self.sha256 == hash_256:
            return False
        self.sha256 = hash_256
        return True


class FileToPackageMapper:
    def __init__(self):
        self._map = {}
        self._syspath_for_map = []
        self.build_file_to_package_map()

    def build_file_to_package_map(self):
        # Future: we could consider sending an event about the sys.path update
        # if that's useful in certain cases
        backend.debug(f"(re)building package to file map with sys.path = {sys.path}")
        packages = importlib.metadata.distributions()
        self._syspath_for_map = sys.path

        for p in packages:
            if p.files is None:
                continue
            for file in p.files:
                self._map[str(p.locate_file(file))] = (p, file.hash)

    def find_file(self, fullpath):
        if sys.path != self._syspath_for_map:
            self.build_file_to_package_map()
        return self._map.get(fullpath)


class ImportMonitor(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.imported_modules = dict()
        self._mapper = FileToPackageMapper()
        self._reported_packages = dict()

    def is_added(self, fullname, path):
        if fullname in self.imported_modules:
            return True
        return False

    def add(self, fullname, path):
        if fullname not in self.imported_modules:
            self.imported_modules[fullname] = ModuleInfo(fullname)
        self.imported_modules[fullname].update_paths(path)

    def set_file_path(self, fullname, filepath):
        self.imported_modules[fullname].set_file_path(filepath)

    def set_module_hash(self, fullname, h):
        return self.imported_modules[fullname].update_hash(h)

    def unknown_package(self, package_name, package_version):
        if package_name == "":
            return False
        if package_name in self._reported_packages:
            if package_version == self._reported_packages[package_name]:
                # no change in version, skip
                return False
        self._reported_packages[package_name] = package_version
        return True

    @wrapper.measure_time
    def find_spec(self, fullname, path, target=None):
        if not cfg.sensor_config.enabled("imports"):
            return None

        # 3.10+ can distinguish easily stdlib imports - that avoids too many events
        # but if we cannot filter out, just send extra events for stdlib.
        if sys.version_info >= (3, 10) and fullname in sys.stdlib_module_names:
            return None

        # Skip bluepython.* modules
        if fullname.startswith("bluepython."):
            return None

        known_module = False
        if self.is_added(fullname, path):
            known_module = True
        else:
            self.add(fullname, path)

        try:
            import_file_path = get_module_filepath(fullname, path)
            self.set_file_path(fullname, import_file_path)
            hash256 = None
            hash_changed = False

            package_name = ""
            package_version = "unknown"
            pkg_info = self._mapper.find_file(import_file_path)
            if pkg_info:
                package_name = pkg_info[0].metadata["Name"]
                package_version = pkg_info[0].version
                if pkg_info[1] and pkg_info[1].mode == "sha256":
                    # add padding to base64
                    b64_hash = pkg_info[1].value + "=" * (4 - len(pkg_info[1].value) % 4)
                    hash256 = base64.urlsafe_b64decode(b64_hash).hex()

            if hash256 is None:
                hash256 = calculate_sha256(import_file_path)
            hash_changed = self.set_module_hash(fullname, hash256)
            # report once unless hash changed
            if known_module and not hash_changed:
                return None

            # skip if package is known and file reporting is disabled
            new_pkg = self.unknown_package(package_name, package_version)
            if not new_pkg and not cfg.sensor_config.imports.fileslist:
                return None

            # message format may change to differentiate between a package/file load
            # and a package/file execution event
            backend.emit_event(
                "import",
                {
                    "fullname": fullname,
                    "path": str(path) if path is not None else None,
                    "file": str(import_file_path) if import_file_path is not None else None,
                    "pkg": package_name,
                    "version": package_version,
                    "sha256": hash256,
                    "hash_changed": hash_changed,
                },
            )
        except backend.Remediation:
            raise
        except Exception as e:
            backend.exception(e)

        # Return None to let the standard import mechanism handle it
        return None


monitor = ImportMonitor()
sys.meta_path.insert(0, monitor)
