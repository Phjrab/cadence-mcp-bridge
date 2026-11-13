"""Local parameter plans and evidence checks for exact registered targets."""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal, localcontext
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge._native_rendering import partition_input, statements
from cadence_mcp_bridge.candidate_contracts import CandidateSourceTarget, CandidateVariableBinding
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    LogicalId,
    NumberText,
    VariableContract,
    VariableModel,
    canonical_digest,
    number_text,
)

ChangeUnit = Literal["V", "A", "m", "um", "nm", "F", "pF"]
_AMP_PM0_STATEMENT_SHA256 = "52bf48b8d845681d1be3727bbadb20eabd424a24c3c822bbc33e8913e3e274c6"
_AMP_CENTER_SHA256 = "c9bcf3e3bd8a9329ff0bb1513df2a08f8a4f60e314f04075e15a3422c03e4006"

GeometryProperty = Literal["fw", "as", "ad", "ps", "pd"]
_UNIT_SCALE: dict[str, int] = {"m": 0, "um": -6, "nm": -9, "F": 0, "pF": -12}


def _checked[T: VariableModel](value: T) -> T:
    return type(value).model_validate_json(value.model_dump_json(warnings="error"))


class ChangeValue(VariableModel):
    value: NumberText
    unit: ChangeUnit

    @property
    def normalized(self) -> tuple[str, str]:
        value = number_text(self.value)
        if self.unit in ("V", "A"):
            return value, self.unit
        magnitude = Decimal(value)
        is_capacitance = self.unit in ("F", "pF")
        if magnitude <= 0:
            quantity = "capacitance" if is_capacitance else "length"
            raise ValueError(f"{quantity} must be positive")
        with localcontext() as context:
            context.prec = 128
            canonical = number_text(str(magnitude.scaleb(_UNIT_SCALE[self.unit])))
        return canonical, "F" if is_capacitance else "m"

    @model_validator(mode="after")
    def valid_value(self) -> Self:
        _ = self.normalized
        return self


class ChangeBaseline(VariableModel):
    revision: RevisionBinding
    revision_sha256: Digest
    testbench_revision_sha256: Digest
    fixed_conditions_sha256: Digest
    netlist_sha256: Digest


class AdeTarget(VariableModel):
    kind: Literal["ade_variable"] = "ade_variable"
    binding: CandidateVariableBinding


class MosWidthTarget(VariableModel):
    """One reviewed schematic master; the exact hierarchical target is registered."""

    kind: Literal["schematic_mos_width"] = "schematic_mos_width"
    instance: CandidateSourceTarget

    @model_validator(mode="after")
    def observed_master_and_property(self) -> Self:
        instance = self.instance
        if (
            instance.master_library,
            instance.master_cell,
            instance.master_view,
            instance.property_name,
        ) != ("gpdk090", "pmos1v", "symbol", "w"):
            raise ValueError("only the observed gpdk090 pmos1v schematic width route is supported")
        return self


class CapacitorTarget(VariableModel):
    """The observed top-level load in the owned inverter testbench."""

    kind: Literal["schematic_load_capacitance"] = "schematic_load_capacitance"
    instance: CandidateSourceTarget

    @model_validator(mode="after")
    def exact_load(self) -> Self:
        instance = self.instance
        if (
            instance.instance_path,
            instance.master_library,
            instance.master_cell,
            instance.master_view,
            instance.property_name,
        ) != ("CL", "analogLib", "cap", "symbol", "c"):
            raise ValueError("only the observed analogLib cap CL c target is supported")
        return self


class DerivedValue(VariableModel):
    property_name: GeometryProperty
    value: Annotated[
        str, Field(pattern=r"^[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,2})?[afpnum]?$", max_length=32)
    ]


class DerivedChange(VariableModel):
    before: DerivedValue
    after: DerivedValue

    @model_validator(mode="after")
    def same_property(self) -> Self:
        if self.before.property_name != self.after.property_name:
            raise ValueError("derived change must identify a single property")
        return self


