"""Layout transaction core for an authenticated fixed native runner, Python 2.6.

The parent runner supplies its verified runtime, shared ReservationSession and
the existing operation I/O primitives. No default/fallback runtime, CLI, grant
writer, shell evaluator, simulator or alternate lock is provided here.
"""

# mypy: ignore-errors
# ruff: noqa: UP004, UP031, SIM105
import sys

if __name__ == "__main__":
    if not sys.flags.ignore_environment or not sys.flags.no_user_site:
        sys.stderr.write("LAYOUT_FIXED_WORKER_REJECTED:layout_runtime_trust_failed\n")
        sys.exit(1)
    _entry = sys.path[0] if sys.path else None
    sys.path[:] = [p for p in sys.path if p and p != _entry]

import copy
import hashlib
import json
import os
import stat
import time
import types
import uuid

LIMIT = 262144


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def object_digest(value):
    value = copy.deepcopy(value)
    if "association" in value:
        value["association"] = "not_verified"
    return digest(value)


def geometry(snapshot):
    """Compare logical geometry independent of observation/verification labels."""
    value = copy.deepcopy(snapshot)
    value.pop("semantic_sha256", None)
    value.pop("provenance", None)
    value.pop("capabilities", None)
    value["technology"]["provenance"] = "synthetic_fixture"
    value["technology"]["allowed_layer_purposes"] = sorted(
        value["technology"]["allowed_layer_purposes"], key=lambda p: (p["layer"], p["purpose"])
    )
    value["technology"]["supported_orientations"] = sorted(
        value["technology"]["supported_orientations"]
    )
    for key in ("instances", "shapes", "pins"):
        value[key] = sorted(value.get(key, []), key=lambda item: item["object_id"])
        for item in value[key]:
            item.pop("association", None)
    return value


def shifted(point, dx, dy):
    return {"x": point["x"] + dx, "y": point["y"] + dy}


CAPABILITIES = dict(
    (k, "unsupported")
    for k in ("rotate", "edit_path", "delete", "pcell_parameters", "via", "auto_route")
)
CAPABILITIES.update(move="not_verified", add_rect="not_verified", add_pin="not_verified")


def snapshot_digest(snapshot):
    value = copy.deepcopy(snapshot)
    value["semantic_sha256"] = "0" * 64
    value["provenance"] = "plan_prediction"
    value["capabilities"] = dict(CAPABILITIES)
    value["technology"]["provenance"] = "synthetic_fixture"
    value["technology"]["allowed_layer_purposes"] = sorted(
        value["technology"]["allowed_layer_purposes"], key=lambda p: (p["layer"], p["purpose"])
    )
    value["technology"]["supported_orientations"] = sorted(
        value["technology"]["supported_orientations"]
    )
    for key in ("instances", "shapes", "pins"):
        value[key] = sorted(value[key], key=lambda o: o["object_id"])
    for pin in value["pins"]:
        pin["association"] = "not_verified"
    return digest(value)


def protocol_lines(raw, start, end, reason, prefixes=None):
    """Ignore banner bytes outside one frame; keep protocol ASCII strict."""
    if len(raw) > LIMIT:
        raise ValueError("layout_frame_size")
    lines = raw.splitlines()
    if any(line.startswith(b"MCP_LAYOUT_ERROR|") for line in lines):
        raise ValueError("layout_native_error_record")
    starts = [i for i, line in enumerate(lines) if line == start]
    ends = [i for i, line in enumerate(lines) if line == end]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise ValueError(reason)
    selected = lines[starts[0] : ends[0] + 1]
    if prefixes is not None:
        # Probe technology loading may interleave private diagnostic chatter.
        selected = [line for line in selected if line in (start, end) or line.startswith(prefixes)]
    return [line.decode("ascii") for line in selected]


