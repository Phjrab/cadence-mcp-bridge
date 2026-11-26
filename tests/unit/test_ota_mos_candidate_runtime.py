"""Focused tests for the isolated OTA worker wire and receipt boundary."""

import base64
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from cadence_mcp_bridge import _ota_mos_candidate_runtime as ota
from cadence_mcp_bridge import _registered_mos_edit_phase as legacy
from cadence_mcp_bridge.m2_cdf import render_reopened_mos_cdf
from cadence_mcp_bridge.mos_wlm_skill import render_mos_wlm_skill
from cadence_mcp_bridge.registered_mos_edit import NativeMosEditReadback, NativeMosEditSave

ASSETS = Path(ota.__file__).parent
OP = "730a1469-9c78-4521-8f83-287f39f57613"
COPY = "c9ff84a6-7208-4156-ad38-a0ba66c6032c"
GENERATION = "dafbdb6b-49a2-4909-b0ac-526a2bde60ea"
_DIGEST = "a" * 64


def _sha(raw):
    return sha256(raw).hexdigest()


def _canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("ascii")


def _length(value):
    return dict(value=str(value), unit="nm")


def _properties(master, count, *, width="1u", length="250n"):
    props = {}
    for key, value in zip(
        ("w", "fw", "l", "m", "fingers", "as", "ad", "ps", "pd", "model"),
        (
            width,
            width,
            length,
            str(count),
            "1",
            "280f",
            "280f",
            "2.56u",
            "2.56u",
            f"gpdk090_{master}",
        ),
        strict=True,
    ):
        props[key] = dict(
            oa_type="string",
            oa_value=value,
            cdf_type="instData",
            cdf_units="lengthMetric" if key in ("w", "fw", "l", "ps", "pd") else None,
            cdf_value=value,
        )
    props["nf"] = dict(oa_type=None, oa_value=None, cdf_type=None, cdf_units=None, cdf_value=None)
    props["dfm"] = {
        **props["nf"],
        "cdf_type": "instData",
        "cdf_value": "Minimum",
    }
    return props


def _lines(props):
    fields = ("oa_type", "oa_value", "cdf_type", "cdf_units", "cdf_value")
    for key in legacy.PROPERTIES:
        values = [props[key][name] for name in fields]
        yield "|".join([key, *("nil" if v is None else json.dumps(v) for v in values)])


