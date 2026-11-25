"""Plan and independently verify a new W/L on a registered, owned MOS copy."""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal, localcontext
from typing import Annotated, Literal, NamedTuple, Self, cast

from pydantic import Field, model_validator

from cadence_mcp_bridge._native_rendering import partition_input
from cadence_mcp_bridge.candidate_contracts import CandidateSourceTarget
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeRequest
from cadence_mcp_bridge.parameter_changes import (
    ChangeBaseline,
    ChangeValue,
    DerivedValue,
    GeometryProperty,
    NetlistProjection,
    _checked,
    _same_inverter_bench_with_reordered_instances,
    _width_options,
    mos_multiplicity_factors,
)
from cadence_mcp_bridge.registered_mos_edit import (
    _GEOMETRY,
    _PROPERTIES,
    MosProperty,
    MosPropertyValue,
    NativeMosEditCapture,
    NativeMosEditSave,
    RegisteredMosEditBinding,
    RegisteredMosEditProvider,
    RegisteredMosEditResult,
    RetainedMosEdit,
    _observed_factors,
    _verify_reopened_cdf,
)
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    NumberText,
    VariableModel,
    canonical_digest,
    number_text,
)

SizingAxis = Literal["w", "l"]
type _NetlistControls = tuple[dict[str, str], list[tuple[str, str]], list[tuple[str, str]]]
_AXES: tuple[SizingAxis, SizingAxis] = ("w", "l")
_OA_DIMENSIONS: tuple[MosProperty, ...] = ("w", "fw", "l")
_PROJECTED_GEOMETRY: tuple[GeometryProperty, ...] = ("fw", "as", "ad", "ps", "pd")
_INPUT_DIMENSIONS: tuple[MosProperty, ...] = ("w", "l", "as", "ad", "ps", "pd")
_STATIC_KEYS = frozenset(("m", "fingers", "nf", "model", "dfm"))
_NETLIST_KEYS = frozenset(("w", "l", "m", "simM")) | _GEOMETRY
_SOURCE9_DC_SHA256 = "5d4134980c80d6cff72e6c1adb0d5957e7871c7b52fa89d5482dfedf113c7f0a"
_ENGINEERING_SCALE = {"": 0, "a": -18, "f": -15, "p": -12, "n": -9, "u": -6, "m": -3}


class MosSizingLength(ChangeValue):
    unit: Literal["nm", "um"]

    @classmethod
    def from_metres(cls, metres: Decimal) -> MosSizingLength:
        with localcontext() as context:
            context.prec = 128
            return cls(value=number_text(str(metres.scaleb(9))), unit="nm")

    def in_nm(self) -> MosSizingLength:
        return self.from_metres(Decimal(self.normalized[0]))


class MosSizingValues(VariableModel):
    w: MosSizingLength | None = None
    l: MosSizingLength | None = None  # noqa: E741 - schematic property name

    @model_validator(mode="after")
    def needs_dimension(self) -> Self:
        if self.w is None and self.l is None:
            raise ValueError("specify at least one MOS sizing dimension")
        return self


class MosSizingDimensions(VariableModel):
    w: MosSizingLength
    l: MosSizingLength  # noqa: E741 - schematic property name


class MosSizingBounds(VariableModel):
    """Only limits observed and approved for this registered dimension."""

    minimum: MosSizingLength | None = None
    maximum: MosSizingLength | None = None
    grid_step: MosSizingLength | None = None
    grid_origin_nm: NumberText | None = None

    @model_validator(mode="after")
    def coherent_bounds(self) -> Self:
        if (
            self.minimum
            and self.maximum
            and Decimal(self.minimum.normalized[0]) > Decimal(self.maximum.normalized[0])
        ):
            raise ValueError("invalid observed MOS sizing limits")
        if (self.grid_step is None) != (self.grid_origin_nm is None):
            raise ValueError("MOS sizing grid requires its observed origin and step")
        if self.grid_origin_nm is not None:
            number_text(self.grid_origin_nm)
        return self

    def check(self, value: MosSizingLength) -> None:
        nm = Decimal(value.in_nm().value)
        if (self.minimum and nm < Decimal(self.minimum.in_nm().value)) or (
            self.maximum and nm > Decimal(self.maximum.in_nm().value)
        ):
            raise ValueError("MOS sizing value is outside the registered bounds")
        if self.grid_step is not None and self.grid_origin_nm is not None:
            with localcontext() as context:
                context.prec = 128
                if (nm - Decimal(self.grid_origin_nm)) % Decimal(self.grid_step.in_nm().value):
                    raise ValueError("MOS sizing value is off the registered grid")


