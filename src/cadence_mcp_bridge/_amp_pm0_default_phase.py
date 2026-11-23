"""Fixed AMP PM0 writer and separate readback/netlist phase (guest Python 2.6)."""

# mypy: ignore-errors
# ruff: noqa: UP004, UP010, UP030, UP031, UP032

import os
import sys

if __name__ == "__main__":
    sys.path[:] = [
        entry
        for entry in sys.path
        if entry and entry.startswith("/") and os.path.realpath(entry) != os.getcwd()
    ]

import base64
import calendar
import hashlib
import json
import math
import re
import stat
import time
import types
from decimal import Decimal, localcontext

CELL = "Differential_Amplifier_TB2"
CENTER = "c9bcf3e3bd8a9329ff0bb1513df2a08f8a4f60e314f04075e15a3422c03e4006"
LIMIT = 131072
COMMON_END = "; AMP_EDIT_ONLY\n"
CONFIRMATIONS = "amp-pm0-confirmations"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("ascii")


def parse(raw):
    value = json.loads(raw)
    assert isinstance(value, dict) and canonical(value) == raw
    return value


def hex_digest(token):
    return bool(re.match(r"^[0-9a-f]{64}\Z", token))


def job_id(token):
    return bool(
        re.match(r"^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}\Z", token)
    )


def pinned(raw, digest):
    assert hex_digest(digest) and sha(raw) == digest
    return raw


def identity(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_nlink,
        info.st_mode,
        info.st_size,
        info.st_mtime,
        info.st_ctime,
    )


def read(path, limit, private=True):
    before = os.lstat(path)
    assert os.path.realpath(path) == path
    assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= limit
    if private:
        assert before.st_uid == os.getuid() and stat.S_IMODE(before.st_mode) & 63 == 0
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        assert identity(os.fstat(stream.fileno())) == identity(before)
        raw = stream.read(limit + 1)
        assert len(raw) == before.st_size and identity(os.fstat(stream.fileno())) == identity(
            before
        )
    assert identity(os.lstat(path)) == identity(before)
    return raw


def private_path(path, parent):
    assert re.match(r"^/[A-Za-z0-9_./-]+\Z", path)
    assert path.startswith(parent + "/") and os.path.realpath(path) == path
    return path


def load_runtime(root, scope):
    native = scope["native"]
    layout = native["layout_manifest_sha256"]
    assert hex_digest(layout)
    path = root + "/layout-runtime/" + layout + "/worker.py"
    source = pinned(read(path, 262144), native["layout_worker_sha256"])
    module = types.ModuleType("fixed_amp_pm0_layout_loader")
    module.__file__ = path
    module.__dict__["__package__"] = None
    eval(compile(source, path, "exec"), module.__dict__)
    runtime = module.load_runtime(layout)
    assert runtime.root == root
    assert runtime.manifest["native_runtime_manifest_sha256"] == scope["native_manifest_sha256"]
    assert runtime.manifest["resource_domain_sha256"] == scope["resource_domain_sha256"]
    assert runtime.manifest["environment_sha256"] == scope["environment_sha256"]
    return module, runtime


def clock_rows(operation):
    def uptime():
        with open("/proc/uptime", "rb") as stream:
            value = stream.read(128).split()[0]
        assert re.match(r"^[0-9]+\.[0-9]{2}\Z", value)
        return float(value)

    u0 = uptime()
    wall = time.time()
    u1 = uptime()
    assert u1 >= u0 and u1 - u0 < 1
    first = int(wall)
    rows = [operation + "|edit", str(int(math.ceil(wall))), "%.9f|%.2f|%.2f" % (wall, u0, u1)]
    offsets = set()
    for epoch in range(first, first + 47):
        parts = time.localtime(epoch)
        choices = set()
        for dst in (0, 1, -1):
            translated = int(time.mktime(parts[:8] + (dst,)))
            if time.localtime(translated)[:6] == parts[:6]:
                choices.add(translated)
        assert choices == set((epoch,))
        offsets.add(calendar.timegm(parts) - epoch)
        rows.append(
            "%d|%s|%s"
            % (
                epoch,
                time.strftime("%b %d %H:%M:%S %Y", parts),
                time.strftime("%Y.%m.%d %H:%M:%S", time.gmtime(epoch)),
            )
        )
    assert len(offsets) == 1
    return "\n".join(rows) + "\n"


