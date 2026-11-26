"""The native finite slot binds one immutable scope template and trusted code."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from cadence_mcp_bridge._mos_sizing_slot import (
    RENDERER_SHA256,
    RENDERER_TEMPLATE_SHA256,
    sizing_scope_template_sha256,
    verify_sizing_slot,
)
from cadence_mcp_bridge.mos_wl_skill import render_mos_wl_skill

_OPERATION = "11111111-1111-4111-8111-111111111111"
_COPY_OPERATION = "22222222-2222-4222-8222-222222222222"
_EXPIRES = 1795630000
_HASH_CHILD = b"test-only immutable hash child bytes"


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _candidate(value, *, render_value=None):
    length = {"value": value, "unit": "nm"}
    width = {"value": "120", "unit": "nm"}
    route = {
        "baseline": {
            "revision_sha256": "a" * 64,
            "testbench_revision_sha256": "b" * 64,
            "netlist_sha256": "c" * 64,
        },
        "source_library": "CmosLong20261111",
        "source_cell": "InvLong",
        "testbench_cell": "InvLongTb",
        "target": {
            "instance": {
                "instance_path": "DUT/MN",
                "master_library": "gpdk090",
                "master_cell": "nmos1v",
                "master_view": "symbol",
                "property_name": "l",
            },
            "netlist_path": "DUT/MN",
            "netlist_model": "gpdk090_nmos1v",
            "netlist_terminals": ["vout", "vin", "vss", "vss"],
        },
        "support": {"w": None, "l": {}, "adapter_sha256": RENDERER_SHA256},
    }
    route_sha = _sha(_wire(route))
    plan = {
        "baseline": route["baseline"],
        "candidate_revision": {"revision_id": "fixed-slot-child"},
        "target": route["target"],
        "route_sha256": route_sha,
        "current": {"w": width, "l": {"value": "100", "unit": "nm"}},
        "requested": {"w": None, "l": length},
        "expected": {"w": width, "l": length},
        "changed": ["l"],
        "allowed_derived": ["as", "ad", "ps", "pd"],
    }
    adapter = render_mos_wl_skill("nmos1v", length_nm=render_value or value)
    assets = {
        "adapter": adapter.decode("ascii"),
        "adapter_sha256": _sha(adapter),
        "hash_child": _HASH_CHILD.decode("ascii"),
        "hash_child_sha256": _sha(_HASH_CHILD),
    }
    scope = {
        "schema_version": 1,
        "route": "registered_mos_sizing",
        "context_id": "trusted-context",
        "resource_domain_sha256": "1" * 64,
        "environment_sha256": "2" * 64,
        "native_manifest_sha256": "3" * 64,
        "subject": {
            "operation_id": _OPERATION,
            "owned_copy_operation_id": _COPY_OPERATION,
            "route_sha256": route_sha,
            "plan_sha256": _sha(_wire(plan)),
            "owned_library": "CmosLongMosSlot1",
            "owned_cell": "InvLong",
            "owned_view": "schematic",
            "owned_before_view_tree_sha256": "4" * 64,
            "owned_before_testbench_tree_sha256": "5" * 64,
            "source_preservation_sha256": "6" * 64,
        },
        "route_qualification": route,
        "plan": plan,
        "candidate_request": plan["requested"],
        "guest_sha256": "7" * 64,
        "native_safety_sha256": "8" * 64,
        "sizing_sha256": _sha(_wire(assets)),
        "valid_until_unix": _EXPIRES,
    }
    return scope, assets


def _manifest(scope):
    original = render_mos_wl_skill("nmos1v", length_nm="250")
    template = original.replace(b'"250n"', b'"@LENGTH_NM@"')
    assert _sha(template) == RENDERER_TEMPLATE_SHA256
    return {
        "schema_version": 1,
        "owner": "C0",
        "route": "registered_mos_sizing",
        "operation_id": _OPERATION,
        "valid_until_unix": _EXPIRES,
        "scope_template_sha256": sizing_scope_template_sha256(scope),
        "length_nm_min": "200",
        "length_nm_max": "250",
        "renderer_template_sha256": RENDERER_TEMPLATE_SHA256,
        "adapter_template": template.decode("ascii"),
        "hash_child_sha256": _sha(_HASH_CHILD),
    }


def _verify(manifest, scope, assets, *, now=_EXPIRES - 1):
    raw = _wire(manifest)
    scope["slot_manifest_sha256"] = _sha(raw)
    scope["sizing_sha256"] = _sha(_wire(assets))
    return verify_sizing_slot(raw, scope, _wire(assets), now)


def test_same_preinstalled_manifest_accepts_two_choices_on_one_unconsumed_slot() -> None:
    first, first_assets = _candidate("200")
    second, second_assets = _candidate("250")
    manifest = _manifest(first)
    assert sizing_scope_template_sha256(first) == sizing_scope_template_sha256(second)
    assert _verify(manifest, first, first_assets) == "200"
    assert _verify(manifest, second, second_assets) == "250"
    assert first["slot_manifest_sha256"] == second["slot_manifest_sha256"]
    assert first["subject"]["plan_sha256"] != second["subject"]["plan_sha256"]
    assert first["sizing_sha256"] != second["sizing_sha256"]


@pytest.mark.parametrize("value", ["199.99", "250.01"])
def test_finite_region_excludes_outside_values(value) -> None:
    baseline, _ = _candidate("200")
    scope, assets = _candidate(value)
    with pytest.raises(ValueError, match="slot_range"):
        _verify(_manifest(baseline), scope, assets)


@pytest.mark.parametrize(
    "constraints",
    [
        {"minimum": {"value": "260", "unit": "nm"}},
        {"maximum": {"value": "0.18", "unit": "um"}},
        {"grid_step": {"value": "3", "unit": "nm"}, "grid_origin_nm": "0"},
        {"other": None},
    ],
)
def test_initial_slot_rejects_unimplemented_cdf_bounds_even_with_matching_anchor(constraints):
    scope, assets = _candidate("200")
    route = scope["route_qualification"]
    route["support"]["l"] = constraints
    scope["subject"]["route_sha256"] = scope["plan"]["route_sha256"] = _sha(_wire(route))
    scope["subject"]["plan_sha256"] = _sha(_wire(scope["plan"]))
    with pytest.raises(ValueError, match="slot_route"):
        _verify(_manifest(scope), scope, assets)


def test_source9_null_constraints_keep_operator_region_available() -> None:
    scope, assets = _candidate("200")
    route = scope["route_qualification"]
    route["support"]["l"] = dict.fromkeys(("minimum", "maximum", "grid_step", "grid_origin_nm"))
    scope["subject"]["route_sha256"] = scope["plan"]["route_sha256"] = _sha(_wire(route))
    scope["subject"]["plan_sha256"] = _sha(_wire(scope["plan"]))
    assert _verify(_manifest(scope), scope, assets) == "200"


@pytest.mark.parametrize("value", ["0", "0250", "+250", "250.0", "25e1", "250\n", "1" * 25])
def test_declared_length_requires_positive_canonical_bounded_decimal(value) -> None:
    baseline, _ = _candidate("200")
    scope, assets = _candidate(value, render_value="250")
    with pytest.raises(ValueError, match="slot_length"):
        _verify(_manifest(baseline), scope, assets)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("environment_sha256",), "0" * 64),
        (("native_safety_sha256",), "0" * 64),
        (("subject", "operation_id"), _COPY_OPERATION),
        (("subject", "owned_copy_operation_id"), "994955a2-2be2-44db-b6e9-44070fadb761"),
        (("subject", "owned_before_view_tree_sha256"), "0" * 64),
        (("subject", "source_preservation_sha256"), "0" * 64),
        (("route_qualification", "baseline", "revision_sha256"), "0" * 64),
        (("plan", "candidate_revision", "revision_id"), "different-child"),
        (("plan", "expected", "w", "value"), "350"),
        (("plan", "allowed_derived"), ["fw", "as", "ad", "ps", "pd"]),
    ],
)
def test_unapproved_stable_fields_never_inherit_slot_authority(path, value) -> None:
    scope, assets = _candidate("200")
    manifest = _manifest(scope)
    parent = scope
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    with pytest.raises(ValueError, match="slot_binding"):
        _verify(manifest, scope, assets)


def test_dynamic_fields_must_still_match_the_exact_plan_and_rendered_bytes() -> None:
    scope, assets = _candidate("200")
    manifest = _manifest(scope)
    scope["candidate_request"] = deepcopy(scope["candidate_request"])
    scope["candidate_request"]["l"]["value"] = "250"
    with pytest.raises(ValueError, match="slot_plan"):
        _verify(manifest, scope, assets)

    scope, assets = _candidate("200")
    scope["subject"]["plan_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="slot_plan"):
        _verify(manifest, scope, assets)

    scope, assets = _candidate("200", render_value="250")
    with pytest.raises(ValueError, match="slot_adapter"):
        _verify(manifest, scope, assets)

    scope, assets = _candidate("200")
    assets["adapter"] += "; unexpected body\n"
    assets["adapter_sha256"] = _sha(assets["adapter"].encode("ascii"))
    with pytest.raises(ValueError, match="slot_adapter"):
        _verify(manifest, scope, assets)

    scope, assets = _candidate("200")
    assets["hash_child"] = "unapproved helper bytes"
    assets["hash_child_sha256"] = _sha(assets["hash_child"].encode("ascii"))
    with pytest.raises(ValueError, match="slot_hash_child"):
        _verify(manifest, scope, assets)


def test_slot_expiry_manifest_pin_and_exact_approved_template_are_mandatory() -> None:
    scope, assets = _candidate("200")
    manifest = _manifest(scope)
    with pytest.raises(ValueError, match="slot_expiry"):
        _verify(manifest, scope, assets, now=_EXPIRES)
    with pytest.raises(ValueError, match="slot_binding"):
        verify_sizing_slot(
            _wire(manifest), dict(scope, slot_manifest_sha256="0" * 64), _wire(assets), _EXPIRES - 1
        )
    manifest["adapter_template"] = "; unapproved template\n" + manifest["adapter_template"]
    manifest["renderer_template_sha256"] = _sha(manifest["adapter_template"].encode("ascii"))
    with pytest.raises(ValueError, match="slot_template"):
        _verify(manifest, scope, assets)


def test_manifest_is_closed_and_canonically_serialized() -> None:
    scope, assets = _candidate("200")
    manifest = _manifest(scope)
    with pytest.raises(ValueError, match="slot_manifest"):
        _verify(dict(manifest, owner="client"), scope, assets)
    with pytest.raises(ValueError, match="slot_manifest"):
        _verify(dict(manifest, client_source="unsupported"), scope, assets)
    with pytest.raises(ValueError, match="slot_manifest"):
        verify_sizing_slot(_wire(manifest) + b"\n", scope, _wire(assets), _EXPIRES - 1)