class MosWidthQualification(VariableModel):
    """A registered transition for one single-finger instance on one baseline."""

    baseline: ChangeBaseline
    target: MosWidthTarget
    old: ChangeValue
    expected: ChangeValue
    fingers: Annotated[int, Field(ge=1, le=1)]
    multiplicity: Annotated[int, Field(ge=1, le=1)]
    cdf_evidence_sha256: Digest
    legal_value_evidence_sha256: Digest
    update_route_evidence_sha256: Digest
    derived: Annotated[tuple[DerivedChange, ...], Field(min_length=1, max_length=5)]

    @model_validator(mode="after")
    def observed_geometry(self) -> Self:
        names = tuple(change.before.property_name for change in self.derived)
        if len(set(names)) != len(names) or "fw" not in names:
            raise ValueError("unique qualified geometry projections including fw are required")
        if (
            self.old.normalized[1] != "m"
            or self.expected.normalized[1] != "m"
            or self.old.normalized == self.expected.normalized
        ):
            raise ValueError("qualified width transition must change a length")
        fw = self.derived[names.index("fw")]
        for value, width in ((fw.before, self.old), (fw.after, self.expected)):
            if self.target.instance.instance_path == "PM0" and value.value.endswith("u"):
                observed_width = ChangeValue(value=value.value[:-1], unit="um")
            elif value.value.endswith("n"):
                observed_width = ChangeValue(value=value.value[:-1], unit="nm")
            else:
                raise ValueError("the qualified fw observation must use explicit nm")
            if observed_width.normalized != width.normalized:
                raise ValueError("observed single-finger w and fw differ")
        return self


class CapacitorQualification(VariableModel):
    """One operator-reviewed transition. No production value is registered here."""

    baseline: ChangeBaseline
    target: CapacitorTarget
    old: ChangeValue
    expected: ChangeValue
    cdf_evidence_sha256: Digest
    legal_value_evidence_sha256: Digest
    update_route_evidence_sha256: Digest

    @model_validator(mode="after")
    def observed_load(self) -> Self:
        one_pf = ("0.000000000001", "F")
        if (
            self.old.normalized != one_pf
            or self.expected.normalized[1] != "F"
            or self.expected.normalized == one_pf
        ):
            raise ValueError("capacitor qualification requires a finite change from the 1 pF load")
        return self


class ChangePlan(VariableModel):
    baseline: ChangeBaseline
    candidate_id: LogicalId
    candidate_revision: RevisionBinding
    target: Annotated[AdeTarget | MosWidthTarget | CapacitorTarget, Field(discriminator="kind")]
    old: ChangeValue
    requested: ChangeValue
    expected: ChangeValue
    qualification_sha256: Digest
    allowed_derived: Annotated[tuple[DerivedChange, ...], Field(max_length=5)] = ()

    @model_validator(mode="after")
    def exact_parent_and_change(self) -> Self:
        baseline, candidate = self.baseline.revision, self.candidate_revision
        if (
            candidate.workspace_id != baseline.workspace_id
            or candidate.design_id != baseline.design_id
            or candidate.source_baseline_sha256 != baseline.source_baseline_sha256
            or candidate.parent_revision_id != baseline.revision_id
            or candidate.parent_revision_sha256 != self.baseline.revision_sha256
            or candidate.revision_id == baseline.revision_id
        ):
            raise ValueError("candidate must be a fresh child of the exact baseline")
        if (
            self.requested.normalized != self.expected.normalized
            or self.old.normalized[1] != self.expected.normalized[1]
            or self.old.normalized == self.expected.normalized
        ):
            raise ValueError("incoherent requested, previous or expected value")
        if isinstance(self.target, AdeTarget):
            if self.old.unit not in ("V", "A") or self.allowed_derived:
                raise ValueError("ADE change must be a registered V/A scalar")
        elif isinstance(self.target, CapacitorTarget):
            if self.old.normalized != ("0.000000000001", "F") or self.allowed_derived:
                raise ValueError("capacitor change must start from the observed 1 pF load")
        elif self.old.normalized[1] != "m" or not self.allowed_derived:
            raise ValueError("MOS width change requires a qualified geometry transition")
        return self

    @property
    def plan_sha256(self) -> str:
        return canonical_digest(self)


def plan_ade_change(
    baseline: ChangeBaseline,
    candidate_id: str,
    candidate_revision: RevisionBinding,
    contract: VariableContract,
    binding: CandidateVariableBinding,
    old: ChangeValue,
    requested: ChangeValue,
) -> ChangePlan:
    baseline = _checked(baseline)
    candidate_revision = _checked(candidate_revision)
    contract = _checked(contract)
    binding = _checked(binding)
    old = _checked(old)
    requested = _checked(requested)
    if (
        contract.mutation_policy != "owned_copy_only"
        or contract.logical_id != binding.logical_id
        or contract.cadence_binding != binding.cadence_binding
        or contract.unit not in ("V", "A")
        or old.unit != contract.unit
        or requested.unit != contract.unit
        or contract.check_number(old.normalized[0]) is not None
        or contract.check_number(requested.normalized[0]) is not None
    ):
        raise ValueError("registered ADE variable or reviewed numeric contract mismatch")
    return ChangePlan(
        baseline=baseline,
        candidate_id=candidate_id,
        candidate_revision=candidate_revision,
        target=AdeTarget(binding=binding),
        old=old,
        requested=requested,
        expected=requested,
        qualification_sha256=canonical_digest(contract),
    )