def render(source, parameters):
    # These are the only substitution points in the installed templates.
    seen = set(re.findall(r"@[A-Z_]+@", source))
    assert seen.issubset(set(parameters))
    for key in seen:
        value = parameters[key]
        assert re.match(r"^[a-zA-Z0-9_./-]+\Z", value)
        source = source.replace(key, value)
    assert "@" not in source and 0 < len(source) <= 32768
    return source


def normalized(rendering, raw, model, model_path):
    statements = list(rendering.statements(raw))
    aliases = ("parameters VBIASN=320m VBIASP=702m", "parameters VBIASN=0.320 VBIASP=0.702")
    rows = [index for index, line in enumerate(statements) if line.startswith("parameters ")]
    assert len(rows) == 1 and statements[rows[0]] in aliases
    statements[rows[0]] = aliases[1]
    includes = [line for line in statements if line.startswith("include ")]
    assert len(includes) == 1
    include = re.match(r'^include "(/[^"\r\n]+)" section=NN\Z', includes[0])
    assert include and os.path.realpath(include.group(1)) == model_path == model["path"]
    return statements


def expected_netlist(statements, plan):
    target = plan["target"]["instance"]
    assert (target["instance_path"], target["property_name"]) == ("PM0", "w")
    assert plan["target"]["kind"] == "schematic_mos_width"
    scales = {"m": 0, "um": -6, "nm": -9}
    with localcontext() as context:
        context.prec = 128
        old, requested = [
            Decimal(plan[field]["value"]).scaleb(scales[plan[field]["unit"]])
            for field in ("old", "requested")
        ]
    assert (old, requested) == (Decimal("20e-6"), Decimal("120e-9"))
    frame = pm0_frame()
    effective = dict(
        (row.split("|")[1], row.split("|")[-1]) for row in frame if row.startswith("AUTO120_PROP|")
    )
    changes = {"w": ("(20u)", "(120n)")}
    for delta in plan["allowed_derived"]:
        key = delta["before"]["property_name"]
        assert key == delta["after"]["property_name"] and key not in changes
        assert key in ("fw", "as", "ad", "ps", "pd") and delta["after"]["value"] == effective[key]
        changes[key] = (delta["before"]["value"], delta["after"]["value"])
    assert set(changes) == set(("w", "fw", "as", "ad", "ps", "pd"))
    # fw is witnessed independently in CDF. The registered Spectre input only emits w.
    del changes["fw"]
    (index,) = [i for i, row in enumerate(statements) if row.startswith("PM0 ")]
    row = re.match(r"^(PM0 \([^()]+\) [a-zA-Z0-9_]+) (.+)\Z", statements[index])
    assert row and row.group(1).endswith(" " + effective["model"])
    seen = set()
    updated = []
    for option in row.group(2).split(" "):
        key, value = option.split("=", 1)
        assert key not in seen
        seen.add(key)
        if key in changes:
            previous, expected = changes[key]
            assert value == previous
            option = key + "=" + expected
        updated.append(option)
    assert set(changes).issubset(seen) and "fw" not in seen
    return statements[:index] + [row.group(1) + " " + " ".join(updated)] + statements[index + 1 :]


def pm0_frame():
    values = {
        "w": "120n",
        "fw": "120n",
        "l": "1u",
        "m": "1",
        "fingers": "1",
        "nf": "-",
        "model": "gpdk090_pmos1v",
        "dfm": "Minimum",
        "as": "69.6f",
        "ad": "69.6f",
        "ps": "1.16u",
        "pd": "1.16u",
    }
    return sorted(
        ["AUTO120_MASTER|PM0|gpdk090|pmos1v|symbol"]
        + [
            "AUTO120_TERM|%s|%s" % term
            for term in (("D", "net33"), ("G", "Vbiasp"), ("S", "VDD"), ("B", "VDD"))
        ]
        + [
            "AUTO120_PROP|%s|%s|%s" % (name, "string|1u" if name == "l" else "-|-", value)
            for name, value in values.items()
        ]
    )


