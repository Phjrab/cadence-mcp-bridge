"""Plan and verify one finite edit through an operator-registered MOS writer."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any, Literal, Protocol, Self, cast

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from cadence_mcp_bridge._native_rendering import partition_input
from cadence_mcp_bridge.candidate_contracts import CandidateSourceTarget
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeRequest
from cadence_mcp_bridge.m2_cdf import _atoms, parse_frame
from cadence_mcp_bridge.m2_inverter import _mos_parameters
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.parameter_changes import (
    ChangePlan,
    ChangeValue,
    NetlistProjection,
    RegisteredMosQualification,
    RegisteredMosTarget,
    _checked,
    _width_options,
    mos_multiplicity_factors,
    plan_registered_mos_change,
    project_netlist_change,
)
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    VariableModel,
    canonical_digest,
)

MosParameter = Literal["w", "fw", "l", "m", "fingers"]
MosSetParameter = Literal["w", "fw", "l", "m"]
MosProperty = Literal["w", "fw", "l", "m", "fingers", "as", "ad", "ps", "pd", "nf", "model", "dfm"]
_GEOMETRY: frozenset[MosProperty] = frozenset(("as", "ad", "ps", "pd"))
_PROPERTIES = frozenset(("w", "fw", "l", "m", "fingers", "nf", "model", "dfm")) | _GEOMETRY
_LENGTH: dict[str, Literal["m", "um", "nm"]] = {"": "m", "u": "um", "n": "nm"}

ObservedLiteral = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[ -~]+$")]


class MosPropertyValue(VariableModel):
    """A paired OA/CDF readback. Null records an observed absent property."""

    oa_type: Literal["string", "int", "float"] | None
    oa_value: ObservedLiteral | None
    cdf_type: BindingName | None
    cdf_units: BindingName | None
    cdf_value: ObservedLiteral | None

    @model_validator(mode="after")
    def complete_reads(self) -> Self:
        if (
            (self.oa_type is None) != (self.oa_value is None)
            or (self.cdf_type is None) != (self.cdf_value is None)
            or (self.cdf_type is None and self.cdf_units is not None)
        ):
            raise ValueError("incomplete OA or CDF property observation")
        return self


def _number(name: MosParameter, row: MosPropertyValue) -> ChangeValue:
    raw = row.cdf_value
    if raw is None:
        raise ValueError("registered scalar needs effective CDF evidence")
    if name in ("m", "fingers"):
        if re.fullmatch(r"[1-9][0-9]{0,5}", raw) is None:
            raise ValueError("observed CDF count must be an explicit bounded positive integer")
        return ChangeValue(value=raw, unit="count")
    if row.cdf_units != "lengthMetric":
        raise ValueError("registered schematic length needs lengthMetric CDF semantics")
    return _length(raw)


def _length(raw: str) -> ChangeValue:
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    value = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?|\.[0-9]+)([un]?)", raw)
    if value is None:
        raise ValueError("unsupported effective CDF length literal")
    unit = _LENGTH[value[2]]
    return ChangeValue(value=value[1], unit=unit)


def _changed_lengths(
    before: dict[MosProperty, MosPropertyValue], after: dict[MosProperty, MosPropertyValue]
) -> tuple[Literal["w", "l"], ...]:
    lengths: tuple[Literal["w", "l"], ...] = ("w", "l")
    return tuple(
        key
        for key in lengths
        if _number(key, before[key]).normalized != _number(key, after[key]).normalized
    )


class MosEditValues(VariableModel):
    w: ChangeValue | None = None
    fw: ChangeValue | None = None
    l: ChangeValue | None = None  # noqa: E741 - Cadence CDF parameter name.
    m: ChangeValue | None = None
    fingers: ChangeValue | None = None


class MosCdfWriteField(VariableModel):
    param_type: Literal["string", "int"]
    minimum: ObservedLiteral | None
    maximum: ObservedLiteral | None
    callback_present: bool

    def check_value(self, name: MosSetParameter, value: ChangeValue) -> None:
        if self.param_type == "int" and name != "m":
            raise ValueError("integer storage is restricted to the multiplier")
        for edge, upper in ((self.minimum, False), (self.maximum, True)):
            if edge is None:
                continue
            if name == "m":
                if re.fullmatch(r"[0-9]{1,6}", edge) is None:
                    raise ValueError("ambiguous CDF multiplier bound")
                limit = Decimal(edge)
            else:
                if not edge.endswith(("u", "n")):
                    raise ValueError("CDF length bound must have an observed metric suffix")
                limit = Decimal(_length(edge).normalized[0])
            scalar = Decimal(value.normalized[0])
            if (upper and scalar > limit) or (not upper and scalar < limit):
                raise ValueError("registered explicit value is outside the observed CDF bounds")


class MosExplicitSet(VariableModel):
    """A reviewed finite OA property setter with an independent target witness."""

    fields: dict[MosSetParameter, MosCdfWriteField]
    constraints_sha256: Digest
    witness_operation_id: OperationId
    witness_readback_sha256: Digest
    witness_cdf_sha256: Digest
    witness_input_sha256: Digest


class RegisteredMosEditRoute(VariableModel):
    """One reviewed before/after tuple, supplied by the trusted host registration."""

    qualification: RegisteredMosQualification
    before: dict[MosProperty, MosPropertyValue]
    after: dict[MosProperty, MosPropertyValue]
    # Pin the vetted Cadence update entry, independent of the CDF value evidence.
    update_route_sha256: Digest
    explicit_set: MosExplicitSet | None = None

    @model_serializer(mode="wrap")
    def omit_absent_explicit_set(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        document: dict[str, Any] = handler(self)
        if self.explicit_set is None:
            document.pop("explicit_set", None)
        return document

    @model_validator(mode="after")
    def finite_single_finger_route(self) -> Self:
        q = self.qualification
        target = q.target
        i = target.instance
        if (
            (i.master_library, i.master_view) != ("gpdk090", "symbol")
            or i.master_cell not in ("nmos1v", "pmos1v")
            or target.netlist_model != f"gpdk090_{i.master_cell}"
            or i.property_name not in ("w", "fw", "l", "m")
            or target.scalar_option != ("w" if i.property_name == "fw" else i.property_name)
            or target.quantity != ("count" if i.property_name == "m" else "length")
            or set(self.before) != _PROPERTIES
            or set(self.after) != _PROPERTIES
        ):
            raise ValueError("unsupported registered GPDK090 single-finger edit binding")
        primary = "w" if i.property_name == "fw" else cast(Literal["w", "l", "m"], i.property_name)
        for frame in (self.before, self.after):
            if (
                _number("w", frame["w"]).normalized != _number("fw", frame["fw"]).normalized
                or _number("fingers", frame["fingers"]).normalized != ("1", "count")
                or (
                    self.explicit_set is None
                    and primary != "m"
                    and _number("m", frame["m"]).normalized != ("1", "count")
                )
            ):
                raise ValueError("this route requires single-finger CDF semantics")
        if (
            _number(primary, self.before[primary]).normalized != q.old.normalized
            or _number(primary, self.after[primary]).normalized != q.expected.normalized
            or q.old.normalized == q.expected.normalized
        ):
            raise ValueError("effective CDF tuple does not match the registered scalar")
        lengths = _changed_lengths(self.before, self.after)
        changes_m = (
            _number("m", self.before["m"]).normalized != _number("m", self.after["m"]).normalized
        )
        if changes_m and lengths and self.explicit_set is None:
            raise ValueError("joint length and multiplier changes need explicit-set evidence")
        # Width is emitted as w. Its finger-width companion is an OA/CDF observation.
        dependencies: set[MosProperty] = set(_GEOMETRY) if lengths else set()
        if "w" in lengths:
            dependencies.add("fw")
        derived = {
            change.before.property_name: (change.before.value, change.after.value)
            for change in q.derived
        }
        effect = {
            key: (self.before[key].cdf_value, self.after[key].cdf_value)
            for key in dependencies
            if self.before[key].cdf_value != self.after[key].cdf_value
        }
        if len(derived) != len(q.derived) or derived != effect:
            raise ValueError("unregistered dependent CDF geometry transition")
        for key, before in self.before.items():
            after = self.after[key]
            if (before.cdf_type, before.cdf_units) != (after.cdf_type, after.cdf_units):
                raise ValueError("CDF parameter schema changed")
            if (
                not (key == "m" and changes_m)
                and key not in lengths
                and key not in derived
                and before != after
            ):
                raise ValueError("non-target OA or effective CDF property changed")
        option_values = {o.name: (o.before, o.after) for o in target.options if o.before != o.after}
        expected_options: set[str] = {*lengths, *(set(derived) & _GEOMETRY)}
        if changes_m:
            expected_options.update(("m", "simM"))
        if set(option_values) != expected_options or any(
            option_values[key] != derived[key] for key in set(derived) & _GEOMETRY
        ):
            raise ValueError("unregistered effective Spectre option transition")
        if changes_m:
            if option_values["m"] != option_values["simM"]:
                raise ValueError(
                    "registered m transition must independently change both emitted factors"
                )
            for token, frame in zip(option_values["m"], (self.before, self.after), strict=True):
                if mos_multiplicity_factors(token) != _observed_factors(frame):
                    raise ValueError(
                        "emitted multiplier or finger factor differs from the CDF tuple"
                    )
        if self.explicit_set is not None:
            self._check_explicit_set(lengths, changes_m)
        old, new = option_values[primary]
        if (
            target.parse_scalar(old, baseline=True).normalized != q.old.normalized
            or target.parse_scalar(new).normalized != q.expected.normalized
        ):
            raise ValueError("emitted scalar differs from the qualified CDF tuple")
        for key in lengths:
            old_token, new_token = option_values[key]
            if (
                _length(old_token).normalized != _number(key, self.before[key]).normalized
                or _length(new_token).normalized != _number(key, self.after[key]).normalized
            ):
                raise ValueError("emitted length differs from the qualified CDF tuple")
        return self

    def _check_explicit_set(self, lengths: tuple[Literal["w", "l"], ...], changes_m: bool) -> None:
        assert self.explicit_set is not None
        fields = self.explicit_set.fields
        required: set[MosSetParameter] = set(lengths)
        if "w" in required:
            required.add("fw")
        if changes_m:
            required.add("m")
        if set(fields) != required:
            raise ValueError(
                "explicit-set metadata must cover exactly the changed dimensions and multiplier"
            )
        for name, spec in fields.items():
            row = self.after[name]
            if row.oa_type != spec.param_type or row.oa_value != row.cdf_value:
                raise ValueError(
                    "explicit storage must match the reviewed effective value and type"
                )
            spec.check_value(name, _number(name, row))
        for geometry in _GEOMETRY:
            if self.before[geometry] != self.after[geometry]:
                row = self.after[geometry]
                if row.oa_type != "string" or row.oa_value != row.cdf_value:
                    raise ValueError("changed geometry needs reviewed explicit string storage")


def plan_registered_mos_edit(
    route: RegisteredMosEditRoute, child: RevisionBinding, requested: MosEditValues
) -> ChangePlan:
    """Match exact finite values. Co-specified fields constrain the result."""
    route, requested = _checked(route), _checked(requested)
    q = route.qualification
    fields: tuple[tuple[MosParameter, ChangeValue | None], ...] = (
        ("w", requested.w),
        ("fw", requested.fw),
        ("l", requested.l),
        ("m", requested.m),
        ("fingers", requested.fingers),
    )
    supplies = {name: value for name, value in fields if value is not None}
    if (
        requested.w is not None
        and requested.fw is not None
        and requested.w.normalized != requested.fw.normalized
    ):
        raise ValueError("w and fw conflict for this single-finger route")
    supplied_lengths = set(supplies)
    if "fw" in supplied_lengths:
        supplied_lengths.add("w")
    if not set(_changed_lengths(route.before, route.after)).issubset(supplied_lengths):
        raise ValueError("every registered width and length change must be explicitly requested")
    if (
        _observed_factors(route.before)[0] != _observed_factors(route.after)[0]
        and requested.m is None
    ):
        raise ValueError("the registered multiplier change must be explicitly requested")
    for name, value in supplies.items():
        if value.normalized != _number(name, route.after[name]).normalized:
            raise ValueError(f"{name} is outside the reviewed finite tuple")
    # Canonical qualification units give equivalent requests one registered plan hash.
    return plan_registered_mos_change(q, child.revision_id, child, q.expected)


class MosEditSubject(VariableModel):
    operation_id: OperationId
    owned_copy_operation_id: OperationId
    plan_sha256: Digest
    route_sha256: Digest
    owned_library: BindingName
    owned_cell: BindingName
    owned_view: Literal["schematic"] = "schematic"
    owned_before_view_tree_sha256: Digest
    owned_before_testbench_tree_sha256: Digest
    source_preservation_sha256: Digest


class RegisteredMosEditBinding(MosEditSubject):
    scope_sha256: Digest


class MosEditSnapshot(VariableModel):
    stage: Literal["baseline", "saved", "reopened"]
    revision_sha256: Digest
    testbench_revision_sha256: Digest
    footprint_sha256: Digest
    receipt_sha256: Digest
    properties: dict[MosProperty, MosPropertyValue]


class NativeMosEditSave(VariableModel):
    operation_id: OperationId
    plan_sha256: Digest
    scope_sha256: Digest
    baseline: MosEditSnapshot
    saved: MosEditSnapshot
    source_preservation_sha256: Digest


def same_saved_testbench(
    target: RegisteredMosTarget, before: MosEditSnapshot, saved: MosEditSnapshot
) -> bool:
    if "/" in target.netlist_path:
        return before.testbench_revision_sha256 == saved.testbench_revision_sha256
    return (
        before.revision_sha256 == before.testbench_revision_sha256
        and saved.revision_sha256 == saved.testbench_revision_sha256
    )


class NativeMosEditReadback(NativeMosEditSave):
    reopened: MosEditSnapshot
    netlisted_revision_sha256: Digest
    netlisted_testbench_revision_sha256: Digest
    netlist_receipt_sha256: Digest
    netlist_sha256: Digest
    cdf_frame_sha256: Digest


class MosSetWitness(VariableModel):
    """C1's independent non-OTA CDF calibration, which may share one test cell."""

    operation_id: OperationId
    method: Literal["cadence_edit_object_properties", "explicit_oa_replace_schcheck"]
    instance: CandidateSourceTarget
    netlist_path: Annotated[
        str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_#-]*(/[A-Za-z][A-Za-z0-9_#-]*)?$", max_length=256)
    ]
    netlist_terminals: tuple[str, str, str, str]
    before_footprint_sha256: Digest
    reopened: MosEditSnapshot
    netlisted_revision_sha256: Digest
    netlisted_testbench_revision_sha256: Digest
    cdf_frame_sha256: Digest
    netlist_sha256: Digest


