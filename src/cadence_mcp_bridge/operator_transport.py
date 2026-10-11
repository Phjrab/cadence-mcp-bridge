"""Bounded internal transport for fixed operator programs, never an MCP command API."""

from __future__ import annotations

import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any

_FIXED_LIMIT = 1048576
_REPAIR_INVENTORY_LIMIT = 16777216


def run_fixed(
    argv: list[str],
    request: bytes,
    environment: dict[str, str],
    *,
    timeout: float = 30,
    limit: int = 32768,
) -> tuple[int, bytes, bytes]:
    return _run_bounded(argv, request, environment, timeout, limit, _FIXED_LIMIT)


def run_repair_inventory(
    argv: list[str], request: bytes, environment: dict[str, str]
) -> tuple[int, bytes, bytes]:
    """Private repair inventory protocol; callers cannot vary its finite bounds."""
    return _run_bounded(
        argv, request, environment, 60, _REPAIR_INVENTORY_LIMIT, _REPAIR_INVENTORY_LIMIT
    )


def _run_bounded(
    argv: list[str],
    request: bytes,
    environment: dict[str, str],
    timeout: float,
    limit: int,
    ceiling: int,
) -> tuple[int, bytes, bytes]:
    if len(request) > limit or not 1 <= limit <= ceiling or not 0 < timeout <= 60:
        raise ValueError("fixed_transport_bounds")
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        shell=False,
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    writer = process.stdin

    def send() -> None:
        try:
            writer.write(request)
            writer.flush()
        finally:
            writer.close()

    deadline = time.monotonic() + timeout
    with ThreadPoolExecutor(max_workers=3) as pool:
        sent = pool.submit(send)
        out = pool.submit(process.stdout.read, limit + 1)
        err = pool.submit(process.stderr.read, limit + 1)
        try:
            pending: set[Future[Any]] = {sent, out, err}
            while pending:
                ready, pending = wait(
                    pending,
                    timeout=max(0.01, deadline - time.monotonic()),
                    return_when=FIRST_COMPLETED,
                )
                if not ready:
                    raise TimeoutError
                for future in ready:
                    value = future.result()
                    if isinstance(value, bytes) and len(value) > limit:
                        raise ValueError("fixed_transport_output_limit")
            stdout, stderr = out.result(), err.result()
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except (OSError, TimeoutError, subprocess.TimeoutExpired):
            raise ValueError("fixed_transport_unavailable_or_timeout") from None
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()
    return code, stdout, stderr
