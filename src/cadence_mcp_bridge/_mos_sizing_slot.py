"""Verify the immutable native authority for one length-only MOS sizing slot.

The native caller must read the manifest from the protected, fixed operation
path. This module performs no file access, claims, dispatch or SKILL evaluation.
Keep it executable on the installed Python 2.6 guest as well as on the host.
"""

import hashlib
import json
import re
from decimal import Decimal

RENDERER_SHA256 = "ac0b45c26c0b76ce593bea1d3621788ab4d94f165854530cb811ed8c915518a2"
RENDERER_TEMPLATE_SHA256 = "3c211b42e61b4acc15cf3f2f129459b3f09e5a5a41e8200476b66531c996849b"
_MARKER = b'"@LENGTH_NM@"'
_ENTRY = (
    b"procedure(mcpMosApplyWL(inst)\n"
    b' mcpMosWlApply(inst "nmos1v" "@LENGTH_NM@" nil list(list("l" "@LENGTH_NM@"))))\n'
)
_TEXT = (str, type(b"".decode("ascii")))
_MANIFEST_FIELDS = set(
    (
        "schema_version",
        "owner",
        "route",
        "operation_id",
        "valid_until_unix",
        "scope_template_sha256",
        "length_nm_min",
        "length_nm_max",
        "renderer_template_sha256",
        "adapter_template",
        "hash_child_sha256",
    )
)


def _require(condition, error):
    if not condition:
        raise ValueError("mos_sizing_slot_" + error)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _document(raw, limit, error):
    _require(type(raw) is bytes and 0 < len(raw) <= limit, error)
    try:
        value = json.loads(raw.decode("ascii"))
        _require(type(value) is dict and _canonical(value) == raw, error)
    except (ValueError, TypeError, RuntimeError):
        raise ValueError("mos_sizing_slot_" + error)  # noqa: B904 - Python 2.6
    return value


def _digest(value):
    return isinstance(value, _TEXT) and re.match(r"[0-9a-f]{64}\Z", value) is not None


