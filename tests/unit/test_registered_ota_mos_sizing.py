"""Source-only checks for the separate OTA sizing admission and verification."""

from __future__ import annotations

from dataclasses import replace

import pytest
from test_registered_mos_sizing import _fixture, _length, _Provider, _sha

from cadence_mcp_bridge.registered_mos_sizing import (
    MosSizingValues,
    _observed_dimensions,
    plan_registered_mos_sizing,
)
from cadence_mcp_bridge.registered_ota_mos_sizing import (
    OtaMosBaseline,
    OtaMosInstance,
    RegisteredOtaMosSizingRoute,
    RegisteredOtaMosSizingService,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


def _ota_input(row: bytes, *, reverse: bool = False) -> bytes:
    mos = [
        f"NM{i:02} (out inn vss vss) gpdk090_nmos1v w=(120n) l=100n "
        "as=98f ad=98f ps=1.26u pd=1.26u m=(1)*(1) simM=(1)*(1)\n".encode()
        for i in range(16)
    ] + [row + b"\n"]
    if reverse:
        mos.reverse()
    return b"".join(
        [
            b"simulator lang=spectre\nparameters VDD=1\n",
            b"subckt Ota inp inn out vdd vss\n",
            *mos,
            b"ends Ota\nDUT (inp inn out vdd 0) Ota\n",
        ]
    )


def _ota_fixture(*, pmos_width: bool):
    existing, child, requested, _, binding, before_input, capture = _fixture(pmos_width=pmos_width)
    slot = existing.target.netlist_path.split("/")[1]
    before_raw = _ota_input(
        next(line for line in before_input.splitlines() if line.startswith(slot.encode()))
    )
    after_raw = _ota_input(
        next(line for line in capture.netlist.splitlines() if line.startswith(slot.encode())),
        reverse=True,
    )
    observed = _observed_dimensions(existing.before, include_m=True)
    devices = tuple(
        OtaMosInstance(
            name=f"NM{i:02}",
            master_cell="nmos1v",
            terminals=("out", "inn", "vss", "vss"),
            dimensions=observed.model_copy(update={"w": _length("120")}),
            finger_width=_length("0.12", "um"),
            fingers=1,
        )
        for i in range(16)
    ) + (
        OtaMosInstance(
            name=slot,
            master_cell=existing.target.instance.master_cell,
            terminals=existing.target.netlist_terminals,
            dimensions=observed,
            finger_width=observed.w,
            fingers=1,
        ),
    )
    ota = OtaMosBaseline(
        generation_operation_id="33333333-3333-4333-8333-333333333333",
        reopen_receipt_sha256="c1" * 32,
        netlist_receipt_sha256="c2" * 32,
        baseline_dc_op_receipt_sha256="c3" * 32,
        baseline_ac_receipt_sha256="c4" * 32,
        symbol_tree_sha256="c5" * 32,
        ade_state_tree_sha256="c6" * 32,
        dut_instance="DUT",
        devices=devices,
    )
    route = RegisteredOtaMosSizingRoute.model_validate(
        {
            **dict(existing),
            "baseline": existing.baseline.model_copy(update={"netlist_sha256": _sha(before_raw)}),
            "source_library": "OwnedOtaBaseline",
            "source_cell": "Ota",
            "testbench_cell": "OtaBench",
            "support": existing.support.model_copy(update={"lifecycle": "headless_wlm_v1"}),
            "ota": ota,
        }
    )
    plan = plan_registered_mos_sizing(route, child, requested)
    pins = {"plan_sha256": plan.plan_sha256, "route_sha256": plan.route_sha256}
    binding = binding.model_copy(
        update={**pins, "owned_library": "OwnedOtaEdit", "owned_cell": "Ota"}
    )
    capture = replace(
        capture,
        netlist=after_raw,
        readback=capture.readback.model_copy(update={**pins, "netlist_sha256": _sha(after_raw)}),
    )
    return route, child, requested, binding, before_raw, capture


def _service(fixture, provider):
    route, child, requested, binding, baseline, _ = fixture
    return RegisteredOtaMosSizingService(
        binding,
        route,
        child,
        requested,
        baseline,
        provider,
        expected_binding_sha256=canonical_digest(binding),
    )


@pytest.mark.parametrize("pmos_width", [False, True])
def test_accepts_only_one_axis_and_retains_original_input_on_lookup(pmos_width):
    data = _ota_fixture(pmos_width=pmos_width)
    provider = _Provider(data[-1])
    service = _service(data, provider)
    result = service.apply(service.identity)
    assert result.outcome == "VERIFIED"
    assert result.observed == result.expected
    assert result.observed.m == 1
    replay, evidence = service.lookup_evidence(service.identity)
    assert replay.replayed
    assert evidence is not None and evidence.confirmed_input == data[-1].netlist
    assert (provider.claims, provider.dispatches) == (1, 1)


@pytest.mark.parametrize(
    ("old", "changed"),
    [
        (b"NM00 (out inn vss vss)", b"NM00 (inn out vss vss)"),
        (b"NM01 (out inn vss vss) gpdk090_nmos1v", b"NM01 (out inn vss vss) gpdk090_pmos1v"),
        (b"NM02 ", b"NM01 "),
        (b"l=100n as=98f", b"l=100n as=99f"),
        (b"l=100n as=98f", b"l=100n nonsense=1 as=98f"),
        (b"m=(1)*(1) simM=(1)*(1)", b"m=(1)*(6) simM=(6)*(1)"),
        (b"parameters VDD=1", b"parameters VDD=1.1"),
        (b"DUT (inp inn out vdd 0) Ota", b"DUT (inn inp out vdd 0) Ota"),
    ],
)
def test_rejects_changed_siblings_fixed_conditions_or_topology(old, changed):
    data = _ota_fixture(pmos_width=False)
    capture = data[-1]
    raw = capture.netlist.replace(old, changed, 1)
    assert raw != capture.netlist
    capture = replace(
        capture,
        netlist=raw,
        readback=capture.readback.model_copy(update={"netlist_sha256": _sha(raw)}),
    )
    service = _service(data, _Provider(capture))
    assert service.apply(service.identity).outcome == "OUTCOME_UNKNOWN"


def test_rejects_unobserved_baseline_and_non_single_axis_before_dispatch():
    route, child, _, binding, raw, capture = _ota_fixture(pmos_width=False)
    observed = route.ota.devices[0]
    ota = route.ota.model_copy(
        update={
            "devices": (
                observed.model_copy(update={"terminals": ("x", "inn", "vss", "vss")}),
                *route.ota.devices[1:],
            )
        }
    )
    route_drift = route.model_copy(update={"ota": ota})
    plan = plan_registered_mos_sizing(route_drift, child, MosSizingValues(l=_length("250")))
    binding_drift = binding.model_copy(
        update={"plan_sha256": plan.plan_sha256, "route_sha256": plan.route_sha256}
    )
    provider = _Provider(capture)
    with pytest.raises(ValueError, match="observed device"):
        _service((route_drift, child, plan.requested, binding_drift, raw, capture), provider)
    with pytest.raises(ValueError, match="not registered"):
        _service(
            (
                route,
                child,
                MosSizingValues(w=_length("120"), l=_length("250")),
                binding,
                raw,
                capture,
            ),
            provider,
        )
    assert (provider.claims, provider.dispatches) == (0, 0)
