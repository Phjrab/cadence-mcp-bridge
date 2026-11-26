"""Run the single enrolled NM11 width edit and two detached HNL modes.

The v2 supervisor embeds the original v1 assets in an isolated module. The
unchanged supervisor still owns the exclusive phase journal, guarded process
and receipts for both paths. This module is also parsed by Python 2.6.
"""

# mypy: ignore-errors

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
import re
import types

V2_HOLDER = "/home/buet/cds_work/Ota17CandidateOutputs20261126_v2"
V1_HOLDER = "/home/buet/cds_work/Ota17CandidateOutputs20261126_v1"
V1_RUNTIME_SHA256 = "d25f179ad7f4f996b75623c3367391d425638a16c9f2eec90a48629a3a93bd4d"
V2_SKILL_SHA256 = "0614facc5c2e6779b60cc1659e6a52b1e51f7b67d4425c9cfd271bf3df3f144f"
V1_RUNTIME_ENTRY = b'if __name__ == "__main__":\n    ota_main()\n'
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MODES = (("ac", "MCP_GREL_Work"), ("dc", "MCP_GREL_WorkDc"))
_COMBINED_LIMIT_BYTES = 4194304
_WRITER_MAX_BYTES = 2621440
_WRITER_MIN_BYTES = 2097152
_V1_ARCHIVE_BYTES = 303104
_FIXED_PARAMETERS = {"VBIASN": "0.32", "VBIASP": "0.702"}
_DC_OP_STATEMENT = "dcOpInfo info what=oppoint where=rawfile"
_V1_FAILED_JOBS = (
    (
        "7d178cb4-8795-493f-b703-500d21216d09",
        65536,
        "e5aa98828a849d0354c7e57b6b109df0a3ce5e409bde6f8116f9b6a7336dbd59",
    ),
    (
        "1c699cf0-ee61-4bfd-8dd9-2afcb78cb592",
        69632,
        "03e445315281381e234740e3f72e6dfdad06641b0d151758b70f04a1cc2d81d6",
    ),
)


def _require(condition, stage):
    if not condition:
        raise ValueError("ota_candidate_v2_" + stage)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _selected_point(route, scope):
    target = route["target"]
    plan = scope["plan"]
    _require(
        route["baseline"]["revision"]["design_id"] == "ota17-baseline"
        and "recovered_source_sha256" in route["ota"]
        and target["netlist_path"] == "DUT/NM11"
        and target["netlist_terminals"] == ["out", "n_bias", "n_sink_stack", "VSS"]
        and plan["changed"] == ["w"]
        and plan["current"]
        == dict(w=dict(value="10000", unit="nm"), l=dict(value="250", unit="nm"), m=1)
        and plan["expected"]
        == dict(w=dict(value="1500", unit="nm"), l=dict(value="250", unit="nm"), m=1),
        "selected_point",
    )


def _verify_safety(pin, route, legacy, verify_base):
    """Use the closed v1 schema plus the sealed clean-copy/peak admission."""
    clean = pin.get("clean_child")
    _require(
        type(pin["schema_version"]) is int
        and pin["schema_version"] == 3
        and "clone_recovery" not in pin
        and pin["job_limit_bytes"] == _COMBINED_LIMIT_BYTES
        and pin["supplemental_bytes"] >= _V1_ARCHIVE_BYTES
        and type(clean) is dict
        and set(clean)
        == set(
            (
                "writer_limit_bytes",
                "protected_v1_library_sha256",
                "protected_v1_state_sha256",
            )
        )
        and type(clean["writer_limit_bytes"]) is int
        and _WRITER_MIN_BYTES <= clean["writer_limit_bytes"] <= _WRITER_MAX_BYTES
        and all(_DIGEST.match(clean[key]) for key in clean if key.endswith("_sha256")),
        "sealed_peak_safety",
    )
    base_pin = dict(pin, schema_version=2)
    del base_pin["clean_child"]
    verify_base(base_pin, route, legacy)


def verify_clean_safety(pin, route, legacy):
    """Use the same closed shape check in the typed host admission."""
    from cadence_mcp_bridge import _ota_mos_candidate_runtime as original

    _verify_safety(pin, route, legacy, original.verify_safety)


