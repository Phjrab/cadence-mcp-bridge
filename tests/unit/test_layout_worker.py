"""Disposable shared-lock/journal and synthetic native frame tests; no VM calls."""

import copy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_layout_engine import _ORIENT_BOXES, _orient_snapshot
from test_layout_models import fixture_request, fixture_snapshot, reseal
from test_shared_reservations import root as root_fixture

from cadence_mcp_bridge import _layout_rendering as rendering
from cadence_mcp_bridge import _layout_worker as worker
from cadence_mcp_bridge import _native_operations as operations
from cadence_mcp_bridge import _shared_reservations as ledger
from cadence_mcp_bridge.layout_engine import build_plan
from cadence_mcp_bridge.layout_models import LayoutApplyRequest, LayoutSnapshot, OrientEdit

root = root_fixture


@pytest.mark.parametrize(
    "selected", [[], None, ["Unknown"], ["Tech", "Tech"], ["Tech"] * 9, "Tech", [[]]]
)
def test_invalid_probe_scope_rejected_before_runtime_or_program(selected):
    registration = {
        "schema_version": 1,
        "routes": [],
        "libraries": [{"name": "Tech"}],
        "owned_libraries": [],
        "protected_views": [],
        "seed": None,
        "probe_libraries": selected,
    }
    # No native module or profile can be touched before rejecting this input.
    with pytest.raises(ValueError, match="probe_library_scope"):
        worker.FixedLayoutRuntime(None, None, registration, None, None, None, None, None)
    runtime = object.__new__(worker.FixedLayoutRuntime)
    runtime.registration = registration
    with pytest.raises(ValueError, match="probe_library_scope"):
        runtime.operator_probe(None)


@pytest.mark.parametrize("selected", [None, ["Design", "Tech"]])
def test_probe_selects_two_but_check_protects_all_six(selected):
    names = ["Design", "Analog", "Basic", "Tech", "SourceA", "SourceB"]
    runtime = object.__new__(worker.FixedLayoutRuntime)
    runtime.registration = {"libraries": [{"name": name} for name in names], "routes": []}
    if selected is not None:
        runtime.registration["probe_libraries"] = selected
    guarded, programs, protections = [], [], []
    runtime.root = "/synthetic"

    class Session:
        root = runtime.root

        def check(self):
            pass

    runtime.accounting = SimpleNamespace(
        ReservationSession=Session,
        state=lambda *a: ({"result_reserved_bytes": 0}, []),
        identity_manifest=lambda *a: {},
        effective_policy=lambda *a: {"result_ceiling_bytes": 33554432},
    )
    runtime.read_check = lambda request: {
        "valid_until_unix": float("inf"),
        "actions": ["probe"],
        "max_job_bytes": 1048576,
    }
    runtime.profile = {"limits": {"disk_floor_bytes": 0, "disk_floor_percent": 0}}
    runtime.native_assets = {"profile.json": b"profile", "probe.py": b"probe"}
    runtime.manifest = {"resource_domain_sha256": "a" * 64, "identity_manifest_sha256": "b" * 64}
    runtime.modules = {
        "probe": SimpleNamespace(
            observe=lambda *a: {"free_bytes": 33554432, "total_bytes": 33554432}
        )
    }
    runtime.gate = SimpleNamespace(library_binding=guarded.append, occupancy=lambda: (0, 0))
    runtime.protected_snapshot = lambda: protections.append("checked")
    runtime.layout_retained_bytes = lambda: 0
    runtime.rendering = SimpleNamespace(probe_script=lambda libs, routes: libs)
    runtime._job = lambda: "synthetic-job"

    def program(session, script, route, job):
        programs.append(script)
        return b"MCP_LAYOUT_PROBE|1\nEND_LAYOUT_PROBE\n"

    runtime._program = program
    session = Session()
    runtime.check(session, {"action": "probe"})
    runtime.operator_probe(session)
    runtime.check(session, {"action": "probe"})
    assert programs == [selected if selected is not None else names]
    assert guarded == [{"libraries": runtime.registration["libraries"]}] * 2
    assert len(guarded[0]["libraries"]) == 6 and protections == ["checked", "checked"]