def parse_frame(raw, route, rendering):
    """Closed bounded frame; private selectors never leave the worker."""
    lines = protocol_lines(
        raw, b"MCP_LAYOUT_FRAME|1", b"END_LAYOUT_FRAME", "layout_frame_delimiters"
    )
    rows = [line.split("|") for line in lines[1:-1]]
    if not rows or len(rows[0]) != 3 or rows[0][0] != "TECH":
        raise ValueError("layout_frame_technology")
    dbu, grid = [int(v) for v in rows[0][1:]]
    if not 0 < dbu <= 1000000000 or not 0 < grid <= 2147483647:
        raise ValueError("layout_frame_units")
    result = {
        "schema_version": 1,
        "binding": route["binding"],
        "source_baseline_sha256": route["binding"]["source_baseline_sha256"],
        "technology": {
            "dbu_per_um": dbu,
            "manufacturing_grid_dbu": grid,
            "allowed_layer_purposes": [],
            "supported_orientations": ["R0"],
            "provenance": "native_observed",
        },
        "instances": [],
        "shapes": [],
        "pins": [],
        "provenance": "native_readback",
        "owned": route["owned"],
        "read_only": route["read_only"],
        "capabilities": dict(CAPABILITIES),
    }
    selectors, lpps, orientations = {}, set(), set(("R0",))

    def box(values):
        if len(values) != 4:
            raise ValueError("layout_frame_bbox")
        a, b, c, d = [rendering.integer(int(v)) for v in values]
        if a >= c or b >= d:
            raise ValueError("layout_frame_bbox_area")
        return {"lower_left": {"x": a, "y": b}, "upper_right": {"x": c, "y": d}}

    for row in rows[1:]:
        kind = row[0]
        if kind == "LPP" and len(row) == 3:
            lpps.add((rendering.token(row[1]), rendering.token(row[2])))
            continue
        if kind == "I" and len(row) == 14:
            for name in row[2:6]:
                rendering.token(name)
            if row[6] not in rendering.ORIENTATIONS or row[9] not in ("0", "1"):
                raise ValueError("layout_frame_instance_semantics")
            selector = {"kind": "instance", "name": row[2]}
            obj = {
                "master_id": "m-" + digest(row[3:6])[:24],
                "origin_dbu": {
                    "x": rendering.integer(int(row[7])),
                    "y": rendering.integer(int(row[8])),
                },
                "orientation": row[6],
                "bbox_dbu": box(row[10:]),
                "pcell_submaster": row[9] == "1",
            }
            orientations.add(row[6])
            group, prefix = "instances", "i-"
        elif kind == "S" and len(row) == 9 and row[2] == "rect":
            selector = {
                "kind": "rect",
                "layer": rendering.token(row[3]),
                "purpose": rendering.token(row[4]),
                "bbox_dbu": box(row[5:]),
            }
            obj = {
                "kind": "rect",
                "layer": row[3],
                "purpose": row[4],
                "bbox_dbu": selector["bbox_dbu"],
                "points_dbu": [],
                "width_dbu": None,
            }
            lpps.add((row[3], row[4]))
            group, prefix = "shapes", "s-"
        elif kind == "P" and len(row) == 10:
            for name in row[2:6]:
                rendering.token(name)
            selector = {"kind": "pin", "layer": row[2], "purpose": row[3], "bbox_dbu": box(row[6:])}
            obj = {
                "layer": row[2],
                "purpose": row[3],
                "bbox_dbu": selector["bbox_dbu"],
                "net_id": "n-" + digest(row[4])[:24],
                "terminal_id": "t-" + digest(row[5])[:24],
                "label": None,
                "association": "native_verified",
            }
            # Created logical net/terminal IDs are also legal native names.
            for field, index in (("net_id", 4), ("terminal_id", 5)):
                try:
                    obj[field] = rendering.token(row[index], rendering.LOGICAL)
                except ValueError:
                    pass
            lpps.add((row[2], row[3]))
            group, prefix = "pins", "p-"
        else:
            raise ValueError("layout_frame_unknown_or_malformed_object")
        object_id = (
            prefix + digest(selector)[:24]
            if row[1] == "-"
            else rendering.token(row[1], rendering.LOGICAL)
        )
        if object_id in selectors:
            raise ValueError("layout_frame_ambiguous_selector")
        obj["object_id"] = object_id
        selectors[object_id] = selector
        result[group].append(obj)
    if (
        len(result["instances"]) > 4096
        or len(result["shapes"]) > 4096
        or len(result["pins"]) > 1024
    ):
        raise ValueError("layout_frame_object_bound")
    result["technology"]["allowed_layer_purposes"] = [
        {"layer": a, "purpose": b} for a, b in sorted(lpps)
    ]
    result["technology"]["supported_orientations"] = sorted(orientations)
    result["capabilities"].update(move="supported", add_rect="supported", add_pin="supported")
    result["semantic_sha256"] = snapshot_digest(result)
    return result, selectors


def predict(before, commands, rendering=None):
    expected = copy.deepcopy(before)
    objects = {}
    instances = set(obj["object_id"] for obj in before["instances"])
    if not isinstance(commands, (tuple, list)) or not 1 <= len(commands) <= 128:
        raise ValueError("layout_edit_bounds")
    if any(not isinstance(command, dict) for command in commands):
        raise ValueError("layout_command_shape")
    if any(command.get("kind") == "orient" for command in commands):
        keys = [command["object_id"] for command in commands]
        if len(keys) != len(set(keys)):
            raise ValueError("layout_duplicate_object_edit")
    for group in ("instances", "shapes", "pins"):
        for obj in expected[group]:
            if obj["object_id"] in objects:
                raise ValueError("layout_duplicate_object_identity")
            objects[obj["object_id"]] = obj
    for command in commands:
        key = command["object_id"]
        if command["kind"] == "move":
            if key not in objects or object_digest(objects[key]) != command["before_sha256"]:
                raise ValueError("layout_move_selector_revision_mismatch")
            obj = objects[key]
            dx, dy = command["dx_dbu"], command["dy_dbu"]
            box = obj["bbox_dbu"]
            box["lower_left"] = shifted(box["lower_left"], dx, dy)
            box["upper_right"] = shifted(box["upper_right"], dx, dy)
            if "origin_dbu" in obj:
                obj["origin_dbu"] = shifted(obj["origin_dbu"], dx, dy)
            if obj.get("points_dbu"):
                obj["points_dbu"] = [shifted(p, dx, dy) for p in obj["points_dbu"]]
        elif command["kind"] == "orient":
            if rendering is None:
                raise ValueError("layout_orientation_renderer_required")
            rendering.orientation_command(command, before["technology"])
            if key not in instances:
                raise ValueError("layout_orientation_instance_required")
            obj = objects[key]
            if obj["pcell_submaster"]:
                raise ValueError("layout_orientation_pcell_submaster_unsupported")
            if before["capabilities"].get("rotate", "unsupported") == "unsupported":
                raise ValueError("layout_orientation_not_supported")
            if object_digest(obj) != command["before_sha256"]:
                raise ValueError("layout_orientation_selector_revision_mismatch")
            if command["origin_dbu"] != obj["origin_dbu"]:
                raise ValueError("layout_orientation_origin_changed")
            box = rendering.oriented_bbox(obj, command["orientation"], before["technology"])
            if box != command["bbox_dbu"]:
                raise ValueError("layout_orientation_bbox_mismatch")
            obj.update(orientation=command["orientation"], bbox_dbu=box)
        elif command["kind"] in ("add_rect", "add_pin"):
            if key in objects:
                raise ValueError("layout_new_object_already_exists")
            group, field = ("shapes", "shape") if command["kind"] == "add_rect" else ("pins", "pin")
            obj = copy.deepcopy(command[field])
            if obj["object_id"] != key:
                raise ValueError("layout_command_object_identity")
            expected[group].append(obj)
            objects[key] = obj
        else:
            raise ValueError("layout_operation_not_supported")
    return expected


