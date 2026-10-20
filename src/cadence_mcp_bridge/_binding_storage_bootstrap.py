# mypy: ignore-errors
# ruff: noqa: UP024
# Imports follow path isolation; Python 2.6 has a distinct IOError class.
"""DRAFT fixed `python -E -s -B -c` entry, source bytes then canonical request.

This authenticates only the exact inspector source bytes. It does not attest the
interpreter, stdlib/runtime dependencies, host, execution authority, or storage.
Never deploy or execute on a VM without the separate bounded read authorization.
"""

import sys

SOURCE_BYTES = 39588
SOURCE_SHA256 = "7aed98fa8017f174d06bcdf8a53bba814ca224245d2769d5e9e1cf33fa73ad79"
SOURCE_NAME = "<cadence-storage-prerequisite-readonly>"
MODULE_NAME = "_cadence_storage_prerequisite_readonly"
MAX_SECONDS = 60


def main():
    if (
        not sys.flags.ignore_environment
        or not sys.flags.no_user_site
        or not sys.dont_write_bytecode
    ):
        sys.stderr.write("STORAGE_INSPECTOR_ISOLATED_PYTHON_REQUIRED\n")
        sys.exit(1)
    entry = sys.path[0] if sys.path else None
    sys.path[:] = [p for p in sys.path if p and p != entry]
    import os

    cwd = os.path.realpath(os.getcwd())
    sys.path[:] = [p for p in sys.path if os.path.isabs(p) and os.path.realpath(p) != cwd]
    import hashlib
    import json
    import signal
    import types

    previous = None

    def expired(signum, frame):
        raise ValueError("inspection_deadline")

    try:
        if len(sys.argv) != 1:
            raise ValueError("no_command_or_path_arguments")
        if not 1 <= SOURCE_BYTES <= 131072:
            raise ValueError("source_byte_bound")
        deadline = os.times()[4] + MAX_SECONDS
        if hasattr(signal, "SIGALRM"):
            previous = signal.signal(signal.SIGALRM, expired)
            signal.alarm(MAX_SECONDS)
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        source = stream.read(SOURCE_BYTES)
        if len(source) != SOURCE_BYTES or hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
            raise ValueError("inspector_source_binding")
        private = types.ModuleType(MODULE_NAME)
        private.__file__ = SOURCE_NAME
        private._FIXED_BOOTSTRAP_ACTIVE = True
        private._FIXED_BOOTSTRAP_DEADLINE = deadline
        eval(compile(source, SOURCE_NAME, "exec"), private.__dict__, private.__dict__)
        private.main()
    except (ValueError, OSError, IOError, KeyError, TypeError) as error:
        code = str(error) if isinstance(error, ValueError) else "inspection_incomplete"
        if code not in (
            "inspection_deadline",
            "no_command_or_path_arguments",
            "source_byte_bound",
            "inspector_source_binding",
        ):
            code = "inspection_incomplete"
        raw = json.dumps(
            dict(
                schema_version=1,
                status="INCOMPLETE",
                error_code=code,
                ready_for_apply=False,
                execution_authorized=False,
            ),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        output = getattr(sys.stdout, "buffer", sys.stdout)
        output.write(raw + b"\n")
    finally:
        if previous is not None:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)


if __name__ == "__main__":
    main()
