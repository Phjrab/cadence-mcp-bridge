"""Host registration and fixed transport for the bounded AMP PM0 writer.

The packaged guest owns Cadence operations, live protection checks and guest
receipts. The host never loads executable bytes from an operator document.
"""

from __future__ import annotations

import base64
import binascii
import os
import shlex
import subprocess
import time
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from cadence_mcp_bridge.amplifier_pm0_default import (
    AmplifierPm0DispatchBinding,
    RegisteredAmplifierPm0DefaultChange,
    _pm0_frame,
    verify_amplifier_pm0_save_metadata,
)
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeResult
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.parameter_changes import (
    ChangePlan,
    MosWidthQualification,
    project_netlist_change,
)
from cadence_mcp_bridge.pmos_default_service import _document, _read, _require, _retain, _sha
from cadence_mcp_bridge.runtime_context import ExecutionContext, resource_lock
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest

_ROUTE = "amplifier_pm0_default"
_ASSETS = (
    "_amp_pm0_default_phase.py",
    "_amp_pm0_default_edit.ocn",
    "_amp_pm0_default_verify.ocn",
)
_LIMIT = 131_072
_ACTIONS = ("edit", "readback-netlist")
_ASSET_LIMITS = (49_152, 32_768, 32_768)


class _Registration(VariableModel):
    schema_version: Literal[2]
    route: Literal["amplifier_pm0_default"]
    context_id: LogicalId
    resource_domain_sha256: Digest
    scope_sha256: Digest
    evidence_directory: Path
    authority_sha256: Digest


class _NativePins(VariableModel):
    site_sha256: Digest
    layout_manifest_sha256: Digest
    layout_worker_sha256: Digest
    owned_copy_operation_id: OperationId
    owned_library_tree_sha256: Digest
    baseline_observation_operation_id: OperationId
    baseline_observation_receipt_sha256: Digest
    baseline_signature_sha256: Digest
    source_view_tree_sha256: Digest
    source_library_tree_sha256: Digest
    archive_cell_tree_sha256: Digest
    archive_library_tree_sha256: Digest
    archive_state_tree_sha256: Digest
    ade_tree_sha256: Digest
    technology_tree_sha256: Digest
    model_graph_sha256: Digest
    ledger_sha256: Digest
    retained_jobs_sha256: Digest
    supplemental_bytes: Annotated[int, Field(ge=0, le=33_554_432)]
    job_limit_bytes: Annotated[int, Field(ge=524_288, le=8_388_608)]


class _Scope(VariableModel):
    schema_version: Literal[1]
    route: Literal["amplifier_pm0_default"]
    context_id: LogicalId
    resource_domain_sha256: Digest
    environment_sha256: Digest
    native_manifest_sha256: Digest
    operation_id: OperationId
    owned_library: Annotated[str, Field(pattern=r"^Amp[A-Za-z0-9_]{3,60}$")]
    owned_cell: Literal["Differential_Amplifier_TB2"]
    owned_view: Literal["schematic"]
    owned_before_view_tree_sha256: Digest
    source_preservation_sha256: Digest
    qualification: MosWidthQualification
    plan: ChangePlan
    plan_sha256: Digest
    guest_sha256: Digest
    edit_script_sha256: Digest
    verify_script_sha256: Digest
    valid_until_unix: Annotated[int, Field(gt=0)]
    native: _NativePins


class _Authority(VariableModel):
    owner: Literal["C0"]
    operation_id: OperationId
    scope_sha256: Digest
    approved_actions: tuple[Literal["edit"], Literal["readback-netlist"]]
    valid_until_unix: Annotated[int, Field(gt=0)]