class LayoutWorker(object):
    """Use existing jobs/immutable I/O and one shared VM lifetime lock.

    runtime.check authenticates installed helper, current operator authority,
    environment/activation, source/library fingerprints, storage bounds and
    registered route. runtime.inspect and runtime.write are fixed OA adapters.
    The runtime is an internal verified object, never a caller-selectable module.
    """

    def __init__(self, runtime, accounting, operations):
        self.runtime = runtime
        self.accounting = accounting
        self.operations = operations
        self.root = runtime.root

    def _write(self, path, document):
        if len(canonical(document)) > LIMIT:
            raise ValueError("layout_receipt_size")
        self.accounting.write_new(path, document)
        self.accounting.sync_directory(os.path.dirname(path))

    def _path(self, operation_id):
        self.operations.uuid(operation_id)
        return self.root + "/" + self.accounting.JOBS + "/" + operation_id

    def lookup(self, operation_id, request):
        path = self._path(operation_id)
        if not os.path.lexists(path):
            return None
        self.operations.private(path, True)
        # An analysis/legacy/partial job occupying this UUID cannot be adopted.
        intent = self.operations.read(path + "/layout-intent.json")
        if intent != {"schema_version": 1, "request_sha256": digest(request), "request": request}:
            raise ValueError("layout_operation_replay_conflict")
        receipt_path = path + "/layout-receipt.json"
        complete_path = path + "/layout-complete.json"
        if (
            os.path.lexists(path + "/layout-failure.json")
            or not os.path.lexists(receipt_path)
            or not os.path.lexists(complete_path)
        ):
            return {
                "state": "OUTCOME_UNKNOWN",
                "operation_id": operation_id,
                "executed": False,
                "replayed": True,
            }
        receipt = self.operations.read(receipt_path)
        complete = self.operations.read(complete_path)
        if complete != {
            "schema_version": 1,
            "operation_id": operation_id,
            "request_sha256": digest(request),
            "receipt_sha256": digest(receipt),
        }:
            raise ValueError("layout_completion_receipt_mismatch")
        if receipt["request_sha256"] != digest(request) or receipt["operation_id"] != operation_id:
            raise ValueError("layout_receipt_identity_mismatch")
        result = copy.deepcopy(receipt)
        result.update(executed=False, replayed=True)
        return result

    def _unsealed(self, binding):
        # Reuse the immutable jobs intents, rather than adding a latest-pointer
        # database. Failed/uncertain apply also seals its target against a new ID.
        parent = self.root + "/" + self.accounting.JOBS
        names = os.listdir(parent)
        if len(names) > 4096:
            raise ValueError("layout_existing_job_inventory_bound")
        for name in names:
            path = parent + "/" + name
            if not os.path.isdir(path):
                continue
            intent_path = path + "/layout-intent.json"
            if not os.path.lexists(intent_path):
                continue
            self.operations.private(path, True)
            intent = self.operations.read(intent_path)["request"]
            if intent["action"] == "apply" and (
                intent["payload"]["plan"]["request"]["binding"] == binding
            ):
                raise ValueError("layout_working_revision_already_sealed")

    def execute(self, action, request):
        if action not in ("fork", "apply"):
            raise ValueError("layout_fixed_write_action")
        operation_id = (
            request["operation_id"]
            if action == "fork"
            else request["plan"]["request"]["operation_id"]
        )
        identity = {"action": action, "payload": request}
        # Lookup first and again under the existing resource lock. Neither
        # lookup nor an uncertain outcome creates a new operation identity.
        replay = self.lookup(operation_id, identity)
        if replay is not None:
            self.runtime.read_check(identity)
            return replay
        with self.accounting.ReservationSession(self.root) as session:
            replay = self.lookup(operation_id, identity)
            if replay is not None:
                self.runtime.read_check(identity)
                return replay
            self.runtime.check(session, identity)
            before, selectors, route = self.runtime.inspect_for_write(action, request)
            baseline = (
                request["expected_baseline_sha256"]
                if action == "fork"
                else request["plan"]["baseline_sha256"]
            )
            if before["semantic_sha256"] != baseline:
                raise ValueError("layout_stale_baseline")
            if action == "apply":
                if not before["owned"] or before["read_only"]:
                    raise ValueError("layout_owned_working_revision_required")
                self._unsealed(before["binding"])
                plan = request["plan"]
                if request["expected_plan_sha256"] != plan["plan_sha256"]:
                    raise ValueError("layout_plan_hash_mismatch")
                sealed = copy.deepcopy(plan)
                sealed["plan_sha256"] = "0" * 64
                if digest(sealed) != plan["plan_sha256"]:
                    raise ValueError("layout_plan_hash_mismatch")
                expected = predict(
                    before, plan["normalized_edits"], getattr(self.runtime, "rendering", None)
                )
                requested = [e for e in plan["request"]["edits"] if e["kind"] == "orient"]
                normalized = [
                    dict((k, c[k]) for k in ("kind", "object_id", "orientation"))
                    for c in plan["normalized_edits"]
                    if c["kind"] == "orient"
                ]
                if requested != normalized:
                    raise ValueError("layout_orientation_request_mismatch")
                if requested and snapshot_digest(expected) != plan["expected_semantic_sha256"]:
                    raise ValueError("layout_orientation_prediction_mismatch")
            else:
                expected = copy.deepcopy(before)
                expected.update(binding=request["binding"], owned=True, read_only=False)
            protected = self.runtime.protected_snapshot()
            job = self._path(operation_id)
            # Occupied target/ID or active OA lock is checked before this durable
            # intent. Once published, failure is retained and never dispatched again.
            self.runtime.destination_check(action, route)
            self.operations.directory(job, self.accounting)
            self._write(
                job + "/layout-intent.json",
                {"schema_version": 1, "request_sha256": digest(identity), "request": identity},
            )
            self.operations.directory(job + "/work", self.accounting)
            self._write(job + "/work/layout-before.json", before)
            self.runtime.check(session, identity)
            try:
                observed = self.runtime.write(
                    session, action, request, before, selectors, route, job
                )
                self.runtime.check(session, identity)
                if self.runtime.protected_snapshot() != protected:
                    raise ValueError("layout_protected_source_changed")
                after = observed["snapshot"]
                if not observed["saved"] or not observed["reopened"]:
                    raise ValueError("layout_save_reopen_not_verified")
                if geometry(expected) != geometry(after):
                    raise ValueError("layout_readback_geometry_mismatch")
                for pin in after["pins"]:
                    if pin["association"] != "native_verified":
                        raise ValueError("layout_native_pin_association_required")
                result = {
                    "schema_version": 1,
                    "operation_id": operation_id,
                    "request_sha256": digest(identity),
                    "state": "SUCCEEDED",
                    "before": before,
                    "snapshot": after,
                    "saved": True,
                    "reopened": True,
                    "source_unchanged": True,
                    "executed": True,
                    "replayed": False,
                }
                self._write(job + "/layout-receipt.json", result)
                # A receipt candidate is not terminal success. All final guards
                # precede immutable completion publication. Any retained failure
                # takes precedence during lookup, including publication failures.
                session.check()
                self._write(
                    job + "/layout-complete.json",
                    {
                        "schema_version": 1,
                        "operation_id": operation_id,
                        "request_sha256": digest(identity),
                        "receipt_sha256": digest(result),
                    },
                )
                return result
            except Exception as error:
                # Preserve target and logs. Failure record cannot authorize retry.
                self._write(
                    job + "/layout-failure.json",
                    {
                        "schema_version": 1,
                        "operation_id": operation_id,
                        "request_sha256": digest(identity),
                        "state": "OUTCOME_UNKNOWN",
                        "reason": type(error).__name__,
                    },
                )
                raise