def plan_mos_width_change(
    qualification: MosWidthQualification,
    candidate_id: str,
    candidate_revision: RevisionBinding,
    requested: ChangeValue,
) -> ChangePlan:
    qualification = _checked(qualification)
    candidate_revision = _checked(candidate_revision)
    requested = _checked(requested)
    if requested.normalized != qualification.expected.normalized:
        raise ValueError("width is outside the qualified finite transition")
    return ChangePlan(
        baseline=qualification.baseline,
        candidate_id=candidate_id,
        candidate_revision=candidate_revision,
        target=qualification.target,
        old=qualification.old,
        requested=requested,
        expected=qualification.expected,
        qualification_sha256=canonical_digest(qualification),
        allowed_derived=qualification.derived,
    )


def plan_capacitor_change(
    qualification: CapacitorQualification,
    candidate_id: str,
    candidate_revision: RevisionBinding,
    requested: ChangeValue,
) -> ChangePlan:
    qualification = _checked(qualification)
    candidate_revision = _checked(candidate_revision)
    requested = _checked(requested)
    if requested.normalized != qualification.expected.normalized:
        raise ValueError("capacitance is outside the qualified finite transition")
    return ChangePlan(
        baseline=qualification.baseline,
        candidate_id=candidate_id,
        candidate_revision=candidate_revision,
        target=qualification.target,
        old=qualification.old,
        requested=requested,
        expected=qualification.expected,
        qualification_sha256=canonical_digest(qualification),
    )


class NetlistProjection(VariableModel):
    artifact_sha256: Digest
    value: ChangeValue
    derived: tuple[DerivedValue, ...] = ()


def _width_options(statements: list[str], path: str) -> tuple[list[str], dict[str, str]]:
    parts = path.split("/")
    if len(parts) != 2:
        raise ValueError(
            "MOS netlist binding requires the registered DUT instance and MOS instance"
        )
    dut, device = parts
    scopes: list[str] = []
    masters: list[str] = []
    instances: list[tuple[str, int, str]] = []
    for index, line in enumerate(statements):
        words = line.split()
        opening = words[1:] if words[0] == "inline" else words
        if opening and opening[0] == "subckt":
            scopes.append(opening[1])
        elif words[0] == "ends":
            scopes.pop()
        elif not scopes and words[0] == dut:
            match = re.fullmatch(r"[^ ]+ \([^()]+\) ([A-Za-z][A-Za-z0-9_#-]*)", line)
            if match is None:
                raise ValueError("unsupported DUT netlist binding")
            masters.append(match[1])
        elif len(scopes) == 1 and words[0] == device:
            instances.append((scopes[0], index, line))
    if len(masters) != 1:
        raise ValueError("DUT netlist binding is missing or ambiguous")
    matches = [(index, line) for scope, index, line in instances if scope == masters[0]]
    if len(matches) != 1:
        raise ValueError("MOS netlist instance is missing or ambiguous")
    return _split_mos_options(statements, *matches[0])


def _split_mos_options(
    statements: list[str], index: int, line: str
) -> tuple[list[str], dict[str, str]]:
    match = re.fullmatch(r"([^ ]+ \([^()]+\) [^ ]+) (.+)", line)
    if match is None:
        raise ValueError("unsupported MOS netlist statement")
    options: dict[str, str] = {}
    for token in match[2].split():
        name, separator, value = token.partition("=")
        if not separator or not name or not value or name in options:
            raise ValueError("invalid or duplicate MOS netlist option")
        options[name] = value
    fixed = statements.copy()
    fixed[index] = match[1]
    return fixed, options


