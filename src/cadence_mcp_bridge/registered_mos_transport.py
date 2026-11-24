"""Resolve one operator-registered MOS edit and call C1's fixed guest phases."""

from __future__ import annotations

import base64
import json
import os
import re
import shlex
import time
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from cadence_mcp_bridge import _registered_mos_edit_phase as guest_contract
from cadence_mcp_bridge import m2_cdf
from cadence_mcp_bridge.amplifier_pm0_service import _FixedAmplifierPm0Provider
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.parameter_changes import ChangePlan
from cadence_mcp_bridge.pmos_default_service import (
    _artifact,
    _document,
    _read,
    _require,
    _retain,
    _sha,
)
from cadence_mcp_bridge.registered_mos_edit import (
    MosEditSubject,
    MosEditValues,
    NativeMosEditCapture,
    NativeMosEditReadback,
    NativeMosEditSave,
    RegisteredMosEditBinding,
    RegisteredMosEditRoute,
    RegisteredMosEditService,
    RetainedMosEdit,
    same_saved_testbench,
)
from cadence_mcp_bridge.runtime_context import (
    ExecutionContext,
    RuntimeRejected,
    read_pmos_default_change_binding,
    resource_lock,
)
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest

Phase = Literal["EDIT_SAVE", "INDEPENDENT_REOPEN_NETLIST"]
_EDIT: Phase = "EDIT_SAVE"
_REOPEN: Phase = "INDEPENDENT_REOPEN_NETLIST"
_CLAIM = "registered-mos-intent.private.json"
_ASSET = "_registered_mos_edit_phase.py"
_LIMIT = 524_288


class _Registration(VariableModel):
    schema_version: Literal[3]
    route: Literal["registered_mos_edit"]
    context_id: LogicalId
    resource_domain_sha256: Digest
    evidence_directory: Path
    scope_sha256: Digest
    authority_sha256: Digest


class _Scope(VariableModel):
    schema_version: Literal[1]
    route: Literal["registered_mos_edit"]
    context_id: LogicalId
    resource_domain_sha256: Digest
    environment_sha256: Digest
    native_manifest_sha256: Digest
    subject: MosEditSubject
    route_qualification: RegisteredMosEditRoute
    plan: ChangePlan
    candidate_request: MosEditValues
    guest_sha256: Digest
    native_safety_sha256: Digest
    valid_until_unix: Annotated[int, Field(gt=0)]


class _Authority(VariableModel):
    owner: Literal["C0"]
    operation_id: OperationId
    scope_sha256: Digest
    approved_phases: tuple[Literal["EDIT_SAVE"], Literal["INDEPENDENT_REOPEN_NETLIST"]]
    valid_until_unix: Annotated[int, Field(gt=0)]


class _Terminal(VariableModel):
    readback: NativeMosEditReadback
    input_base64: str
    cdf_frame_base64: str


def _encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _fixed_assets(scope: _Scope) -> tuple[bytes, bytes, bytes]:
    guest_contract.exact_route(scope.model_dump(mode="json"))  # type: ignore[no-untyped-call]
    package = files("cadence_mcp_bridge")
    try:
        collect = m2_cdf.render_reopened_mos_cdf
        guest = package.joinpath(_ASSET).read_bytes()
        support = package.joinpath("_amp_pm0_default_phase.py").read_bytes()
        collector = collect()
    except (AttributeError, FileNotFoundError):
        raise OperationRejected("registered_mos_fixed_package_incomplete") from None
    digest_pins = (scope.guest_sha256, guest_contract.SUPPORT_SHA256, guest_contract.CDF_SHA256)
    _require(
        all(
            0 < len(raw) <= 65_536 and _sha(raw) == digest and raw.isascii()
            for raw, digest in zip((guest, support, collector), digest_pins, strict=True)
        ),
        "registered_mos_fixed_assets",
    )
    return guest, support, collector