def private_bytes(path, maximum=LIMIT):
    """Bootstrap trust matches the existing native runtime's ordinary-user rules."""
    if os.name != "posix" or os.getuid() == 0 or os.geteuid() != os.getuid():
        raise ValueError("layout_normal_posix_user_required")
    current = os.path.dirname(path)
    while True:
        info = os.lstat(current)
        if (
            not stat.S_ISDIR(info.st_mode)
            or os.path.realpath(current) != current
            or info.st_uid not in (0, os.getuid())
            or info.st_mode & 18
        ):
            raise ValueError("layout_untrusted_ancestor")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    info = os.lstat(path)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.getuid()
        or info.st_mode & 63
        or os.path.realpath(path) != path
    ):
        raise ValueError("layout_private_file_required")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stream = os.fdopen(fd, "rb")
    try:
        opened = os.fstat(fd)
        raw = stream.read(maximum + 1)
        after = os.lstat(path)

        def identity(selected):
            return (
                selected.st_dev,
                selected.st_ino,
                selected.st_mode,
                selected.st_uid,
                selected.st_gid,
                selected.st_nlink,
                selected.st_size,
                selected.st_mtime,
                selected.st_ctime,
            )

        if (
            len(raw) > maximum
            or identity(info) != identity(opened)
            or identity(info) != identity(after)
        ):
            raise ValueError("layout_private_file_drift")
        return raw
    finally:
        stream.close()


def load_module(name, path, raw):
    module = types.ModuleType(name)
    module.__file__ = path
    module.__dict__["__package__"] = None
    eval(compile(raw, path, "exec"), module.__dict__)
    return module


def probe_libraries(registration):
    """Select technology observations without narrowing dependency protection."""
    registered = [lib["name"] for lib in registration["libraries"]]
    if "probe_libraries" not in registration:
        return registered
    selected = registration["probe_libraries"]
    if (
        type(selected) is not list
        or not 1 <= len(selected) <= 8
        # JSON names are unicode in Python 2.6 and str in Python 3.
        or any(not isinstance(name, type(b"".decode("ascii"))) for name in selected)
        or len(set(selected)) != len(selected)
        or not set(selected).issubset(set(registered))
    ):
        raise ValueError("layout_probe_library_scope")
    return selected