class _Receipt(VariableModel):
    status: Literal["VERIFIED"]
    operation_id: OperationId
    scope_sha256: Digest
    plan_sha256: Digest
    owned_before_view_tree_sha256: Digest
    saved_view_tree_sha256: Digest
    reopened_view_tree_sha256: Digest
    netlisted_view_tree_sha256: Digest
    source_preservation_sha256: Digest
    reopen_receipt_sha256: Digest
    netlist_receipt_sha256: Digest
    presave_signature_sha256: Digest
    reopened_signature_sha256: Digest
    netlist_sha256: Digest
    edit_live_counter: Annotated[int, Field(ge=0)]
    reopen_frame: Annotated[tuple[str, ...], Field(min_length=17, max_length=17)]
    ocean_calls: Literal[2]
    simulations: Literal[0]
    reservations: Literal[0]


class _Response(VariableModel):
    receipt: _Receipt
    receipt_sha256: Digest
    presave_base64: str
    reopened_base64: str
    input_base64: str


class _EditReceipt(VariableModel):
    status: Literal["SAVED"]
    operation_id: OperationId
    scope_sha256: Digest
    saved_view_tree_sha256: Digest
    saved_library_tree_sha256: Digest
    presave_signature_sha256: Digest
    reopened_signature_sha256: Digest
    edit_live_counter: Annotated[int, Field(ge=0)]
    source_preservation_sha256: Digest


class _EditResponse(VariableModel):
    receipt: _EditReceipt
    receipt_sha256: Digest


