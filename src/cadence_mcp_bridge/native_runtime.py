"""Operator-only immutable native bundle construction. No remote writes or grants."""

from __future__ import annotations

import base64
import hashlib
import json
import shlex
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge import _native_setup as setup
from cadence_mcp_bridge import _runner_bootstrap as installer
from cadence_mcp_bridge.authenticated_provider import NativeProviderBinding
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.environments import EnvironmentModel, load_environment
from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration, bind_inputs
from cadence_mcp_bridge.generic_measurements import GenericReaderRegistration, bind_reader
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.operator_operations import (
    OperationPlan,
    OperationRejected,
    OperationRequest,
    bounded_document,
)
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import BindingName, Digest

RemotePath = Annotated[str, Field(pattern=r"^/[A-Za-z0-9_#./-]{1,511}$", max_length=512)]
SOURCES = {
    "provider.py": "_native_dispatch.py",
    "operations.py": "_native_operations.py",
    "gate.py": "_native_gate.py",
    "worker.py": "_native_eda_worker.py",
    "rendering.py": "_native_rendering.py",
    "copying.py": "_native_copy.py",
    "confirmation.py": "_operator_confirmation.py",
    "reservations.py": "_shared_reservations.py",
    "installer.py": "_runner_bootstrap.py",
    "probe.py": "_environment_probe.py",
    "storage.py": "_storage_worker.py",
}
KIND = "STANDARD_VM_CONFIRMED_NATIVE_RUNTIME"


class NativeLibrary(EnvironmentModel):
    name: BindingName
    path: RemotePath

    @model_validator(mode="after")
    def canonical(self) -> Self:
        if str(PurePosixPath(self.path)) != self.path or ".." in PurePosixPath(self.path).parts:
            raise ValueError("canonical library path required")
        if self.name == "MCP_GREL_Work":
            raise ValueError("owned library collision")
        return self


