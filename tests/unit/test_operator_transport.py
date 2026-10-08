"""Resource-bound transport tests use only owned synthetic child processes."""

import os
import sys

import pytest

from cadence_mcp_bridge.operator_transport import run_fixed


def test_bounded_echo():
    code, out, err = run_fixed(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
        b"request",
        dict(os.environ),
    )
    assert (code, out, err) == (0, b"request", b"")


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_output_bound_kills_owned_child(stream):
    code = f"import sys,time; sys.{stream}.write('x'*100000); sys.{stream}.flush(); time.sleep(10)"
    with pytest.raises(ValueError, match="output_limit"):
        run_fixed([sys.executable, "-c", code], b"", dict(os.environ), limit=1024, timeout=0.5)


def test_timeout_kills_owned_child():
    with pytest.raises(ValueError, match="timeout"):
        run_fixed(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            b"",
            dict(os.environ),
            timeout=0.1,
        )


def test_bounded_large_package_transfer_does_not_expand_public_provider_limits():
    request = b"x" * 524288
    code, out, err = run_fixed(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
        request,
        dict(os.environ),
        limit=1048576,
    )
    assert code == 0 and out == request and err == b""
    with pytest.raises(ValueError, match="bounds"):
        run_fixed(["unused"], request, dict(os.environ), limit=262144)
    with pytest.raises(ValueError, match="bounds"):
        run_fixed(["unused"], b"", dict(os.environ), limit=1048577)