def _amp_pm0_options(statements: list[str], *, baseline: bool) -> tuple[list[str], dict[str, str]]:
    depth = 0
    matches: list[tuple[int, str]] = []
    for index, line in enumerate(statements):
        if line.startswith(("subckt ", "inline subckt ")):
            depth += 1
        elif line == "ends" or line.startswith("ends "):
            depth -= 1
        elif line.split(" ", 1)[0] == "PM0":
            if depth or not line.startswith("PM0 (net33 Vbiasp VDD VDD) gpdk090_pmos1v "):
                raise ValueError("unsupported amplifier PM0 netlist binding")
            matches.append((index, line))
    if len(matches) != 1:
        raise ValueError("amplifier PM0 is missing or ambiguous")
    index, line = matches[0]
    if baseline and hashlib.sha256(line.encode("ascii")).hexdigest() != _AMP_PM0_STATEMENT_SHA256:
        raise ValueError("amplifier PM0 baseline statement mismatch")
    fixed, options = _split_mos_options(statements, index, line)
    if options.get("l") != "1u":
        raise ValueError("amplifier PM0 length must remain 1u")
    return fixed, options


def _netlist_width(options: dict[str, str], *, amplifier: bool = False) -> ChangeValue:
    if options.get("m") != "(1)*(1)" or options.get("simM") != "(1)*(1)":
        raise ValueError("unsupported effective MOS multiplicity expression")
    token = options.pop("w", "")
    if amplifier and token.startswith("(") and token.endswith("u)"):
        return ChangeValue(value=token[1:-2], unit="um")
    if not (token.startswith("(") and token.endswith("n)")):
        raise ValueError("unsupported effective width expression")
    return ChangeValue(value=token[1:-2], unit="nm")


def _load_capacitance(statements: list[str]) -> tuple[list[str], ChangeValue]:
    """Read the sole top-level CL in the observed Spectre form."""
    depth = 0
    matches: list[tuple[int, str]] = []
    for index, line in enumerate(statements):
        if line.startswith(("subckt ", "inline subckt ")):
            depth += 1
        elif line == "ends" or line.startswith("ends "):
            depth -= 1
        elif line.startswith("CL "):
            match = re.fullmatch(r"CL \(vout 0\) capacitor c=([0-9]+(?:\.[0-9]+)?)p", line)
            if depth != 0 or match is None:
                raise ValueError("unsupported CL capacitor statement")
            matches.append((index, match[1]))
    if len(matches) != 1:
        raise ValueError("CL capacitor is missing or ambiguous")
    index, value = matches[0]
    fixed = statements.copy()
    fixed[index] = "CL (vout 0) capacitor"
    return fixed, ChangeValue(value=value, unit="pF")


# The source9 inverter testbench has four independent instance declarations.
# Keep their exact syntax, connectivity, and values when admitting a permutation.
_INVERTER_BENCH_INSTANCES = frozenset(
    {
        "DUT (vdd vin vout 0) InvLong",
        "VDD (vdd 0) vsource dc=1 type=dc",
        "VIN (vin 0) vsource dc=m2_vin type=pulse val0=0 val1=1 period=150n "
        "delay=10n rise=100p fall=100p width=65n",
        "CL (vout 0) capacitor c=1p",
    }
)


def _inverter_bench_block(lines: list[str]) -> tuple[int, int] | None:
    depth = 0
    indexes: list[int] = []
    identifiers: set[str] = set()
    for index, line in enumerate(lines):
        if line.startswith(("subckt ", "inline subckt ")):
            depth += 1
        elif line == "ends" or line.startswith("ends "):
            depth -= 1
        elif depth == 0 and (name := line.split(" ", 1)[0]) in ("DUT", "VDD", "VIN", "CL"):
            if name in identifiers or line not in _INVERTER_BENCH_INSTANCES:
                return None
            identifiers.add(name)
            indexes.append(index)
    if len(indexes) == 4 and indexes[-1] - indexes[0] == 3:
        return indexes[0], indexes[-1] + 1
    return None


def _same_inverter_bench_with_reordered_instances(
    old_static: list[str], new_static: list[str], old_input: bytes, new_input: bytes
) -> bool:
    # Compare blocks in the raw statement sequence too. The partitioned static
    # sequence omits include, parameters and analysis statements.
    old_raw: list[str] = statements(old_input)  # type: ignore[no-untyped-call]
    new_raw: list[str] = statements(new_input)  # type: ignore[no-untyped-call]
    raw_block = _inverter_bench_block(old_raw)
    static_block = _inverter_bench_block(old_static)
    if (
        raw_block is None
        or raw_block != _inverter_bench_block(new_raw)
        or static_block is None
        or static_block != _inverter_bench_block(new_static)
    ):
        return False
    # Control placement must agree even though the MP value may differ.
    controls = re.compile(r"^(?:include |parameters |[A-Za-z][A-Za-z0-9_]* (?:dc|ac|tran)(?: |$))")
    if len(old_raw) != len(new_raw) or any(
        a != b and (controls.match(a) or controls.match(b))
        for a, b in zip(old_raw, new_raw, strict=True)
    ):
        return False
    first, last = static_block
    return old_static[:first] == new_static[:first] and old_static[last:] == new_static[last:]