def _operation_id(value):
    return (
        isinstance(value, _TEXT)
        and re.match(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z", value) is not None
    )


def _nm(value):
    # The renderer accepts a bounded decimal. The sealed path also requires
    # the host's canonical spelling, so an equivalent value has one wire form.
    _require(
        isinstance(value, _TEXT)
        and len(value) <= 24
        and re.match(r"(?:0\.[0-9]*[1-9]|[1-9][0-9]*(?:\.[0-9]*[1-9])?)\Z", value) is not None,
        "length",
    )
    return Decimal(value)


def _dimension(row):
    _require(
        type(row) is dict and set(row) == set(("value", "unit")) and row["unit"] == "nm",
        "dimension",
    )
    return _nm(row["value"])


def sizing_scope_template_sha256(scope):
    """Pin the complete scope after removing the exact candidate-dependent leaves."""
    try:
        # Round-trip to independent JSON branches even when the builder reused
        # the same in-memory request object in both locations.
        anchor = json.loads(_canonical(scope).decode("ascii"))
        del anchor["subject"]["plan_sha256"]
        del anchor["plan"]["requested"]["l"]
        del anchor["plan"]["expected"]["l"]
        del anchor["candidate_request"]["l"]
        del anchor["sizing_sha256"]
        anchor.pop("slot_manifest_sha256", None)
    except (KeyError, TypeError, AttributeError):
        raise ValueError("mos_sizing_slot_scope_shape")  # noqa: B904
    return _sha(_canonical(anchor))


def _length_from_plan(scope, subject):
    plan, route = scope["plan"], scope["route_qualification"]
    current, expected, requested = plan["current"], plan["expected"], plan["requested"]
    _require(
        plan["changed"] == ["l"]
        and plan["allowed_derived"] == ["as", "ad", "ps", "pd"]
        and scope["candidate_request"] == requested
        and requested == {"w": None, "l": expected["l"]}
        and expected == {"w": current["w"], "l": requested["l"]}
        and plan["baseline"] == route["baseline"]
        and plan["target"] == route["target"]
        and plan["route_sha256"] == subject["route_sha256"] == _sha(_canonical(route))
        and _sha(_canonical(plan)) == subject["plan_sha256"],
        "plan",
    )
    target, support = route["target"], route["support"]
    length_constraints = support["l"]
    _require(
        target["instance"]["master_library"] == "gpdk090"
        and target["instance"]["master_cell"] == "nmos1v"
        and target["instance"]["master_view"] == "symbol"
        and target["instance"]["property_name"] == "l"
        and support["w"] is None
        and type(length_constraints) is dict
        and set(length_constraints).issubset(("minimum", "maximum", "grid_step", "grid_origin_nm"))
        and all(value is None for value in length_constraints.values())
        and support["adapter_sha256"] == RENDERER_SHA256,
        "route",
    )
    _dimension(current["w"])
    length = _dimension(expected["l"])
    _require(length != _dimension(current["l"]), "no_change")
    return expected["l"]["value"], length


def _verify_assets(manifest, scope, sizing_raw, length_nm):
    assets = _document(sizing_raw, 32768, "assets")
    _require(
        _sha(sizing_raw) == scope["sizing_sha256"]
        and set(assets) == set(("adapter", "adapter_sha256", "hash_child", "hash_child_sha256"))
        and all(isinstance(assets[key], _TEXT) for key in assets),
        "assets",
    )
    template = manifest["adapter_template"].encode("ascii")
    _require(
        _sha(template) == manifest["renderer_template_sha256"] == RENDERER_TEMPLATE_SHA256
        and template.endswith(_ENTRY)
        and template.count(b"@LENGTH_NM@") == template.count(_MARKER) == 2,
        "template",
    )
    expected = template.replace(_MARKER, ('"' + length_nm + 'n"').encode("ascii"))
    actual = assets["adapter"].encode("ascii")
    child = assets["hash_child"].encode("ascii")
    _require(actual == expected and _sha(actual) == assets["adapter_sha256"], "adapter")
    _require(
        0 < len(child) <= 8192
        and _sha(child) == assets["hash_child_sha256"] == manifest["hash_child_sha256"],
        "hash_child",
    )


def verify_sizing_slot(manifest_raw, scope, sizing_raw, now_unix):
    """Accept only the length authorized by the protected one-slot manifest."""
    manifest = _document(manifest_raw, 16384, "manifest")
    _require(
        set(manifest) == _MANIFEST_FIELDS
        and type(manifest["schema_version"]) is int
        and manifest["schema_version"] == 1
        and manifest["owner"] == "C0"
        and manifest["route"] == "registered_mos_sizing"
        and _operation_id(manifest["operation_id"])
        and _digest(manifest["scope_template_sha256"])
        and _digest(manifest["hash_child_sha256"])
        and isinstance(manifest["adapter_template"], _TEXT),
        "manifest",
    )
    expires = manifest["valid_until_unix"]
    _require(
        type(expires) is int and type(now_unix) in (int, float) and 0 <= now_unix < expires,
        "expiry",
    )
    lower, upper = _nm(manifest["length_nm_min"]), _nm(manifest["length_nm_max"])
    _require(lower <= upper, "range")
    try:
        subject = scope["subject"]
        _require(
            type(scope["schema_version"]) is int
            and scope["schema_version"] == 1
            and scope["route"] == manifest["route"]
            and subject["operation_id"] == manifest["operation_id"]
            and _operation_id(subject["owned_copy_operation_id"])
            and subject["owned_copy_operation_id"] != manifest["operation_id"]
            and scope["valid_until_unix"] == expires
            and _sha(manifest_raw) == scope["slot_manifest_sha256"]
            and sizing_scope_template_sha256(scope) == manifest["scope_template_sha256"],
            "binding",
        )
        length_nm, length = _length_from_plan(scope, subject)
        _require(lower <= length <= upper, "range")
        _verify_assets(manifest, scope, sizing_raw, length_nm)
    except (KeyError, TypeError, AttributeError, UnicodeError):
        raise ValueError("mos_sizing_slot_scope_shape")  # noqa: B904
    return length_nm