class FixedLayoutRuntime(object):
    """New layout operations retain the original runtime/activation/trust gates.

    Registration and confirmation are independently pinned private operator
    documents. This class never creates or extends either document.
    """

    def __init__(
        self, here, manifest, registration, native, native_assets, profile, modules, rendering
    ):
        keys = set(
            ("schema_version", "routes", "libraries", "owned_libraries", "protected_views", "seed")
        )
        if set(registration) not in (keys, keys | set(("probe_libraries",))):
            raise ValueError("layout_registration_shape")
        probe_libraries(registration)
        self.here, self.manifest, self.registration = here, manifest, registration
        self.native, self.native_assets, self.profile = native, native_assets, profile
        self.modules, self.rendering = modules, rendering
        self.root = profile["paths"]["managed_root"]
        self.accounting, self.operations = modules["reservations"], modules["operations"]
        self.copying = modules["copying"]
        self.original_registration = json.loads(native_assets["registration.json"].decode("ascii"))
        self.gate = modules["gate"].ConfirmedGate(
            profile,
            native_assets["profile.json"],
            self.original_registration,
            manifest["native_runtime_manifest_sha256"],
            hashlib.sha256(native_assets["probe.py"]).hexdigest(),
            (
                self.accounting,
                modules["confirmation"],
                modules["probe"],
                modules["storage"],
                self.copying,
            ),
            lambda: native.activation(profile, manifest["native_runtime_manifest_sha256"]),
            modules["modeltrust"],
        )
        self.eda = modules["worker"].EdaWorker(
            self.gate, self.operations, modules["rendering"], self.copying, modules["installer"]
        )
        if not 1 <= len(registration["routes"]) <= 32 or not registration["protected_views"]:
            raise ValueError("layout_registration_inventory_required")
        paths = [r["path"] for r in registration["routes"]]
        if len(set(paths)) != len(paths):
            raise ValueError("layout_revision_path_alias")
        for owned in registration["owned_libraries"]:
            for lib in registration["libraries"]:
                a, b = owned["path"], lib["path"]
                if a == b or a.startswith(b + "/") or b.startswith(a + "/"):
                    raise ValueError("layout_owned_protected_library_overlap")

    def read_check(self, request):
        manifest_raw = private_bytes(self.here + "/manifest.json")
        if hashlib.sha256(manifest_raw).hexdigest() != os.path.basename(self.here):
            raise ValueError("layout_manifest_changed")
        for name, pin in self.manifest["files"].items():
            raw = private_bytes(self.here + "/" + name)
            if pin != {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}:
                raise ValueError("layout_fixed_asset_changed")
        expected = self.manifest["native_runtime_manifest_sha256"]
        self.native.validate(expected)
        self.native.activation(self.profile, expected)
        self.native.history_guard(
            self.profile,
            expected,
            self.manifest["identity_manifest_sha256"],
            self.modules["confirmation"],
        )
        confirmation = json.loads(
            private_bytes(
                self.root
                + "/layout-confirmations/"
                + self.manifest["confirmation_sha256"]
                + ".json"
            )
        )
        if (
            hashlib.sha256(canonical(confirmation)).hexdigest()
            != self.manifest["confirmation_sha256"]
        ):
            raise ValueError("layout_confirmation_digest")
        if (
            confirmation["registration_sha256"]
            != self.manifest["files"]["registration.json"]["sha256"]
            or confirmation["identity_manifest_sha256"] != self.manifest["identity_manifest_sha256"]
            or confirmation["native_runtime_manifest_sha256"] != expected
            or confirmation["scope"] != "OWNED_LAYOUT_EDIT"
        ):
            raise ValueError("layout_confirmation_scope")
        self.modules["confirmation"].authority_reference(confirmation["operator_authority"])
        if os.path.lexists(
            self.root
            + "/layout-confirmations/"
            + self.manifest["confirmation_sha256"]
            + ".revoked.json"
        ):
            raise ValueError("layout_confirmation_revoked")
        return confirmation

    def check(self, session, request):
        if type(session) is not self.accounting.ReservationSession or session.root != self.root:
            raise ValueError("layout_existing_resource_session_required")
        session.check()
        self.session = session
        confirmation = self.read_check(request)
        if time.time() >= confirmation["valid_until_unix"]:
            raise ValueError("layout_confirmation_expired")
        if request["action"] not in confirmation["actions"]:
            raise ValueError("layout_confirmation_action_denied")
        observation = self.modules["probe"].observe(
            self.profile,
            hashlib.sha256(self.native_assets["profile.json"]).hexdigest(),
            hashlib.sha256(self.native_assets["probe.py"]).hexdigest(),
            uuid.uuid4().hex,
        )
        self.gate.library_binding({"libraries": self.registration["libraries"]})
        self.protected_snapshot()
        # Retain all previous accounting; layout never increments Spectre slots.
        binding = {
            "root_sha256": hashlib.sha256(self.root.encode("ascii")).hexdigest(),
            "resource_domain_sha256": self.manifest["resource_domain_sha256"],
            "identity_manifest_sha256": self.manifest["identity_manifest_sha256"],
        }
        counter, records = self.accounting.state(self.root, binding)
        anchor = self.accounting.identity_manifest(self.root, binding)
        policy = self.accounting.effective_policy(self.root, anchor)
        logical, allocated = self.gate.occupancy()
        limit = confirmation["max_job_bytes"]
        if type(limit) is not int or not 1048576 <= limit <= 33554432:
            raise ValueError("layout_job_size_bound")
        if max(logical, allocated) + limit > policy["result_ceiling_bytes"]:
            raise ValueError("layout_existing_result_capacity")
        if (
            counter["result_reserved_bytes"] + self.layout_retained_bytes() + limit
            > (policy["result_ceiling_bytes"])
        ):
            raise ValueError("layout_retained_reservation_capacity")
        if (
            observation["free_bytes"]
            < max(
                self.profile["limits"]["disk_floor_bytes"],
                (observation["total_bytes"] * self.profile["limits"]["disk_floor_percent"] + 99)
                // 100,
            )
            + limit
        ):
            raise ValueError("layout_disk_floor")
        self.limit = limit
        session.check()

    def layout_retained_bytes(self):
        """Charge retained layout output alongside all existing reservations."""
        storage = self.gate.storage
        io = storage.PosixIO()
        total, budget = 0, [0]

        def retained(path):
            parent = io.root(os.path.dirname(path))
            try:
                size, blocks, unused = storage.tree(io, parent, os.path.basename(path), budget)
                return max(size, blocks)
            finally:
                os.close(parent)

        jobs_path = self.root + "/" + self.accounting.JOBS
        names = os.listdir(jobs_path)
        if len(names) > 4096:
            raise ValueError("layout_existing_job_inventory_bound")
        for name in names:
            if os.path.lexists(jobs_path + "/" + name + "/layout-intent.json"):
                self.operations.uuid(name)
                total += retained(jobs_path + "/" + name)
        for library in self.registration["owned_libraries"]:
            path = library["path"]
            if not path.startswith(self.root + "/"):
                raise ValueError("layout_owned_library_required")
            if os.path.lexists(path):
                total += retained(path)
        return total

    def route(self, binding, registered_revision=False):
        matches = [
            r
            for r in self.registration["routes"]
            if (
                r["binding"]["workspace_id"] == binding["workspace_id"]
                and r["binding"]["design_id"] == binding["design_id"]
                and r["binding"]["revision_id"] == binding["revision_id"]
            )
        ]
        if len(matches) != 1 or (not registered_revision and matches[0]["binding"] != binding):
            raise ValueError("layout_unregistered_revision_binding")
        route = matches[0]
        self.rendering.binding(route["cellview"])
        self.copying.path(route["path"])
        libraries = [
            lib
            for lib in self.registration["libraries"] + self.registration["owned_libraries"]
            if lib["name"] == route["cellview"]["library"]
        ]
        if len(libraries) != 1 or route["path"] != (
            libraries[0]["path"] + "/" + route["cellview"]["cell"] + "/layout"
        ):
            raise ValueError("layout_registered_view_path_mismatch")
        if route["owned"]:
            owned = [lib for lib in self.registration["owned_libraries"] if lib == libraries[0]]
            if len(owned) != 1 or not libraries[0]["path"].startswith(self.root + "/"):
                raise ValueError("layout_owned_library_required")
            self.copying.owned_parent(libraries[0]["path"])
        elif not route["read_only"]:
            raise ValueError("layout_source_read_only_required")
        return route

    def protected_snapshot(self):
        result = []
        for entry in self.registration["protected_views"]:
            observed = self.copying.snapshot(entry["path"])
            if observed["tree_sha256"] != entry["tree_sha256"]:
                raise ValueError("layout_protected_view_registration_drift")
            result.append(observed)
        return result

    def destination_check(self, action, route):
        if not route["owned"] or route["read_only"]:
            raise ValueError("layout_registered_owned_destination_required")
        if action == "fork" and os.path.lexists(os.path.dirname(route["path"])):
            raise ValueError("layout_destination_cell_already_exists")
        if action == "apply":
            self.copying.snapshot(route["path"])  # Reject lock/recovery/link artifacts.

    def _job(self):
        job = self.root + "/" + self.accounting.JOBS + "/" + str(uuid.uuid4())
        self.operations.directory(job, self.accounting)
        self.operations.directory(job + "/work", self.accounting)
        return job

    def _program(self, session, script, route, job):
        work = job + "/work"
        script = self.rendering.execution_script(script)
        libraries = self.registration["libraries"] + self.registration["owned_libraries"]
        cds = "".join(
            "DEFINE %s %s\n" % (self.rendering.token(lib["name"]), self.copying.path(lib["path"]))
            for lib in libraries
        )
        for name, raw in (("layout.ocn", script), ("cds.lib", cds.encode("ascii"))):
            self.modules["installer"].exclusive(work + "/" + name, raw)
        journal = type("LayoutJob", (object,), {"job": job, "work": work})()
        self.eda.program(
            session,
            journal,
            [
                self.profile["tools"]["ocean"]["path"],
                "-nograph",
                "-nocdsinit",
                "-log",
                work + "/cadence.log",
                "-cdslib",
                work + "/cds.lib",
                "-restore",
                work + "/layout.ocn",
            ],
            "layout",
            45,
            self.limit,
        )
        raw = self.operations.read_bytes(work + "/layout.stdout")
        if len(raw) > LIMIT or any(
            line.startswith(b"MCP_LAYOUT_ERROR|") for line in raw.splitlines()
        ):
            raise ValueError("layout_native_error_record")
        if route is None:
            return raw
        snapshot, selectors = parse_frame(raw, route, self.rendering)
        return raw, snapshot, selectors

    def inspect(self, session, request):
        route = self.route(request["binding"], request.get("registered_revision", False))
        before = self.copying.snapshot(route["path"])
        raw, snapshot, selectors = self._program(
            session, self.rendering.inspect_script(route["cellview"]), route, self._job()
        )
        if self.copying.snapshot(route["path"]) != before:
            raise ValueError("layout_read_only_view_changed")
        return snapshot, selectors, route

    def inspect_for_write(self, action, request):
        # The caller already owns the session. It is retained across all reads
        # and the mutation; the narrow runtime never opens a second VM lock.
        target = self.route(
            request["binding"] if action == "fork" else request["plan"]["request"]["binding"]
        )
        selected = target
        if action == "fork":
            parents = [
                r
                for r in self.registration["routes"]
                if (
                    r["binding"]["workspace_id"] == target["binding"]["workspace_id"]
                    and r["binding"]["design_id"] == target["binding"]["design_id"]
                    and r["binding"]["revision_id"] == target["binding"]["parent_revision_id"]
                )
            ]
            if len(parents) != 1:
                raise ValueError("layout_registered_parent_required")
            selected = parents[0]
        before, selectors, _ = self.inspect(self.session, {"binding": selected["binding"]})
        if (
            action == "fork"
            and before["semantic_sha256"] != target["binding"]["parent_revision_sha256"]
        ):
            raise ValueError("layout_fork_parent_hash_mismatch")
        return before, selectors, target

    def write(self, session, action, request, before, selectors, route, job):
        parents = [
            r
            for r in self.registration["routes"]
            if (
                r["binding"]["workspace_id"] == route["binding"]["workspace_id"]
                and r["binding"]["design_id"] == route["binding"]["design_id"]
                and r["binding"]["revision_id"] == route["binding"]["parent_revision_id"]
            )
        ]
        if len(parents) != 1:
            raise ValueError("layout_registered_parent_required")
        parent_state = self.copying.snapshot(parents[0]["path"])
        if action == "fork":
            script = self.rendering.write_script(
                parents[0]["cellview"], route["cellview"], selectors, before["technology"]
            )
        else:
            script = self.rendering.apply_script(
                route["cellview"],
                selectors,
                before["technology"],
                request["plan"]["normalized_edits"],
            )
        raw, snapshot, unused = self._program(session, script, route, job)
        if self.copying.snapshot(parents[0]["path"]) != parent_state:
            raise ValueError("layout_protected_source_changed")
        marker = b"MCP_LAYOUT_SAVED_REOPENED|1"
        return {
            "snapshot": snapshot,
            "saved": marker in raw.splitlines(),
            "reopened": marker in raw.splitlines(),
        }

    def operator_probe(self, session):
        libraries = probe_libraries(self.registration)
        candidates = [r["cellview"] for r in self.registration["routes"]]
        raw = self._program(
            session, self.rendering.probe_script(libraries, candidates), None, self._job()
        )
        lines = protocol_lines(
            raw,
            b"MCP_LAYOUT_PROBE|1",
            b"END_LAYOUT_PROBE",
            "layout_probe_incomplete",
            (b"API|", b"TECHLIB|", b"LPP|", b"VIEW|"),
        )
        return {"observation": "\n".join(lines) + "\n"}

    def operator_seed(self, operation_id):
        """Pinned operator-only new-library seed, with the existing durable jobs."""
        seed = self.registration.get("seed")
        if seed is None:
            raise ValueError("layout_seed_not_registered")
        routes = [
            r
            for r in self.registration["routes"]
            if r["binding"]["revision_id"] == seed["revision_id"]
        ]
        if len(routes) != 1:
            raise ValueError("layout_seed_owned_route_required")
        route = routes[0]
        identity = {"action": "seed", "payload": {"operation_id": operation_id}}
        worker = LayoutWorker(self, self.accounting, self.operations)
        with self.accounting.ReservationSession(self.root) as session:
            replay = worker.lookup(operation_id, identity)
            if replay is not None:
                self.read_check(identity)
                return replay
            self.check(session, identity)
            if not route["owned"] or route["read_only"]:
                raise ValueError("layout_seed_owned_route_required")
            library = route["cellview"]["library"]
            libs = [lib for lib in self.registration["owned_libraries"] if lib["name"] == library]
            library_path = libs[0]["path"]
            if not library_path.startswith(self.root + "/"):
                raise ValueError("layout_owned_library_required")
            self.copying.path(library_path)
            self.copying.owned_parent(os.path.dirname(library_path))
            if os.path.lexists(library_path):
                raise ValueError("layout_seed_library_exists")
            script = self.rendering.seed_script(
                library,
                library_path,
                seed["technology_library"],
                seed["master_cell"],
                route["cellview"]["cell"],
                seed["technology"],
                seed["layer_purpose"],
            )
            protected = self.protected_snapshot()
            job = worker._path(operation_id)
            self.operations.directory(job, self.accounting)
            worker._write(
                job + "/layout-intent.json",
                {"schema_version": 1, "request_sha256": digest(identity), "request": identity},
            )
            self.operations.directory(job + "/work", self.accounting)
            try:
                raw, snapshot, unused = self._program(session, script, route, job)
                self.check(session, identity)
                if self.protected_snapshot() != protected:
                    raise ValueError("layout_protected_source_changed")
                if b"MCP_LAYOUT_SAVED_REOPENED|1" not in raw.splitlines() or (
                    len(snapshot["instances"]) != 1
                    or len(snapshot["shapes"]) != 1
                    or snapshot["pins"]
                    or snapshot["technology"]["dbu_per_um"] != seed["technology"]["dbu_per_um"]
                    or snapshot["technology"]["manufacturing_grid_dbu"]
                    != seed["technology"]["manufacturing_grid_dbu"]
                ):
                    raise ValueError("layout_seed_readback_mismatch")
                result = {
                    "schema_version": 1,
                    "operation_id": operation_id,
                    "request_sha256": digest(identity),
                    "state": "SUCCEEDED",
                    "snapshot": snapshot,
                    "saved": True,
                    "reopened": True,
                    "source_unchanged": True,
                    "executed": True,
                    "replayed": False,
                }
                worker._write(job + "/layout-receipt.json", result)
                session.check()
                worker._write(
                    job + "/layout-complete.json",
                    {
                        "schema_version": 1,
                        "operation_id": operation_id,
                        "request_sha256": digest(identity),
                        "receipt_sha256": digest(result),
                    },
                )
                return result
            except Exception as error:
                worker._write(
                    job + "/layout-failure.json",
                    {
                        "schema_version": 1,
                        "operation_id": operation_id,
                        "request_sha256": digest(identity),
                        "state": "OUTCOME_UNKNOWN",
                        "reason": type(error).__name__,
                    },
                )
                raise