@dataclass(frozen=True)
class NativeMosEditCapture:
    readback: NativeMosEditReadback
    netlist: bytes
    cdf_frame: bytes


def _verify_reopened_cdf(
    raw: bytes, target: RegisteredMosTarget, properties: dict[MosProperty, MosPropertyValue]
) -> None:
    (device,) = parse_frame(raw)
    instance = target.instance
    terminals = ("D", "G", "S", "B")
    if (
        "metadata_fields" not in device
        or (device["library"], device["cell"], device["instance"])
        != (
            instance.master_library,
            instance.master_cell,
            instance.instance_path.rsplit("/", 1)[-1],
        )
        or set(device["terminals"]) != set(terminals)  # type: ignore[call-overload]
        or set(device["spectre"]) != {("base", None, terminals), ("effective", None, terminals)}  # type: ignore[call-overload]
        or _mos_parameters(device)["model"] != target.netlist_model
    ):
        raise ValueError("reopened raw CDF has a different instance, master or Spectre mapping")
    rows = device["parameters"]
    assert isinstance(rows, tuple)
    effective = {
        name: (kind, unit, value)
        for scope, name, kind, unit, _, value in rows
        if scope == "effective"
    }
    if any(
        effective.get(key)
        != (None if row.cdf_type is None else (row.cdf_type, row.cdf_units, row.cdf_value))
        for key, row in properties.items()
    ):
        raise ValueError("reopened raw CDF differs from the effective property readback")


