"""Fixed OTA candidate worker. This guest asset must parse on Python 2.6."""

# mypy: ignore-errors
# ruff: noqa: B905, UP004, UP030, UP031, UP032

import os
import sys

if __name__ == "__main__":
    sys.path[:] = [
        entry
        for entry in sys.path
        if entry and entry.startswith("/") and os.path.realpath(entry) != os.getcwd()
    ]

import base64
import hashlib
import json
import re
import time
import types
from decimal import Decimal, localcontext

OTA_SIZING_ROUTE = "registered_ota_mos_sizing"
SOURCE, CHILD = "Ota17Base20261126", "Ota17Candidate20261126"
DUT, TB = "self_cascode_ota_17mos", "self_cascode_ota_tb"
SOURCE_PATH = "/home/buet/cds_work/Ota17BaseOutputs20261126_v1/" + SOURCE
CHILD_PATH = "/home/buet/cds_work/Ota17CandidateOutputs20261126_v1/" + CHILD
CHILD_STATE = os.path.dirname(CHILD_PATH) + "/" + TB + "_ADE"
SOURCE9_SHA256 = "539794c47d1b5ab57a04030e892ab41763be93a0b752129f5771f2369447c147"
OTA_SKILL_SHA256 = "9ed25ec92700c9b323ecabbd0e0e2ccea2323b1009fdb8a1fa6c53081be7192c"
_LEGACY_MAIN_SUFFIX = b'if __name__ == "__main__":\n    main()\n'
PHASES = ("EDIT_SAVE", "INDEPENDENT_REOPEN_NETLIST")
DEVICES = frozenset(
    (
        "NM0",
        "NM1",
        "NM2",
        "NM3",
        "NM6",
        "NM7",
        "NM8",
        "NM9",
        "NM10",
        "NM11",
        "PM2",
        "PM3",
        "PM4",
        "PM5",
        "PM6",
        "PM7",
        "PM8",
    )
)
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_OP = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_SKILL_TOKEN = re.compile(r"@[A-Za-z0-9_]+@")
_SCOPE_FIELDS = frozenset(
    (
        "schema_version",
        "route",
        "context_id",
        "resource_domain_sha256",
        "environment_sha256",
        "native_manifest_sha256",
        "subject",
        "route_qualification",
        "plan",
        "candidate_request",
        "guest_sha256",
        "native_safety_sha256",
        "sizing_sha256",
        "valid_until_unix",
    )
)
_SUBJECT_FIELDS = frozenset(
    (
        "operation_id",
        "owned_copy_operation_id",
        "plan_sha256",
        "route_sha256",
        "owned_library",
        "owned_cell",
        "owned_view",
        "owned_before_view_tree_sha256",
        "owned_before_testbench_tree_sha256",
        "source_preservation_sha256",
    )
)
_OTA_FIELDS = frozenset(
    (
        "generation_operation_id",
        "reopen_receipt_sha256",
        "reopen_stdout_sha256",
        "dut_plan_sha256",
        "baseline_dc_op_receipt_sha256",
        "baseline_ac_receipt_sha256",
        "symbol_tree_sha256",
        "ade_state_tree_sha256",
        "dut_instance",
        "devices",
    )
)
_PACKET_FIELDS = frozenset(
    (
        "managed_root",
        "scope_base64",
        "authority_base64",
        "baseline_base64",
        "native_safety_base64",
        "previous_receipt_sha256",
        "support_base64",
        "cdf_collector_base64",
        "sizing_base64",
        "baseline_reopen_stdout_base64",
    )
)
_RECOVERY_FIELDS = frozenset(("baseline_recovery_base64", "baseline_reopen_receipt_base64"))


def require(condition, stage):
    if not condition:
        raise ValueError("registered_ota_mos_" + stage)


def render_ota_skill(template, values):
    """Render only fixed OTA placeholders, including underscored names."""
    names = frozenset(_SKILL_TOKEN.findall(template))
    require(names.issubset(values), "skill_placeholder_binding")
    program = _SKILL_TOKEN.sub(lambda match: values[match.group(0)], template)
    require(_SKILL_TOKEN.search(program) is None, "skill_placeholder_remaining")
    return program.encode("ascii")


def _canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "ascii"
    )


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _nm(legacy, dimension):
    require(set(dimension) == set(("value", "unit")), "dimension_fields")
    with localcontext() as context:
        context.prec = 128
        return legacy.finite_length(dimension["value"], dimension["unit"]) * Decimal("1e9")


def _axis_bound(legacy, value, bounds):
    require(
        set(bounds) == set(("minimum", "maximum", "grid_step", "grid_origin_nm")),
        "axis_bounds_fields",
    )
    low, high, step, origin = (
        bounds[name] for name in ("minimum", "maximum", "grid_step", "grid_origin_nm")
    )
    require(
        (low is None or _nm(legacy, low) <= value)
        and (high is None or value <= _nm(legacy, high))
        and (step is None) == (origin is None),
        "axis_bounds",
    )
    if step is not None:
        require(len(origin) <= 48 and re.match(r"-?[0-9]+(?:\.[0-9]+)?\Z", origin), "axis_grid")
        with localcontext() as context:
            context.prec = 128
            require((value - Decimal(origin)) % _nm(legacy, step) == 0, "axis_grid")