def load_runtime(expected):
    if not valid_digest(expected):
        raise ValueError("layout_manifest_digest")
    here = os.path.dirname(os.path.abspath(__file__))
    if (
        os.path.basename(here) != expected
        or os.path.basename(os.path.dirname(here)) != "layout-runtime"
    ):
        raise ValueError("layout_runtime_namespace")
    raw = private_bytes(here + "/manifest.json")
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("layout_manifest_digest")
    manifest = json.loads(raw.decode("ascii"))
    if (
        set(manifest)
        != set(
            (
                "schema_version",
                "resource_domain_sha256",
                "environment_sha256",
                "native_runtime_manifest_sha256",
                "native_provider_sha256",
                "identity_manifest_sha256",
                "confirmation_sha256",
                "files",
            )
        )
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
    ):
        raise ValueError("layout_manifest_shape")
    if any(
        not valid_digest(manifest[key])
        for key in manifest
        if key not in ("schema_version", "files")
    ):
        raise ValueError("layout_manifest_shape")
    if set(manifest["files"]) != set(("worker.py", "rendering.py", "registration.json")):
        raise ValueError("layout_manifest_shape")
    if set(os.listdir(here)) != set(
        ("worker.py", "rendering.py", "registration.json", "manifest.json")
    ):
        raise ValueError("layout_runtime_inventory")
    assets = {}
    for name, pin in manifest["files"].items():
        data = private_bytes(here + "/" + name)
        if pin != {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}:
            raise ValueError("layout_runtime_asset_drift")
        assets[name] = data
    root = os.path.dirname(os.path.dirname(here))
    native_path = root + "/runtime/" + manifest["native_runtime_manifest_sha256"] + "/provider.py"
    native_raw = private_bytes(native_path)
    if hashlib.sha256(native_raw).hexdigest() != manifest["native_provider_sha256"]:
        raise ValueError("layout_native_entry_binding")
    native = load_module("layout_bound_native", native_path, native_raw)
    native_here, native_manifest, native_assets, profile = native.validate(
        manifest["native_runtime_manifest_sha256"]
    )
    if root != profile["paths"]["managed_root"] or (
        hashlib.sha256(native_assets["profile.json"]).hexdigest() != manifest["environment_sha256"]
    ):
        raise ValueError("layout_environment_binding")
    registration = json.loads(assets["registration.json"].decode("ascii"))
    original = json.loads(native_assets["registration.json"].decode("ascii"))
    if original["identity_manifest_sha256"] != manifest["identity_manifest_sha256"]:
        raise ValueError("layout_existing_accounting_anchor")
    modules = native.verified_modules(native_here, native_assets)
    rendering = load_module(
        "layout_fixed_rendering", here + "/rendering.py", assets["rendering.py"]
    )
    return FixedLayoutRuntime(
        here, manifest, registration, native, native_assets, profile, modules, rendering
    )


