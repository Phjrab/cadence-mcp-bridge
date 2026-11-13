"""Fixed Source9 PMOS phase and readback validator, Python 2.6 compatible."""

# mypy: ignore-errors

import sys

# This module is also imported by the host verifier. Scrub import paths only
# for the fixed remote entry point, before loading any other modules.
if __name__ == "__main__":
    sys.path[:] = [p for p in sys.path if p and p.startswith("/")]

import base64
import hashlib
import json
import os

if __name__ == "__main__":
    sys.path[:] = [p for p in sys.path if os.path.realpath(p) != os.path.realpath(os.getcwd())]

import re
import stat
import time
import types

OVERRIDES = ("w", "fw", "as", "ad", "ps", "pd")
BASELINE = {"w": "350n", "as": "98f", "ad": "98f", "ps": "1.26u", "pd": "1.26u"}
BASELINE_NETLIST = "5d4134980c80d6cff72e6c1adb0d5957e7871c7b52fa89d5482dfedf113c7f0a"
SOURCE_TREE = "64f06d2c1764f47681211920dc550409f8f09c64becbb74b6848a33d21998a52"
SOURCE_VIEWS = {
    "dut": "10e0afa1a0e39c42e92786299b39114c981b8988077d1ee9201ad4664dc4b8ed",
    "symbol": "247a21db3d90c5a67e7ef7e9c63f78cde4a943a38abda5d03d27b08fd023adfb",
    "tb": "6b70f3bdb99c3030bbb7d31273a552fdea702e4f0b221ace7db4beedb0032193",
}
STATE_TREE = "54c4215de1002d398aa80401880660f37df0c0cbc6c327755501ecf2949b494b"
LIMIT = 33554432
RESPONSE = 65536
TRANSPORT = 131072


DEFAULTS = (
    ("w", "lengthMetric", "120n"),
    ("fw", "lengthMetric", "120n"),
    ("l", "lengthMetric", "100n"),
    ("m", "nil", "1"),
    ("fingers", "nil", "1"),
    ("model", "nil", "gpdk090_pmos1v"),
    ("as", "nil", "69.6f"),
    ("ad", "nil", "69.6f"),
    ("ps", "lengthMetric", "1.16u"),
    ("pd", "lengthMetric", "1.16u"),
)


def _frame_check(condition):
    if not condition:
        raise ValueError("pmos_default_change_frame")


def read_frame(raw, candidate_library):
    _frame_check(0 < len(raw) <= 8192 and b"\r" not in raw and raw.endswith(b"\n"))
    lines = raw.decode("ascii").splitlines()
    _frame_check(
        lines[:3]
        == [
            "C1_PMOS_OVERRIDE_REVERSION|1",
            "TB|REOPENED|" + candidate_library + "|InvLong|symbol",
            "COPY|SOURCE_AND_CHILD|TOPOLOGY_AND_PROPERTIES_EQUAL",
        ]
    )
    _frame_check(lines[-2:] == ["COPY|REOPENED|FIXED_TOPOLOGY_AND_PROPERTIES_EQUAL", "COMPLETE"])
    rows = lines[3:-2]
    _frame_check(len(rows) == 76)
    stages = {}
    offset = 0
    removed = set(OVERRIDES)
    for stage in ("BASE", "COPY_BASELINE", "BEFORE_SAVE", "REOPENED"):
        observed = {}
        for name, units, default in DEFAULTS:
            old = "350n" if name == "fw" else BASELINE.get(name, default)
            expected = old if stage == "COPY_BASELINE" else default
            cdf = rows[offset].split("|")
            offset += 1
            kind = "baseCellData" if stage == "BASE" else "instData"
            _frame_check(cdf == ["CDF", stage, name, kind, units, expected])
            value = {"cdf_type": kind, "units": units, "effective": cdf[5]}
            if stage == "COPY_BASELINE" and name in removed:
                cell_default = rows[offset].split("|")
                offset += 1
                _frame_check(cell_default == ["DEFAULT", stage, name, default])
                value["effective_cell_default"] = cell_default[3]
            if stage != "BASE":
                oa = rows[offset].split("|")
                offset += 1
                absent = stage != "COPY_BASELINE" and name in removed
                expect_oa = ["ABSENT", "-", "-"] if absent else ["EXPLICIT", "string", expected]
                _frame_check(oa == ["OA", stage, name] + expect_oa)
                value.update(oa_state=oa[3], oa_value=None if absent else oa[5])
            observed[name] = value
        stages[stage] = observed
    _frame_check(offset == len(rows) and stages["BEFORE_SAVE"] == stages["REOPENED"])
    return stages


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(runtime, value):
    return sha(runtime.accounting.canonical(value))