class NativeRoute(EnvironmentModel):
    # Explicit local values validate compiler binding only; never a dispatch.
    validation_request: OperationRequest
    ade: AdeExecutionRegistration
    reader: GenericReaderRegistration
    source_cell: RemotePath
    source_state: RemotePath
    libraries: Annotated[tuple[NativeLibrary, ...], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def canonical(self) -> Self:
        for source in (self.source_cell, self.source_state):
            if str(PurePosixPath(source)) != source or ".." in PurePosixPath(source).parts:
                raise ValueError("canonical source path required")
        if len({lib.name for lib in self.libraries}) != len(self.libraries):
            raise ValueError("duplicate library name")
        return self


class NativeRegistration(EnvironmentModel):
    schema_version: Literal[1]
    identity_manifest_sha256: Digest
    routes: Annotated[tuple[NativeRoute, ...], Field(min_length=1, max_length=48)]

    @model_validator(mode="after")
    def distinct(self) -> Self:
        identities = [(r.ade.design_id, r.ade.analysis_id) for r in self.routes]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate native route")
        return self


def projection(context: ExecutionContext, registration: NativeRegistration) -> dict[str, object]:
    if context.binding.ledger_ref != "shared-ledger":
        raise OperationRejected("native_runtime_logical_ledger_required")
    routes: list[dict[str, object]] = []
    environment = context.contracts.environment
    for route in registration.routes:
        # A compiler-only plan checks the existing closed registrations. Its
        # zero grant hash is never written as confirmation or sent to a runner.
        plan = OperationPlan(
            resource_domain_sha256=context.resource_domain_sha256,
            runner_sha256=context.binding.runner_sha256,
            ledger_ref=context.binding.ledger_ref,
            environment_sha256=context.binding.environment_sha256,
            design_sha256=context.binding.design_sha256,
            pdk_sha256=context.binding.pdk_sha256,
            grant_sha256="0" * 64,
            request=route.validation_request,
            analysis=route.ade.inputs.analysis,
        )
        bind_inputs(context, plan, route.ade)
        bind_reader(context, plan, route.ade, route.reader)
        profile = context.contracts.designs.profile(route.ade.design_id)
        source_library = next(
            (lib for lib in route.libraries if lib.name == profile.binding.library), None
        )
        if (
            source_library is None
            or route.source_cell != source_library.path + "/" + profile.binding.cell
        ):
            raise OperationRejected("native_runtime_source_library_binding")
        for source in (route.source_cell, route.source_state):
            if PurePosixPath(source).is_relative_to(environment.paths.managed_root) or any(
                PurePosixPath(source).is_relative_to(root)
                for root in environment.paths.protected_roots
            ):
                raise OperationRejected("native_runtime_source_inside_runtime_or_vendor")
        if any(
            not PurePosixPath(source).is_relative_to(environment.paths.workspace_root)
            for source in (route.source_cell, route.source_state)
        ):
            raise OperationRejected("native_runtime_source_outside_workspace")
        for library in route.libraries:
            if not any(
                PurePosixPath(library.path).is_relative_to(root)
                for root in (
                    environment.paths.workspace_root,
                    *environment.paths.protected_roots,
                )
            ) or PurePosixPath(library.path).is_relative_to(environment.paths.managed_root):
                raise OperationRejected("native_runtime_library_outside_registered_roots")
        variable_set = context.contracts.designs.variable_set(profile.design_id)
        routes.append(
            {
                "design_id": route.ade.design_id,
                "analysis_id": route.ade.analysis_id,
                "analysis": route.ade.inputs.analysis,
                "profile": profile.model_dump(mode="json"),
                "variables": []
                if variable_set is None
                else [v.model_dump(mode="json") for v in variable_set.variables],
                "source_cell": route.source_cell,
                "source_state": route.source_state,
                "libraries": [lib.model_dump(mode="json") for lib in route.libraries],
                "ade": route.ade.model_dump(mode="json"),
                "reader": route.reader.model_dump(mode="json"),
            }
        )
    return {
        "schema_version": 1,
        "identity_manifest_sha256": registration.identity_manifest_sha256,
        "environment_sha256": context.binding.environment_sha256,
        "design_sha256": context.binding.design_sha256,
        "pdk_sha256": context.binding.pdk_sha256,
        "routes": sorted(routes, key=lambda r: (str(r["design_id"]), str(r["analysis_id"]))),
    }


def bundle(context: ExecutionContext, registration_path: Path, output: Path) -> dict[str, object]:
    registration = NativeRegistration.model_validate_json(bounded_document(registration_path))
    environment, profile_raw = load_environment(context.binding.environment_profile)
    if hashlib.sha256(profile_raw).hexdigest() != context.binding.environment_sha256:
        raise OperationRejected("native_runtime_environment_changed")
    compiled = projection(context, registration)
    assets = {
        name: files("cadence_mcp_bridge").joinpath(source).read_bytes()
        for name, source in SOURCES.items()
    }
    assets.update({"profile.json": profile_raw, "registration.json": _canonical(compiled)})
    manifest = {
        "schema_version": 3,
        "kind": KIND,
        "environment_id": environment.environment_id,
        "profile_sha256": context.binding.environment_sha256,
        "registration_sha256": hashlib.sha256(assets["registration.json"]).hexdigest(),
        "files": {
            name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            for name, raw in assets.items()
        },
    }
    raw = _canonical(manifest)
    expected = hashlib.sha256(raw).hexdigest()
    target = _local_path(output)
    if target.exists() or not target.parent.is_dir():
        raise OperationRejected("native_runtime_exclusive_output_required")
    target.mkdir(mode=0o700)
    for name, data in {**assets, "manifest.json": raw}.items():
        installer.exclusive(str(target / name), data)  # type: ignore[no-untyped-call]
    binding = NativeProviderBinding(
        schema_version=1,
        identity_manifest_sha256=registration.identity_manifest_sha256,
        runtime_manifest_sha256=expected,
    )
    return {
        "status": "NATIVE_RUNTIME_BUNDLE_PREPARED_LOCAL_NOT_INSTALLED",
        "manifest_sha256": expected,
        "provider_binding": binding.model_dump(mode="json"),
        "asset_count": len(assets),
        "content_bytes": sum(len(v) for v in assets.values()),
        "execution_authorized": False,
        "remote_contact": False,
    }


class NativeSetupRemoteRejected(OperationRejected):
    remote_contact = True


def setup_runtime(
    local_bundle: Path, expected: str, action: str, operator_authority: str | None = None
) -> dict[str, object]:
    if action not in ("stage", "activate", "inspect", "revoke"):
        raise OperationRejected("native_setup_fixed_action")
    target = _local_path(local_bundle)
    if not target.is_dir() or {p.name for p in target.iterdir()} != set(
        setup.FILES + ("manifest.json",)
    ):
        raise OperationRejected("native_setup_bundle_inventory")
    assets: dict[str, bytes] = {
        name: installer.regular(str(_local_path(target / name)))  # type: ignore[no-untyped-call]
        for name in (*setup.FILES, "manifest.json")
    }
    known = {
        name: hashlib.sha256(files("cadence_mcp_bridge").joinpath(source).read_bytes()).hexdigest()
        for name, source in SOURCES.items()
    }
    # All source assets must match this installed package before any contact.
    manifest, profile, registration = setup.inventory(assets, expected, known)  # type: ignore[no-untyped-call]
    environment, raw_profile = load_environment(target / "profile.json")
    if raw_profile != assets["profile.json"]:
        raise OperationRejected("native_setup_profile_drift")
    if action == "inspect":
        if operator_authority is not None:
            raise OperationRejected("native_setup_inspection_authority")
    else:
        from cadence_mcp_bridge import _operator_confirmation

        _operator_confirmation.authority_reference(operator_authority)  # type: ignore[no-untyped-call]
    request = _canonical(
        {
            "schema_version": 1,
            "action": action,
            "manifest_sha256": expected,
            "operator_authority": operator_authority,
            "files": {name: base64.b64encode(raw).decode("ascii") for name, raw in assets.items()},
        }
    )
    # The hash map is compiled from package resources, never caller JSON/code.
    code = files("cadence_mcp_bridge").joinpath("_native_setup.py").read_text("utf-8")
    code += "\nmain(" + repr(known) + ")\n"
    argv = _ssh(environment) + ["-c", shlex.quote(code), expected]
    try:
        status, stdout, stderr = run_fixed(
            argv,
            request,
            OpenSshBackend._ssh_environment(),
            timeout=60,
            limit=1048576,
        )
    except (ValueError, OSError):
        raise NativeSetupRemoteRejected("native_setup_transport_ambiguous") from None
    if status or stderr:
        raise NativeSetupRemoteRejected("native_setup_remote_rejected")
    from cadence_mcp_bridge.domain_provisioning import _closed_document

    try:
        _closed_document(stdout)
        result = json.loads(stdout)
    except ValueError:
        raise NativeSetupRemoteRejected("native_setup_response_ambiguous") from None
    if (
        not isinstance(result, dict)
        or set(result)
        != {
            "schema_version",
            "status",
            "manifest_sha256",
            "identity_manifest_sha256",
            "changed_files",
            "active",
            "counter",
            "operator_uid",
            "execution_authorized",
            "new_reservations",
            "new_simulations",
        }
        or (
            type(result["schema_version"]) is not int
            or result["schema_version"] != 1
            or result["status"] != "NATIVE_RUNTIME_" + action.upper()
            or result["manifest_sha256"] != expected
            or result["identity_manifest_sha256"] != registration["identity_manifest_sha256"]
            or type(result["changed_files"]) is not int
            or not 0 <= result["changed_files"] <= len(setup.FILES) + 1
            or type(result["active"]) is not bool
            or type(result["operator_uid"]) is not int
            or result["operator_uid"] <= 0
            or result["execution_authorized"] is not False
            or type(result["new_reservations"]) is not int
            or result["new_reservations"] != 0
            or type(result["new_simulations"]) is not int
            or result["new_simulations"] != 0
        )
    ):
        raise NativeSetupRemoteRejected("native_setup_receipt_binding")
    counter = result["counter"]
    if (
        not isinstance(counter, dict)
        or set(counter) != {"campaign_id", "count", "result_reserved_bytes"}
        or not isinstance(counter["campaign_id"], str)
        or not 1 <= len(counter["campaign_id"]) <= 64
        or type(counter["count"]) is not int
        or not 0 <= counter["count"] <= environment.limits.spectre_attempts
        or type(counter["result_reserved_bytes"]) is not int
        or not 0 <= counter["result_reserved_bytes"] <= environment.limits.result_reserved_bytes
        or (action == "inspect" and result["changed_files"] != 0)
        or (action == "activate" and not result["active"])
        or (action == "revoke" and result["active"])
    ):
        raise NativeSetupRemoteRejected("native_setup_receipt_scope")
    return {**result, "remote_contact": True}