def edit_counter(output, operation_id):
    # OCEAN stdout is bytes and may contain a non-ASCII banner.
    done = ("AUTO120_DONE|%s|edit" % operation_id).encode("ascii")
    assert output.count(done) == 1
    (row,) = [row for row in output if row.startswith(b"AMP_SAVE_COUNTER|")]
    counter = re.match(b"^AMP_SAVE_COUNTER[|]([0-9]{1,10})\\Z", row)
    assert counter
    return int(counter.group(1))


def check_reopen_output(output, operation_id, frame):
    fields = (b"AUTO120_PROP|", b"AUTO120_TERM|", b"AUTO120_MASTER|")
    assert sorted(row for row in output if row.startswith(fields)) == [
        row.encode("ascii") for row in frame
    ]
    prefixes = (
        b"AUTO120_DONE|",
        b"C1_VERIFIED_INDEPENDENT_REOPEN",
        b"C1_AMP_ADE_STAGE|",
        b"C1_AMP_ADE_COMPLETE|",
    )
    expected = [
        "AUTO120_DONE|%s|reopen" % operation_id,
        "C1_VERIFIED_INDEPENDENT_REOPEN",
        "C1_AMP_ADE_STAGE|START_SESSION",
        "C1_AMP_ADE_STAGE|LOAD_PINNED_STATE",
        "C1_AMP_ADE_STAGE|SELECT_ANALYSIS",
        "C1_AMP_ADE_STAGE|EMIT_NETLIST",
        "C1_AMP_ADE_STAGE|CLOSE_SESSION",
        "C1_AMP_ADE_COMPLETE|child-netlist|%s" % operation_id,
    ]
    assert [row for row in output if row.startswith(prefixes)] == [
        row.encode("ascii") for row in expected
    ]


