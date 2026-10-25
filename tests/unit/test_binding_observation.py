"""Synthetic protocol tests; these do not qualify real OA or CDF observations."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.binding_observation import (
    BindingScanRequest,
    BindingScanVariable,
    parse_frame,
    render_collector,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


def request_data() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "observation_id": "8197b274-d171-48d5-844f-a12dc53677ec",
        "nonce": "a" * 64,
        "library": "SyntheticSources",
        "cell": "SyntheticCell",
        "view": "schematic",
        "variables": [
            {"logical_id": "input-plus", "cadence_binding": "qa_vp"},
            {"logical_id": "input-minus", "cadence_binding": "qa_vm"},
        ],
    }


def request(data: dict[str, Any] | None = None) -> BindingScanRequest:
    return BindingScanRequest.model_validate_json(json.dumps(data or request_data()))


def binding(
    ordinal: int = 1,
    logical_id: str = "input-plus",
    cadence_binding: str = "qa_vp",
    instance: str = "SourceA",
    property_name: str = "dc",
    stored_type: str = "string",
    cdf: str = "observed|float|voltage|string|qa_vp",
) -> str:
    return (
        f"BIND|{ordinal}|{logical_id}|{cadence_binding}|{instance}"
        f"|SyntheticDevices|voltage_source|symbol|{property_name}|{stored_type}"
        f"|{cadence_binding}|{cdf}"
    )


def frame(
    scan: BindingScanRequest | None = None,
    body: list[str] | None = None,
    complete: str = "COMPLETE|2|2|2",
) -> bytes:
    scan = scan or request()
    if body is None:
        body = [
            "SCAN|1|1",
            binding(),
            "SCAN|2|1",
            binding(
                2, "input-minus", "qa_vm", "SourceB", cdf="observed|float|voltage|string|qa_vm"
            ),
        ]
    return (
        "\n".join(
            [
                f"BINDING_OBSERVATION_V1|{scan.observation_id}|{scan.nonce}|{canonical_digest(scan)}",
                f"SOURCE|{scan.library}|{scan.cell}|schematic",
                *[f"VARIABLE|{v.logical_id}|{v.cadence_binding}" for v in scan.variables],
                *body,
                complete,
            ]
        )
        + "\n"
    ).encode("ascii")


def test_exact_target_observation_is_distinct_from_qualification() -> None:
    result = parse_frame(frame(), request())
    assert result["status"] == "OBSERVED_OWNED_COPY_BINDINGS"
    assert result["qualification"] == "NOT_ESTABLISHED_BY_BINDING_SCAN"
    assert result["record_scope"] == "FIXED_FRAME_ONLY_NO_TRANSPORT_OR_SOURCE_ATTESTATION"
    assert result["effective_cdf_complete"] is True
    assert result["scan_counts"] == {"instances": 2, "properties": 2, "matches": 2}
    assert result["new_simulations"] == result["new_extractions"] == 0
    assert result["new_result_reservation_bytes"] == 0
    bindings = result["bindings"]
    assert isinstance(bindings, list)
    assert bindings[0]["instance_path"] == "SourceA"
    assert bindings[0]["master_cell"] == "voltage_source"
    assert bindings[0]["property_name"] == "dc"
    assert bindings[0]["effective_cdf"]["value"] == "qa_vp"


@pytest.mark.parametrize("status", ["missing", "read_error", "wrong_type", "unsupported_value"])
def test_cdf_unavailable_is_preserved_as_partial_evidence(status: str) -> None:
    raw = frame().replace(b"observed|float|voltage|string|qa_vp", f"{status}|-|-|-|-".encode())
    result = parse_frame(raw, request())
    assert result["effective_cdf_complete"] is False
    bindings = result["bindings"]
    assert isinstance(bindings, list)
    assert bindings[0]["effective_cdf"] == {
        "status": status, "parameter_type": None, "units": None, "value_type": None, "value": None,
    }


@pytest.mark.parametrize("kind,value", [("string", "0.500"), ("fixnum", "0"), ("flonum", "5e-1")])
def test_numeric_cdf_spelling_is_not_evaluated_or_canonicalized(kind: str, value: str) -> None:
    raw = frame().replace(b"string|qa_vp\n", f"{kind}|{value}\n".encode())
    result = parse_frame(raw, request())
    bindings = result["bindings"]
    assert isinstance(bindings, list)
    assert bindings[0]["effective_cdf"]["value"] == value


def test_exact_stored_symbol_is_supported() -> None:
    raw = frame().replace(b"|dc|string|qa_vp|", b"|dc|symbol|qa_vp|")
    result = parse_frame(raw, request())
    bindings = result["bindings"]
    assert isinstance(bindings, list)
    assert bindings[0]["stored_type"] == "symbol"


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True), ("schema_version", "1"), ("schema_version", 2),
        ("schema_version", 1.0), ("observation_id", "not-an-operation"),
        ("observation_id", "8197b274-d171-18d5-844f-a12dc53677ec"),
        ("nonce", "A" * 64), ("nonce", "a" * 63),
        ("library", '../Source'), ("library", 'Source\")system("bad")'),
        ("cell", "Cell|SOURCE"), ("cell", "Cell\nSCAN|2|0"),
        ("view", "symbol"), ("variables", []),
    ],
)
def test_request_rejects_coercion_identity_errors_and_injection(field: str, value: object) -> None:
    data = request_data()
    data[field] = value
    with pytest.raises(ValidationError):
        request(data)


@pytest.mark.parametrize("name", ["command", "script", "property_name", "path", "hierarchy"])
def test_no_arbitrary_execution_or_target_fields(name: str) -> None:
    data = request_data()
    data[name] = "anything"
    with pytest.raises(ValidationError):
        request(data)


def test_request_rejects_duplicate_ids_ade_aliases_and_more_than_four() -> None:
    data = request_data()
    data["variables"].append(data["variables"][0])
    with pytest.raises(ValidationError):
        request(data)
    data = request_data()
    data["variables"][1]["cadence_binding"] = "qa_vp"
    with pytest.raises(ValidationError):
        request(data)
    data["variables"] = [
        {"logical_id": f"variable-{n}", "cadence_binding": f"var_{n}"} for n in range(5)
    ]
    with pytest.raises(ValidationError):
        request(data)


@pytest.mark.parametrize("value", ["qa_vp+1", 'VAR("qa_vp")', "parent/qa_vp", "qa_vp\n"])
def test_request_cannot_request_expression_or_hierarchy_bindings(value: str) -> None:
    data = request_data()
    data["variables"][0]["cadence_binding"] = value
    with pytest.raises(ValidationError):
        request(data)


def test_nested_extra_target_and_callback_fields_are_closed() -> None:
    data = request_data()
    data["variables"][0]["callback"] = "arbitrary"
    with pytest.raises(ValidationError):
        request(data)


@pytest.mark.parametrize(
    "change",
    [
        {"library": 'Escape\")system("bad")'},
        {"schema_version": True},
        {"variables": ()},
        {"variables": (
            BindingScanVariable.model_construct(logical_id="bad/", cadence_binding="q"),
        )},
    ],
)
def test_frozen_model_copy_bypass_is_rejected_at_both_boundaries(change: dict[str, Any]) -> None:
    forged = request().model_copy(update=change)
    with pytest.raises(ValidationError):
        parse_frame(frame(), forged)
    with pytest.raises(ValidationError):
        render_collector(forged)


@pytest.mark.parametrize(
    "old,new",
    [
        (b"8197b274-d171-48d5-844f-a12dc53677ec", b"9197b274-d171-48d5-844f-a12dc53677ec"),
        (b"a" * 64, b"b" * 64),
        (b"SOURCE|SyntheticSources", b"SOURCE|OtherSources"),
        (b"VARIABLE|input-plus|qa_vp", b"VARIABLE|input-plus|qa_other"),
        (b"|dc|string|qa_vp|", b"|dc|string|qa_vp+1|"),
        (b"|dc|string|qa_vp|", b"|dc|list|qa_vp|"),
        (b"|SourceA|", b"|Other/SourceA|"),
        (b"|voltage_source|", b"|voltage_source()|"),
        (b"|dc|", b"|dc\x00|"),
        (b"|float|voltage|string|qa_vp", b"|float|voltage|string|VAR(qa_vp)"),
        (b"|float|voltage|string|qa_vp", b"|float|voltage|string|qa_vp+0"),
        (b"|float|voltage|string|qa_vp", b"|float|voltage|symbol|0.5"),
        (b"|float|voltage|string|qa_vp", b"|float|voltage|flonum|qa_vp"),
        (b"|float|voltage|string|qa_vp", b"|-|voltage|string|qa_vp"),
        (b"|float|voltage|string|qa_vp", b"|float||string|qa_vp"),
        (b"observed|float|voltage|string|qa_vp", b"missing|-|-|-|0.5"),
        (b"observed|float|voltage|string|qa_vp", b"verified|float|voltage|string|qa_vp"),
        (b"SCAN|1|1", b"SCAN|01|1"),
        (b"SCAN|1|1", b"SCAN|0|1"),
        (b"SCAN|1|1", b"SCAN|1|33"),
        (b"BIND|1", b"BIND|2"),
        (b"COMPLETE|2|2|2", b"COMPLETE|1|2|2"),
        (b"COMPLETE|2|2|2", b"COMPLETE|2|3|2"),
        (b"COMPLETE|2|2|2", b"COMPLETE|2|2|3"),
        (b"COMPLETE|2|2|2", b"COMPLETE|65|2|2"),
    ],
)
def test_response_rejects_identity_expression_representation_and_count_drift(
    old: bytes, new: bytes,
) -> None:
    with pytest.raises(ValueError):
        parse_frame(frame().replace(old, new), request())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw[:-1],
        lambda raw: raw[: raw.rfind(b"COMPLETE")],
        lambda raw: raw + b"COMPLETE|2|2|2\n",
        lambda raw: raw + b"\n",
        lambda raw: raw.replace(b"\n", b"\r\n"),
        lambda raw: raw.replace(b"SCAN|1|1", b"\xff"),
        lambda raw: raw.replace(b"SCAN|1|1", b"SCAN|1|1\x1b"),
        lambda raw: raw.replace(b"SCAN|2|1", b"SCAN|2|1|extra"),
        lambda raw: raw.replace(b"SCAN|1|1\n", b""),
        lambda raw: raw.replace(b"SCAN|2|1", b"VARIABLE|extra|other"),
        lambda raw: raw.replace(b"SOURCE|", b" SOURCE|"),
    ],
)
def test_response_rejects_incomplete_extra_and_non_ascii_frames(mutate: Any) -> None:
    with pytest.raises(ValueError):
        parse_frame(mutate(frame()), request())


def test_response_size_bound_includes_framing_and_newlines() -> None:
    with pytest.raises(ValueError):
        parse_frame(b"x" * 65_536 + b"\n", request())
    with pytest.raises(ValueError):
        parse_frame(frame() + b"x" * 65_536, request())


def test_missing_variable_cannot_be_a_complete_success() -> None:
    with pytest.raises(ValueError, match="missing variable"):
        parse_frame(frame(body=["SCAN|1|1", binding()], complete="COMPLETE|1|1|1"), request())


def test_multiple_exact_references_are_bounded_and_do_not_qualify_numbers() -> None:
    data = request_data()
    data["variables"] = data["variables"][:1]
    scan = request(data)
    body = [
        value
        for n in range(1, 5)
        for value in (f"SCAN|{n}|1", binding(n, instance=f"Source{n}"))
    ]
    result = parse_frame(frame(scan, body, "COMPLETE|4|4|4"), scan)
    assert result["qualification"] == "NOT_ESTABLISHED_BY_BINDING_SCAN"
    body += ["SCAN|5|1", binding(5, instance="Source5")]
    with pytest.raises(ValueError, match="excessive binding matches"):
        parse_frame(frame(scan, body, "COMPLETE|5|5|5"), scan)


@pytest.mark.parametrize(
    "body,complete",
    [
        (["SCAN|1|2", binding(), binding()], "COMPLETE|1|2|2"),
        (["SCAN|1|2", binding(), binding(
            logical_id="input-minus", cadence_binding="qa_vm",
            cdf="observed|float|voltage|string|qa_vm",
        )], "COMPLETE|1|2|2"),
        (["SCAN|1|1", binding(), "SCAN|2|1", binding(2)], "COMPLETE|2|2|2"),
        (["SCAN|1|0", binding()], "COMPLETE|1|0|1"),
        (["SCAN|1|2", binding(), binding(instance="Other")], "COMPLETE|1|2|2"),
        (["SCAN|1|2", binding(), binding(property_name="ac").replace(
            "SyntheticDevices", "OtherDevices")], "COMPLETE|1|2|2"),
    ],
)
def test_duplicate_alias_scan_and_master_conflicts_fail_closed(
    body: list[str], complete: str,
) -> None:
    with pytest.raises(ValueError):
        parse_frame(frame(body=body, complete=complete), request())


def test_maximum_complete_scan_and_match_counts_are_accepted() -> None:
    data = request_data()
    data["variables"] = [
        {"logical_id": f"variable-{n}", "cadence_binding": f"var_{n}"} for n in range(4)
    ]
    scan = request(data)
    body = []
    for ordinal in range(1, 65):
        body.append(f"SCAN|{ordinal}|32")
        if ordinal <= 16:
            n = (ordinal - 1) // 4
            body.append(binding(
                ordinal, f"variable-{n}", f"var_{n}", f"Source{ordinal}",
                cdf="missing|-|-|-|-",
            ))
    result = parse_frame(frame(scan, body, "COMPLETE|64|2048|16"), scan)
    assert result["scan_counts"] == {"instances": 64, "properties": 2048, "matches": 16}


def test_render_is_fixed_owned_copy_read_only_and_bound_to_request() -> None:
    scan = request()
    program = render_collector(scan).decode("ascii")
    assert 'outfile("binding-frame.txt")' in program
    assert 'dbOpenCellViewByType("SyntheticSources" "SyntheticCell" "schematic" "" "r")' in program
    assert scan.observation_id in program
    assert scan.nonce in program
    assert canonical_digest(scan) in program
    assert 'list("input-plus" "qa_vp")' in program
    assert "bindingBytes>65536" in program
    assert "length(bindingCv~>instances)>64" in program
    assert "count>32" in program
    assert "hits>4 matchTotal>16" in program
    assert "cdfFindParamByName(cdf property)" in program
    for denied in (
        "dbSave", "dbCreate", "dbReplace", "dbDelete", "cdfGetBaseCellCDF", "~>parameters",
        "defValue", "asi", "createNetlist", "simulator(", "run(", "eval(", "load(", "system(",
    ):
        assert denied not in program
    assert "@" not in program
    # Syntax balance is a local structural check, not an actual SKILL execution.
    import re

    structure = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"|;[^\n]*', "", program)
    assert structure.count("(") == structure.count(")")


def test_request_digest_matches_the_single_worker_renderer() -> None:
    from cadence_mcp_bridge import _binding_observation

    scan = request()
    assert canonical_digest(scan) == _binding_observation.digest(  # type: ignore[no-untyped-call]
        _binding_observation.canonical(scan.model_dump(mode="json"))  # type: ignore[no-untyped-call]
    )
    assert render_collector(scan) == _binding_observation.render_collector(  # type: ignore[no-untyped-call]
        scan.model_dump(mode="json")
    )
