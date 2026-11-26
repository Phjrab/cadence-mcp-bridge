"""Bind reviewed P4 readbacks to the existing OTA StaticDraftPort, offline."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from cadence_mcp_bridge.domain_provisioning import _closed_document
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.parameter_changes import mos_multiplicity_factors
from cadence_mcp_bridge.registered_mos_edit import _verify_reopened_cdf
from cadence_mcp_bridge.registered_mos_sizing import (
    MosSizingDimensions,
    MosSizingPlan,
    RegisteredMosSizingResult,
    _check_input,
    _engineering,
    _observed_dimensions,
)
from cadence_mcp_bridge.research_circuit import Evidence
from cadence_mcp_bridge.research_draft import DevicePort, StaticDraftPort, compile_research_draft
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel

GeometryKey = tuple[str, Decimal, Decimal, Decimal, int, int]
FIXTURE_SLOTS = {
    "p4-n01": ("CalN01", "nmos1v", 1000, 250, 1),
    "p4-n03": ("CalN03", "nmos1v", 10000, 250, 1),
    "p4-n04": ("CalN04", "nmos1v", 15000, 250, 1),
    "p4-p02": ("CalP02", "pmos1v", 30000, 250, 1),
    "p4-p03": ("CalP03", "pmos1v", 10000, 1000, 1),
    "p4-p04": ("CalP04", "pmos1v", 16000, 1000, 6),
}
FIXTURE_TARGETS: set[GeometryKey] = {
    (master, Decimal(w).scaleb(-9), Decimal(w).scaleb(-9), Decimal(l).scaleb(-9), m, 1)
    for _, master, w, l, m in FIXTURE_SLOTS.values()
}


class Artifact(VariableModel):
    path: Path
    sha256: Digest

    def read(self, root: Path, limit: int = 262_144) -> bytes:
        path = (root / self.path).resolve()
        if self.path.is_absolute() or not path.is_relative_to(root):
            raise ValueError("evidence paths must stay relative to the manifest directory")
        return read_pinned(path, self.sha256, limit)


class PointEvidence(VariableModel):
    plan: Artifact
    lookup_result: Artifact
    cdf: Artifact
    netlist: Artifact


class ReviewedEvidence(VariableModel):
    points: Annotated[tuple[PointEvidence, ...], Field(max_length=2)] = ()
    fixture_report: Artifact | None = None


class FixturePointPins(VariableModel):
    properties_sha256: Digest
    cdf_sha256: Digest


class FixturePoint(VariableModel):
    instance: str
    master: Literal["nmos1v", "pmos1v"]
    terminals: tuple[str, str, str, str]
    observed: MosSizingDimensions
    fingers: Literal[1]
    netlist_options: dict[str, str]
    original_point_pins: tuple[FixturePointPins, FixturePointPins, FixturePointPins]


class FixtureReport(VariableModel):
    schema_version: Literal[1]
    status: Literal["VERIFIED_FIXTURE_TUPLES"]
    evidence_index_sha256: Digest
    operation_id: OperationId
    scope_sha256: Digest
    receipts: dict[Literal["setup", "save", "reopen-netlist"], Digest]
    fixture_library: str
    dut_revision_sha256: Digest
    testbench_revision_sha256: Digest
    netlist_sha256: Digest
    points: dict[str, FixturePoint]


def fixture_points(
    root: Path, artifact: Artifact
) -> tuple[OperationId, dict[GeometryKey, tuple[Evidence, Evidence]]]:
    """Consume the independently pinned output of C6's original-receipt verifier."""
    raw = artifact.read(root)
    _closed_document(raw)
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("status") != "VERIFIED_FIXTURE_TUPLES":
        raise ValueError("expected VERIFIED_FIXTURE_TUPLES from the C6 original-evidence verifier")
    report = FixtureReport.model_validate_json(raw)
    if (
        set(report.receipts) != {"setup", "save", "reopen-netlist"}
        or len(set(report.receipts.values())) != 3
        or report.points.keys() != FIXTURE_SLOTS.keys()
    ):
        raise ValueError("incomplete C6 fixture report")
    rows = document["points"]
    result = {}
    for point_id, row in report.points.items():
        slot, master, width_nm, length_nm, count = FIXTURE_SLOTS[point_id]
        width, length = Decimal(width_nm).scaleb(-9), Decimal(length_nm).scaleb(-9)
        rail = "vss" if master == "nmos1v" else "vdd"
        options = row.netlist_options
        if (
            (row.instance, row.master, row.observed.m) != (slot, master, count)
            or row.terminals != ("vout", "vin", rail, rail)
            or _engineering(row.observed.w.normalized[0]) != width
            or _engineering(row.observed.l.normalized[0]) != length
            or set(options) != {"w", "l", "m", "simM", "as", "ad", "ps", "pd"}
            or (_engineering(options["w"]), _engineering(options["l"])) != (width, length)
            or any(mos_multiplicity_factors(options[key]) != (str(count), "1") for key in ("m", "simM"))
        ):
            raise ValueError(f"{point_id}: C6 fixture row differs from the approved target")
        row_bytes = json.dumps(
            rows[point_id], sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
        reference = f"Reviewed non-OTA P4 fixture {report.operation_id} / {slot} ({point_id})"
        result[(master, width, width, length, count, 1)] = (
            Evidence(
                reference=f"{reference}: C6 verified row",
                status="confirmed",
                sha256=sha256(row_bytes).hexdigest(),
            ),
            Evidence(
                reference=f"{reference}: independent Spectre input",
                status="confirmed",
                sha256=report.netlist_sha256,
            ),
        )
    return report.operation_id, result


def read_pinned(path: Path, pin: str, limit: int = 262_144) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if not 0 < len(raw) <= limit or sha256(raw).hexdigest() != pin:
        raise ValueError(f"{path.name}: size or SHA-256 mismatch")
    return raw


def target_key(device: DevicePort) -> GeometryKey:
    geometry, spectre = device.geometry, device.spectre
    key = (
        device.master.cell,
        geometry.w.metres(),
        geometry.fw.metres(),
        geometry.length.metres(),
        geometry.multiplier,
        geometry.fingers,
    )
    if (
        device.master.library != "gpdk090"
        or device.master.view != "symbol"
        or device.master.cell != f"{device.kind}1v"
        or key[1] != key[2]
        or key[-1] != 1
        or geometry.width_meaning != "total_width"
        or spectre.model != f"gpdk090_{device.master.cell}"
        or (spectre.width.metres(), spectre.length.metres(), spectre.multiplier)
        != (key[2], key[3], key[4])
    ):
        raise ValueError(f"{device.name}: inconsistent single-finger OTA target")
    return key


def reviewed_point(root: Path, point: PointEvidence) -> tuple[GeometryKey, str]:
    plan_raw = point.plan.read(root)
    result_raw = point.lookup_result.read(root)
    _closed_document(plan_raw)
    _closed_document(result_raw)
    plan = MosSizingPlan.model_validate_json(plan_raw)
    result = RegisteredMosSizingResult.model_validate_json(result_raw)
    readback, projection = result.readback, result.effective_input
    if (
        result.outcome != "VERIFIED"
        or not result.replayed
        or result.dispatched_this_call is not False
        or readback is None
        or projection is None
        or result.observed is None
        or result.observed.m is None
    ):
        raise ValueError("P4 point requires a VERIFIED W/L/m lookup without dispatch")
    if (
        result.identity.operation_id != readback.operation_id
        or result.identity.expected_plan_sha256 != plan.plan_sha256
        or readback.plan_sha256 != plan.plan_sha256
        or readback.scope_sha256 != result.identity.expected_scope_sha256
        or result.candidate_revision != plan.candidate_revision
        or result.requested != plan.requested
        or result.expected != plan.expected
        or result.observed != plan.expected
        or readback.cdf_frame_sha256 != point.cdf.sha256
        or readback.netlist_sha256 != point.netlist.sha256
        or projection.artifact_sha256 != point.netlist.sha256
    ):
        raise ValueError("P4 plan, readback or source digest mismatch")
    saved, reopened = readback.saved, readback.reopened
    if (
        (readback.baseline.stage, saved.stage, reopened.stage) != ("baseline", "saved", "reopened")
        or saved.revision_sha256 != reopened.revision_sha256
        or saved.testbench_revision_sha256 != reopened.testbench_revision_sha256
        or reopened.revision_sha256 != readback.netlisted_revision_sha256
        or reopened.testbench_revision_sha256 != readback.netlisted_testbench_revision_sha256
        or saved.properties != reopened.properties
        or saved.footprint_sha256 != reopened.footprint_sha256
        or len(
            {
                readback.baseline.receipt_sha256,
                saved.receipt_sha256,
                reopened.receipt_sha256,
                readback.netlist_receipt_sha256,
            }
        ) != 4
    ):
        raise ValueError("P4 save, independent reopen and netlist revisions disagree")

    properties = reopened.properties
    if _observed_dimensions(properties, include_m=True) != result.observed:
        raise ValueError("P4 observed dimensions differ from reopened values")
    _verify_reopened_cdf(
        point.cdf.read(root),
        plan.target,
        properties,
        compare_widths=lambda total, finger: _engineering(total) == _engineering(finger),
    )
    _, _, options = _check_input(plan.target, point.netlist.read(root, 32_768), properties)
    if options != result.effective_mos_options:
        raise ValueError("P4 retained MOS options differ from the original Spectre input")
    key = (
        plan.target.instance.master_cell,
        _engineering(properties["w"].cdf_value),
        _engineering(properties["fw"].cdf_value),
        _engineering(properties["l"].cdf_value),
        result.observed.m,
        1,
    )
    return key, result.identity.operation_id


def bind(
    draft: bytes, port_raw: bytes, manifest: ReviewedEvidence, root: Path
) -> tuple[bytes, dict[str, object]]:
    compile_research_draft(draft, port_raw, static_preview=True)
    port = StaticDraftPort.model_validate_json(port_raw)
    keys = {device.name: target_key(device) for device in port.devices}
    targets = set(keys.values())
    paper = json.loads(draft, parse_float=Decimal)
    if port.topology_source.sha256 != paper["source"]["pdf_sha256"]:
        raise ValueError("OTA topology source differs from the pinned paper")
    for device in paper["design"]["devices"]:
        geometry = device["dimensions_candidate"]
        _, width, _, length, multiplier, _ = keys[device["name"]]
        paper_key = (
            Decimal(geometry["W"]).scaleb(-6),
            Decimal(geometry["L"]).scaleb(-6),
            geometry["multiplier"],
        )
        if geometry["unit"] != "um" or (width, length, multiplier) != paper_key:
            raise ValueError(f"{device['name']}: port geometry differs from the declared OTA target")
        bulk = "VSS" if device["device_kind_candidate"] == "nmos" else "VDD"
        if device["terminals"]["B"] != bulk:
            raise ValueError(f"{device['name']}: draft differs from the selected bulk convention")
    if len(port.devices) != 17 or len(targets) != 8 or any(
        "confirmed" in (device.geometry.source.status, device.spectre.source.status)
        for device in port.devices
    ):
        raise ValueError("expected an unpromoted 17-device OTA port with eight targets")
    if len({point.lookup_result.sha256 for point in manifest.points}) != len(manifest.points):
        raise ValueError("duplicate P4 lookup result")

    by_target: dict[GeometryKey, tuple[Evidence, Evidence]] = {}
    operations = set()
    if manifest.fixture_report is not None:
        batch, by_target = fixture_points(root, manifest.fixture_report)
        if not by_target.keys() <= targets:
            raise ValueError("C6 fixture report contains a target outside the OTA port")
        operations.add(batch)
    for point in manifest.points:
        key, operation = reviewed_point(root, point)
        if key not in targets:
            raise ValueError("P4 readback does not match an OTA target")
        if key in FIXTURE_TARGETS:
            raise ValueError("this P4 target requires the common fixture report")
        if key in by_target or operation in operations:
            raise ValueError("duplicate P4 target or operation")
        by_target[key] = (
            Evidence(
                reference="Reviewed non-OTA P4 lookup: saved and independently reopened OA/CDF",
                status="confirmed",
                sha256=point.lookup_result.sha256,
            ),
            Evidence(
                reference="Reviewed non-OTA P4 independent Spectre netlist",
                status="confirmed",
                sha256=point.netlist.sha256,
            ),
        )
        operations.add(operation)

    devices = []
    missing = []
    for device in port.devices:
        evidence = by_target.get(keys[device.name])
        if evidence is None:
            missing.append(device.name)
            devices.append(device)
            continue
        geometry_source, spectre_source = evidence
        devices.append(
            device.model_copy(
                update={
                    "geometry": device.geometry.model_copy(update={"source": geometry_source}),
                    "spectre": device.spectre.model_copy(update={"source": spectre_source}),
                }
            )
        )
    updated = port.model_copy(update={"devices": tuple(devices)})
    raw = updated.model_dump_json(indent=2).encode("utf-8") + b"\n"
    compile_research_draft(draft, raw, static_preview=True)
    return raw, {
        "qualified_targets": len(by_target),
        "total_targets": len(targets),
        "unbound_devices": missing,
        "execution_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", nargs=2, required=True, metavar=("FILE", "SHA256"))
    parser.add_argument("--port", nargs=2, required=True, metavar=("FILE", "SHA256"))
    parser.add_argument("--reviewed", nargs=2, required=True, metavar=("MANIFEST", "SHA256"))
    parser.add_argument("--output", type=Path, help="New static port file. Omit for status only.")
    args = parser.parse_args()
    reviewed = Path(args.reviewed[0]).resolve()
    manifest_raw = read_pinned(reviewed, args.reviewed[1])
    _closed_document(manifest_raw)
    raw, summary = bind(
        read_pinned(Path(args.draft[0]), args.draft[1]),
        read_pinned(Path(args.port[0]), args.port[1]),
        ReviewedEvidence.model_validate_json(manifest_raw),
        reviewed.parent,
    )
    if args.output is not None:
        with args.output.open("xb") as stream:
            stream.write(raw)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
