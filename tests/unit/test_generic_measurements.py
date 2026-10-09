"""Analytical disposable frame checks, never native reader qualification."""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_generic_ade import setup
from test_operator_operations import operator as operator_fixture

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.generic_measurements import (
    GenericReaderRegistration,
    project_frame,
    render_reader,
)
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.power_measurements import SignedSource, delivered_power, signed_power_totals
from cadence_mcp_bridge.variable_contracts import canonical_digest

operator_base = operator_fixture


@pytest.fixture
def operator(operator_base):
    from cadence_mcp_bridge.analyses import AnalysisContract
    from cadence_mcp_bridge.designs import DesignMeasurementRegistry, DesignProfile
    from cadence_mcp_bridge.runtime_context import load_runtime
    from cadence_mcp_bridge.variable_contracts import DesignVariables

    context, grant, request, settings = operator_base
    registry = json.loads(context.contracts.designs.model_dump_json())
    profile = registry["designs"][0]
    profile["allowed_measurements"].append("tran-summary")
    profile_hash = canonical_digest(DesignProfile.model_validate_json(json.dumps(profile)))
    registry["variable_sets"][0]["design_profile_sha256"] = profile_hash
    variable_hash = canonical_digest(
        DesignVariables.model_validate_json(json.dumps(registry["variable_sets"][0]))
    )
    registry["schema_version"] = 4
    registry["measurement_contracts"] = []
    for contract in registry["analysis_contracts"]:
        contract.update(design_profile_sha256=profile_hash, variable_set_sha256=variable_hash)
        registry["measurement_contracts"].append(
            dict(
                design_id=profile["design_id"],
                measurement_id={"dc": "dc-output", "ac": "ac-gain", "tran": "tran-summary"}[
                    contract["analysis"]
                ],
                analysis_id=contract["analysis_id"],
                analysis_contract_sha256=canonical_digest(
                    AnalysisContract.model_validate_json(json.dumps(contract))
                ),
                reader="unqualified",
                output_id=None,
                definition_sha256=None,
            )
        )
    registry_model = DesignMeasurementRegistry.model_validate_json(json.dumps(registry))
    path = context.binding.design_registry
    path.write_text(registry_model.model_dump_json())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    runtime = json.loads(settings.read_bytes())
    runtime["contexts"][0]["design_sha256"] = digest
    settings.write_text(json.dumps(runtime))
    return (
        load_runtime(settings)[0],
        grant.model_copy(update={"design_sha256": digest}),
        request,
        settings,
    )


def reader_for(operator, analysis="dc"):
    context, plan, ade, _ = setup(operator, analysis)
    if analysis == "ac":
        ade = ade.model_copy(
            update={
                "inputs": ade.inputs.model_copy(
                    update={"start_hz": "1000", "stop_hz": "2000", "points_per_decade": 1}
                )
            }
        )
    if analysis == "tran":
        ade = ade.model_copy(
            update={"inputs": ade.inputs.model_copy(update={"maxstep_s": "0.004"})}
        )
    reader = GenericReaderRegistration.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "design_id": plan.request.design_id,
                "analysis_id": plan.request.analysis_id,
                "measurement_id": {"dc": "dc-output", "ac": "ac-gain", "tran": "tran-summary"}[
                    analysis
                ],
                "measurement_contract_sha256": canonical_digest(
                    next(
                        m
                        for m in context.contracts.designs.measurements_for(plan.request.design_id)
                        if m.analysis_id == plan.request.analysis_id
                    )
                ),
                "ade_registration_sha256": canonical_digest(ade),
                "nodes": [
                    {"logical_id": "input", "selector": "/in"},
                    {"logical_id": "output", "selector": "/out"},
                ],
                "sources": [
                    {
                        "source_id": "rail",
                        "role": "supply",
                        "positive_node": "input",
                        "negative_node": "output",
                        "current_selector": "/VDD/PLUS",
                        "current_convention": "positive_into_source_positive_terminal_A",
                    }
                ]
                if analysis == "dc"
                else [],
                "transfer": {
                    "positive_input": "input",
                    "negative_input": None,
                    "positive_output": "output",
                    "negative_output": None,
                    "gain_frequencies_hz": ["1000"],
                }
                if analysis == "ac"
                else None,
                "maximum_samples": 64 if analysis == "ac" else 4,
            }
        )
    )
    return context, plan, ade, reader, str(uuid4()), "d" * 64


