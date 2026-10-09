"""Operator-only source/dependency fingerprints from package assets, no admission."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shlex
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge import _native_rendering as rendering
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.generic_ade import (
    AcInputs,
    AdeExecutionRegistration,
    TranInputs,
    _read_input,
)
from cadence_mcp_bridge.generic_measurements import (
    GenericReaderRegistration,
    NodeSignal,
    SourceSignal,
    TransferSignal,
)
from cadence_mcp_bridge.native_runtime import (
    NativeLibrary,
    NativeModelFile,
    NativeRegistration,
    RemotePath,
    projection,
)
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.operator_operations import (
    OperationRejected,
    OperationRequest,
    bounded_document,
)
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    LogicalId,
    VariableModel,
    canonical_digest,
)


class LibrarySelection(VariableModel):
    name: BindingName
    path: RemotePath


class ModelSelection(VariableModel):
    path: RemotePath
    section: BindingName


class FingerprintResponse(VariableModel):
    schema_version: Literal[1]
    status: Literal["REGISTRATION_FINGERPRINTS_OBSERVED"]
    source_tree_sha256: Digest
    ade_state_tree_sha256: Digest
    libraries: Annotated[tuple[NativeLibrary, ...], Field(min_length=1, max_length=32)]
    model_files: Annotated[tuple[NativeModelFile, ...], Field(max_length=128)]
    entries: Annotated[int, Field(strict=True, ge=1, le=32768)]
    content_bytes: Annotated[int, Field(strict=True, ge=0, le=268435456)]
    operator_uid: Annotated[int, Field(strict=True, ge=1)]
    new_simulations: Literal[0]
    new_reservations: Literal[0]
    execution_authorized: Literal[False]

    @field_validator("execution_authorized", mode="before")
    @classmethod
    def no_authority(cls, value: bool) -> bool:
        if value is not False:
            raise ValueError("observation cannot authorize execution")
        return value

    @field_validator("schema_version", "new_simulations", "new_reservations", mode="before")
    @classmethod
    def integer_only(cls, value: int) -> int:
        if type(value) is not int:
            raise ValueError("integer observation counters required")
        return value


class RegistrationObservation(VariableModel):
    schema_version: Literal[1]
    status: Literal["REGISTRATION_FINGERPRINTS_PREPARED_NOT_AUTHORIZED"]
    ade: AdeExecutionRegistration
    libraries: Annotated[tuple[NativeLibrary, ...], Field(min_length=1, max_length=32)]
    model_files: Annotated[tuple[NativeModelFile, ...], Field(max_length=128)]
    source_cell: RemotePath
    source_state: RemotePath
    baseline_input_sha256: Digest
    operator_uid: Annotated[int, Field(strict=True, ge=1)]
    helper_sha256: Digest
    execution_authorized: Literal[False]
    new_simulations: Literal[0]
    new_reservations: Literal[0]

    @field_validator("execution_authorized", mode="before")
    @classmethod
    def no_authority(cls, value: bool) -> bool:
        if value is not False:
            raise ValueError("observation cannot authorize execution")
        return value

    @field_validator("schema_version", "new_simulations", "new_reservations", mode="before")
    @classmethod
    def integer_only(cls, value: int) -> int:
        return FingerprintResponse.integer_only(value)


class DcSelection(VariableModel):
    analysis: Literal["dc"]
    mode: Literal["saved_operating_point"]


class RegistrationProbeRequest(VariableModel):
    schema_version: Literal[1]
    validation_request: OperationRequest
    source_cell: RemotePath
    source_state: RemotePath
    libraries: Annotated[tuple[LibrarySelection, ...], Field(min_length=1, max_length=32)]
    model_includes: Annotated[tuple[ModelSelection, ...], Field(max_length=16)]
    inputs: DcSelection | AcInputs | TranInputs
    baseline_netlist: Path

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({v.name for v in self.libraries}) != len(self.libraries) or len(
            {v.path for v in self.model_includes}
        ) != len(self.model_includes):
            raise ValueError("unique registered library/model selections required")
        for path in (
            self.source_cell,
            self.source_state,
            *(v.path for v in self.libraries),
            *(v.path for v in self.model_includes),
        ):
            if str(PurePosixPath(path)) != path or ".." in PurePosixPath(path).parts:
                raise ValueError("canonical registration paths required")
        return self


def prepared(
    context: ExecutionContext, request: RegistrationProbeRequest
) -> tuple[dict[str, Any], dict[str, Any], str]:
    design = context.contracts.designs.profile(request.validation_request.design_id)
    contract = next(
        (
            c
            for c in context.contracts.designs.analyses_for(design.design_id)
            if c.analysis_id == request.validation_request.analysis_id
        ),
        None,
    )
    source = next((lib for lib in request.libraries if lib.name == design.binding.library), None)
    if (
        contract is None
        or contract.analysis != request.inputs.analysis
        or source is None
        or request.source_cell != source.path + "/" + design.binding.cell
    ):
        raise OperationRejected("registration_design_analysis_binding")
    supplied = {v.logical_id: v for v in request.validation_request.values}
    variables = context.contracts.designs.variable_set(design.design_id)
    if set(supplied) != set(design.allowed_variables):
        raise OperationRejected("all_explicit_registered_values_required")
    parameters = {}
    for variable in () if variables is None else variables.variables:
        value = supplied.get(variable.logical_id)
        if value is None or value.unit != variable.unit or variable.check_number(value.value):
            raise OperationRejected("registered_numeric_contract_denied")
        parameters[variable.cadence_binding] = value.value
    raw = _read_input(_local_path(request.baseline_netlist))
    _, _, analyses, static = rendering.partition_input(raw)  # type: ignore[no-untyped-call]
    inputs = request.inputs.model_dump(mode="json")
    if request.inputs.analysis == "dc":
        if len(analyses) != 1 or analyses[0][0] != "dc":
            raise OperationRejected("registration_baseline_analysis")
        inputs["statement_sha256"] = hashlib.sha256(
            ("dc " + analyses[0][1]).encode("ascii")
        ).hexdigest()
    static_sha = rendering.static_fingerprint(static)  # type: ignore[no-untyped-call]
    rendering.effective_input(  # type: ignore[no-untyped-call]
        raw, parameters, [(m.path, m.section) for m in request.model_includes], inputs, static_sha
    )
    environment = context.contracts.environment
    remote = dict(
        hostname=environment.host.hostname,
        user=environment.host.user,
        workspace_root=environment.paths.workspace_root,
        managed_root=environment.paths.managed_root,
        protected_roots=list(environment.paths.protected_roots),
        source_cell=request.source_cell,
        source_state=request.source_state,
        libraries=[v.model_dump(mode="json") for v in request.libraries],
        model_includes=[v.model_dump(mode="json") for v in request.model_includes],
    )
    ade = dict(
        schema_version=1,
        design_id=design.design_id,
        analysis_id=contract.analysis_id,
        design_profile_sha256=canonical_digest(design),
        variable_set_sha256=canonical_digest(variables) if variables else None,
        static_statements_sha256=static_sha,
        inputs=inputs,
    )
    return remote, ade, hashlib.sha256(raw).hexdigest()


def observe(context: ExecutionContext, request: RegistrationProbeRequest) -> dict[str, Any]:
    remote, ade, baseline_sha = prepared(context, request)
    assets = {
        name: files("cadence_mcp_bridge").joinpath(source).read_bytes()
        for name, source in {
            "copying": "_native_copy.py",
            "modeltrust": "_installation_repair.py",
        }.items()
    }
    known = {name: hashlib.sha256(raw).hexdigest() for name, raw in assets.items()}
    code = (
        files("cadence_mcp_bridge").joinpath("_registration_probe.py").read_text("utf-8")
        + "\nmain("
        + repr(known)
        + ")\n"
    )
    status, stdout, stderr = run_fixed(
        _ssh(context.contracts.environment) + ["-c", shlex.quote(code)],
        _canonical(
            dict(
                request=remote,
                assets={
                    name: base64.b64encode(raw).decode("ascii") for name, raw in assets.items()
                },
            )
        ),
        OpenSshBackend._ssh_environment(),
        timeout=60,
        limit=262144,
    )
    if status or stderr:
        raise OperationRejected("registration_fingerprint_rejected")
    _closed_document(stdout)
    response = FingerprintResponse.model_validate_json(stdout)
    result = response.model_dump(mode="json")
    libraries = response.libraries
    models = response.model_files
    if [(v.name, v.path) for v in libraries] != [(v.name, v.path) for v in request.libraries]:
        raise OperationRejected("registration_fingerprint_library_binding")
    hashes = {v.path: v.file_sha256 for v in models}
    if any(v.path not in hashes for v in request.model_includes):
        raise OperationRejected("registration_model_dependency_binding")
    ade.update(
        source_tree_sha256=result["source_tree_sha256"],
        ade_state_tree_sha256=result["ade_state_tree_sha256"],
        model_includes=[
            dict(path=v.path, section=v.section, file_sha256=hashes[v.path])
            for v in request.model_includes
        ],
    )
    registration = AdeExecutionRegistration.model_validate_json(json.dumps(ade))
    if (
        hashlib.sha256(_read_input(_local_path(request.baseline_netlist))).hexdigest()
        != baseline_sha
    ):
        raise OperationRejected("registration_baseline_changed")
    return dict(
        schema_version=1,
        status="REGISTRATION_FINGERPRINTS_PREPARED_NOT_AUTHORIZED",
        ade=registration.model_dump(mode="json"),
        libraries=[v.model_dump(mode="json") for v in libraries],
        model_files=[v.model_dump(mode="json") for v in models],
        source_cell=request.source_cell,
        source_state=request.source_state,
        baseline_input_sha256=baseline_sha,
        operator_uid=result["operator_uid"],
        helper_sha256=hashlib.sha256(code.encode()).hexdigest(),
        execution_authorized=False,
        new_simulations=0,
        new_reservations=0,
    )


def operator_observe(
    context: ExecutionContext, request_path: Path, output: Path
) -> dict[str, object]:
    request = RegistrationProbeRequest.model_validate_json(bounded_document(request_path))
    target = _local_path(output)
    if target.exists() or not target.parent.is_dir():
        raise OperationRejected("exclusive_registration_output_required")
    result = observe(context, request)
    # Private output is an operator record, never MCP-visible path/content output.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(_canonical(result))
        stream.flush()
        os.fsync(stream.fileno())
    return dict(
        status=result["status"],
        record_sha256=hashlib.sha256(_canonical(result)).hexdigest(),
        operator_uid=result["operator_uid"],
        libraries=len(result["libraries"]),
        model_files=len(result["model_files"]),
        remote_contact=True,
        execution_authorized=False,
        new_simulations=0,
        new_reservations=0,
    )


class ReaderDefinition(VariableModel):
    measurement_id: LogicalId
    nodes: Annotated[tuple[NodeSignal, ...], Field(min_length=1, max_length=8)]
    sources: Annotated[tuple[SourceSignal, ...], Field(max_length=8)]
    transfer: TransferSignal | None
    maximum_samples: Annotated[int, Field(ge=2, le=256)]


def assemble(
    context: ExecutionContext,
    request_paths: list[Path],
    record_paths: list[Path],
    reader_paths: list[Path],
    identity_manifest_sha256: str,
    output: Path,
) -> dict[str, object]:
    if not 1 <= len(request_paths) <= 48 or not len(request_paths) == len(record_paths) == len(
        reader_paths
    ):
        raise OperationRejected("registration_assembly_count")
    target = _local_path(output)
    if target.exists() or not target.parent.is_dir():
        raise OperationRejected("exclusive_registration_output_required")
    routes = []
    for request_path, record_path, reader_path in zip(
        request_paths, record_paths, reader_paths, strict=True
    ):
        request = RegistrationProbeRequest.model_validate_json(bounded_document(request_path))
        observation = RegistrationObservation.model_validate_json(bounded_document(record_path))
        record = observation.model_dump(mode="json")
        _, expected, baseline_sha = prepared(context, request)
        if (
            record.get("status") != "REGISTRATION_FINGERPRINTS_PREPARED_NOT_AUTHORIZED"
            or record.get("baseline_input_sha256") != baseline_sha
            or record.get("source_cell") != request.source_cell
            or record.get("source_state") != request.source_state
            or record.get("new_simulations") != 0
            or record.get("new_reservations") != 0
            or record.get("execution_authorized") is not False
            or any(record["ade"].get(key) != value for key, value in expected.items())
            or [(v["name"], v["path"]) for v in record["libraries"]]
            != [(v.name, v.path) for v in request.libraries]
            or [(v["path"], v["section"]) for v in record["ade"]["model_includes"]]
            != [(v.path, v.section) for v in request.model_includes]
        ):
            raise OperationRejected("registration_observation_binding")
        ade = AdeExecutionRegistration.model_validate_json(json.dumps(record["ade"]))
        definition = ReaderDefinition.model_validate_json(bounded_document(reader_path))
        measurement = next(
            (
                m
                for m in context.contracts.designs.measurements_for(ade.design_id)
                if m.measurement_id == definition.measurement_id
                and m.analysis_id == ade.analysis_id
            ),
            None,
        )
        if measurement is None:
            raise OperationRejected("registration_reader_measurement_binding")
        reader = GenericReaderRegistration.model_validate_json(
            json.dumps(
                dict(
                    schema_version=1,
                    design_id=ade.design_id,
                    analysis_id=ade.analysis_id,
                    ade_registration_sha256=canonical_digest(ade),
                    measurement_contract_sha256=canonical_digest(measurement),
                    **definition.model_dump(mode="json"),
                )
            )
        )
        routes.append(
            dict(
                validation_request=request.validation_request.model_dump(mode="json"),
                ade=ade.model_dump(mode="json"),
                reader=reader.model_dump(mode="json"),
                source_cell=record["source_cell"],
                source_state=record["source_state"],
                libraries=record["libraries"],
                model_files=record["model_files"],
            )
        )
    registration = NativeRegistration.model_validate_json(
        json.dumps(
            dict(schema_version=1, identity_manifest_sha256=identity_manifest_sha256, routes=routes)
        )
    )
    projection(context, registration)
    raw = _canonical(registration.model_dump(mode="json"))
    if len(raw) > 65536:
        raise OperationRejected("registration_assembly_document_bound")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return dict(
        status="NATIVE_REGISTRATION_ASSEMBLED_NOT_AUTHORIZED",
        registration_sha256=hashlib.sha256(raw).hexdigest(),
        routes=len(routes),
        execution_authorized=False,
        remote_contact=False,
        new_simulations=0,
        new_reservations=0,
    )
