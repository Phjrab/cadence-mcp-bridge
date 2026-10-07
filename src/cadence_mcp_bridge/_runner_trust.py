"""Fixed read-only executable/ancestor trust diagnosis, standalone Python2.6."""

# mypy: ignore-errors
import json
import os
import re
import stat
import sys


def main():
    if len(sys.argv) != 1:
        raise ValueError("fixed_diagnostic")
    data = sys.stdin.read(32769)
    if len(data) > 32768:
        raise ValueError("profile_size")
    profile = json.loads(data)
    results = {}
    for name in ("virtuoso", "spectre", "ocean"):
        path = profile["tools"][name]["path"]
        if not re.match(r"^/[A-Za-z0-9._/-]{1,511}$", path) or ".." in path.split("/"):
            raise ValueError("path_shape")
        if os.path.basename(path) != name:
            raise ValueError("executable_name")
        real = os.path.realpath(path)
        items = []
        current = real
        while current != "/":
            info = os.stat(current)
            if info.st_mode & 18:
                items.append(
                    {
                        "path": current,
                        "mode_octal": oct(stat.S_IMODE(info.st_mode)),
                        "uid": info.st_uid,
                        "gid": info.st_gid,
                        "problem": "group_or_other_writable",
                    }
                )
            current = os.path.dirname(current)
        results[name] = {"unsafe_components": items, "unsafe_count": len(items)}
    print(
        json.dumps(
            {"schema_version": 1, "tools": results, "diagnosis": "METADATA_ONLY_NOT_QUALIFICATION"},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("TRUST_DIAGNOSTIC_REJECTED\n")
        sys.exit(1)