def frame_for(args, body):
    _, plan, _, reader, operation, execution = args
    return (
        "|".join(
            (
                "MCP_GREL_FRAME",
                "1",
                operation,
                plan.plan_sha256,
                execution,
                canonical_digest(reader),
            )
        )
        + "\n"
        + body
        + "\nEND\n"
    ).encode("ascii")


@pytest.mark.parametrize("selectors", [("/input", "/rc/output"), ("/gate", "/mos/drain")])
def test_dc_signed_power_from_registered_terminal_difference(operator, selectors):
    args = reader_for(operator)
    context, plan, ade, reader, operation, execution = args
    reader = reader.model_copy(
        update={
            "nodes": tuple(
                n.model_copy(update={"selector": s})
                for n, s in zip(reader.nodes, selectors, strict=True)
            )
        }
    )
    args = (context, plan, ade, reader, operation, execution)
    frame = frame_for(args, "V|input|3\nV|output|1\nI|rail|-0.001")
    result = project_frame(*args, frame)
    assert result["power"] == dict(
        supply_w=0.002, bias_w=0.0, stimulus_w=0.0, all_registered_sources_w=0.002
    )
    assert result["sources"][0]["voltage_v"] == 2
    assert result["status"] == "BOUNDED_FRAME_VALIDATED_NATIVE_UNATTESTED"
    assert (
        result["native_provenance"] == "NOT_ATTESTED"
        and result["spec_evaluation"] == "not_evaluated"
    )
    assert not result["execution_authorized"] and not result["remote_contact"]
    script = render_reader(*args)
    assert all(s.encode() in script for s in selectors)
    assert b"/VDD/PLUS" in script and b"run()" not in script and b"system(" not in script
    assert b"END\\n" in script and b"ExampleLib" not in script
    assert not context.binding.analysis_journal.exists() and not context.lock_path.exists()


def test_power_retains_absorption_and_separate_roles():
    assert signed_power_totals(
        (("supply", 3, -0.001), ("bias", 1, 0.002), ("stimulus", 2, -0.004))
    ) == pytest.approx((0.003, -0.002, 0.008, 0.009))
    # Preserve the original six-source arithmetic, including its fsum order.
    sources = tuple(
        SignedSource(source_id=name, role=role, voltage_v=v, current_a=i)
        for name, role, v, i in (
            ("vdd", "supply", 1e20, -1),
            ("vss", "supply", 1, 1),
            ("bias-n", "bias", 1e20, 1),
            ("bias-p", "bias", 1, -1),
            ("input-p", "stimulus", 1, -2),
            ("input-m", "stimulus", 1, 1),
        )
    )
    assert delivered_power(sources) == (1e20, -1e20, 1.0, 1.0)


@pytest.mark.parametrize("amplitude", [0, 4])
def test_ac_uses_measured_complex_stimulus_and_selected_frequency(operator, amplitude):
    args = reader_for(operator, "ac")
    frame = frame_for(
        args,
        f"P|input|0|1000|2|0\nP|input|1|2000|2|0\nP|output|0|1000|0|{amplitude}\nP|output|1|2000|0|{amplitude}",
    )
    value = project_frame(*args, frame)["transfer"][0]
    assert value["frequency_hz"] == 1000 and value["gain_v_per_v"] == amplitude / 2
    assert value["phase_deg"] == (90.0 if amplitude else None)
    assert value["gain_db"] == (pytest.approx(6.020599913) if amplitude else None)


