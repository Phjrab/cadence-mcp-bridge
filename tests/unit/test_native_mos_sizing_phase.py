# The guest modules also run under Python 2.6 and expose unannotated entry points.
# mypy: disable-error-code="no-untyped-call"

import base64
import hashlib
import io
import re
from inspect import getfile
from pathlib import Path
from typing import Any

import pytest

from cadence_mcp_bridge import _amp_pm0_default_phase as support
from cadence_mcp_bridge import _mos_cdf_call_contract as callback
from cadence_mcp_bridge import _mos_pmos_width_callback as width_callback
from cadence_mcp_bridge import _mos_wlm_callback as wlm_callback
from cadence_mcp_bridge import _mos_wlm_phase as wlm_phase
from cadence_mcp_bridge import _registered_mos_edit_phase as guest
from cadence_mcp_bridge.mos_wl_skill import render_mos_wl_skill


def _row(value: str, units: str | None = None) -> dict[str, str | None]:
    return dict(
        oa_type="string", oa_value=value, cdf_type="instData", cdf_units=units, cdf_value=value
    )


def _before() -> dict[str, dict[str, str | None]]:
    return {
        "w": _row("120n", "lengthMetric"),
        "fw": _row("120n", "lengthMetric"),
        "l": _row("100n", "lengthMetric"),
        "m": _row("1"),
        "fingers": _row("1"),
        "as": _row("69.6f"),
        "ad": _row("69.6f"),
        "ps": _row("1.16u", "lengthMetric"),
        "pd": _row("1.16u", "lengthMetric"),
        "nf": dict.fromkeys(("oa_type", "oa_value", "cdf_type", "cdf_units", "cdf_value")),
        "model": _row("gpdk090_nmos1v"),
        "dfm": _row("Minimum"),
    }


def test_native_sizing_checks_actual_new_length_and_fixed_properties() -> None:
    before = _before()
    expected = {"w": {"value": "120", "unit": "nm"}, "l": {"value": "250", "unit": "nm"}}
    observed = dict(before, l=_row("0.25u", "lengthMetric"))
    # Derived geometry is observed, and no anticipated after-tuple is loaded.
    observed["as"] = _row("72f")
    guest.sizing_readback(before, observed, expected)
    with pytest.raises(ValueError, match="sizing_dimension"):
        guest.sizing_readback(before, dict(observed, l=before["l"]), expected)
    with pytest.raises(ValueError, match="sizing_property_conservation"):
        guest.sizing_readback(before, dict(observed, m=_row("2")), expected)
    with pytest.raises(ValueError, match="sizing_geometry_persistence"):
        guest.sizing_readback(
            before, dict(observed, ad=dict(_row("72f"), oa_value="69.6f")), expected
        )


def test_callback_child_uses_fixed_digest_and_strict_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = b"fixture()"
    pin = hashlib.sha256(raw).hexdigest().encode("ascii")
    monkeypatch.setattr(callback, "NMOS_LENGTH_CALLBACK_SHA256", pin)
    assert callback.check_length_callback(io.BytesIO(b"nmos1v|l|9\n" + raw + b"\nEND\n"))
    assert not callback.check_length_callback(io.BytesIO(b"nmos1v|w|9\n" + raw + b"\nEND\n"))
    assert not callback.check_length_callback(io.BytesIO(b"nmos1v|l|9\n" + raw + b"\nBAD\n"))
    assert not callback.check_length_callback(io.BytesIO(b"nmos1v|l|4097\n"))
    assert not callback.check_length_callback(io.BytesIO(b"nmos1v|l|9\nother()x!\nEND\n"))


def test_callback_child_uses_verified_phase_path_and_source_pin() -> None:
    work = "/home/buet/native-jobs/copy-1/edit/work"
    rendered = guest.render(guest.VERIFY_LENGTH_CALLBACK, {"@WORK@": work})
    assert b"@WORK@" not in rendered
    command = (
        b"/usr/bin/python -E -s -B " + work.encode("ascii") + b"/verify-nmos-length-callback.py"
    )
    assert command in rendered
    assert (
        hashlib.sha256(Path(getfile(callback)).read_bytes()).hexdigest()
        == guest.SIZING_HASH_CHILD_SHA256
    )