def parse_ota_sizing_route(scope, legacy=None, wlm_phase=None):
    """Validate the closed v1 OTA scope used by the independently registered lane."""
    if legacy is None:
        from cadence_mcp_bridge import _registered_mos_edit_phase as legacy
    if wlm_phase is None:
        from cadence_mcp_bridge import _mos_wlm_phase as wlm_phase
    require(
        set(scope) == _SCOPE_FIELDS
        and scope["route"] == OTA_SIZING_ROUTE
        and type(scope["schema_version"]) is int
        and scope["schema_version"] == 1
        and type(scope["valid_until_unix"]) is int
        and scope["valid_until_unix"] > 0,
        "scope_fields",
    )
    require(
        all(_HEX.match(scope[key]) for key in _SCOPE_FIELDS if key.endswith("_sha256")),
        "scope_pins",
    )
    route, plan, subject = scope["route_qualification"], scope["plan"], scope["subject"]
    require(
        set(subject) == _SUBJECT_FIELDS
        and all(_HEX.match(subject[key]) for key in _SUBJECT_FIELDS if key.endswith("_sha256"))
        and _sha(_canonical(route)) == subject["route_sha256"]
        and _sha(_canonical(plan)) == subject["plan_sha256"],
        "subject_pins",
    )
    target, support, ota = route["target"], route["support"], route["ota"]
    custody = set(ota).difference(_OTA_FIELDS)
    require(
        _OTA_FIELDS.issubset(ota)
        and custody in (set(("netlist_receipt_sha256",)), set(("recovered_source_sha256",)))
        and all(_HEX.match(ota[k]) for k in ota if k.endswith("_sha256")),
        "baseline_custody",
    )
    operations = (
        subject["operation_id"],
        subject["owned_copy_operation_id"],
        ota["generation_operation_id"],
    )
    receipts = (
        ota["reopen_receipt_sha256"],
        ota[next(iter(custody))],
        ota["baseline_dc_op_receipt_sha256"],
        ota["baseline_ac_receipt_sha256"],
    )
    require(
        all(_OP.match(op) for op in operations)
        and len(set(operations)) == 3
        and len(set(receipts)) == 4,
        "independent_baseline",
    )
    instance = target["instance"]
    name = instance["instance_path"].partition("/")[2]
    axis = instance["property_name"]
    require(name in DEVICES and axis in ("l", "w"), "target_axis")
    master = "nmos1v" if name.startswith("NM") else "pmos1v"
    path = "DUT/" + name
    require(
        (route["source_library"], route["source_cell"], route["testbench_cell"])
        == (SOURCE, DUT, TB)
        and (subject["owned_library"], subject["owned_cell"], subject["owned_view"])
        == (CHILD, DUT, "schematic")
        and instance
        == dict(
            instance_path=path,
            master_library="gpdk090",
            master_cell=master,
            master_view="symbol",
            property_name=axis,
        )
        and (target["netlist_path"], target["netlist_model"], ota["dut_instance"])
        == (path, "gpdk090_" + master, "DUT"),
        "target_identity",
    )
    inventory = ota["devices"]
    require(len(inventory) == 17 and set(row["name"] for row in inventory) == DEVICES, "inventory")
    selected = None
    for row in inventory:
        cell = "nmos1v" if row["name"].startswith("NM") else "pmos1v"
        rail = "VSS" if cell == "nmos1v" else "VDD"
        dimensions = row["dimensions"]
        require(
            set(row)
            == set(("name", "master_cell", "terminals", "dimensions", "finger_width", "fingers"))
            and row["master_cell"] == cell
            and type(row["fingers"]) is int
            and row["fingers"] == 1
            and len(row["terminals"]) == 4
            and row["terminals"][3] == rail
            and all(_ID.match(net) for net in row["terminals"])
            and set(dimensions) == set(("w", "l", "m"))
            and type(dimensions["m"]) is int
            and dimensions["m"] in (1, 6)
            and _nm(legacy, dimensions["l"]) > 0
            and _nm(legacy, dimensions["w"]) == _nm(legacy, row["finger_width"]),
            "device_inventory_row",
        )
        if row["name"] == name:
            selected = row
    held = "w" if axis == "l" else "l"
    current, requested, expected = plan["current"], plan["requested"], plan["expected"]
    require(
        selected["terminals"] == target["netlist_terminals"]
        and support["lifecycle"] == legacy.WLM_LIFECYCLE
        and support["adapter_sha256"] == legacy.WLM_RENDERER_SHA256
        and (support["cadence_version"], support["pdk_release"]) == ("6.1.5.500.15", "4.6")
        and support["pdk_identity_sha256"] == legacy.SIZING_PDK_TREE_SHA256
        and _HEX.match(support["cdf_constraints_sha256"])
        and support.get("m") is None
        and support.get(held) is None
        and isinstance(support[axis], dict)
        and set(current) == set(expected) == set(("l", "w", "m"))
        and set(requested) == set(("w", "l"))
        and requested[held] is None
        and scope["candidate_request"] == requested
        and plan["changed"] == [axis]
        and plan["allowed_derived"] == list(wlm_phase.wlm_overrides(legacy, (axis,))[1:])
        and expected[axis] == requested[axis]
        and expected[held] == current[held]
        and type(expected["m"]) is int
        and type(current["m"]) is int
        and expected["m"] == current["m"] == selected["dimensions"]["m"]
        and plan["baseline"] == route["baseline"]
        and plan["target"] == target
        and plan["route_sha256"] == subject["route_sha256"],
        "single_axis_plan",
    )
    for key in ("l", "w"):
        require(
            current[key]["unit"] == expected[key]["unit"] == "nm"
            and _nm(legacy, current[key]) == _nm(legacy, selected["dimensions"][key]),
            "baseline_dimension",
        )
    value = _nm(legacy, expected[axis])
    require(value != _nm(legacy, current[axis]), "no_effect")
    _axis_bound(legacy, value, support[axis])
    before = route["before"]
    require(
        set(before) == set(legacy.PROPERTIES)
        and before["model"]["cdf_value"] == target["netlist_model"]
        and before["dfm"]["cdf_value"] == "Minimum"
        and all(value is None for value in before["nf"].values()),
        "baseline_properties",
    )
    wlm_phase.wlm_readback(legacy, before, before, current, ())
    return route