def test_transient_uses_all_samples_time_weighted_mean(operator):
    args = reader_for(operator, "tran")
    body = (
        "P|input|0|0|0|0\nP|input|1|0.001|2|0\nP|input|2|0.004|2|0\n"
        "P|output|0|0|1|0\nP|output|1|0.001|1|0\nP|output|2|0.004|1|0"
    )
    result = project_frame(*args, frame_for(args, body))["transient"]
    assert result[0]["time_weighted_mean"] == 1.75
    assert result[0]["maximum_step_s"] == 0.003 and result[0]["sample_count"] == 3
    assert result[1]["time_weighted_mean"] == 1.0


@pytest.mark.parametrize(
    "old,new",
    [
        ("END", ""),
        ("V|input|3", "V|output|3"),
        ("V|input|3", "V|input|nil"),
        ("V|input|3", "V|input|NaN"),
        ("V|input|3", "V|input|inf"),
        ("V|input|3", "V|input|1e309"),
        ("V|input|3", "V|input|1e-400"),
        ("V|input|3", "V|input|(+ 1 2)"),
        ("I|rail|-0.001", "I|other|-0.001"),
        ("END", "V|extra|1\nEND"),
        ("MCP_GREL_FRAME|1", "MCP_GREL_FRAME|2"),
    ],
)
def test_bad_dc_frames_fail_without_partial_values(operator, old, new):
    args = reader_for(operator)
    frame = frame_for(args, "V|input|3\nV|output|1\nI|rail|-0.001")
    with pytest.raises(OperationRejected):
        project_frame(*args, frame.replace(old.encode(), new.encode()))


@pytest.mark.parametrize("field", ["operation", "plan", "input", "registration"])
def test_every_frame_identity_is_bound(operator, field):
    args = reader_for(operator)
    frame = frame_for(args, "V|input|3\nV|output|1\nI|rail|-0.001")
    old = {
        "operation": args[4],
        "plan": args[1].plan_sha256,
        "input": args[5],
        "registration": canonical_digest(args[3]),
    }[field]
    with pytest.raises(OperationRejected):
        project_frame(*args, frame.replace(old.encode(), b"a" * len(old)))


@pytest.mark.parametrize(
    "old,new",
    [
        ("input|1|2000", "input|0|2000"),
        ("input|1|2000", "input|1|1000"),
        ("output|1|2000", "output|1|2000000"),
        ("output|1|2000", "output|1|999999"),
        ("input|0|1000|2|0", "input|0|1000|0|0"),
        ("input|0|1000", "input|0|1001"),
        ("output|0|1000", "output|0|1001"),
    ],
)
def test_ac_zero_input_missing_gain_sample_nonmatching_axes_or_order(operator, old, new):
    args = reader_for(operator, "ac")
    body = "P|input|0|1000|2|0\nP|input|1|2000|2|0\nP|output|0|1000|0|4\nP|output|1|2000|0|4"
    with pytest.raises(OperationRejected):
        project_frame(*args, frame_for(args, body.replace(old, new)))


@pytest.mark.parametrize(
    "old,new",
    [
        ("|0|0|1|0", "|0|0.0001|1|0"),
        ("|1|0.004|1|0", "|1|0.003|1|0"),
        ("|1|0.004|1|0", "|1|0.004|1|1"),
    ],
)
def test_tran_wrong_interval_or_complex_values(operator, old, new):
    args = reader_for(operator, "tran")
    body = "P|input|0|0|1|0\nP|input|1|0.004|1|0\nP|output|0|0|1|0\nP|output|1|0.004|1|0"
    with pytest.raises(OperationRejected):
        project_frame(*args, frame_for(args, body.replace(old, new)))