def test_length_job_renders_complete_baseline_and_only_held_fields_afterward() -> None:
    job = guest.Source9MosJob.__new__(guest.Source9MosJob)
    job.sizing = (b"fixed adapter", b"fixed verifier")
    job.route = {"before": _before()}
    job.library = "CmosLongMosFixture"
    job.owned = "/home/buet/owned"
    job.source = "/home/buet/source"
    job.source_alias = guest.SOURCE
    job.operation = "00e78318-9c30-4064-9233-5d7d9827ff70"

    values = job.values("/home/buet/job/edit/work")
    before = set(re.findall(r'\("([a-z]+)"', values["@BEFORE@"]))
    after = set(re.findall(r'\("([a-z]+)"', values["@AFTER@"]))
    assert before == set(guest.PROPERTIES)
    assert after == before.difference(guest.SIZING_OVERRIDES)

    edit = guest.render(guest.COMMON + guest.EDIT, values)
    reopen = guest.render(guest.COMMON + guest.REOPEN, values)
    assert values["@BEFORE@"].encode("ascii") in edit
    assert values["@AFTER@"].encode("ascii") in edit
    assert values["@AFTER@"].encode("ascii") in reopen
    assert b"mcpMosApplyWL(inst)==t" in edit
    assert b"mcpMosApplyWL(" not in reopen


def _width_scope() -> dict[str, Any]:
    target = dict(
        instance=dict(
            instance_path="DUT/MP",
            master_library="gpdk090",
            master_cell="pmos1v",
            master_view="symbol",
            property_name="w",
        ),
        netlist_path="DUT/MP",
        netlist_model="gpdk090_pmos1v",
        netlist_terminals=["vout", "vin", "vdd", "vdd"],
    )
    before = dict(
        _before(),
        w=_row("350n", "lengthMetric"),
        fw=_row("350n", "lengthMetric"),
        model=_row("gpdk090_pmos1v"),
        ad=_row("98f"),
        ps=_row("1.26u", "lengthMetric"),
        pd=_row("1.26u", "lengthMetric"),
        dfm=dict(_row("Minimum"), oa_type=None, oa_value=None),
    )
    before["as"] = _row("98f")
    baseline = {"fixture": "common original"}
    qualification = dict(
        source_library=guest.SOURCE,
        source_cell=guest.DUT,
        testbench_cell=guest.TB,
        target=target,
        before=before,
        baseline=baseline,
        support={
            "cadence_version": "6.1.5.500.15",
            "pdk_release": "4.6",
            "pdk_identity_sha256": guest.SIZING_PDK_TREE_SHA256,
            "adapter_sha256": guest.SIZING_RENDERER_SHA256,
            "w": {},
            "l": None,
        },
    )
    current = {"w": {"value": "350", "unit": "nm"}, "l": {"value": "100", "unit": "nm"}}
    width = {"value": "3000", "unit": "nm"}
    return dict(
        route_qualification=qualification,
        plan=dict(
            baseline=baseline,
            target=target,
            route_sha256="route",
            changed=["w"],
            current=current,
            requested={"w": width, "l": None},
            expected={"w": width, "l": current["l"]},
            allowed_derived=["fw", "as", "ad", "ps", "pd"],
        ),
        subject=dict(
            owned_cell=guest.DUT,
            owned_view="schematic",
            owned_library="CmosLongMosWidthFixture",
            route_sha256="route",
        ),
    )


def test_width_scope_selects_exact_pmos_total_width_candidate() -> None:
    scope = _width_scope()
    assert guest.sizing_route(scope) == scope["route_qualification"]
    scope["plan"]["expected"]["w"]["value"] = "3001"
    with pytest.raises(ValueError, match="sizing_width_scope"):
        guest.sizing_route(scope)
    scope = _width_scope()
    scope["plan"]["expected"]["l"] = {"value": "250", "unit": "nm"}
    with pytest.raises(ValueError, match="sizing_route"):
        guest.sizing_route(scope)
    scope = _width_scope()
    scope["plan"]["target"]["instance"]["master_cell"] = "nmos1v"
    with pytest.raises(ValueError, match="sizing_route"):
        guest.sizing_route(scope)