def fixture(axis):
    name = "NM0" if axis == "l" else "PM6"
    devices, properties, lines = [], {}, []
    for device in sorted(ota.DEVICES):
        master = "nmos1v" if device.startswith("NM") else "pmos1v"
        rail = "VSS" if master == "nmos1v" else "VDD"
        count = 6 if device == "PM6" else 1
        devices.append(
            dict(
                name=device,
                master_cell=master,
                terminals=["out", "inp", rail, rail],
                dimensions=dict(w=_length(1000), l=_length(250), m=count),
                finger_width=_length(1000),
                fingers=1,
            )
        )
        props = _properties(master, count)
        properties[device] = props
        lines.extend(f"OTA17_TARGET_PROP|{ota.DUT}|{device}|{line}" for line in _lines(props))
    lines.append(f"OTA17_TARGET_PROPERTIES_END|{_DIGEST}")
    stdout = b"Cadence \xa9\n" + ("\n".join(lines) + "\n").encode("ascii")
    selected = next(device for device in devices if device["name"] == name)
    master = selected["master_cell"]
    path = f"DUT/{name}"
    target = dict(
        instance=dict(
            instance_path=path,
            master_library="gpdk090",
            master_cell=master,
            master_view="symbol",
            property_name=axis,
        ),
        netlist_path=path,
        netlist_model=f"gpdk090_{master}",
        netlist_terminals=selected["terminals"],
    )
    baseline_raw = b"simulator lang=spectre\n"
    bounds = dict(minimum=_length(100), maximum=_length(2000), grid_step=None, grid_origin_nm=None)
    baseline = dict(
        revision=dict(design_id="ota17-baseline"),
        revision_sha256="b" * 64,
        testbench_revision_sha256="c" * 64,
        fixed_conditions_sha256=_DIGEST,
        netlist_sha256=_sha(baseline_raw),
    )
    route = dict(
        source_library=ota.SOURCE,
        source_cell=ota.DUT,
        testbench_cell=ota.TB,
        baseline=baseline,
        target=target,
        before=properties[name],
        support=dict(
            lifecycle=legacy.WLM_LIFECYCLE,
            cadence_version="6.1.5.500.15",
            pdk_release="4.6",
            pdk_identity_sha256=legacy.SIZING_PDK_TREE_SHA256,
            adapter_sha256=legacy.WLM_RENDERER_SHA256,
            cdf_constraints_sha256=_DIGEST,
            w=bounds if axis == "w" else None,
            l=bounds if axis == "l" else None,
        ),
        ota=dict(
            generation_operation_id=GENERATION,
            reopen_receipt_sha256="1" * 64,
            reopen_stdout_sha256=_sha(stdout),
            dut_plan_sha256=_DIGEST,
            baseline_dc_op_receipt_sha256="3" * 64,
            baseline_ac_receipt_sha256="4" * 64,
            symbol_tree_sha256="5" * 64,
            ade_state_tree_sha256="6" * 64,
            dut_instance="DUT",
            devices=devices,
            netlist_receipt_sha256="2" * 64,
        ),
    )
    requested = {axis: _length(300 if axis == "l" else 1500)}
    plan = dict(
        baseline=baseline,
        target=target,
        route_sha256=_sha(_canonical(route)),
        current=selected["dimensions"],
        requested=requested,
        expected={**selected["dimensions"], **requested},
        changed=[axis],
        allowed_derived=list(
            (legacy.SIZING_OVERRIDES if axis == "l" else legacy.WIDTH_SIZING_OVERRIDES)[1:]
        ),
    )
    subject = dict(
        operation_id=OP,
        owned_copy_operation_id=COPY,
        plan_sha256=_sha(_canonical(plan)),
        route_sha256=plan["route_sha256"],
        owned_library=ota.CHILD,
        owned_cell=ota.DUT,
        owned_view="schematic",
        owned_before_view_tree_sha256="7" * 64,
        owned_before_testbench_tree_sha256="8" * 64,
        source_preservation_sha256="9" * 64,
    )
    adapter = render_mos_wlm_skill(
        master, length_nm="300" if axis == "l" else None, width_nm="1500" if axis == "w" else None
    )
    parts = dict(
        adapter=adapter,
        hash_child=(ASSETS / "_mos_wlm_callback.py").read_bytes(),
        phase=(ASSETS / "_mos_wlm_phase.py").read_bytes(),
    )
    sizing = _canonical(
        {
            **{key: raw.decode("ascii") for key, raw in parts.items()},
            **{f"{key}_sha256": _sha(raw) for key, raw in parts.items()},
        }
    )
    pin = {name: _DIGEST for name in legacy.SAFETY_FIELDS}
    pin.update(
        schema_version=2,
        source_ade_path=ota.SOURCE_PATH.rsplit("/", 1)[0] + "/" + ota.TB + "_ADE",
        source_ade_design=[ota.SOURCE, ota.TB, "schematic"],
        technology_path="/eda/cdsDefTechLib",
        technology_tree_sha256=_DIGEST,
        source_dut_tree_sha256="b" * 64,
        source_tb_tree_sha256="c" * 64,
        source_symbol_tree_sha256="5" * 64,
        source_ade_tree_sha256="6" * 64,
        supplemental_bytes=0,
        job_limit_bytes=4194304,
    )
    scope = dict(
        schema_version=1,
        route=ota.OTA_SIZING_ROUTE,
        context_id="fixture",
        resource_domain_sha256=_DIGEST,
        environment_sha256=_DIGEST,
        native_manifest_sha256=_DIGEST,
        subject=subject,
        route_qualification=route,
        plan=plan,
        candidate_request=requested,
        guest_sha256=_DIGEST,
        native_safety_sha256=_sha(_canonical(pin)),
        sizing_sha256=_sha(sizing),
        valid_until_unix=2000000000,
    )
    fields = dict(
        baseline=baseline_raw,
        baseline_reopen_stdout=stdout,
        native_safety=_canonical(pin),
        sizing=sizing,
        legacy=(ASSETS / "_registered_mos_edit_phase.py").read_bytes(),
        support=(ASSETS / "_amp_pm0_default_phase.py").read_bytes(),
        ota_skill=(ASSETS / "_ota_mos_candidate_skill.py").read_bytes(),
        cdf_collector=render_reopened_mos_cdf(),
    )
    return scope, fields