def _session_program(rendering, job, selected, operation, scope_sha, alias, mode, inputs):
    """Isolate the two stock renderings using only closed supervisor paths."""
    mode_root = selected + "/" + mode
    mode_sha = _sha((scope_sha + "|" + mode).encode("ascii"))
    program = rendering.netlist(job, "schematic", "state1", [], inputs, mode_sha, operation)
    replacements = (
        (selected + "/project", mode_root + "/project", 1),
        (selected + "/state-root", mode_root + "/state-root", 2),
        ("MCP_GREL_Work", alias, 4),
    )
    for before, after, count in replacements:
        old = ('"' + before + '"').encode("ascii")
        new = ('"' + after + '"').encode("ascii")
        _require(program.count(old) == count, "stock_netlist_session")
        program = program.replace(old, new)
    terminal = b"exit(0)\n"
    _require(program.endswith(terminal) and program.count(terminal) == 1, "stock_netlist_exit")
    closed = "OTA17_HNL_MODE_CLOSED|" + mode + "|" + mode_sha + "|" + operation
    return (
        program[: -len(terminal)] + ('printf("' + closed + '\\n")\n').encode("ascii"),
        ["MCP_GENERIC_ADE_NETLIST|" + mode_sha + "|" + operation, closed],
    )


def _check_shared_static(rendering, ac, dc):
    ac_static = rendering.partition_input(ac)[3]
    dc_static = rendering.partition_input(dc)[3]
    _require(dc_static.count(_DC_OP_STATEMENT) == 1, "paired_static_input")
    position = dc_static.index(_DC_OP_STATEMENT)
    _require(
        0 < position < len(dc_static) - 1
        and dc_static[position - 1].startswith("simulatorOptions options ")
        and dc_static[position + 1] == "modelParameter info what=models where=rawfile"
        and ac_static == dc_static[:position] + dc_static[position + 1 :],
        "paired_static_input",
    )


def _adapt_skill(v1, v2):
    return type(
        "OtaV2Skill",
        (object,),
        dict(
            compose_common=staticmethod(lambda common: v2.common_v2(v1.compose_common(common))),
            EDIT_BEGIN=v2.edit_begin(v1.EDIT_BEGIN),
            EDIT_CHECKS=v2.edit_checks(v1.EDIT_CHECKS),
            EDIT_END=v2.edit_end(v1.EDIT_END),
            REOPEN=v2.reopen(v1.REOPEN),
        ),
    )