def test_width_readback_accepts_numeric_equivalence_and_protects_held_rows() -> None:
    scope = _width_scope()
    before = scope["route_qualification"]["before"]
    expected = scope["plan"]["expected"]
    observed = dict(before, w=_row("3u", "lengthMetric"), fw=_row("3000n", "lengthMetric"))
    observed["as"] = _row("720f")
    guest.sizing_readback(before, observed, expected, "w")
    with pytest.raises(ValueError, match="sizing_dimension"):
        guest.sizing_readback(before, dict(observed, fw=before["fw"]), expected, "w")
    with pytest.raises(ValueError, match="sizing_property_conservation"):
        guest.sizing_readback(before, dict(observed, l=_row("250n", "lengthMetric")), expected, "w")
    with pytest.raises(ValueError, match="sizing_geometry_persistence"):
        guest.sizing_readback(
            before, dict(observed, ad=dict(_row("720f"), oa_value="98f")), expected, "w"
        )


def test_width_assets_require_exact_width_child_and_bound_adapter() -> None:
    scope = _width_scope()
    program = render_mos_wl_skill("pmos1v", width_nm="3000", width_field="w")
    child = Path(getfile(width_callback)).read_bytes()

    def dispatch(adapter: bytes, verifier: bytes) -> Any:
        payload = support.canonical(
            dict(
                adapter=adapter.decode("ascii"),
                adapter_sha256=support.sha(adapter),
                hash_child=verifier.decode("ascii"),
                hash_child_sha256=support.sha(verifier),
            )
        )
        scope["sizing_sha256"] = support.sha(payload)
        packet = {"sizing_base64": base64.b64encode(payload).decode("ascii")}
        return guest.read_sizing_assets(support, packet, scope)

    assert dispatch(program, child) == (program, child)
    with pytest.raises(ValueError, match="sizing_asset_identity"):
        dispatch(program, Path(getfile(callback)).read_bytes())
    with pytest.raises(ValueError, match="sizing_width_adapter"):
        dispatch(render_mos_wl_skill("pmos1v", width_nm="3000", width_field="fw"), child)


def test_width_edit_and_detached_reopen_select_mp_and_hold_length() -> None:
    scope = _width_scope()
    job = guest.Source9MosJob.__new__(guest.Source9MosJob)
    job.sizing = (b"fixed adapter", b"fixed verifier")
    job.axis = guest.sizing_axis(scope["plan"])
    job.route = scope["route_qualification"]
    job.library = scope["subject"]["owned_library"]
    job.owned = "/home/buet/owned"
    job.source = "/home/buet/source"
    job.source_alias = guest.SOURCE
    job.operation = "00e78318-9c30-4064-9233-5d7d9827ff70"
    values = job.values("/home/buet/job/edit/work")
    assert (values["@TARGET@"], values["@MASTER@"], values["@RAIL@"]) == ("MP", "pmos1v", "vdd")
    held = set(re.findall(r'\("([a-z]+)"', values["@AFTER@"]))
    assert held == set(guest.PROPERTIES).difference(guest.WIDTH_SIZING_OVERRIDES)
    assert "l" in held
    edit = guest.render(guest.COMMON + guest.VERIFY_WIDTH_CALLBACK + guest.EDIT, values)
    reopen = guest.render(guest.COMMON + guest.REOPEN, values)
    assert b'cdfFindParamByName(base "w")' in edit
    assert b"param~>callback==body" in edit
    assert b"verify-pmos-width-callback.py" in edit
    assert b"verify-nmos-length-callback.py" not in edit
    assert b"mcpMosApplyWL(" not in reopen
    assert b"dbSave(" not in reopen


def test_sizing_trace_surrounds_the_existing_checks_and_save() -> None:
    work = "/home/buet/job/edit/work"
    tokens = {name: name for name in set(re.findall(r"@[A-Z]+@", guest.SIZING_EDIT))}
    tokens.update({"@WORK@": work, "@AFTER@": "heldPropertyCheck()"})
    rendered = guest.render(guest.SIZING_EDIT, tokens)
    legacy = guest.render(guest.EDIT, tokens)
    assert b"MCP_MOS_WL_EDIT|" not in legacy
    assert b"MCP_MOS_WL_TIME|" not in legacy
    assert b"drain(poport)" in rendered
    assert b'printf("MCP_MOS_WL_EDIT|%s|%s\\n" step state)\n drain(poport)' in rendered
    assert b'infile("/proc/uptime")' in rendered
    assert b"errset(mosSizingUptime() nil)" in rendered
    calls = (
        b'mosSizingTrace("SCH_CHECK" "STARTED")',
        b'mosSizingCheck("SCH_CHECK" schCheck(child))',
        b'mosSizingTrace("FOOTPRINT" "STARTED")',
        b'mosSizingCheck("FOOTPRINT" equal(stable mosFoot(child omit)))',
        b'mosSizingTrace("HELD_PROPERTIES" "STARTED")',
        b"heldPropertyCheck()",
        b'mosSizingTrace("HELD_PROPERTIES" "RETURNED_OK")',
        b'mosSizingTrace("EVIDENCE" "STARTED")',
        b'/saved.properties" inst)',
        b'mosSizingTrace("EVIDENCE" "RETURNED_OK")',
        b'mosSizingTrace("DB_SAVE" "STARTED")',
        b'mosSizingCheck("DB_SAVE" dbSave(child))',
        b'mosSizingTrace("DB_CLOSE" "STARTED")',
        b'mosSizingCheck("DB_CLOSE" dbClose(child))',
        b"C6_MOS_EDIT_SAVED|",
    )
    offsets = [rendered.index(call) for call in calls]
    assert offsets == sorted(offsets)
    for held_call in (b"schCheck(child)", b"dbSave(child)", b"dbClose(child)"):
        assert rendered.count(held_call) == legacy.count(held_call)


