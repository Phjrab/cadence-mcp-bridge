"""Fixed extraction-only recovery; Python2.6, existing ledger, original read-only.

This module has no CLI, path/code input or simulation entry. Only the authenticated
dispatcher supplies its worker/gate. Every recovery is a separately reserved job.
"""

# mypy: ignore-errors
import os


class ExtractionRecovery(object):
    def __init__(self, eda):
        self.eda = eda
        self.gate, self.operations = eda.gate, eda.operations

    def source(self, plan, enforce=True):
        self.gate.read(plan)
        ref = plan["recovery"]
        op = self.operations.uuid(ref["original_operation_id"])
        # The source plan is retained admission data, never a caller-supplied plan.
        work = self.gate.root + "/" + self.gate.accounting.JOBS + "/" + op + "/work"
        admission = self.operations.read(work + "/operation/admission.json")
        original = self.operations.OperationJournal(
            self.gate.root, op, admission["plan"], self.gate.accounting
        )
        if original.plan_sha != ref["original_plan_sha256"] or "recovery" in original.plan:
            raise ValueError("native_recovery_original_identity")
        observed = original.observation()
        if observed is None or observed["progress"]["phase"] != "EXTRACTION_FAILED":
            raise ValueError("native_recovery_original_not_extraction_failed")
        if any(original.plan[key] != plan[key] for key in (
            "resource_domain_sha256", "ledger_ref", "environment_sha256", "design_sha256",
            "pdk_sha256", "analysis",
        )) or any(original.plan["request"][key] != plan["request"][key]
                  for key in ("schema_version", "design_id", "analysis_id", "values")):
            raise ValueError("native_recovery_original_scope")
        route = self.gate.route(plan)
        data = self.operations.read_bytes(work + "/input.scs")
        parameters = dict((v["cadence_binding"], self.eda.rendering.number_text(
            next(x["value"] for x in plan["request"]["values"]
                 if x["logical_id"] == v["logical_id"]))) for v in route["variables"])
        effective = self.eda.rendering.effective_input(
            data, parameters,
            [(m["path"], m["section"]) for m in route["ade"]["model_includes"]],
            route["ade"]["inputs"], route["ade"]["static_statements_sha256"],
        )
        retained = self.operations.read(work + "/effective-input.json")
        if retained["operation_id"] != op or retained["plan_sha256"] != original.plan_sha or (
            retained["native_input_sha256"] != effective["input_sha256"]
            or retained["planned_execution_input_sha256"]
            != original.admission()["binding"]["execution_input_sha256"]
        ):
            raise ValueError("native_recovery_effective_input")
        _, events = original.events()
        extracting = [event for event in events if event["phase"] == "EXTRACTING"]
        if len(extracting) != 1 or extracting[0]["evidence_sha256"] != self.operations.digest(
            self.operations.canonical(effective)
        ):
            raise ValueError("native_recovery_spectre_completion_evidence")
        io = self.gate.storage.PosixIO()
        fd = io.root(work)
        try:
            _, _, psf = self.gate.storage.tree(io, fd, "psf", [0])
        finally:
            os.close(fd)
        logical, allocated, metadata_tree = self.eda.size(original.job)
        # Authenticate retained payload contents as well as the descriptor-scanned
        # metadata. The fixed64MiB/4096-entry bound fails closed for larger sources.
        content = self.eda.copying.dependency_snapshot(original.job)
        tree = self.operations.digest(self.operations.canonical({
            "metadata_tree": metadata_tree, "content_tree": content["tree_sha256"],
        }))
        if self.eda.size(original.job) != (logical, allocated, metadata_tree):
            raise ValueError("native_recovery_original_drift")
        if max(logical, allocated) > original.plan["request"]["result_reservation_bytes"]:
            raise ValueError("native_recovery_original_capacity")
        if enforce and tree != ref["original_tree_fingerprint"]:
            raise ValueError("native_recovery_original_drift")
        if original.observation() != observed:
            raise ValueError("native_recovery_original_terminal_drift")
        return original, {
            "original_operation_id": op,
            "original_plan_sha256": original.plan_sha,
            "original_tree_fingerprint": tree,
            "original_terminal_sha256": observed["progress"]["provider_receipt_sha256"],
            "native_input_sha256": effective["input_sha256"],
            "psf_tree_fingerprint": psf,
        }

    def preflight(self, plan):
        self.source(plan)

    def result(self, journal, plan):
        original, before = self.source(plan)
        link = self.operations.read(journal.work + "/recovery-source.json")
        if link != before:
            raise ValueError("native_recovery_source_link_drift")
        value = self.eda.result(journal, plan, original.work)
        if self.source(plan)[1] != before:
            raise ValueError("native_recovery_original_drift")
        return value

    def run(self, session, journal, plan):
        if journal.operation_id == plan["recovery"]["original_operation_id"]:
            raise ValueError("native_recovery_identity_collision")
        self.eda.operation_id = journal.operation_id
        self.eda.live(session, plan)
        original, before = self.source(plan)
        route = self.gate.route(plan)
        protected = dict((key, self.eda.copying.snapshot(route[key]))
                         for key in ("source_cell", "source_state"))
        self.eda.protected(route, protected)
        amount = plan["request"]["result_reservation_bytes"]
        fragment = max(4096, os.statvfs(journal.job).f_frsize)
        limit = amount - (16384 + 8 * fragment)
        if limit <= 1048576:
            raise ValueError("native_recovery_capacity")
        reader_sha = self.operations.digest(self.operations.canonical(route["reader"]))
        reader = self.eda.rendering.reader(
            self.gate.profile["paths"]["job_root"], plan["analysis"], route["reader"],
            journal.operation_id, journal.plan_sha, before["native_input_sha256"], reader_sha,
            original.operation_id,
        )
        self.gate.accounting.write_new(journal.work + "/recovery-source.json", before)
        self.eda.write(journal.work + "/input.scs",
                       self.operations.read_bytes(original.work + "/input.scs"))
        self.eda.write(journal.work + "/reader.ocn", reader)
        journal.append(session, "EXTRACTING",
                       self.operations.digest(self.operations.canonical(before)))
        try:
            self.eda.program(session, journal, [
                self.gate.profile["tools"]["ocean"]["path"], "-nograph", "-nocdsinit",
                "-log", journal.work + "/reader-cadence.log", "-cdslib",
                original.job + "/cds.lib", "-restore", journal.work + "/reader.ocn",
            ], "reader", 120, limit)
            frame = self.operations.read_bytes(journal.work + "/generic-frame.txt")
            self.eda.frame(frame, plan, route, before["native_input_sha256"])
            self.eda.protected(route, protected)
            if self.source(plan)[1] != before:
                raise ValueError("native_recovery_original_drift")
            logical, allocated, tree = self.eda.size(journal.job)
            if max(logical, allocated) > limit:
                raise ValueError("native_recovery_capacity")
            receipt = {
                "schema_version": 1, "operation_id": journal.operation_id,
                "plan_sha256": journal.plan_sha,
                "native_input_sha256": before["native_input_sha256"],
                "reader_registration_sha256": reader_sha,
                "reader_script_sha256": self.operations.digest(reader),
                "frame_sha256": self.operations.digest(frame),
                "psf_tree_fingerprint": before["psf_tree_fingerprint"],
                "pre_receipt_tree_fingerprint": tree,
                "logical_bytes": logical, "allocated_bytes": allocated,
                "originals_preserved": True,
            }
            self.gate.accounting.write_new(journal.work + "/extraction-receipt.json", receipt)
            if max(self.eda.size(journal.job)[:2]) > amount - (8192 + 4 * fragment):
                raise ValueError("native_recovery_terminal_capacity")
            journal.append(session, "SUCCEEDED",
                           self.operations.digest(self.operations.canonical(receipt)))
        except Exception:
            journal.append(session, "EXTRACTION_FAILED", self.operations.digest(
                self.operations.canonical({"failure": "fixed_recovery_reader_failed"})))
            raise
