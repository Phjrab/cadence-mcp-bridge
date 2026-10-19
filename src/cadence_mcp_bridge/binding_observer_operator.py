"""Explicit operator preparation and finite owned-copy OA observation.

Import, schema and prepare never dispatch. Run requires independently pinned
human authority and reviewed standard-VM runtime/init trust evidence.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import secrets
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import uuid4

from cadence_mcp_bridge.binding_observation import (
    BindingScanRequest,
    BindingScanVariable,
    render_collector,
)
from cadence_mcp_bridge.candidate_cli import read_candidate_document
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.errors import BridgeError
from cadence_mcp_bridge.native_runtime import NativeRegistration, projection
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.physical_metadata import _intent_metadata, _payload
from cadence_mcp_bridge.runtime_context import ExecutionContext, load_runtime

ASSETS = (
    "_binding_observation.py",
    "binding_observation.py",
    "binding_observation_bootstrap.py",
    "binding_observation_claim.py",
    "binding_observer_operator.py",
    "binding_observation_transport.py",
    "_native_copy.py",
    "_shared_reservations.py",
    "_native_eda_worker.py",
)
LIMITS = {
    "remote_attempts": 1,
    "ocean_starts": 1,
    "outer_seconds": 60,
    "ocean_seconds": 45,
    "source_state_entries": 64,
    "source_state_content_bytes": 1048576,
    "registered_libraries": 8,
    "dependency_entries_per_library": 4096,
    "dependency_entries_combined": 8192,
    "dependency_content_bytes_combined": 67108864,
    "top_level_instances": 64,
    "properties_per_instance": 32,
    "matches_per_variable": 4,
    "matches_total": 16,
    "frame_bytes_including_framing": 65536,
    "bytes_per_output_stream": 65536,
    "stage_logical_and_allocated_bytes": 8388608,
    "new_simulations": 0,
    "new_extractions": 0,
    "new_result_reservations": 0,
}
BLOCKERS = (
    "RUNTIME_AND_LIBRARY_INITIALIZATION_TRUST_NOT_ESTABLISHED",
    "SEPARATE_FINITE_BINDING_OBSERVATION_AUTHORITY_REQUIRED",
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def asset_pins() -> dict[str, str]:
    """Pin normalized packaged code, without exporting or running any helper."""
    return {
        name: _sha(files("cadence_mcp_bridge").joinpath(name).read_bytes().replace(b"\r\n", b"\n"))
        for name in ASSETS
    }


def _execution_documents(
    context: ExecutionContext, compiled: dict[str, Any], request: BindingScanRequest,
    pins: dict[str, str], design_id: str, analysis_id: str,
) -> tuple[bytes, bytes, bytes, bytes]:
    # Keep original profile/registration file hashes in the plan. The guest
    # receives a canonical semantic projection; pretty operator JSON is valid
    # and never rewritten merely to meet the wire format.
    profile = _canonical(context.contracts.environment.model_dump(mode="json"))
    execution = {**compiled, "environment_sha256": _sha(profile)}
    registration = _canonical(execution)
    scan = _canonical(request.model_dump(mode="json"))
    selection = _canonical({
        "schema_version": 1,
        "design_id": design_id, "analysis_id": analysis_id,
        "profile_sha256": _sha(profile), "registration_sha256": _sha(registration),
        "request_sha256": _sha(scan), "collector_sha256": _sha(render_collector(request)),
        "helper_sha256": pins["_binding_observation.py"],
    })
    return profile, registration, selection, scan


def _plan_value(
    context: ExecutionContext, raw: bytes, compiled: dict[str, Any], route: Any,
    design_id: str, analysis_id: str, request: BindingScanRequest, pins: dict[str, str],
) -> dict[str, Any]:
    documents = _execution_documents(context, compiled, request, pins, design_id, analysis_id)
    return {
        "schema_version": 1,
        "status": "LOCAL_PLAN_ONLY_OPERATIONALLY_BLOCKED",
        "context_sha256": context.context_sha256,
        "environment_sha256": context.binding.environment_sha256,
        "design_sha256": context.binding.design_sha256,
        "pdk_sha256": context.binding.pdk_sha256,
        "resource_domain_sha256": context.resource_domain_sha256,
        "registration_input_sha256": _sha(raw),
        "compiled_registration_sha256": _sha(_canonical(compiled)),
        "execution_profile_sha256": _sha(documents[0]),
        "execution_registration_sha256": _sha(documents[1]),
        "design_id": design_id, "analysis_id": analysis_id,
        "source_cell": route.source_cell, "source_state": route.source_state,
        "retained_source_tree_sha256": route.ade.source_tree_sha256,
        "retained_ade_state_tree_sha256": route.ade.ade_state_tree_sha256,
        "request": request.model_dump(mode="json"),
        "request_sha256": _sha(documents[3]), "collector_sha256": _sha(render_collector(request)),
        "package_asset_lf_sha256": pins, "limits": dict(LIMITS), "blockers": list(BLOCKERS),
        "license_impact": "OCEAN_START_MAY_USE_EXISTING_LICENSE_SESSION",
        "observation_scope": "PROPOSED_READ_ONLY_OWNED_COPY_NOT_YET_OBSERVED",
        "execution_authorized": False, "qualification_established": False,
        "remote_contact": False, "claim_spent": False,
    }


def _reserved(context: ExecutionContext, registration: Path) -> set[Path]:
    paths = {_local_path(registration), _local_path(context.lock_path)}
    for name in type(context.binding).model_fields:
        value = getattr(context.binding, name)
        if isinstance(value, Path):
            paths.add(_local_path(value))
    for path in (context.binding.analysis_journal, context.binding.sweep_journal):
        path = _local_path(path)
        paths.update(path.with_name(path.name + suffix) for suffix in ("-wal", "-shm", "-journal"))
    return paths


def _directory_identity(path: Path) -> tuple[int, ...]:
    _local_path(path)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise OperationRejected("binding_observation_output_namespace_drift")
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode


@contextmanager
def _held_output(
    output: Path, parents: dict[Path, tuple[int, ...]],
) -> Iterator[tuple[int | None, Callable[[], None]]]:
    """Keep Windows names non-renamable or anchor POSIX writes to an owned fd.

    Named-chain checks additionally reject detachment on POSIX. A failed export
    stays as evidence in the owned directory; no replacement path receives writes.
    """
    identity = _directory_identity(output)
    expected = {output: identity, **parents}
    descriptors: list[int] = []
    handles: list[int] = []
    kernel: Any = None
    try:
        if os.name == "nt":
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateFileW.argtypes = [
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
            ]
            kernel.CreateFileW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        for path, before in expected.items():
            if _directory_identity(path) != before:
                raise OperationRejected("binding_observation_output_namespace_drift")
            if kernel is not None:
                # No FILE_SHARE_DELETE: held names/ancestors cannot be replaced.
                # LIST_DIRECTORY is a data-read access participating in Windows
                # share checks; READ_ATTRIBUTES alone does not prevent rename.
                handle = kernel.CreateFileW(str(path), 1, 3, None, 3, 0x02200000, None)
                if handle == ctypes.c_void_p(-1).value or handle is None:
                    raise OperationRejected("binding_observation_output_pin_failed")
                handles.append(handle)
            else:
                descriptor = os.open(
                    path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,  # type: ignore[attr-defined]
                )
                descriptors.append(descriptor)
                held = os.fstat(descriptor)
                if (held.st_dev, held.st_ino) != before[:2]:
                    raise OperationRejected("binding_observation_output_namespace_drift")
            if _directory_identity(path) != before:
                raise OperationRejected("binding_observation_output_namespace_drift")

        def guard() -> None:
            if any(_directory_identity(path) != before for path, before in expected.items()):
                raise OperationRejected("binding_observation_output_namespace_drift")
            if _intent_metadata(output, True) != identity:
                raise OperationRejected("binding_observation_output_namespace_drift")

        guard()
        if any(output.iterdir()):
            raise OperationRejected("binding_observation_exclusive_output_required")
        if descriptors:
            # Publish the newly created directory durably before retaining any
            # evidence inside it. The held parent is the verified original inode.
            os.fsync(descriptors[1])
        yield (descriptors[0] if descriptors else None), guard
        guard()
    finally:
        try:
            if descriptors:
                try:
                    # Retain completed or partial evidence even when preparation
                    # fails. A sync failure must still try the parent and close
                    # every held descriptor.
                    os.fsync(descriptors[0])
                finally:
                    if len(descriptors) > 1:
                        os.fsync(descriptors[1])
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
            for handle in reversed(handles):
                kernel.CloseHandle(handle)


def prepare(
    context: ExecutionContext,
    registration_path: Path,
    design_id: str,
    analysis_id: str,
    output: Path,
) -> dict[str, Any]:
    """Export a local plan for every registered V/A variable of one saved DC route.

    No claim is spent, remote process started, context rewritten or observation
    authority generated here. An exclusive output directory retains any partial
    export on failure. A fresh ID does not create another execution allowance.
    """
    raw = read_candidate_document(registration_path)
    registration = NativeRegistration.model_validate_json(raw)
    compiled = projection(context, registration)
    routes = [
        route for route in registration.routes
        if (route.ade.design_id, route.ade.analysis_id) == (design_id, analysis_id)
    ]
    if len(routes) != 1:
        raise OperationRejected("binding_observation_registered_route_required")
    route = routes[0]
    if route.ade.inputs.analysis != "dc" or route.ade.inputs.mode != "saved_operating_point":
        raise OperationRejected("binding_observation_saved_dc_only")
    profile = context.contracts.designs.profile(design_id)
    variables = context.contracts.designs.variable_set(design_id)
    if variables is None or not 1 <= len(variables.variables) <= 4 or any(
        variable.unit not in ("V", "A") for variable in variables.variables
    ):
        raise OperationRejected("binding_observation_complete_va_inventory_required")
    request = BindingScanRequest(
        schema_version=1,
        observation_id=str(uuid4()),
        nonce=secrets.token_hex(32),
        library=profile.binding.library,
        cell=profile.binding.cell,
        view="schematic",
        variables=tuple(
            BindingScanVariable(logical_id=v.logical_id, cadence_binding=v.cadence_binding)
            for v in sorted(variables.variables, key=lambda item: item.logical_id)
        ),
    )
    script = render_collector(request)
    pins = asset_pins()
    plan = _plan_value(context, raw, compiled, route, design_id, analysis_id, request, pins)
    output = _local_path(output)
    if not output.parent.is_dir() or any(
        path == output or path.is_relative_to(output)
        for path in _reserved(context, registration_path)
    ):
        raise OperationRejected("binding_observation_exclusive_output_required")
    # Recheck inputs and exact installed resources before publishing any output.
    if read_candidate_document(registration_path) != raw or asset_pins() != pins:
        raise OperationRejected("binding_observation_preparation_drift")
    parents = {path: _directory_identity(path) for path in output.parents}
    try:
        output.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError:
        raise OperationRejected("binding_observation_exclusive_output_required") from None
    payloads = {
        "binding-plan.private.json": _canonical(plan),
        "binding-request.private.json": _canonical(request.model_dump(mode="json")),
        "collector.ocn": script,
    }
    with _held_output(output, parents) as (directory_fd, guard):
        for name, data in payloads.items():
            guard()
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = (
                os.open(output / name, flags, 0o600) if directory_fd is None
                else os.open(name, flags, 0o600, dir_fd=directory_fd)
            )
            with os.fdopen(descriptor, "wb") as stream:
                guard()
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
                guard()
    if read_candidate_document(registration_path) != raw or asset_pins() != pins:
        raise OperationRejected("binding_observation_preparation_drift")
    return {
        "status": plan["status"],
        "plan_sha256": _sha(payloads["binding-plan.private.json"]),
        "request_sha256": plan["request_sha256"],
        "collector_sha256": plan["collector_sha256"],
        "blockers": list(BLOCKERS),
        "remote_contact": False,
        "claim_spent": False,
        "execution_authorized": False,
        "new_simulations": 0,
        "new_extractions": 0,
        "new_reserved_bytes": 0,
    }


def run(
    context: ExecutionContext, registration_path: Path, prepared: Path, expected_plan: str,
    admission_path: Path, expected_admission: str, manifest_path: Path,
    attestation_path: Path, output: Path,
) -> dict[str, Any]:
    """One explicit operator action, never approval generation or automatic retry.

    The expected admission digest must come from the actual finite human approval.
    An agent-created plan/attestation cannot stand in for that approval or review.
    """
    from cadence_mcp_bridge import binding_observation_bootstrap as factory
    from cadence_mcp_bridge import binding_observation_claim as claims
    from cadence_mcp_bridge import binding_observation_transport as transport

    inputs = {
        "plan": _local_path(prepared) / "binding-plan.private.json",
        "request": _local_path(prepared) / "binding-request.private.json",
        "collector": _local_path(prepared) / "collector.ocn",
        "registration": _local_path(registration_path),
        "admission": _local_path(admission_path),
        "manifest": _local_path(manifest_path),
        "closure": _local_path(attestation_path),
    }
    original = {
        key: _payload(path) if key == "collector" else read_candidate_document(path)
        for key, path in inputs.items()
    }
    plan = factory._document(original["plan"], 65_536)
    admission = factory._document(original["admission"], 16_384)
    if _sha(original["plan"]) != expected_plan or _sha(original["admission"]) != (
        expected_admission
    ):
        raise OperationRejected("binding_observation_external_approval_digest")
    registration = NativeRegistration.model_validate_json(original["registration"])
    compiled = projection(context, registration)
    request = BindingScanRequest.model_validate_json(original["request"])
    routes = [route for route in registration.routes if (
        route.ade.design_id, route.ade.analysis_id
    ) == (plan["design_id"], plan["analysis_id"])]
    if len(routes) != 1:
        raise OperationRejected("binding_observation_registered_route_required")
    pins = asset_pins()
    expected = _plan_value(
        context, original["registration"], compiled, routes[0], plan["design_id"],
        plan["analysis_id"], request, pins,
    )
    if original["plan"] != _canonical(expected) or original["collector"] != (
        render_collector(request)
    ) or original["request"] != _canonical(request.model_dump(mode="json")):
        raise OperationRejected("binding_observation_prepared_inputs_changed")
    documents = _execution_documents(
        context, compiled, request, pins, plan["design_id"], plan["analysis_id"],
    )
    worker = factory.construct_worker(*documents)
    worker._admission(
        request.model_dump(mode="json"), original["admission"], original["manifest"],
        original["closure"],
    )
    if any(admission[key] != value for key, value in {
        "prepared_plan_sha256": expected_plan,
        "package_sha256": _sha(_canonical(pins)),
        "resource_domain_sha256": context.resource_domain_sha256,
        "identity_manifest_sha256": registration.identity_manifest_sha256,
    }.items()):
        raise OperationRejected("binding_observation_admission_identity")
    payload = transport.build_payload(
        *documents, original["admission"], original["manifest"], original["closure"],
    )
    output = _local_path(output)
    reserved = _reserved(context, registration_path) | set(inputs.values())
    if not output.parent.is_dir() or any(
        path == output or path.is_relative_to(output) for path in reserved
    ):
        raise OperationRejected("binding_observation_exclusive_output_required")
    parents = {path: _directory_identity(path) for path in output.parents}
    output.mkdir(mode=0o700, exist_ok=False)
    with _held_output(output, parents) as (directory_fd, guard):
        def publish(name: str, data: bytes) -> None:
            guard()
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(output / name, flags, 0o600) if directory_fd is None else os.open(
                name, flags, 0o600, dir_fd=directory_fd,
            )
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            guard()

        if any((_payload(path) if key == "collector" else read_candidate_document(path)) != (
            original[key]) for key, path in inputs.items()) or (
            asset_pins() != pins
        ):
            raise OperationRejected("binding_observation_predispatch_drift")
        # Preserve the exact authority and input identities before the durable
        # account claim. A new output directory never creates another allowance.
        publish("admission.private.json", original["admission"])
        publish("request.private.json", documents[3])
        publish("payload.private.json", payload)
        claims.claim(context.contracts.environment, admission["predecessor"], {
            "approval_receipt_sha256": admission["approval_receipt_sha256"],
            "plan_sha256": expected_plan, "request_sha256": plan["request_sha256"],
            "helper_sha256": pins["_binding_observation.py"],
            "package_sha256": admission["package_sha256"],
        })
        publish("started.private.json", _canonical({
            "status": "ATTEMPT_SPENT_NO_RETRY", "admission_sha256": expected_admission,
            "payload_sha256": _sha(payload),
        }))
        try:
            code, stdout, stderr = transport.dispatch(
                context.contracts.environment, payload, _sha(payload),
                pins["_binding_observation.py"],
                {name: pin for name, (_, pin) in factory._HELPERS.items()},
            )
            publish("stdout.private.json", stdout)
            publish("stderr.private.log", stderr)
            if code or stderr:
                raise OperationRejected("binding_observation_remote_rejected")
            result = transport.validate_terminal(stdout, payload)
            publish("terminal.private.json", _canonical(result))
            return result
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            publish("failed.private.json", _canonical({
                "status": "FAILED_OR_UNKNOWN_NO_RETRY", "admission_sha256": expected_admission,
                "observation_id": request.observation_id, "retry_permitted": False,
            }))
            raise OperationRejected("binding_observation_failed_or_unknown_no_retry") from None


def read_result(output: Path, expected_admission: str) -> dict[str, Any]:
    """Inspect retained local evidence without a context, claim, SSH or EDA start."""
    from cadence_mcp_bridge.binding_observation_transport import validate_terminal

    output = _local_path(output)
    admission = read_candidate_document(output / "admission.private.json")
    if _sha(admission) != expected_admission:
        raise OperationRejected("binding_observation_external_approval_digest")
    terminal = read_candidate_document(output / "terminal.private.json")
    invocation = output / "payload.private.json"
    _intent_metadata(invocation, False)
    before = invocation.lstat()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(invocation, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        payload = stream.read(2_097_153)
    after = invocation.lstat()
    keys = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
            "st_size", "st_mtime_ns", "st_ctime_ns")
    # Windows lstat exposes creation time while CRT fstat may expose change time.
    # Keep the full named-file before/after guard on every platform.
    if len(payload) > 2_097_152 or any(
        getattr(before, key) != getattr(after, key)
        or (getattr(before, key) != getattr(opened, key)
            and (key != "st_ctime_ns" or os.name != "nt"))
        for key in keys
    ):
        raise OperationRejected("binding_observation_retained_invocation_drift")
    value = validate_terminal(terminal, payload)
    if value.get("admission_sha256") != expected_admission:
        raise OperationRejected("binding_observation_retained_identity")
    return value


def add_binding_observer_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    parser = subparsers.add_parser(
        "operator-binding-observation", help="Explicit finite experimental OA binding observation."
    )
    actions = parser.add_subparsers(dest="binding_observation_action", required=True)
    actions.add_parser("schema")
    command = actions.add_parser("prepare", help="Export a private plan; no remote execution.")
    for name in ("settings", "registration", "output"):
        command.add_argument("--" + name, type=Path, required=True)
    for name in ("context", "design-id", "analysis-id"):
        command.add_argument("--" + name, required=True)
    command = actions.add_parser("run", help="One externally approved observer; never retry.")
    for name in ("settings", "registration", "prepared", "admission", "manifest",
                 "attestation", "output"):
        command.add_argument("--" + name, type=Path, required=True)
    for name in ("context", "expected-plan", "expected-admission"):
        command.add_argument("--" + name, required=True)
    command = actions.add_parser("result", help="Read retained local terminal evidence only.")
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--expected-admission", required=True)


def binding_observer_cli(arguments: argparse.Namespace) -> int:
    try:
        if arguments.binding_observation_action == "schema":
            result: dict[str, Any] = {
                "request_schema": BindingScanRequest.model_json_schema(),
                "operational_status": "CAPABILITY_NOT_QUALIFIED",
                "blockers": list(BLOCKERS),
                "limits": dict(LIMITS),
                "remote_contact": False,
                "execution_authorized": False,
            }
        elif arguments.binding_observation_action == "result":
            result = read_result(arguments.output, arguments.expected_admission)
        else:
            contexts = load_runtime(_local_path(arguments.settings))
            selected = [c for c in contexts if c.binding.context_id == arguments.context]
            if len(selected) != 1:
                raise OperationRejected("binding_observation_context_required")
            reserved = {_local_path(arguments.settings)}
            for context in contexts:
                reserved.update(_reserved(context, arguments.registration))
            output = _local_path(arguments.output)
            if any(path == output or path.is_relative_to(output) for path in reserved):
                raise OperationRejected("binding_observation_exclusive_output_required")
            if arguments.binding_observation_action == "prepare":
                result = prepare(
                    selected[0], arguments.registration, arguments.design_id,
                    arguments.analysis_id, arguments.output,
                )
            else:
                result = run(
                    selected[0], arguments.registration, arguments.prepared,
                    arguments.expected_plan, arguments.admission, arguments.expected_admission,
                    arguments.manifest, arguments.attestation, arguments.output,
                )
    except (OSError, ValueError, BridgeError, RecursionError, KeyError, TypeError):
        print(json.dumps({
            "status": "blocked", "reason": "binding_observation_operation_rejected",
            "remote_contact": "UNKNOWN" if arguments.binding_observation_action == "run" else False,
            "execution_authorized": False,
        }))
        return 1
    print(json.dumps(result))
    return int(arguments.binding_observation_action == "run" and (
        result.get("status") != "PROCESS_COMPLETED"))