def test_sizing_trace_records_only_complete_ordered_steps() -> None:
    # The retained W3000 job ended at this last callback marker. It cannot
    # establish a post-callback step, even if the supervisor killed the child.
    retained_prefix = (
        b"MCP_MOS_WL_STAGE|INIT\nMCP_MOS_WL_STAGE|FIELD|w\n"
        b"MCP_MOS_WL_STAGE|COMMIT\nMCP_MOS_WL_STAGE|DONE\n"
        b"MCP_MOS_WL_READY_FOR_SAVE_CHECK\n"
    )
    assert guest.sizing_edit_trace(retained_prefix) is None
    first = retained_prefix + b"MCP_MOS_WL_EDIT|SCH_CHECK|STARTED\n"
    assert guest.sizing_edit_trace(first) == dict(step="SCH_CHECK", state="STARTED")
    assert guest.sizing_edit_trace(first + b"MCP_MOS_WL_EDIT|SCH_CHECK|RETURNED_NIL\n") == dict(
        step="SCH_CHECK", state="RETURNED_NIL"
    )
    assert guest.sizing_edit_trace(first + b"MCP_MOS_WL_EDIT|FOOTPRINT|STARTED\n") is None
    assert guest.sizing_edit_trace(first + b"MCP_MOS_WL_EDIT|SCH_CHECK|RETURNED_OK") == dict(
        step="SCH_CHECK", state="STARTED"
    )
    earlier = b"".join(
        f"MCP_MOS_WL_EDIT|{step}|{state}\n".encode("ascii")
        for step in ("SCH_CHECK", "FOOTPRINT", "HELD_PROPERTIES", "EVIDENCE")
        for state in ("STARTED", "RETURNED_OK")
    )
    saving = earlier + b"MCP_MOS_WL_EDIT|DB_SAVE|STARTED\n"
    assert guest.sizing_edit_trace(saving) == dict(step="DB_SAVE", state="STARTED")
    saved = saving + b"MCP_MOS_WL_EDIT|DB_SAVE|RETURNED_OK\n"
    assert guest.sizing_edit_trace(saved) == dict(step="DB_SAVE", state="RETURNED_OK")
    assert guest.sizing_edit_trace(saved + b"MCP_MOS_WL_EDIT|DB_CLOSE|STARTED\n") == dict(
        step="DB_CLOSE", state="STARTED"
    )


def test_sizing_time_is_bound_to_ordered_completed_edges() -> None:
    start = b"MCP_MOS_WL_EDIT|SCH_CHECK|STARTED\n"
    first = b"MCP_MOS_WL_TIME|SCH_CHECK|STARTED|320.20\n"
    end = b"MCP_MOS_WL_EDIT|SCH_CHECK|RETURNED_OK\n"
    last = b"MCP_MOS_WL_TIME|SCH_CHECK|RETURNED_OK|321.53\n"
    assert guest.sizing_edit_timing(start + first + end + last) == [
        dict(step="SCH_CHECK", state="STARTED", elapsed_centiseconds=0),
        dict(step="SCH_CHECK", state="RETURNED_OK", elapsed_centiseconds=133),
    ]
    assert guest.sizing_edit_timing(start + end) is None
    assert guest.sizing_edit_timing(start + first + end + last.rstrip()) == [
        dict(step="SCH_CHECK", state="STARTED", elapsed_centiseconds=0)
    ]
    assert guest.sizing_edit_timing(start + first + first) is None
    assert guest.sizing_edit_timing(start + first + end + last.replace(b"321", b"319")) is None
    assert guest.sizing_edit_timing(start + first + end + last.replace(b"321", b"399")) is None
    wrong_step = last.replace(b"SCH_CHECK", b"DB_SAVE")
    assert guest.sizing_edit_timing(start + first + end + wrong_step) is None


