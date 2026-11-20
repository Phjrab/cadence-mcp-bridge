"""Bounded research projections over retained operating-point and transfer data."""

import hashlib
import json
import math

import pytest
from test_result_reports import configured, operator, operator_base, seed

from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.research_measurements import (
    AcGainDefinition,
    DeviceOpQuery,
    DeviceOpRegistration,
    DeviceOpSourceBinding,
    capture_device_operating_points,
    parse_device_op_frame,
    project_device_operating_points,
    render_device_op_reads,
    sampled_ac_gain,
    static_supply_power,
)
from cadence_mcp_bridge.result_reports import make_report
from cadence_mcp_bridge.variable_contracts import canonical_digest

__all__ = ["configured", "operator", "operator_base"]


def sample(frequency, real, imag=0.0):
    magnitude = math.hypot(real, imag)
    return {
        "frequency_hz": float(frequency),
        "input_real_v": 0.3,
        "input_imag_v": 0.4,
        "real_v_per_v": float(real),
        "imag_v_per_v": float(imag),
        "gain_v_per_v": magnitude,
        "gain_db": 20 * math.log10(magnitude) if magnitude else None,
        "phase_deg": math.degrees(math.atan2(imag, real)) if magnitude else None,
        "method": "exact_sample_complex_output_over_measured_input",
    }


def test_ac_reference_and_log_interpolated_unity_crossing():
    result = sampled_ac_gain(
        [sample(1, 0, 2), sample(100, 0.5)],
        AcGainDefinition(reference_frequency_hz=1.0),
    )
    assert result["reference"]["input_magnitude_v"] == 0.5
    assert result["reference"]["input_phase_deg"] == pytest.approx(53.130102)
    assert result["reference"]["imag_v_per_v"] == 2.0
    assert result["unity_gain_frequency"]["value"] == pytest.approx(10.0)
    assert result["unity_gain_frequency"]["bracket_hz"] == [1.0, 100.0]


@pytest.mark.parametrize(
    ("reference", "end", "reason"),
    [
        (2.0, 0.5, "reference_sample_unavailable"),
        (100.0, 0.5, "samples_after_reference_unavailable"),
        (1.0, 1.5, "downward_crossing_absent"),
        (1.0, 0.0, "zero_transfer_at_crossing_bracket"),
    ],
)
def test_ac_does_not_invent_crossing(reference, end, reason):
    result = sampled_ac_gain(
        [sample(1, 2), sample(100, end)],
        AcGainDefinition(reference_frequency_hz=reference),
    )
    assert result["unity_gain_frequency"]["value"] is None
    assert result["unity_gain_frequency"]["reason"] == reason


def test_registered_op_reads_and_missing_signed_region_values(configured):
    _, record, result = seed(configured)
    report = make_report(record, result)
    registry = DeviceOpRegistration(instance_paths=tuple(f"/I0/M{i}" for i in range(17)))
    reads = render_device_op_reads(registry, "dcOpInfo")
    assert len(reads.splitlines()) == 119
    assert '"/I0/M16" "vdsat" "dcOpInfo"' in reads
    lines = ["BEGIN"]
    values = {"id": "value|-3e-6", "region": "value|2"}
    for index in range(1, 18):
        for field in ("id", "gm", "gds", "vgs", "vds", "vdsat", "region"):
            lines.append(f"OP|registered|mos{index:02d}|{field}|{values.get(field, 'missing|nil')}")
    frame = ("\n".join([*lines, "END"]) + "\n").encode()
    digest = hashlib.sha256(frame).hexdigest()
    payload = parse_device_op_frame(report, registry, frame, expected_frame_sha256=digest)
    measured = project_device_operating_points(report, registry, payload)
    assert measured["operation_id"] == report.operation_id
    assert measured["op_frame_sha256"] == digest
    first = measured["measurements"][:7]
    assert (first[0]["value"], first[0]["unit"]) == (-3e-6, "A")
    assert (first[1]["value"], first[1]["reason"]) == (None, "field_not_available")
    assert first[6]["value"] == 2
    assert first[6]["interpretation_reason"] == "registered_model_region_meaning_unavailable"
    with pytest.raises(OperationRejected) as mismatched_digest:
        parse_device_op_frame(report, registry, frame + b"invalid", expected_frame_sha256=digest)
    assert mismatched_digest.value.reason == "research_op_frame_size_or_digest_mismatch"
    drift = frame.replace(b"mos01|id", b"mos02|id", 1)
    with pytest.raises(OperationRejected) as mismatched_row:
        parse_device_op_frame(
            report,
            registry,
            drift,
            expected_frame_sha256=hashlib.sha256(drift).hexdigest(),
        )
    assert mismatched_row.value.reason == "research_op_frame_invalid"


