"""Registered, finite Source9 PMOS default reversion."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import time
from contextlib import suppress
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.candidate_execution import (
    PmosDefaultChangeRequest,
    PmosDefaultChangeResult,
    PmosDefaultChangeService,
)
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.parameter_changes import (
    ChangePlan,
    ChangeValue,
    MosWidthQualification,
    plan_mos_width_change,
    project_netlist_change,
)
from cadence_mcp_bridge.runtime_context import (
    ExecutionContext,
    RuntimeRejected,
    read_pmos_default_change_binding,
    resource_lock,
)
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel

_PHASES = ("revert", "netlist")
_OVERRIDES = ("w", "fw", "as", "ad", "ps", "pd")
_BASELINE_LIBRARY = "64f06d2c1764f47681211920dc550409f8f09c64becbb74b6848a33d21998a52"
_BASELINE_NETLIST = "5d4134980c80d6cff72e6c1adb0d5957e7871c7b52fa89d5482dfedf113c7f0a"
_BASELINE_TB = "6b70f3bdb99c3030bbb7d31273a552fdea702e4f0b221ace7db4beedb0032193"
_BASELINE_REVISION = "c657fc4527f1a92faa7a918f35e9cab331eb0b4980fca92e5eaf8d5b1f40ee19"
_BASELINE_CONDITIONS = "52fe1fca41a24f7c2cd3a576df34c9784632d33c44235a085184a218134350d8"
_BASELINE_VIEWS = {
    "dut": "10e0afa1a0e39c42e92786299b39114c981b8988077d1ee9201ad4664dc4b8ed",
    "symbol": "247a21db3d90c5a67e7ef7e9c63f78cde4a943a38abda5d03d27b08fd023adfb",
    "tb": _BASELINE_TB,
}
_A02 = "fe36c224-f140-4dbf-a10f-13f12c389863"
_A02_NETLIST = "35d50bb1-94df-4b9c-aa1f-5c8fa2300dd6"
# Accepted Source9 qualification evidence. The route pin identifies the
# retained receipt envelope, distinct from the guest receipt's canonical hash.
_SOURCE9_CDF_FRAME = "0f2463784aa3a8ee958e77ca383fdd611c56636af6da8e562f6603acb28cc987"
_SOURCE9_REOPEN_ENVELOPE = "8adceb5468cfb12f2a81cf7bed49e6cf7b4bf64059ed5df6c11a94c32850dbe9"
_OUTPUT_LIMIT = 65536
_TRANSPORT_LIMIT = 131072
_JOB_LIMIT = 33554432

# Retained Source9 attempt with a successful guest receipt and one known Python 2
# warning from comparing a Unicode marker to OCEAN byte lines.
_RECONCILABLE_SCOPE = "e2ec61a8a1709e07e86a3baa3a3f890971c67ca427ec2ba99556d4cb8626c5d1"
_RECONCILABLE_PHASE = "d5305ff42c5b8d688a59b2979781020885bd6d56dd9ce8826edcbb7d07d6d6f9"
_RECONCILABLE_STDERR = "90497817df2382ce4bb453b3615e0128adbbe3ef559a6952b8c31d374e6025d2"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require(condition: object, reason: str) -> None:
    if not condition:
        raise OperationRejected(reason)


class _Counter(VariableModel):
    campaign_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    count: Annotated[int, Field(ge=0, le=500)]
    result_reserved_bytes: Annotated[int, Field(ge=0, le=17179869184)]


class _Registration(VariableModel):
    schema_version: Literal[1]
    context_id: LogicalId
    resource_domain_sha256: Digest
    scope_sha256: Digest
    evidence_directory: Path


class _Scope(VariableModel):
    schema_version: Literal[1]
    operation_id: OperationId
    diagnostic_netlist_id: OperationId
    context_id: LogicalId
    resource_domain_sha256: Digest
    environment_sha256: Digest
    native_manifest_sha256: Digest
    layout_manifest_sha256: Digest
    worker_sha256: Digest
    phase_sha256: Digest
    valid_until_unix: Annotated[int, Field(gt=0)]
    skill_sha256: Digest
    service_sha256: Digest
    qualification: MosWidthQualification
    plan: ChangePlan
    plan_sha256: Digest
    phases: tuple[Literal["revert"], Literal["netlist"]]
    only_override_names: tuple[
        Literal["w"], Literal["fw"], Literal["as"], Literal["ad"], Literal["ps"], Literal["pd"]
    ]
    old_jobs: Annotated[int, Field(ge=1, le=4096)]
    old_jobs_sha256: Digest
    counter: _Counter
    counter_sha256: Digest
    protected_sha256: Digest
    candidate_library: Annotated[str, Field(pattern=r"^CmosLongPDefault[A-Za-z0-9]{3,32}$")]

    @model_validator(mode="after")
    def finite_route(self) -> Self:
        plan = self.plan
        baseline = plan.baseline
        expected_geometry = {
            "fw": ("350n", "120n"),
            "as": ("98f", "69.6f"),
            "ad": ("98f", "69.6f"),
            "ps": ("1.26u", "1.16u"),
            "pd": ("1.26u", "1.16u"),
        }
        geometry = {
            c.before.property_name: (c.before.value, c.after.value) for c in plan.allowed_derived
        }
        if (
            (
                baseline.revision.workspace_id,
                baseline.revision.design_id,
                baseline.revision.revision_id,
            )
            != ("layout-mvp", "cmos-long-inverter", "long-r1")
            or baseline.revision.source_baseline_sha256 != _BASELINE_REVISION
            or baseline.revision_sha256 != _BASELINE_LIBRARY
            or baseline.testbench_revision_sha256 != _BASELINE_TB
            or baseline.fixed_conditions_sha256 != _BASELINE_CONDITIONS
            or baseline.netlist_sha256 != _BASELINE_NETLIST
            or self.qualification.target.instance.instance_path != "DUT/MP"
            or self.qualification.cdf_evidence_sha256 != _SOURCE9_CDF_FRAME
            or self.qualification.legal_value_evidence_sha256 != _SOURCE9_CDF_FRAME
            or self.qualification.update_route_evidence_sha256 != _SOURCE9_REOPEN_ENVELOPE
            or plan.old.normalized != ChangeValue(value="350", unit="nm").normalized
            or plan.expected.normalized != ChangeValue(value="120", unit="nm").normalized
            or geometry != expected_geometry
            or self.operation_id == self.diagnostic_netlist_id
            or {self.operation_id, self.diagnostic_netlist_id} & {_A02, _A02_NETLIST}
            or self.candidate_library in ("CmosLongPDefaultA1C1", "CmosLongPDefaultA1")
            or plan.candidate_revision.revision_id == "a02-continuation-02"
            or plan.plan_sha256 != self.plan_sha256
            or plan_mos_width_change(
                self.qualification, plan.candidate_id, plan.candidate_revision, plan.requested
            )
            != plan
        ):
            raise ValueError("exact Source9 PMOS default change route required")
        return self


class _Authority(VariableModel):
    owner: Literal["C0"]
    scope_sha256: Digest
    approved_actions: tuple[Literal["revert"], Literal["netlist"]]
    valid_until_unix: Annotated[int, Field(gt=0)]


class _Views(VariableModel):
    dut: Digest
    symbol: Digest
    tb: Digest


class _PhaseReceipt(VariableModel):
    status: Literal["VERIFIED"]
    operation_id: OperationId
    scope_sha256: Digest
    phase: Literal["revert", "netlist"]
    old_jobs: int
    current_jobs: int
    ledger: _Counter
    source_preservation_sha256: Digest
    owned_tree_sha256: Digest
    view_tree_sha256: _Views
    job_logical_bytes: Annotated[int, Field(ge=0, le=_JOB_LIMIT)]
    job_allocated_bytes: Annotated[int, Field(ge=0, le=_JOB_LIMIT)]
    callback_executions: Literal[0]
    spectre_calls: Literal[0]
    simulations: Literal[0]
    reservations: Literal[0]
    receipt_sha256: Digest
    frame_sha256: Digest | None = None
    frame_base64: str | None = None
    netlist_sha256: Digest | None = None
    effective_input_base64: str | None = None
    diagnostic_netlist_id: OperationId | None = None


def _read(path: Path, limit: int, expected: str | None = None) -> bytes:
    path = _local_path(path)
    info = path.stat()
    _require(
        stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit,
        "pmos_default_change_unsafe_artifact",
    )
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        _require(
            (opened.st_dev, opened.st_ino, opened.st_nlink) == (info.st_dev, info.st_ino, 1),
            "pmos_default_change_artifact_changed",
        )
        data = stream.read(limit + 1)
    _require(
        len(data) <= limit and (expected is None or _sha(data) == expected),
        "pmos_default_change_artifact_digest",
    )
    return data


def _document(raw: bytes) -> dict[str, object]:
    _closed_document(raw, max_bytes=_OUTPUT_LIMIT)
    value = json.loads(raw)
    if not isinstance(value, dict) or _canonical(value) != raw:
        raise OperationRejected("pmos_default_change_record_shape")
    return value


def _retain(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _require(_read(path, len(raw)) == raw, "pmos_default_change_record_readback")
    if os.name != "nt":
        fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _artifact(token: str | None, expected: str | None, limit: int) -> bytes:
    _require(token is not None and expected is not None, "pmos_default_change_missing_artifact")
    assert token is not None
    raw = base64.b64decode(token, validate=True)
    _require(0 < len(raw) <= limit and _sha(raw) == expected, "pmos_default_change_evidence_digest")
    return raw


class _RegisteredDefaultChange:
    def __init__(
        self, context: ExecutionContext, directory: Path, scope: _Scope, raw: bytes
    ) -> None:
        self.context = context
        self.directory = directory
        self.scope = scope
        self.scope_raw = raw
        self.digest = _sha(raw)

    def _record(self, name: str, data: dict[str, object]) -> None:
        _retain(self.directory / f"{name}.private.json", _canonical(data))

    def _intent(self) -> dict[str, object]:
        return dict(
            operation_id=self.scope.operation_id,
            scope_sha256=self.digest,
            plan_sha256=self.scope.plan_sha256,
            phases=list(_PHASES),
            retry=False,
        )

    def _check_qualification_evidence(self) -> None:
        scope = self.scope
        for name, expected in (
            ("cdf-evidence", scope.qualification.cdf_evidence_sha256),
            ("legal-value-evidence", scope.qualification.legal_value_evidence_sha256),
            ("update-route-evidence", scope.qualification.update_route_evidence_sha256),
        ):
            _read(self.directory / f"{name}.private", _OUTPUT_LIMIT, expected)

    def _baseline(self) -> bytes:
        return _read(self.directory / "baseline-input.private.scs", 32768, _BASELINE_NETLIST)

    def _receipt(self, phase: str, out: bytes) -> _PhaseReceipt:
        value = _document(out)
        result = _PhaseReceipt.model_validate_json(out)
        scope = self.scope
        expected_fields = set(_PhaseReceipt.model_fields) - {
            "frame_sha256",
            "frame_base64",
            "netlist_sha256",
            "effective_input_base64",
            "diagnostic_netlist_id",
        }
        expected_fields |= (
            {"frame_sha256", "frame_base64"}
            if phase == "revert"
            else {"netlist_sha256", "effective_input_base64", "diagnostic_netlist_id"}
        )
        material = {
            k: v for k, v in value.items() if k != "receipt_sha256" and not k.endswith("_base64")
        }
        _require(
            set(value) == expected_fields
            and result.phase == phase
            and result.operation_id == scope.operation_id
            and result.scope_sha256 == self.digest
            and result.ledger == scope.counter
            and result.old_jobs == scope.old_jobs
            and result.current_jobs == scope.old_jobs + 1
            and result.owned_tree_sha256 != _BASELINE_LIBRARY
            and result.view_tree_sha256.tb != _BASELINE_TB
            and result.receipt_sha256 == _sha(_canonical(material)),
            "pmos_default_change_receipt_binding",
        )
        return result

    def _request(
        self, phase: str, baseline: bytes, previous: dict[str, str], authority: bytes, skill: bytes
    ) -> bytes:
        return _canonical(
            dict(
                phase=phase,
                previous=previous,
                scope_base64=base64.b64encode(self.scope_raw).decode("ascii"),
                authority_base64=base64.b64encode(authority).decode("ascii"),
                baseline_base64=base64.b64encode(baseline).decode("ascii"),
                skill_base64=base64.b64encode(skill).decode("ascii"),
            )
        )

    def _load_phase(
        self,
        phase: str,
        previous: dict[str, str],
        baseline: bytes,
        *,
        retained_lookup: bool = False,
    ) -> _PhaseReceipt:
        directory = self.directory
        intent = _document(_read(directory / f"{phase}-intent.private.json", 4096))
        request_sha = intent.get("request_sha256")
        _require(
            isinstance(request_sha, str) and bool(re.fullmatch(r"[a-f0-9]{64}", request_sha)),
            "pmos_default_change_retained_request",
        )
        _require(
            intent
            == dict(
                scope_sha256=self.digest,
                phase=phase,
                previous=previous,
                request_sha256=request_sha,
                retry=False,
            ),
            "pmos_default_change_retained_phase",
        )
        capture = _document(_read(directory / f"{phase}-execution.private.json", 4096))
        out = _read(directory / f"{phase}-stdout.private.json", _OUTPUT_LIMIT)
        err = _read(directory / f"{phase}-stderr.private.txt", _OUTPUT_LIMIT)
        reviewed_warning = (
            retained_lookup
            and phase == "netlist"
            and self.digest == _RECONCILABLE_SCOPE
            and self.scope.phase_sha256 == _RECONCILABLE_PHASE
            and len(err) == 130
            and _sha(err) == _RECONCILABLE_STDERR
        )
        _require(
            (not err or reviewed_warning)
            and capture
            == dict(
                exit_code=0,
                stdout_sha256=_sha(out),
                stdout_bytes=len(out),
                stderr_sha256=_sha(err),
                stderr_bytes=len(err),
            ),
            "pmos_default_change_retained_transport",
        )
        receipt = self._receipt(phase, out)
        if phase == "revert":
            frame = _artifact(receipt.frame_base64, receipt.frame_sha256, 8192)
            self._check_frame(frame)
        else:
            netlist = _artifact(receipt.effective_input_base64, receipt.netlist_sha256, 32768)
            _require(
                receipt.diagnostic_netlist_id == self.scope.diagnostic_netlist_id,
                "pmos_default_change_diagnostic_identity",
            )
            self._check_netlist(baseline, netlist)
        return receipt

    def _check_frame(self, frame: bytes) -> None:
        from cadence_mcp_bridge._pmos_default_phase import read_frame

        read_frame(frame, self.scope.candidate_library)  # type: ignore[no-untyped-call]

    def _check_netlist(self, baseline: bytes, child: bytes) -> None:
        headers = child.decode("ascii").splitlines()
        for line in (
            "// Design library name: MCP_GREL_Work",
            "// Design cell name: Grel_" + self.scope.diagnostic_netlist_id.replace("-", "_"),
            "// Library name: " + self.scope.candidate_library,
        ):
            _require(headers.count(line) == 1, "pmos_default_change_netlist_child_binding")
        project_netlist_change(self.scope.plan, baseline, child)

    def _result(
        self,
        request: PmosDefaultChangeRequest,
        *,
        replayed: bool,
    ) -> PmosDefaultChangeResult:
        reopen = netlist = None
        try:
            reopen = self._load_phase("revert", {}, b"")
            observed = self._load_phase(
                "netlist",
                {"revert": reopen.receipt_sha256},
                self._baseline(),
                retained_lookup=replayed,
            )
            _require(
                (
                    observed.owned_tree_sha256,
                    observed.view_tree_sha256,
                    observed.source_preservation_sha256,
                )
                == (
                    reopen.owned_tree_sha256,
                    reopen.view_tree_sha256,
                    reopen.source_preservation_sha256,
                ),
                "pmos_default_change_same_revision_required",
            )
            netlist = observed
        except (OSError, ValueError, AssertionError):
            pass
        result = PmosDefaultChangeResult(
            operation_id=self.scope.operation_id,
            scope_sha256=self.digest,
            plan_sha256=self.scope.plan_sha256,
            candidate_revision=self.scope.plan.candidate_revision,
            outcome="VERIFIED" if netlist else "OUTCOME_UNKNOWN",
            replayed=replayed,
            dispatched_this_call=False if replayed else (True if netlist else None),
            observed_revision_sha256=reopen.owned_tree_sha256 if reopen else None,
            observed_testbench_revision_sha256=reopen.view_tree_sha256.tb if reopen else None,
            source_preservation_sha256=reopen.source_preservation_sha256 if reopen else None,
            reopen_receipt_sha256=reopen.receipt_sha256 if reopen else None,
            netlist_receipt_sha256=netlist.receipt_sha256 if netlist else None,
            netlist_sha256=netlist.netlist_sha256 if netlist else None,
            reason=None if netlist else "complete_same_revision_evidence_unavailable",
        )
        result.check_registered_scope(
            request, registered_plan=self.scope.plan, registered_scope_sha256=self.digest
        )
        return result

    def _prepared_transport(self) -> tuple[list[str], bytes, bytes]:
        scope = self.scope
        _require(
            self.context.binding.runner_sha256 == scope.native_manifest_sha256,
            "pmos_default_change_native_binding",
        )
        package = files("cadence_mcp_bridge")
        _require(
            _sha(Path(__file__).read_bytes()) == scope.service_sha256,
            "pmos_default_change_service_digest",
        )
        phase = package.joinpath("_pmos_default_phase.py").read_bytes()
        skill = package.joinpath("_pmos_default_reopen.ocn").read_bytes()
        _require(
            (_sha(phase), _sha(skill)) == (scope.phase_sha256, scope.skill_sha256),
            "pmos_default_change_fixed_assets",
        )
        code = phase + b"\nmain()\n"
        argv = _ssh(self.context.contracts.environment) + [
            "-c",
            shlex.quote(code.decode("ascii")),
            self.digest,
        ]
        _require(len(subprocess.list2cmdline(argv)) < 30000, "pmos_default_change_command_bound")
        authority = _read(self.directory / "c0-exact-ack.private.json", 4096)
        _document(authority)
        ack = _Authority.model_validate_json(authority)
        _require(
            ack.scope_sha256 == self.digest
            and ack.valid_until_unix == scope.valid_until_unix
            and time.time() < scope.valid_until_unix,
            "pmos_default_change_authority",
        )
        return argv, authority, skill

    def _dispatch(
        self, phase: str, argv: list[str], payload: bytes, previous: dict[str, str]
    ) -> None:
        _require(len(payload) <= _TRANSPORT_LIMIT, "pmos_default_change_request_bound")
        self._record(
            f"{phase}-intent",
            dict(
                scope_sha256=self.digest,
                phase=phase,
                previous=previous,
                request_sha256=_sha(payload),
                retry=False,
            ),
        )
        try:
            code, out, err = run_fixed(
                argv, payload, OpenSshBackend._ssh_environment(), timeout=60, limit=_TRANSPORT_LIMIT
            )
        except (OSError, ValueError) as error:
            self._record(
                f"{phase}-execution",
                dict(status="TRANSPORT_FAILED_RETAINED", error_type=type(error).__name__),
            )
            raise
        capture = dict(
            exit_code=code,
            stdout_sha256=_sha(out),
            stdout_bytes=len(out),
            stderr_sha256=_sha(err),
            stderr_bytes=len(err),
        )
        if max(len(out), len(err)) > _OUTPUT_LIMIT:
            self._record(f"{phase}-execution", {**capture, "status": "RESPONSE_LIMIT_EXCEEDED"})
            raise OperationRejected("pmos_default_change_response_bound")
        _retain(self.directory / f"{phase}-stdout.private.json", out)
        _retain(self.directory / f"{phase}-stderr.private.txt", err)
        self._record(f"{phase}-execution", capture)

    def apply(self, request: PmosDefaultChangeRequest) -> PmosDefaultChangeResult:
        request = PmosDefaultChangeRequest.model_validate_json(request.model_dump_json())
        _require(
            (request.operation_id, request.expected_plan_sha256, request.expected_scope_sha256)
            == (self.scope.operation_id, self.scope.plan_sha256, self.digest),
            "pmos_default_change_identity_mismatch",
        )
        with resource_lock(self.context):
            intent = self.directory / "execution-intent.private.json"
            if os.path.lexists(intent):
                try:
                    _require(
                        _document(_read(intent, 4096)) == self._intent(),
                        "pmos_default_change_retained_intent",
                    )
                except (OSError, ValueError):
                    return self._unknown(
                        request, replayed=True, reason="retained_intent_unverified"
                    )
                return self._result(request, replayed=True)
            if any(
                os.path.lexists(self.directory / f"{phase}-{leaf}.private.{suffix}")
                for phase in _PHASES
                for leaf, suffix in (
                    ("intent", "json"),
                    ("execution", "json"),
                    ("stdout", "json"),
                    ("stderr", "txt"),
                )
            ) or os.path.lexists(self.directory / "verified.private.json"):
                return self._unknown(request, replayed=True, reason="orphaned_phase_evidence")
            try:
                self._check_qualification_evidence()
                baseline = self._baseline()
                argv, authority, skill = self._prepared_transport()
            except OperationRejected:
                raise
            except (OSError, ValueError):
                raise OperationRejected("pmos_default_change_prerequisite_invalid") from None
            try:
                self._record("execution-intent", self._intent())
            except FileExistsError:
                raise OperationRejected("pmos_default_change_claim_lost") from None
            previous: dict[str, str] = {}
            try:
                for phase in _PHASES:
                    self._dispatch(
                        phase,
                        argv,
                        self._request(phase, baseline, previous, authority, skill),
                        previous,
                    )
                    receipt = self._load_phase(phase, previous, baseline)
                    previous[phase] = receipt.receipt_sha256
            except (OSError, ValueError, AssertionError):
                return self._result(request, replayed=False)
            result = self._result(request, replayed=False)
            if result.outcome == "VERIFIED":
                # Complete phase captures already establish the outcome.
                with suppress(OSError):
                    self._record("verified", result.model_dump(mode="json"))
            return result

    def _unknown(
        self,
        request: PmosDefaultChangeRequest,
        *,
        replayed: bool,
        reason: str,
    ) -> PmosDefaultChangeResult:
        result = PmosDefaultChangeResult(
            operation_id=self.scope.operation_id,
            scope_sha256=self.digest,
            plan_sha256=self.scope.plan_sha256,
            candidate_revision=self.scope.plan.candidate_revision,
            outcome="OUTCOME_UNKNOWN",
            replayed=replayed,
            dispatched_this_call=False,
            reason=reason,
        )
        result.check_registered_scope(
            request, registered_plan=self.scope.plan, registered_scope_sha256=self.digest
        )
        return result


def registered_pmos_default_change(context: ExecutionContext) -> PmosDefaultChangeService:
    """Resolve one fixed operator registration in the selected runtime context."""
    path = context.binding.pmos_default_change_binding
    expected = context.binding.pmos_default_change_sha256
    if path is None or expected is None:
        raise OperationRejected("pmos_default_change_not_registered")
    try:
        raw = read_pmos_default_change_binding(path, expected)
        registration = _Registration.model_validate_json(raw)
        directory = _local_path(registration.evidence_directory)
        _require(
            registration.evidence_directory.is_absolute() and directory.is_dir(),
            "pmos_default_change_evidence_directory",
        )
        # Keep fixed evidence leaves and service output away from existing journals.
        for journal in (
            context.binding.analysis_journal,
            context.binding.sweep_journal,
            context.lock_path,
        ):
            resolved = _local_path(journal)
            _require(
                not resolved.is_relative_to(directory), "pmos_default_change_journal_collision"
            )
        scope_raw = _read(
            directory / "execution-scope.private.json", 16384, registration.scope_sha256
        )
        _document(scope_raw)
        scope = _Scope.model_validate_json(scope_raw)
        _require(
            registration.context_id == scope.context_id == context.binding.context_id
            and registration.resource_domain_sha256
            == scope.resource_domain_sha256
            == context.resource_domain_sha256
            and scope.environment_sha256 == context.binding.environment_sha256
            and scope.native_manifest_sha256 == context.binding.runner_sha256,
            "pmos_default_change_runtime_binding",
        )
    except (OSError, ValueError, RecursionError, RuntimeRejected):
        raise OperationRejected("pmos_default_change_registration_invalid") from None
    return _RegisteredDefaultChange(context, directory, scope, scope_raw)