class MosSizingSupport(VariableModel):
    cadence_version: Annotated[str, Field(pattern=r"^[0-9]+(?:\.[0-9]+){2,5}$", max_length=48)]
    pdk_release: Literal["4.6"]
    pdk_identity_sha256: Digest
    adapter_sha256: Digest
    cdf_constraints_sha256: Digest
    w: MosSizingBounds | None = None
    l: MosSizingBounds | None = None  # noqa: E741 - schematic property name

    @model_validator(mode="after")
    def supported_axis(self) -> Self:
        if self.w is None and self.l is None:
            raise ValueError("registered MOS sizing requires an admitted W or L axis")
        return self


class MosSizingTarget(VariableModel):
    instance: CandidateSourceTarget
    netlist_path: Annotated[
        str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_#-]*(/[A-Za-z][A-Za-z0-9_#-]*)?$", max_length=256)
    ]
    netlist_model: Literal["gpdk090_nmos1v", "gpdk090_pmos1v"]
    netlist_terminals: tuple[str, str, str, str]

    @model_validator(mode="after")
    def supported_target(self) -> Self:
        target = self.instance
        if (
            (target.master_library, target.master_view) != ("gpdk090", "symbol")
            or target.master_cell not in ("nmos1v", "pmos1v")
            or target.property_name not in ("w", "l")
            or target.instance_path != self.netlist_path
            or self.netlist_model != f"gpdk090_{target.master_cell}"
            or any(
                re.fullmatch(r"[A-Za-z0-9_#!:+.-]{1,128}", net) is None
                for net in self.netlist_terminals
            )
        ):
            raise ValueError("unsupported registered MOS sizing target")
        return self


def _engineering(raw: str | None) -> Decimal:
    if raw is None:
        raise ValueError("missing observed MOS numeric literal")
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?([afpnum]?)", raw)
    if match is None:
        raise ValueError("unsupported observed MOS numeric literal")
    value = Decimal(number_text(match[1] + (match[2] or "")))
    with localcontext() as context:
        context.prec = 128
        return value.scaleb(_ENGINEERING_SCALE[match[3]])


def _observed_dimensions(properties: dict[MosProperty, MosPropertyValue]) -> MosSizingDimensions:
    if properties.keys() != _PROPERTIES or _observed_factors(properties) != ("1", "1"):
        raise ValueError("MOS sizing requires complete observations with m=1 and one finger")
    if any(properties[key].cdf_units != "lengthMetric" for key in _OA_DIMENSIONS):
        raise ValueError("MOS sizing requires observed lengthMetric CDF dimensions")
    width = _engineering(properties["w"].cdf_value)
    if width != _engineering(properties["fw"].cdf_value):
        raise ValueError("single-finger total width and finger width disagree")
    return MosSizingDimensions(
        w=MosSizingLength.from_metres(width),
        l=MosSizingLength.from_metres(_engineering(properties["l"].cdf_value)),
    )


class RegisteredMosSizingRoute(VariableModel):
    baseline: ChangeBaseline
    source_library: BindingName
    source_cell: BindingName
    testbench_cell: BindingName
    target: MosSizingTarget
    support: MosSizingSupport
    before: dict[MosProperty, MosPropertyValue]

    @model_validator(mode="after")
    def observed_baseline(self) -> Self:
        _observed_dimensions(self.before)
        if (
            self.source_library in ("gpdk090", "analogLib", "basic")
            or self.before["model"].cdf_value != self.target.netlist_model
            or self.before["nf"].cdf_value is not None
            or self.before["nf"].oa_value is not None
            or self.before["dfm"].cdf_value != "Minimum"
        ):
            raise ValueError("registered MOS sizing baseline differs from the supported mode")
        return self


class MosSizingPlan(VariableModel):
    baseline: ChangeBaseline
    candidate_revision: RevisionBinding
    target: MosSizingTarget
    route_sha256: Digest
    current: MosSizingDimensions
    requested: MosSizingValues
    expected: MosSizingDimensions
    changed: Annotated[tuple[SizingAxis, ...], Field(min_length=1, max_length=2)]
    allowed_derived: tuple[GeometryProperty, ...]

    @property
    def plan_sha256(self) -> str:
        return canonical_digest(self)


