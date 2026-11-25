"""Verify the enrolled Source9 PMOS total-width callback in a private guest pipe."""

import hashlib
import re
import signal
import sys

if sys.version_info[0] >= 3:  # noqa: UP036 - guest executes this on Python 2.6
    from typing import BinaryIO  # noqa: F401 - referenced in a Python 2.6 type comment

PMOS_WIDTH_CALLBACK_SHA256 = b"ee118e38a0bd277bb6fe1ac2a66d1b0d722813192e121a1615fcfa43464ce4ca"


def check_width_callback(stream):
    # type: (BinaryIO) -> bool
    """Accept one fixed PMOS w frame and emit no callback data."""
    header = stream.readline(32)
    match = re.match(b"pmos1v\\|w\\|([1-9][0-9]{0,3})\n\\Z", header)
    if match is None:
        return False
    size = int(match.group(1))
    if size > 4096:
        return False
    raw = stream.read(size)
    if len(raw) != size or stream.readline(16) != b"\n" or stream.readline(16) != b"END\n":
        return False
    return hashlib.sha256(raw).hexdigest().encode("ascii") == PMOS_WIDTH_CALLBACK_SHA256


def main():
    # type: () -> None
    if sys.version_info[:2] != (2, 6) or len(sys.argv) != 1:
        raise SystemExit(69)
    signal.alarm(10)
    try:
        verified = check_width_callback(getattr(sys.stdin, "buffer", sys.stdin))
    except (IOError, OSError):  # noqa: UP024 - distinct in Python 2.6
        raise SystemExit(69)  # noqa: B904 - Python 2.6 has no raise-from syntax
    if not verified:
        raise SystemExit(69)
    sys.stdout.write("C1_PMOS_WIDTH_CALLBACK_VERIFIED\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