class _FixedRegisteredMosProvider:
    def __init__(
        self,
        context: ExecutionContext,
        directory: Path,
        registration: _Registration,
        scope: _Scope,
        raw_scope: bytes,
        baseline: bytes,
    ) -> None:
        self._context = context
        self._directory = directory
        self._registration = registration
        self._scope = scope
        self._raw_scope = raw_scope
        self._baseline = baseline

    def _intent(self, binding: RegisteredMosEditBinding) -> bytes:
        return _canonical(
            {
                "operation_id": binding.operation_id,
                "scope_sha256": binding.scope_sha256,
                "plan_sha256": binding.plan_sha256,
                "dispatch_binding_sha256": canonical_digest(binding),
                "retry": False,
            }
        )

    def lookup(self, binding: RegisteredMosEditBinding) -> RetainedMosEdit | None:
        claim = self._directory / _CLAIM
        if not os.path.lexists(claim):
            if any(self._directory.glob("registered-mos-phase-*")):
                return RetainedMosEdit(None)
            return None
        try:
            raw = _read(claim, 4096)
            _document(raw)
        except (OSError, ValueError):
            return RetainedMosEdit(None)
        _require(raw == self._intent(binding), "registered_mos_intent_conflict")
        try:
            edit_raw = self._captured(binding, _EDIT, None)
            edit = self._saved(binding, edit_raw)
            return self._terminal(edit, self._captured(binding, _REOPEN, _sha(edit_raw)))
        except (OSError, ValueError, RecursionError):
            return RetainedMosEdit(None)

    def claim(self, binding: RegisteredMosEditBinding) -> bool:
        with resource_lock(self._context):
            if self.lookup(binding) is not None:
                return False
            self._prepare(binding, _EDIT, None)
            _retain(self._directory / _CLAIM, self._intent(binding))
        return True

    def dispatch(self, binding: RegisteredMosEditBinding) -> RetainedMosEdit:
        with resource_lock(self._context):
            _require(
                _read(self._directory / _CLAIM, 4096) == self._intent(binding),
                "registered_mos_intent_conflict",
            )
            edit_raw = self._run(binding, _EDIT, None)
            edit = self._saved(binding, edit_raw)
            return self._terminal(edit, self._run(binding, _REOPEN, _sha(edit_raw)))

    def _prepare(
        self, binding: RegisteredMosEditBinding, phase: Phase, previous: str | None
    ) -> tuple[list[str], bytes]:
        scope, directory = self._scope, self._directory
        authority = _read(
            directory / "c0-exact-ack.private.json", 4096, self._registration.authority_sha256
        )
        _document(authority)
        ack = _Authority.model_validate_json(authority)
        _require(
            (ack.operation_id, ack.scope_sha256) == (binding.operation_id, binding.scope_sha256)
            and ack.valid_until_unix == scope.valid_until_unix
            and time.time() < ack.valid_until_unix,
            "registered_mos_authority",
        )
        _read(
            directory / "cdf-evidence.private",
            262_144,
            scope.route_qualification.qualification.evidence_sha256,
        )
        _read(
            directory / "update-route-evidence.private",
            65_536,
            scope.route_qualification.update_route_sha256,
        )
        safety = _read(directory / "native-safety.private.json", 65_536, scope.native_safety_sha256)
        _document(safety)
        guest, support, collector = _fixed_assets(scope)
        bootstrap = shlex.quote(
            "import hashlib,sys\n"
            f"fixed=sys.stdin.read({len(guest)})\n"
            f"if hashlib.sha256(fixed.encode('ascii')).hexdigest()!='{scope.guest_sha256}':"
            " raise ValueError('MOS asset')\n"
            f"eval(compile(fixed,'{_ASSET}','exec'))"
        )
        return (
            _ssh(self._context.contracts.environment)
            + ["-c", bootstrap, binding.scope_sha256, phase],
            guest
            + _canonical(
                {
                    "managed_root": self._context.contracts.environment.paths.managed_root,
                    "scope_base64": _encode(self._raw_scope),
                    "authority_base64": _encode(authority),
                    "baseline_base64": _encode(self._baseline),
                    "native_safety_base64": _encode(safety),
                    "support_base64": _encode(support),
                    "cdf_collector_base64": _encode(collector),
                    "previous_receipt_sha256": previous,
                }
            ),
        )

    def _path(self, phase: Phase, label: str) -> Path:
        return self._directory / f"registered-mos-phase-{phase}-{label}"

    def _phase_intent(
        self, binding: RegisteredMosEditBinding, previous: str | None
    ) -> dict[str, object]:
        return {
            "claim_sha256": _sha(self._intent(binding)),
            "previous_receipt_sha256": previous,
            "retry": False,
        }

    def _run(self, binding: RegisteredMosEditBinding, phase: Phase, previous: str | None) -> bytes:
        argv, payload = self._prepare(binding, phase, previous)
        _retain(
            self._path(phase, "intent.private.json"),
            _canonical(
                {
                    **self._phase_intent(binding, previous),
                    "request_sha256": _sha(payload),
                }
            ),
        )
        transport = self._path(phase, "transport.private.json")
        try:
            code, out, err = run_fixed(
                argv, payload, OpenSshBackend._ssh_environment(), timeout=60, limit=_LIMIT
            )
        except (OSError, ValueError) as exc:
            _retain(
                transport,
                _canonical(
                    {"status": "TRANSPORT_FAILED_RETAINED", "error_type": type(exc).__name__}
                ),
            )
            raise
        _retain(self._path(phase, "stdout.private.json"), out)
        _retain(self._path(phase, "stderr.private.txt"), err)
        _retain(transport, _canonical(_FixedAmplifierPm0Provider._transport_record(code, out, err)))
        _require(code == 0 and not err, "registered_mos_native_dispatch_unverified")
        return out

    def _captured(
        self, binding: RegisteredMosEditBinding, phase: Phase, previous: str | None
    ) -> bytes:
        intent = _document(_read(self._path(phase, "intent.private.json"), 4096))
        request_sha = intent.pop("request_sha256", None)
        out = _read(self._path(phase, "stdout.private.json"), _LIMIT)
        err = _read(self._path(phase, "stderr.private.txt"), _LIMIT)
        transport = _document(_read(self._path(phase, "transport.private.json"), 4096))
        _require(
            isinstance(request_sha, str)
            and re.fullmatch(r"[a-f0-9]{64}", request_sha) is not None
            and intent == self._phase_intent(binding, previous)
            and not err
            and transport == _FixedAmplifierPm0Provider._transport_record(0, out, err),
            "registered_mos_retained_transport",
        )
        return out

    def _saved(self, binding: RegisteredMosEditBinding, raw: bytes) -> NativeMosEditSave:
        _document(raw)
        save = NativeMosEditSave.model_validate_json(raw)
        before, after = save.baseline, save.saved
        route = self._scope.route_qualification
        _require(
            (save.operation_id, save.plan_sha256, save.scope_sha256)
            == (binding.operation_id, binding.plan_sha256, binding.scope_sha256)
            and save.source_preservation_sha256 == binding.source_preservation_sha256
            and (before.stage, after.stage) == ("baseline", "saved")
            and (before.revision_sha256, before.testbench_revision_sha256)
            == (binding.owned_before_view_tree_sha256, binding.owned_before_testbench_tree_sha256)
            and after.revision_sha256
            not in (before.revision_sha256, self._scope.plan.baseline.revision_sha256)
            and same_saved_testbench(route.qualification.target, before, after)
            and before.footprint_sha256 == after.footprint_sha256
            and before.properties == route.before
            and after.properties == route.after
            and before.receipt_sha256 != after.receipt_sha256,
            "registered_mos_save_receipt",
        )
        return save

    @staticmethod
    def _terminal(save: NativeMosEditSave, raw: bytes) -> RetainedMosEdit:
        _closed_document(raw, max_bytes=_LIMIT)
        terminal = _Terminal.model_validate_json(raw)
        _require(
            _canonical(json.loads(raw)) == raw
            and NativeMosEditSave.model_validate(
                terminal.readback.model_dump(include=set(NativeMosEditSave.model_fields))
            )
            == save,
            "registered_mos_reopen_receipt",
        )
        observed = terminal.readback
        return RetainedMosEdit(
            NativeMosEditCapture(
                observed,
                _artifact(terminal.input_base64, observed.netlist_sha256, 32_768),
                _artifact(terminal.cdf_frame_base64, observed.cdf_frame_sha256, 262_144),
            )
        )