class _CleanOtaJob(object):  # noqa: UP004 - Python 2.6 new-style class
    """Extend the qualified journal with a two-mode, one-process reopen."""

    def __init__(self, runtime, operator, request, digest):
        request = dict(request, skill=_adapt_skill(request["skill"], request["v2_skill"]))
        super(_CleanOtaJob, self).__init__(runtime, operator, request, digest)  # noqa: UP008
        _selected_point(self.route, self.scope)
        self.clean = self.pin["clean_child"]
        _require(self.owned == V2_HOLDER + "/" + self.library, "v2_owned_holder")
        _require(
            all(op not in (self.operation, self.copy_operation) for op, _, _ in _V1_FAILED_JOBS),
            "fresh_v2_operations",
        )
        (self.dc,) = [
            row
            for row in runtime.original_registration["routes"]
            if row["design_id"] == "ota17-baseline" and row["analysis"] == "dc"
        ]
        dc, ac = self.dc, self.analysis
        variables = ac["variables"]
        _require(
            dc["libraries"] == ac["libraries"]
            and dc["source_cell"] == ac["source_cell"]
            and dc["source_state"] == ac["source_state"]
            and dc["variables"] == variables
            and len(variables) == len(_FIXED_PARAMETERS)
            and dict((row["cadence_binding"], row["fixed_value"]) for row in variables)
            == _FIXED_PARAMETERS
            and all(row["mutation_policy"] == "fixed" and row["unit"] == "V" for row in variables)
            and all(
                dc["ade"][key] == ac["ade"][key]
                for key in (
                    "source_tree_sha256",
                    "ade_state_tree_sha256",
                    "model_includes",
                )
            )
            and set(dc["ade"]["inputs"]) == set(("analysis", "mode", "statement_sha256"))
            and dc["ade"]["inputs"]["analysis"] == "dc"
            and dc["ade"]["inputs"]["mode"] == "saved_operating_point"
            and _DIGEST.match(dc["ade"]["inputs"]["statement_sha256"]),
            "registered_dc",
        )

    def _source_guard(self):
        super(_CleanOtaJob, self)._source_guard()  # noqa: UP008
        self.rt.gate.model_binding(self.dc)
        copying = self.rt.copying
        _require(
            copying.dependency_snapshot(V1_HOLDER + "/" + self.library)["tree_sha256"]
            == self.clean["protected_v1_library_sha256"]
            and self.tree(V1_HOLDER + "/" + self.request["ota_base"].TB + "_ADE")
            == self.clean["protected_v1_state_sha256"]
            and sorted(os.listdir(V1_HOLDER))
            == sorted((self.library, self.request["ota_base"].TB + "_ADE"))
            and max(self.rt.eda.size(V1_HOLDER)[:2]) == _V1_ARCHIVE_BYTES,
            "protected_v1",
        )
        for op, charge, digest in _V1_FAILED_JOBS:
            logical, allocated, footprint = self.rt.eda.size(self.jobs + "/" + op)
            _require((max(logical, allocated), footprint) == (charge, digest), "failed_v1_job")

    def _capacity(self):
        total_writer_limit = super(_CleanOtaJob, self)._capacity()  # noqa: UP008
        writer_limit = min(total_writer_limit, self.clean["writer_limit_bytes"])
        if os.path.lexists(self.job):
            _require(max(self.rt.eda.size(self.job)[:2]) + 32768 <= writer_limit, "writer_capacity")
        return writer_limit

    def run(self, session, work, program, definitions, phase, markers):
        output = super(_CleanOtaJob, self).run(  # noqa: UP008
            session,
            work,
            program,
            definitions,
            phase,
            markers,
        )
        parse = self.request["v2_skill"].parse_writer_metadata
        if phase == "edit":
            parse(output, "EDIT_SAVED_META")
        else:
            prefixes = (b"MCP_GENERIC_ADE_NETLIST|", b"OTA17_HNL_MODE_CLOSED|")
            _require(
                [row for row in output.splitlines() if row.startswith(prefixes)]
                == [mark.encode("ascii") for mark in markers[1:]],
                "two_exact_mode_markers",
            )
            saved = self.h.read(self.job + "/edit/work/edit.stdout", 65536)
            _require(
                parse(output, "EDIT_REOPEN_META") == parse(saved, "EDIT_SAVED_META"),
                "reopened_bookkeeping",
            )
        return output

    def _phase_modes(self, selected, work, tb_path, tb, ade):
        rt = self.rt
        work_dirs, definitions, programs, markers = {}, [], [], []
        cell = self.values(work)["@NETLISTCELL@"]
        for mode, alias in _MODES:
            root = selected + "/" + mode
            project, library, state = root + "/project", root + "/library", root + "/state-root"
            bench, target = (
                library + "/" + cell,
                state + "/" + alias + "/" + cell + "/spectre/state1",
            )
            for path in (
                root,
                project,
                library,
                state,
                state + "/" + alias,
                state + "/" + alias + "/" + cell,
                os.path.dirname(target),
            ):
                rt.operations.directory(path, rt.accounting)
            rt.copying.copy_owned(tb_path, bench, tb["tree_sha256"])
            rt.copying.copy_owned(self.state, target, ade["tree_sha256"])
            if mode == "ac":
                self._remap_state(target, cell, project)
            else:
                self._remap_mode_state(target, (alias, cell, "schematic"), project)
            copied_bench = rt.copying.snapshot(bench)
            _require(copied_bench["content_sha256"] == tb["content_sha256"], "copied_bench")
            work_dirs[mode] = dict(
                bench=bench,
                project=project,
                state=target,
                bench_snapshot=copied_bench,
                state_snapshot=rt.copying.snapshot(target),
            )
            definitions.append((alias, library))
            registration = self.analysis if mode == "ac" else self.dc
            script, expected = _session_program(
                rt.modules["rendering"],
                self.job,
                selected,
                self.operation,
                self.digest,
                alias,
                mode,
                registration["ade"]["inputs"],
            )
            check = 'unless(ddGetObj("{0}")~>readPath=="{1}" exit(1))\n'.format(  # noqa: UP030,UP032
                alias,
                library,
            )
            programs.append(check.encode("ascii") + script)
            markers.extend(expected)
        lines = self.library_lines(definitions[0])
        alias, path = definitions[1]
        lines += "DEFINE {0} {1}\n".format(  # noqa: UP030,UP032
            rt.rendering.token(alias),
            rt.copying.path(path),
        ).encode("ascii")
        return work_dirs, lines, b"".join(programs) + b"exit(0)\n", markers

    def _remap_mode_state(self, target, design, project):
        rt, h = self.rt, self.h
        info = target + "/ADE_state.info"
        original = h.read(info, 65536)
        data = rt.copying.remap_ade_info(original, self.pin["source_ade_design"], design, project)
        origin = os.lstat(info)
        fd = os.open(info, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "wb") as stream:
            _require(
                h.identity(os.fstat(stream.fileno())) == h.identity(origin), "ade_info_identity"
            )
            stream.truncate(0)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        rt.copying.sync(target)
        _require(h.read(info, 65536) == data, "ade_info_readback")

    def _mode_output(self, mode, paths, work, output_sha, before, prior):
        rt, h = self.rt, self.h
        source = self.analysis if mode == "ac" else self.dc
        _require(
            rt.copying.snapshot(paths["state"]) == paths["state_snapshot"]
            and rt.copying.snapshot(paths["bench"]) == paths["bench_snapshot"],
            "isolated_mode_inputs",
        )
        rendering = rt.modules["rendering"]
        expected = [(row["path"], row["section"]) for row in source["ade"]["model_includes"]]
        input_path = rt.eda.find_input(paths["project"])
        _require(input_path.startswith(paths["project"] + "/"), "mode_input_location")
        raw = h.read(input_path, 32768, False)
        verified = rt.eda.normalize_model_includes(raw, expected, source["libraries"])
        _, _, _, static = rendering.partition_input(verified)
        # The phase compares the two static parts, then the typed host checks
        # the candidate projection against the original baseline.
        rendering.effective_input(
            verified,
            _FIXED_PARAMETERS,
            expected,
            source["ade"]["inputs"],
            rendering.static_fingerprint(static),
        )
        rt.eda.write(work + "/effective-input-" + mode + ".scs", raw)
        return raw, dict(
            analysis=mode,
            operation_id=self.operation,
            scope_sha256=self.digest,
            saved_receipt_sha256=prior,
            dut_revision_sha256=before["dut"],
            testbench_revision_sha256=before["tb"],
            state_path=paths["state"],
            project_path=paths["project"],
            input_path=input_path,
            enabled_analyses=[mode],
            netlisted=True,
            isolated_bench_tree_sha256=paths["bench_snapshot"]["tree_sha256"],
            isolated_state_tree_sha256=paths["state_snapshot"]["tree_sha256"],
            project_tree_sha256=rt.copying.dependency_snapshot(paths["project"])["tree_sha256"],
            registered_inputs_sha256=self.digest_doc(source["ade"]["inputs"]),
            hnl_stdout_sha256=output_sha,
            netlist_sha256=_sha(raw),
        )

    def reopen(self, session, selected, work, before, saved):
        rt, h, legacy, skill = self.rt, self.h, self.legacy, self.request["skill"]
        tb_path = self.owned + "/" + self.request["ota_base"].TB
        tb, ade = rt.copying.snapshot(tb_path), rt.copying.snapshot(self.state)
        _require(ade["tree_sha256"] == self.pin["source_ade_tree_sha256"], "source_ade")
        rt.eda.copy_capacity(
            dict(ac_tb=tb, ac_ade=ade, dc_tb=tb, dc_ade=ade), self.job, self.guard(session)
        )
        mode_dirs, definitions, netlists, markers = self._phase_modes(
            selected, work, tb_path, tb, ade
        )
        collector = self.collector.decode("ascii")
        needle = 'outfile("cdf-frame.txt")'
        _require(collector.count(needle) == 1, "cdf_output")
        script = (
            skill.compose_common(legacy.COMMON)
            + collector.replace(needle, 'outfile("@WORK@/cdf-frame.txt")')
            + skill.REOPEN
        )
        program = self.request["ota_base"].render_ota_skill(script, self.values(work)) + netlists
        output = self.run(
            session,
            work,
            program,
            definitions,
            "reopen",
            ["C6_MOS_READ_ONLY_CLOSED|" + self.operation] + markers,
        )
        _require(
            self.views(self.owned) == before
            and rt.copying.snapshot(tb_path) == tb
            and rt.copying.snapshot(self.state) == ade,
            "reopened_revision",
        )
        reopened = self.snapshot(work, "reopened", before, "after")
        _require(
            reopened["footprint_sha256"] == saved["saved"]["footprint_sha256"]
            and reopened["properties"] == saved["saved"]["properties"],
            "reopened_footprint",
        )
        cdf = h.read(work + "/cdf-frame.txt", 65536)
        _require(cdf.startswith(b"M2_CDF_V2\n") and cdf.endswith(b"COMPLETE\n"), "cdf_frame")
        prior = self.request["prior"]
        ac_raw, ac_leaf = self._mode_output(
            "ac", mode_dirs["ac"], selected, _sha(output), before, prior
        )
        dc_raw, dc_leaf = self._mode_output(
            "dc", mode_dirs["dc"], selected, _sha(output), before, prior
        )
        _require(ac_leaf["netlist_sha256"] != dc_leaf["netlist_sha256"], "distinct_raw_inputs")
        _check_shared_static(rt.modules["rendering"], ac_raw, dc_raw)
        receipt = dict(
            saved,
            reopened=reopened,
            netlisted_revision_sha256=before["dut"],
            netlisted_testbench_revision_sha256=before["tb"],
            netlist_sha256=_sha(ac_raw),
            cdf_frame_sha256=_sha(cdf),
        )
        receipt["netlist_receipt_sha256"] = self.digest_doc(receipt)
        paired = dict(
            schema_version=1,
            ocean_invocations=1,
            spectre=0,
            reservations=0,
            ac=ac_leaf,
            dc=dc_leaf,
        )
        retained = dict(readback=receipt, diagnostics=paired)
        return retained, dict(
            readback=receipt,
            diagnostics=paired,
            input_base64=base64.b64encode(ac_raw).decode("ascii"),
            dc_input_base64=base64.b64encode(dc_raw).decode("ascii"),
            cdf_frame_base64=base64.b64encode(cdf).decode("ascii"),
        )