class Runtime:
    rendering = rendering
    orientation_qualification = None

    def __init__(self, root):
        self.root = str(root)
        self.snapshot = fixture_snapshot()
        self.writes = 0
        self.denied = False
        self.failure = False
        self.protected = "original"

    def read_check(self, request):
        return None

    def check(self, session, request):
        session.check()
        if self.denied:
            raise ValueError("synthetic_authority_denied")

    def inspect_for_write(self, action, request):
        return self.snapshot.model_dump(mode="json"), {}, {}

    def protected_snapshot(self):
        return self.protected

    def destination_check(self, action, route):
        return None

    def write(self, session, action, request, before, selectors, route, job):
        self.writes += 1
        if self.failure:
            raise OSError("synthetic failure after durable intent")
        after = worker.predict(before, request["plan"]["normalized_edits"], rendering)
        after.pop("semantic_sha256")
        after.update(provenance="native_readback")
        for pin in after["pins"]:
            pin["association"] = "native_verified"
        self.snapshot = LayoutSnapshot.model_validate_json(worker.canonical(after))
        return {"snapshot": self.snapshot.model_dump(mode="json"), "saved": True, "reopened": True}


def request_for(snapshot):
    request = fixture_request(snapshot)
    edits = tuple(
        e.model_copy(update={"label": None}) if e.kind == "add_pin" else e for e in request.edits
    )
    plan = build_plan(snapshot, request.model_copy(update={"edits": edits}))
    return LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256).model_dump(
        mode="json"
    )


def orientation_request(snapshot=None, target="R90"):
    snapshot = snapshot or _orient_snapshot()
    request = fixture_request(snapshot).model_copy(
        update={"edits": (OrientEdit(kind="orient", object_id="inst-one", orientation=target),)}
    )
    plan = build_plan(snapshot, request)
    return LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256).model_dump(
        mode="json"
    )


@pytest.mark.parametrize("old", tuple(_ORIENT_BOXES))
@pytest.mark.parametrize("target", tuple(_ORIENT_BOXES))
def test_orientation_worker_exact_asymmetric_pairs(old, target):
    snapshot = _orient_snapshot(old)
    before = snapshot.model_dump(mode="json")
    frozen = copy.deepcopy(before)
    if old == target:
        command = {
            "kind": "orient",
            "object_id": "inst-one",
            "before_sha256": worker.object_digest(before["instances"][0]),
            "orientation": target,
            "origin_dbu": before["instances"][0]["origin_dbu"],
            "bbox_dbu": before["instances"][0]["bbox_dbu"],
        }
        with pytest.raises(ValueError, match="no_change"):
            worker.predict(before, [command], rendering)
    else:
        request = orientation_request(snapshot, target)
        after = worker.predict(before, request["plan"]["normalized_edits"], rendering)
        lowx, lowy, highx, highy = _ORIENT_BOXES[target]
        assert after["instances"][0]["bbox_dbu"] == dict(
            lower_left=dict(x=lowx, y=lowy), upper_right=dict(x=highx, y=highy)
        )
        assert after["instances"][0]["orientation"] == target
        assert after["instances"][0]["origin_dbu"] == before["instances"][0]["origin_dbu"]
        assert after["instances"][0]["master_id"] == before["instances"][0]["master_id"]
        assert after["shapes"] == before["shapes"] and after["pins"] == before["pins"]
    assert before == frozen


def seal_orientation_request(request):
    request["plan"]["plan_sha256"] = "0" * 64
    pin = worker.digest(request["plan"])
    request["plan"]["plan_sha256"] = request["expected_plan_sha256"] = pin


def qualify(runtime):
    runtime.orientation_qualification = {
        "binding": runtime.snapshot.binding.model_dump(mode="json"),
        "orientations": ["R0", "R90"],
    }


