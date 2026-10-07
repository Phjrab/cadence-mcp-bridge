"""Installed local operation forms; fictional zero-variable circuit, no native jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import cadence_mcp_bridge
from cadence_mcp_bridge.designs import DesignProfile
from cadence_mcp_bridge.runtime_context import load_runtime
from cadence_mcp_bridge.variable_contracts import canonical_digest


def verify(workspace: Path, examples: Path) -> dict[str, object]:
    if not Path(cadence_mcp_bridge.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError("installed wheel origin required")
    workspace.mkdir(parents=False, exist_ok=False)
    environment = json.loads((examples / "environment.json").read_bytes())
    environment["limits"].update(spectre_attempts=6, result_reserved_bytes=805306368)
    registry = json.loads((examples / "designs.json").read_bytes())
    profile = registry["designs"][0]
    profile["allowed_variables"] = []
    registry["variable_sets"] = []
    digest = canonical_digest(DesignProfile.model_validate_json(json.dumps(profile)))
    for contract in registry["analysis_contracts"]:
        contract.update(design_profile_sha256=digest, variable_set_sha256=None)
    pdk = json.loads((examples / "pdks.json").read_bytes())
    paths = [workspace / (name + ".json") for name in ("environment", "design", "pdk")]
    for path, payload in zip(paths, (environment, registry, pdk), strict=True):
        path.write_text(json.dumps(payload), encoding="utf-8")
    binding = dict(
        context_id="installed-operation",
        environment_profile=str(paths[0]),
        environment_sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest(),
        design_registry=str(paths[1]),
        design_sha256=hashlib.sha256(paths[1].read_bytes()).hexdigest(),
        pdk_registry=str(paths[2]),
        pdk_sha256=hashlib.sha256(paths[2].read_bytes()).hexdigest(),
        runner_sha256="b" * 64,
        authority_ref="fictional-record",
        ledger_ref="fictional-existing",
        analysis_journal=str(workspace / "analysis.sqlite3"),
        sweep_journal=str(workspace / "sweep.sqlite3"),
    )
    settings = workspace / "runtime.json"
    settings.write_text(
        json.dumps(dict(schema_version=1, resource_state_root=str(workspace), contexts=[binding])),
        encoding="utf-8",
    )
    context = load_runtime(settings)[0]
    grant = workspace / "authority.json"
    grant.write_text(
        json.dumps(
            dict(
                schema_version=1,
                grant_id="fictional-record",
                authorization_source="explicit_operator_record",
                resource_domain_sha256=context.resource_domain_sha256,
                runner_sha256="b" * 64,
                ledger_ref="fictional-existing",
                environment_sha256=binding["environment_sha256"],
                design_sha256=binding["design_sha256"],
                pdk_sha256=binding["pdk_sha256"],
                design_ids=["example-amplifier"],
                analyses=["dc"],
                actions=["submit"],
                numeric_regions=[],
                attempt_limit=6,
                result_reserved_bytes_limit=805306368,
                valid_from_unix=1,
                valid_until_unix=int(time.time()) + 3600,
                status="active",
            )
        ),
        encoding="utf-8",
    )
    request = workspace / "request.json"
    request.write_text(
        json.dumps(
            dict(
                schema_version=1,
                design_id="example-amplifier",
                analysis_id="example-dc",
                values=[],
                result_reservation_bytes=134217728,
            )
        ),
        encoding="utf-8",
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.upper().startswith("CADENCE_MCP_")
        and k.upper() not in ("PYTHONPATH", "PYTHONHOME")
    }
    arguments = [
        "--settings",
        str(settings),
        "--context",
        "installed-operation",
        "--grant",
        str(grant),
        "--expected-grant-sha256",
        hashlib.sha256(grant.read_bytes()).hexdigest(),
    ]
    plans = []
    for action in ("check-authority", "plan", "plan"):
        args = arguments + (["--request", str(request)] if action == "plan" else [])
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-X",
                "utf8",
                "-m",
                "cadence_mcp_bridge",
                "operation",
                action,
                *args,
            ],
            cwd=workspace,
            env=env,
            capture_output=True,
            timeout=30,
            check=True,
        )
        report = json.loads(result.stdout)
        assert not report["execution_authorized"] and not report["remote_contact"]
        assert str(workspace) not in result.stdout.decode("utf-8")
        if action == "plan":
            assert not report["dispatch_eligible"] and not report["admission_created"]
            plans.append(report["plan_sha256"])
    assert plans[0] == plans[1]
    assert not list(workspace.glob("*.sqlite3")) and not list(workspace.glob("*.lock"))
    return {
        "status": "PASS",
        "evidence": "INSTALLED_OPERATION_FORMS_SYNTHETIC",
        "durable_admission": "NOT_RUN",
        "native_dispatch": "NOT_RUN",
        "repeat_plan_identity": True,
        "execution_authorized": False,
        "remote_contact": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--examples", type=Path, required=True)
    arguments = parser.parse_args()
    print(
        json.dumps(
            verify(arguments.workspace.resolve(), arguments.examples.resolve()), sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
