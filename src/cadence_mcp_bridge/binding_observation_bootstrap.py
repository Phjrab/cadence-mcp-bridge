"""Local authenticated construction, never operational observer admission.

The installed package and this interpreter's normal startup remain the local
trust root. Exact retained bytes, rather than cached namesake modules, supply the
review-only worker. This does not attest OCEAN, loader, library initialization,
remote installation, authority, or the registered source on disk.
"""

from __future__ import annotations

import hashlib
import json
import types
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.binding_observation import BindingScanRequest
from cadence_mcp_bridge.designs import DesignProfile
from cadence_mcp_bridge.environments import EnvironmentModel, EnvironmentProfile
from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration
from cadence_mcp_bridge.generic_measurements import GenericReaderRegistration
from cadence_mcp_bridge.native_runtime import NativeLibrary, NativeModelFile, RemotePath
from cadence_mcp_bridge.variable_contracts import (
    DesignVariables,
    Digest,
    LogicalId,
    VariableContract,
    canonical_digest,
)

_HELPERS = {
    "copy.py": (
        "_native_copy.py",
        "97e3805a6c407617bc588c20907d8804bd0a251bc315ca7f47a16918c44f94e7",
    ),
    "reservations.py": (
        "_shared_reservations.py",
        "959712af7bacb06fac9dda204fe4ab9db3a8e51c8e51743805eb5f7d61e5b372",
    ),
    "process.py": (
        "_native_eda_worker.py",
        "e54b182be1cce49df2fc0cde9dfb70388747ec3ecf06afbadb33b4ac5f9062c0",
    ),
}
_WORKER = "_binding_observation.py"
_CODE_LIMIT = 131_072


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("ascii")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _document(raw: bytes, limit: int) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > limit:
        raise ValueError("binding_bootstrap_document_bound")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("binding_bootstrap_duplicate_json")
            result[key] = value
        return result

    def constant(_: str) -> None:
        raise ValueError("binding_bootstrap_nonfinite_json")

    try:
        result = json.loads(raw.decode("ascii"), object_pairs_hook=pairs, parse_constant=constant)
        if type(result) is not dict or _canonical(result) != raw:
            raise ValueError("binding_bootstrap_canonical_object_required")
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError):
        raise ValueError("binding_bootstrap_invalid_json") from None
    return result


class _Selection(EnvironmentModel):
    schema_version: Literal[1]
    design_id: LogicalId
    analysis_id: LogicalId
    profile_sha256: Digest
    registration_sha256: Digest
    request_sha256: Digest
    collector_sha256: Digest
    helper_sha256: Digest


class _Route(EnvironmentModel):
    design_id: LogicalId
    analysis_id: LogicalId
    analysis: Literal["dc", "ac", "tran"]
    profile: DesignProfile
    variables: Annotated[tuple[VariableContract, ...], Field(max_length=32)]
    source_cell: RemotePath
    source_state: RemotePath
    model_files: Annotated[tuple[NativeModelFile, ...], Field(max_length=128)]
    libraries: Annotated[tuple[NativeLibrary, ...], Field(min_length=1, max_length=32)]
    ade: AdeExecutionRegistration
    reader: GenericReaderRegistration

    @model_validator(mode="after")
    def coherent(self) -> Self:
        identity = (self.design_id, self.analysis_id)
        if identity != (self.ade.design_id, self.ade.analysis_id) or identity != (
            self.reader.design_id, self.reader.analysis_id,
        ) or self.profile.design_id != self.design_id or (
            self.analysis != self.ade.inputs.analysis
            or self.analysis not in self.profile.allowed_analyses
            or self.ade.design_profile_sha256 != canonical_digest(self.profile)
            or self.reader.ade_registration_sha256 != canonical_digest(self.ade)
        ):
            raise ValueError("binding_bootstrap_route_identity")
        ids = [variable.logical_id for variable in self.variables]
        bindings = [variable.cadence_binding for variable in self.variables]
        if len(set(ids)) != len(ids) or len(set(bindings)) != len(bindings) or (
            set(ids) != set(self.profile.allowed_variables)
        ):
            raise ValueError("binding_bootstrap_route_variables")
        variable_set = DesignVariables(
            design_id=self.design_id, design_profile_sha256=canonical_digest(self.profile),
            variables=self.variables,
        )
        # Projection represents both an absent variable set and an explicitly
        # registered empty set as []. Its ADE digest retains that distinction.
        expected_variables: set[str | None] = {canonical_digest(variable_set)}
        if not self.variables:
            expected_variables.add(None)
        if self.ade.variable_set_sha256 not in expected_variables:
            raise ValueError("binding_bootstrap_route_variable_digest")
        for source in (self.source_cell, self.source_state):
            if str(PurePosixPath(source)) != source or ".." in PurePosixPath(source).parts:
                raise ValueError("binding_bootstrap_source_path")
        libraries = {library.name: library for library in self.libraries}
        source_library = libraries.get(self.profile.binding.library)
        if len(libraries) != len(self.libraries) or source_library is None or (
            self.source_cell != source_library.path + "/" + self.profile.binding.cell
        ):
            raise ValueError("binding_bootstrap_route_library")
        models = {model.path: model.file_sha256 for model in self.model_files}
        if list(models) != sorted(set(models)) or len(models) != len(self.model_files) or (
            bool(models) != bool(self.ade.model_includes)
        ) or any(models.get(model.path) != model.file_sha256 for model in self.ade.model_includes):
            raise ValueError("binding_bootstrap_route_models")
        return self