@pytest.mark.parametrize(
    "fault",
    [
        "hash",
        "origin",
        "bbox",
        "extra",
        "offgrid",
        "boolean",
        "overflow",
        "unknown",
        "unregistered",
        "noninstance",
        "duplicate",
        "pcell",
        "capability",
        "request",
        "dropped",
        "qualification",
        "mirror-target",
        "mirror-source",
        "prediction",
    ],
)
def test_orientation_invalid_raw_command_never_publishes_intent(root, fault):
    runtime = Runtime(root)
    runtime.snapshot = _orient_snapshot("MX" if fault == "mirror-source" else "R0")
    qualify(runtime)
    request = orientation_request(runtime.snapshot, "MX" if fault == "mirror-target" else "R90")
    command = request["plan"]["normalized_edits"][0]
    if fault == "hash":
        command["before_sha256"] = "f" * 64
    elif fault == "origin":
        command["origin_dbu"]["x"] += 5
    elif fault == "bbox":
        command["bbox_dbu"]["lower_left"]["x"] += 5
    elif fault == "extra":
        command["angle"] = 90
    elif fault == "offgrid":
        command["origin_dbu"]["x"] += 1
    elif fault == "boolean":
        command["origin_dbu"]["x"] = True
    elif fault == "overflow":
        command["bbox_dbu"]["upper_right"]["x"] = 2147483648
    elif fault == "unknown":
        command["orientation"] = "R45"
    elif fault == "unregistered":
        runtime.snapshot = reseal(
            runtime.snapshot,
            technology=runtime.snapshot.technology.model_copy(
                update={"supported_orientations": ("R0",)}
            ),
        )
    elif fault == "noninstance":
        command["object_id"] = "rect-one"
    elif fault == "duplicate":
        request["plan"]["normalized_edits"].append(copy.deepcopy(command))
    elif fault == "pcell":
        runtime.snapshot = reseal(
            runtime.snapshot,
            instances=(runtime.snapshot.instances[0].model_copy(update={"pcell_submaster": True}),),
        )
    elif fault == "capability":
        runtime.snapshot = reseal(
            runtime.snapshot,
            capabilities=runtime.snapshot.capabilities.model_copy(update={"rotate": "unsupported"}),
        )
    elif fault == "request":
        request["plan"]["request"]["edits"][0]["orientation"] = "MX"
    elif fault == "dropped":
        request["plan"]["normalized_edits"] = request_for(runtime.snapshot)["plan"][
            "normalized_edits"
        ]
    elif fault == "prediction":
        request["plan"]["expected_semantic_sha256"] = "f" * 64
    elif fault == "qualification":
        runtime.orientation_qualification = None
    request["plan"]["baseline_sha256"] = runtime.snapshot.semantic_sha256
    seal_orientation_request(request)
    with pytest.raises(ValueError):
        worker.LayoutWorker(runtime, ledger, operations).execute("apply", request)
    assert runtime.writes == 0 and not list(root.rglob("layout-intent.json"))


@pytest.mark.parametrize(
    "fault",
    [None, "write", "master", "origin", "bbox", "orientation", "protected", "saved", "reopened"],
)
def test_orientation_transaction_preservation_and_durable_replay(root, fault):
    class OrientRuntime(Runtime):
        def write(self, *args):
            observed = super().write(*args)
            if fault in ("saved", "reopened"):
                observed[fault] = False
            elif fault == "protected":
                self.protected = "changed"
            elif fault in ("master", "origin", "bbox", "orientation"):
                obj = observed["snapshot"]["instances"][0]
                if fault == "master":
                    obj["master_id"] = "changed-master"
                elif fault == "origin":
                    obj["origin_dbu"]["x"] += 5
                elif fault == "bbox":
                    obj["bbox_dbu"]["upper_right"]["x"] += 5
                else:
                    obj["orientation"] = "MX"
            return observed

    runtime = OrientRuntime(root)
    runtime.snapshot = _orient_snapshot()
    qualify(runtime)
    runtime.failure = fault == "write"
    request = orientation_request(runtime.snapshot)
    counter = (root / ledger.LEDGER).read_bytes()
    native = worker.LayoutWorker(runtime, ledger, operations)
    if fault:
        with pytest.raises((ValueError, OSError)):
            native.execute("apply", request)
        assert list(root.rglob("layout-failure.json")) and not list(
            root.rglob("layout-complete.json")
        )
    else:
        assert native.execute("apply", request)["state"] == "SUCCEEDED"
    # Fresh worker object, same durable ID: no extra write even after expiry.
    runtime.denied = True
    result = worker.LayoutWorker(runtime, ledger, operations).execute("apply", request)
    assert result["state"] == ("OUTCOME_UNKNOWN" if fault else "SUCCEEDED")
    assert result["replayed"] and not result["executed"] and runtime.writes == 1
    assert (root / ledger.LEDGER).read_bytes() == counter