def _wlm_scope(axes: str = "lwm") -> dict[str, Any]:
    scope = _width_scope()
    route, plan = scope["route_qualification"], scope["plan"]
    current = {"w": {"value": "350", "unit": "nm"}, "l": {"value": "100", "unit": "nm"}, "m": 1}
    chosen = {"w": {"value": "16000", "unit": "nm"}, "l": {"value": "1000", "unit": "nm"}, "m": 6}
    route["support"].update(
        lifecycle=guest.WLM_LIFECYCLE,
        adapter_sha256=guest.WLM_RENDERER_SHA256,
        l={},
        m=[1, 6],
    )
    plan.update(
        current=current,
        requested={axis: chosen[axis] for axis in axes},
        expected={axis: chosen[axis] if axis in axes else value for axis, value in current.items()},
        changed=list(axes),
        allowed_derived=list(wlm_phase.wlm_overrides(guest, axes)[len(axes) :]),
    )
    return scope


def test_wlm_callback_frames_verify_only_selected_ordered_pinned_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert hashlib.sha256(Path(getfile(wlm_callback)).read_bytes()).hexdigest() == (
        guest.WLM_HASH_CHILD_SHA256
    )
    bodies = {b"l": b"a()\nb()", b"w": b"width()", b"m": b"m()"}
    for axis, body in bodies.items():
        monkeypatch.setitem(wlm_callback.CALLBACKS, axis, hashlib.sha256(body).hexdigest().encode())

    def frame(axes: bytes, master: bytes = b"pmos1v") -> bytes:
        return (
            b"headless_wlm_v1|"
            + master
            + b"|"
            + axes
            + b"\n"
            + b"".join(
                b"%s|%d\n%s\n" % (axis, len(bodies[axis]), bodies[axis])
                for axis in (bytes((key,)) for key in axes)
            )
            + b"END\n"
        )

    assert wlm_callback.check_callbacks(io.BytesIO(frame(b"lwm")))
    assert wlm_callback.check_callbacks(io.BytesIO(frame(b"wm", b"nmos1v")))
    assert wlm_callback.check_callbacks(io.BytesIO(frame(b"m")))
    assert not wlm_callback.check_callbacks(io.BytesIO(frame(b"wlm")))
    assert not wlm_callback.check_callbacks(io.BytesIO(frame(b"ll")))
    assert not wlm_callback.check_callbacks(io.BytesIO(frame(b"")))
    assert not wlm_callback.check_callbacks(io.BytesIO(frame(b"m", b"pmos2v")))
    assert not wlm_callback.check_callbacks(io.BytesIO(frame(b"m").replace(b"m()", b"x()")))
    assert not wlm_callback.check_callbacks(io.BytesIO(frame(b"m").replace(b"m|3", b"m|4097")))
    assert not wlm_callback.check_callbacks(io.BytesIO(frame(b"m")[:-4]))


def test_wlm_route_and_readback_reject_wrong_axes_target_and_geometry() -> None:
    scope = _wlm_scope()
    route = guest.sizing_route(scope)
    before = route["before"]
    expected = scope["plan"]["expected"]
    saved = dict(
        before,
        w=_row("16u", "lengthMetric"),
        fw=_row("16000n", "lengthMetric"),
        l=_row("1u", "lengthMetric"),
        m=_row("6"),
    )
    saved["as"] = _row("5f")
    wlm_phase.wlm_readback(guest, before, saved, expected, ("l", "w", "m"))
    for name, row in (
        ("m", _row("1")),
        ("fw", _row("15999n", "lengthMetric")),
        ("l", _row("999n", "lengthMetric")),
        ("fingers", _row("2")),
        ("dfm", _row("Wide")),
    ):
        with pytest.raises(ValueError):
            wlm_phase.wlm_readback(
                guest, before, dict(saved, **{name: row}), expected, ("l", "w", "m")
            )
    m_only = _wlm_scope("m")
    mono = guest.sizing_route(m_only)
    observed = dict(mono["before"], m=_row("6"))
    wlm_phase.wlm_readback(guest, mono["before"], observed, m_only["plan"]["expected"], ("m",))
    with pytest.raises(ValueError, match="sizing_property_conservation"):
        observed["as"] = _row("5f")
        wlm_phase.wlm_readback(guest, mono["before"], observed, m_only["plan"]["expected"], ("m",))
    scope["plan"]["changed"] = ["w", "l", "m"]
    with pytest.raises(ValueError, match="wlm_change_set"):
        guest.sizing_route(scope)
    scope = _wlm_scope()
    scope["route_qualification"]["support"]["m"] = [1]
    with pytest.raises(ValueError, match="wlm_multiplier_admission"):
        guest.sizing_route(scope)
    scope = _wlm_scope()
    scope["route_qualification"]["target"]["netlist_terminals"][-1] = "vss"
    with pytest.raises(ValueError, match="wlm_route"):
        guest.sizing_route(scope)


