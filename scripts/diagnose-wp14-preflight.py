"""Fixed read-only preflight diagnostic; never invokes the runner or deployment."""

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 1:
        return 2
    path = Path(__file__).with_name("collect-wp14-remote-preimages.py")
    digest = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
    if digest != "b0bbcd9823e561805c1979b9e1eca3b79f96a4d0126e9c8aa32fe1db0427cc7c":
        return 2
    spec = importlib.util.spec_from_file_location("bounded_transport", path)
    assert spec and spec.loader
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    # Separate diagnostic: preserves the consumed deployment authorization/claim.
    # Reuses only bounded transport, not collector activation or collection operations.
    checks = [
        ("HOST", 'test "$(hostname)" = cadence'),
        ("USER", 'test "$(id -un)" = buet'),
        ("NO_CADENCE_PROCESS", "! ps -ef | grep -E '[v]irtuoso|[o]cean' >/dev/null"),
        ("ROOT", "test -d /home/buet/cds_work/.cadence_mcp"),
        ("RUNNER_EXECUTABLE", "test -x /home/buet/cds_work/.cadence_mcp/bin/cadence-runner"),
        (
            "SNAPSHOT_ABSENT",
            "test ! -e /home/buet/cds_work/.cadence_mcp/deployment-snapshots/"
            "wp14-7d93fefb-runner-0.19.0",
        ),
    ]
    for name in (
        "bin",
        "lib",
        "py26",
        "discovery",
        "config",
        "profiles/actual-differential-amplifier-tb2-transient",
    ):
        checks.append(
            ("PARENT_" + str(len(checks)), "test -d /home/buet/cds_work/.cadence_mcp/" + name)
        )
    command = "set -f; export LC_ALL=C; " + "; ".join(
        "if "
        + check
        + "; then printf '"
        + label
        + "=PASS\\n'; else printf '"
        + label
        + "=FAIL\\n'; fi"
        for label, check in checks
    )
    try:
        raw = transport._invoke_bounded_ssh(command, datetime.now(UTC) + timedelta(seconds=60))
        lines = raw.decode("utf-8", errors="strict").splitlines()
        if len(lines) != len(checks):
            raise ValueError("Unexpected result size")
        result = {}
        for (label, _), line in zip(checks, lines, strict=True):
            if line not in (label + "=PASS", label + "=FAIL"):
                raise ValueError("Unexpected result")
            result[label] = line.split("=", 1)[1]
        print(json.dumps({"observed_at": datetime.now(UTC).isoformat(), "checks": result}))
        return 0
    except Exception:
        print('{"status":"DIAGNOSTIC_TRANSPORT_OR_SCHEMA_FAILED"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
