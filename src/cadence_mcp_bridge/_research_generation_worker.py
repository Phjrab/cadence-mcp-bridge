"""Fixed owned research generation phase. Guest Python 2.6, no public CLI."""

# mypy: ignore-errors
# ruff: noqa: E402, I001, SIM105, UP004, UP024, UP031

import sys

if __name__ == "__main__":
    sys.path[:] = [path for path in sys.path if path and path.startswith("/")]

import base64
import hashlib
import json
import os
import re
import stat
import time
import types

PHASES = ("save", "reopen", "netlist")
LIMIT = 262144
WIRE_LIMIT = 1048576
MARKER_LIMIT = 65536
try:
    TEXT = basestring
except NameError:
    TEXT = str


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def closed(raw, keys, limit=LIMIT):
    require(0 < len(raw) <= limit, "research_generation_document_bound")
    data = json.loads(raw.decode("ascii"))
    require(
        isinstance(data, dict) and set(data) == set(keys) and canonical(data) == raw,
        "research_generation_document_shape",
    )
    return data


def match(pattern, value):
    require(
        isinstance(value, TEXT) and re.match(pattern + r"\Z", value) is not None,
        "research_generation_token",
    )
    return value


def digest(value):
    return match(r"[0-9a-f]{64}", value)


def name(value):
    return match(r"[A-Za-z][A-Za-z0-9_]{0,63}", value)