def _verify_effective_options(
    raw: bytes, target: RegisteredMosTarget, properties: dict[MosProperty, MosPropertyValue]
) -> dict[str, str]:
    _, _, _, static = partition_input(raw)  # type: ignore[no-untyped-call]
    _, options = _width_options(static, target.netlist_path, registered=target)
    if (
        set(options) != {"w", "l", "m", "simM", *_GEOMETRY}
        or _length(options["w"]).normalized != _number("fw", properties["fw"]).normalized
        or _length(options["l"]).normalized != _number("l", properties["l"]).normalized
        or mos_multiplicity_factors(options["m"]) != _observed_factors(properties)
        or mos_multiplicity_factors(options["simM"]) != _observed_factors(properties)
        or any(options[key] != properties[key].cdf_value for key in _GEOMETRY)
        or properties["model"].cdf_value != target.netlist_model
    ):
        raise ValueError("effective Spectre MOS options differ from the observed CDF")
    return options


def _observed_factors(properties: dict[MosProperty, MosPropertyValue]) -> tuple[str, str]:
    return _number("m", properties["m"]).normalized[0], _number(
        "fingers", properties["fingers"]
    ).normalized[0]


def verify_explicit_set_evidence(
    route: RegisteredMosEditRoute, constraints: bytes, readback: bytes, cdf: bytes, netlist: bytes
) -> None:
    """Check the independently retained C1 evidence before a writer claim."""
    proof = route.explicit_set
    if proof is None:
        raise ValueError("registered explicit-set evidence is required")
    for raw, pin in (
        (constraints, proof.constraints_sha256),
        (readback, proof.witness_readback_sha256),
        (cdf, proof.witness_cdf_sha256),
        (netlist, proof.witness_input_sha256),
    ):
        if hashlib.sha256(raw).hexdigest() != pin:
            raise ValueError("explicit-set evidence digest changed")
    witness = MosSetWitness.model_validate_json(readback)
    target = route.qualification.target
    calibration = witness.instance
    if (
        witness.operation_id != proof.witness_operation_id
        or calibration.model_copy(update={"instance_path": target.instance.instance_path})
        != target.instance
        or witness.reopened.stage != "reopened"
        or witness.reopened.footprint_sha256 != witness.before_footprint_sha256
        or witness.reopened.properties != route.after
        or witness.reopened.revision_sha256 != witness.netlisted_revision_sha256
        or witness.reopened.testbench_revision_sha256 != witness.netlisted_testbench_revision_sha256
        or witness.cdf_frame_sha256 != proof.witness_cdf_sha256
        or witness.netlist_sha256 != proof.witness_input_sha256
    ):
        raise ValueError("independent setter witness does not match the reopened target tuple")
    lines = constraints.decode("ascii").splitlines()
    if not 2 <= len(lines) <= 96 or lines[0] != "M2_CDF_CONSTRAINTS_V1" or lines[-1] != "COMPLETE":
        raise ValueError("missing C1 CDF constraint frame")
    fields = ("paramType", "minVal", "maxVal", "callback")
    observed: dict[tuple[str, str], tuple[object, object, object]] = {}
    for line in lines[1:-1]:
        kind, *columns = line.split("|")
        if kind != "LIMIT" or len(columns) != 6 or len(line) > 512:
            raise ValueError("malformed CDF constraint record")
        (master,), (name,), (field,), (status,), (data_type,), (value,) = map(_atoms, columns)
        if (
            master != target.instance.master_cell
            or not isinstance(name, str)
            or name not in proof.fields
            or not isinstance(field, str)
            or field not in fields
        ):
            continue
        key = name, field
        if key in observed or status not in ("observed", "missing"):
            raise ValueError("invalid duplicate or unobserved CDF constraint")
        observed[key] = status, data_type, value
    for name, spec in proof.fields.items():
        param_type, minimum, maximum, callback = (observed.get((name, field)) for field in fields)
        if (
            param_type != ("observed", "string", spec.param_type)
            or not _observed_bound(minimum, spec.minimum)
            or not _observed_bound(maximum, spec.maximum)
            or callback is None
            or callback[0] != ("observed" if spec.callback_present else "missing")
            or callback[2] is not None
        ):
            raise ValueError("CDF constraint frame differs from the reviewed setting")
    calibration_target = target.model_copy(
        update={
            "instance": calibration,
            "netlist_path": witness.netlist_path,
            "netlist_terminals": witness.netlist_terminals,
        }
    )
    _verify_reopened_cdf(cdf, calibration_target, route.after)
    _verify_effective_options(netlist, calibration_target, route.after)