def plan_registered_mos_sizing(
    route: RegisteredMosSizingRoute, child: RevisionBinding, requested: MosSizingValues
) -> MosSizingPlan:
    route, child, requested = _checked(route), _checked(child), _checked(requested)
    baseline = route.baseline
    parent = baseline.revision
    if (child.workspace_id, child.design_id, child.source_baseline_sha256) != (
        parent.workspace_id,
        parent.design_id,
        parent.source_baseline_sha256,
    ) or (child.parent_revision_id, child.parent_revision_sha256) != (
        parent.revision_id,
        baseline.revision_sha256,
    ):
        raise ValueError("MOS sizing candidate must be a fresh child of the registered baseline")
    current = _observed_dimensions(route.before)
    supplied: dict[SizingAxis, MosSizingLength] = {}
    changed: list[SizingAxis] = []
    for axis in _AXES:
        value = getattr(requested, axis)
        if value is None:
            continue
        bounds = getattr(route.support, axis)
        if bounds is None:
            raise ValueError(f"MOS sizing dimension {axis} is not registered")
        bounds.check(value)
        supplied[axis] = value.in_nm()
        if supplied[axis] != getattr(current, axis):
            changed.append(axis)
    if not changed:
        raise ValueError("MOS sizing request does not change the registered dimensions")
    return MosSizingPlan(
        baseline=baseline,
        candidate_revision=child,
        target=route.target,
        route_sha256=canonical_digest(route),
        current=current,
        requested=MosSizingValues(w=supplied.get("w"), l=supplied.get("l")),
        expected=MosSizingDimensions(
            w=supplied.get("w", current.w), l=supplied.get("l", current.l)
        ),
        changed=tuple(changed),
        allowed_derived=_PROJECTED_GEOMETRY if "w" in changed else _PROJECTED_GEOMETRY[1:],
    )


def verify_mos_sizing_save(
    plan: MosSizingPlan,
    route: RegisteredMosSizingRoute,
    binding: RegisteredMosEditBinding,
    save: NativeMosEditSave,
) -> None:
    """Gate the detached phase using the original save receipt and its observed values."""
    save = _checked(save)
    before, after = save.baseline, save.saved
    if (
        binding.plan_sha256 != plan.plan_sha256
        or binding.route_sha256 != plan.route_sha256
        or plan.route_sha256 != canonical_digest(route)
        or (save.operation_id, save.plan_sha256, save.scope_sha256)
        != (binding.operation_id, binding.plan_sha256, binding.scope_sha256)
        or save.source_preservation_sha256 != binding.source_preservation_sha256
        or (before.stage, after.stage) != ("baseline", "saved")
        or (before.revision_sha256, before.testbench_revision_sha256)
        != (binding.owned_before_view_tree_sha256, binding.owned_before_testbench_tree_sha256)
        or after.revision_sha256 in (before.revision_sha256, plan.baseline.revision_sha256)
        or before.footprint_sha256 != after.footprint_sha256
        or before.receipt_sha256 == after.receipt_sha256
        or before.properties != route.before
    ):
        raise ValueError("MOS sizing save receipt differs from its exact baseline or owned binding")
    if "/" in plan.target.netlist_path:
        valid_bench = before.testbench_revision_sha256 == after.testbench_revision_sha256
    else:
        valid_bench = (
            before.testbench_revision_sha256 == before.revision_sha256
            and after.testbench_revision_sha256 == after.revision_sha256
        )
    if not valid_bench:
        raise ValueError("MOS sizing testbench revision changed unexpectedly")
    observed = after.properties
    if _observed_dimensions(observed) != plan.expected:
        raise ValueError("saved OA/CDF MOS dimensions differ from the requested or held values")
    for key, old in before.properties.items():
        row = observed[key]
        if (old.cdf_type, old.cdf_units) != (row.cdf_type, row.cdf_units):
            raise ValueError("MOS sizing changed the observed property schema")
        if key in _STATIC_KEYS and row != old:
            raise ValueError(f"MOS sizing changed fixed property {key}")
        if key in ("w", "fw", "l"):
            axis = "w" if key == "fw" else key
            if axis in plan.changed:
                if row.oa_type != "string" or _engineering(row.oa_value) != _engineering(
                    row.cdf_value
                ):
                    raise ValueError(f"saved OA property {key} differs from the effective CDF")
            elif row.oa_type != old.oa_type or (
                row.oa_value != old.oa_value
                and (
                    row.oa_value is None
                    or old.oa_value is None
                    or _engineering(row.oa_value) != _engineering(old.oa_value)
                )
            ):
                raise ValueError(f"MOS sizing changed held property {key}")
        if key in _GEOMETRY:
            cdf_value = _engineering(row.cdf_value)
            if row.oa_value is not None and _engineering(row.oa_value) != cdf_value:
                raise ValueError(f"saved OA junction property {key} differs from the effective CDF")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _check_input(
    target: MosSizingTarget, raw: bytes, properties: dict[MosProperty, MosPropertyValue]
) -> tuple[_NetlistControls, list[str], dict[str, str]]:
    params, includes, analyses, static = partition_input(raw)  # type: ignore[no-untyped-call]
    fixed, options = _width_options(static, target.netlist_path, registered=target)
    if (
        options.keys() != _NETLIST_KEYS
        or mos_multiplicity_factors(options["m"]) != ("1", "1")
        or mos_multiplicity_factors(options["simM"]) != ("1", "1")
        or any(
            _engineering(options[key])
            != _engineering(properties["fw" if key == "w" else key].cdf_value)
            for key in _INPUT_DIMENSIONS
        )
    ):
        raise ValueError("actual Spectre MOS options differ from the reopened CDF")
    return (params, includes, analyses), fixed, options


