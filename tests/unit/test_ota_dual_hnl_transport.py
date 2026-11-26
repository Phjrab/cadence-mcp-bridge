"""Check both original OTA netlists and the durable reopened-phase binding."""

import json
import sys
from contextlib import nullcontext
from hashlib import sha256
from importlib.resources import files
from io import StringIO
from types import SimpleNamespace

import pytest
from cadence_mcp_bridge.ota_dual_hnl_transport import read_ota_dual_hnl
from test_registered_mos_sizing import _fixture

from cadence_mcp_bridge import registered_mos_transport
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.registered_mos_edit import NativeMosEditSave
from cadence_mcp_bridge.registered_mos_sizing_transport import _ota_supervisor, _SizingPhaseProvider
from cadence_mcp_bridge.registered_mos_transport import _encode

PREVIOUS = "f" * 64
MANAGED = "/managed"


@pytest.fixture
def capture():
    _, _, _, _, _, _, captured = _fixture()
    dc_input = b"simulator lang=spectre\ndc dc\n"
    observed = captured.readback
    terminal = {
        "readback": observed.model_dump(mode="json"),
        "input_base64": _encode(captured.netlist),
        "dc_input_base64": _encode(dc_input),
        "cdf_frame_base64": _encode(captured.cdf_frame),
        "diagnostics": {
            "schema_version": 1,
            "ocean_invocations": 1,
            "spectre": 0,
            "reservations": 0,
        },
    }
    for mode, data in (("ac", captured.netlist), ("dc", dc_input)):
        operation = observed.operation_id
        root = f"{MANAGED}/native-mcp-v1-jobs/{operation}/{operation}/{mode}"
        cell = "Grel_" + operation.replace("-", "_")
        alias = "MCP_GREL_Work" if mode == "ac" else "MCP_GREL_WorkDc"
        terminal["diagnostics"][mode] = {
            "analysis": mode,
            "operation_id": observed.operation_id,
            "scope_sha256": observed.scope_sha256,
            "saved_receipt_sha256": PREVIOUS,
            "dut_revision_sha256": observed.netlisted_revision_sha256,
            "testbench_revision_sha256": observed.netlisted_testbench_revision_sha256,
            "isolated_bench_tree_sha256": "a" * 64,
            "isolated_state_tree_sha256": "b" * 64,
            "project_tree_sha256": "c" * 64,
            "registered_inputs_sha256": "d" * 64,
            "hnl_stdout_sha256": "e" * 64,
            "state_path": f"{root}/state-root/{alias}/{cell}/spectre/state1",
            "project_path": f"{root}/project",
            "input_path": f"{root}/project/netlist/input.scs",
            "netlist_sha256": sha256(data).hexdigest(),
            "enabled_analyses": [mode],
            "netlisted": True,
        }
    return terminal, captured, dc_input


def test_ota_reopen_retains_both_original_netlists(capture):
    terminal, captured, dc_input = capture
    original, receipt, ac, dc = read_ota_dual_hnl(
        _canonical(terminal), PREVIOUS, managed_root=MANAGED
    )
    assert original.readback == captured.readback
    assert ac == captured.netlist and dc == dc_input
    assert receipt.ocean_invocations == 1 and receipt.spectre == receipt.reservations == 0


def test_v2_terminal_allows_two_exactly_bounded_inputs(capture):
    terminal, _, _ = capture
    ac, dc = b"a" * 32_768, b"d" * 32_768
    for mode, raw, key in (("ac", ac, "input_base64"), ("dc", dc, "dc_input_base64")):
        terminal[key] = _encode(raw)
        terminal["diagnostics"][mode]["netlist_sha256"] = sha256(raw).hexdigest()
    terminal["readback"]["netlist_sha256"] = sha256(ac).hexdigest()
    wire = _canonical(terminal)
    assert 65_536 < len(wire) <= 524_288
    _, _, observed_ac, observed_dc = read_ota_dual_hnl(wire, PREVIOUS, managed_root=MANAGED)
    assert (observed_ac, observed_dc) == (ac, dc)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ocean_invocations", 2),
        ("ocean_invocations", True),
        ("spectre", 1),
        ("reservations", 1),
    ],
)
def test_ota_reopen_rejects_wrong_phase_custody(capture, key, value):
    terminal, _, _ = capture
    terminal["diagnostics"][key] = value
    with pytest.raises(ValueError):
        read_ota_dual_hnl(_canonical(terminal), PREVIOUS, managed_root=MANAGED)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("enabled_analyses", ["ac"]),
        ("netlisted", False),
        ("netlisted", 1),
        ("input_path", "/managed/outside/input.scs"),
        ("state_path", "/managed/other-state"),
        ("netlist_sha256", "0" * 64),
        ("saved_receipt_sha256", "0" * 64),
        ("dut_revision_sha256", "0" * 64),
        ("hnl_stdout_sha256", "0" * 64),
    ],
)
def test_ota_reopen_rejects_invalid_second_original(capture, key, value):
    terminal, _, _ = capture
    terminal["diagnostics"]["dc"][key] = value
    with pytest.raises(ValueError):
        read_ota_dual_hnl(_canonical(terminal), PREVIOUS, managed_root=MANAGED)