def wire(scope, fields, prior=None):
    raw_scope = _canonical(scope)
    digest = _sha(raw_scope)
    authority = _canonical(
        dict(
            owner="C0",
            operation_id=scope["subject"]["operation_id"],
            scope_sha256=digest,
            approved_phases=list(ota.PHASES),
            valid_until_unix=scope["valid_until_unix"],
        )
    )
    fields = {**fields, "authority": authority, "scope": raw_scope}
    return _canonical(
        {
            **{
                key + "_base64": base64.b64encode(raw).decode("ascii")
                for key, raw in fields.items()
            },
            "managed_root": "/home/buet/managed",
            "previous_receipt_sha256": prior,
        }
    ), digest


@pytest.mark.parametrize("axis", ["l", "w"])
def test_pinned_phase_wire_and_actual_legacy_assets(axis):
    scope, fields = fixture(axis)
    for phase, prior in zip(ota.PHASES, (None, "d" * 64), strict=True):
        raw, digest = wire(scope, fields, prior)
        admitted = ota.read_request(raw, digest, phase, 1900000000)
        values = ota.skill_values(admitted, "/home/buet/managed/job/work")
        assert values["@TARGET_LINKS@"].startswith('list(list("D" "out") list("G" "inp")')
        assert values["@AXISTOKEN@"] == axis
        assert values["@OTA_INVENTORY@"].count('list("D"') == 17
        assert admitted["prior"] == prior
        with pytest.raises(ValueError, match="authority_or_predecessor"):
            ota.read_request(raw, digest, ota.PHASES[1 - ota.PHASES.index(phase)], 1900000000)
    raw, digest = wire(
        scope, {**fields, "baseline_reopen_stdout": fields["baseline_reopen_stdout"] + b"x"}
    )
    with pytest.raises(ValueError, match="reopen_digest"):
        ota.read_request(raw, digest, ota.PHASES[0], 1900000000)