class AmplifierDefaultJob(object):
    def __init__(self, runtime, scope, digest, site, operator):
        self.runtime = runtime
        self.scope = scope
        self.pin = scope["native"]
        self.digest = digest
        self.op = scope["operation_id"]
        self.copy_op = self.pin["owned_copy_operation_id"]
        anchor = self.pin["baseline_observation_operation_id"]
        assert len(set((self.op, self.copy_op, anchor))) == 3
        assert all(job_id(op) for op in (self.op, self.copy_op, anchor))
        excluded = site["excluded_operation_ids"]
        assert 0 < len(excluded) <= 64 and len(set(excluded)) == len(excluded)
        assert all(job_id(op) for op in excluded)
        assert self.op not in excluded and self.copy_op not in excluded
        self.library = scope["owned_library"]
        assert re.match(r"^Amp[A-Za-z0-9_]{3,60}\Z", self.library)
        assert (scope["owned_cell"], scope["owned_view"]) == (CELL, "schematic")
        self.root = runtime.root
        self.operator = operator
        self.jobs = self.root + "/" + runtime.accounting.JOBS
        self.job = self.jobs + "/" + self.op
        self.owned_job = self.jobs + "/" + self.copy_op
        self.owned = self.owned_job + "/" + self.library
        self.view = self.owned + "/" + CELL + "/schematic"
        self.anchor = self.jobs + "/" + anchor + "/check"
        self.copy_claim = self.owned_job + "/amp-pm0-writer-intent.json"
        self.cap = self.pin["job_limit_bytes"]
        assert type(self.cap) is int and 524288 <= self.cap <= 8388608
        self.supplemental = self.pin["supplemental_bytes"]
        assert type(self.supplemental) is int and 0 <= self.supplemental <= 33554432
        (self.route,) = [
            r
            for r in runtime.original_registration["routes"]
            if (r["design_id"], r["analysis_id"])
            == ("reference-differential-amplifier-tb2", "matched-dc")
        ]
        source = site["original_source_library"]
        self.source = private_path(source, runtime.profile["paths"]["workspace_root"])
        assert not (self.source == self.root or self.source.startswith(self.root + "/"))
        self.ade = (
            operator.pw_dir
            + "/.artist_states/"
            + os.path.basename(source)
            + "/"
            + CELL
            + "/spectre/state1"
        )
        self.tech = private_path(site["technology_library"], operator.pw_dir)
        assert os.path.basename(self.tech) == "cdsDefTechLib"
        self.archive = self.route["source_cell"]
        assert self.archive.endswith("/" + CELL) and self.archive != self.source + "/" + CELL
        (self.model,) = self.route["ade"]["model_includes"]
        assert self.model["section"] == "NN"
        self.model_path = self.model["path"]
        assert os.path.realpath(self.model_path) == self.model_path
        paths = site["supplemental_paths"]
        assert len(paths) <= 64 and len(set(paths)) == len(paths)
        self.supplemental_paths = [
            private_path(path, runtime.profile["paths"]["workspace_root"]) for path in paths
        ]
        assert self.root + "/" + CONFIRMATIONS not in self.supplemental_paths

    def record(self, path, value):
        raw = canonical(value)
        self.runtime.eda.write(path, raw)
        assert read(path, LIMIT) == raw
        return sha(raw)

    def space(self, binding, ledger):
        rt = self.runtime
        records = ledger[1]
        counter = ledger[0]
        policy = rt.accounting.effective_policy(
            self.root, rt.accounting.identity_manifest(self.root, binding)
        )
        ceiling = policy["result_ceiling_bytes"]
        layout = rt.layout_retained_bytes()
        extra_paths = self.supplemental_paths + [self.root + "/" + CONFIRMATIONS]
        supplemental = sum(max(rt.eda.size(path)[:2]) for path in extra_paths)
        assert supplemental <= self.supplemental and supplemental + self.cap <= 33554432
        amp_jobs = sum(
            max(rt.eda.size(self.jobs + "/" + name)[:2])
            for name in os.listdir(self.jobs)
            if name != self.op
            and os.path.lexists(self.jobs + "/" + name + "/edit/intent.json")
            and self.jobs + "/" + name not in extra_paths
        )
        present = max(rt.eda.size(self.job)[:2]) if os.path.lexists(self.job) else 0
        assert present <= self.cap
        remaining = self.cap - present
        logical, allocated = rt.gate.occupancy()
        assert max(logical, allocated) + layout + supplemental + remaining <= ceiling
        assert (
            counter["result_reserved_bytes"] + layout + supplemental + amp_jobs + self.cap
            <= ceiling
        )
        statfs = os.statvfs(self.root)
        block = statfs.f_frsize or statfs.f_bsize
        limits = rt.profile["limits"]
        floor = max(
            limits["disk_floor_bytes"],
            (statfs.f_blocks * block * limits["disk_floor_percent"] + 99) // 100,
        )
        inflight = sum(intent["binding"]["reserve_bytes"] for intent, _ in records)
        assert statfs.f_bavail * block >= floor + inflight + remaining

    def protect(self, session):
        rt = self.runtime
        session.check()
        assert time.time() < self.scope["valid_until_unix"]
        rt.read_check({})
        assert not rt.gate.storage.active_eda(self.root, True)
        rt.gate.model_binding(self.route)
        archive_library = os.path.dirname(self.archive)
        (bound_archive,) = [
            lib for lib in self.route["libraries"] if lib["path"] == archive_library
        ]
        libraries = [lib for lib in self.route["libraries"] if lib != bound_archive]
        rt.gate.library_binding({"libraries": libraries})
        copy = rt.copying
        assert (
            copy.snapshot(self.source + "/" + CELL + "/schematic")["tree_sha256"]
            == self.pin["source_view_tree_sha256"]
        )
        assert (
            copy.dependency_snapshot(self.source)["tree_sha256"]
            == self.pin["source_library_tree_sha256"]
        )
        assert copy.snapshot(self.archive)["tree_sha256"] == self.pin["archive_cell_tree_sha256"]
        assert (
            copy.dependency_snapshot(archive_library)["tree_sha256"]
            == self.pin["archive_library_tree_sha256"]
        )
        assert (
            copy.snapshot(self.route["source_state"])["tree_sha256"]
            == self.pin["archive_state_tree_sha256"]
        )
        assert (
            copy.dependency_snapshot(self.tech)["tree_sha256"] == self.pin["technology_tree_sha256"]
        )
        assert copy.snapshot(self.ade)["tree_sha256"] == self.pin["ade_tree_sha256"]
        model = rt.modules["modeltrust"].trusted_model_graph(self.model_path, "NN")
        assert sha(canonical(model)) == self.pin["model_graph_sha256"]
        domain, binding, user, uid = rt.modules["confirmation"].domain(
            rt.profile, rt.manifest["identity_manifest_sha256"]
        )
        assert (domain, user, uid) == (self.root, self.operator.pw_name, self.operator.pw_uid)
        ledger = rt.accounting.state(self.root, binding)
        assert (
            sha(read(self.root + "/" + rt.accounting.LEDGER, 262144)) == self.pin["ledger_sha256"]
        )
        names = sorted(os.listdir(self.jobs))
        assert len(names) <= 4096
        retained = [
            (name, rt.eda.size(self.jobs + "/" + name))
            for name in names
            if name not in (self.op, self.copy_op)
        ]
        assert sha(canonical(retained)) == self.pin["retained_jobs_sha256"]
        assert sha(canonical(rt.protected_snapshot())) == self.scope["source_preservation_sha256"]
        self.space(binding, ledger)
        session.check()

    def snapshot(self):
        tree = self.runtime.copying.snapshot(self.owned)
        prefix = CELL + "/schematic"
        outside = [
            row
            for row in tree["metadata"]
            if row[1] not in ("", CELL, prefix) and not row[1].startswith(prefix + "/")
        ]
        return self.runtime.copying.snapshot(self.view)["tree_sha256"], outside

    def mapping(self):
        libs = [
            row
            for row in self.route["libraries"]
            if row["name"] in ("basic", "analogLib", "gpdk090")
        ]
        assert (
            set(row["name"] for row in libs) == set(("basic", "analogLib", "gpdk090"))
            and len(libs) == 3
        )
        libs.extend(
            (dict(name="cdsDefTechLib", path=self.tech), dict(name=self.library, path=self.owned))
        )
        rt = self.runtime
        return "".join(
            "DEFINE %s %s\n" % (rt.rendering.token(row["name"]), rt.copying.path(row["path"]))
            for row in libs
        )

    def run(self, session, stage, program, edit=False):
        rt = self.runtime
        work = stage + "/work"
        rt.operations.directory(work, rt.accounting)
        rt.eda.write(work + "/cds.lib", self.mapping().encode("ascii"))
        rt.eda.write(work + "/fixed.ocn", program.encode("ascii"))
        self.protect(session)
        tool = rt.profile["tools"]["ocean"]
        assert rt.modules["probe"].digest_file(os.path.realpath(tool["path"])) == tool["sha256"]
        argv = [
            tool["path"],
            "-nograph",
            "-nocdsinit",
            "-log",
            work + "/cadence.log",
            "-cdslib",
            work + "/cds.lib",
            "-restore",
            work + "/fixed.ocn",
        ]
        journal = type("AmplifierPm0Journal", (object,), dict(job=self.job, work=work))()
        if edit:
            rt.eda.write(work + "/clock.rows", clock_rows(self.op).encode("ascii"))
        rt.eda.program(session, journal, argv, "ocean", 45, self.cap - LIMIT)
        assert not read(work + "/ocean.stderr", 8192)
        return read(work + "/ocean.stdout", 32768).splitlines()

    def qualified_baseline(self):
        raw = pinned(
            read(self.anchor + "/receipt.json", 16384),
            self.pin["baseline_observation_receipt_sha256"],
        )
        receipt = parse(raw)
        complete = parse(read(self.anchor + "/complete.json", 4096))
        assert complete["receipt_sha256"] == sha(raw)
        assert receipt["status"] == "CLOSED_BASELINE_DIAGNOSTIC"
        assert receipt["operation"] == self.pin["baseline_observation_operation_id"]
        assert receipt["signatures"][0] == self.pin["baseline_signature_sha256"]
        return pinned(
            read(self.anchor + "/before.txt", 65536), self.pin["baseline_signature_sha256"]
        )

    def record_failure(self, session, stage, error):
        # End the attempt in place; never remove an intent, copy or partial result.
        protected = "UNKNOWN"
        try:
            self.protect(session)
            protected = "MATCHED"
        except Exception:
            pass
        self.record(
            stage + "/failure.json",
            dict(
                status="OUTCOME_UNKNOWN",
                operation_id=self.op,
                scope_sha256=self.digest,
                failure_type=type(error).__name__,
                source_conservation=protected,
            ),
        )

    def edit(self, session, template):
        rt = self.runtime
        self.protect(session)
        assert not os.path.lexists(self.job) and not os.path.lexists(self.copy_claim)
        rt.copying.owned_parent(self.owned_job)
        baseline = self.qualified_baseline()
        before, outside = self.snapshot()
        assert before == self.scope["owned_before_view_tree_sha256"]
        assert (
            rt.copying.snapshot(self.owned)["tree_sha256"] == self.pin["owned_library_tree_sha256"]
        )
        claim = dict(
            operation_id=self.op, scope_sha256=self.digest, target=self.copy_op, retry=False
        )
        self.record(self.copy_claim, claim)
        rt.operations.directory(self.job, rt.accounting)
        stage = self.job + "/edit"
        rt.operations.directory(stage, rt.accounting)
        self.record(stage + "/intent.json", claim)
        try:
            rt.eda.write(stage + "/qualified-before.txt", baseline)
            program = render(
                template,
                {
                    "@STAGE@": stage,
                    "@JOB@": self.job,
                    "@OWNED@": self.owned,
                    "@LIB@": self.library,
                    "@OP@": self.op,
                    "@TECH@": self.tech,
                },
            )
            counter = edit_counter(self.run(session, stage, program, edit=True), self.op)
            presave = read(stage + "/pre-save.txt", 65536)
            saved = read(stage + "/saved-full.txt", 65536)
            after, remainder = self.snapshot()
            assert after != before and remainder == outside
            self.protect(session)
            receipt = dict(
                status="SAVED",
                operation_id=self.op,
                scope_sha256=self.digest,
                saved_view_tree_sha256=after,
                presave_signature_sha256=sha(presave),
                saved_library_tree_sha256=rt.copying.snapshot(self.owned)["tree_sha256"],
                reopened_signature_sha256=sha(saved),
                edit_live_counter=counter,
                source_preservation_sha256=self.scope["source_preservation_sha256"],
            )
            digest = self.record(stage + "/receipt.json", receipt)
            self.record(stage + "/complete.json", dict(receipt_sha256=digest))
            return dict(receipt=receipt, receipt_sha256=digest)
        except Exception as error:
            self.record_failure(session, stage, error)
            raise

    def copy_ade(self, stage):
        rt = self.runtime
        project = stage + "/project"
        root = stage + "/state-root"
        snap = rt.copying.snapshot(self.ade)
        assert snap["tree_sha256"] == self.pin["ade_tree_sha256"]
        rt.eda.copy_capacity({"state": snap}, self.job, self.cap)
        for path in (
            project,
            root,
            root + "/" + self.library,
            root + "/" + self.library + "/" + CELL,
            root + "/" + self.library + "/" + CELL + "/spectre",
        ):
            rt.operations.directory(path, rt.accounting)
        target = root + "/" + self.library + "/" + CELL + "/spectre/state1"
        rt.copying.copy_owned(self.ade, target, snap["tree_sha256"])
        path = target + "/ADE_state.info"
        original = read(self.ade + "/ADE_state.info", 65536, False)
        assert read(path, 65536) == original
        data = rt.copying.remap_ade_info(
            original,
            (os.path.basename(self.source), CELL, "schematic"),
            (self.library, CELL, "schematic"),
            project,
        )
        before = os.lstat(path)
        fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "wb") as stream:
            assert identity(os.fstat(stream.fileno())) == identity(before)
            stream.truncate(0)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        rt.copying.sync(target)
        assert read(path, 65536) == data
        return project, target

    def expected_input(self, baseline):
        original = normalized(
            self.runtime.modules["rendering"], baseline, self.model, self.model_path
        )
        return expected_netlist(original, self.scope["plan"])

    def verify(self, session, prior, edit_template, verify_template, expected):
        rt = self.runtime
        self.protect(session)
        edit_stage = self.job + "/edit"
        edit = parse(pinned(read(edit_stage + "/receipt.json", 16384), prior))
        assert parse(read(edit_stage + "/complete.json", 4096)) == dict(receipt_sha256=prior)
        assert not os.path.lexists(edit_stage + "/failure.json")
        assert (edit["status"], edit["operation_id"], edit["scope_sha256"]) == (
            "SAVED",
            self.op,
            self.digest,
        )
        claim = parse(read(self.copy_claim, 4096))
        assert claim == dict(
            operation_id=self.op, scope_sha256=self.digest, target=self.copy_op, retry=False
        )
        before = self.snapshot()
        assert before[0] == edit["saved_view_tree_sha256"]
        assert rt.copying.snapshot(self.owned)["tree_sha256"] == edit["saved_library_tree_sha256"]
        frozen = pinned(
            read(edit_stage + "/saved-full.txt", 65536), edit["reopened_signature_sha256"]
        )
        presave = pinned(
            read(edit_stage + "/pre-save.txt", 65536), edit["presave_signature_sha256"]
        )
        stage = self.job + "/readback-netlist"
        assert not os.path.lexists(stage)
        rt.operations.directory(stage, rt.accounting)
        self.record(
            stage + "/intent.json",
            dict(operation_id=self.op, scope_sha256=self.digest, prior=prior),
        )
        try:
            project, ade = self.copy_ade(stage)
            ade_before = rt.copying.snapshot(ade)
            frame = pm0_frame()
            marker = (
                "\n".join(["READ_ONLY_CLOSED|%s|%s" % (self.op, sha(frozen))] + frame) + "\n"
            ).encode("ascii")
            rt.eda.write(stage + "/expected-footprint.txt", frozen)
            rt.eda.write(stage + "/expected-frame.txt", marker)
            assert edit_template.count(COMMON_END) == 1
            program = render(
                edit_template.split(COMMON_END, 1)[0] + verify_template,
                {
                    "@STAGE@": stage,
                    "@OWNED@": self.owned,
                    "@LIB@": self.library,
                    "@OP@": self.op,
                    "@SAVED_SIGNATURE@": sha(frozen),
                    "@TECH@": self.tech,
                },
            )
            check_reopen_output(self.run(session, stage, program), self.op, frame)
            reopened = read(stage + "/fixed-footprint.txt", 65536)
            assert reopened == frozen and read(stage + "/readback.txt", 8192) == marker
            assert self.snapshot() == before and rt.copying.snapshot(ade) == ade_before
            raw = read(rt.eda.find_input(project), 32768, False)
            assert expected == normalized(rt.modules["rendering"], raw, self.model, self.model_path)
            headers = raw.splitlines()
            for line in ("// Design library name: " + self.library, "// Design cell name: " + CELL):
                assert headers.count(line.encode("ascii")) == 1
            rt.eda.write(stage + "/effective-input.scs", raw)
            self.protect(session)
            reopen_pin = self.record(
                stage + "/reopen-receipt.json",
                dict(
                    operation_id=self.op,
                    scope_sha256=self.digest,
                    view_tree_sha256=before[0],
                    footprint_sha256=sha(reopened),
                    readback_sha256=sha(marker),
                ),
            )
            netlist_pin = self.record(
                stage + "/netlist-receipt.json",
                dict(
                    operation_id=self.op,
                    scope_sha256=self.digest,
                    view_tree_sha256=before[0],
                    reopen_receipt_sha256=reopen_pin,
                    input_sha256=sha(raw),
                ),
            )
            receipt = dict(
                status="VERIFIED",
                operation_id=self.op,
                scope_sha256=self.digest,
                plan_sha256=self.scope["plan_sha256"],
                owned_before_view_tree_sha256=self.scope["owned_before_view_tree_sha256"],
                saved_view_tree_sha256=before[0],
                reopened_view_tree_sha256=before[0],
                netlisted_view_tree_sha256=before[0],
                source_preservation_sha256=self.scope["source_preservation_sha256"],
                reopen_receipt_sha256=reopen_pin,
                netlist_receipt_sha256=netlist_pin,
                presave_signature_sha256=sha(presave),
                reopened_signature_sha256=sha(reopened),
                netlist_sha256=sha(raw),
                edit_live_counter=edit["edit_live_counter"],
                reopen_frame=frame,
                ocean_calls=2,
                simulations=0,
                reservations=0,
            )
            response = dict(
                receipt=receipt,
                receipt_sha256=sha(canonical(receipt)),
                presave_base64=base64.b64encode(presave),
                reopened_base64=base64.b64encode(reopened),
                input_base64=base64.b64encode(raw),
            )
            assert len(canonical(response)) <= LIMIT
            digest = self.record(stage + "/receipt.json", receipt)
            self.record(stage + "/complete.json", dict(receipt_sha256=digest))
            return response
        except Exception as error:
            self.record_failure(session, stage, error)
            raise