def test_ota_reopen_rejects_missing_or_overlapping_project(capture):
    terminal, _, _ = capture
    original = terminal["diagnostics"]["dc"].copy()
    terminal["diagnostics"]["dc"]["project_path"] = terminal["diagnostics"]["ac"]["project_path"]
    terminal["diagnostics"]["dc"]["input_path"] = terminal["diagnostics"]["ac"]["input_path"]
    with pytest.raises(ValueError):
        read_ota_dual_hnl(_canonical(terminal), PREVIOUS, managed_root=MANAGED)
    terminal["diagnostics"]["dc"] = original
    terminal.pop("dc_input_base64")
    with pytest.raises(ValueError):
        read_ota_dual_hnl(_canonical(terminal), PREVIOUS, managed_root=MANAGED)


def test_v2_support_is_hash_bound_and_does_not_consume_phase_json(monkeypatch):
    asset, supervisor, framed_support = _ota_supervisor(2)
    runtime = files("cadence_mcp_bridge").joinpath(asset).read_bytes()
    assert len(supervisor) <= 131_072 and supervisor.endswith(runtime)
    header = compile(supervisor[: -len(runtime)], "v2-fixed-header", "exec")
    phase = b'{"original_phase_packet":"unchanged"}'
    stream = StringIO((framed_support + phase).decode("ascii"))
    monkeypatch.setattr(sys, "stdin", stream)
    namespace = {"__name__": "__main__"}
    exec(header, namespace)
    assert stream.read().encode("ascii") == phase
    assert (
        _encode(namespace["OTA_V1_RUNTIME_SOURCE"])
        == json.loads(framed_support)["OTA_V1_RUNTIME_SOURCE"]
    )
    monkeypatch.setattr(sys, "stdin", StringIO((b"[" + framed_support[1:] + phase).decode("ascii")))
    with pytest.raises(ValueError, match="OTA v2 packaged support"):
        exec(header, {"__name__": "__main__"})


@pytest.mark.parametrize("lose_dc", [False, True])
def test_v2_durable_submit_and_same_id_replay_gate_both_modes(
    tmp_path, monkeypatch, capture, lose_dc
):
    terminal, captured, _ = capture
    _, _, candidate, _, binding, _, _ = _fixture()
    save = NativeMosEditSave.model_validate(
        captured.readback.model_dump(include=set(NativeMosEditSave.model_fields))
    )
    save_raw = _canonical(save.model_dump(mode="json"))
    for mode in ("ac", "dc"):
        terminal["diagnostics"][mode]["saved_receipt_sha256"] = sha256(save_raw).hexdigest()
    if lose_dc:
        terminal.pop("dc_input_base64")
    provider = object.__new__(_SizingPhaseProvider)
    provider._directory = tmp_path
    provider._enrollment = SimpleNamespace(schema_version=6)
    provider._scope = SimpleNamespace(candidate_request=candidate)
    provider._enrollment_sha = "a" * 64
    provider._context = SimpleNamespace(
        contracts=SimpleNamespace(
            environment=SimpleNamespace(paths=SimpleNamespace(managed_root=MANAGED))
        )
    )
    monkeypatch.setattr(registered_mos_transport, "resource_lock", lambda _: nullcontext())
    monkeypatch.setattr(provider, "_prepare", lambda _, phase, __: ([phase], b"fixed"))
    monkeypatch.setattr(provider, "_saved", lambda *args: save)
    dispatched = []

    def fake_run(argv, _payload, _env, **_limits):
        dispatched.append(argv[0])
        return 0, save_raw if argv[0] == "EDIT_SAVE" else _canonical(terminal), b""

    monkeypatch.setattr(registered_mos_transport, "run_fixed", fake_run)
    assert provider.claim(binding)
    if lose_dc:
        with pytest.raises(ValueError):
            provider.dispatch(binding)
    else:
        assert provider.dispatch(binding).capture == captured
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}
    assert provider.lookup(binding).capture == (None if lose_dc else captured)
    assert not provider.claim(binding)
    assert dispatched == ["EDIT_SAVE", "INDEPENDENT_REOPEN_NETLIST"]
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == before