def _decode(encoded: str, limit: int, expected: str | None = None) -> bytes:
    try:
        if len(encoded) > 4 * ((limit + 2) // 3):
            raise ValueError("encoded AMP evidence exceeds bound")
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise OperationRejected("amp_pm0_invalid_native_evidence") from exc
    _require(
        0 < len(data) <= limit and (expected is None or _sha(data) == expected),
        "amp_pm0_native_evidence_digest",
    )
    return data


def _asset_bytes(scope: _Scope) -> tuple[bytes, bytes, bytes]:
    package = files("cadence_mcp_bridge")
    payloads = tuple(package.joinpath(name).read_bytes() for name in _ASSETS)
    expected = scope.guest_sha256, scope.edit_script_sha256, scope.verify_script_sha256
    _require(
        all(
            0 < len(raw) <= limit and _sha(raw) == pin
            for raw, pin, limit in zip(payloads, expected, _ASSET_LIMITS, strict=True)
        ),
        "amp_pm0_fixed_asset_digest",
    )
    return payloads[0], payloads[1], payloads[2]


def _fixed_guest(guest: bytes) -> str:
    """Read exactly the installed guest bytes preceding the canonical request."""
    return shlex.quote(
        "import hashlib,sys\n"
        f"fixed=sys.stdin.read({len(guest)})\n"
        f"if hashlib.sha256(fixed).hexdigest()!='{_sha(guest)}': raise ValueError('AMP asset')\n"
        "eval(compile(fixed,'_amp_pm0_default_phase.py','exec'))"
    )


class _FixedAmplifierPm0Provider:
    def __init__(
        self,
        context: ExecutionContext,
        directory: Path,
        registration: _Registration,
        scope: _Scope,
        raw_scope: bytes,
    ) -> None:
        self._context = context
        self._directory = directory
        self._registration = registration
        self._scope = scope
        self._raw_scope = raw_scope

    def _intent(self, binding: AmplifierPm0DispatchBinding) -> bytes:
        return _canonical(
            {
                "operation_id": binding.operation_id,
                "scope_sha256": binding.scope_sha256,
                "plan_sha256": binding.plan_sha256,
                "dispatch_binding_sha256": canonical_digest(binding),
                "retry": False,
            }
        )

    def _result(
        self,
        binding: AmplifierPm0DispatchBinding,
        *,
        replayed: bool,
        receipt: _Receipt | None = None,
    ) -> PmosDefaultChangeResult:
        return PmosDefaultChangeResult(
            operation_id=binding.operation_id,
            scope_sha256=binding.scope_sha256,
            plan_sha256=binding.plan_sha256,
            candidate_revision=self._scope.plan.candidate_revision,
            outcome="VERIFIED" if receipt else "OUTCOME_UNKNOWN",
            replayed=replayed,
            dispatched_this_call=False if replayed else (True if receipt else None),
            observed_revision_sha256=receipt.saved_view_tree_sha256 if receipt else None,
            observed_testbench_revision_sha256=receipt.reopened_view_tree_sha256
            if receipt
            else None,
            source_preservation_sha256=receipt.source_preservation_sha256 if receipt else None,
            reopen_receipt_sha256=receipt.reopen_receipt_sha256 if receipt else None,
            netlist_receipt_sha256=receipt.netlist_receipt_sha256 if receipt else None,
            netlist_sha256=receipt.netlist_sha256 if receipt else None,
            reason=None if receipt else "durable_amp_writer_intent_without_verified_result",
        )

    def _baseline(self) -> bytes:
        return _read(
            self._directory / "baseline-input.private.scs",
            32768,
            self._scope.plan.baseline.netlist_sha256,
        )

    def _prepare(self, binding: AmplifierPm0DispatchBinding) -> tuple[list[str], bytes, bytes]:
        try:
            guest, edit, verify = _asset_bytes(self._scope)
        except FileNotFoundError:
            raise OperationRejected("amp_pm0_reviewed_assets_missing") from None
        raw_ack = _read(
            self._directory / "c0-exact-ack.private.json", 4096, self._registration.authority_sha256
        )
        _document(raw_ack)
        ack = _Authority.model_validate_json(raw_ack)
        _require(
            ack.operation_id == binding.operation_id
            and ack.scope_sha256 == binding.scope_sha256
            and ack.approved_actions == _ACTIONS
            and ack.valid_until_unix == self._scope.valid_until_unix
            and time.time() < ack.valid_until_unix,
            "amp_pm0_exact_authority",
        )
        qualification = self._scope.qualification
        for name, digest in (
            ("cdf", qualification.cdf_evidence_sha256),
            ("legal-value", qualification.legal_value_evidence_sha256),
            ("update-route", qualification.update_route_evidence_sha256),
        ):
            _read(self._directory / f"{name}-evidence.private", 65_536, digest)
        baseline = self._baseline()
        argv = _ssh(self._context.contracts.environment) + [
            "-c",
            _fixed_guest(guest),
            binding.scope_sha256,
        ]
        payload = guest + _canonical(
            {
                "managed_root": self._context.contracts.environment.paths.managed_root,
                **{
                    name: base64.b64encode(raw).decode("ascii")
                    for name, raw in (
                        ("scope_base64", self._raw_scope),
                        ("authority_base64", raw_ack),
                        ("baseline_base64", baseline),
                        ("edit_base64", edit),
                        ("verify_base64", verify),
                    )
                },
            }
        )
        _require(
            len(subprocess.list2cmdline(argv + ["readback-netlist", "0" * 64])) < 30000
            and len(payload) <= _LIMIT,
            "amp_pm0_fixed_transport_bound",
        )
        return argv, payload, baseline

    def _receipt(
        self,
        binding: AmplifierPm0DispatchBinding,
        output: bytes,
        baseline: bytes,
        edit: _EditResponse,
    ) -> _Receipt:
        _document(output)
        response = _Response.model_validate_json(output)
        receipt = response.receipt
        _require(
            canonical_digest(receipt) == response.receipt_sha256
            and (receipt.operation_id, receipt.plan_sha256, receipt.scope_sha256)
            == (binding.operation_id, binding.plan_sha256, binding.scope_sha256)
            and receipt.owned_before_view_tree_sha256 == binding.owned_before_view_tree_sha256
            and receipt.source_preservation_sha256 == self._scope.source_preservation_sha256
            and receipt.saved_view_tree_sha256 == edit.receipt.saved_view_tree_sha256
            and receipt.presave_signature_sha256 == edit.receipt.presave_signature_sha256
            and receipt.reopened_signature_sha256 == edit.receipt.reopened_signature_sha256
            and receipt.edit_live_counter == edit.receipt.edit_live_counter
            and receipt.saved_view_tree_sha256
            == receipt.reopened_view_tree_sha256
            == receipt.netlisted_view_tree_sha256
            and receipt.saved_view_tree_sha256
            not in (
                binding.owned_before_view_tree_sha256,
                self._scope.plan.baseline.revision_sha256,
            )
            and list(receipt.reopen_frame) == _pm0_frame(baseline=False)[0],
            "amp_pm0_native_receipt_binding",
        )
        verify_amplifier_pm0_save_metadata(
            _decode(response.presave_base64, 65536, receipt.presave_signature_sha256),
            _decode(response.reopened_base64, 65536, receipt.reopened_signature_sha256),
            live_counter=receipt.edit_live_counter,
        )
        netlist = _decode(response.input_base64, 32768, receipt.netlist_sha256)
        project_netlist_change(self._scope.plan, baseline, netlist)
        return receipt

    def _edit_receipt(self, binding: AmplifierPm0DispatchBinding, output: bytes) -> _EditResponse:
        _document(output)
        response = _EditResponse.model_validate_json(output)
        receipt = response.receipt
        _require(
            canonical_digest(receipt) == response.receipt_sha256
            and (receipt.operation_id, receipt.scope_sha256)
            == (binding.operation_id, binding.scope_sha256)
            and receipt.source_preservation_sha256 == self._scope.source_preservation_sha256
            and receipt.saved_view_tree_sha256
            not in (
                binding.owned_before_view_tree_sha256,
                self._scope.plan.baseline.revision_sha256,
            ),
            "amp_pm0_saved_receipt_binding",
        )
        return response

    def lookup(self, binding: AmplifierPm0DispatchBinding) -> PmosDefaultChangeResult | None:
        claimed = self._directory / "amp-writer-intent.private.json"
        if not os.path.lexists(claimed):
            if any(self._directory.glob("amp-edit-*")) or any(
                self._directory.glob("amp-readback-netlist-*")
            ):
                return self._result(binding, replayed=True)
            return None
        try:
            claim = _read(claimed, 4096)
            _document(claim)
        except (OSError, ValueError):
            return self._result(binding, replayed=True)
        _require(claim == self._intent(binding), "amp_pm0_writer_intent_conflict")
        try:
            edit = self._edit_receipt(binding, self._captured(binding, "edit", "none"))
            output = self._captured(binding, "readback-netlist", edit.receipt_sha256)
            receipt = self._receipt(binding, output, self._baseline(), edit)
        except (OSError, ValueError):
            return self._result(binding, replayed=True)
        return self._result(binding, replayed=True, receipt=receipt)

    def claim(self, binding: AmplifierPm0DispatchBinding) -> bool:
        with resource_lock(self._context):
            if self.lookup(binding) is not None:
                return False
            self._prepare(binding)
            _retain(self._directory / "amp-writer-intent.private.json", self._intent(binding))
        return True

    @staticmethod
    def _transport_record(code: int, out: bytes, err: bytes) -> dict[str, object]:
        return dict(
            exit_code=code,
            stdout_sha256=_sha(out),
            stderr_sha256=_sha(err),
            stdout_bytes=len(out),
            stderr_bytes=len(err),
        )

    def dispatch(self, binding: AmplifierPm0DispatchBinding) -> PmosDefaultChangeResult:
        with resource_lock(self._context):
            intent = self._intent(binding)
            _require(
                _read(self._directory / "amp-writer-intent.private.json", 4096) == intent,
                "amp_pm0_writer_intent_conflict",
            )
            argv, payload, baseline = self._prepare(binding)
            edit = self._edit_receipt(
                binding, self._run_phase(binding, argv, payload, "edit", "none")
            )
            output = self._run_phase(
                binding, argv, payload, "readback-netlist", edit.receipt_sha256
            )
            receipt = self._receipt(binding, output, baseline, edit)
        return self._result(binding, replayed=False, receipt=receipt)

    def _captured(self, binding: AmplifierPm0DispatchBinding, phase: str, prior: str) -> bytes:
        prefix = self._directory / f"amp-{phase}"
        intent = _document(_read(prefix.with_name(prefix.name + "-intent.private.json"), 4096))
        out = _read(prefix.with_name(prefix.name + "-stdout.private.json"), _LIMIT)
        err = _read(prefix.with_name(prefix.name + "-stderr.private.txt"), _LIMIT)
        capture = _document(_read(prefix.with_name(prefix.name + "-transport.private.json"), 4096))
        _require(
            intent.get("claim_sha256") == _sha(self._intent(binding))
            and intent.get("prior_receipt_sha256") == prior
            and intent.get("retry") is False
            and not err
            and capture == self._transport_record(0, out, err),
            "amp_pm0_retained_transport",
        )
        return out

    def _run_phase(
        self,
        binding: AmplifierPm0DispatchBinding,
        argv: list[str],
        payload: bytes,
        phase: str,
        prior: str,
    ) -> bytes:
        base = f"amp-{phase}"
        _retain(
            self._directory / f"{base}-intent.private.json",
            _canonical(
                {
                    "claim_sha256": _sha(self._intent(binding)),
                    "request_sha256": _sha(payload),
                    "prior_receipt_sha256": prior,
                    "retry": False,
                }
            ),
        )
        capture = self._directory / f"{base}-transport.private.json"
        try:
            code, out, err = run_fixed(
                argv + [phase, prior],
                payload,
                OpenSshBackend._ssh_environment(),
                timeout=60,
                limit=_LIMIT,
            )
        except (OSError, ValueError) as exc:
            _retain(
                capture,
                _canonical(
                    {
                        "status": "TRANSPORT_FAILED_RETAINED",
                        "error_type": type(exc).__name__,
                    }
                ),
            )
            raise
        _retain(self._directory / f"{base}-stdout.private.json", out)
        _retain(self._directory / f"{base}-stderr.private.txt", err)
        _retain(capture, _canonical(self._transport_record(code, out, err)))
        _require(code == 0 and not err, "amp_pm0_native_dispatch_unverified")
        return out


def registered_amplifier_pm0_default_change(
    context: ExecutionContext, raw: bytes, directory: Path
) -> RegisteredAmplifierPm0DefaultChange:
    """Resolve the AMP branch from the existing digest-pinned operator binding."""
    registration = _Registration.model_validate_json(raw)
    raw_scope = _read(directory / "execution-scope.private.json", 32768, registration.scope_sha256)
    _document(raw_scope)
    scope = _Scope.model_validate_json(raw_scope)
    _require(
        registration.context_id == scope.context_id == context.binding.context_id
        and registration.resource_domain_sha256
        == scope.resource_domain_sha256
        == context.resource_domain_sha256
        and scope.environment_sha256 == context.binding.environment_sha256
        and scope.native_manifest_sha256 == context.binding.runner_sha256,
        "amp_pm0_registered_runtime_binding",
    )
    binding = AmplifierPm0DispatchBinding(
        operation_id=scope.operation_id,
        scope_sha256=registration.scope_sha256,
        plan_sha256=scope.plan_sha256,
        owned_library=scope.owned_library,
        owned_cell=scope.owned_cell,
        owned_view=scope.owned_view,
        owned_before_view_tree_sha256=scope.owned_before_view_tree_sha256,
    )
    return RegisteredAmplifierPm0DefaultChange(
        binding,
        scope.plan,
        scope.qualification,
        _FixedAmplifierPm0Provider(context, directory, registration, scope, raw_scope),
        expected_binding_sha256=canonical_digest(binding),
    )