def _observed_bound(row: tuple[object, object, object] | None, expected: str | None) -> bool:
    if expected is None:
        return row == ("missing", None, None)
    return row is not None and row[0] == "observed" and row[2] == expected


@dataclass(frozen=True)
class RetainedMosEdit:
    """A durable native claim. An absent capture represents an unknown outcome."""

    capture: NativeMosEditCapture | None


class RegisteredMosEditProvider(Protocol):
    """C1-owned fixed runner and existing durable store, resolved only by the host."""

    def lookup(self, binding: RegisteredMosEditBinding) -> RetainedMosEdit | None: ...
    def claim(self, binding: RegisteredMosEditBinding) -> bool: ...
    def dispatch(self, binding: RegisteredMosEditBinding) -> RetainedMosEdit: ...


class RegisteredMosEditResult(VariableModel):
    identity: PmosDefaultChangeRequest
    candidate_revision: RevisionBinding
    outcome: Literal["NOT_FOUND", "OUTCOME_UNKNOWN", "VERIFIED"]
    replayed: bool
    dispatched_this_call: bool | None
    readback: NativeMosEditReadback | None = None
    effective_input: NetlistProjection | None = None
    effective_mos_options: dict[str, str] | None = None
    new_simulations: Literal[0] = 0
    new_reservations: Literal[0] = 0
    analysis_execution_authorized: Literal[False] = False