def _load_base(raw, legacy_source, skill_source, v2_skill_source):
    """Load the pinned original in this supervisor process only."""
    _require(
        type(raw) is bytes
        and 0 < len(raw) <= 65536
        and _sha(raw) == V1_RUNTIME_SHA256
        and raw.endswith(V1_RUNTIME_ENTRY),
        "v1_program",
    )
    _require(
        type(v2_skill_source) is bytes
        and 0 < len(v2_skill_source) <= 32768
        and _sha(v2_skill_source) == V2_SKILL_SHA256,
        "v2_skill",
    )
    module = types.ModuleType("ota_candidate_pinned_v1")
    eval(compile(raw, module.__name__ + ".py", "exec"), module.__dict__)
    module.OTA_LEGACY_SOURCE = legacy_source
    module.OTA_SKILL_SOURCE = skill_source
    skill = module._module("ota_candidate_pinned_v2_skill", v2_skill_source)
    verify_base = module.verify_safety
    module.CHILD_PATH = V2_HOLDER + "/" + module.CHILD
    module.CHILD_STATE = V2_HOLDER + "/" + module.TB + "_ADE"

    def verify_safety(pin, route, legacy):
        _verify_safety(pin, route, legacy, verify_base)

    def new_job(runtime, operator, request, digest):
        class Job(_CleanOtaJob, module._OtaJob, request["legacy"].Source9MosJob):
            pass

        return Job(runtime, operator, dict(request, ota_base=module, v2_skill=skill), digest)

    module.verify_safety = verify_safety
    module.new_job = new_job
    return module


def ota_v2_main():
    base = _load_base(
        globals().get("OTA_V1_RUNTIME_SOURCE"),
        globals().get("OTA_LEGACY_SOURCE"),
        globals().get("OTA_SKILL_SOURCE"),
        globals().get("OTA_V2_SKILL_SOURCE"),
    )
    base.ota_main()


if __name__ == "__main__":
    ota_v2_main()