def verify_original_reopen(raw, route, legacy, wlm_phase):
    """Verify the original 204 typed rows and the one selected baseline property set."""
    ota = route["ota"]
    require(0 < len(raw) <= 65536 and _sha(raw) == ota["reopen_stdout_sha256"], "reopen_digest")
    props = dict((name, {}) for name in DEVICES)
    end = False
    for line in raw.splitlines():
        if not line.startswith(b"OTA17_TARGET_"):
            continue
        require(not end, "reopen_after_end")
        bits = line.decode("ascii").split("|")
        if bits == ["OTA17_TARGET_PROPERTIES_END", ota["dut_plan_sha256"]]:
            end = True
            continue
        require(
            len(bits) == 9
            and bits[:2] == ["OTA17_TARGET_PROP", DUT]
            and bits[2] in props
            and bits[3] in legacy.PROPERTIES
            and bits[3] not in props[bits[2]],
            "reopen_row",
        )
        props[bits[2]][bits[3]] = "|".join(bits[3:])
    require(end, "reopen_completion")
    values = {}
    for row in ota["devices"]:
        name = row["name"]
        require(set(props[name]) == set(legacy.PROPERTIES), "reopen_fields")
        data = "\n".join([props[name][key] for key in legacy.PROPERTIES] + ["COMPLETE", ""])
        actual = legacy.read_properties(data.encode("ascii"))
        wlm_phase.wlm_readback(legacy, actual, actual, row["dimensions"], ())
        require(
            actual["model"]["cdf_value"] == "gpdk090_" + row["master_cell"]
            and all(value is None for value in actual["nf"].values())
            and actual["dfm"]
            == dict(
                oa_type=None,
                oa_value=None,
                cdf_type="instData",
                cdf_units=None,
                cdf_value="Minimum",
            )
            and all(
                rec["oa_type"] == "string" and rec["oa_value"] == rec["cdf_value"]
                for key, rec in actual.items()
                if key not in ("dfm", "nf")
            ),
            "reopen_properties",
        )
        values[name] = actual
    selected = route["target"]["netlist_path"].split("/")[1]
    require(values[selected] == route["before"], "reopen_selected")
    return values


def verify_recovery(source, reopen, route):
    """Keep the failed original HNL receipt separate from the verified export."""
    baseline, ota = route["baseline"], route["ota"]
    require(
        _sha(_canonical(source)) == ota["recovered_source_sha256"]
        and _sha(_canonical(reopen)) == ota["reopen_receipt_sha256"]
        and source["status"] == "LOCAL_RETAINED_NETLIST_SOURCE_VERIFIED"
        and source["generation_status"] == "OUTCOME_UNKNOWN"
        and source["execution_authorized"] is False
        and source["recovery_kind"] == "OTA17_NAMED_PORT_PERMUTATION"
        and source["reopen_receipt_sha256"] == ota["reopen_receipt_sha256"]
        and source["operation_id"] == reopen["operation_id"] == ota["generation_operation_id"]
        and source["dut_plan_sha256"] == reopen["plan_sha256"] == ota["dut_plan_sha256"]
        and source["reopen_stdout_sha256"]
        == reopen["artifact_sha256"]
        == ota["reopen_stdout_sha256"]
        and source["library"] == reopen["library"]
        and (source["library"]["name"], source["library"]["path"]) == (SOURCE, SOURCE_PATH)
        and reopen["phase"] == "reopen"
        and source["dut_cell"] == reopen["source_cell"] == SOURCE_PATH + "/" + DUT
        and source["source_cell"] == reopen["bench_cell"] == SOURCE_PATH + "/" + TB
        and source["dut_tree_sha256"] == reopen["source_tree_sha256"] == baseline["revision_sha256"]
        and source["source_tree_sha256"]
        == reopen["bench_tree_sha256"]
        == baseline["testbench_revision_sha256"]
        and source["full_netlist_sha256"] == baseline["netlist_sha256"]
        and source["conditions_sha256"] == baseline["fixed_conditions_sha256"]
        and source["symbol_tree_sha256"] == ota["symbol_tree_sha256"]
        and source["ade_state_tree_sha256"] == ota["ade_state_tree_sha256"],
        "recovery_binding",
    )


def _module(name, raw):
    module = types.ModuleType(name)
    sys.modules[name] = module
    try:
        eval(compile(raw, name + ".py", "exec"), module.__dict__)
    except Exception:
        del sys.modules[name]
        raise
    return module


def read_request(raw, digest, phase, now):
    """Decode and authenticate an OTA-only phase wire before opening the runtime."""
    require(phase in PHASES and _HEX.match(digest) and 0 < len(raw) <= 524288, "request")
    packet = json.loads(raw)
    require(
        set(packet) in (_PACKET_FIELDS, _PACKET_FIELDS | _RECOVERY_FIELDS),
        "request_fields",
    )
    # The transport strips only the original entry point before embedding.
    # Verify the original package bytes, then load the inert body alone.
    source = globals().get("OTA_LEGACY_SOURCE")
    skill_source = globals().get("OTA_SKILL_SOURCE")
    require(
        type(source) is bytes
        and 0 < len(source) <= 65536
        and type(skill_source) is bytes
        and 0 < len(skill_source) <= 32768,
        "embedded_assets",
    )
    _pinned(source + _LEGACY_MAIN_SUFFIX, SOURCE9_SHA256)
    _pinned(skill_source, OTA_SKILL_SHA256)
    legacy = _module("ota_fixed_source9_support", source)

    def read(name, limit):
        return legacy.read_encoded(packet, name, limit)

    helper = _module(
        "ota_fixed_native_support",
        _pinned(read("support", 65536), legacy.SUPPORT_SHA256),
    )
    require(helper.parse(raw) == packet and raw == helper.canonical(packet), "request_canonical")
    scope = helper.parse(_pinned(read("scope", 32768), digest))
    sizing = legacy.read_sizing_assets(helper, packet, scope)
    require(len(sizing) == 3, "wlm_assets")
    wlm = _module("ota_fixed_wlm_phase", sizing[2])
    route = parse_ota_sizing_route(scope, legacy, wlm)
    recovery = "recovered_source_sha256" in route["ota"]
    require(recovery == _RECOVERY_FIELDS.issubset(packet), "recovery_fields")
    if recovery:
        recovery_source = helper.parse(read("baseline_recovery", 65536))
        reopen = helper.parse(read("baseline_reopen_receipt", 16384))
        verify_recovery(recovery_source, reopen, route)
    else:
        recovery_source = None
    verify_original_reopen(read("baseline_reopen_stdout", 65536), route, legacy, wlm)
    baseline = _pinned(read("baseline", 32768), route["baseline"]["netlist_sha256"])
    authority = read("authority", 4096)
    prior = packet["previous_receipt_sha256"]
    require(
        helper.parse(authority)
        == dict(
            owner="C0",
            operation_id=scope["subject"]["operation_id"],
            scope_sha256=digest,
            approved_phases=list(PHASES),
            valid_until_unix=scope["valid_until_unix"],
        )
        and now < scope["valid_until_unix"]
        and (
            prior is None
            if phase == PHASES[0]
            else isinstance(prior, legacy.STRING_TYPES) and helper.hex_digest(prior)
        ),
        "authority_or_predecessor",
    )
    pin = helper.parse(_pinned(read("native_safety", 65536), scope["native_safety_sha256"]))
    verify_safety(pin, route, legacy)
    skill = _module("ota_fixed_skill", skill_source)
    collector = _pinned(read("cdf_collector", 32768), legacy.CDF_SHA256)
    return dict(
        root=packet["managed_root"],
        scope=scope,
        pin=pin,
        approval=authority,
        collector=collector,
        legacy=legacy,
        helper=helper,
        wlm=wlm,
        sizing=sizing,
        skill=skill,
        prior=prior,
        baseline=baseline,
        recovery=recovery_source,
    )