def test_real_shared_lock_receipt_replay_sealed_target_and_counter_unchanged(root):
    runtime = Runtime(root)
    native = worker.LayoutWorker(runtime, ledger, operations)
    request = request_for(runtime.snapshot)
    counter = (root / ledger.LEDGER).read_bytes()
    reply = native.execute("apply", request)
    assert reply["state"] == "SUCCEEDED" and runtime.writes == 1
    runtime.denied = True
    replay = worker.LayoutWorker(runtime, ledger, operations).execute("apply", request)
    assert replay["replayed"] and not replay["executed"] and runtime.writes == 1
    runtime.denied = False
    # Same sealed revision with another UUID is rejected even with fresh geometry.
    fresh = fixture_request(runtime.snapshot)
    fresh = fresh.model_copy(update={"operation_id": str(uuid4()), "edits": fresh.edits[:1]})
    new_plan = build_plan(runtime.snapshot, fresh)
    another = LayoutApplyRequest(plan=new_plan, expected_plan_sha256=new_plan.plan_sha256)
    another = another.model_dump(mode="json")
    with pytest.raises(ValueError, match="already_sealed"):
        native.execute("apply", another)
    assert (root / ledger.LEDGER).read_bytes() == counter
    assert runtime.protected == "original"


def test_uncertain_intent_never_redispatches_and_conflicting_id_rejects(root):
    runtime = Runtime(root)
    native = worker.LayoutWorker(runtime, ledger, operations)
    request = request_for(runtime.snapshot)
    runtime.failure = True
    with pytest.raises(OSError):
        native.execute("apply", request)
    assert runtime.writes == 1
    reply = native.execute("apply", request)
    assert reply["state"] == "OUTCOME_UNKNOWN" and runtime.writes == 1
    changed = copy.deepcopy(request)
    changed["expected_plan_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="replay_conflict"):
        native.execute("apply", changed)
    assert list(root.rglob("layout-failure.json"))


def test_auth_or_stale_baseline_does_not_publish_intent(root):
    runtime = Runtime(root)
    native = worker.LayoutWorker(runtime, ledger, operations)
    request = request_for(runtime.snapshot)
    runtime.denied = True
    with pytest.raises(ValueError, match="authority_denied"):
        native.execute("apply", request)
    runtime.denied = False
    request["plan"]["baseline_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="stale_baseline"):
        native.execute("apply", request)
    assert not list(root.rglob("layout-intent.json")) and runtime.writes == 0


def test_orientation_qualification_projects_only_exact_child_and_keeps_observed_mirror():
    child = _orient_snapshot().binding.model_dump(mode="json")
    parent = dict(
        child,
        revision_id=child["parent_revision_id"],
        parent_revision_id=None,
        parent_revision_sha256=None,
    )
    child_route = dict(binding=child, owned=True, read_only=False)
    parent_route = dict(binding=parent, owned=True, read_only=False)
    qualification = {"binding": child, "orientations": ["R0", "R90"]}
    registration = {
        "routes": [parent_route, child_route],
        "orientation_qualification": qualification,
    }
    assert worker.orientation_qualification(registration, rendering) == qualification
    raw = (
        b"MCP_LAYOUT_FRAME|1\nTECH|1000|5\n"
        b"I|inst-one|I0|SeedLib|RectMaster|layout|R0|0|0|0|0|0|100|200\n"
        b"I|inst-two|I1|SeedLib|RectMaster|layout|MX|0|0|0|0|-200|100|0\nEND_LAYOUT_FRAME\n"
    )
    baseline, _ = worker.parse_frame(raw, parent_route, rendering)
    source, _ = worker.parse_frame(raw, parent_route, rendering, qualification)
    assert source == baseline and source["capabilities"]["rotate"] == "unsupported"
    before, _ = worker.parse_frame(raw, child_route, rendering, qualification)
    after, _ = worker.parse_frame(
        raw.replace(b"|R0|0|0|0|0|0|100|200", b"|R90|0|0|0|-200|0|0|100"),
        child_route,
        rendering,
        qualification,
    )
    assert before["technology"]["supported_orientations"] == ["MX", "R0", "R90"]
    assert before["technology"] == after["technology"]
    assert before["capabilities"]["rotate"] == after["capabilities"]["rotate"] == "not_verified"
    assert before["semantic_sha256"] != after["semantic_sha256"]
    projected = copy.deepcopy(source)
    projected["binding"] = child
    worker.project_orientation(projected, qualification)
    assert worker.geometry(projected) == worker.geometry(before)
    child_route["read_only"] = True
    with pytest.raises(ValueError, match="owned_route_required"):
        worker.orientation_qualification(registration, rendering)


def test_native_frame_model_hash_and_semantic_normalization():
    reference = fixture_snapshot()
    route = {
        "binding": reference.binding.model_dump(mode="json"),
        "owned": True,
        "read_only": False,
    }
    raw = (
        b"noise\nMCP_LAYOUT_FRAME|1\nTECH|1000|5\nLPP|metal1|drawing\nLPP|metal1|pin\n"
        b"I|-|I0|SeedLib|RectMaster|layout|R0|0|0|0|0|0|100|200\n"
        b"S|-|rect|metal1|drawing|300|0|400|100\n"
        b"P|-|metal1|pin|old_net|OUT|0|300|100|400\nEND_LAYOUT_FRAME\n"
    )
    parsed, selectors = worker.parse_frame(raw, route, rendering)
    snapshot = LayoutSnapshot.model_validate_json(worker.canonical(parsed))
    assert snapshot.semantic_sha256 == worker.snapshot_digest(parsed)
    assert len(selectors) == 3 and snapshot.pins[0].association == "native_verified"
    shuffled = reseal(
        snapshot,
        technology=snapshot.technology.model_copy(
            update={
                "provenance": "synthetic_fixture",
                "allowed_layer_purposes": snapshot.technology.allowed_layer_purposes[::-1],
            }
        ),
    )
    assert worker.geometry(shuffled.model_dump(mode="json")) == worker.geometry(parsed)
    assert all("0x" not in key for key in selectors)
    with pytest.raises(ValueError, match="unknown_or_malformed"):
        worker.parse_frame(raw.replace(b"S|-|rect", b"S|-|polygon"), route, rendering)


def test_safe_error_reasons_do_not_echo_arbitrary_exception():
    assert worker.safe_reason(ValueError("layout_stale_baseline")) == "layout_revision_conflict"
    assert worker.safe_reason(OSError(11, "private path")) == "layout_resource_lock_busy"
    assert worker.safe_reason(ValueError("secret proprietary content")) == "layout_outcome_unknown"


def test_explicit_native_error_precedes_frame_and_success_marker():
    snapshot = fixture_snapshot()
    route = {"binding": snapshot.binding.model_dump(mode="json"), "owned": True, "read_only": False}
    raw = (
        b"MCP_LAYOUT_FRAME|1\nTECH|1000|5\nLPP|metal1|drawing\n"
        b"END_LAYOUT_FRAME\nMCP_LAYOUT_ERROR|unsupported_source_shape\n"
        b"MCP_LAYOUT_SAVED_REOPENED|1\n"
    )
    with pytest.raises(ValueError, match="native_error_record"):
        worker.parse_frame(raw, route, rendering)


def test_non_ascii_banner_is_excluded_but_frame_encoding_stays_strict():
    route = {
        "binding": fixture_snapshot().binding.model_dump(mode="json"),
        "owned": True,
        "read_only": False,
    }
    frame = b"MCP_LAYOUT_FRAME|1\nTECH|1000|5\nLPP|metal1|drawing\nEND_LAYOUT_FRAME\n"
    clean, unused = worker.parse_frame(frame, route, rendering)
    banner = b"COPYRIGHT \xa9\n"
    actual, unused = worker.parse_frame(banner + frame + banner, route, rendering)
    assert actual == clean
    with pytest.raises(UnicodeDecodeError):
        worker.parse_frame(frame.replace(b"metal1", b"metal\xa9"), route, rendering)
    for raw in (
        banner + b"MCP_LAYOUT_ERROR|failed\n" + frame,
        frame + banner + b"MCP_LAYOUT_ERROR|failed\n",
    ):
        with pytest.raises(ValueError, match="native_error_record"):
            worker.parse_frame(raw, route, rendering)


@pytest.mark.parametrize("fault", [None, "encoding", "duplicate", "reversed", "error"])
def test_probe_banner_excluded_and_malformed_protocol_rejected(fault):
    runtime = object.__new__(worker.FixedLayoutRuntime)
    runtime.registration = {"libraries": [{"name": "Tech"}], "routes": []}
    runtime.rendering = rendering
    runtime._job = lambda: "synthetic-job"
    frame = b"MCP_LAYOUT_PROBE|1\nAPI|dbSave|t\nTECHLIB|Tech|1000|0.005\nEND_LAYOUT_PROBE\n"
    raw = (
        b"COPYRIGHT \xa9\n"
        + frame.replace(b"API|", b"loading chatter \xff\nAPI|")
        + b"noise \xff\n"
    )
    if fault == "encoding":
        raw = raw.replace(b"dbSave", b"db\xa9Save")
    elif fault == "duplicate":
        raw += frame
    elif fault == "reversed":
        raw = b"END_LAYOUT_PROBE\nMCP_LAYOUT_PROBE|1\n"
    elif fault == "error":
        raw += b"MCP_LAYOUT_ERROR|failed\n"
    runtime._program = lambda *args: raw
    if fault:
        with pytest.raises(ValueError):
            runtime.operator_probe(None)
    else:
        assert runtime.operator_probe(None) == {"observation": frame.decode("ascii")}


def test_none_is_a_persistent_id_distinct_from_absent_property():
    snapshot = fixture_snapshot()
    route = {"binding": snapshot.binding.model_dump(mode="json"), "owned": True, "read_only": False}
    raw = (
        b"MCP_LAYOUT_FRAME|1\nTECH|1000|5\nLPP|metal1|drawing\n"
        b"S|none|rect|metal1|drawing|0|0|100|100\nEND_LAYOUT_FRAME\n"
    )
    parsed, unused = worker.parse_frame(raw, route, rendering)
    assert parsed["shapes"][0]["object_id"] == "none"
    absent, unused = worker.parse_frame(raw.replace(b"S|none|", b"S|-|"), route, rendering)
    assert absent["shapes"][0]["object_id"].startswith("s-")


@pytest.mark.parametrize("failure", [False, True])
def test_operator_seed_uses_durable_identity_and_preserves_failure(root, failure):
    from types import SimpleNamespace

    snapshot = fixture_snapshot().model_dump(mode="json")
    snapshot["pins"] = []
    route = {
        "binding": snapshot["binding"],
        "owned": True,
        "read_only": False,
        "cellview": {"library": "Owned", "cell": "Seed", "view": "layout"},
        "path": str(root / "Owned" / "Seed" / "layout"),
    }
    runtime = object.__new__(worker.FixedLayoutRuntime)
    runtime.root, runtime.accounting, runtime.operations = str(root), ledger, operations
    runtime.rendering = rendering
    runtime.registration = {
        "routes": [route],
        "owned_libraries": [{"name": "Owned", "path": str(root) + "/Owned"}],
        "seed": {
            "revision_id": snapshot["binding"]["revision_id"],
            "technology_library": "ObservedTech",
            "master_cell": "RectMaster",
            "technology": snapshot["technology"],
            "layer_purpose": snapshot["technology"]["allowed_layer_purposes"][0],
        },
    }
    runtime.copying = SimpleNamespace(path=lambda p: p, owned_parent=lambda p: None)
    runtime.check = lambda session, request: session.check()
    runtime.read_check = lambda request: None
    runtime.protected_snapshot = lambda: "original"
    writes = []
    # Renderer path syntax is POSIX-only; this test isolates durable dispatch on Windows.
    runtime.rendering = SimpleNamespace(seed_script=lambda *a: b"fixed seed")

    def program(session, script, selected, job):
        writes.append(job)
        (root / "Owned").mkdir()
        if failure:
            raise OSError("synthetic seed failure")
        return b"MCP_LAYOUT_SAVED_REOPENED|1\n", snapshot, {}

    runtime._program = program
    operation_id = str(uuid4())
    if failure:
        with pytest.raises(OSError, match="seed failure"):
            runtime.operator_seed(operation_id)
        assert runtime.operator_seed(operation_id)["state"] == "OUTCOME_UNKNOWN"
        assert list(root.rglob("layout-failure.json"))
    else:
        assert runtime.operator_seed(operation_id)["state"] == "SUCCEEDED"
    assert runtime.operator_seed(operation_id)["replayed"]
    assert len(writes) == 1
    with pytest.raises(ValueError, match="seed_library_exists"):
        runtime.operator_seed(str(uuid4()))
    assert len(writes) == 1