class RegisteredMosSizingResult(RegisteredMosEditResult):
    requested: MosSizingValues
    expected: MosSizingDimensions
    observed: MosSizingDimensions | None = None


class RetainedMosSizingEvidence(NamedTuple):
    plan: MosSizingPlan
    binding: RegisteredMosEditBinding
    baseline_input: bytes
    confirmed_input: bytes


class RegisteredMosSizingService:
    """Reuse the existing exclusive claim and two native capture phases for W/L."""

    def __init__(
        self,
        binding: RegisteredMosEditBinding,
        route: RegisteredMosSizingRoute,
        child: RevisionBinding,
        requested: MosSizingValues,
        baseline_input: bytes,
        provider: RegisteredMosEditProvider,
        *,
        expected_binding_sha256: str,
    ) -> None:
        binding, route = _checked(binding), _checked(route)
        plan = plan_registered_mos_sizing(route, child, requested)
        if (
            canonical_digest(binding) != expected_binding_sha256
            or binding.route_sha256 != plan.route_sha256
            or binding.plan_sha256 != plan.plan_sha256
            or binding.operation_id == binding.owned_copy_operation_id
            or binding.owned_library in (route.source_library, "gpdk090", "analogLib", "basic")
            or binding.owned_cell != route.source_cell
            or not 0 < len(baseline_input) <= 32768
            or _sha(baseline_input) != plan.baseline.netlist_sha256
        ):
            raise ValueError("MOS sizing registration, baseline or owned copy mismatch")
        self.plan = plan
        self.identity = PmosDefaultChangeRequest(
            operation_id=binding.operation_id,
            expected_plan_sha256=plan.plan_sha256,
            expected_scope_sha256=binding.scope_sha256,
        )
        self._before = _check_input(route.target, baseline_input, route.before)
        self._binding, self._route = binding, route
        self._baseline_input, self._provider = baseline_input, provider

    def _check_request(self, request: PmosDefaultChangeRequest) -> None:
        if _checked(request) != self.identity:
            raise ValueError("MOS sizing request conflicts with the approved operation")

    def lookup(self, request: PmosDefaultChangeRequest) -> RegisteredMosSizingResult:
        result, _ = self.lookup_evidence(request)
        return result

    def lookup_evidence(
        self, request: PmosDefaultChangeRequest,
    ) -> tuple[RegisteredMosSizingResult, RetainedMosSizingEvidence | None]:
        """Return the verified original capture to trusted host consumers only."""
        self._check_request(request)
        retained = self._provider.lookup(self._binding)
        if retained is None:
            return self._empty("NOT_FOUND", replayed=False), None
        result = self._result(retained, replayed=True)
        if result.outcome != "VERIFIED" or retained.capture is None:
            return result, None
        return result, RetainedMosSizingEvidence(
            self.plan, self._binding, self._baseline_input, retained.capture.netlist,
        )

    def apply(self, request: PmosDefaultChangeRequest) -> RegisteredMosSizingResult:
        self._check_request(request)
        binding, provider = self._binding, self._provider
        retained = provider.lookup(binding)
        if retained is not None:
            return self._result(retained, replayed=True)
        if not provider.claim(binding):
            return self._result(provider.lookup(binding) or RetainedMosEdit(None), replayed=True)
        try:
            retained = provider.dispatch(binding)
        except (OSError, ValueError):
            retained = RetainedMosEdit(None)
        return self._result(retained, replayed=False)

    def _empty(
        self, outcome: Literal["NOT_FOUND", "OUTCOME_UNKNOWN"], *, replayed: bool
    ) -> RegisteredMosSizingResult:
        return RegisteredMosSizingResult(
            identity=self.identity,
            candidate_revision=self.plan.candidate_revision,
            requested=self.plan.requested,
            expected=self.plan.expected,
            outcome=outcome,
            replayed=replayed,
            dispatched_this_call=False if replayed or outcome == "NOT_FOUND" else None,
        )

    def _result(self, retained: RetainedMosEdit, *, replayed: bool) -> RegisteredMosSizingResult:
        if retained.capture is not None:
            try:
                return self._verified(retained.capture, replayed=replayed)
            except ValueError:
                pass
        return self._empty("OUTCOME_UNKNOWN", replayed=replayed)

    def _verified(
        self, capture: NativeMosEditCapture, *, replayed: bool
    ) -> RegisteredMosSizingResult:
        plan = self.plan
        readback = _checked(capture.readback)
        verify_mos_sizing_save(plan, self._route, self._binding, readback)
        before, saved, reopened = readback.baseline, readback.saved, readback.reopened
        if (
            reopened.stage != "reopened"
            or (reopened.revision_sha256, reopened.testbench_revision_sha256)
            != (saved.revision_sha256, saved.testbench_revision_sha256)
            or (readback.netlisted_revision_sha256, readback.netlisted_testbench_revision_sha256)
            != (reopened.revision_sha256, reopened.testbench_revision_sha256)
            or reopened.properties != saved.properties
            or reopened.footprint_sha256 != saved.footprint_sha256
            or len(
                {
                    before.receipt_sha256,
                    saved.receipt_sha256,
                    reopened.receipt_sha256,
                    readback.netlist_receipt_sha256,
                }
            )
            != 4
            or not 0 < len(capture.cdf_frame) <= 262144
            or _sha(capture.cdf_frame) != readback.cdf_frame_sha256
            or not 0 < len(capture.netlist) <= 32768
            or _sha(capture.netlist) != readback.netlist_sha256
        ):
            raise ValueError(
                "independent sizing readback or netlisted revision differs from the save"
            )
        _verify_reopened_cdf(capture.cdf_frame, plan.target, reopened.properties)
        header, fixed, options = _check_input(plan.target, capture.netlist, reopened.properties)
        old_header, old_fixed, _ = self._before
        source9 = (
            plan.baseline.netlist_sha256 == _SOURCE9_DC_SHA256
            and plan.baseline.revision.design_id == "cmos-long-inverter"
            and plan.baseline.revision.revision_id == "long-r1"
            and plan.target.netlist_path in ("DUT/MN", "DUT/MP")
        )
        if header != old_header or (
            fixed != old_fixed
            and not (
                source9
                and _same_inverter_bench_with_reordered_instances(
                    old_fixed, fixed, self._baseline_input, capture.netlist
                )
            )
        ):
            raise ValueError("MOS sizing changed fixed Netlist conditions, model or topology")
        observed = _observed_dimensions(reopened.properties)
        return RegisteredMosSizingResult(
            identity=self.identity,
            candidate_revision=plan.candidate_revision,
            requested=plan.requested,
            expected=plan.expected,
            observed=observed,
            outcome="VERIFIED",
            replayed=replayed,
            dispatched_this_call=not replayed,
            readback=readback,
            effective_mos_options=options,
            effective_input=NetlistProjection(
                artifact_sha256=readback.netlist_sha256,
                value=observed.w if plan.changed[0] == "w" else observed.l,
                derived=tuple(
                    DerivedValue(
                        property_name=key, value=cast(str, reopened.properties[key].cdf_value)
                    )
                    for key in _PROJECTED_GEOMETRY
                ),
            ),
        )