def _pinned(raw, expected):
    require(_sha(raw) == expected, "asset_digest")
    return raw


_OTA_SAFETY_ADDITIONS = frozenset(
    (
        "technology_path",
        "technology_tree_sha256",
        "source_ade_path",
        "source_ade_design",
    )
)
_CLONE_RECOVERY_FIELDS = frozenset(
    (
        "retarget_operation_id",
        "lineage_sha256",
        "original_intent_sha256",
        "original_failure_sha256",
        "original_reconciliation_sha256",
        "pre_retarget_trees",
    )
)


def verify_safety(p, route, legacy):
    require(
        set(p).difference(("clone_recovery",)) == set(legacy.SAFETY_FIELDS) | _OTA_SAFETY_ADDITIONS
        and type(p["schema_version"]) is int
        and p["schema_version"] == 2
        and all(_HEX.match(p[key]) for key in p if key.endswith("_sha256")),
        "native_safety",
    )
    require(
        p["source_ade_path"] == os.path.dirname(SOURCE_PATH) + "/" + TB + "_ADE"
        and p["source_ade_design"] == [SOURCE, TB, "schematic"]
        and re.match(r"/[A-Za-z0-9_./-]+/cdsDefTechLib\Z", p["technology_path"])
        and type(p["supplemental_bytes"]) is int
        and 0 <= p["supplemental_bytes"] <= 67108864
        and type(p["job_limit_bytes"]) is int
        and 1048576 <= p["job_limit_bytes"] <= 4194304,
        "native_safety_values",
    )
    baseline, ota = route["baseline"], route["ota"]
    require(
        p["source_dut_tree_sha256"] == baseline["revision_sha256"]
        and p["source_tb_tree_sha256"] == baseline["testbench_revision_sha256"]
        and p["source_symbol_tree_sha256"] == ota["symbol_tree_sha256"]
        and p["source_ade_tree_sha256"] == ota["ade_state_tree_sha256"],
        "native_safety_baseline",
    )
    if "clone_recovery" in p:
        recovery = p["clone_recovery"]
        require(
            isinstance(recovery, dict)
            and set(recovery) == _CLONE_RECOVERY_FIELDS
            and _OP.match(recovery["retarget_operation_id"])
            and all(_HEX.match(recovery[key]) for key in recovery if key.endswith("_sha256")),
            "clone_recovery_safety",
        )
        trees = recovery["pre_retarget_trees"]
        require(
            set(trees) == set(("child_library", "child_dut", "child_bench", "child_state"))
            and all(_HEX.match(value) for value in trees.values()),
            "clone_recovery_trees",
        )


def verify_clone_lineage(lineage, original_intent, original_failure, receipt, recovery, subject):
    """Verify the separate retarget without treating the failed clone as complete."""
    original = subject["owned_copy_operation_id"]
    retarget = recovery["retarget_operation_id"]
    require(
        len(set((original, retarget, subject["operation_id"]))) == 3
        and _sha(_canonical(lineage)) == recovery["lineage_sha256"]
        and _sha(_canonical(original_intent)) == recovery["original_intent_sha256"]
        and _sha(_canonical(original_failure)) == recovery["original_failure_sha256"]
        and _HEX.match(original_intent["scope_sha256"])
        and original_intent
        == dict(
            scope_sha256=original_intent["scope_sha256"],
            operation_id=original,
            retry=False,
        )
        and original_failure == dict(status="OUTCOME_UNKNOWN", checkpoint="RETARGET")
        and type(lineage["physical_copies_created_here"]) is int
        and lineage
        == dict(
            status="OTA17_ORIGINAL_COPY_WITH_SEPARATE_CORRECTED_RETARGET",
            original_physical_copy_operation_id=original,
            retarget_operation_id=retarget,
            scope_sha256=receipt["scope_sha256"],
            original_failure_sha256=recovery["original_failure_sha256"],
            reconciliation_sha256=recovery["original_reconciliation_sha256"],
            retarget_receipt_sha256=_sha(_canonical(receipt)),
            physical_copies_created_here=0,
        ),
        "clone_lineage",
    )
    before, after = recovery["pre_retarget_trees"], receipt["owned_trees"]
    require(
        (before["child_dut"], before["child_state"]) == (after["dut"], after["state"])
        and before["child_bench"] != after["bench"]
        and before["child_library"] != after["strict_library"],
        "clone_retarget_tree_change",
    )


