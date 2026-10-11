"""Resource-bound transport tests use only owned synthetic child processes."""

import os
import sys

import pytest

from cadence_mcp_bridge import _installation_repair as repair
from cadence_mcp_bridge import operator_transport
from cadence_mcp_bridge.operator_transport import run_fixed, run_repair_inventory


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


@pytest.mark.parametrize("limit", [262145, repair.LIMIT])
def test_other_fixed_transports_keep_original_ceiling(monkeypatch, limit):
    def denied(*args, **kwargs):
        raise AssertionError("invalid bounds launched a child")

    monkeypatch.setattr(operator_transport.subprocess, "Popen", denied)
    with pytest.raises(ValueError, match="fixed_transport_bounds"):
        run_fixed([sys.executable], b"", dict(os.environ), limit=limit)


def test_repair_inventory_accepts_large_request_and_exact_protocol_output():
    request = b"x" * 262145
    code, out, err = run_repair_inventory(
        [sys.executable, "-c",
         "import sys; n=len(sys.stdin.buffer.read()); "
         "assert n==262145; sys.stdout.buffer.write(b'x'*16777216)"],
        request,
        dict(os.environ),
    )
    assert operator_transport._REPAIR_INVENTORY_LIMIT == repair.LIMIT
    assert (code, len(out), err) == (0, repair.LIMIT, b"")


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_repair_inventory_output_cannot_exceed_protocol_limit(stream):
    code = (
        f"import sys; sys.stdin.buffer.read(); "
        f"sys.{stream}.buffer.write(b'x'*16777217)"
    )
    with pytest.raises(ValueError, match="fixed_transport_output_limit"):
        run_repair_inventory([sys.executable, "-c", code], b"", dict(os.environ))


def test_repair_inventory_rejects_oversized_request_before_launch(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("invalid request launched a child")

    monkeypatch.setattr(operator_transport.subprocess, "Popen", denied)
    with pytest.raises(ValueError, match="fixed_transport_bounds"):
        run_repair_inventory([sys.executable], b"x" * (repair.LIMIT + 1), dict(os.environ))