def project_netlist_change(
    plan: ChangePlan, baseline_input: bytes, candidate_input: bytes
) -> NetlistProjection:
    """Extract effective values from actual inputs and compare the allowed delta.

    Input provenance and model-file bytes are checked by the native caller.
    """
    plan = _checked(plan)
    if hashlib.sha256(baseline_input).hexdigest() != plan.baseline.netlist_sha256:
        raise ValueError("baseline netlist digest mismatch")
    old_params, old_includes, old_analyses, old_static = partition_input(baseline_input)  # type: ignore[no-untyped-call]
    new_params, new_includes, new_analyses, new_static = partition_input(candidate_input)  # type: ignore[no-untyped-call]
    if old_includes != new_includes or old_analyses != new_analyses:
        raise ValueError("model includes or analysis settings changed")

    derived: tuple[DerivedValue, ...] = ()
    if isinstance(plan.target, AdeTarget):
        name = plan.target.binding.cadence_binding
        unit = plan.old.unit
        old = ChangeValue(value=old_params.pop(name, ""), unit=unit)
        observed = ChangeValue(value=new_params.pop(name, ""), unit=unit)
    elif isinstance(plan.target, CapacitorTarget):
        old_static, old = _load_capacitance(old_static)
        new_static, observed = _load_capacitance(new_static)
    else:
        instance_path = plan.target.instance.instance_path
        amplifier = instance_path == "PM0"
        if amplifier:
            revision = plan.baseline.revision
            if (
                revision.design_id != "reference-differential-amplifier-tb2"
                or revision.revision_id != "reference-amplifier-bias-grid-v1"
                or plan.baseline.netlist_sha256 != _AMP_CENTER_SHA256
            ):
                raise ValueError("amplifier PM0 requires the registered center DC baseline")
            old_static, old_options = _amp_pm0_options(old_static, baseline=True)
            new_static, new_options = _amp_pm0_options(new_static, baseline=False)
        else:
            old_static, old_options = _width_options(old_static, instance_path)
            new_static, new_options = _width_options(new_static, instance_path)
        old = _netlist_width(old_options, amplifier=amplifier)
        observed = _netlist_width(new_options, amplifier=amplifier)
        geometry = [
            change for change in plan.allowed_derived if change.before.property_name != "fw"
        ]
        values = []
        for change in geometry:
            name = change.before.property_name
            previous = DerivedValue(property_name=name, value=old_options.pop(name, ""))
            current = DerivedValue(property_name=name, value=new_options.pop(name, ""))
            if (previous, current) != (change.before, change.after):
                raise ValueError("derived MOS netlist geometry differs from qualification")
            values.append(current)
        if old_options != new_options:
            raise ValueError("fixed MOS netlist options changed")
        derived = tuple(values)
    if old_params != new_params or (
        old_static != new_static
        and not (
            isinstance(plan.target, MosWidthTarget)
            and plan.target.instance.instance_path != "PM0"
            and _same_inverter_bench_with_reordered_instances(
                old_static, new_static, baseline_input, candidate_input
            )
        )
    ):
        raise ValueError("fixed netlist parameters or topology changed")
    if old.normalized != plan.old.normalized or observed.normalized != plan.expected.normalized:
        raise ValueError("effective netlist value differs from plan")
    return NetlistProjection(
        artifact_sha256=hashlib.sha256(candidate_input).hexdigest(),
        value=observed,
        derived=derived,
    )


class Readback(VariableModel):
    """Value projected by an observer from its own artifact; hashes identify the capture."""

    stage: Literal["baseline", "reopened", "netlist"]
    plan_sha256: Digest
    target_sha256: Digest
    revision: RevisionBinding
    revision_sha256: Digest
    testbench_revision_sha256: Digest
    fixed_conditions_sha256: Digest
    artifact_sha256: Digest
    value: ChangeValue
    derived: Annotated[tuple[DerivedValue, ...], Field(max_length=5)] = ()
    mos_fingers: Annotated[int, Field(ge=1, le=1)] | None = None
    mos_multiplicity: Annotated[int, Field(ge=1, le=1)] | None = None

    @model_validator(mode="after")
    def distinct_properties(self) -> Self:
        if len({value.property_name for value in self.derived}) != len(self.derived):
            raise ValueError("readback contains duplicate derived properties")
        return self