def test_static_power_preserves_absorption_and_missing_rail(configured):
    _, record, result = seed(configured)
    result["sources"] = [
        {"source_id": "vdd", "role": "supply", "delivered_w": 4e-6},
        {"source_id": "return", "role": "supply", "delivered_w": -1e-6},
    ]
    report = make_report(record, result)
    assert static_supply_power(report, ("vdd", "return"))["value"] == pytest.approx(3e-6)
    incomplete = static_supply_power(report, ("vdd", "return", "vss"))
    assert incomplete["value"] is None
    assert incomplete["missing_supply_ids"] == ["vss"]


def test_operator_pinned_device_op_reads_numeric_and_missing_rows(configured, tmp_path):
    native, record, result = seed(configured)
    report = make_report(record, result)
    registration = DeviceOpRegistration(instance_paths=("PM0",))
    query = DeviceOpQuery(
        operation_id=report.operation_id,
        expected_plan_sha256=report.plan.plan_sha256,
        registration_id="pmos-op",
    )

    def write_artifact(name, data):
        path = tmp_path / name
        path.write_bytes(data)
        return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}

    frame = (
        "BEGIN\nOP|registered|mos01|id|value|-3e-6\n"
        + "".join(
            f"OP|registered|mos01|{field}|missing|nil\n"
            for field in ("gm", "gds", "vgs", "vds", "vdsat", "region")
        )
        + "END\n"
    ).encode()
    frame_ref = write_artifact("op-frame.txt", frame)
    doc = {
        "schema_version": 1,
        "records": [
            {
                **query.model_dump(exclude={"expected_plan_sha256"}),
                "plan_sha256": query.expected_plan_sha256,
                "execution_input_sha256": report.execution_input_sha256,
                "terminal_sha256": record.progress.provider_receipt_sha256,
                "registration": registration.model_dump(mode="json"),
                "registration_sha256": canonical_digest(registration),
                "report": write_artifact("op-report.json", report.model_dump_json().encode()),
                "frame": frame_ref,
            }
        ],
    }
    ref = write_artifact("op-catalog.json", json.dumps(doc).encode())
    binding = DeviceOpSourceBinding(
        catalog_path=tmp_path / "op-catalog.json", catalog_sha256=ref["sha256"]
    )
    journal = native.context.binding.analysis_journal
    before = journal.read_bytes()

    assert capture_device_operating_points(native, query, source=None)["status"] == "NOT_AVAILABLE"
    result = capture_device_operating_points(native, query, source=binding)
    assert result["status"] == "AVAILABLE"
    assert result["remote_contact"] is False and result["new_extractions"] == 0
    measured = result["measurement"]["measurements"]
    assert (measured[0]["field"], measured[0]["value"]) == ("id", -3e-6)
    assert (measured[1]["field"], measured[1]["value"], measured[1]["reason"]) == (
        "gm",
        None,
        "field_not_available",
    )
    assert capture_device_operating_points(native, query, source=binding) == result
    assert journal.read_bytes() == before
    native.provider.report_result.assert_not_called()

    wrong = query.model_copy(update={"expected_plan_sha256": "0" * 64})
    with pytest.raises(OperationRejected) as stale:
        capture_device_operating_points(native, wrong, source=binding)
    assert stale.value.reason == "research_op_registration_or_plan_mismatch"

    (tmp_path / "op-frame.txt").write_bytes(frame.replace(b"-3e-6", b"-4e-6"))
    with pytest.raises(OperationRejected) as tampered:
        capture_device_operating_points(native, query, source=binding)
    assert tampered.value.reason == "research_op_artifact_digest_or_size_mismatch"