def registered_mos_edit(context: ExecutionContext) -> RegisteredMosEditService:
    """Resolve version 3 of the existing pinned operator edit registration slot."""
    path = context.binding.pmos_default_change_binding
    expected = context.binding.pmos_default_change_sha256
    if path is None or expected is None:
        raise OperationRejected("registered_mos_edit_not_registered")
    try:
        raw = read_pmos_default_change_binding(path, expected)
        _document(raw)
        reg = _Registration.model_validate_json(raw)
        directory = _local_path(reg.evidence_directory)
        _require(
            reg.evidence_directory.is_absolute()
            and directory.is_dir()
            and all(
                not _local_path(p).is_relative_to(directory)
                for p in (
                    context.binding.analysis_journal,
                    context.binding.sweep_journal,
                    context.lock_path,
                )
            ),
            "registered_mos_evidence_directory",
        )
        scope_raw = _read(directory / "execution-scope.private.json", 32_768, reg.scope_sha256)
        _document(scope_raw)
        scope = _Scope.model_validate_json(scope_raw)
        _require(
            reg.context_id == scope.context_id == context.binding.context_id
            and reg.resource_domain_sha256
            == scope.resource_domain_sha256
            == context.resource_domain_sha256
            and scope.environment_sha256 == context.binding.environment_sha256
            and scope.native_manifest_sha256 == context.binding.runner_sha256
            and scope.subject.plan_sha256 == scope.plan.plan_sha256,
            "registered_mos_runtime_binding",
        )
        binding = RegisteredMosEditBinding(
            scope_sha256=reg.scope_sha256, **scope.subject.model_dump()
        )
        baseline = _read(
            directory / "baseline-input.private.scs", 32_768, scope.plan.baseline.netlist_sha256
        )
        engine = RegisteredMosEditService(
            binding,
            scope.route_qualification,
            scope.plan.candidate_revision,
            scope.candidate_request,
            baseline,
            _FixedRegisteredMosProvider(context, directory, reg, scope, scope_raw, baseline),
            expected_binding_sha256=canonical_digest(binding),
        )
        _require(engine.plan == scope.plan, "registered_mos_plan_conflict")
        return engine
    except (OSError, ValueError, RecursionError, RuntimeRejected):
        raise OperationRejected("registered_mos_edit_registration_invalid") from None