class ChangeReadback(VariableModel):
    plan_sha256: Digest
    status: Literal["MISSING", "STALE", "CONFLICT", "MATCHED"]
    reason: str
    baseline: Readback | None
    reopened: Readback | None
    netlist: Readback | None
    provenance: Literal["LOCAL_EVIDENCE_COMPARISON"] = "LOCAL_EVIDENCE_COMPARISON"
    execution_authorized: Literal[False] = False


def verify_change_readback(
    plan: ChangePlan,
    *,
    baseline: Readback | None = None,
    reopened: Readback | None = None,
    netlist: Readback | None = None,
) -> ChangeReadback:
    """Compare projected values. Authentication and execution admission stay with C1."""
    plan = _checked(plan)
    baseline = None if baseline is None else _checked(baseline)
    reopened = None if reopened is None else _checked(reopened)
    netlist = None if netlist is None else _checked(netlist)
    status, reason = _check_readback(plan, baseline, reopened, netlist)
    return ChangeReadback(
        plan_sha256=plan.plan_sha256,
        status=status,
        reason=reason,
        baseline=baseline,
        reopened=reopened,
        netlist=netlist,
    )


def _check_readback(
    plan: ChangePlan,
    baseline: Readback | None,
    reopened: Readback | None,
    netlist: Readback | None,
) -> tuple[Literal["MISSING", "STALE", "CONFLICT", "MATCHED"], str]:
    reference = plan.baseline
    for stage, row in (("baseline", baseline), ("reopened", reopened), ("netlist", netlist)):
        if row is None:
            continue
        is_baseline = stage == "baseline"
        revision = reference.revision if is_baseline else plan.candidate_revision
        if (
            row.stage != stage
            or row.plan_sha256 != plan.plan_sha256
            or row.target_sha256 != canonical_digest(plan.target)
            or row.revision != revision
            or (row.revision_sha256 == reference.revision_sha256) != is_baseline
            or (
                is_baseline and row.testbench_revision_sha256 != reference.testbench_revision_sha256
            )
        ):
            return "STALE", f"{stage}_binding_mismatch"
        if row.fixed_conditions_sha256 != reference.fixed_conditions_sha256:
            return "CONFLICT", f"{stage}_fixed_conditions_changed"
        expected = plan.old if is_baseline else plan.expected
        if row.value.normalized != expected.normalized:
            return "CONFLICT", f"{stage}_value_mismatch"
        observed_mos_counts = (row.mos_fingers, row.mos_multiplicity)
        expected_mos_counts = (
            (1, 1)
            if isinstance(plan.target, MosWidthTarget) and stage != "netlist"
            else (None, None)
        )
        if observed_mos_counts != expected_mos_counts:
            return "CONFLICT", f"{stage}_mos_shape_mismatch"
        # The simulator exposes the effective width, not the OA fw property.
        # Other allowed geometry projections still need their own netlist values.
        derived = {
            change.before.property_name: (change.before if is_baseline else change.after).value
            for change in plan.allowed_derived
            if stage != "netlist" or change.before.property_name != "fw"
        }
        if {value.property_name: value.value for value in row.derived} != derived:
            return "CONFLICT", f"{stage}_derived_values_mismatch"
    if baseline is None or reopened is None or netlist is None:
        return "MISSING", "baseline_reopened_and_netlist_readbacks_required"
    if (
        reopened.revision_sha256 != netlist.revision_sha256
        or reopened.testbench_revision_sha256 != netlist.testbench_revision_sha256
    ):
        return "STALE", "reopened_and_netlist_revisions_differ"
    if (
        isinstance(plan.target, CapacitorTarget)
        and reopened.testbench_revision_sha256 == reference.testbench_revision_sha256
    ):
        return "STALE", "capacitor_testbench_revision_reuses_baseline"
    if len({baseline.artifact_sha256, reopened.artifact_sha256, netlist.artifact_sha256}) != 3:
        return "CONFLICT", "independent_readback_artifacts_required"
    return "MATCHED", "local_projections_match"
