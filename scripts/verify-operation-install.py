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
    from cadence_mcp_bridge.analyses import AnalysisContract

    registry["schema_version"] = 4
    registry["measurement_contracts"] = [
        dict(
            design_id=c["design_id"],
            measurement_id="dc-output" if c["analysis"] == "dc" else "ac-gain",
            analysis_id=c["analysis_id"],
            analysis_contract_sha256=canonical_digest(
                AnalysisContract.model_validate_json(json.dumps(c))
            ),
            reader="unqualified",
            output_id=None,
            definition_sha256=None,
        )
        for c in registry["analysis_contracts"]
        if c["analysis"] in ("dc", "ac")
    ]
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
        ledger_ref="shared-ledger",
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
                ledger_ref="shared-ledger",
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

    # Exercise generic artifacts from the installed wheel for two independent
    # fictional topologies. This is not OA/ADE/native qualification.
    from cadence_mcp_bridge.generic_ade import static_fingerprint
    from cadence_mcp_bridge.operator_operations import OperationRequest, prepare_plan

    templates = []
    for design_id, analysis_id, static_lines in (
        (
            "example-amplifier",
            "example-dc",
            ["R0 (in out) resistor r=1000", "C0 (out 0) capacitor c=0.000001"],
        ),
        (
            "synthetic-parameterized",
            "synthetic-parameterized-dc",
            ["M0 (out gate 0 0) nch w=0.000002 l=0.0000001", "V0 (gate 0) vsource dc=1"],
        ),
    ):
        profile_model = context.contracts.designs.profile(design_id)
        variable_model = context.contracts.designs.variable_set(design_id)
        request_model = OperationRequest.model_validate_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "design_id": design_id,
                    "analysis_id": analysis_id,
                    "values": [
                        {"logical_id": name, "unit": "V", "value": "1"}
                        for name in profile_model.allowed_variables
                    ],
                    "result_reservation_bytes": 134217728,
                }
            )
        )
        from cadence_mcp_bridge.operator_operations import load_grant

        loaded_grant, grant_digest = load_grant(
            grant, hashlib.sha256(grant.read_bytes()).hexdigest()
        )
        input_plan = prepare_plan(
            context, loaded_grant, grant_digest, request_model, int(time.time())
        )
        input_request = workspace / (design_id + "-request.json")
        input_request.write_text(request_model.model_dump_json(), encoding="utf-8")
        registration = workspace / (design_id + "-ade.json")
        registration.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "design_id": design_id,
                    "analysis_id": analysis_id,
                    "design_profile_sha256": canonical_digest(profile_model),
                    "variable_set_sha256": canonical_digest(variable_model)
                    if variable_model
                    else None,
                    "source_tree_sha256": "1" * 64,
                    "ade_state_tree_sha256": "2" * 64,
                    "static_statements_sha256": static_fingerprint(static_lines),
                    "model_includes": [],
                    "inputs": {
                        "analysis": "dc",
                        "mode": "saved_operating_point",
                        "statement_sha256": hashlib.sha256(b"dc save=all").hexdigest(),
                    },
                }
            ),
            encoding="utf-8",
        )
        # Original zero-variable fixture is a read-only description; compilation
        # must reject it rather than silently broadening its copy policy.
        input_args = [
            *arguments,
            "--request",
            str(input_request),
            "--registration",
            str(registration),
            "--expected-registration-sha256",
            hashlib.sha256(registration.read_bytes()).hexdigest(),
            "--operation-id",
            str(uuid4()),
            "--expected-plan-sha256",
            input_plan.plan_sha256,
        ]
        output = workspace / (design_id + "-ade-inputs")
        compiled = subprocess.run(
            [
                sys.executable,
                "-I",
                "-X",
                "utf8",
                "-m",
                "cadence_mcp_bridge",
                "ade-input",
                "compile",
                *input_args,
                "--output",
                str(output),
            ],
            cwd=workspace,
            env=env,
            capture_output=True,
            timeout=30,
        )
        receipt = json.loads(compiled.stdout)
        if profile_model.work_copy_policy != "owned_copy_only":
            assert compiled.returncode == 1 and not output.exists()
            assert receipt["reason"] == "ade_subtype_or_copy_policy_unsupported"
            continue
        assert compiled.returncode == 0 and not receipt["execution_authorized"]
        assert json.loads((output / "manifest.json").read_bytes()) == receipt
        templates.append(receipt["template_sha256"])
        native_input = workspace / (design_id + "-synthetic.scs")
        params = "parameters " + " ".join(
            v.cadence_binding + "=1" for v in variable_model.variables
        )
        native_input.write_text(
            "simulator lang=spectre\n"
            + params
            + "\n"
            + "\n".join(static_lines)
            + "\nanalysis0 dc save=all\n",
            encoding="ascii",
        )
        matched = subprocess.run(
            [
                sys.executable,
                "-I",
                "-X",
                "utf8",
                "-m",
                "cadence_mcp_bridge",
                "ade-input",
                "verify-input",
                *input_args,
                "--native-input",
                str(native_input),
            ],
            cwd=workspace,
            env=env,
            capture_output=True,
            timeout=30,
            check=True,
        )
        verified = json.loads(matched.stdout)
        assert verified["status"] == "LOCAL_EFFECTIVE_INPUT_MATCHED"
        assert not verified["native_source_copy_attested"] and not verified["remote_contact"]
        assert str(workspace) not in matched.stdout.decode()
        # Compile/project through the isolated installed CLI, never execute OCEAN.
        from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration
        from cadence_mcp_bridge.generic_measurements import GenericReaderRegistration

        ade_model = AdeExecutionRegistration.model_validate_json(registration.read_bytes())
        reader_model = GenericReaderRegistration.model_validate_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "design_id": design_id,
                    "analysis_id": analysis_id,
                    "measurement_id": profile_model.allowed_measurements[0],
                    "ade_registration_sha256": canonical_digest(ade_model),
                    "measurement_contract_sha256": canonical_digest(
                        next(
                            m
                            for m in context.contracts.designs.measurements_for(design_id)
                            if m.analysis_id == analysis_id
                        )
                    ),
                    "nodes": [
                        {"logical_id": "input", "selector": "/gate"},
                        {"logical_id": "output", "selector": "/out"},
                    ],
                    "sources": [
                        {
                            "source_id": "rail",
                            "role": "supply",
                            "positive_node": "input",
                            "negative_node": None,
                            "current_selector": "/V0/PLUS",
                            "current_convention": "positive_into_source_positive_terminal_A",
                        }
                    ],
                    "transfer": None,
                    "maximum_samples": 256,
                }
            )
        )
        # Installed package exports the same fixed provider/worker inventory.
        # This step creates local artifacts only; it cannot confirm or dispatch.
        from cadence_mcp_bridge import _native_dispatch
        from cadence_mcp_bridge.native_runtime import SOURCES

        native_registration = workspace / (design_id + "-native-registration.json")
        library = profile_model.binding.library
        remote_workspace = context.contracts.environment.paths.workspace_root
        native_registration.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "identity_manifest_sha256": "a" * 64,
                    "routes": [
                        {
                            "validation_request": request_model.model_dump(mode="json"),
                            "ade": ade_model.model_dump(mode="json"),
                            "reader": reader_model.model_dump(mode="json"),
                            "source_cell": remote_workspace
                            + "/"
                            + library
                            + "/"
                            + profile_model.binding.cell,
                            "source_state": remote_workspace + "/fictional-state",
                            "libraries": [
                                {
                                    "name": library,
                                    "path": remote_workspace + "/" + library,
                                    "tree_sha256": "b" * 64,
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="ascii",
        )
        native_output = workspace / (design_id + "-native-runtime")
        native_export = subprocess.run(
            [
                sys.executable,
                "-I",
                "-X",
                "utf8",
                "-m",
                "cadence_mcp_bridge",
                "native-runtime",
                "bundle",
                "--settings",
                str(settings),
                "--context",
                "installed-operation",
                "--registration",
                str(native_registration),
                "--output",
                str(native_output),
            ],
            cwd=workspace,
            env=env,
            capture_output=True,
            timeout=30,
            check=True,
        )
        native_receipt = json.loads(native_export.stdout)
        native_manifest_raw = (native_output / "manifest.json").read_bytes()
        native_manifest = json.loads(native_manifest_raw)
        assert native_receipt["manifest_sha256"] == hashlib.sha256(native_manifest_raw).hexdigest()
        assert native_receipt["asset_count"] == len(_native_dispatch.FILES)
        assert not native_receipt["execution_authorized"] and not native_receipt["remote_contact"]
        assert set(native_manifest["files"]) == set(_native_dispatch.FILES)
        from importlib.resources import files

        for name, source in SOURCES.items():
            assert (native_output / name).read_bytes() == files("cadence_mcp_bridge").joinpath(
                source
            ).read_bytes()
        assert store.path.read_bytes() == before

        reader_path = workspace / (design_id + "-reader.json")
        reader_path.write_text(reader_model.model_dump_json(), encoding="ascii")
        plan_path = workspace / (design_id + "-plan.json")
        plan_path.write_text(input_plan.model_dump_json(), encoding="ascii")
        operation_id = input_args[input_args.index("--operation-id") + 1]
        reader_args = [
            "--settings",
            str(settings),
            "--context",
            "installed-operation",
            "--plan",
            str(plan_path),
            "--expected-plan-sha256",
            input_plan.plan_sha256,
            "--ade-registration",
            str(registration),
            "--expected-ade-sha256",
            canonical_digest(ade_model),
            "--reader-registration",
            str(reader_path),
            "--expected-reader-sha256",
            canonical_digest(reader_model),
            "--operation-id",
            operation_id,
            "--execution-input-sha256",
            receipt["execution_input_sha256"],
        ]
        reader_output = workspace / (design_id + "-reader-output")
        prepared = subprocess.run(
            [
                sys.executable,
                "-I",
                "-X",
                "utf8",
                "-m",
                "cadence_mcp_bridge",
                "result-reader",
                "compile",
                *reader_args,
                "--output",
                str(reader_output),
            ],
            cwd=workspace,
            env=env,
            capture_output=True,
            timeout=30,
            check=True,
        )
        assert not json.loads(prepared.stdout)["execution_authorized"]
        frame_path = workspace / (design_id + "-frame.txt")
        header = "|".join(
            (
                "MCP_GREL_FRAME",
                "1",
                operation_id,
                input_plan.plan_sha256,
                receipt["execution_input_sha256"],
                canonical_digest(reader_model),
            )
        )
        frame_path.write_text(
            header + "\nV|input|1\nV|output|0.5\nI|rail|-0.001\nEND\n", encoding="ascii"
        )
        projected = subprocess.run(
            [
                sys.executable,
                "-I",
                "-X",
                "utf8",
                "-m",
                "cadence_mcp_bridge",
                "result-reader",
                "project-frame",
                *reader_args,
                "--frame",
                str(frame_path),
            ],
            cwd=workspace,
            env=env,
            capture_output=True,
            timeout=30,
            check=True,
        )
        result = json.loads(projected.stdout)
        assert result["power"]["supply_w"] == 0.001
        assert result["native_provenance"] == "NOT_ATTESTED" and not result["remote_contact"]
        assert str(workspace) not in projected.stdout.decode()
    assert len(templates) == 1 and store.path.read_bytes() == before

    confirmation_output = workspace / "confirmation-helper"
    exported = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-m",
            "cadence_mcp_bridge",
            "operator-authority",
            "export-helper",
            "--output",
            str(confirmation_output),
        ],
        cwd=workspace,
        env=env,
        capture_output=True,
        timeout=30,
        check=True,
    )
    exported_receipt = json.loads(exported.stdout)
    from cadence_mcp_bridge.operator_confirmation import contents as confirmation_contents

    assets, manifest, helper_sha = confirmation_contents()
    assert exported_receipt["manifest_sha256"] == helper_sha
    assert not exported_receipt["execution_authorized"] and not exported_receipt["remote_contact"]
    assert (confirmation_output / "manifest.json").read_bytes() == manifest
    assert all((confirmation_output / name).read_bytes() == data for name, data in assets.items())
    assert store.path.read_bytes() == before

    from cadence_mcp_bridge import _native_copy

    copy_source = workspace / "synthetic-owned-source"
    copy_source.mkdir(mode=0o700)
    (copy_source / "state").mkdir(mode=0o700)
    (copy_source / "state" / "variables").write_bytes(b"synthetic state bytes")
    copy_parent = workspace / "synthetic-job"
    copy_parent.mkdir(mode=0o700)
    source_before = _native_copy.snapshot(str(copy_source.resolve()))
    copied_receipt = _native_copy.copy_owned(
        str(copy_source.resolve()),
        str((copy_parent / "copy").resolve()),
        source_before["tree_sha256"],
    )
    assert copied_receipt["source_preserved"]
    assert copied_receipt["copy_content_sha256"] == source_before["content_sha256"]
    assert _native_copy.snapshot(str(copy_source.resolve())) == source_before
    assert store.path.read_bytes() == before

    # Exercise the installed parser and bounded pre-contact failure. No SSH or admission.
    for action in ("submit", "reconcile", "cancel-pending", "result"):
        documented = subprocess.run(
            [sys.executable, "-I", "-m", "cadence_mcp_bridge", "operation", action, "--help"],
            cwd=workspace,
            env=env,
            capture_output=True,
            timeout=30,
            check=True,
        )
        assert b"--provider-binding" in documented.stdout
        provider_path = workspace / "invalid-provider.json"
        provider_path.write_bytes(b"{}")
        argv = [
            sys.executable,
            "-I",
            "-m",
            "cadence_mcp_bridge",
            "operation",
            action,
            "--settings",
            str(settings),
            "--context",
            "installed-operation",
            "--provider-binding",
            str(provider_path),
            "--expected-provider-sha256",
            "0" * 64,
            "--operation-id",
            operation_id,
            "--expected-plan-sha256",
            input_plan.plan_sha256,
        ]
        if action in ("submit", "cancel-pending"):
            argv.extend(["--grant", str(grant), "--expected-grant-sha256", "0" * 64])
        if action == "submit":
            argv.extend(["--request", str(plan_path)])
        denied = subprocess.run(argv, cwd=workspace, env=env, capture_output=True, timeout=30)
        assert denied.returncode == 1 and not denied.stderr
        assert json.loads(denied.stdout)["reason"] == "native_operator_binding_changed"
        assert store.path.read_bytes() == before

    # Installed stdio conditional tools and local plan; fictional runtime only.
    from cadence_mcp_bridge.authenticated_provider import NativeProviderBinding

    selected_provider = workspace / "selected-provider.json"
    selected_provider.write_bytes(
        NativeProviderBinding(
            schema_version=1,
            identity_manifest_sha256="a" * 64,
            runtime_manifest_sha256=context.binding.runner_sha256,
        )
        .model_dump_json()
        .encode("ascii")
    )
    configured = json.loads(settings.read_bytes())
    configured["contexts"][0].update(
        native_provider_binding=str(selected_provider),
        native_provider_sha256=hashlib.sha256(selected_provider.read_bytes()).hexdigest(),
        operator_grant=str(grant),
        operator_grant_sha256=hashlib.sha256(grant.read_bytes()).hexdigest(),
    )
    native_settings = workspace / "native-service.json"
    native_settings.write_text(json.dumps(configured), encoding="ascii")

    async def native_stdio() -> None:
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters

        configured_env = {
            **env,
            "CADENCE_MCP_RUNTIME_SETTINGS_PATH": str(native_settings),
            "CADENCE_MCP_RUNTIME_CONTEXT_ID": "installed-operation",
        }
        params = StdioServerParameters(
            command=sys.executable,
            args=["-I", "-m", "cadence_mcp_bridge", "serve-operator"],
            env=configured_env,
            cwd=str(workspace),
        )
        for _ in range(2):
            async with Client(params) as client:
                tools = (await client.list_tools()).tools
                names = {tool.name for tool in tools}
                assert len(names) == 96 and "cadence_submit_operation" in names
                planned = await client.call_tool(
                    "cadence_plan_operation",
                    {"request": input_plan.request.model_dump(mode="json")},
                )
                assert not planned.is_error and planned.structured_content is not None
                assert planned.structured_content["plan_sha256"] == input_plan.plan_sha256
                assert not planned.structured_content["remote_contact"]
            assert store.path.read_bytes() == before

    import asyncio

    asyncio.run(native_stdio())

    return {
        "status": "PASS",
        "evidence": "INSTALLED_OPERATION_FORMS_SYNTHETIC",
        "durable_admission": "NOT_RUN",
        "installed_conditional_native_stdio": "PASS96_SCHEMA_LOCAL_PLAN_RESTART_NO_TRANSPORT",
        "installed_native_operation_forms": "PASS_PARSE_AND_PRECONTACT_DENIAL_ONLY",
        "installed_confirmation_helper_export": "PASS_LOCAL_NO_AUTHORITY_OR_SSH",
        "installed_owned_copy": "SYNTHETIC_FILES_ONLY_NOT_NATIVE_OA",
        "native_dispatch": "NOT_RUN",
        "repeat_plan_identity": True,
        "same_grant_distinct_design_variable_sets": 2,
        "installed_generic_ade_compile_and_effective_input": "SYNTHETIC_PASS",
        "installed_generic_reader_compile_and_frame": "SYNTHETIC_NATIVE_UNATTESTED_PASS",
        "read_only_design_compile": "REJECTED",
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
