"""Verify the enrolled Source9 NMOS length callback over an in-guest pipe."""

import hashlib
import re
import signal
import sys

NMOS_LENGTH_CALLBACK_SHA256 = b"b6be0698d4779420a8860f9a896d998acdd6e05b2852b41d81db390a7b9fc00e"


def check_length_callback(stream):
    """Verify one bounded callback payload without returning its contents."""
    header = stream.readline(32)
    match = re.match(b"nmos1v\\|l\\|([1-9][0-9]{0,3})\n\\Z", header)
    if match is None:
        return False
    size = int(match.group(1))
    if size > 4096:
        return False
    raw = stream.read(size)
    if len(raw) != size or stream.readline(16) != b"\n" or stream.readline(16) != b"END\n":
        return False
    return hashlib.sha256(raw).hexdigest().encode("ascii") == NMOS_LENGTH_CALLBACK_SHA256


def main():
    if sys.version_info[:2] != (2, 6) or len(sys.argv) != 1:
        raise SystemExit(69)
    signal.alarm(10)
    if not check_length_callback(sys.stdin):
        raise SystemExit(69)
    sys.stdout.write("C1_NMOS_LENGTH_CALLBACK_VERIFIED\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
