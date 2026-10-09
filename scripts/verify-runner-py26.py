"""Fixed current-host grammar check of shipped runner assets; no execution or writes."""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import subprocess
from importlib.resources import files
from pathlib import Path

from cadence_mcp_bridge.ssh_backend import OpenSshBackend

ASSETS = (
    "_runner_bootstrap.py",
    "_generic_runner.py",
    "_runner_launcher.py",
    "_runner_trust.py",
    "_shared_reservations.py",
)
CHECK = (
    "import ast,sys; data=sys.stdin.read(262145); assert len(data)<=262144; "
    "ast.parse(data); sys.stdout.write('PY26_SYNTAX_OK')"
)


def main() -> None:
    executable = shutil.which("ssh.exe")
    if executable is None:
        raise RuntimeError("OpenSSH missing")
    results = []
    for name in ASSETS:
        data = files("cadence_mcp_bridge").joinpath(name).read_bytes()
        process = subprocess.run(
            [
                executable,
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "ConnectTimeout=10",
                "cadence-vm",
                "/usr/bin/python",
                "-B",
                "-c",
                shlex.quote(CHECK),
            ],
            input=data.replace(b"\r\n", b"\n"),
            capture_output=True,
            timeout=30,
            env=OpenSshBackend._ssh_environment(),
            check=False,
        )
        if process.returncode != 0 or process.stdout != b"PY26_SYNTAX_OK" or process.stderr:
            Path(".tmp/runner-py26-rejection.txt").write_bytes(process.stderr)
            raise RuntimeError("Fixed runtime grammar check rejected: " + name)
        results.append({"asset": name, "sha256": hashlib.sha256(data).hexdigest()})
    print(
        json.dumps(
            {
                "status": "PASS",
                "scope": "ACTUAL_PY26_SYNTAX_ONLY_NO_ASSET_EXECUTION",
                "assets": results,
                "new_simulations": 0,
                "remote_writes": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