def valid_digest(value):
    return (
        isinstance(value, (str, type(json.loads('""'))))
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def main():
    raw = sys.stdin.read(LIMIT + 1)
    if not isinstance(raw, bytes):
        raw = raw.encode("ascii")
    request = json.loads(raw.decode("ascii"))
    if (
        len(raw) > LIMIT
        or canonical(request) != raw
        or set(request)
        != set(
            (
                "schema_version",
                "action",
                "layout_manifest_sha256",
                "identity_manifest_sha256",
                "payload",
            )
        )
    ):
        raise ValueError("layout_closed_request")
    if type(request["schema_version"]) is not int or request["schema_version"] != 1:
        raise ValueError("layout_request_version")
    action = request["action"]
    if action not in ("inspect", "lookup", "fork", "apply", "probe", "seed"):
        raise ValueError("layout_fixed_action")
    runtime = load_runtime(request["layout_manifest_sha256"])
    if request["identity_manifest_sha256"] != runtime.manifest["identity_manifest_sha256"]:
        raise ValueError("layout_request_anchor")
    worker = LayoutWorker(runtime, runtime.accounting, runtime.operations)
    if action == "lookup":
        payload = request["payload"]
        runtime.read_check(payload)
        operation_id = (
            payload["payload"]["operation_id"]
            if payload["action"] == "fork"
            else payload["payload"]["plan"]["request"]["operation_id"]
        )
        result = worker.lookup(operation_id, payload)
    elif action == "seed":
        if set(request["payload"]) != set(("operation_id",)):
            raise ValueError("layout_closed_request")
        result = runtime.operator_seed(request["payload"]["operation_id"])
    elif action in ("inspect", "probe"):
        with runtime.accounting.ReservationSession(runtime.root) as session:
            runtime.check(session, {"action": action, "payload": request["payload"]})
            protected = runtime.protected_snapshot()
            if action == "probe":
                if request["payload"] != {}:
                    raise ValueError("layout_closed_request")
                result = runtime.operator_probe(session)
            else:
                result, selectors, route = runtime.inspect(session, request["payload"])
            runtime.check(session, {"action": action, "payload": request["payload"]})
            if runtime.protected_snapshot() != protected:
                raise ValueError("layout_read_only_protected_drift")
    else:
        result = worker.execute(action, request["payload"])
    response = canonical(
        {
            "schema_version": 1,
            "layout_manifest_sha256": request["layout_manifest_sha256"],
            "action": action,
            "payload": result,
        }
    )
    if len(response) > LIMIT:
        raise ValueError("layout_response_size")
    sys.stdout.write(response.decode("ascii") + "\n")


def safe_reason(error):
    message = str(error)
    if message in ("reservation_lock_drift", "reservation_session_closed"):
        return "layout_resource_lock_busy"
    if isinstance(error, OSError) and error.errno in (11, 13, 35):
        return "layout_resource_lock_busy"
    if message in (
        "layout_stale_baseline",
        "layout_unregistered_revision_binding",
        "layout_working_revision_already_sealed",
        "layout_operation_replay_conflict",
        "layout_destination_cell_already_exists",
        "layout_fork_parent_hash_mismatch",
    ):
        return "layout_revision_conflict"
    if message in (
        "layout_protected_source_changed",
        "layout_protected_view_registration_drift",
        "layout_read_only_view_changed",
        "layout_read_only_protected_drift",
    ):
        return "layout_source_protection_failed"
    if message in (
        "layout_existing_result_capacity",
        "layout_retained_reservation_capacity",
        "layout_disk_floor",
    ):
        return "layout_result_capacity"
    if message in ("native_worker_program_failed", "layout_native_error_record"):
        return "layout_program_failed"
    if message in (
        "layout_manifest_digest",
        "layout_runtime_asset_drift",
        "layout_fixed_asset_changed",
        "layout_native_entry_binding",
        "executable_permissions",
        "executable_drift",
        "layout_confirmation_scope",
        "layout_confirmation_digest",
        "layout_confirmation_expired",
        "layout_confirmation_revoked",
        "native_runtime_activation_mismatch",
    ):
        return "layout_runtime_trust_failed"
    if isinstance(error, OSError) and error.errno == 2:
        return "layout_setup_required"
    return "layout_outcome_unknown"


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # No raw exception, path, arbitrary log or traceback crosses the wire.
        # A malformed/unbound request has no trusted response identity.
        sys.stderr.write("LAYOUT_FIXED_WORKER_REJECTED:%s\n" % safe_reason(error))
        sys.exit(1)
