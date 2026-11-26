"""Resolve one finite operator enrollment and reuse the registered MOS phase journal."""

from __future__ import annotations

import os
import shlex
import time
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from cadence_mcp_bridge import _registered_mos_edit_phase as guest_contract
from cadence_mcp_bridge import m2_cdf
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeRequest
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.mos_wl_skill import render_mos_wl_skill
from cadence_mcp_bridge.mos_wlm_skill import render_mos_wlm_skill
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.pmos_default_service import _document, _read, _require, _sha
from cadence_mcp_bridge.registered_mos_edit import (
    MosEditSubject,
    NativeMosEditSave,
    RegisteredMosEditBinding,
)
from cadence_mcp_bridge.registered_mos_sizing import (
    MosSizingBounds,
    MosSizingCount,
    MosSizingDimensions,
    MosSizingPlan,
    MosSizingSupport,
    MosSizingTarget,
    MosSizingValues,
    RegisteredMosSizingResult,
    RegisteredMosSizingRoute,
    RegisteredMosSizingService,
    RetainedMosSizingEvidence,
    _observed_dimensions,
    plan_registered_mos_sizing,
    verify_mos_sizing_save,
)
from cadence_mcp_bridge.registered_mos_transport import (
    _ASSET,
    _CLAIM,
    _GUEST_SOURCE_LIMIT,
    Phase,
    _Authority,
    _encode,
    _RegisteredMosPhaseProvider,
)
from cadence_mcp_bridge.registered_ota_mos_sizing import (
    RegisteredOtaMosSizingRoute,
    RegisteredOtaMosSizingService,
)
from cadence_mcp_bridge.research_circuit import MosBlockStageReceipt
from cadence_mcp_bridge.research_generation_ota_recovery import RecoveredOtaGenerationAnalysisSource
from cadence_mcp_bridge.runtime_context import ExecutionContext, read_pmos_default_change_binding
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    LogicalId,
    VariableModel,
    canonical_digest,
)


class MosSizingCandidate(VariableModel):
    operation_id: OperationId
    expected_enrollment_sha256: Digest
    expected_baseline_sha256: Digest
    values: MosSizingValues


class MosSizingApply(VariableModel):
    candidate: MosSizingCandidate
    identity: PmosDefaultChangeRequest


class _Slot(VariableModel):
    operation_id: OperationId
    owned_copy_operation_id: OperationId
    child: RevisionBinding
    owned_library: BindingName
    owned_before_view_tree_sha256: Digest
    owned_before_testbench_tree_sha256: Digest
    source_preservation_sha256: Digest
    native_safety_sha256: Digest
    slot_manifest_sha256: Digest | None = None


_AdmittedMultipliers = Annotated[tuple[MosSizingCount, ...], Field(min_length=1, max_length=2)]
_SizingRouteName = Literal["registered_mos_sizing", "registered_ota_mos_sizing"]