class _Registration(EnvironmentModel):
    schema_version: Literal[1]
    identity_manifest_sha256: Digest
    environment_sha256: Digest
    design_sha256: Digest
    pdk_sha256: Digest
    routes: Annotated[tuple[_Route, ...], Field(min_length=1, max_length=48)]

    @model_validator(mode="after")
    def distinct(self) -> Self:
        identities = [(route.design_id, route.analysis_id) for route in self.routes]
        if identities != sorted(set(identities)):
            raise ValueError("binding_bootstrap_registration_routes")
        return self


def _registered_request(
    profile: EnvironmentProfile, registration: _Registration,
    selection: _Selection, request: BindingScanRequest,
) -> None:
    routes = [route for route in registration.routes if (route.design_id, route.analysis_id) == (
        selection.design_id, selection.analysis_id,
    )]
    if len(routes) != 1:
        raise ValueError("binding_bootstrap_selected_route")
    route = routes[0]
    if route.analysis != "dc" or route.ade.inputs.analysis != "dc" or (
        route.ade.inputs.mode != "saved_operating_point"
        or route.profile.binding.ade.kind != "ade_l"
        or route.profile.work_copy_policy != "owned_copy_only"
        or not 1 <= len(route.variables) <= 4
        or any(variable.unit not in ("V", "A") for variable in route.variables)
        or route.profile.environment_id != profile.environment_id
    ):
        raise ValueError("binding_bootstrap_saved_dc_va_route_required")
    if (request.library, request.cell, request.view) != (
        route.profile.binding.library, route.profile.binding.cell, route.profile.binding.view,
    ) or {(v.logical_id, v.cadence_binding) for v in request.variables} != {
        (v.logical_id, v.cadence_binding) for v in route.variables
    }:
        raise ValueError("binding_bootstrap_complete_request_binding")
    workspace = PurePosixPath(profile.paths.workspace_root)
    managed = PurePosixPath(profile.paths.managed_root)
    protected = [PurePosixPath(root) for root in profile.paths.protected_roots]
    for source in (route.source_cell, route.source_state):
        path = PurePosixPath(source)
        if not path.is_relative_to(workspace) or path.is_relative_to(managed) or any(
            path.is_relative_to(root) for root in protected
        ):
            raise ValueError("binding_bootstrap_registered_source_roots")
    for library in route.libraries:
        path = PurePosixPath(library.path)
        if path.is_relative_to(managed) or not any(
            path.is_relative_to(root) for root in (workspace, *protected)
        ):
            raise ValueError("binding_bootstrap_registered_library_roots")
    if any(not any(PurePosixPath(model.path).is_relative_to(root) for root in protected)
           for model in route.model_files):
        raise ValueError("binding_bootstrap_registered_model_roots")


def construct_worker(
    profile_raw: bytes, registration_raw: bytes, selection_raw: bytes, request_raw: bytes,
) -> Any:
    """Validate canonical local descriptions and retain authenticated code in memory.

    There is no arbitrary resource/code-path argument, asset, activation or trust
    flag. Operator profile paths remain inert registered configuration here.
    Returned worker ``observe`` is unconditionally disabled. Its private methods
    are implementation pieces, never an operational admission API.
    """
    for raw, bound in (
        (profile_raw, 65_536), (registration_raw, 262_144),
        (selection_raw, 4096), (request_raw, 4096),
    ):
        _document(raw, bound)
    profile = EnvironmentProfile.model_validate_json(profile_raw)
    registration = _Registration.model_validate_json(registration_raw)
    selection = _Selection.model_validate_json(selection_raw)
    request = BindingScanRequest.model_validate_json(request_raw)
    if (_digest(profile_raw), _digest(registration_raw), _digest(request_raw)) != (
        selection.profile_sha256, selection.registration_sha256, selection.request_sha256,
    ) or registration.environment_sha256 != selection.profile_sha256:
        raise ValueError("binding_bootstrap_manifest_digest")
    _registered_request(profile, registration, selection, request)

    # Read fixed installed resources once; validate every retained byte before
    # compiling any of them. Changed caches/paths cannot supply worker code.
    package = files("cadence_mcp_bridge")
    retained: dict[str, bytes] = {}
    for name in (_WORKER, *(source for source, _ in _HELPERS.values())):
        with package.joinpath(name).open("rb") as stream:
            raw = stream.read(_CODE_LIMIT + 1)
        if type(raw) is not bytes or not raw or len(raw) > _CODE_LIMIT:
            raise ValueError("binding_bootstrap_installed_code_bound")
        retained[name] = raw.replace(b"\r\n", b"\n")
    if _digest(retained[_WORKER]) != selection.helper_sha256:
        raise ValueError("binding_bootstrap_installed_worker_digest")
    assets: dict[str, bytes] = {}
    pins: dict[str, str] = {}
    for name, (source, pin) in _HELPERS.items():
        if _digest(retained[source]) != pin:
            raise ValueError("binding_bootstrap_fixed_helper_digest")
        assets[name], pins[name] = retained[source], pin

    module = types.ModuleType("_cadence_binding_observation_retained")
    module.__dict__["__package__"] = None
    exec(compile(retained[_WORKER], _WORKER, "exec"), module.__dict__)
    if pins != module.HELPER_PINS:
        raise ValueError("binding_bootstrap_compiled_helper_inventory")
    if _digest(module.render_collector(request.model_dump(mode="json"))) != (
        selection.collector_sha256
    ):
        raise ValueError("binding_bootstrap_collector_digest")
    worker = module.BindingObservationWorker(
        profile_raw, registration_raw, selection.model_dump(mode="json"), assets, pins,
    )
    worker._bound(request.model_dump(mode="json"))
    return worker