def test_wlm_render_uses_batched_properties_and_distinct_read_only_reopen() -> None:
    scope = _wlm_scope()
    job = guest.Source9MosJob.__new__(guest.Source9MosJob)
    job.scope = scope
    job.sizing = (b"fixed adapter", b"fixed child")
    job.wlm_axes = ("l", "w", "m")
    job.wlm_phase = wlm_phase
    job.route = guest.sizing_route(scope)
    job.library = scope["subject"]["owned_library"]
    job.owned = "/home/buet/owned"
    job.source = "/home/buet/source"
    job.source_alias = guest.SOURCE
    job.operation = "00e78318-9c30-4064-9233-5d7d9827ff70"
    values = job.values("/home/buet/job/edit/work")
    before, after = values["@BEFORE@"], values["@AFTER@"]
    assert before.count("cdfGetInstCDF(inst)") == 1
    assert set(re.findall(r'\("([a-z]+)"', before)) == set(guest.PROPERTIES)
    held, expected = after.split("let((param prop", 1)
    assert after.count("cdfGetInstCDF(inst)") == 1
    assert set(re.findall(r'\("([a-z]+)"', held)) == {"fingers", "nf", "model", "dfm"}
    assert '("l" "1000n") ("w" "16000n") ("fw" "16000n") ("m" "6")' in expected
    edit = guest.render(guest.COMMON + wlm_phase.VERIFY_WLM_CALLBACKS + guest.SIZING_EDIT, values)
    reopen = guest.render(guest.COMMON + guest.REOPEN, values)
    assert b'expected=\'("l" "w" "m")' in edit
    assert b'"pmos1v"' in edit
    assert b"param~>callback==body" in edit
    assert b"/home/buet/job/edit/work/verify-wlm-callbacks.py" in edit
    assert b"mcpMosApplyWL(" not in reopen
    assert b"dbSave(" not in reopen


def test_wlm_phase_asset_is_separately_pinned_within_existing_guest_limit() -> None:
    scope = _wlm_scope()
    child = Path(getfile(wlm_callback)).read_bytes()
    phase = Path(getfile(wlm_phase)).read_bytes()
    adapter = b"compiled fixed renderer"
    assert len(Path(getfile(guest)).read_bytes()) <= 65_536
    assets = {
        "adapter": adapter.decode(),
        "adapter_sha256": hashlib.sha256(adapter).hexdigest(),
        "hash_child": child.decode(),
        "hash_child_sha256": guest.WLM_HASH_CHILD_SHA256,
        "phase": phase.decode(),
        "phase_sha256": guest.WLM_PHASE_SHA256,
    }

    def decode_assets() -> tuple[bytes, bytes, bytes]:
        raw = support.canonical(assets)
        scope["sizing_sha256"] = hashlib.sha256(raw).hexdigest()
        packet = {"sizing_base64": base64.b64encode(raw).decode()}
        value: tuple[bytes, bytes, bytes] = guest.read_sizing_assets(support, packet, scope)
        return value

    assert decode_assets() == (adapter, child, phase)
    assets["phase"] += "\n"
    assets["phase_sha256"] = hashlib.sha256(assets["phase"].encode()).hexdigest()
    with pytest.raises(ValueError, match="wlm_phase_identity"):
        decode_assets()
    del assets["phase"]
    with pytest.raises(ValueError, match="sizing_asset_fields"):
        decode_assets()
