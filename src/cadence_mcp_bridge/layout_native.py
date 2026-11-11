"""Pinned native layout facade. Setup never installs helpers or writes authority."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.layout_engine import compute_diff, predict_snapshot, validate_plan
from cadence_mcp_bridge.layout_models import (
    LayerPurpose,
    LayoutApplyRequest,
    LayoutDiffRequest,
    LayoutForkRequest,
    LayoutInspectRequest,
    LayoutOrientationQualification,
    LayoutResult,
    LayoutSelectRequest,
    LayoutSnapshot,
    LayoutTechnology,
)
from cadence_mcp_bridge.layout_service import LayoutService
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.operator_operations import bounded_document
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.runtime_context import ExecutionContext, select_context
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import BindingName, Digest, LogicalId, VariableModel

SAFE_REASONS = {
    "layout_setup_required",
    "layout_transport_unavailable",
    "layout_resource_lock_busy",
    "layout_revision_conflict",
    "layout_outcome_unknown",
    "layout_program_failed",
    "layout_source_protection_failed",
    "layout_runtime_trust_failed",
    "layout_result_capacity",
}


class _LayoutQualificationBinding(VariableModel):
    orientation_qualification: LayoutOrientationQualification | None = None

    @model_serializer(mode="wrap")
    def omit_absent_qualification(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        document: dict[str, Any] = handler(self)
        if self.orientation_qualification is None:
            document.pop("orientation_qualification", None)
        return document


class LayoutProviderBinding(_LayoutQualificationBinding):
    schema_version: Literal[1]
    resource_domain_sha256: Digest
    environment_sha256: Digest
    native_runtime_manifest_sha256: Digest
    identity_manifest_sha256: Digest
    layout_manifest_sha256: Digest
    worker_sha256: Digest


class LayoutCellView(VariableModel):
    library: BindingName
    cell: BindingName
    view: Literal["layout"] = "layout"


class LayoutLayerPolicy(VariableModel):
    """Operator-registered writable LPPs on one protected technology library."""

    technology_library: BindingName
    layer_purposes: Annotated[tuple[LayerPurpose, ...], Field(max_length=32)]

    @model_validator(mode="after")
    def canonical_order(self) -> Self:
        pairs = [(item.layer, item.purpose) for item in self.layer_purposes]
        if pairs != sorted(set(pairs)):
            raise ValueError("layout_layer_policy_order")
        return self


class LayoutRegisteredView(VariableModel):
    binding: RevisionBinding
    cellview: LayoutCellView
    path: str
    owned: bool
    read_only: bool
    layer_policy: LayoutLayerPolicy | None = None

    @field_validator("layer_policy")
    @classmethod
    def reject_null_layer_policy(cls, value: LayoutLayerPolicy | None) -> LayoutLayerPolicy:
        if value is None:
            raise ValueError("layout_layer_policy_shape")
        return value

    @model_serializer(mode="wrap")
    def omit_absent_layer_policy(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        document: dict[str, Any] = handler(self)
        if self.layer_policy is None:
            document.pop("layer_policy", None)
        return document


class LayoutRegisteredLibrary(VariableModel):
    name: BindingName
    path: str
    tree_sha256: Digest | None = None


class LayoutProtectedView(VariableModel):
    path: str
    tree_sha256: Digest


class LayoutSeed(VariableModel):
    revision_id: LogicalId
    technology_library: BindingName
    master_cell: BindingName
    technology: LayoutTechnology
    layer_purpose: LayerPurpose

    @model_validator(mode="after")
    def observed(self) -> Self:
        if self.technology.provenance != "native_observed" or (
            self.layer_purpose not in self.technology.allowed_layer_purposes
        ):
            raise ValueError("layout_seed_observation_required")
        return self


class LayoutRegistration(_LayoutQualificationBinding):
    schema_version: Literal[1] = 1
    routes: Annotated[tuple[LayoutRegisteredView, ...], Field(min_length=1, max_length=32)]
    libraries: Annotated[tuple[LayoutRegisteredLibrary, ...], Field(min_length=1, max_length=32)]
    owned_libraries: Annotated[
        tuple[LayoutRegisteredLibrary, ...], Field(min_length=1, max_length=8)
    ]
    protected_views: Annotated[tuple[LayoutProtectedView, ...], Field(min_length=1, max_length=32)]
    seed: LayoutSeed | None = None
    probe_libraries: (
        Annotated[tuple[BindingName, ...], Field(min_length=1, max_length=8)] | None
    ) = None

    @model_validator(mode="after")
    def closed_routes(self) -> Self:
        libraries = {lib.name: lib for lib in (*self.libraries, *self.owned_libraries)}
        dependency_names = {lib.name for lib in self.libraries}
        if len(libraries) != len(self.libraries) + len(self.owned_libraries):
            raise ValueError("layout_library_identity_collision")
        if any(lib.tree_sha256 is None for lib in self.libraries):
            raise ValueError("layout_protected_library_hash_required")
        if self.probe_libraries is not None and (
            len(set(self.probe_libraries)) != len(self.probe_libraries)
            or not set(self.probe_libraries) <= dependency_names
        ):
            raise ValueError("layout_probe_library_scope")
        # Pure syntax checks only: never touch a remote path on this Windows host.
        paths = [item.path for item in self.libraries + self.owned_libraries]
        paths += [item.path for item in self.protected_views]
        paths += [item.path for item in self.routes]
        for path in paths:
            if not re.fullmatch(r"/[A-Za-z0-9_./-]{1,511}", path) or any(
                p in ("", ".", "..") for p in path[1:].split("/")
            ):
                raise ValueError("layout_registered_path_shape")
        identities = [
            (r.binding.workspace_id, r.binding.design_id, r.binding.revision_id)
            for r in self.routes
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("layout_duplicate_revision")
        if len({r.path for r in self.routes}) != len(self.routes):
            raise ValueError("layout_revision_path_alias")
        for owned in self.owned_libraries:
            if any(
                owned.path == lib.path
                or owned.path.startswith(lib.path + "/")
                or lib.path.startswith(owned.path + "/")
                for lib in self.libraries
            ):
                raise ValueError("layout_owned_protected_library_overlap")
        for route in self.routes:
            lib = libraries.get(route.cellview.library)
            if lib is None or route.path != lib.path + "/" + route.cellview.cell + "/layout":
                raise ValueError("layout_registered_path_binding")
            if route.owned != (lib in self.owned_libraries) or route.read_only == route.owned:
                raise ValueError("layout_registered_ownership")
            if not route.owned and route.path not in {p.path for p in self.protected_views}:
                raise ValueError("layout_original_protection_required")
            if route.layer_policy and route.layer_policy.technology_library not in dependency_names:
                raise ValueError("layout_layer_policy_registered_technology_required")
        if self.orientation_qualification is not None:
            qualified = [
                r for r in self.routes if r.binding == self.orientation_qualification.binding
            ]
            if len(qualified) != 1 or not qualified[0].owned or qualified[0].read_only:
                raise ValueError("layout_orientation_qualification_owned_route_required")
        if self.seed is not None:
            routes = [r for r in self.routes if r.binding.revision_id == self.seed.revision_id]
            if len(routes) != 1 or not routes[0].owned:
                raise ValueError("layout_seed_owned_route_required")
            route = routes[0]
            if self.seed.technology_library not in dependency_names:
                raise ValueError("layout_seed_registered_technology_required")
            if route.layer_policy and (
                route.layer_policy.technology_library != self.seed.technology_library
                or self.seed.layer_purpose not in route.layer_policy.layer_purposes
            ):
                raise ValueError("layout_seed_layer_policy_mismatch")
            if route.cellview.cell == self.seed.master_cell:
                raise ValueError("layout_seed_master_collision")
        return self


@dataclass(frozen=True)
class LayoutBundle:
    assets: dict[str, bytes]
    manifest_sha256: str
    provider: LayoutProviderBinding


def build_layout_bundle(
    context: ExecutionContext,
    registration: LayoutRegistration,
    *,
    native_provider_sha256: str,
    identity_manifest_sha256: str,
    confirmation_sha256: str,
) -> LayoutBundle:
    """Pure local exporter. No deployment, confirmation writer or source allowance.

    The three supplied pins come from independently retained operator/runtime
    evidence. This builder does not discover, approve or refresh them.
    """
    registration = LayoutRegistration.model_validate_json(registration.model_dump_json())
    managed = context.transport.remote_root
    if any(not lib.path.startswith(managed + "/") for lib in registration.owned_libraries):
        raise ConfigurationError("Owned layout library must be inside registered managed root")
    assets = {
        "worker.py": files("cadence_mcp_bridge").joinpath("_layout_worker.py").read_bytes(),
        "rendering.py": files("cadence_mcp_bridge").joinpath("_layout_rendering.py").read_bytes(),
        "registration.json": registration.model_dump_json().encode("ascii"),
    }
    assets = {name: raw.replace(b"\r\n", b"\n") for name, raw in assets.items()}

    # Canonical registration bytes are bound in the independently prepared
    # confirmation; exact defaults and field ordering must not be implicit.
    def canonical(value: Any) -> bytes:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")

    registration_document = registration.model_dump(mode="json")
    if registration.probe_libraries is None:
        # Old workers require exactly the original keys, including seed=null.
        registration_document.pop("probe_libraries")
    assets["registration.json"] = canonical(registration_document)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "resource_domain_sha256": context.resource_domain_sha256,
        "environment_sha256": context.binding.environment_sha256,
        "native_runtime_manifest_sha256": context.binding.runner_sha256,
        "native_provider_sha256": native_provider_sha256,
        "identity_manifest_sha256": identity_manifest_sha256,
        "confirmation_sha256": confirmation_sha256,
        "files": {
            name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            for name, raw in assets.items()
        },
    }
    for key in ("native_provider_sha256", "identity_manifest_sha256", "confirmation_sha256"):
        if len(manifest[key]) != 64 or any(c not in "0123456789abcdef" for c in manifest[key]):
            raise ValueError("layout_operator_pin_required")
    assets["manifest.json"] = canonical(manifest)
    manifest_sha = hashlib.sha256(assets["manifest.json"]).hexdigest()
    provider = LayoutProviderBinding(
        schema_version=1,
        resource_domain_sha256=context.resource_domain_sha256,
        environment_sha256=context.binding.environment_sha256,
        native_runtime_manifest_sha256=context.binding.runner_sha256,
        identity_manifest_sha256=identity_manifest_sha256,
        layout_manifest_sha256=manifest_sha,
        worker_sha256=manifest["files"]["worker.py"]["sha256"],
        orientation_qualification=registration.orientation_qualification,
    )
    return LayoutBundle(assets, manifest_sha, provider)


class NativeLayoutProvider:
    """One fixed authenticated helper, no caller paths, scripts or retries.

    The helper must independently enforce trust/authority, shared VM lock,
    immutable jobs identity, revision baseline and source preservation. Its
    typed receipts are also rechecked here against the pure layout engine.
    """

    def __init__(self, context: ExecutionContext, registration: LayoutProviderBinding) -> None:
        if (
            registration.resource_domain_sha256 != context.resource_domain_sha256
            or registration.environment_sha256 != context.binding.environment_sha256
            or registration.native_runtime_manifest_sha256 != context.binding.runner_sha256
        ):
            raise ConfigurationError("LAYOUT_SETUP_REQUIRED: provider runtime binding mismatch")
        self.context, self.registration = context, registration
        self.worker = (
            context.transport.remote_root
            + "/layout-runtime/"
            + registration.layout_manifest_sha256
            + "/worker.py"
        )

    async def _invoke(self, action: str, payload: dict[str, Any]) -> Any:
        if action not in ("inspect", "lookup", "fork", "apply"):
            raise InvalidInputError("Unsupported fixed layout action")
        request = {
            "schema_version": 1,
            "action": action,
            "layout_manifest_sha256": self.registration.layout_manifest_sha256,
            "identity_manifest_sha256": self.registration.identity_manifest_sha256,
            "payload": payload,
        }
        raw = json.dumps(
            request, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
        # Authenticate the initial entry bytes before executing them. Transitive
        # helpers/configuration must then pass the remote runner's own guards.
        bootstrap = (
            "import sys; sys.path[:]=[p for p in sys.path if p and p.startswith('/')]; "
            "import os; sys.path[:]=[p for p in sys.path if os.path.realpath(p)"
            "!=os.path.realpath(os.getcwd())]; import stat,hashlib; p=" + repr(self.worker) + "; "
            "f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK); "
            "s=os.fstat(f); b=os.fdopen(f,'rb').read(262145); "
            "assert stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() "
            "and s.st_nlink==1 and not s.st_mode&63 and len(b)<=262144; "
            "assert hashlib.sha256(b).hexdigest()==" + repr(self.registration.worker_sha256) + "; "
            "g={'__name__':'__main__','__file__':p}; eval(compile(b,p,'exec'),g)"
        )
        argv = _ssh(self.context.contracts.environment) + ["-c", shlex.quote(bootstrap)]
        try:
            code, stdout, stderr = await asyncio.to_thread(
                run_fixed,
                argv,
                raw,
                OpenSshBackend._ssh_environment(),
                timeout=60,
                limit=262144,
            )
            fixed_errors = {
                ("LAYOUT_FIXED_WORKER_REJECTED:" + reason + "\n").encode("ascii"): reason
                for reason in SAFE_REASONS
            }
            if code and not stdout and stderr in fixed_errors:
                reason = fixed_errors[stderr]
                error_class = (
                    ConfigurationError
                    if reason == "layout_setup_required"
                    else InvalidInputError
                    if reason == "layout_revision_conflict"
                    else RemoteFailureError
                )
                raise error_class("Native layout operation rejected", details={"reason": reason})
            if code or stderr or len(stdout) > 262144:
                raise ValueError("layout_fixed_worker_failed")
            result = json.loads(stdout)
            if (
                set(result) != {"schema_version", "layout_manifest_sha256", "action", "payload"}
                or type(result["schema_version"]) is not int
                or result["schema_version"] != 1
                or result["layout_manifest_sha256"] != self.registration.layout_manifest_sha256
                or result["action"] != action
            ):
                raise ValueError("layout_worker_response_binding")
            if type(result["payload"]) is dict and set(result["payload"]) == {"error"}:
                reason = result["payload"]["error"].get("reason")
                if reason not in SAFE_REASONS:
                    raise ValueError("layout_unrecognized_worker_reason")
                error_class = (
                    ConfigurationError
                    if reason == "layout_setup_required"
                    else InvalidInputError
                    if reason == "layout_revision_conflict"
                    else RemoteFailureError
                )
                raise error_class("Native layout operation rejected", details={"reason": reason})
            return result["payload"]
        except (OSError, ValueError, TypeError, KeyError):
            # No transport retry: the original operation may have written.
            raise RemoteFailureError(
                "Native layout response unavailable; reconcile the same operation ID",
                details={"reason": "layout_transport_unavailable"},
            ) from None

    async def inspect(self, request: LayoutInspectRequest) -> LayoutSnapshot:
        data = await self._invoke("inspect", request.model_dump(mode="json"))
        snapshot = LayoutSnapshot.model_validate_json(json.dumps(data))
        if snapshot.binding != request.binding or snapshot.provenance != "native_readback":
            raise InvalidInputError("Layout native snapshot binding mismatch")
        self._check_orientation_snapshot(snapshot)
        return snapshot

    def _check_orientation_snapshot(self, snapshot: LayoutSnapshot) -> None:
        qualification = self.registration.orientation_qualification
        if qualification is None or snapshot.binding != qualification.binding:
            coherent = snapshot.capabilities.rotate == "unsupported"
        else:
            coherent = (
                snapshot.owned
                and not snapshot.read_only
                and snapshot.capabilities.rotate == "not_verified"
                and set(qualification.orientations)
                <= set(snapshot.technology.supported_orientations)
            )
        if not coherent:
            raise InvalidInputError("Layout native orientation qualification mismatch")

    @staticmethod
    def _result(data: dict[str, Any], binding: RevisionBinding, *, fork: bool) -> LayoutResult:
        operation_id = data["operation_id"]
        if data["state"] == "OUTCOME_UNKNOWN":
            return LayoutResult(
                status="OUTCOME_UNKNOWN",
                operation_id=operation_id,
                binding=binding,
                replayed=data.get("replayed", False),
            )
        if data["state"] != "SUCCEEDED":
            raise RemoteFailureError(
                "Native layout operation did not produce a verified receipt",
                details={"reason": "layout_outcome_unknown"},
            )
        before = LayoutSnapshot.model_validate_json(json.dumps(data["before"]))
        after = LayoutSnapshot.model_validate_json(json.dumps(data["snapshot"]))
        if after.binding != binding or after.provenance != "native_readback":
            raise InvalidInputError("Layout native receipt revision mismatch")
        return LayoutResult(
            executed=data["executed"],
            status="FORK_VERIFIED" if fork else "NOT_VERIFIED",
            operation_id=operation_id,
            binding=binding,
            new_revision=binding if fork else None,
            diff=compute_diff(before, after),
            snapshot=after,
            saved=data["saved"],
            reopened=data["reopened"],
            source_unchanged=data["source_unchanged"],
            replayed=data["replayed"],
        )

    async def fork(self, request: LayoutForkRequest) -> LayoutResult:
        raw = request.model_dump(mode="json")
        data = await self._invoke("fork", raw)
        result = self._result(data, request.binding, fork=True)
        if result.operation_id != request.operation_id:
            raise InvalidInputError("Layout operation identity mismatch")
        if result.snapshot is not None:
            self._check_orientation_snapshot(result.snapshot)
        return result

    async def apply(self, request: LayoutApplyRequest) -> LayoutResult:
        request = LayoutApplyRequest.model_validate_json(request.model_dump_json())
        if request.expected_plan_sha256 != request.plan.plan_sha256:
            raise InvalidInputError("Layout plan hash mismatch")
        if any(
            e.kind == "add_pin" and e.pin is not None and e.pin.label is not None
            for e in request.plan.normalized_edits
        ):
            raise InvalidInputError("Native layout pin labels are not supported")
        payload = request.model_dump(mode="json")
        # Read-only lookup precedes current baseline checks, including after
        # restart/expiry. New writes still recheck baseline inside shared flock.
        data = await self._invoke("lookup", {"action": "apply", "payload": payload})
        if data is None:
            current = await self.inspect(LayoutInspectRequest(binding=request.plan.request.binding))
            validate_plan(
                current,
                request,
                orientation_qualification=self.registration.orientation_qualification,
            )
            data = await self._invoke("apply", payload)
        result = self._result(data, request.plan.request.binding, fork=False)
        if result.operation_id != request.plan.request.operation_id:
            raise InvalidInputError("Layout operation identity mismatch")
        if result.status == "OUTCOME_UNKNOWN":
            return result
        before = LayoutSnapshot.model_validate_json(json.dumps(data["before"]))
        self._check_orientation_snapshot(before)
        validate_plan(
            before, request, orientation_qualification=self.registration.orientation_qualification
        )
        expected, _ = predict_snapshot(
            before,
            request.plan.request,
            orientation_qualification=self.registration.orientation_qualification,
        )
        assert result.snapshot is not None
        self._check_orientation_snapshot(result.snapshot)
        difference = compute_diff(before, result.snapshot, expected=expected)
        if (
            not difference.matches_plan
            or difference.metadata_changes
            or not result.saved
            or not result.reopened
            or not result.source_unchanged
            or result.snapshot.semantic_sha256 != request.plan.expected_semantic_sha256
            or any(p.association != "native_verified" for p in result.snapshot.pins)
        ):
            raise RemoteFailureError("Native layout readback does not match the exact plan")
        return LayoutResult.model_validate_json(
            result.model_copy(
                update={
                    "status": "EDIT_VERIFIED",
                    "diff": difference,
                }
            ).model_dump_json()
        )

    async def diff(self, request: LayoutDiffRequest) -> LayoutResult:
        current = await self.inspect(LayoutInspectRequest(binding=request.binding))
        parent_binding = request.binding.model_copy(
            update={
                "revision_id": request.before_revision_id,
                "parent_revision_id": None,
                "parent_revision_sha256": None,
            }
        )
        # The native registry resolves and validates exact full revision binding;
        # it never derives a remote path from this logical revision ID.
        old = await self._invoke(
            "inspect",
            {"binding": parent_binding.model_dump(mode="json"), "registered_revision": True},
        )
        before = LayoutSnapshot.model_validate_json(json.dumps(old))
        if before.semantic_sha256 != request.expected_before_sha256:
            raise InvalidInputError("Layout diff baseline mismatch")
        return LayoutResult(
            status="DIFF",
            binding=request.binding,
            snapshot=current,
            diff=compute_diff(before, current),
        )

    async def select(self, request: LayoutSelectRequest) -> LayoutResult:
        snapshot = await self.inspect(LayoutInspectRequest(binding=request.binding))
        if snapshot.semantic_sha256 != request.expected_baseline_sha256:
            raise InvalidInputError("Layout selection baseline mismatch")
        return LayoutResult(status="SELECTED", binding=request.binding, snapshot=snapshot)


def create_layout_service(settings: BridgeConfig) -> LayoutService:
    context = select_context(settings)
    if context is None or context.binding.layout_provider_binding is None:
        raise ConfigurationError("LAYOUT_SETUP_REQUIRED: register a pinned native layout provider")
    path: Path = context.binding.layout_provider_binding
    try:
        raw = bounded_document(path)
        if hashlib.sha256(raw).hexdigest() != context.binding.layout_provider_sha256:
            raise ValueError("stale_layout_provider_digest")
        registration = LayoutProviderBinding.model_validate_json(raw)
    except (OSError, ValueError):
        raise ConfigurationError(
            "LAYOUT_SETUP_REQUIRED: invalid pinned layout provider registration",
            details={"reason": "layout_setup_required"},
        ) from None
    return LayoutService(
        NativeLayoutProvider(context, registration),
        orientation_qualification=registration.orientation_qualification,
    )