def verify_clone_receipt(receipt, completion, intent, stdout, pin, subject, generation):
    """Bind the original C1 clone journal without synthesizing a receipt."""
    digest = pin["copy_receipt_sha256"]
    operation = subject["owned_copy_operation_id"]
    require(
        set(receipt)
        == set(
            (
                "status",
                "operation_id",
                "scope_sha256",
                "intent_sha256",
                "original_trees",
                "owned_trees",
                "owned_library",
                "owned_state",
                "original_ac_operation_id",
                "original_dc_operation_id",
                "stdout_sha256",
                "ocean",
                "spectre",
                "reservations",
            )
        )
        and _sha(_canonical(receipt)) == digest
        and completion == dict(receipt_sha256=digest)
        and _HEX.match(receipt["scope_sha256"])
        and _sha(_canonical(intent)) == receipt["intent_sha256"]
        and intent
        == dict(scope_sha256=receipt["scope_sha256"], operation_id=operation, retry=False)
        and (
            receipt["status"],
            receipt["operation_id"],
            receipt["owned_library"],
            receipt["owned_state"],
        )
        == ("OTA17_OWNED_CLONE_RETARGETED", operation, CHILD, CHILD_STATE)
        and all(type(receipt[key]) is int for key in ("ocean", "spectre", "reservations"))
        and (receipt["ocean"], receipt["spectre"], receipt["reservations"]) == (1, 0, 0),
        "clone_journal",
    )
    ids = (
        receipt["original_ac_operation_id"],
        receipt["original_dc_operation_id"],
        operation,
        generation,
        subject["operation_id"],
    )
    marker = ("OTA17_CANDIDATE_BENCH_RETARGETED|" + operation).encode("ascii")
    require(
        all(_OP.match(value) for value in ids)
        and len(set(ids)) == len(ids)
        and _sha(stdout) == receipt["stdout_sha256"]
        and [row for row in stdout.splitlines() if row.startswith(b"OTA17_CANDIDATE_")] == [marker],
        "clone_operation_evidence",
    )
    original, owned = receipt["original_trees"], receipt["owned_trees"]
    fields = set(("library", "strict_library", "dut", "symbol", "bench", "state"))
    require(
        set(original) == set(owned) == fields
        and all(_HEX.match(tree[field]) for tree in (original, owned) for field in fields)
        and (
            original["library"],
            original["dut"],
            original["symbol"],
            original["bench"],
            original["state"],
        )
        == (
            pin["source_library_tree_sha256"],
            pin["source_dut_tree_sha256"],
            pin["source_symbol_tree_sha256"],
            pin["source_tb_tree_sha256"],
            pin["source_ade_tree_sha256"],
        )
        and (owned["strict_library"], owned["dut"], owned["symbol"], owned["bench"])
        == (
            pin["owned_library_tree_sha256"],
            subject["owned_before_view_tree_sha256"],
            pin["owned_symbol_tree_sha256"],
            subject["owned_before_testbench_tree_sha256"],
        ),
        "clone_tree_binding",
    )
    return original, owned


def _skill_links(legacy, terminals):
    return (
        "list("
        + " ".join(
            "list(%s %s)" % (legacy.skill_token(pin), legacy.skill_token(net))
            for pin, net in zip(("D", "G", "S", "B"), terminals)
        )
        + ")"
    )


def skill_values(request, work):
    """Build tokens only from the previously verified route and owned work directory."""
    require(re.match(r"/[A-Za-z0-9_./-]+\Z", work) and ".." not in work.split("/"), "work_path")
    scope, legacy, wlm = request["scope"], request["legacy"], request["wlm"]
    route, plan, subject = scope["route_qualification"], scope["plan"], scope["subject"]
    target = route["target"]
    name = target["netlist_path"].split("/")[1]
    axes = tuple(plan["changed"])
    omit = wlm.wlm_overrides(legacy, axes)
    inventory = " ".join(
        "list(%s %s %s)"
        % (
            legacy.skill_token(row["name"]),
            legacy.skill_token(row["master_cell"]),
            _skill_links(legacy, row["terminals"]),
        )
        for row in route["ota"]["devices"]
    )
    operation = subject["operation_id"]
    return {
        "@LIB@": CHILD,
        "@OWNED@": CHILD_PATH,
        "@SOURCE@": SOURCE_PATH,
        "@SOURCEALIAS@": SOURCE,
        "@OTA_INVENTORY@": "list(" + inventory + ")",
        "@TARGET@": name,
        "@MASTER@": target["instance"]["master_cell"],
        "@TARGET_LINKS@": _skill_links(legacy, target["netlist_terminals"]),
        "@WORK@": work,
        "@OP@": operation,
        "@NETLISTCELL@": "Grel_" + operation.replace("-", "_"),
        "@AXES@": " ".join(legacy.skill_token(axis) for axis in axes),
        "@AXISTOKEN@": "".join(axes),
        "@OVERRIDES@": "'(" + " ".join(legacy.skill_token(key) for key in omit) + ")",
        "@BEFORE@": legacy.skill_check(route["before"], batch_cdf=True),
        "@AFTER@": legacy.skill_check(
            route["before"],
            tuple(key for key in legacy.PROPERTIES if key not in omit),
            batch_cdf=True,
            expected_checks=wlm.wlm_skill_expected(plan["expected"], axes),
        ),
        "@MUTATION@": "mosRequire(mcpMosApplyWL(inst)==t)",
    }


