"""Local preparation for a fixed OA binding observer; no remote execution path.

Prepared plans are private descriptions, never grants or source attestations.
The internal worker remains operationally blocked until its execution trust
boundary and a separate finite observation authority have been established.
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
from cadence_mcp_bridge.physical_metadata import _intent_metadata
from cadence_mcp_bridge.runtime_context import ExecutionContext, load_runtime

ASSETS = (
    "_binding_observation.py",
    "binding_observation.py",
    "binding_observation_bootstrap.py",
    "binding_observation_claim.py",
    "binding_observer_operator.py",
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
    "NO_OPERATIONAL_TRANSPORT_OR_ACTIVATION_ENTRYPOINT",
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def asset_pins() -> dict[str, str]:
    """Pin normalized packaged code, without exporting or running any helper."""
    return {
        name: _sha(files("cadence_mcp_bridge").joinpath(name).read_bytes().replace(b"\r\n", b"\n"))
        for name in ASSETS
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
    plan = {
        "schema_version": 1,
        "status": "LOCAL_PLAN_ONLY_OPERATIONALLY_BLOCKED",
        "context_sha256": context.context_sha256,
        "environment_sha256": context.binding.environment_sha256,
        "design_sha256": context.binding.design_sha256,
        "pdk_sha256": context.binding.pdk_sha256,
        "resource_domain_sha256": context.resource_domain_sha256,
        "registration_input_sha256": _sha(raw),
        "compiled_registration_sha256": _sha(_canonical(compiled)),
        "design_id": design_id,
        "analysis_id": analysis_id,
        "source_cell": route.source_cell,
        "source_state": route.source_state,
        "retained_source_tree_sha256": route.ade.source_tree_sha256,
        "retained_ade_state_tree_sha256": route.ade.ade_state_tree_sha256,
        "request": request.model_dump(mode="json"),
        "request_sha256": _sha(_canonical(request.model_dump(mode="json"))),
        "collector_sha256": _sha(script),
        "package_asset_lf_sha256": pins,
        "limits": dict(LIMITS),
        "blockers": list(BLOCKERS),
        "license_impact": "OCEAN_START_MAY_USE_EXISTING_LICENSE_SESSION",
        "observation_scope": "PROPOSED_READ_ONLY_OWNED_COPY_NOT_YET_OBSERVED",
        "execution_authorized": False,
        "qualification_established": False,
        "remote_contact": False,
        "claim_spent": False,
    }
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


def add_binding_observer_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    parser = subparsers.add_parser(
        "operator-binding-observation", help="Local-only experimental OA binding preparation."
    )
    actions = parser.add_subparsers(dest="binding_observation_action", required=True)
    actions.add_parser("schema")
    command = actions.add_parser("prepare", help="Export a private plan; no remote execution.")
    for name in ("settings", "registration", "output"):
        command.add_argument("--" + name, type=Path, required=True)
    for name in ("context", "design-id", "analysis-id"):
        command.add_argument("--" + name, required=True)


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
            result = prepare(
                selected[0], arguments.registration, arguments.design_id,
                arguments.analysis_id, arguments.output,
            )
    except (OSError, ValueError, BridgeError, RecursionError):
        print(json.dumps({
            "status": "blocked", "reason": "binding_observation_local_preparation_rejected",
            "remote_contact": False, "execution_authorized": False,
        }))
        return 1
    print(json.dumps(result))
    return 0