@pytest.mark.parametrize(
    "selector",
    ["/../secret", "/a//b", "/a/./b", "/a/", '/a" system("x")', "/a;exit(0)", "/a\nb", "/a|b"],
)
def test_operator_selectors_cannot_escape_fixed_api(operator, selector):
    data = json.loads(reader_for(operator)[3].model_dump_json())
    data["nodes"][0]["selector"] = selector
    with pytest.raises(ValidationError):
        GenericReaderRegistration.model_validate_json(json.dumps(data))


def test_closed_registration_rejects_bad_references_duplicates_and_schema_bool(operator):
    original = json.loads(reader_for(operator)[3].model_dump_json())
    for field, value in [
        ("schema_version", True),
        ("maximum_samples", 257),
        ("maximum_samples", True),
        ("extra", 1),
    ]:
        data = dict(original)
        data[field] = value
        with pytest.raises(ValidationError):
            GenericReaderRegistration.model_validate_json(json.dumps(data))
    for mutate in (
        lambda d: d["nodes"].append(d["nodes"][0]),
        lambda d: d["sources"][0].update(positive_node="missing"),
        lambda d: d["sources"][0].update(current_selector="/VDD/MINUS"),
    ):
        data = json.loads(json.dumps(original))
        mutate(data)
        with pytest.raises(ValidationError):
            GenericReaderRegistration.model_validate_json(json.dumps(data))


def test_analysis_binding_and_frame_bounds(operator):
    args = reader_for(operator)
    context, plan, ade, reader, op, execution = args
    for changed in [
        reader.model_copy(update={"measurement_id": "unregistered"}),
        reader.model_copy(update={"ade_registration_sha256": "a" * 64}),
    ]:
        with pytest.raises(OperationRejected):
            render_reader(context, plan, ade, changed, op, execution)
    with pytest.raises(OperationRejected):
        project_frame(*args, b"x" * 262145)
    ac = reader_for(operator, "ac")
    r = ac[3].model_copy(update={"sources": reader.sources})
    with pytest.raises(OperationRejected):
        render_reader(*ac[:3], r, *ac[4:])


