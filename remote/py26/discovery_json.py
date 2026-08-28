#!/usr/bin/env python
"""Python 2.6-compatible metadata-only Cadence discovery helper."""

from __future__ import print_function

import json
import os
import re
import sys

IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_#-]{0,63}$")


def fail(message):
    sys.stderr.write(message + "\n")
    return 64


def emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def load_allowlist(path):
    with open(path, "rb") as handle:
        config = json.load(handle)
    required = set(["cds_lib", "project_root", "libraries"])
    if set(config) != required or not isinstance(config["libraries"], dict):
        raise ValueError("invalid discovery allowlist")
    return config


def parse_cds_lib(path):
    definitions = {}
    with open(path, "rb") as handle:
        for raw_line in handle:
            line = raw_line.decode("utf-8", "strict").strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) == 3 and parts[0].upper() == "DEFINE":
                definitions[parts[1]] = parts[2]
    return definitions


def checked_library(config, library):
    if not IDENTIFIER.match(library) or library not in config["libraries"]:
        raise ValueError("library is outside the discovery allowlist")
    entry = config["libraries"][library]
    configured = os.path.realpath(entry["path"])
    project_root = os.path.realpath(config["project_root"])
    if os.path.dirname(configured) != project_root:
        raise ValueError("library path is outside the project root")
    definitions = parse_cds_lib(config["cds_lib"])
    defined = definitions.get(library)
    if defined is None:
        raise ValueError("allowlisted library is not defined")
    if not os.path.isabs(defined):
        defined = os.path.join(project_root, defined)
    if os.path.realpath(defined) != configured:
        raise ValueError("library definition does not match the allowlist")
    if os.path.islink(entry["path"]) or not os.path.isdir(entry["path"]):
        raise ValueError("allowlisted library is unavailable")
    return entry


def checked_cell(config, library, cell):
    entry = checked_library(config, library)
    if not IDENTIFIER.match(cell) or cell not in entry["cells"]:
        raise ValueError("cell is outside the discovery allowlist")
    path = os.path.join(entry["path"], cell)
    if os.path.islink(path) or not os.path.isdir(path):
        raise ValueError("allowlisted cell is unavailable")
    if os.path.dirname(os.path.realpath(path)) != os.path.realpath(entry["path"]):
        raise ValueError("cell path escaped the allowlisted library")
    return entry, path


def list_libraries(config):
    libraries = []
    for library in sorted(config["libraries"]):
        entry = checked_library(config, library)
        existing = 0
        for cell in entry["cells"]:
            path = os.path.join(entry["path"], cell)
            if os.path.isdir(path) and not os.path.islink(path):
                existing += 1
        libraries.append({"name": library, "allowed_cell_count": existing})
    emit(
        {
            "libraries": libraries,
            "allowlist_enforced": True,
            "proprietary_content_included": False,
        }
    )


def list_cells(config, library):
    entry = checked_library(config, library)
    cells = []
    for cell in sorted(entry["cells"]):
        path = os.path.join(entry["path"], cell)
        if os.path.isdir(path) and not os.path.islink(path):
            cells.append(cell)
    emit(
        {
            "library": library,
            "cells": cells,
            "allowlist_enforced": True,
            "proprietary_content_included": False,
        }
    )


def inspect_cellview(config, library, cell, view):
    entry, cell_path = checked_cell(config, library, cell)
    if not IDENTIFIER.match(view) or view not in entry["cells"][cell]:
        raise ValueError("view is outside the discovery allowlist")
    view_path = os.path.join(cell_path, view)
    exists = os.path.isdir(view_path) and not os.path.islink(view_path)
    if exists and os.path.dirname(os.path.realpath(view_path)) != os.path.realpath(cell_path):
        raise ValueError("cellview path escaped the allowlisted cell")
    emit(
        {
            "library": library,
            "cell": cell,
            "view": view,
            "exists": exists,
            "kind": "cellview",
            "allowlist_enforced": True,
            "proprietary_content_included": False,
        }
    )


def main():
    if len(sys.argv) < 3:
        return 64
    config_path = sys.argv[1]
    command = sys.argv[2]
    arguments = sys.argv[3:]
    try:
        config = load_allowlist(config_path)
        if command == "list-libraries" and len(arguments) == 0:
            list_libraries(config)
        elif command == "list-cells" and len(arguments) == 1:
            list_cells(config, arguments[0])
        elif command == "inspect-cellview" and len(arguments) == 3:
            inspect_cellview(config, arguments[0], arguments[1], arguments[2])
        else:
            return fail("invalid discovery request")
    except (IOError, OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        return fail(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