def test_independent_capture_receipts_and_no_source_writes(tmp_path, monkeypatch):
    scope, fields = fixture("w")
    raw, digest = wire(scope, fields)
    request = ota.read_request(raw, digest, ota.PHASES[0], 1900000000)
    baseline = scope["plan"]["baseline"]
    pin = request["pin"]
    analysis = dict(
        design_id=baseline["revision"]["design_id"],
        analysis="ac",
        source_cell=ota.SOURCE_PATH + "/" + ota.TB,
        source_state=pin["source_ade_path"],
        ade=dict(
            source_tree_sha256=baseline["testbench_revision_sha256"],
            ade_state_tree_sha256=pin["source_ade_tree_sha256"],
            inputs=dict(analysis="ac", start_hz="1", stop_hz="1000000000", points_per_decade=16),
            model_includes=[{"section": "NN"}],
        ),
    )
    runtime = SimpleNamespace(
        root="/managed",
        accounting=SimpleNamespace(JOBS="jobs"),
        original_registration={"routes": [analysis]},
    )
    job = ota.new_job(runtime, None, request, digest)
    assert isinstance(job, request["legacy"].Source9MosJob)
    job.h = SimpleNamespace(read=lambda path, *_: (tmp_path / Path(path).name).read_bytes())
    job.library_lines = lambda extra=None: b"fixed"
    job.guard = lambda session: 4194304
    job.save_document = lambda path, doc: None
    job.digest_doc = lambda doc: _sha(_canonical(doc))
    original = deepcopy(job.route["before"])
    changed = _properties("pmos1v", 6, width="1.5u")
    views_before = dict(dut="7" * 64, tb="8" * 64, symbol="9" * 64)
    views_after = {**views_before, "dut": "c" * 64}
    job.views = lambda library: views_after
    work = "/job/work"
    invocations = []
    remaps = []

    def retain(name, data):
        (tmp_path / name).write_bytes(data)

    def run(session, root, program, definitions, phase, markers):
        invocations.append(phase)
        assert "@TARGET@" not in program.decode("ascii")

        def frame(props):
            return ("\n".join([*_lines(props), "COMPLETE", ""])).encode("ascii")

        retain("footprint.txt", b"equal independently captured footprint\n")
        if phase == "edit":
            retain("baseline.properties", frame(original))
            retain("saved.properties", frame(changed))
            assert b"mcpMosApplyWL(inst)" in program
        else:
            assert b"dbSave(" not in program and b"mcpMosApplyWL" not in program
            retain("reopened.properties", frame(changed))
            retain("cdf-frame.txt", b"M2_CDF_V2\nCOMPLETE\n")
            retain("input.scs", b"synthetic native handoff\n")
        return b""

    job.run = run
    job._remap_state = lambda *args: remaps.append(args)
    job.rt.copying = SimpleNamespace(
        snapshot=lambda path: dict(
            tree_sha256=request["pin"]["source_ade_tree_sha256"], content_sha256=_DIGEST
        ),
        copy_owned=lambda source, dest, digest: invocations.append((source, dest)),
    )
    job.rt.accounting = object()
    job.rt.operations = SimpleNamespace(directory=lambda *args: None)
    job.rt.eda = SimpleNamespace(
        write=lambda path, data: retain(Path(path).name, data),
        copy_capacity=lambda *args: None,
        find_input=lambda path: "/job/input.scs",
    )
    job.rt.modules = {
        "probe": SimpleNamespace(digest_file=lambda path: legacy.SYSTEM_PYTHON_SHA256),
        "rendering": SimpleNamespace(netlist=lambda *args: b"\n; fixed netlist only\n"),
    }
    realpath = ota.os.path.realpath
    monkeypatch.setattr(
        ota.os.path, "realpath", lambda p: p if p == "/usr/bin/python" else realpath(p)
    )
    save = job.edit(None, work, views_before)
    assert NativeMosEditSave.model_validate_json(_canonical(save)).saved.revision_sha256 == "c" * 64
    receipt, response = job.reopen(None, f"/jobs/{OP}/{OP}", work, views_after, save)
    typed = NativeMosEditReadback.model_validate_json(_canonical(response["readback"]))
    assert typed.reopened.properties["m"].oa_value == "6"
    assert typed.reopened.footprint_sha256 == typed.saved.footprint_sha256
    assert _sha(base64.b64decode(response["input_base64"])) == typed.netlist_sha256
    assert response["readback"] == receipt
    assert invocations[0] == "edit" and invocations[-1] == "reopen"
    assert all(dest.startswith(f"/jobs/{OP}/{OP}/") for _, dest in invocations[1:-1])
    assert len(remaps) == 1
    with pytest.raises(ValueError, match="reopened_footprint"):
        job.reopen(
            None,
            f"/jobs/{OP}/{OP}",
            work,
            views_after,
            {**save, "saved": {**save["saved"], "footprint_sha256": "e" * 64}},
        )