def artifact(value, limit):
    require(
        isinstance(value, TEXT) and len(value) <= 4 * ((limit + 2) // 3),
        "research_generation_artifact_bound",
    )
    encoded = value.encode("ascii")
    raw = base64.b64decode(encoded)
    require(
        0 < len(raw) <= limit and base64.b64encode(raw) == encoded,
        "research_generation_artifact_encoding",
    )
    return raw


def read_regular(path, limit):
    before = os.lstat(path)
    require(
        os.path.realpath(path) == path
        and stat.S_ISREG(before.st_mode)
        and before.st_uid == os.getuid()
        and before.st_nlink == 1
        and not before.st_mode & 63
        and before.st_size <= limit,
        "research_generation_private_artifact",
    )

    def identity(value):
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime, value.st_ctime

    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        require(
            identity(os.fstat(stream.fileno())) == identity(before),
            "research_generation_artifact_open_drift",
        )
        raw = stream.read(limit + 1)
    require(
        len(raw) == before.st_size and identity(os.lstat(path)) == identity(before),
        "research_generation_artifact_read_drift",
    )
    return raw


def parse_request(argv, raw):
    require(len(argv) == 3 and argv[1] in PHASES, "research_generation_phase")
    scope_sha, phase, prior = argv
    require(
        re.match(r"[0-9a-f]{64}\Z", scope_sha) is not None
        and (prior == "" if phase == "save" else re.match(r"[0-9a-f]{64}\Z", prior) is not None),
        "research_generation_phase_pins",
    )
    data = closed(
        raw,
        ("managed_root", "binding", "scope_base64", "authority_base64", "program_base64"),
        WIRE_LIMIT,
    )
    scope_raw = artifact(data["scope_base64"], LIMIT)
    require(sha(scope_raw) == scope_sha, "research_generation_scope_digest")
    scope = closed(
        scope_raw,
        (
            "schema_version",
            "binding",
            "layout_manifest_sha256",
            "layout_worker_sha256",
            "identity_manifest_sha256",
            "operator_authority",
            "valid_until_unix",
            "source_route",
            "technology",
            "dut_cell",
            "bench_cell",
            "dut_subcircuits",
            "markers",
            "netlist_statements_sha256",
            "protected_sha256",
            "additional_protected",
            "counter",
            "ledger_records_sha256",
            "jobs_sha256",
            "prior_supplemental_bytes",
            "external_bytes",
            "job_bytes",
        ),
    )
    binding = data["binding"]
    require(
        isinstance(binding, dict)
        and set(binding)
        == set(
            (
                "operation_id",
                "context_id",
                "resource_domain_sha256",
                "native_manifest_sha256",
                "scope_sha256",
                "plan_sha256",
                "bench_plan_sha256",
                "conditions_sha256",
                "output_library",
                "owned_library_path",
                "save_program_sha256",
                "reopen_program_sha256",
                "netlist_program_sha256",
            )
        ),
        "research_generation_binding_shape",
    )
    for key, value in binding.items():
        if key.endswith("_sha256"):
            digest(value)
    scoped_binding = dict(binding)
    del scoped_binding["scope_sha256"]
    require(
        binding["scope_sha256"] == scope_sha and scope["binding"] == scoped_binding,
        "research_generation_scope_binding",
    )
    for key in (
        "layout_manifest_sha256",
        "layout_worker_sha256",
        "identity_manifest_sha256",
        "netlist_statements_sha256",
        "protected_sha256",
        "ledger_records_sha256",
        "jobs_sha256",
    ):
        digest(scope[key])
    markers = scope["markers"]
    require(
        isinstance(markers, dict)
        and set(markers) == set(PHASES)
        and all(
            isinstance(rows, list)
            and 1 <= len(rows) <= 128
            and all(
                isinstance(row, TEXT)
                and 0 < len(row) <= 512
                and all(32 <= ord(ch) <= 126 for ch in row)
                and row.startswith(("RESEARCH_BENCH_", "MOS_BLOCK_", "MCP_GENERIC_ADE_NETLIST|"))
                for row in rows
            )
            for rows in markers.values()
        ),
        "research_generation_marker_scope",
    )
    op = match(
        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        binding["operation_id"],
    )
    binding_sha = sha(canonical(binding))
    ack = closed(
        artifact(data["authority_base64"], 4096),
        (
            "operation_id",
            "binding_sha256",
            "scope_sha256",
            "approved_phases",
            "valid_until_unix",
        ),
        4096,
    )
    require(
        type(scope["schema_version"]) is int
        and scope["schema_version"] == 1
        and type(scope["valid_until_unix"]) is int
        and ack
        == dict(
            operation_id=op,
            binding_sha256=binding_sha,
            scope_sha256=scope_sha,
            approved_phases=list(PHASES),
            valid_until_unix=scope["valid_until_unix"],
        )
        and 0 < scope["valid_until_unix"] - time.time() <= 7200,
        "research_generation_exact_authority",
    )
    program = artifact(data["program_base64"], LIMIT)
    require(sha(program) == binding[phase + "_program_sha256"], "research_generation_program_pin")
    program.decode("ascii")
    return data["managed_root"], scope, binding, binding_sha, phase, prior or None, program


def load_runtime(root, scope, binding):
    require(
        isinstance(root, TEXT)
        and root.startswith("/")
        and os.path.realpath(root) == root
        and os.path.basename(root) == ".cadence_mcp",
        "research_generation_managed_root",
    )
    layout = digest(scope["layout_manifest_sha256"])
    path = root + "/layout-runtime/" + layout + "/worker.py"
    raw = read_regular(path, LIMIT)
    require(sha(raw) == digest(scope["layout_worker_sha256"]), "research_generation_worker_pin")
    module = types.ModuleType("research_bound_layout")
    module.__file__ = path
    eval(compile(raw, path, "exec"), module.__dict__)
    runtime = module.load_runtime(layout)
    require(
        runtime.root == root
        and runtime.manifest["native_runtime_manifest_sha256"] == binding["native_manifest_sha256"]
        and runtime.manifest["resource_domain_sha256"] == binding["resource_domain_sha256"]
        and runtime.manifest["identity_manifest_sha256"] == scope["identity_manifest_sha256"],
        "research_generation_runtime_binding",
    )
    return runtime


def dut_projection(statements, expected):
    """Project the exact declared, nonnested DUT subcircuits from the verified full input."""
    require(
        isinstance(expected, list)
        and 1 <= len(expected) <= 31
        and len(set(expected)) == len(expected),
        "research_generation_dut_inventory",
    )
    expected = set(name(item) for item in expected)
    depth, selected, seen, lines = 0, None, set(), ["simulator lang=spectre"]
    for line in statements:
        words = line.split()
        if not words:
            continue
        if words[0] == "subckt" or words[:2] == ["inline", "subckt"]:
            label = words[1 if words[0] == "subckt" else 2]
            if label in expected:
                require(
                    depth == 0 and label not in seen and words[0] == "subckt",
                    "research_generation_dut_subcircuit",
                )
                selected = label
                seen.add(label)
            elif selected:
                raise ValueError("research_generation_nested_dut")
            depth += 1
        if selected:
            lines.append(line)
        if words[0] == "ends":
            require(depth > 0, "research_generation_unmatched_ends")
            depth -= 1
            if depth == 0:
                selected = None
    require(depth == 0 and seen == expected, "research_generation_incomplete_dut")
    return ("\n".join(lines) + "\n").encode("ascii")


class GenerationPhase(object):
    def __init__(self, runtime, scope, binding, binding_sha):
        self.r, self.scope, self.binding, self.binding_sha = runtime, scope, binding, binding_sha
        self.copy, self.ops, self.eda = runtime.copying, runtime.operations, runtime.eda
        self.root, self.op = runtime.root, binding["operation_id"]
        self.jobs = self.root + "/" + runtime.accounting.JOBS
        self.job = self.jobs + "/" + self.op
        self.store = self.job + "/research-generation"
        self.library = self.copy.path(binding["owned_library_path"])
        self.parent = os.path.dirname(self.library)
        name(os.path.basename(self.parent))
        self.workspace = runtime.profile["paths"]["workspace_root"]
        self.dut, self.bench = name(scope["dut_cell"]), name(scope["bench_cell"])
        self.library_name = name(binding["output_library"])
        require(
            self.dut != self.bench
            and self.dut in scope["dut_subcircuits"]
            and os.path.basename(self.library) == self.library_name
            and os.path.dirname(self.parent) == self.workspace
            and self.parent != self.root,
            "research_generation_owned_target",
        )
        route = scope["source_route"]
        require(
            isinstance(route, dict) and set(route) == set(("design_id", "analysis_id")),
            "research_generation_source_route",
        )
        (self.route,) = (
            item
            for item in runtime.original_registration["routes"]
            if (item["design_id"], item["analysis_id"])
            == (route["design_id"], route["analysis_id"])
        )
        protected = [item["path"] for item in runtime.registration["protected_views"]]
        protected += list(runtime.profile["paths"]["protected_roots"])
        additional = scope["additional_protected"]
        require(
            isinstance(additional, list) and len(additional) <= 32,
            "research_generation_additional_protection_inventory",
        )
        self.additional = {}
        for item in additional:
            require(
                isinstance(item, dict) and set(item) == set(("path", "tree_sha256")),
                "research_generation_additional_protection_shape",
            )
            path = self.copy.path(item["path"])
            require(
                path not in self.additional and os.path.isdir(path),
                "research_generation_additional_protection_path",
            )
            self.additional[path] = digest(item["tree_sha256"])
        protected.extend(self.additional)
        for item in runtime.original_registration["routes"]:
            protected.extend([item["source_cell"], item["source_state"]])
            protected.extend(lib["path"] for lib in item["libraries"])
        require(
            not any(
                self.parent == path
                or self.parent.startswith(path + "/")
                or path.startswith(self.parent + "/")
                for path in protected
            ),
            "research_generation_protected_target_overlap",
        )
        for key in ("external_bytes", "job_bytes", "prior_supplemental_bytes"):
            require(
                type(scope[key]) is int and 0 <= scope[key] <= 33554432,
                "research_generation_storage_bound",
            )
        require(
            scope["external_bytes"] > 0
            and scope["job_bytes"] > 1048576
            and scope["external_bytes"] + scope["job_bytes"] <= 8388608,
            "research_generation_scope_storage_bound",
        )
        self.state = self.parent + "/" + self.bench + "_ADE"
        self.accounting_binding = dict(
            root_sha256=sha(self.root.encode("ascii")),
            resource_domain_sha256=binding["resource_domain_sha256"],
            identity_manifest_sha256=digest(scope["identity_manifest_sha256"]),
        )
        self.claim = dict(
            binding_sha256=binding_sha,
            operation_id=self.op,
            scope_sha256=binding["scope_sha256"],
            retry=False,
        )

    def write(self, path, payload):
        self.eda.write(path, payload)
        require(read_regular(path, LIMIT) == payload, "research_generation_write_readback")
        return sha(payload)

    def record(self, path, doc):
        return self.write(path, canonical(doc))

    def original_jobs(self):
        jobs = os.listdir(self.jobs)
        require(len(jobs) <= 4096, "research_generation_job_inventory_cap")
        return sorted(name_ for name_ in jobs if name_ != self.op)

    def size(self, path):
        return max(self.eda.size(path)[:2]) if os.path.lexists(path) else 0

    def guard(self, session):
        r, s = self.r, self.scope
        session.check()
        require(time.time() < s["valid_until_unix"], "research_generation_scope_expired")
        r.read_check({})
        r.modules["confirmation"].authority_reference(s["operator_authority"])
        require(not r.gate.storage.active_eda(self.root, True), "research_generation_eda_busy")
        r.gate.library_binding(self.route)
        r.gate.model_binding(self.route)
        self.maps()
        require(
            all(
                self.copy.dependency_snapshot(path)["tree_sha256"] == expected
                for path, expected in self.additional.items()
            ),
            "research_generation_additional_protection_drift",
        )
        source = self.copy.snapshot(self.route["source_cell"])["tree_sha256"]
        state = self.copy.snapshot(self.route["source_state"])["tree_sha256"]
        ade = self.route["ade"]
        protected = sha(canonical(r.protected_snapshot()))
        jobs = self.original_jobs()
        counter, records = session.observe(self.accounting_binding)
        require(
            source == ade["source_tree_sha256"]
            and state == ade["ade_state_tree_sha256"]
            and protected == s["protected_sha256"]
            and sha(canonical(jobs)) == s["jobs_sha256"]
            and counter == s["counter"]
            and sha(canonical(records)) == s["ledger_records_sha256"],
            "research_generation_originals_or_ledger_drift",
        )
        external, current = self.size(self.parent), self.size(self.job)
        require(
            external <= s["external_bytes"] and current <= s["job_bytes"],
            "research_generation_charge_exhausted",
        )
        limits = r.profile["limits"]
        anchor = r.accounting.identity_manifest(self.root, self.accounting_binding)
        ceiling = r.accounting.effective_policy(self.root, anchor)["result_ceiling_bytes"]
        pending = sum(
            row["binding"]["reserve_bytes"] for row, receipt in records if receipt is None
        )
        cap = s["external_bytes"] + s["job_bytes"]
        logical, allocated = r.gate.occupancy()
        fs = os.statvfs(self.root)
        block = fs.f_frsize or fs.f_bsize
        floor = max(
            limits["disk_floor_bytes"],
            (fs.f_blocks * block * limits["disk_floor_percent"] + 99) // 100,
        )
        require(
            ceiling == limits["result_reserved_bytes"]
            and counter["result_reserved_bytes"] + s["prior_supplemental_bytes"] + cap <= ceiling
            and max(logical, allocated) + s["prior_supplemental_bytes"] + cap - current <= ceiling
            and fs.f_bavail * block >= floor + pending + cap - current - external,
            "research_generation_capacity",
        )
        workspace = self.copy.directory(self.workspace)
        require(
            workspace.st_uid == os.getuid() and not workspace.st_mode & 18,
            "research_generation_workspace_trust",
        )
        session.check()
        return dict(
            source=source,
            state=state,
            protected=protected,
            jobs_sha256=s["jobs_sha256"],
            counter=counter,
            ledger_records_sha256=s["ledger_records_sha256"],
        )

    def maps(self):
        result = [
            (item["name"], item["path"])
            for item in self.route["libraries"]
            if item["name"] in ("basic", "analogLib", "gpdk090")
        ]
        require(
            set(label for label, _ in result) == set(("basic", "analogLib", "gpdk090"))
            and len(result) == 3,
            "research_generation_library_map",
        )
        tech = self.scope["technology"]
        require(
            isinstance(tech, dict)
            and set(tech) == set(("path", "tree_sha256"))
            and os.path.basename(tech["path"]) == "cdsDefTechLib"
            and re.match(r"/[A-Za-z0-9_./-]+\Z", tech["path"]) is not None
            and self.copy.dependency_snapshot(tech["path"])["tree_sha256"] == tech["tree_sha256"],
            "research_generation_technology_binding",
        )
        return result + [("cdsDefTechLib", tech["path"])]

    def trees(self):
        self.copy.owned_parent(self.parent)
        require(
            sorted(os.listdir(self.parent)) == sorted([self.library_name, self.bench + "_ADE"]),
            "research_generation_owned_tree_shape",
        )
        return dict(
            library=self.copy.dependency_snapshot(self.library)["tree_sha256"],
            strict_library=self.copy.snapshot(self.library)["tree_sha256"],
            dut=self.copy.snapshot(self.library + "/" + self.dut)["tree_sha256"],
            bench=self.copy.snapshot(self.library + "/" + self.bench)["tree_sha256"],
            state=self.copy.snapshot(self.state)["tree_sha256"],
        )

    def stage_intent(self, phase, prior):
        return dict(
            claim_sha256=sha(canonical(self.claim)),
            phase=phase,
            program_sha256=self.binding[phase + "_program_sha256"],
            previous_receipt_sha256=prior,
            retry=False,
        )

    def previous(self, phase, prior):
        folder = self.store + "/" + phase
        require(
            not os.path.lexists(folder + "/failure.json"), "research_generation_predecessor_failed"
        )
        intent = read_regular(folder + "/intent.json", 4096)
        raw = read_regular(folder + "/receipt.json", 8192)
        done = read_regular(folder + "/complete.json", 1024)
        record = json.loads(raw.decode("ascii"))
        receipt = record["receipt"]
        require(
            intent == canonical(self.stage_intent(phase, prior))
            and done == canonical(dict(intent_sha256=sha(intent), receipt_sha256=sha(raw)))
            and canonical(record) == raw
            and receipt["phase"] == phase
            and receipt["operation_id"] == self.op
            and receipt["plan_sha256"] == self.binding["plan_sha256"]
            and record["scope_sha256"] == self.binding["scope_sha256"]
            and record["previous_receipt_sha256"] == prior
            and receipt["script_sha256"] == self.binding[phase + "_program_sha256"],
            "research_generation_predecessor_drift",
        )
        require(
            sha(read_regular(folder + "/work/ocean.stdout", MARKER_LIMIT))
            == receipt["artifact_sha256"],
            "research_generation_predecessor_artifact",
        )
        return record

    def copy_state(self, source, target, pin, from_binding, to_binding, project):
        self.copy.copy_owned(source, target, pin)
        leaf = target + "/ADE_state.info"
        raw = read_regular(leaf, MARKER_LIMIT)
        updated = self.copy.remap_ade_info(raw, from_binding, to_binding, project)
        info = self.ops.private(leaf)
        fd = os.open(leaf, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "wb") as stream:
            actual = os.fstat(stream.fileno())
            require(
                (actual.st_dev, actual.st_ino, actual.st_nlink) == (info.st_dev, info.st_ino, 1),
                "research_generation_copied_ade_identity",
            )
            stream.truncate(0)
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        self.copy.sync(target)
        require(
            read_regular(leaf, MARKER_LIMIT) == updated
            and self.copy.snapshot(source)["tree_sha256"] == pin,
            "research_generation_copied_ade_drift",
        )
        return self.copy.snapshot(target)["tree_sha256"]

    def prepare(self, phase, previous, work, maps):
        r = self.r
        if phase == "save":
            os.mkdir(self.parent, 448)
            self.copy.sync(self.workspace)
            self.copy.owned_parent(self.parent)
            source = self.route["source_state"]
            old_cell = self.route["source_cell"]
            old = (
                os.path.basename(os.path.dirname(old_cell)),
                os.path.basename(old_cell),
                "schematic",
            )
            self.eda.copy_capacity(
                {"state": self.copy.snapshot(source)}, self.parent, self.scope["external_bytes"]
            )
            self.copy_state(
                source,
                self.state,
                self.route["ade"]["ade_state_tree_sha256"],
                old,
                (self.library_name, self.bench, "schematic"),
                self.parent + "/project",
            )
        else:
            maps.append((self.library_name, self.library))
        if phase != "netlist":
            return None
        cell = "Grel_" + self.op.replace("-", "_")
        for leaf in (
            "project",
            "library",
            "state-root",
            "state-root/MCP_GREL_Work",
            "state-root/MCP_GREL_Work/" + cell,
            "state-root/MCP_GREL_Work/" + cell + "/spectre",
        ):
            self.ops.directory(work + "/" + leaf, r.accounting)
        maps.append(("MCP_GREL_Work", work + "/library"))
        target = work + "/state-root/MCP_GREL_Work/" + cell + "/spectre/state1"
        bench = self.library + "/" + self.bench
        self.eda.copy_capacity(
            {"state": self.copy.snapshot(self.state), "bench": self.copy.snapshot(bench)},
            self.job,
            self.scope["job_bytes"] - LIMIT,
        )
        self.copy.copy_owned(bench, work + "/library/" + cell, previous["trees"]["bench"])
        bench_target = work + "/library/" + cell
        bench_copy = self.copy.snapshot(bench_target)
        require(
            bench_copy["content_sha256"] == self.copy.snapshot(bench)["content_sha256"],
            "research_generation_bench_copy_drift",
        )
        pin = self.copy_state(
            self.state,
            target,
            previous["trees"]["state"],
            (self.library_name, self.bench, "schematic"),
            ("MCP_GREL_Work", cell, "schematic"),
            work + "/project",
        )
        return target, pin, bench_target, bench_copy

    def run(self, session, phase, prior, program):
        before = self.guard(session)
        maps = self.maps()
        stage = self.store + "/" + phase
        require(not os.path.lexists(stage), "research_generation_phase_already_started")
        previous, predecessor = None, None
        if phase == "save":
            require(
                not os.path.lexists(self.job) and not os.path.lexists(self.parent),
                "research_generation_target_already_claimed",
            )
            self.ops.directory(self.job, self.r.accounting)
            self.ops.directory(self.store, self.r.accounting)
            self.record(self.store + "/intent.json", self.claim)
        else:
            require(
                read_regular(self.store + "/intent.json", 4096) == canonical(self.claim),
                "research_generation_claim_mismatch",
            )
            for parent_phase in PHASES[: PHASES.index(phase)]:
                previous = self.previous(parent_phase, predecessor)
                require(
                    previous["protected"] == before, "research_generation_predecessor_protection"
                )
                predecessor = sha(canonical(previous["receipt"]))
            require(
                previous is not None and predecessor == prior and self.trees() == previous["trees"],
                "research_generation_predecessor_identity",
            )
        self.ops.directory(stage, self.r.accounting)
        intent = self.record(stage + "/intent.json", self.stage_intent(phase, prior))
        checkpoint = "PREPARE"
        try:
            work = stage + "/work"
            self.ops.directory(work, self.r.accounting)
            netlist_state = self.prepare(phase, previous, work, maps)
            mapping = "".join(
                "DEFINE %s %s\n" % (self.r.rendering.token(k), self.copy.path(v)) for k, v in maps
            ).encode("ascii")
            self.write(work + "/cds.lib", mapping)
            self.write(work + "/fixed.ocn", program)
            require(
                self.guard(session) == before
                and (phase != "save" or not os.path.lexists(self.library)),
                "research_generation_prelaunch_drift",
            )
            owner = self
            deadline = os.times()[4] + 45

            class LiveGuard(object):
                def check(self):
                    session.check()
                    require(
                        time.time() < owner.scope["valid_until_unix"],
                        "research_generation_scope_expired",
                    )
                    owner.eda.measure_live(
                        session, owner.parent, deadline, owner.scope["external_bytes"]
                    )

            journal = type("ResearchJournal", (object,), dict(job=self.job, work=work))()
            checkpoint = "OCEAN"
            self.eda.program(
                LiveGuard(),
                journal,
                [
                    self.r.profile["tools"]["ocean"]["path"],
                    "-nograph",
                    "-nocdsinit",
                    "-log",
                    work + "/cadence.log",
                    "-cdslib",
                    work + "/cds.lib",
                    "-restore",
                    work + "/fixed.ocn",
                ],
                "ocean",
                45,
                self.scope["job_bytes"] - LIMIT,
            )
            checkpoint = "READBACK"
            require(
                not read_regular(work + "/ocean.stderr", 8192), "research_generation_ocean_stderr"
            )
            stdout = read_regular(work + "/ocean.stdout", MARKER_LIMIT)
            markers = [
                line
                for line in stdout.decode("ascii").splitlines()
                if line.startswith(("RESEARCH_BENCH_", "MOS_BLOCK_", "MCP_GENERIC_ADE_NETLIST|"))
            ]
            require(
                markers and markers == self.scope["markers"][phase], "research_generation_markers"
            )
            after = self.trees()
            require(
                previous is None or after == previous["trees"],
                "research_generation_owned_tree_drift",
            )
            full, dut = b"", b""
            if netlist_state:
                target, pin, bench_target, bench_copy = netlist_state
                require(
                    self.copy.snapshot(target)["tree_sha256"] == pin
                    and self.copy.snapshot(bench_target) == bench_copy,
                    "research_generation_ade_or_bench_drift",
                )
                full = read_regular(self.eda.find_input(work + "/project"), LIMIT)
                statements = self.r.modules["rendering"].statements(full)
                require(
                    sha(canonical(statements)) == digest(self.scope["netlist_statements_sha256"]),
                    "research_generation_netlist_statement_drift",
                )
                _, _, _, static = self.r.modules["rendering"].partition_input(full)
                dut = dut_projection(static, self.scope["dut_subcircuits"])
                self.write(stage + "/full.scs", full)
                self.write(stage + "/dut.scs", dut)
            require(self.guard(session) == before, "research_generation_postflight_drift")
            receipt = dict(
                phase=phase,
                operation_id=self.op,
                plan_sha256=self.binding["plan_sha256"],
                library=dict(
                    name=self.library_name, path=self.library, tree_sha256=after["library"]
                ),
                source_cell=self.library + "/" + self.dut,
                source_tree_sha256=after["dut"],
                bench_cell=self.library + "/" + self.bench,
                bench_tree_sha256=after["bench"],
                artifact_sha256=sha(full or stdout),
                script_sha256=None if full else sha(program),
            )
            record = dict(
                receipt=receipt,
                scope_sha256=self.binding["scope_sha256"],
                previous_receipt_sha256=prior,
                protected=before,
                trees=after,
                ocean_calls=1,
                simulations=0,
                reservations=0,
                output_sha256=sha(stdout),
                dut_sha256=sha(dut) if dut else None,
            )
            response = canonical(
                dict(
                    binding_sha256=self.binding_sha,
                    scope_sha256=self.binding["scope_sha256"],
                    program_sha256=sha(program),
                    previous_receipt_sha256=prior,
                    receipt=receipt,
                    stdout_base64=base64.b64encode(b"" if full else stdout).decode("ascii"),
                    dut_netlist_base64=base64.b64encode(dut).decode("ascii"),
                    full_netlist_base64=base64.b64encode(full).decode("ascii"),
                )
            )
            require(len(response) < WIRE_LIMIT, "research_generation_response_bound")
            retained = self.record(stage + "/receipt.json", record)
            self.record(
                stage + "/complete.json", dict(intent_sha256=intent, receipt_sha256=retained)
            )
            return response
        except (IOError, OSError, ValueError):
            try:
                self.record(
                    stage + "/failure.json", dict(status="OUTCOME_UNKNOWN", checkpoint=checkpoint)
                )
            except (IOError, OSError, ValueError):
                pass
            raise


def main():
    require(sys.version_info[:2] == (2, 6) and os.getuid() == 500, "research_generation_guest_host")
    # Fixed bootstrap reads this asset first. The remaining stdin is the request only.
    raw = sys.stdin.read(WIRE_LIMIT + 1)
    root, scope, binding, binding_sha, phase, prior, program = parse_request(sys.argv[1:], raw)
    runtime = load_runtime(root, scope, binding)
    os.umask(63)
    operation = GenerationPhase(runtime, scope, binding, binding_sha)
    with runtime.accounting.ReservationSession(root) as session:
        outcome = operation.run(session, phase, prior, program)
    sys.stdout.write(outcome)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("RESEARCH_GENERATION_REJECTED\n")
        sys.exit(69)
