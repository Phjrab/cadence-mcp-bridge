"""Verify ordered live GPDK090 W/L/m callback identities in a private pipe."""

import hashlib
import re
import signal
import sys

if sys.version_info[0] >= 3:  # noqa: UP036 - guest runs Python 2.6
    from typing import BinaryIO  # noqa: F401 - referenced in a Python 2.6 type comment

CALLBACKS = {
    b"l": b"b6be0698d4779420a8860f9a896d998acdd6e05b2852b41d81db390a7b9fc00e",
    b"w": b"ee118e38a0bd277bb6fe1ac2a66d1b0d722813192e121a1615fcfa43464ce4ca",
    b"m": b"9790d823d25e5a73c3ab70cebfe9dec1205641fe01c6daf9866ca4bafe32e0e7",
}


def check_callbacks(stream):
    # type: (BinaryIO) -> bool
    """Read the selected callback sequence and compare each exact digest."""
    header = re.match(b"headless_wlm_v1\\|(nmos1v|pmos1v)\\|(l?w?m?)\n\\Z", stream.readline(40))
    if header is None or not header.group(2):
        return False
    for index in range(len(header.group(2))):
        axis = header.group(2)[index : index + 1]
        row = re.match(b"([lwm])\\|([1-9][0-9]{0,3})\n\\Z", stream.readline(16))
        if row is None or row.group(1) != axis:
            return False
        size = int(row.group(2))
        if size > 4096:
            return False
        body = stream.read(size)
        if len(body) != size or stream.readline(2) != b"\n":
            return False
        if hashlib.sha256(body).hexdigest().encode("ascii") != CALLBACKS[axis]:
            return False
    return stream.readline(5) == b"END\n"


def main():
    # type: () -> None
    if sys.version_info[:2] != (2, 6) or len(sys.argv) != 1:
        raise SystemExit(69)
    signal.alarm(10)
    try:
        verified = check_callbacks(getattr(sys.stdin, "buffer", sys.stdin))
    except (IOError, OSError):  # noqa: UP024 - distinct in Python 2.6
        raise SystemExit(69)  # noqa: B904 - guest has no raise-from syntax
    if not verified:
        raise SystemExit(69)
    sys.stdout.write("C1_WLM_CALLBACKS_VERIFIED\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
