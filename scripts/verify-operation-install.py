"""Installed local operation forms; fictional zero-variable circuit, no native jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path

import cadence_mcp_bridge
from cadence_mcp_bridge.designs import DesignProfile
from cadence_mcp_bridge.runtime_context import load_runtime
from cadence_mcp_bridge.variable_contracts import DesignVariables, canonical_digest


def verify(workspace: Path, examples: Path) -> dict[str, object]:
    if not Path(cadence_mcp_bridge.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError("installed wheel origin required")
    workspace.mkdir(parents=False, exist_ok=False)
    environment = json.loads((examples / "environment.json").read_bytes())
    environment["limits"].update(spectre_attempts=6, result_reserved_bytes=805306368)
    registry = json.loads((examples / "designs.json").read_bytes())
    parameterized = deepcopy(registry["designs"][0])
    parameterized["design_id"] = "synthetic-parameterized"
    parameterized["binding"]["cell"] = "SyntheticParameterized"
    parameterized["work_copy_policy"] = "owned_copy_only"
    variables = deepcopy(registry["variable_sets"][0])
    profile = registry["designs"][0]
    profile["allowed_variables"] = []
    registry["variable_sets"] = []
    digest = canonical_digest(DesignProfile.model_validate_json(json.dumps(profile)))
    for contract in registry["analysis_contracts"]:
        contract.update(design_profile_sha256=digest, variable_set_sha256=None)
    parameterized_hash = canonical_digest(
        DesignProfile.model_validate_json(json.dumps(parameterized))
    )
    variables.update(design_id="synthetic-parameterized", design_profile_sha256=parameterized_hash)
    for variable in variables["variables"]:
        variable.update(mutation_policy="fixed", default="1", fixed_value="1", step_policy="fixed")
    variable_hash = canonical_digest(DesignVariables.model_validate_json(json.dumps(variables)))
    registry["designs"].append(parameterized)
    registry["variable_sets"].append(variables)
    contract = deepcopy(registry["analysis_contracts"][0])
    contract.update(
        design_id="synthetic-parameterized",
        analysis_id="synthetic-parameterized-dc",
        design_profile_sha256=parameterized_hash,
        variable_set_sha256=variable_hash,
    )
    registry["analysis_contracts"].append(contract)
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
                design_ids=["example-amplifier", "synthetic-parameterized"],
                analyses=["dc"],
                actions=["submit"],
                numeric_regions=[
                    dict(
                        design_id="synthetic-parameterized",
                        logical_id=name,
                        unit="V",
                        minimum="1",
                        maximum="1",
                    )
                    for name in parameterized["allowed_variables"]
                ],
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
    for action in ("check-authority", "plan", "plan", "parameterized-plan", "parameterized-plan"):
        if action == "parameterized-plan":
            request.write_text(
                json.dumps(
                    dict(
                        schema_version=1,
                        design_id="synthetic-parameterized",
                        analysis_id="synthetic-parameterized-dc",
                        values=[
                            dict(logical_id=name, unit="V", value="1")
                            for name in parameterized["allowed_variables"]
                        ],
                        result_reservation_bytes=134217728,
                    )
                ),
                encoding="utf-8",
            )
            action = "plan"
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
    assert plans[0] == plans[1] and plans[2] == plans[3] and plans[0] != plans[2]
    assert not list(workspace.glob("*.sqlite3")) and not list(workspace.glob("*.lock"))
    from uuid import uuid4

    from cadence_mcp_bridge.analysis_store import AnalysisStore
    from cadence_mcp_bridge.operator_operations import OperationPlan

    durable_plan = OperationPlan.model_validate_json(json.dumps(report["plan"]))
    synthetic_id = str(uuid4())
    store = AnalysisStore(context.binding.analysis_journal)
    assert store.admit_operation(synthetic_id, durable_plan)
    before = store.path.read_bytes()
    observed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-m",
            "cadence_mcp_bridge",
            "operation",
            "journal-status",
            "--settings",
            str(settings),
            "--context",
            "installed-operation",
            "--operation-id",
            synthetic_id,
            "--expected-plan-sha256",
            durable_plan.plan_sha256,
        ],
        cwd=workspace,
        env=env,
        capture_output=True,
        timeout=30,
        check=True,
    )
    cached = json.loads(observed.stdout)
    assert cached["progress"]["phase"] == "ADMITTED" and not cached["remote_contact"]
    assert store.path.read_bytes() == before and str(workspace) not in observed.stdout.decode()

    return {
        "status": "PASS",
        "evidence": "INSTALLED_OPERATION_FORMS_SYNTHETIC",
        "durable_admission": "NOT_RUN",
        "native_dispatch": "NOT_RUN",
        "repeat_plan_identity": True,
        "same_grant_distinct_design_variable_sets": 2,
        "cached_lifecycle_metadata": "LOCAL_SYNTHETIC_NOT_REMOTE_AUTHORITY",
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