class _SizingEnrollment(VariableModel):
    schema_version: Literal[4, 5]
    route: _SizingRouteName
    owner: Literal["C0"]
    context_id: LogicalId
    resource_domain_sha256: Digest
    environment_sha256: Digest
    native_manifest_sha256: Digest
    evidence_directory: Path
    route_qualification: RegisteredOtaMosSizingRoute | RegisteredMosSizingRoute
    guest_sha256: Digest
    support_sha256: Digest
    collector_sha256: Digest
    renderer_sha256: Digest
    hash_child_sha256: Digest
    width_field: Literal["w", "fw"] | None = None
    admitted_w: MosSizingBounds | None = None
    admitted_l: MosSizingBounds | None = None
    admitted_m: _AdmittedMultipliers | None = None
    valid_until_unix: Annotated[int, Field(gt=0)]
    slots: Annotated[tuple[_Slot, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def distinct_slots(self) -> _SizingEnrollment:
        support = self.route_qualification.support
        if isinstance(self.route_qualification, RegisteredOtaMosSizingRoute):
            if (
                self.schema_version != 5
                or self.route != "registered_ota_mos_sizing"
                or len(self.slots) != 1
            ):
                raise ValueError("OTA sizing requires its separately registered operator lane")
        elif self.schema_version != 4 or self.route != "registered_mos_sizing":
            raise ValueError("MOS sizing enrollment route and schema differ")
        ids = {
            id_ for slot in self.slots for id_ in (slot.operation_id, slot.owned_copy_operation_id)
        }
        if (
            len(ids) != 2 * len(self.slots)
            or len({slot.child.revision_id for slot in self.slots}) != len(self.slots)
            or len({slot.owned_library for slot in self.slots}) != len(self.slots)
            or (self.width_field is None) != (self.route_qualification.support.w is None)
            or self.renderer_sha256 != self.route_qualification.support.adapter_sha256
            or (self.admitted_w is None) != (self.route_qualification.support.w is None)
            or (self.admitted_l is None) != (self.route_qualification.support.l is None)
            or any(
                axis is not None and (axis.minimum is None or axis.maximum is None)
                for axis in (self.admitted_w, self.admitted_l)
            )
        ):
            raise ValueError("MOS sizing enrollment slots or renderer are inconsistent")
        if support.lifecycle == "headless_wlm_v1":
            admitted = self.admitted_m or ()
            if (
                self.width_field not in (None, "w")
                or any(slot.slot_manifest_sha256 is not None for slot in self.slots)
                or (self.admitted_m is None) != (support.m is None)
                or len(set(admitted)) != len(admitted)
                or not set(admitted).issubset(support.m or ())
            ):
                raise ValueError("MOS W/L/m enrollment axes or exact-scope mode differ")
        elif self.admitted_m is not None:
            raise ValueError("MOS multiplier requires the W/L/m lifecycle")
        return self

    @model_serializer(mode="wrap")
    def omit_legacy_multiplier(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        document: dict[str, Any] = handler(self)
        if self.admitted_m is None:
            document.pop("admitted_m", None)
        return document


class _SizingScope(VariableModel):
    schema_version: Literal[1] = 1
    route: _SizingRouteName = "registered_mos_sizing"
    context_id: LogicalId
    resource_domain_sha256: Digest
    environment_sha256: Digest
    native_manifest_sha256: Digest
    subject: MosEditSubject
    route_qualification: RegisteredOtaMosSizingRoute | RegisteredMosSizingRoute
    plan: MosSizingPlan
    candidate_request: MosSizingValues
    guest_sha256: Digest
    native_safety_sha256: Digest
    sizing_sha256: Digest
    valid_until_unix: Annotated[int, Field(gt=0)]
    slot_manifest_sha256: Digest | None = None

    @model_serializer(mode="wrap")
    def omit_exact_mode_slot(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        document: dict[str, Any] = handler(self)
        if self.slot_manifest_sha256 is None:
            del document["slot_manifest_sha256"]
        return document


class MosSizingRegistrationInfo(VariableModel):
    enrollment_sha256: Digest
    baseline_sha256: Digest
    target: MosSizingTarget
    support: MosSizingSupport
    admission_w: MosSizingBounds | None
    admission_l: MosSizingBounds | None
    admission_m: _AdmittedMultipliers | None = None
    current: MosSizingDimensions
    operation_ids: tuple[OperationId, ...]
    valid_until_unix: int
    multiplier: Literal[1, 6] = 1
    fingers: Literal[1] = 1
    execution_authorized: Literal[False] = False

    @model_serializer(mode="wrap")
    def omit_legacy_multiplier(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        document: dict[str, Any] = handler(self)
        if self.admission_m is None:
            document.pop("admission_m", None)
        return document


class MosSizingPreview(VariableModel):
    identity: PmosDefaultChangeRequest
    enrollment_sha256: Digest
    plan: MosSizingPlan
    execution_authorized: Literal[False] = False


class MosSizingLookup(VariableModel):
    identity: PmosDefaultChangeRequest
    outcome: Literal["NOT_FOUND", "OUTCOME_UNKNOWN", "VERIFIED"]
    result: RegisteredMosSizingResult | None = None


def _asset(raw: bytes, digest: str, *, max_bytes: int = 65_536) -> bytes:
    _require(
        0 < len(raw) <= max_bytes and raw.isascii() and _sha(raw) == digest,
        "registered_mos_sizing_asset",
    )
    return raw


def _hash_child_asset(reg: _SizingEnrollment) -> tuple[str, str | None]:
    if reg.route_qualification.support.lifecycle == "headless_wlm_v1":
        return "_mos_wlm_callback.py", getattr(guest_contract, "WLM_HASH_CHILD_SHA256", None)
    instance = reg.route_qualification.target.instance
    if (instance.instance_path, instance.master_cell, instance.property_name) == (
        "DUT/MP", "pmos1v", "w"
    ):
        _require(
            reg.width_field == "w"
            and reg.admitted_w is not None
            and reg.admitted_l is None
            and all(slot.slot_manifest_sha256 is None for slot in reg.slots),
            "registered_mos_sizing_pmos_width_enrollment",
        )
        return (
            "_mos_pmos_width_callback.py",
            getattr(guest_contract, "SIZING_WIDTH_HASH_CHILD_SHA256", None),
        )
    return "_mos_cdf_call_contract.py", guest_contract.SIZING_HASH_CHILD_SHA256


class _SizingPhaseProvider(_RegisteredMosPhaseProvider):
    def __init__(
        self,
        context: ExecutionContext,
        directory: Path,
        enrollment: _SizingEnrollment,
        enrollment_sha: str,
        scope: _SizingScope,
        sizing_raw: bytes,
        baseline: bytes,
    ) -> None:
        super().__init__(context, directory)
        self._enrollment = enrollment
        self._enrollment_sha = enrollment_sha
        self._scope = scope
        self._sizing = sizing_raw
        self._baseline = baseline

    def _intent(self, binding: RegisteredMosEditBinding) -> bytes:
        return _canonical(
            {
                **_document(super()._intent(binding)),
                "enrollment_sha256": self._enrollment_sha,
                "candidate_request": self._scope.candidate_request.model_dump(mode="json"),
            }
        )

    def _prepare(
        self, binding: RegisteredMosEditBinding, phase: Phase, previous: str | None
    ) -> tuple[list[str], bytes]:
        scope, reg = self._scope, self._enrollment
        _require(time.time() < reg.valid_until_unix, "registered_mos_sizing_authority_expired")
        path = self._context.binding.pmos_default_change_binding
        if path is None:
            raise ValueError("Registered MOS sizing enrollment is missing")
        read_pmos_default_change_binding(path, self._enrollment_sha)
        raw_scope = _canonical(scope.model_dump(mode="json"))
        _require(_sha(raw_scope) == binding.scope_sha256, "registered_mos_sizing_scope")
        authority = _Authority(
            owner=reg.owner,
            operation_id=binding.operation_id,
            scope_sha256=binding.scope_sha256,
            approved_phases=("EDIT_SAVE", "INDEPENDENT_REOPEN_NETLIST"),
            valid_until_unix=reg.valid_until_unix,
        )
        safety = _read(
            self._directory / "native-safety.private.json", 65_536, scope.native_safety_sha256
        )
        _document(safety)
        package = files("cadence_mcp_bridge")
        guest = _asset(
            package.joinpath(_ASSET).read_bytes(), reg.guest_sha256, max_bytes=_GUEST_SOURCE_LIMIT
        )
        support = _asset(
            package.joinpath("_amp_pm0_default_phase.py").read_bytes(), reg.support_sha256
        )
        collector = _asset(m2_cdf.render_reopened_mos_cdf(), reg.collector_sha256)
        packet = {
            "managed_root": self._context.contracts.environment.paths.managed_root,
            "scope_base64": _encode(raw_scope),
            "authority_base64": _encode(_canonical(authority.model_dump(mode="json"))),
            "baseline_base64": _encode(self._baseline),
            "native_safety_base64": _encode(safety),
            "support_base64": _encode(support),
            "cdf_collector_base64": _encode(collector),
            "sizing_base64": _encode(self._sizing),
            "previous_receipt_sha256": previous,
        }
        if scope.slot_manifest_sha256 is not None:
            verifier_pin = getattr(guest_contract, "SIZING_SLOT_VERIFIER_SHA256", None)
            if not isinstance(verifier_pin, str):
                raise ValueError("Registered MOS guest does not support finite slot verification")
            verifier = package.joinpath("_mos_sizing_slot.py").read_bytes()
            _require(len(verifier) <= 16_384, "registered_mos_sizing_slot_verifier_size")
            packet["slot_verifier_base64"] = _encode(_asset(verifier, verifier_pin))
        bootstrap = shlex.quote(
            "import hashlib,sys\n"
            f"fixed=sys.stdin.read({len(guest)})\n"
            f"if hashlib.sha256(fixed.encode('ascii')).hexdigest()!='{reg.guest_sha256}':"
            " raise ValueError('MOS asset')\n"
            f"eval(compile(fixed,'{_ASSET}','exec'))"
        )
        return (
            _ssh(self._context.contracts.environment)
            + ["-c", bootstrap, binding.scope_sha256, phase],
            guest + _canonical(packet),
        )

    def _saved(self, binding: RegisteredMosEditBinding, raw: bytes) -> NativeMosEditSave:
        _document(raw)
        save = NativeMosEditSave.model_validate_json(raw)
        verify_mos_sizing_save(self._scope.plan, self._scope.route_qualification, binding, save)
        return save


class RegisteredMosSizing:
    """User-facing selections cannot choose evidence, executable assets or copy paths."""

    def __init__(self, context: ExecutionContext, raw: bytes, digest: str) -> None:
        _document(raw)
        reg = _SizingEnrollment.model_validate_json(raw)
        _require(
            _sha(raw) == digest
            and (
                reg.context_id,
                reg.resource_domain_sha256,
                reg.environment_sha256,
                reg.native_manifest_sha256,
            )
            == (
                context.binding.context_id,
                context.resource_domain_sha256,
                context.binding.environment_sha256,
                context.binding.runner_sha256,
            ),
            "registered_mos_sizing_runtime_binding",
        )
        directory = _local_path(reg.evidence_directory)
        _require(
            reg.evidence_directory.is_absolute()
            and directory.is_dir()
            and not any(
                _local_path(path).is_relative_to(directory)
                for path in (
                    context.binding.analysis_journal,
                    context.binding.sweep_journal,
                    context.lock_path,
                )
            ),
            "registered_mos_sizing_evidence_directory",
        )
        package = files("cadence_mcp_bridge")
        if reg.route_qualification.support.lifecycle == "headless_wlm_v1":
            renderer_name = "mos_wlm_skill.py"
            renderer_pin = getattr(guest_contract, "WLM_RENDERER_SHA256", None)
        else:
            renderer_name = "mos_wl_skill.py"
            renderer_pin = guest_contract.SIZING_RENDERER_SHA256
        child_name, child_pin = _hash_child_asset(reg)
        _asset(package.joinpath(renderer_name).read_bytes(), reg.renderer_sha256)
        _asset(
            package.joinpath(_ASSET).read_bytes(), reg.guest_sha256, max_bytes=_GUEST_SOURCE_LIMIT
        )
        route_pin = (
            "OTA_SIZING_ROUTE" if reg.route == "registered_ota_mos_sizing" else "SIZING_ROUTE"
        )
        _require(
            getattr(guest_contract, route_pin, None) == reg.route
            and reg.renderer_sha256 == renderer_pin
            and reg.hash_child_sha256 == child_pin
            and reg.support_sha256 == guest_contract.SUPPORT_SHA256
            and reg.collector_sha256 == guest_contract.CDF_SHA256,
            "registered_mos_sizing_guest_contract",
        )
        self._baseline = _read(
            directory / "baseline-input.private.scs",
            32_768,
            reg.route_qualification.baseline.netlist_sha256,
        )
        route = reg.route_qualification
        self._baseline_reopen_stdout = (
            _read(
                directory / "baseline-reopen-stdout.private.txt", 65_536,
                route.ota.reopen_stdout_sha256,
            )
            if isinstance(route, RegisteredOtaMosSizingRoute)
            else None
        )
        self._baseline_recovery: RecoveredOtaGenerationAnalysisSource | None = None
        self._baseline_reopen_receipt: MosBlockStageReceipt | None = None
        if isinstance(route, RegisteredOtaMosSizingRoute) and route.ota.recovered_source_sha256:
            self._baseline_recovery = RecoveredOtaGenerationAnalysisSource.model_validate_json(
                _read(directory / "baseline-recovered-source.private.json", 16_384)
            )
            self._baseline_reopen_receipt = MosBlockStageReceipt.model_validate_json(
                _read(directory / "baseline-reopen-receipt.private.json", 8_192)
            )
            _require(
                canonical_digest(self._baseline_recovery) == route.ota.recovered_source_sha256
                and canonical_digest(self._baseline_reopen_receipt)
                == route.ota.reopen_receipt_sha256,
                "registered_ota_mos_sizing_recovered_baseline",
            )
        _read(
            directory / "cdf-constraints.private.txt",
            65_536,
            reg.route_qualification.support.cdf_constraints_sha256,
        )
        self._hash_child = _asset(
            package.joinpath(child_name).read_bytes(),
            reg.hash_child_sha256,
        )
        self._phase_asset = None
        if reg.route_qualification.support.lifecycle == "headless_wlm_v1":
            phase_pin = getattr(guest_contract, "WLM_PHASE_SHA256", None)
            if not isinstance(phase_pin, str):
                raise ValueError("Registered MOS guest does not support the W/L/m phase asset")
            self._phase_asset = _asset(
                package.joinpath("_mos_wlm_phase.py").read_bytes(), phase_pin, max_bytes=12_288
            )
        self._context, self._directory, self._reg, self.enrollment_sha256 = (
            context,
            directory,
            reg,
            digest,
        )

    def inspect(self) -> MosSizingRegistrationInfo:
        route = self._reg.route_qualification
        current = _observed_dimensions(route.before, include_m=route.support.lifecycle is not None)
        return MosSizingRegistrationInfo(
            enrollment_sha256=self.enrollment_sha256,
            baseline_sha256=route.baseline.revision_sha256,
            target=route.target,
            support=route.support,
            admission_w=self._reg.admitted_w,
            admission_l=self._reg.admitted_l,
            admission_m=self._reg.admitted_m,
            current=current,
            multiplier=current.m or 1,
            operation_ids=tuple(slot.operation_id for slot in self._reg.slots),
            valid_until_unix=self._reg.valid_until_unix,
        )

    def _slot(self, operation_id: str) -> tuple[_Slot, Path]:
        slot = next((slot for slot in self._reg.slots if slot.operation_id == operation_id), None)
        if slot is None:
            raise ValueError("MOS sizing operation is not registered")
        directory = _local_path(self._directory / slot.operation_id)
        _require(directory.is_dir(), "registered_mos_sizing_slot_directory")
        return slot, directory

    def _service(self, candidate: MosSizingCandidate) -> RegisteredMosSizingService:
        candidate = MosSizingCandidate.model_validate_json(candidate.model_dump_json())
        reg, route = self._reg, self._reg.route_qualification
        _require(
            candidate.expected_enrollment_sha256 == self.enrollment_sha256
            and candidate.expected_baseline_sha256 == route.baseline.revision_sha256,
            "registered_mos_sizing_candidate_binding",
        )
        slot, directory = self._slot(candidate.operation_id)
        plan = plan_registered_mos_sizing(route, slot.child, candidate.values)
        for value, admission in (
            (plan.requested.w, reg.admitted_w),
            (plan.requested.l, reg.admitted_l),
        ):
            if value is not None:
                if admission is None:
                    raise ValueError("MOS sizing axis is not admitted by the enrollment")
                admission.check(value)
        if plan.requested.m is not None:
            _require(
                plan.requested.m in (reg.admitted_m or ()),
                "registered_mos_sizing_multiplier_admission",
            )
        length = plan.expected.l.value if "l" in plan.changed else None
        width = plan.expected.w.value if "w" in plan.changed else None
        master = route.target.instance.master_cell
        if master not in ("nmos1v", "pmos1v"):
            raise ValueError("unsupported sizing master")
        master_cell = cast(Literal["nmos1v", "pmos1v"], master)
        if route.support.lifecycle == "headless_wlm_v1":
            adapter = render_mos_wlm_skill(
                master_cell,
                length_nm=length,
                width_nm=width,
                multiplier=plan.expected.m if "m" in plan.changed else None,
            )
        else:
            adapter = render_mos_wl_skill(
                master_cell,
                length_nm=length,
                width_nm=width,
                width_field=reg.width_field if width is not None else None,
            )
        assets = {
            "adapter": adapter.decode("ascii"),
            "adapter_sha256": _sha(adapter),
            "hash_child": self._hash_child.decode("ascii"),
            "hash_child_sha256": reg.hash_child_sha256,
        }
        if self._phase_asset is not None:
            assets.update(
                phase=self._phase_asset.decode("ascii"), phase_sha256=_sha(self._phase_asset)
            )
        sizing = _canonical(assets)
        _require(len(sizing) <= 32_768, "registered_mos_sizing_asset_bundle_size")
        subject = MosEditSubject(
            operation_id=slot.operation_id,
            owned_copy_operation_id=slot.owned_copy_operation_id,
            route_sha256=plan.route_sha256,
            plan_sha256=plan.plan_sha256,
            owned_library=slot.owned_library,
            owned_cell=route.source_cell,
            owned_before_view_tree_sha256=slot.owned_before_view_tree_sha256,
            owned_before_testbench_tree_sha256=slot.owned_before_testbench_tree_sha256,
            source_preservation_sha256=slot.source_preservation_sha256,
        )
        scope = _SizingScope(
            route=reg.route,
            context_id=reg.context_id,
            resource_domain_sha256=reg.resource_domain_sha256,
            environment_sha256=reg.environment_sha256,
            native_manifest_sha256=reg.native_manifest_sha256,
            subject=subject,
            route_qualification=route,
            plan=plan,
            candidate_request=plan.requested,
            guest_sha256=reg.guest_sha256,
            native_safety_sha256=slot.native_safety_sha256,
            sizing_sha256=_sha(sizing),
            valid_until_unix=reg.valid_until_unix,
            slot_manifest_sha256=slot.slot_manifest_sha256,
        )
        guest_contract.sizing_route(scope.model_dump(mode="json"))  # type: ignore[no-untyped-call]
        binding = RegisteredMosEditBinding(
            scope_sha256=canonical_digest(scope), **subject.model_dump()
        )
        provider = _SizingPhaseProvider(
            self._context,
            directory,
            reg,
            self.enrollment_sha256,
            scope,
            sizing,
            self._baseline,
        )
        binding_pin = canonical_digest(binding)
        if isinstance(route, RegisteredOtaMosSizingRoute):
            if self._baseline_reopen_stdout is None:
                raise ValueError("OTA sizing requires the original detached reopen stdout")
            return RegisteredOtaMosSizingService(
                binding,
                route,
                slot.child,
                plan.requested,
                self._baseline,
                provider,
                expected_binding_sha256=binding_pin,
                baseline_reopen_stdout=self._baseline_reopen_stdout,
                baseline_recovery=self._baseline_recovery,
                baseline_reopen_receipt=self._baseline_reopen_receipt,
            )
        return RegisteredMosSizingService(
            binding,
            route,
            slot.child,
            plan.requested,
            self._baseline,
            provider,
            expected_binding_sha256=binding_pin,
        )

    def plan(self, candidate: MosSizingCandidate) -> MosSizingPreview:
        service = self._service(candidate)
        return MosSizingPreview(
            identity=service.identity,
            enrollment_sha256=self.enrollment_sha256,
            plan=service.plan,
        )

    def apply(self, request: MosSizingApply) -> RegisteredMosSizingResult:
        return self._service(request.candidate).apply(request.identity)

    def lookup(self, request: PmosDefaultChangeRequest) -> MosSizingLookup:
        status, _ = self.lookup_evidence(request)
        return status

    def lookup_evidence(
        self, request: PmosDefaultChangeRequest,
    ) -> tuple[MosSizingLookup, RetainedMosSizingEvidence | None]:
        _, directory = self._slot(request.operation_id)
        claim = directory / _CLAIM
        if not os.path.lexists(claim):
            outcome: Literal["NOT_FOUND", "OUTCOME_UNKNOWN"] = (
                "OUTCOME_UNKNOWN" if any(directory.glob("registered-mos-phase-*")) else "NOT_FOUND"
            )
            return MosSizingLookup(identity=request, outcome=outcome), None
        try:
            intent = _document(_read(claim, 4096))
            values = MosSizingValues.model_validate(intent["candidate_request"])
        except (OSError, ValueError, KeyError):
            return MosSizingLookup(identity=request, outcome="OUTCOME_UNKNOWN"), None
        _require(
            intent.get("enrollment_sha256") == self.enrollment_sha256,
            "registered_mos_sizing_claim_enrollment",
        )
        result, evidence = self._service(
            MosSizingCandidate(
                operation_id=request.operation_id,
                expected_enrollment_sha256=self.enrollment_sha256,
                expected_baseline_sha256=self._reg.route_qualification.baseline.revision_sha256,
                values=values,
            )
        ).lookup_evidence(request)
        return MosSizingLookup(identity=request, outcome=result.outcome, result=result), evidence


def selected_mos_sizing(context: ExecutionContext) -> RegisteredMosSizing | None:
    """Dispatch only the new discriminator; existing v3 checks stay in their loader."""
    path = context.binding.pmos_default_change_binding
    digest = context.binding.pmos_default_change_sha256
    if path is None or digest is None:
        return None
    raw = read_pmos_default_change_binding(path, digest)
    if _document(raw).get("route") not in ("registered_mos_sizing", "registered_ota_mos_sizing"):
        return None
    return RegisteredMosSizing(context, raw, digest)