class _OtaJob(object):
    """OTA-specific physical contract. Claim, child launch, and receipts use the stock worker."""

    def __init__(self, runtime, operator, request, digest):
        self.request, self.legacy = request, request["legacy"]
        self.rt, self.h, self.operator = runtime, request["helper"], operator
        self.scope, self.pin, self.approval = request["scope"], request["pin"], request["approval"]
        self.digest, self.collector, self.sizing = digest, request["collector"], request["sizing"]
        self.wlm_phase = request["wlm"]
        self.wlm_axes = tuple(self.scope["plan"]["changed"])
        self.subject, self.route = self.scope["subject"], self.scope["route_qualification"]
        self.operation, self.library = self.subject["operation_id"], CHILD
        self.owned, self.source, self.source_alias = CHILD_PATH, SOURCE_PATH, SOURCE
        self.limit, self.state = self.pin["job_limit_bytes"], self.pin["source_ade_path"]
        self.jobs = runtime.root + "/" + runtime.accounting.JOBS
        self.job = self.jobs + "/" + self.operation
        self.clone_recovery = self.pin.get("clone_recovery")
        self.physical_copy = self.jobs + "/" + self.subject["owned_copy_operation_id"]
        self.copy_operation = (
            self.clone_recovery["retarget_operation_id"]
            if self.clone_recovery is not None
            else self.subject["owned_copy_operation_id"]
        )
        require(
            self.clone_recovery is None
            or self.copy_operation
            not in (
                self.subject["owned_copy_operation_id"],
                self.operation,
                self.route["ota"]["generation_operation_id"],
            ),
            "clone_retarget_identity",
        )
        self.copy = self.jobs + "/" + self.copy_operation
        self.copy_claim = self.copy + "/registered-mos-edit-intent.json"
        self.confirmations = runtime.root + "/" + self.legacy.CONFIRMATIONS
        self.slot = None
        verify_safety(self.pin, self.route, self.legacy)
        baseline = self.route["baseline"]
        (self.analysis,) = [
            row
            for row in runtime.original_registration["routes"]
            if row["design_id"] == baseline["revision"]["design_id"] and row["analysis"] == "ac"
        ]
        require(
            self.analysis["ade"]["source_tree_sha256"] == baseline["testbench_revision_sha256"]
            and self.analysis["source_cell"] == SOURCE_PATH + "/" + TB
            and self.analysis["source_state"] == self.state
            and self.analysis["ade"]["ade_state_tree_sha256"] == self.pin["source_ade_tree_sha256"]
            and self.analysis["ade"]["inputs"]
            == dict(
                analysis="ac",
                start_hz="1",
                stop_hz="1000000000",
                points_per_decade=16,
            )
            and len(self.analysis["ade"]["model_includes"]) == 1
            and self.analysis["ade"]["model_includes"][0]["section"] == "NN",
            "registered_ac",
        )

    def views(self, library):
        return dict(
            dut=self.tree(library + "/" + DUT),
            symbol=self.tree(library + "/" + DUT + "/symbol"),
            tb=self.tree(library + "/" + TB),
        )

    def outside_dut(self):
        return [
            row
            for row in self.rt.copying.snapshot(self.owned)["metadata"]
            if row[1] not in ("", DUT, DUT + "/schematic")
            and not row[1].startswith(DUT + "/schematic/")
        ]

    def _source_guard(self):
        rt, p = self.rt, self.pin
        source = self.views(self.source)
        original = dict(
            library=rt.copying.dependency_snapshot(self.source)["tree_sha256"],
            dut=source["dut"],
            symbol=source["symbol"],
            tb=source["tb"],
            ade=self.tree(self.state),
            protected=self.digest_doc(rt.protected_snapshot()),
        )
        require(
            original
            == dict(
                library=p["source_library_tree_sha256"],
                dut=p["source_dut_tree_sha256"],
                symbol=p["source_symbol_tree_sha256"],
                tb=p["source_tb_tree_sha256"],
                ade=p["source_ade_tree_sha256"],
                protected=p["original_protected_sha256"],
            )
            and self.digest_doc(original) == self.subject["source_preservation_sha256"],
            "original_preservation",
        )
        rt.gate.library_binding({"libraries": self._registered_libraries()})
        rt.gate.model_binding(self.analysis)

    def _capacity(self):
        rt, p = self.rt, self.pin
        domain, binding, user, uid = rt.modules["confirmation"].domain(
            rt.profile, rt.manifest["identity_manifest_sha256"]
        )
        require(
            (domain, user, uid) == (rt.root, self.operator.pw_name, self.operator.pw_uid),
            "operator",
        )
        counter, records = rt.accounting.state(rt.root, binding)
        ledger = rt.operations.read_bytes(rt.root + "/" + rt.accounting.LEDGER)
        require(_sha(ledger) == p["ledger_sha256"], "ledger")
        names = sorted(
            name
            for name in os.listdir(self.jobs)
            if name not in (self.operation, self.copy_operation)
        )
        require(len(names) <= 4096, "retained_jobs_bound")
        retained = [(name, rt.eda.size(self.jobs + "/" + name)) for name in names]
        require(self.digest_doc(retained) == p["retained_jobs_sha256"], "retained_jobs")
        identity = rt.accounting.identity_manifest(rt.root, binding)
        policy = rt.accounting.effective_policy(rt.root, identity)
        require(self.digest_doc(policy) == p["policy_sha256"], "policy")
        copies = max(rt.eda.size(self.copy)[:2]) + max(rt.eda.size(os.path.dirname(self.owned))[:2])
        writer = max(rt.eda.size(self.job)[:2]) if os.path.lexists(self.job) else 0
        remaining = self.limit - copies - writer
        require(remaining > 32768, "receipt_capacity")
        external = max(rt.eda.size(os.path.dirname(self.owned))[:2])
        overhead = rt.layout_retained_bytes() + p["supplemental_bytes"]
        ceiling = policy["result_ceiling_bytes"]
        reserved_ids = set(identity.get("legacy_operation_ids", []))
        reserved_ids.update(intent["operation_id"] for intent, _ in records)
        unreserved = sum(max(size[:2]) for name, size in retained if name not in reserved_ids)
        require(
            max(rt.gate.occupancy()) + overhead + external + remaining <= ceiling
            and counter["result_reserved_bytes"] + overhead + unreserved + self.limit <= ceiling,
            "retention_ceiling",
        )
        fs = os.statvfs(rt.root)
        unit = fs.f_frsize or fs.f_bsize
        limits = rt.profile["limits"]
        floor = max(
            limits["disk_floor_bytes"],
            (fs.f_blocks * unit * limits["disk_floor_percent"] + 99) // 100,
        )
        inflight = sum(
            intent["binding"]["reserve_bytes"] for intent, receipt in records if receipt is None
        )
        require(fs.f_bavail * unit >= floor + inflight + remaining, "disk_floor")
        return self.limit - copies - 32768

    def guard(self, session):
        rt, h, p = self.rt, self.h, self.pin
        session.check()
        require(time.time() < self.scope["valid_until_unix"], "approval_expired")
        rt.read_check({})
        require(not rt.gate.storage.active_eda(rt.root, True), "eda_busy")
        for path in (self.copy, self.owned, self.confirmations):
            rt.copying.owned_parent(path)
        require(
            h.read(self.confirmations + "/" + self.digest + ".json", 4096) == self.approval,
            "native_approval",
        )
        require(not os.path.lexists(self.copy + "/failure.json"), "clone_failure")
        receipt = h.parse(
            _pinned(h.read(self.copy + "/receipt.json", 4096), p["copy_receipt_sha256"])
        )
        original, owned = verify_clone_receipt(
            receipt,
            h.parse(h.read(self.copy + "/complete.json", 4096)),
            h.parse(h.read(self.copy + "/intent.json", 4096)),
            h.read(self.copy + "/work/ocean.stdout", 65536),
            p,
            dict(self.subject, owned_copy_operation_id=self.copy_operation),
            self.route["ota"]["generation_operation_id"],
        )
        if self.clone_recovery is not None:
            rt.copying.owned_parent(self.physical_copy)
            require(
                not any(
                    os.path.lexists(self.physical_copy + "/" + leaf)
                    for leaf in ("complete.json", "receipt.json", "registered-mos-edit-intent.json")
                ),
                "failed_clone_immutable",
            )
            verify_clone_lineage(
                h.parse(h.read(self.copy + "/clone-lineage.json", 4096)),
                h.parse(h.read(self.physical_copy + "/intent.json", 4096)),
                h.parse(h.read(self.physical_copy + "/failure.json", 4096)),
                receipt,
                self.clone_recovery,
                self.subject,
            )
        require(
            self.tree(self.source) == original["strict_library"]
            and self.tree(CHILD_STATE) == owned["state"],
            "clone_retained_source_and_state",
        )
        self._source_guard()
        capacity = self._capacity()
        session.check()
        return capacity

    def _registered_libraries(self):
        libraries = self.analysis["libraries"]
        rows = dict((row["name"], row) for row in libraries)
        require(
            len(libraries) == 5
            and set(rows) == set(("analogLib", "basic", "gpdk090", "cdsDefTechLib", SOURCE)),
            "fixed_libraries",
        )
        tech, source = rows["cdsDefTechLib"], rows[SOURCE]
        require(
            (tech["path"], tech["tree_sha256"])
            == (self.pin["technology_path"], self.pin["technology_tree_sha256"])
            and (source["path"], source["tree_sha256"])
            == (self.source, self.pin["source_library_tree_sha256"])
            and rows["gpdk090"]["tree_sha256"] == self.legacy.SIZING_PDK_TREE_SHA256,
            "registered_library_pins",
        )
        return libraries

    def library_lines(self, extra=None):
        rt = self.rt
        libraries = [(row["name"], row["path"]) for row in self._registered_libraries()]
        libraries.append((CHILD, self.owned))
        if extra is not None:
            require(extra[0] == "MCP_GREL_Work", "netlist_library")
            libraries.append(extra)
        return "".join(
            "DEFINE %s %s\n" % (rt.rendering.token(name), rt.copying.path(path))
            for name, path in libraries
        ).encode("ascii")

    def values(self, work):
        return skill_values(self.request, work)

    def run(self, session, work, program, definitions, phase, markers):
        owner = self
        external = os.path.dirname(self.owned)
        copied = max(self.rt.eda.size(self.copy)[:2])
        deadline = os.times()[4] + 45

        class LiveGuard(object):
            def check(self):
                session.check()
                require(time.time() < owner.scope["valid_until_unix"], "approval_expired")
                writer = max(owner.rt.eda.size(owner.job, live=True)[:2])
                owner.rt.eda.measure_live(
                    session,
                    external,
                    deadline,
                    owner.limit - copied - writer - 32768,
                )

        return self.legacy.Source9MosJob.run(
            self,
            LiveGuard(),
            work,
            program,
            definitions,
            phase,
            markers,
        )

    def snapshot(self, work, stage, views, expected):
        result = dict(
            stage=stage,
            revision_sha256=views["dut"],
            testbench_revision_sha256=views["tb"],
            footprint_sha256=_sha(self.h.read(work + "/footprint.txt", 65536)),
            properties=self.legacy.read_properties(
                self.h.read(work + "/" + stage + ".properties", 8192)
            ),
        )
        if expected == "after":
            self.wlm_phase.wlm_readback(
                self.legacy,
                self.route["before"],
                result["properties"],
                self.scope["plan"]["expected"],
                self.wlm_axes,
            )
        else:
            require(result["properties"] == self.route["before"], "baseline_readback")
        result["receipt_sha256"] = self.digest_doc(result)
        return result

    def phase(self, session, phase, prior):
        require(phase in PHASES, "phase_name")
        if phase == PHASES[1]:
            require(not os.path.lexists(self.job + "/" + self.operation), "reopen_already_claimed")
            prior_doc = self.h.parse(
                _pinned(self.h.read(self.job + "/edit/receipt.json", 16384), prior)
            )
            require(
                (
                    prior_doc["operation_id"],
                    prior_doc["scope_sha256"],
                    prior_doc["plan_sha256"],
                    prior_doc["source_preservation_sha256"],
                )
                == (
                    self.operation,
                    self.digest,
                    self.subject["plan_sha256"],
                    self.subject["source_preservation_sha256"],
                ),
                "predecessor_scope",
            )
        return self.legacy.Source9MosJob.phase(self, session, phase, prior)

    def edit(self, session, work, before):
        legacy, skill = self.legacy, self.request["skill"]
        adapter, child = self.sizing[:2]
        interpreter = os.path.realpath("/usr/bin/python")
        require(
            interpreter.startswith("/usr/bin/")
            and self.rt.modules["probe"].digest_file(interpreter) == legacy.SYSTEM_PYTHON_SHA256,
            "sizing_hash_interpreter",
        )
        values = self.values(work)
        child_path = work + "/verify-wlm-callbacks.py"
        self.rt.eda.write(child_path, child)
        require(self.h.read(child_path, 8192) == child, "sizing_child_readback")
        program = render_ota_skill(
            skill.compose_common(legacy.COMMON)
            + self.wlm_phase.VERIFY_WLM_CALLBACKS
            + adapter.decode("ascii")
            + legacy.SIZING_TRACE_SKILL
            + skill.EDIT_BEGIN
            + skill.EDIT_CHECKS
            + skill.EDIT_END,
            values,
        )
        markers = [
            "MCP_MOS_WL_STAGE|INIT",
            "MCP_MOS_WL_STAGE|FIELD|" + self.wlm_axes[0],
            "MCP_MOS_WL_STAGE|COMMIT",
            "MCP_MOS_WL_STAGE|DONE",
            "MCP_MOS_WL_READY_FOR_SAVE_CHECK",
            "C6_MOS_EDIT_SAVED|" + self.operation,
        ]
        output = self.run(session, work, program, self.library_lines(), "edit", markers)
        self.save_document(
            work + "/edit-timing.json",
            dict(
                operation_id=self.operation,
                stdout_sha256=_sha(output),
                samples=legacy.sizing_edit_timing(output),
            ),
        )
        saved = self.views(self.owned)
        require(
            saved["dut"] != before["dut"]
            and saved["tb"] == before["tb"]
            and saved["symbol"] == before["symbol"],
            "saved_revision",
        )
        return dict(
            operation_id=self.operation,
            scope_sha256=self.digest,
            plan_sha256=self.subject["plan_sha256"],
            source_preservation_sha256=self.subject["source_preservation_sha256"],
            baseline=self.snapshot(work, "baseline", before, "before"),
            saved=self.snapshot(work, "saved", saved, "after"),
        )

    def _remap_state(self, target, cell, project):
        rt, h = self.rt, self.h
        info = target + "/ADE_state.info"
        original = h.read(info, 65536)
        data = rt.copying.remap_ade_info(
            original,
            self.pin["source_ade_design"],
            ("MCP_GREL_Work", cell, "schematic"),
            project,
        )
        origin = os.lstat(info)
        fd = os.open(info, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "wb") as stream:
            require(
                h.identity(os.fstat(stream.fileno())) == h.identity(origin), "ade_info_identity"
            )
            stream.truncate(0)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        rt.copying.sync(target)
        require(h.read(info, 65536) == data, "ade_info_readback")

    def reopen(self, session, selected, work, before, saved):
        rt, h, legacy, skill = self.rt, self.h, self.legacy, self.request["skill"]
        tb_path = self.owned + "/" + TB
        tb, ade = rt.copying.snapshot(tb_path), rt.copying.snapshot(self.state)
        require(ade["tree_sha256"] == self.pin["source_ade_tree_sha256"], "source_ade")
        rt.eda.copy_capacity({"testbench": tb, "state": ade}, self.job, self.guard(session))
        values = self.values(work)
        cell = values["@NETLISTCELL@"]
        project, library = selected + "/project", selected + "/library"
        state_root = selected + "/state-root"
        target = state_root + "/MCP_GREL_Work/" + cell + "/spectre/state1"
        for path in (
            project,
            library,
            state_root,
            state_root + "/MCP_GREL_Work",
            state_root + "/MCP_GREL_Work/" + cell,
            os.path.dirname(target),
        ):
            rt.operations.directory(path, rt.accounting)
        rt.copying.copy_owned(tb_path, library + "/" + cell, tb["tree_sha256"])
        rt.copying.copy_owned(self.state, target, ade["tree_sha256"])
        self._remap_state(target, cell, project)
        frozen = rt.copying.snapshot(target)
        copied_bench = rt.copying.snapshot(library + "/" + cell)
        require(copied_bench["content_sha256"] == tb["content_sha256"], "copied_bench")
        collector = self.collector.decode("ascii")
        needle = 'outfile("cdf-frame.txt")'
        require(collector.count(needle) == 1, "cdf_output")
        collector = collector.replace(needle, 'outfile("@WORK@/cdf-frame.txt")')
        script = (
            'unless(ddGetObj("MCP_GREL_Work")~>readPath=="%s" exit(1))\n' % library
            + skill.compose_common(legacy.COMMON)
            + collector
            + skill.REOPEN
        )
        inputs = self.analysis["ade"]["inputs"]
        netlist = rt.modules["rendering"].netlist(
            self.job,
            "schematic",
            "state1",
            [],
            inputs,
            self.digest,
            self.operation,
        )
        self.run(
            session,
            work,
            render_ota_skill(script, values) + netlist,
            self.library_lines(("MCP_GREL_Work", library)),
            "reopen",
            [
                "C6_MOS_READ_ONLY_CLOSED|" + self.operation,
                "MCP_GENERIC_ADE_NETLIST|" + self.digest + "|" + self.operation,
            ],
        )
        require(
            self.views(self.owned) == before
            and rt.copying.snapshot(target) == frozen
            and rt.copying.snapshot(tb_path) == tb
            and rt.copying.snapshot(library + "/" + cell) == copied_bench,
            "reopened_revision",
        )
        reopened = self.snapshot(work, "reopened", before, "after")
        require(
            reopened["footprint_sha256"] == saved["saved"]["footprint_sha256"]
            and reopened["properties"] == saved["saved"]["properties"],
            "reopened_footprint",
        )
        cdf = h.read(work + "/cdf-frame.txt", 65536)
        raw = h.read(rt.eda.find_input(project), 32768, False)
        require(
            raw and cdf.startswith(b"M2_CDF_V2\n") and cdf.endswith(b"COMPLETE\n"),
            "native_artifacts",
        )
        rt.eda.write(selected + "/effective-input.scs", raw)
        receipt = dict(saved)
        receipt.update(
            reopened=reopened,
            netlisted_revision_sha256=before["dut"],
            netlisted_testbench_revision_sha256=before["tb"],
            netlist_sha256=_sha(raw),
            cdf_frame_sha256=_sha(cdf),
        )
        receipt["netlist_receipt_sha256"] = self.digest_doc(receipt)
        return receipt, dict(
            readback=receipt,
            input_base64=base64.b64encode(raw).decode("ascii"),
            cdf_frame_base64=base64.b64encode(cdf).decode("ascii"),
        )


