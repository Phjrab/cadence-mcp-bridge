"""Compiled standard-VM OA/ADE/netlist/Spectre/reader worker, Python2.6.

No raw command/path/code input surface. Only the verified runtime's registered
route and confirmed numeric request are consumed. Original source is read-only.
"""

# mypy: ignore-errors
import errno
import hashlib
import math
import os
import signal
import stat
import subprocess
import time


class EdaWorker(object):
    def __init__(self, gate, operations, rendering, copying, installer):
        self.gate, self.operations, self.rendering = gate, operations, rendering
        self.copying, self.installer = copying, installer

    def write(self, path, data):
        self.operations.private(os.path.dirname(path), True)
        if len(data) > 262144:
            raise ValueError("native_worker_input_size")
        self.installer.exclusive(path, data)
        self.gate.accounting.sync_directory(os.path.dirname(path))

    def size(self, job):
        io = self.gate.storage.PosixIO()
        parent = io.root(os.path.dirname(job))
        try:
            logical, allocated, fingerprint = self.gate.storage.tree(
                io, parent, os.path.basename(job), [0]
            )
            return logical, allocated, fingerprint
        finally:
            os.close(parent)

    def live(self, session, plan):
        session.check()
        self.gate.read(plan)
        self.gate.confirmation.inspect(
            self.gate.profile, plan["grant_sha256"], self.gate.anchor, True
        )
        session.observe(
            self.operations.read(
                self.gate.root
                + "/"
                + self.gate.accounting.JOBS
                + "/"
                + self.operation_id
                + "/work/operation/admission.json"
            )["binding"]
        )

    def process_identity(self, pid):
        # Linux /proc is part of the qualified standard VM. Keep the Popen
        # leader unreaped (including its zombie) until its group is empty.
        path = "/proc/%d/stat" % pid
        if os.stat(path).st_uid != os.getuid():
            raise ValueError("native_worker_process_owner")
        stream = open(path, "rb")
        try:
            raw = stream.read(8193).decode("ascii")
        finally:
            stream.close()
        fields = raw[raw.rfind(")") + 2 :].split()
        if len(raw) > 8192 or len(fields) < 20:
            raise ValueError("native_worker_process_identity")
        return fields[0], int(fields[2]), int(fields[3]), fields[19]

    def group_active(self, process, identity):
        current = self.process_identity(process.pid)
        if current[1:] != identity[1:] or current[1:3] != (process.pid, process.pid):
            raise ValueError("native_worker_process_identity_drift")
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                if os.stat("/proc/" + name + "/stat").st_uid != os.getuid():
                    continue
                member = self.process_identity(int(name))
            except OSError as error:
                if error.errno in (errno.ENOENT, errno.ESRCH):
                    continue
                raise
            if member[1] == process.pid and member[0] not in ("Z", "X"):
                return True
        return False

    def signal_group(self, process, identity, sig):
        # PID/PGID cannot be recycled while the unreaped leader remains pinned.
        current = self.process_identity(process.pid)
        if current[1:] != identity[1:] or os.getpgid(process.pid) != process.pid:
            raise ValueError("native_worker_process_identity_drift")
        os.killpg(process.pid, sig)

    def program(self, session, journal, argv, label, seconds, limit):
        # argv is constructed only by this compiled worker. No JSON selects it.
        session.check()
        process, identity = None, None
        out, err, null = None, None, None
        deadline = os.times()[4] + seconds
        try:
            for suffix in ("stdout", "stderr"):
                fd = os.open(
                    journal.work + "/" + label + "." + suffix,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    384,
                )
                try:
                    stream = os.fdopen(fd, "wb")
                except Exception:
                    os.close(fd)
                    raise
                if suffix == "stdout":
                    out = stream
                else:
                    err = stream
            null = open(os.devnull, "rb")
            process = subprocess.Popen(
                argv,
                cwd=journal.job,
                stdin=null,
                stdout=out,
                stderr=err,
                close_fds=True,
                preexec_fn=os.setsid,
                shell=False,
            )
            identity = self.process_identity(process.pid)
            while self.group_active(process, identity):
                session.check()
                logical, allocated, fingerprint = self.size(journal.job)
                if os.times()[4] >= deadline or max(logical, allocated) > limit:
                    raise ValueError("native_worker_owned_process_limit")
                time.sleep(0.1)
            # Reap only after the entire owned group has stopped writing.
            returncode = process.wait()
            process = None
            if returncode != 0:
                raise ValueError("native_worker_program_failed")
            logical, allocated, fingerprint = self.size(journal.job)
            if max(logical, allocated) > limit:
                raise ValueError("native_worker_owned_process_limit")
        finally:
            try:
                if process is not None:
                    if identity is None:
                        identity = self.process_identity(process.pid)
                    if self.group_active(process, identity):
                        self.signal_group(process, identity, signal.SIGTERM)
                        end = os.times()[4] + 2
                        while self.group_active(process, identity) and os.times()[4] < end:
                            time.sleep(0.05)
                        if self.group_active(process, identity):
                            self.signal_group(process, identity, signal.SIGKILL)
                        # Retain the worker's lifetime lock until all owned
                        # group members stop, even if the leader exited first.
                        while self.group_active(process, identity):
                            time.sleep(0.05)
                    process.wait()
            finally:
                if null is not None:
                    null.close()
                try:
                    for stream in (out, err):
                        if stream is not None:
                            stream.flush()
                            os.fsync(stream.fileno())
                finally:
                    for stream in (out, err):
                        if stream is not None:
                            stream.close()
                self.gate.accounting.sync_directory(journal.work)

    def protected(self, route, before):
        for key, registration_key in (
            ("source_cell", "source_tree_sha256"),
            ("source_state", "ade_state_tree_sha256"),
        ):
            current = self.copying.snapshot(route[key])
            if current != before[key] or current["tree_sha256"] != route["ade"][registration_key]:
                raise ValueError("native_worker_original_drift")
        for model in route["ade"]["model_includes"]:
            if self.gate.probe.digest_file(model["path"]) != model["file_sha256"]:
                raise ValueError("native_worker_model_drift")

    def find_input(self, project):
        selected, nodes = [], 0
        for current, dirs, files in os.walk(project):
            nodes += len(dirs) + len(files)
            if nodes > 4096 or len(current[len(project) :].split("/")) > 16:
                raise ValueError("native_worker_netlist_inventory")
            for name in dirs + files:
                path = current + "/" + name
                info = os.lstat(path)
                if not stat.S_ISDIR(info.st_mode) and not stat.S_ISREG(info.st_mode):
                    raise ValueError("native_worker_netlist_link_or_special")
            if "input.scs" in files:
                selected.append(current + "/input.scs")
        if len(selected) != 1:
            raise ValueError("native_worker_unique_effective_input_required")
        return selected[0]

    def frame(self, data, plan, route, input_sha):
        lines = data.decode("ascii").splitlines()
        expected = "|".join(
            (
                "MCP_GREL_FRAME",
                "1",
                self.operation_id,
                self.operations.digest(self.operations.canonical(plan)),
                input_sha,
                self.operations.digest(self.operations.canonical(route["reader"])),
            )
        )
        if not lines or lines[0] != expected or lines[-1] != "END" or len(data) > 65536:
            raise ValueError("native_worker_frame_binding")
        index = 1
        for node in route["reader"]["nodes"]:
            if plan["analysis"] == "dc":
                row = lines[index].split("|")
                if len(row) != 3 or row[:2] != ["V", node["logical_id"]]:
                    raise ValueError("native_worker_frame_inventory")
                self.finite(row[2])
                index += 1
            else:
                count, previous = 0, None
                while index < len(lines) - 1 and lines[index].startswith(
                    "P|" + node["logical_id"] + "|"
                ):
                    row = lines[index].split("|")
                    if len(row) != 6 or row[2] != str(count):
                        raise ValueError("native_worker_frame_inventory")
                    axis = self.finite(row[3])
                    self.finite(row[4])
                    self.finite(row[5])
                    if previous is not None and axis <= previous:
                        raise ValueError("native_worker_frame_axis")
                    previous, count, index = axis, count + 1, index + 1
                if not 2 <= count <= route["reader"]["maximum_samples"]:
                    raise ValueError("native_worker_frame_count")
        for source in route["reader"]["sources"]:
            row = lines[index].split("|")
            if len(row) != 3 or row[:2] != ["I", source["source_id"]]:
                raise ValueError("native_worker_frame_inventory")
            self.finite(row[2])
            index += 1
        if index != len(lines) - 1:
            raise ValueError("native_worker_frame_extra_rows")

    def finite(self, text):
        if len(text) > 48:
            raise ValueError("native_worker_frame_number")
        self.rendering.number_text(text)
        number = float(text)
        if math.isnan(number) or math.isinf(number):
            raise ValueError("native_worker_frame_number")
        return number

    def run(self, session, journal, plan):
        self.operation_id = journal.operation_id
        self.live(session, plan)
        route = self.gate.route(plan)
        before = dict(
            (key, self.copying.snapshot(route[key])) for key in ("source_cell", "source_state")
        )
        self.protected(route, before)
        amount = plan["request"]["result_reservation_bytes"]
        if sum(v["bytes"] for v in before.values()) + 1048576 > amount:
            raise ValueError("native_worker_copy_capacity")
        root, work = journal.job, journal.work
        for name in ("library", "state-root", "project"):
            self.operations.directory(root + "/" + name, self.gate.accounting)
        cell = "Grel_" + journal.operation_id.replace("-", "_")
        copied = self.copying.copy_owned(
            route["source_cell"], root + "/library/" + cell, route["ade"]["source_tree_sha256"]
        )
        state_parent = root + "/state-root/MCP_GREL_Work"
        for path in (
            state_parent,
            state_parent + "/" + cell,
            state_parent + "/" + cell + "/spectre",
        ):
            self.operations.directory(path, self.gate.accounting)
        state = (
            state_parent + "/" + cell + "/spectre/" + route["profile"]["binding"]["ade"]["state"]
        )
        copied_state = self.copying.copy_owned(
            route["source_state"], state, route["ade"]["ade_state_tree_sha256"]
        )
        original_info = self.installer.regular(state + "/ADE_state.info")
        source = route["profile"]["binding"]
        remapped = self.copying.remap_ade_info(
            original_info,
            (source["library"], source["cell"], source["view"]),
            ("MCP_GREL_Work", cell, source["view"]),
            root + "/project",
        )
        # Only owned info routing changes. Preserve the copied bytes as evidence.
        self.write(work + "/original-owned-ADE_state.info", original_info)
        self.operations.private(state + "/ADE_state.info")
        stream = open(state + "/ADE_state.info", "wb")
        try:
            stream.write(remapped)
            stream.flush()
            os.fsync(stream.fileno())
        finally:
            stream.close()
        self.gate.accounting.sync_directory(state)
        definitions = [
            "DEFINE " + library["name"] + " " + library["path"] for library in route["libraries"]
        ]
        definitions.append("DEFINE MCP_GREL_Work " + root + "/library")
        self.write(root + "/cds.lib", ("\n".join(definitions) + "\n").encode("ascii"))
        values = dict((v["logical_id"], v["value"]) for v in plan["request"]["values"])
        mapped = [(v["cadence_binding"], values[v["logical_id"]]) for v in route["variables"]]
        netlist = self.rendering.netlist(
            self.gate.profile["paths"]["job_root"],
            source["view"],
            source["ade"]["state"],
            mapped,
            route["ade"]["inputs"],
            journal.plan_sha,
            journal.operation_id,
        )
        create = (
            'unless(ddGetObj("MCP_GREL_Work") || ddCreateLib("MCP_GREL_Work" '
            + self.rendering.quoted(root + "/library")
            + ") exit(1))\n"
        )
        script = create.encode("ascii") + netlist
        self.write(work + "/netlist.ocn", script)
        ocean = self.gate.profile["tools"]["ocean"]["path"]
        self.program(
            session,
            journal,
            [
                ocean,
                "-nograph",
                "-nocdsinit",
                "-log",
                work + "/netlist-cadence.log",
                "-cdslib",
                root + "/cds.lib",
                "-restore",
                work + "/netlist.ocn",
            ],
            "netlist",
            240,
            amount,
        )
        self.protected(route, before)
        native_input = self.installer.regular(self.find_input(root + "/project"))
        parameters = dict(
            (v["cadence_binding"], self.rendering.number_text(values[v["logical_id"]]))
            for v in route["variables"]
        )
        effective = self.rendering.effective_input(
            native_input,
            parameters,
            [(m["path"], m["section"]) for m in route["ade"]["model_includes"]],
            route["ade"]["inputs"],
            route["ade"]["static_statements_sha256"],
        )
        input_sha = effective["input_sha256"]
        self.write(work + "/input.scs", native_input)
        self.gate.accounting.write_new(
            work + "/effective-input.json",
            {
                "schema_version": 1,
                "operation_id": journal.operation_id,
                "plan_sha256": journal.plan_sha,
                "planned_execution_input_sha256": journal.admission()["binding"][
                    "execution_input_sha256"
                ],
                "native_input_sha256": input_sha,
                "source_copy": copied,
                "state_copy": copied_state,
            },
        )
        self.live(session, plan)
        self.program(
            session,
            journal,
            [
                self.gate.profile["tools"]["spectre"]["path"],
                work + "/input.scs",
                "-raw",
                work + "/psf",
                "+log",
                work + "/spectre.log",
                "-format",
                "psfbin",
            ],
            "spectre",
            180,
            amount,
        )
        self.protected(route, before)
        journal.append(
            session, "EXTRACTING", self.operations.digest(self.operations.canonical(effective))
        )
        reader_sha = self.operations.digest(self.operations.canonical(route["reader"]))
        reader = self.rendering.reader(
            self.gate.profile["paths"]["job_root"],
            plan["analysis"],
            route["reader"],
            journal.operation_id,
            journal.plan_sha,
            input_sha,
            reader_sha,
        )
        self.write(work + "/reader.ocn", reader)
        try:
            self.program(
                session,
                journal,
                [
                    ocean,
                    "-nograph",
                    "-nocdsinit",
                    "-log",
                    work + "/reader-cadence.log",
                    "-cdslib",
                    root + "/cds.lib",
                    "-restore",
                    work + "/reader.ocn",
                ],
                "reader",
                120,
                amount,
            )
            frame = self.installer.regular(work + "/generic-frame.txt")
            self.frame(frame, plan, route, input_sha)
            self.protected(route, before)
            logical, allocated, pre_receipt_fingerprint = self.size(root)
            io = self.gate.storage.PosixIO()
            work_fd = io.root(work)
            try:
                _, _, psf_fingerprint = self.gate.storage.tree(io, work_fd, "psf", [0])
            finally:
                os.close(work_fd)
            receipt = {
                "schema_version": 1,
                "operation_id": journal.operation_id,
                "plan_sha256": journal.plan_sha,
                "native_input_sha256": input_sha,
                "reader_registration_sha256": reader_sha,
                "reader_script_sha256": hashlib.sha256(reader).hexdigest(),
                "frame_sha256": hashlib.sha256(frame).hexdigest(),
                "psf_tree_fingerprint": psf_fingerprint,
                "pre_receipt_tree_fingerprint": pre_receipt_fingerprint,
                "logical_bytes": logical,
                "allocated_bytes": allocated,
                "originals_preserved": True,
            }
            self.gate.accounting.write_new(work + "/extraction-receipt.json", receipt)
            journal.append(
                session, "SUCCEEDED", self.operations.digest(self.operations.canonical(receipt))
            )
        except Exception:
            journal.append(
                session,
                "EXTRACTION_FAILED",
                self.operations.digest(
                    self.operations.canonical({"failure": "fixed_reader_failed"})
                ),
            )
            raise