class RegisteredMosEditService:
    """Apply one pinned plan via C1, and verify three OA observations and the Netlist."""

    def __init__(
        self,
        binding: RegisteredMosEditBinding,
        route: RegisteredMosEditRoute,
        child: RevisionBinding,
        requested: MosEditValues,
        baseline_input: bytes,
        provider: RegisteredMosEditProvider,
        *,
        expected_binding_sha256: str,
    ) -> None:
        binding, route = _checked(binding), _checked(route)
        plan = plan_registered_mos_edit(route, child, requested)
        baseline = plan.baseline
        if (
            canonical_digest(binding) != expected_binding_sha256
            or binding.route_sha256 != canonical_digest(route)
            or binding.plan_sha256 != plan.plan_sha256
            or binding.operation_id == binding.owned_copy_operation_id
            or binding.owned_before_view_tree_sha256 == baseline.revision_sha256
            or binding.owned_library in ("gpdk090", "analogLib", "basic")
            or not 0 < len(baseline_input) <= 32768
            or hashlib.sha256(baseline_input).hexdigest() != baseline.netlist_sha256
        ):
            raise ValueError("MOS edit registration, baseline or owned copy mismatch")
        target = route.qualification.target
        options = _verify_effective_options(baseline_input, target, route.before)
        if any(options.get(option.name) != option.before for option in target.options):
            raise ValueError("registered baseline Spectre options differ before dispatch")
        self.plan = plan
        self.identity = PmosDefaultChangeRequest(
            operation_id=binding.operation_id,
            expected_plan_sha256=plan.plan_sha256,
            expected_scope_sha256=binding.scope_sha256,
        )
        self._binding = binding
        self._route = route
        self._baseline_input = baseline_input
        self._provider = provider

    def lookup(self, request: PmosDefaultChangeRequest) -> RegisteredMosEditResult:
        self._check_request(request)
        retained = self._provider.lookup(self._binding)
        if retained is None:
            return RegisteredMosEditResult(
                identity=self.identity,
                candidate_revision=self.plan.candidate_revision,
                outcome="NOT_FOUND",
                replayed=False,
                dispatched_this_call=False,
            )
        return self._result(retained, replayed=True)

    def apply(self, request: PmosDefaultChangeRequest) -> RegisteredMosEditResult:
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

    def _check_request(self, request: PmosDefaultChangeRequest) -> None:
        if _checked(request) != self.identity:
            raise ValueError("MOS edit request conflicts with the approved operation")

    def _result(self, retained: RetainedMosEdit, *, replayed: bool) -> RegisteredMosEditResult:
        if retained.capture is not None:
            try:
                return self._verify_capture(retained.capture, replayed=replayed)
            except ValueError:
                pass
        return RegisteredMosEditResult(
            identity=self.identity,
            candidate_revision=self.plan.candidate_revision,
            outcome="OUTCOME_UNKNOWN",
            replayed=replayed,
            dispatched_this_call=False if replayed else None,
        )

    def _verify_capture(
        self, capture: NativeMosEditCapture, *, replayed: bool
    ) -> RegisteredMosEditResult:
        observed = _checked(capture.readback)
        binding, route = self._binding, self._route
        baseline, saved, reopened = observed.baseline, observed.saved, observed.reopened
        target = route.qualification.target
        if (
            (observed.operation_id, observed.plan_sha256, observed.scope_sha256)
            != (binding.operation_id, binding.plan_sha256, binding.scope_sha256)
            or observed.source_preservation_sha256 != binding.source_preservation_sha256
            or (baseline.stage, saved.stage, reopened.stage) != ("baseline", "saved", "reopened")
            or (baseline.revision_sha256, baseline.testbench_revision_sha256)
            != (binding.owned_before_view_tree_sha256, binding.owned_before_testbench_tree_sha256)
            or saved.revision_sha256
            in (baseline.revision_sha256, self.plan.baseline.revision_sha256)
            or saved.revision_sha256 != reopened.revision_sha256
            or reopened.revision_sha256 != observed.netlisted_revision_sha256
            or saved.testbench_revision_sha256 != reopened.testbench_revision_sha256
            or reopened.testbench_revision_sha256 != observed.netlisted_testbench_revision_sha256
            or not same_saved_testbench(target, baseline, saved)
            or baseline.footprint_sha256 != saved.footprint_sha256
            or saved.footprint_sha256 != reopened.footprint_sha256
            or baseline.properties != route.before
            or saved.properties != route.after
            or reopened.properties != route.after
            or len(
                {
                    baseline.receipt_sha256,
                    saved.receipt_sha256,
                    reopened.receipt_sha256,
                    observed.netlist_receipt_sha256,
                }
            )
            != 4
            or not 0 < len(capture.netlist) <= 32768
            or hashlib.sha256(capture.netlist).hexdigest() != observed.netlist_sha256
            or not 0 < len(capture.cdf_frame) <= 262144
            or hashlib.sha256(capture.cdf_frame).hexdigest() != observed.cdf_frame_sha256
        ):
            raise ValueError("native MOS edit receipts, properties or footprint differ")
        _verify_reopened_cdf(capture.cdf_frame, target, reopened.properties)
        options = _verify_effective_options(capture.netlist, target, reopened.properties)
        return RegisteredMosEditResult(
            identity=self.identity,
            candidate_revision=self.plan.candidate_revision,
            outcome="VERIFIED",
            replayed=replayed,
            dispatched_this_call=not replayed,
            readback=observed,
            effective_mos_options=options,
            effective_input=project_netlist_change(
                self.plan, self._baseline_input, capture.netlist
            ),
        )