def new_job(runtime, operator, request, digest):
    """Compose with the pinned stock worker for journal, marker and launch primitives."""

    class Job(_OtaJob, request["legacy"].Source9MosJob):
        pass

    return Job(runtime, operator, request, digest)


def ota_main():
    import pwd

    require(
        sys.version_info[:2] == (2, 6)
        and os.getuid() != 0
        and not sys.flags.optimize
        and len(sys.argv) == 3,
        "native_identity",
    )
    digest, phase = sys.argv[1:]
    raw = sys.stdin.read(524289)
    request = read_request(raw, digest, phase, time.time())
    helper, scope, pin = request["helper"], request["scope"], request["pin"]
    operator = pwd.getpwuid(os.getuid())
    root = helper.private_path(request["root"], operator.pw_dir)
    runtime_scope = dict(
        scope,
        native=dict(
            layout_manifest_sha256=pin["layout_manifest_sha256"],
            layout_worker_sha256=pin["layout_worker_sha256"],
        ),
    )
    _, runtime = helper.load_runtime(root, runtime_scope)
    os.umask(63)
    with runtime.accounting.ReservationSession(root) as session:
        job = new_job(runtime, operator, request, digest)
        result = helper.canonical(job.phase(session, phase, request["prior"]))
        require(len(result) <= 524288, "response_bound")
        session.check()
        sys.stdout.write(result)


if __name__ == "__main__":
    ota_main()