def test_cli_compile_project_and_denial_are_installed_operator_actions(operator, tmp_path, capsys):
    args = reader_for(operator)
    _, plan, ade, reader, op, execution = args
    paths = []
    for name, model in (("plan", plan), ("ade", ade), ("reader", reader)):
        path = tmp_path / (name + ".json")
        path.write_text(model.model_dump_json())
        paths.append(path)
    command = [
        "result-reader",
        "compile",
        "--settings",
        str(operator[3]),
        "--context",
        "operator",
        "--plan",
        str(paths[0]),
        "--expected-plan-sha256",
        plan.plan_sha256,
        "--ade-registration",
        str(paths[1]),
        "--expected-ade-sha256",
        canonical_digest(ade),
        "--reader-registration",
        str(paths[2]),
        "--expected-reader-sha256",
        canonical_digest(reader),
        "--operation-id",
        op,
        "--execution-input-sha256",
        execution,
    ]
    output = tmp_path / "compiled"
    assert main([*command, "--output", str(output)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (
        not report["execution_authorized"]
        and report["reader_script_sha256"]
        == hashlib.sha256((output / "extract.ocn").read_bytes()).hexdigest()
    )
    original = (output / "extract.ocn").read_bytes()
    assert main([*command, "--output", str(output)]) == 1
    assert (output / "extract.ocn").read_bytes() == original
    assert "private" not in capsys.readouterr().out
    frame = tmp_path / "frame.txt"
    frame.write_bytes(frame_for(args, "V|input|3\nV|output|1\nI|rail|-0.001"))
    command[1] = "project-frame"
    assert main([*command, "--frame", str(frame)]) == 0
    assert json.loads(capsys.readouterr().out)["native_provenance"] == "NOT_ATTESTED"
    assert main(["result-reader", "schema"]) == 0
    assert json.loads(capsys.readouterr().out)["additionalProperties"] is False


def test_aggregate_rows_and_unsupported_array_size_are_denied_before_write(operator):
    data = json.loads(reader_for(operator)[3].model_dump_json())
    data["nodes"] = [{"logical_id": "n" + str(i), "selector": "/n" + str(i)} for i in range(8)]
    data["sources"] = []
    data["maximum_samples"] = 256
    with pytest.raises(ValidationError):
        GenericReaderRegistration.model_validate_json(json.dumps(data))
    data["maximum_samples"] = 192
    assert GenericReaderRegistration.model_validate_json(json.dumps(data)).maximum_samples == 192


@pytest.mark.parametrize(
    "change", ["wrong_analysis", "stale_contract", "missing_contract", "protected_legacy"]
)
def test_measurement_identity_requires_registered_exact_analysis_and_definition(operator, change):
    from dataclasses import replace

    args = reader_for(operator, "ac")
    context, plan, ade, reader, op, execution = args
    contracts = context.contracts.designs.measurements_for(reader.design_id)
    if change == "wrong_analysis":
        other = next(m for m in contracts if m.analysis_id.endswith("dc"))
        reader = reader.model_copy(
            update={
                "measurement_id": other.measurement_id,
                "measurement_contract_sha256": canonical_digest(other),
            }
        )
    elif change == "stale_contract":
        reader = reader.model_copy(update={"measurement_contract_sha256": "a" * 64})
    else:
        changed = (
            tuple()
            if change == "missing_contract"
            else tuple(
                m.model_copy(update={"reader": "native-bounded-result-v1"})
                if m.analysis_id == reader.analysis_id
                else m
                for m in contracts
            )
        )
        registry = context.contracts.designs.model_copy(update={"measurement_contracts": changed})
        context = replace(context, contracts=replace(context.contracts, designs=registry))
        if change == "protected_legacy":
            reader = reader.model_copy(
                update={
                    "measurement_contract_sha256": canonical_digest(
                        next(m for m in changed if m.analysis_id == reader.analysis_id)
                    )
                }
            )
    with pytest.raises(OperationRejected) as error:
        render_reader(context, plan, ade, reader, op, execution)
    assert error.value.reason == (
        "reader_legacy_definition_protected"
        if change == "protected_legacy"
        else "reader_measurement_analysis_binding_mismatch"
    )


@pytest.mark.parametrize("selector", ["/VDD/PLUS", "/VDD/MINUS", "/nested/VDD/PLUS"])
def test_branch_current_selectors_are_never_projected_as_node_voltage(operator, selector):
    data = json.loads(reader_for(operator)[3].model_dump_json())
    data["nodes"][0]["selector"] = selector
    with pytest.raises(ValidationError):
        GenericReaderRegistration.model_validate_json(json.dumps(data))


def test_disjoint_voltage_and_current_inventories_even_for_internal_prebuilt_models(operator):
    # Keep the cross-inventory invariant independent from today's selector grammar.
    reader = reader_for(operator)[3]
    source = reader.sources[0].model_copy(update={"current_selector": reader.nodes[0].selector})
    with pytest.raises(ValueError):
        reader.model_copy(update={"sources": (source,)}).inventory()


@pytest.mark.parametrize("frequencies", [("10", "100", "1000"), ("1000", "10000", "100000")])
def test_gain_frequency_count_must_fit_reader_samples(operator, frequencies):
    args = reader_for(operator, "ac")
    data = json.loads(args[3].model_dump_json())
    data["transfer"]["gain_frequencies_hz"] = frequencies
    data["maximum_samples"] = 2
    with pytest.raises(ValidationError, match="frequency count"):
        GenericReaderRegistration.model_validate_json(json.dumps(data))
    data["maximum_samples"] = 3
    assert (
        len(
            GenericReaderRegistration.model_validate_json(
                json.dumps(data)
            ).transfer.gain_frequencies_hz
        )
        == 3
    )


@pytest.mark.parametrize(
    "frequencies", [("100000000000", "100000000000.000001"), ("1000", "1000.00000000000001")]
)
def test_gain_frequencies_must_remain_distinct_as_projected_floats(operator, frequencies):
    args = reader_for(operator, "ac")
    data = json.loads(args[3].model_dump_json())
    data["transfer"]["gain_frequencies_hz"] = frequencies
    with pytest.raises(ValidationError, match="float conversion"):
        GenericReaderRegistration.model_validate_json(json.dumps(data))


def test_close_distinct_gain_frequencies_cannot_share_a_saved_sample(operator):
    args = reader_for(operator, "ac")
    context, plan, ade, reader, operation, execution = args
    data = json.loads(reader.model_dump_json())
    data["transfer"]["gain_frequencies_hz"] = ["1000", "1000.0000000005"]
    reader = GenericReaderRegistration.model_validate_json(json.dumps(data))
    args = (context, plan, ade, reader, operation, execution)
    frame = frame_for(
        args, "P|input|0|1000|2|0\nP|input|1|2000|2|0\nP|output|0|1000|4|0\nP|output|1|2000|4|0"
    )
    with pytest.raises(OperationRejected, match="Operator operation rejected") as exc:
        project_frame(*args, frame)
    assert exc.value.reason == "reader_gain_sample_reused"


@pytest.mark.parametrize(
    "stop,ppd,limit,allowed",
    [
        ("1000000", 100, 256, False),
        ("1000000", 10, 60, False),
        ("1000000", 10, 61, True),
        ("2", 10, 4, False),
        ("2", 10, 5, True),
    ],
)
def test_declared_ac_grid_must_fit_waveform_limit_before_compiling(
    operator, stop, ppd, limit, allowed
):
    from cadence_mcp_bridge.generic_ade import AcInputs

    context, plan, ade, reader, op, execution = reader_for(operator, "ac")
    ade = ade.model_copy(
        update={
            "inputs": AcInputs(analysis="ac", start_hz="1", stop_hz=stop, points_per_decade=ppd)
        }
    )
    transfer = reader.transfer.model_copy(update={"gain_frequencies_hz": ("1",)})
    reader = reader.model_copy(
        update={
            "ade_registration_sha256": canonical_digest(ade),
            "maximum_samples": limit,
            "transfer": transfer,
        }
    )
    if allowed:
        assert render_reader(context, plan, ade, reader, op, execution)
    else:
        with pytest.raises(OperationRejected) as exc:
            render_reader(context, plan, ade, reader, op, execution)
        assert exc.value.reason == "reader_ac_grid_exceeds_sample_limit"
    assert not context.binding.analysis_journal.exists()


@pytest.mark.parametrize("start,stop", [("1", "1.2345678901234567"), ("1.2345678901234564", "2")])
def test_ac_interval_accepts_extractor_endpoint_rounding(operator, start, stop):
    from cadence_mcp_bridge.generic_ade import AcInputs

    context, plan, ade, reader, op, execution = reader_for(operator, "ac")
    ade = ade.model_copy(
        update={
            "inputs": AcInputs(analysis="ac", start_hz=start, stop_hz=stop, points_per_decade=1)
        }
    )
    transfer = reader.transfer.model_copy(update={"gain_frequencies_hz": (start, stop)})
    reader = reader.model_copy(
        update={"ade_registration_sha256": canonical_digest(ade), "transfer": transfer}
    )
    args = (context, plan, ade, reader, op, execution)
    lo, hi = (format(float(x), ".16g") for x in (start, stop))
    body = f"P|input|0|{lo}|2|0\nP|input|1|{hi}|2|0\nP|output|0|{lo}|4|0\nP|output|1|{hi}|4|0"
    result = project_frame(*args, frame_for(args, body))["transfer"]
    assert len(result) == 2 and all(r["gain_v_per_v"] == 2 for r in result)
    # Materially outside the declared interval must still reject.
    outside = body.replace(f"|1|{hi}|", f"|1|{float(stop) * 1.000001:.16g}|")
    with pytest.raises(OperationRejected) as exc:
        project_frame(*args, frame_for(args, outside))
    assert exc.value.reason == "reader_ac_interval_invalid"


@pytest.mark.parametrize("axis", [("1000", "10000"), ("1000", "1000000"), ("1", "1000", "1000000")])
def test_ac_omitted_endpoints_or_interior_samples_are_rejected(operator, axis):
    from cadence_mcp_bridge.generic_ade import AcInputs

    context, plan, ade, reader, op, execution = reader_for(operator, "ac")
    ade = ade.model_copy(
        update={
            "inputs": AcInputs(analysis="ac", start_hz="1", stop_hz="1000000", points_per_decade=1)
        }
    )
    reader = reader.model_copy(update={"ade_registration_sha256": canonical_digest(ade)})
    args = (context, plan, ade, reader, op, execution)
    body = "\n".join(
        f"P|{node}|{i}|{x}|{value}|0"
        for node, value in (("input", 2), ("output", 4))
        for i, x in enumerate(axis)
    )
    with pytest.raises(OperationRejected):
        project_frame(*args, frame_for(args, body))


def test_ac_exact_neighbor_samples_take_precedence_over_tolerant_matches(operator):
    from cadence_mcp_bridge.generic_ade import AcInputs

    context, plan, ade, reader, op, execution = reader_for(operator, "ac")
    endpoints = ("1000000", "1000000.000001")
    ade = ade.model_copy(
        update={
            "inputs": AcInputs(
                analysis="ac", start_hz=endpoints[0], stop_hz=endpoints[1], points_per_decade=1
            )
        }
    )
    transfer = reader.transfer.model_copy(update={"gain_frequencies_hz": endpoints})
    reader = reader.model_copy(
        update={"ade_registration_sha256": canonical_digest(ade), "transfer": transfer}
    )
    args = (context, plan, ade, reader, op, execution)
    body = "\n".join(
        f"P|{node}|{i}|{x}|{value}|0"
        for node, value in (("input", 2), ("output", 4))
        for i, x in enumerate(endpoints)
    )
    results = project_frame(*args, frame_for(args, body))["transfer"]
    assert [r["frequency_hz"] for r in results] == [float(x) for x in endpoints]
    assert all(r["gain_v_per_v"] == 2 for r in results)


def test_ac_complete_declared_grid_passes_and_changed_interior_rejects(operator):
    from cadence_mcp_bridge.generic_ade import AcInputs

    context, plan, ade, reader, op, execution = reader_for(operator, "ac")
    ade = ade.model_copy(
        update={
            "inputs": AcInputs(analysis="ac", start_hz="1", stop_hz="1000000", points_per_decade=1)
        }
    )
    reader = reader.model_copy(update={"ade_registration_sha256": canonical_digest(ade)})
    args = (context, plan, ade, reader, op, execution)
    axis = (1, 10, 100, 1000, 10000, 100000, 1000000)
    body = "\n".join(
        f"P|{node}|{i}|{x}|{value}|0"
        for node, value in (("input", 2), ("output", 4))
        for i, x in enumerate(axis)
    )
    assert project_frame(*args, frame_for(args, body))["transfer"][0]["gain_v_per_v"] == 2
    changed = body.replace("|2|100|", "|2|101|")
    with pytest.raises(OperationRejected) as exc:
        project_frame(*args, frame_for(args, changed))
    assert exc.value.reason == "reader_ac_grid_incomplete_or_unsupported"


def test_ac_grid_must_remain_distinct_after_extractor_serialization(operator):
    from cadence_mcp_bridge.generic_ade import AcInputs

    context, plan, ade, reader, op, execution = reader_for(operator, "ac")
    ade = ade.model_copy(
        update={
            "inputs": AcInputs(
                analysis="ac", start_hz="1", stop_hz="1.0000000000000002", points_per_decade=1
            )
        }
    )
    transfer = reader.transfer.model_copy(update={"gain_frequencies_hz": ("1",)})
    reader = reader.model_copy(
        update={"ade_registration_sha256": canonical_digest(ade), "transfer": transfer}
    )
    with pytest.raises(OperationRejected) as exc:
        render_reader(context, plan, ade, reader, op, execution)
    assert exc.value.reason == "reader_ac_grid_float_resolution_invalid"


@pytest.mark.parametrize(
    "frequencies,reason",
    [
        ("1500", "reader_gain_sample_unavailable"),
        ("1000.0000000005,1000.0000000006", "reader_gain_sample_reused"),
    ],
)
def test_in_interval_frequencies_need_unique_declared_grid_samples_before_compile(
    operator, frequencies, reason
):
    context, plan, ade, reader, op, execution = reader_for(operator, "ac")
    transfer = reader.transfer.model_copy(
        update={"gain_frequencies_hz": tuple(frequencies.split(","))}
    )
    reader = reader.model_copy(update={"transfer": transfer})
    with pytest.raises(OperationRejected) as exc:
        render_reader(context, plan, ade, reader, op, execution)
    assert exc.value.reason == reason
    assert not context.binding.analysis_journal.exists()


@pytest.mark.parametrize(
    "stop,step,limit,allowed",
    [
        ("1", "0.001", 256, False),
        ("0.003", "0.001", 3, False),
        ("0.003", "0.001", 4, True),
        ("0.0031", "0.001", 4, False),
        ("0.0031", "0.001", 5, True),
    ],
)
def test_tran_minimum_saved_grid_must_fit_reader_before_compile(
    operator, stop, step, limit, allowed
):
    from cadence_mcp_bridge.generic_ade import TranInputs

    context, plan, ade, reader, op, execution = reader_for(operator, "tran")
    ade = ade.model_copy(
        update={"inputs": TranInputs(analysis="tran", stop_s=stop, maxstep_s=step, method="trap")}
    )
    reader = reader.model_copy(
        update={"ade_registration_sha256": canonical_digest(ade), "maximum_samples": limit}
    )
    if allowed:
        assert render_reader(context, plan, ade, reader, op, execution)
    else:
        with pytest.raises(OperationRejected) as exc:
            render_reader(context, plan, ade, reader, op, execution)
        assert exc.value.reason == "reader_tran_grid_exceeds_sample_limit"
    assert not context.binding.analysis_journal.exists()


@pytest.mark.parametrize("axis", [("0", "0.004"), ("0", "0.0005", "0.001", "0.004")])
def test_tran_saved_grid_cannot_have_gaps_above_the_declared_maxstep(operator, axis):
    context, plan, ade, reader, op, execution = reader_for(operator, "tran")
    ade = ade.model_copy(update={"inputs": ade.inputs.model_copy(update={"maxstep_s": "0.002"})})
    reader = reader.model_copy(update={"ade_registration_sha256": canonical_digest(ade)})
    args = (context, plan, ade, reader, op, execution)
    body = "\n".join(
        f"P|{node}|{i}|{x}|{value}|0"
        for node, value in (("input", 2), ("output", 4))
        for i, x in enumerate(axis)
    )
    with pytest.raises(OperationRejected) as exc:
        project_frame(*args, frame_for(args, body))
    assert exc.value.reason == "reader_tran_saved_step_exceeds_declared_maxstep"


def test_registered_selectors_bind_verified_standard_vm_psf_aliases(operator):
    from cadence_mcp_bridge import _native_rendering

    _, _, _, reader, op, _ = reader_for(operator)
    text = _native_rendering.reader(
        "/managed/jobs", "dc", reader.model_dump(mode="json"), op, "a" * 64, "b" * 64, "c" * 64
    ).decode()
    assert 'mcpGenericScalar("/in" "in")' in text
    assert 'mcpGenericScalar("/out" "out")' in text
    assert 'mcpGenericScalar("/VDD/PLUS" "VDD:p")' in text
    # Alias selection is compiled only from registered selectors; no expression.
    assert "unless(data data=getData(alias))" in text