def decode(packet, name, limit):
    token = packet[name + "_base64"].encode("ascii")
    assert len(token) <= 4 * ((limit + 2) // 3)
    raw = base64.b64decode(token)
    assert 0 < len(raw) <= limit and base64.b64encode(raw) == token
    return raw


def main():
    import pwd

    # A caller cannot disable the checks embedded in the reviewed guest.
    if sys.version_info[:2] != (2, 6) or os.getuid() == 0 or sys.flags.optimize:
        raise ValueError("AMP native guest identity")
    operator = pwd.getpwuid(os.getuid())
    assert len(sys.argv) == 4
    digest, phase, prior = sys.argv[1:]
    assert hex_digest(digest) and (
        (phase == "edit" and prior == "none") or (phase == "readback-netlist" and hex_digest(prior))
    )
    packet = parse(sys.stdin.read(LIMIT + 1))
    assert set(packet) == set(
        (
            "managed_root",
            "scope_base64",
            "authority_base64",
            "baseline_base64",
            "edit_base64",
            "verify_base64",
        )
    )
    root = private_path(packet["managed_root"], operator.pw_dir)
    raw_scope = pinned(decode(packet, "scope", 32768), digest)
    scope = parse(raw_scope)
    assert scope["schema_version"] == 1 and scope["route"] == "amplifier_pm0_default"
    assert job_id(scope["operation_id"]) and hex_digest(scope["plan_sha256"])
    assert sha(canonical(scope["plan"])) == scope["plan_sha256"]
    assert scope["plan"]["baseline"]["netlist_sha256"] == CENTER
    assert type(scope["valid_until_unix"]) is int and time.time() < scope["valid_until_unix"]
    authority = decode(packet, "authority", 4096)
    assert parse(authority) == dict(
        owner="C0",
        operation_id=scope["operation_id"],
        scope_sha256=digest,
        approved_actions=["edit", "readback-netlist"],
        valid_until_unix=scope["valid_until_unix"],
    )
    baseline = pinned(decode(packet, "baseline", 32768), CENTER)
    edit = pinned(decode(packet, "edit", 32768), scope["edit_script_sha256"])
    verify = pinned(decode(packet, "verify", 32768), scope["verify_script_sha256"])
    _, runtime = load_runtime(root, scope)
    os.umask(63)
    with runtime.accounting.ReservationSession(root) as session:
        # The native operator provisions these documents outside the reservation registry.
        directory = root + "/" + CONFIRMATIONS
        runtime.copying.owned_parent(directory)
        stamp = identity(os.lstat(directory))
        assert read(directory + "/" + digest + ".json", 4096) == authority
        site_pin = scope["native"]["site_sha256"]
        assert hex_digest(site_pin)
        site = parse(pinned(read(directory + "/" + site_pin + ".site.json", 16384), site_pin))
        assert set(site) == set(
            (
                "original_source_library",
                "technology_library",
                "excluded_operation_ids",
                "supplemental_paths",
            )
        )
        assert stamp == identity(os.lstat(directory))
        job = AmplifierDefaultJob(runtime, scope, digest, site, operator)
        expected = job.expected_input(baseline)
        result = (
            job.edit(session, edit)
            if phase == "edit"
            else job.verify(session, prior, edit, verify, expected)
        )
        assert stamp == identity(os.lstat(directory))
        session.check()
        raw = canonical(result)
        assert len(raw) <= LIMIT
        sys.stdout.write(raw)


if __name__ == "__main__":
    main()