def digest_string(value):
    return re.match(r"^[0-9a-f]{64}\Z", value) is not None


def uuid_string(value):
    return (
        re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z", value)
        is not None
    )


def private_source(path, expected):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        assert (
            stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1
            and info.st_uid == 500
            and not info.st_mode & 63
        )
        raw = stream.read(262145)
    assert len(raw) <= 262144 and sha(raw) == expected
    return raw


class Source9Change(object):  # noqa: UP004 - Python 2.6 new-style class
    def __init__(self, scope, scope_sha):
        self.scope = scope
        self.scope_sha = scope_sha
        self.root = "/home/buet/cds_work/.cadence_mcp"
        self.source = self.root + "/layout-owned-20261111/CmosLong20261111"
        self.state = "/home/buet/cds_work/M2Owned_States_20261015_v2/Owned_Inverter_TB"
        self.operation = scope["operation_id"]
        self.diagnostic = scope["diagnostic_netlist_id"]
        self.library = scope["candidate_library"]
        assert uuid_string(self.operation) and uuid_string(self.diagnostic)
        assert self.operation != self.diagnostic
        assert not set((self.operation, self.diagnostic)).intersection(
            ("fe36c224-f140-4dbf-a10f-13f12c389863", "35d50bb1-94df-4b9c-aa1f-5c8fa2300dd6")
        )
        assert re.match(r"^CmosLongPDefault[A-Za-z0-9]{3,32}\Z", self.library)
        assert self.library not in ("CmosLongPDefaultA1", "CmosLongPDefaultA1C1")
        assert scope["phases"] == ["revert", "netlist"] and scope["only_override_names"] == list(
            OVERRIDES
        )
        layout = scope["layout_manifest_sha256"]
        self.native = scope["native_manifest_sha256"]
        assert all(digest_string(value) for value in (layout, self.native, scope["worker_sha256"]))
        path = self.root + "/layout-runtime/" + layout + "/worker.py"
        self.worker = types.ModuleType("source9_default_layout_loader")
        self.worker.__file__ = path
        self.worker.__dict__["__package__"] = None
        raw = private_source(path, scope["worker_sha256"])
        eval(compile(raw, path, "exec"), self.worker.__dict__)
        self.runtime = self.worker.load_runtime(layout)
        assert self.runtime.manifest["native_runtime_manifest_sha256"] == self.native
        assert self.runtime.manifest["resource_domain_sha256"] == scope["resource_domain_sha256"]
        assert self.runtime.manifest["environment_sha256"] == scope["environment_sha256"]
        self.jobs = self.root + "/" + self.runtime.accounting.JOBS
        self.job = self.jobs + "/" + self.operation
        self.candidate = self.job + "/" + self.library
        (self.route,) = [
            row
            for row in self.runtime.original_registration["routes"]
            if row["design_id"] == "m2-owned-inverter" and row["analysis"] == "dc"
        ]
        assert self.route["source_state"] == self.state
        assert self.route["ade"]["ade_state_tree_sha256"] == STATE_TREE

        # Retain the installed supervision methods; scope the OCEAN working
        # directory to each private phase while sizing the entire change job.
        eda_path = self.root + "/runtime/" + self.native + "/worker.py"
        manifest = self.runtime.native.validate(self.native)[1]
        eda_raw = private_source(eda_path, manifest["files"]["worker.py"]["sha256"])
        old = 'cwd=journal.work if label == "spectre" else journal.job,'
        new = 'cwd=journal.work if label in ("spectre", "revert", "netlist") else journal.job,'
        assert eda_raw.count(old) == 1
        derived = eda_raw.replace(old, new)
        assert derived.replace(new, old) == eda_raw
        self.eda_module = types.ModuleType("source9_default_scoped_eda")
        self.eda_module.__file__ = eda_path
        self.eda_module.__dict__["__package__"] = None
        eval(compile(derived, eda_path, "exec"), self.eda_module.__dict__)
        self.eda = self.eda_module.EdaWorker(
            self.runtime.gate,
            self.runtime.operations,
            self.runtime.modules["rendering"],
            self.runtime.copying,
            self.runtime.modules["installer"],
        )

    def tree(self, path):
        return self.runtime.copying.snapshot(path)["tree_sha256"]

    def views(self, path):
        return dict(
            dut=self.tree(path + "/InvLong/schematic"),
            symbol=self.tree(path + "/InvLong/symbol"),
            tb=self.tree(path + "/InvLongTb/schematic"),
        )

    def protect(self, session, binding):
        runtime = self.runtime
        session.check()
        runtime.native.validate(self.native)
        runtime.native.activation(runtime.profile, self.native)
        runtime.native.history_guard(
            runtime.profile,
            self.native,
            runtime.manifest["identity_manifest_sha256"],
            runtime.modules["confirmation"],
        )
        runtime.gate.library_binding({"libraries": runtime.registration["libraries"]})
        runtime.gate.model_binding(self.route)
        assert self.tree(self.source) == SOURCE_TREE and self.views(self.source) == SOURCE_VIEWS
        assert self.tree(self.state) == STATE_TREE
        protected = runtime.protected_snapshot()
        assert digest(runtime, protected) == self.scope["protected_sha256"]
        counter, records = runtime.accounting.state(self.root, binding)
        assert counter == self.scope["counter"]
        ledger = runtime.operations.read_bytes(self.root + "/" + runtime.accounting.LEDGER)
        assert sha(ledger) == self.scope["counter_sha256"]
        old = sorted(name for name in os.listdir(self.jobs) if name != self.operation)
        assert (
            len(old) == self.scope["old_jobs"]
            and digest(runtime, old) == self.scope["old_jobs_sha256"]
        )
        models = runtime.modules["modeltrust"].trusted_model_metadata(
            dict((entry["path"], entry["file_sha256"]) for entry in self.route["model_files"])
        )
        result = dict(
            protected=protected,
            models=models,
            ledger=sha(ledger),
            records=digest(runtime, records),
            old_jobs=[(name, self.eda.size(self.jobs + "/" + name)) for name in old],
        )
        session.check()
        return digest(runtime, result)

    def capacity(self, binding, growth):
        runtime = self.runtime
        anchor = runtime.accounting.identity_manifest(self.root, binding)
        policy = runtime.accounting.effective_policy(self.root, anchor)
        ceiling = policy["result_ceiling_bytes"]
        assert ceiling == 17179869184 and policy["attempt_ceiling"] == 500
        runtime.copying.owned_parent(self.jobs)
        retained = runtime.layout_retained_bytes()
        for path in (
            self.source,
            "/home/buet/cds_work/CmosLong_Inputs_20261111_v1",
            "/home/buet/cds_work/CmosLong_P120_Inputs_20261113_v1",
            self.root + "/layout-owned-20261111/.c1-a02-occupancy-observation-01",
            self.root + "/layout-owned-20261111/.c1-a02-occupancy-observation-02",
        ):
            retained += max(self.eda.size(path)[:2])
        present = max(self.eda.size(self.job)[:2]) if os.path.lexists(self.job) else 0
        assert present <= LIMIT
        projection = LIMIT - present if growth else 0
        assert max(runtime.gate.occupancy()) + retained + projection <= ceiling
        # Native helper bytes are outside the reservation counter.
        for name in (
            "fe36c224-f140-4dbf-a10f-13f12c389863",
            "64bd94b5-40f9-4c53-89c2-137596f5c6fe",
            "f1da0abd-84bd-4af7-b85c-cb26f48ce825",
            "ed5858f2-1dc0-47d0-9960-3be160e3a100",
            "518844af-ce37-47d9-be48-b3d0eab838d0",
        ):
            retained += max(self.eda.size(self.jobs + "/" + name)[:2])
        counter, records = runtime.accounting.state(self.root, binding)
        assert counter == self.scope["counter"]
        assert counter["result_reserved_bytes"] + retained + present + projection <= ceiling
        inflight = sum(intent["binding"]["reserve_bytes"] for intent, receipt in records)
        fs = os.statvfs(self.root)
        unit = fs.f_frsize or fs.f_bsize
        limits = runtime.profile["limits"]
        floor = max(
            limits["disk_floor_bytes"],
            (fs.f_blocks * unit * limits["disk_floor_percent"] + 99) // 100,
        )
        assert fs.f_bavail * unit >= floor + inflight + projection

    def define(self, name, path):
        return "DEFINE {0} {1}\n".format(  # noqa: UP030, UP032 - Python 2.6
            self.runtime.rendering.token(name),
            self.runtime.copying.path(path),
        )

    def ocean(self, session, phase, selected, definitions, program):
        work = selected + "/work"
        self.runtime.operations.directory(work, self.runtime.accounting)
        self.eda.write(work + "/cds.lib", definitions.encode("ascii"))
        self.eda.write(work + "/fixed.ocn", program)
        journal = type("PmosDefaultJob", (object,), {"job": self.job, "work": work})()
        argv = [
            self.runtime.profile["tools"]["ocean"]["path"],
            "-nograph",
            "-nocdsinit",
            "-log",
            work + "/cadence.log",
            "-cdslib",
            work + "/cds.lib",
            "-restore",
            work + "/fixed.ocn",
        ]
        self.eda.program(session, journal, argv, phase, 45, LIMIT)
        return work

    def netlist(self, session, selected, definitions):
        runtime = self.runtime
        cell = "Grel_" + self.diagnostic.replace("-", "_")
        for leaf in (
            "library",
            "project",
            "state-root",
            "state-root/MCP_GREL_Work",
            "state-root/MCP_GREL_Work/" + cell,
            "state-root/MCP_GREL_Work/" + cell + "/spectre",
        ):
            runtime.operations.directory(selected + "/" + leaf, runtime.accounting)
        tb = self.candidate + "/InvLongTb"
        tb_tree = runtime.copying.snapshot(tb)
        state_tree = runtime.copying.snapshot(self.state)
        assert state_tree["tree_sha256"] == STATE_TREE
        self.eda.copy_capacity({"testbench": tb_tree, "state": state_tree}, self.job, LIMIT)
        runtime.copying.copy_owned(tb, selected + "/library/" + cell, tb_tree["tree_sha256"])
        state = selected + "/state-root/MCP_GREL_Work/" + cell + "/spectre/state1"
        runtime.copying.copy_owned(self.state, state, STATE_TREE)
        info = state + "/ADE_state.info"
        remapped = runtime.copying.remap_ade_info(
            runtime.modules["installer"].regular(info),
            ("M2Owned_SourceV3", "Owned_Inverter_TB", "schematic"),
            ("MCP_GREL_Work", cell, "schematic"),
            selected + "/project",
        )
        fd = os.open(info, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
        with os.fdopen(fd, "wb") as stream:
            stream.write(remapped)
            stream.flush()
            os.fsync(stream.fileno())
        assert runtime.modules["installer"].regular(info) == remapped
        runtime.accounting.sync_directory(state)
        definitions += self.define(self.library, self.candidate)
        definitions += self.define("MCP_GREL_Work", selected + "/library")
        program = (
            'unless(ddGetObj("MCP_GREL_Work") || ddCreateLib("MCP_GREL_Work" "'
            + selected
            + '/library") exit(1))\n'
        ).encode("ascii")
        inputs = dict(
            analysis="dc",
            mode="saved_operating_point",
            statement_sha256="5efc41247ec68e90840d347c30bb2c9d0177f894c8d736bf3c43afbc45ef51e6",
        )
        program += runtime.modules["rendering"].netlist(
            self.job,
            "schematic",
            "state1",
            [("m2_vin", "0")],
            inputs,
            self.scope_sha,
            self.diagnostic,
        )
        work = self.ocean(session, "netlist", selected, definitions, program)
        frame = runtime.operations.read_bytes(work + "/netlist.stdout")
        assert len(frame) <= RESPONSE
        assert (
            frame.splitlines().count(
                "MCP_GENERIC_ADE_NETLIST|" + self.scope_sha + "|" + self.diagnostic
            )
            == 1
        )
        assert runtime.copying.snapshot(tb) == tb_tree
        raw = runtime.modules["installer"].regular(self.eda.find_input(selected + "/project"))
        assert 0 < len(raw) <= 32768
        self.eda.write(selected + "/effective-input.scs", raw)
        return raw

    def write(self, path, value):
        raw = self.worker.canonical(value)
        self.eda.write(path, raw)
        assert self.runtime.operations.read_bytes(path) == raw

    def prior_reopen(self, previous, preserved):
        runtime = self.runtime
        assert set(previous) == set(("revert",))
        path = self.job + "/revert"
        receipt = runtime.operations.read(path + "-receipt.json")
        intent = runtime.operations.read(path + "-intent.json")
        complete = runtime.operations.read(path + "-complete.json")
        assert intent == self.intent("revert")
        assert digest(runtime, receipt) == previous["revert"]
        assert complete == dict(
            intent_sha256=digest(runtime, intent), receipt_sha256=previous["revert"]
        )
        assert receipt["status"] == "VERIFIED" and receipt["phase"] == "revert"
        assert receipt["source_preservation_sha256"] == preserved
        assert receipt["owned_tree_sha256"] == self.tree(self.candidate)
        assert receipt["view_tree_sha256"] == self.views(self.candidate)
        frame = runtime.operations.read_bytes(self.job + "/revert.frame")
        assert sha(frame) == receipt["frame_sha256"]
        read_frame(frame, self.library)
        return receipt

    def intent(self, phase):
        return dict(
            scope_sha256=self.scope_sha,
            phase=phase,
            operation_id=self.operation,
            payload_sha256=self.scope["skill_sha256"] if phase == "revert" else BASELINE_NETLIST,
        )

    def phase(self, phase, previous, skill, expiry):
        runtime = self.runtime
        os.umask(63)
        with runtime.accounting.ReservationSession(self.root) as session:
            domain, binding, user, uid = runtime.modules["confirmation"].domain(
                runtime.profile, runtime.manifest["identity_manifest_sha256"]
            )
            assert domain == self.root and user == "buet" and uid == 500
            before = self.protect(session, binding)
            self.capacity(binding, True)
            marker = self.job + "/" + phase
            selected = self.job + "/" + (phase if phase == "revert" else self.diagnostic)
            for path in (
                selected,
                marker + "-intent.json",
                marker + "-receipt.json",
                marker + "-complete.json",
                marker + "-failure.json",
            ):
                assert not os.path.lexists(path)
            if phase == "revert":
                assert previous == {} and not os.path.lexists(self.job)
            else:
                reopened = self.prior_reopen(previous, before)
            assert time.time() < expiry
            if phase == "revert":
                os.mkdir(self.job, 448)
                runtime.accounting.sync_directory(self.jobs)
            intent = self.intent(phase)
            self.write(marker + "-intent.json", intent)
            value = dict(
                status="OUTCOME_UNKNOWN",
                phase=phase,
                operation_id=self.operation,
                scope_sha256=self.scope_sha,
                old_jobs=self.scope["old_jobs"],
                current_jobs=self.scope["old_jobs"] + 1,
                ledger=self.scope["counter"],
                source_preservation_sha256=before,
                callback_executions=0,
                spectre_calls=0,
                simulations=0,
                reservations=0,
            )
            try:
                libraries = runtime.registration["libraries"]
                assert len(libraries) == 6
                assert not set((self.library, "CmosLong20261111", "MCP_GREL_Work")).intersection(
                    lib["name"] for lib in libraries
                )
                definitions = "".join(self.define(lib["name"], lib["path"]) for lib in libraries)
                runtime.operations.directory(selected, runtime.accounting)
                if phase == "revert":
                    self.eda.copy_capacity(
                        {"source": runtime.copying.snapshot(self.source)}, self.job, LIMIT
                    )
                    definitions += self.define("CmosLong20261111", self.source)
                    assert (
                        skill.count("__PMOS_JOB__") == 2
                        and skill.count("__PMOS_CHILD_LIBRARY__") == 3
                    )
                    program = skill.replace("__PMOS_JOB__", self.job).replace(
                        "__PMOS_CHILD_LIBRARY__", self.library
                    )
                    self.ocean(session, phase, selected, definitions, program)
                    raw = runtime.operations.read_bytes(self.job + "/revert.frame")
                    read_frame(raw, self.library)
                    value.update(frame_sha256=sha(raw), frame_base64=base64.b64encode(raw))
                else:
                    raw = self.netlist(session, selected, definitions)
                    assert self.tree(self.candidate) == reopened["owned_tree_sha256"]
                    assert self.views(self.candidate) == reopened["view_tree_sha256"]
                    value.update(
                        netlist_sha256=sha(raw),
                        effective_input_base64=base64.b64encode(raw),
                        diagnostic_netlist_id=self.diagnostic,
                    )
                revision, views = self.tree(self.candidate), self.views(self.candidate)
                assert revision != SOURCE_TREE and views["tb"] != SOURCE_VIEWS["tb"]
                value.update(status="VERIFIED", owned_tree_sha256=revision, view_tree_sha256=views)
            except Exception as error:
                value.update(status="OUTCOME_UNKNOWN", failure_type=type(error).__name__)
            assert self.protect(session, binding) == before
            self.capacity(binding, False)
            assert len(os.listdir(self.jobs)) == value["current_jobs"]
            logical, allocated, unused = self.eda.size(self.job)
            value.update(job_logical_bytes=logical, job_allocated_bytes=allocated)
            receipt = dict(
                (key, item) for key, item in value.items() if not key.endswith("_base64")
            )
            if value["status"] == "VERIFIED":
                self.write(marker + "-receipt.json", receipt)
                self.capacity(binding, False)
                receipt_sha = digest(runtime, receipt)
                self.write(
                    marker + "-complete.json",
                    dict(intent_sha256=digest(runtime, intent), receipt_sha256=receipt_sha),
                )
                value["receipt_sha256"] = receipt_sha
            else:
                self.write(marker + "-failure.json", receipt)
                value = receipt
            self.capacity(binding, False)
            session.check()
            raw = self.worker.canonical(value)
            assert len(raw) <= RESPONSE
            sys.stdout.write(raw)


def main():
    assert sys.version_info[:2] == (2, 6) and os.getuid() == 500
    assert len(sys.argv) == 2 and digest_string(sys.argv[1])
    raw = sys.stdin.read(TRANSPORT + 1)
    assert 0 < len(raw) <= TRANSPORT
    envelope = json.loads(raw)
    assert set(envelope) == set(
        ("phase", "previous", "scope_base64", "authority_base64", "baseline_base64", "skill_base64")
    )
    phase = envelope["phase"]
    assert phase in ("revert", "netlist")
    scope_raw = base64.b64decode(envelope["scope_base64"])
    assert sha(scope_raw) == sys.argv[1] and len(scope_raw) <= 16384
    scope = json.loads(scope_raw)
    authority = json.loads(base64.b64decode(envelope["authority_base64"]))
    assert set(authority) == set(("owner", "scope_sha256", "approved_actions", "valid_until_unix"))
    assert authority["owner"] == "C0" and authority["scope_sha256"] == sys.argv[1]
    assert authority["approved_actions"] == ["revert", "netlist"]
    assert (
        type(authority["valid_until_unix"]) is int
        and authority["valid_until_unix"] == scope["valid_until_unix"]
        and time.time() < authority["valid_until_unix"]
    )
    baseline = base64.b64decode(envelope["baseline_base64"])
    assert 0 < len(baseline) <= 32768 and sha(baseline) == BASELINE_NETLIST
    skill = base64.b64decode(envelope["skill_base64"])
    assert 0 < len(skill) <= 8192 and sha(skill) == scope["skill_sha256"]
    change = Source9Change(scope, sys.argv[1])
    change.phase(phase, envelope["previous"], skill, authority["valid_until_unix"])
