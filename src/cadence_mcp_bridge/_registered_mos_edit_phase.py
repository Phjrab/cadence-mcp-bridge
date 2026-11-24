"""Fixed Source9 PMOS default restore and independent readback/Netlist (Python 2.6)."""

# mypy: ignore-errors
# ruff: noqa: B905, UP004, UP010, UP030, UP031, UP032

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

SUPPORT_SHA256 = "71de4c49873c8c40b04c6482432390daa7a6aa4ef9092d2a762f4657a9d68d61"
CDF_SHA256 = "2563fca0a14f557317e69ec31a326642ee00c4f1dfd7af29ee08683542a25372"
SOURCE_NETLIST = "5d4134980c80d6cff72e6c1adb0d5957e7871c7b52fa89d5482dfedf113c7f0a"
SOURCE = "CmosLong20261111"
DUT, TB = "InvLong", "InvLongTb"
PHASES = ("EDIT_SAVE", "INDEPENDENT_REOPEN_NETLIST")
CONFIRMATIONS = "registered-mos-confirmations"
LIMIT = 524288
OVERRIDES = ("w", "fw", "as", "ad", "ps", "pd")
PROPERTIES = ("w", "fw", "l", "m", "fingers", "as", "ad", "ps", "pd", "nf", "model", "dfm")
ROWS = (
    ("w", "lengthMetric", "350n", "120n"),
    ("fw", "lengthMetric", "350n", "120n"),
    ("l", "lengthMetric", "100n", "100n"),
    ("m", None, "1", "1"),
    ("fingers", None, "1", "1"),
    ("as", None, "98f", "69.6f"),
    ("ad", None, "98f", "69.6f"),
    ("ps", "lengthMetric", "1.26u", "1.16u"),
    ("pd", "lengthMetric", "1.26u", "1.16u"),
    ("model", None, "gpdk090_pmos1v", "gpdk090_pmos1v"),
)
SAFETY_FIELDS = (
    "schema_version",
    "layout_manifest_sha256",
    "layout_worker_sha256",
    "copy_receipt_sha256",
    "source_library_tree_sha256",
    "source_dut_tree_sha256",
    "source_symbol_tree_sha256",
    "source_tb_tree_sha256",
    "source_ade_tree_sha256",
    "original_protected_sha256",
    "owned_library_tree_sha256",
    "owned_symbol_tree_sha256",
    "ledger_sha256",
    "policy_sha256",
    "retained_jobs_sha256",
    "supplemental_bytes",
    "job_limit_bytes",
)

COMMON = r"""
procedure(mosRequire(ok) unless(ok error("C6_MOS_QUALIFICATION")) ok)
procedure(mosByName(a b) alphalessp(car(a) car(b)))
procedure(mosOpen(lib cell mode)
 let((cv)
  cv=dbOpenCellViewByType(lib cell "schematic" "" mode)
  mosRequire(and(cv cv~>libName==lib cv~>cellName==cell
                 cv~>viewName=="schematic" cv~>mode==mode)) cv))
procedure(mosTarget(cv)
 let((matches inst)
  matches=setof(item cv~>instances item~>name=="MP")
  mosRequire(length(matches)==1)
  inst=car(matches)
  mosRequire(and(inst~>libName=="gpdk090" inst~>cellName=="pmos1v" inst~>viewName=="symbol"))
  mosRequire(equal(mosLinks(inst~>instTerms)
     list(list("B" "vdd") list("D" "vout") list("G" "vin") list("S" "vdd"))))
  inst))
procedure(mosLinks(terms)
 sort(foreach(mapcar term terms
      list(term~>name if(term~>net then term~>net~>name else nil))) 'mosByName))
procedure(mosTb(lib)
 let((cv targets inst)
  cv=mosOpen(lib "InvLongTb" "r")
  targets=setof(item cv~>instances item~>name=="DUT")
  mosRequire(and(length(cv~>instances)==4 length(targets)==1))
  inst=car(targets)
  mosRequire(and(inst~>libName==lib inst~>cellName=="InvLong"
                 inst~>viewName=="symbol" length(inst~>instTerms)==4))
  mosRequire(dbClose(cv))))
procedure(mosEncode(value depth)
 let((encoded item)
  mosRequire(depth<=24)
  cond((null(value) "N")
       (listp(value)
        mosRequire(length(value)<=512)
        encoded=sprintf(nil "L%d:" length(value))
        foreach(memberValue value
          item=mosEncode(memberValue depth+1)
          encoded=strcat(encoded sprintf(nil "%d:" strlen(item)) item)) encoded)
       (fixp(value) sprintf(nil "I%d" value))
       (floatp(value) sprintf(nil "D%.17g" value))
       (stringp(value) strcat("S" value))
       (symbolp(value) sprintf(nil "Y%L" value))
       (t error("C6_MOS_UNSUPPORTED_FOOTPRINT")))))
procedure(mosProps(owner omit)
 mosRequire(length(owner~>prop)<=100)
 sort(foreach(mapcar p setof(item owner~>prop !member(item~>name omit))
      list(p~>name p~>valueType p~>value)) 'mosByName))
procedure(mosFoot(cv omit)
 let((rows figures)
  mosRequire(and(length(cv~>instances)<=8 length(cv~>terminals)<=8 length(cv~>nets)<=32
                 length(cv~>shapes)<=128))
  rows=foreach(mapcar inst cv~>instances
   list(inst~>name inst~>libName inst~>cellName inst~>viewName inst~>orient inst~>xy
        mosLinks(inst~>instTerms) mosProps(inst if(inst~>name=="MP" then omit else nil))))
  figures=foreach(mapcar shape cv~>shapes
   mosEncode(list(shape~>objType shape~>layerName shape~>purpose shape~>bBox
    if(member(shape~>objType list("line" "polygon" "path")) then shape~>points else nil)
    if(shape~>objType=="label" then shape~>theLabel else nil)
    if(shape~>net then shape~>net~>name else nil) mosProps(shape nil)) 0))
  mosEncode(list(sort(rows 'mosByName)
   sort(foreach(mapcar term cv~>terminals list(term~>name term~>direction
     if(term~>net then term~>net~>name else nil))) 'mosByName)
   sort(foreach(mapcar net cv~>nets net~>name) 'alphalessp)
   sort(figures 'alphalessp)) 0)))
procedure(mosTuple(path inst)
 let((port cdf prop param)
  cdf=cdfGetInstCDF(inst)
  mosRequire(cdf)
  port=outfile(path)
  mosRequire(port)
  foreach(key '("w" "fw" "l" "m" "fingers" "as" "ad" "ps" "pd" "nf" "model" "dfm")
   prop=dbFindProp(inst key)
   param=cdfFindParamByName(cdf key)
   when(prop mosRequire(and(stringp(prop~>valueType) stringp(prop~>value))))
   when(param mosRequire(and(stringp(param~>type) stringp(param~>value)
                             (null(param~>units) || stringp(param~>units)))))
   fprintf(port "%s|%L|%L|%L|%L|%L\n" key
     if(prop then prop~>valueType else nil) if(prop then prop~>value else nil)
     if(param then param~>type else nil) if(param then param~>units else nil)
     if(param then param~>value else nil)))
  fprintf(port "COMPLETE\n")
  mosRequire(close(port))))
procedure(mosText(path text)
 let((port)
  port=outfile(path) mosRequire(port)
  fprintf(port "%s\n" text) mosRequire(close(port))))
"""

EDIT = r"""
procedure(mosEdit()
 let((source child inst original stable omit expected)
  mosRequire(and(ddGetObj("@LIB@")~>readPath=="@OWNED@"
                 ddGetObj("CmosLong20261111")~>readPath=="@SOURCE@"))
  mosTb("@LIB@")
  omit='("w" "fw" "as" "ad" "ps" "pd")
  source=mosOpen("CmosLong20261111" "InvLong" "r")
  child=mosOpen("@LIB@" "InvLong" "r")
  inst=mosTarget(child)
  mosRequire(dbIsConnCurrent(child))
  original=mosFoot(source nil)
  mosRequire(equal(original mosFoot(child nil)))
  mosRequire(dbClose(source))
  stable=mosFoot(child omit)
  mosTuple("@WORK@/baseline.properties" inst)
  mosRequire(dbClose(child))
  child=mosOpen("@LIB@" "InvLong" "a")
  mosRequire(equal(original mosFoot(child nil)))
  inst=mosTarget(child)
  expected=cdfGetInstCDF(inst)
  foreach(row '(("w" "350n" "120n") ("fw" "350n" "120n") ("as" "98f" "69.6f")
                ("ad" "98f" "69.6f") ("ps" "1.26u" "1.16u") ("pd" "1.26u" "1.16u"))
   let((prop param)
    prop=dbFindProp(inst car(row))
    param=cdfFindParamByName(expected car(row))
    mosRequire(and(prop prop~>valueType=="string" prop~>value==cadr(row)
      param param~>value==cadr(row) param~>defValue==caddr(row)))))
  @BEFORE@
  foreach(key omit
   dbDeletePropByName(inst key)
   mosRequire(!dbFindProp(inst key)))
  mosRequire(and(schCheck(child) equal(stable mosFoot(child omit))))
  @AFTER@
  mosTuple("@WORK@/saved.properties" inst)
  mosText("@WORK@/footprint.txt" stable)
  mosRequire(and(dbSave(child) dbClose(child)))
  printf("C6_MOS_EDIT_SAVED|@OP@\n")
  drain(poport) t))
if(errset(mosEdit() t) then exit(0) else exit(1))
"""

REOPEN = r"""
procedure(mosReopen()
 let((child inst copied)
  mosRequire(ddGetObj("@LIB@")~>readPath=="@OWNED@")
  mosTb("@LIB@")
  child=mosOpen("@LIB@" "InvLong" "r")
  inst=mosTarget(child)
  mosRequire(dbIsConnCurrent(child))
  @AFTER@
  mosTuple("@WORK@/reopened.properties" inst)
  mosText("@WORK@/footprint.txt" mosFoot(child '("w" "fw" "as" "ad" "ps" "pd")))
  mosRequire(m2ReopenedMosFrame(inst))
  mosRequire(dbClose(child))
  copied=mosOpen("MCP_GREL_Work" "@NETLISTCELL@" "r")
  mosRequire(length(setof(dut copied~>instances and(dut~>name=="DUT" dut~>libName=="@LIB@"
             dut~>cellName=="InvLong" dut~>viewName=="symbol")))==1)
  mosRequire(dbClose(copied))
  printf("C6_MOS_READ_ONLY_CLOSED|@OP@\n")
  drain(poport) t))
unless(errset(mosReopen() t) exit(1))
"""


def require(condition, stage):
    if not condition:
        raise ValueError("registered_mos_" + stage)


def read_encoded(packet, name, limit):
    token = packet[name + "_base64"].encode("ascii")
    require(0 < len(token) <= 4 * ((limit + 2) // 3), "base64_limit")
    raw = base64.b64decode(token)
    require(0 < len(raw) <= limit and base64.b64encode(raw) == token, "base64")
    return raw


def read_properties(raw):
    lines = raw.decode("ascii").splitlines()
    require(len(lines) == len(PROPERTIES) + 1 and lines[-1] == "COMPLETE", "property_frame")
    result = {}
    fields = ("oa_type", "oa_value", "cdf_type", "cdf_units", "cdf_value")
    for name, text in zip(PROPERTIES, lines[:-1]):
        cells = text.split("|")
        require(len(cells) == 6 and cells[0] == name, "property_name")
        values = []
        for token in cells[1:]:
            require(
                token == "nil" or re.match(r'^"[A-Za-z0-9_. +-]{1,128}"\Z', token), "property_value"
            )
            values.append(None if token == "nil" else token[1:-1])
        result[name] = dict(zip(fields, values))
    return result


def exact_route(scope):
    route = scope["route_qualification"]
    q = route["qualification"]
    plan, target = scope["plan"], q["target"]
    subject = scope["subject"]
    scalar = dict(unit="nm", value="120")
    require(
        target["instance"]
        == dict(
            instance_path="DUT/MP",
            master_library="gpdk090",
            master_cell="pmos1v",
            master_view="symbol",
            property_name="w",
        )
        and (
            target["quantity"],
            target["scalar_option"],
            target["scalar_unit"],
            target["netlist_path"],
            target["netlist_model"],
            target["netlist_terminals"],
        )
        == ("length", "w", "nm", "DUT/MP", "gpdk090_pmos1v", ["vout", "vin", "vdd", "vdd"])
        and q["old"] == dict(unit="nm", value="350")
        and q["expected"] == scalar
        and plan["old"] == q["old"]
        and plan["requested"] == plan["expected"] == scalar
        and plan["target"] == target
        and plan["baseline"] == q["baseline"]
        and q["baseline"]["netlist_sha256"] == SOURCE_NETLIST
        and (q["baseline"]["revision"]["design_id"], q["baseline"]["revision"]["revision_id"])
        == ("cmos-long-inverter", "long-r1")
        and subject["owned_cell"] == DUT
        and subject["owned_view"] == "schematic"
        and re.match(r"^CmosLongMos[A-Za-z0-9]{3,40}\Z", subject["owned_library"]),
        "exact_source9_route",
    )
    for before, name in ((True, "before"), (False, "after")):
        props = route[name]
        require(set(props) == set(PROPERTIES), "enrollment_properties")
        for key, units, old, new in ROWS:
            explicit = before or key not in OVERRIDES
            row = props[key]
            val = old if before else new
            require(
                row
                == dict(
                    oa_type="string" if explicit else None,
                    oa_value=val if explicit else None,
                    cdf_type="instData",
                    cdf_units=units,
                    cdf_value=val,
                ),
                "source9_tuple",
            )
        require(all(val is None for val in props["nf"].values()), "source9_nf")
    require(route["before"]["dfm"] == route["after"]["dfm"], "source9_dfm")
    return route


def skill_check(rows):
    def token(value):
        if value is None:
            return "nil"
        require(re.match(r"^[A-Za-z0-9_. +-]{1,128}\Z", value), "skill_tuple_literal")
        return '"' + value + '"'

    result = []
    for key in PROPERTIES:
        row = rows[key]
        result.append(
            "("
            + " ".join(
                token(value)
                for value in (
                    key,
                    row["oa_type"],
                    row["oa_value"],
                    row["cdf_type"],
                    row["cdf_units"],
                    row["cdf_value"],
                )
            )
            + ")"
        )
    return (
        "foreach(row '(" + " ".join(result) + ")\n"
        " let((prop param)\n"
        "  prop=dbFindProp(inst car(row)) param=cdfFindParamByName(cdfGetInstCDF(inst) car(row))\n"
        "  mosRequire(equal(list(if(prop then prop~>valueType else nil)\n"
        "     if(prop then prop~>value else nil)\n"
        "     if(param then param~>type else nil) if(param then param~>units else nil)\n"
        "     if(param then param~>value else nil)) cdr(row)))))"
    )


def render(template, values):
    names = set(re.findall(r"@[A-Z]+@", template))
    require(names.issubset(values), "fixed_template")
    return re.sub(r"@[A-Z]+@", lambda match: values[match.group(0)], template).encode("ascii")


class Source9MosJob(object):
    def __init__(self, rt, helper, operator, scope, pin, digest, approval, collector):
        self.rt, self.h, self.scope, self.pin, self.digest = rt, helper, scope, pin, digest
        self.operator, self.approval, self.collector = operator, approval, collector
        self.subject = scope["subject"]
        self.route = exact_route(scope)
        self.operation = self.subject["operation_id"]
        copy_id = self.subject["owned_copy_operation_id"]
        require(
            helper.job_id(self.operation) and helper.job_id(copy_id) and self.operation != copy_id,
            "operation_identity",
        )
        self.library = self.subject["owned_library"]
        self.jobs = rt.root + "/" + rt.accounting.JOBS
        self.job, self.copy = self.jobs + "/" + self.operation, self.jobs + "/" + copy_id
        self.owned = self.copy + "/" + self.library
        self.source = rt.root + "/layout-owned-20261111/" + SOURCE
        self.confirmations = rt.root + "/" + CONFIRMATIONS
        self.copy_claim = self.copy + "/registered-mos-edit-intent.json"
        self.limit = pin["job_limit_bytes"]
        (self.analysis,) = [
            row
            for row in rt.original_registration["routes"]
            if row["design_id"] == "m2-owned-inverter" and row["analysis"] == "dc"
        ]
        self.state = self.analysis["source_state"]
        require(self.analysis["ade"]["inputs"]["mode"] == "saved_operating_point", "registered_dc")
        require(
            type(self.limit) is int
            and 1048576 <= self.limit <= 3145728
            and type(pin["supplemental_bytes"]) is int
            and 0 <= pin["supplemental_bytes"] <= 33554432,
            "finite_capacity",
        )

    def digest_doc(self, value):
        return self.h.sha(self.h.canonical(value))

    def tree(self, path):
        return self.rt.copying.snapshot(path)["tree_sha256"]

    def views(self, library):
        return dict(
            dut=self.tree(library + "/" + DUT + "/schematic"),
            symbol=self.tree(library + "/" + DUT + "/symbol"),
            tb=self.tree(library + "/" + TB + "/schematic"),
        )

    def guard(self, session):
        rt, h, p = self.rt, self.h, self.pin
        session.check()
        require(time.time() < self.scope["valid_until_unix"], "approval_expired")
        rt.read_check({})
        require(not rt.gate.storage.active_eda(rt.root, True), "eda_busy")
        rt.copying.owned_parent(self.copy)
        rt.copying.owned_parent(self.owned)
        rt.copying.owned_parent(self.confirmations)
        require(
            h.read(self.confirmations + "/" + self.digest + ".json", 4096) == self.approval,
            "native_approval",
        )
        copy_receipt = h.parse(
            h.pinned(
                h.read(self.copy + "/registered-mos-copy-receipt.json", 4096),
                p["copy_receipt_sha256"],
            )
        )
        require(
            copy_receipt
            == dict(
                status="VERIFIED_OWNED_COPY",
                operation_id=self.subject["owned_copy_operation_id"],
                source_library_tree_sha256=p["source_library_tree_sha256"],
                owned_library=self.library,
                owned_library_tree_sha256=p["owned_library_tree_sha256"],
                dut=self.subject["owned_before_view_tree_sha256"],
                symbol=p["owned_symbol_tree_sha256"],
                tb=self.subject["owned_before_testbench_tree_sha256"],
            ),
            "copy_custody",
        )
        rt.gate.library_binding({"libraries": rt.registration["libraries"]})
        rt.gate.model_binding(self.analysis)
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
            "originals",
        )
        domain, binding, user, uid = rt.modules["confirmation"].domain(
            rt.profile, rt.manifest["identity_manifest_sha256"]
        )
        require(
            (domain, user, uid) == (rt.root, self.operator.pw_name, self.operator.pw_uid),
            "operator",
        )
        counter, records = rt.accounting.state(rt.root, binding)
        ledger = rt.operations.read_bytes(rt.root + "/" + rt.accounting.LEDGER)
        require(h.sha(ledger) == p["ledger_sha256"], "ledger")
        names = sorted(
            name
            for name in os.listdir(self.jobs)
            if name not in (self.operation, self.subject["owned_copy_operation_id"])
        )
        require(len(names) <= 4096, "job_inventory_bound")
        retained = [(name, rt.eda.size(self.jobs + "/" + name)) for name in names]
        require(self.digest_doc(retained) == p["retained_jobs_sha256"], "retained_jobs")
        identity = rt.accounting.identity_manifest(rt.root, binding)
        policy = rt.accounting.effective_policy(rt.root, identity)
        require(self.digest_doc(policy) == p["policy_sha256"], "policy")
        copies = max(rt.eda.size(self.copy)[:2])
        writer = max(rt.eda.size(self.job)[:2]) if os.path.lexists(self.job) else 0
        require(copies + writer < self.limit, "owned_job_capacity")
        remaining = self.limit - copies - writer
        layout = rt.layout_retained_bytes()
        ceiling = policy["result_ceiling_bytes"]
        occupancy = max(rt.gate.occupancy()) + layout + p["supplemental_bytes"]
        reserved = counter["result_reserved_bytes"] + layout + p["supplemental_bytes"]
        reserved_ids = set(identity.get("legacy_operation_ids", []))
        reserved_ids.update(intent["operation_id"] for intent, _ in records)
        unreserved = sum(max(size[:2]) for name, size in retained if name not in reserved_ids)
        require(
            occupancy + remaining <= ceiling and reserved + unreserved + self.limit <= ceiling,
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
        session.check()
        # Leave room for bounded final retained receipts outside the EDA child.
        require(self.limit - copies - 32768 > writer, "receipt_capacity")
        return self.limit - copies - 32768

    def save_document(self, path, doc):
        raw = self.h.canonical(doc)
        self.rt.eda.write(path, raw)
        require(self.h.read(path, LIMIT) == raw, "durable_record")
        return self.h.sha(raw)

    def library_lines(self, extra):
        rt = self.rt
        libs = [(row["name"], row["path"]) for row in rt.registration["libraries"]]
        require(
            len(libs) == 6
            and not set((SOURCE, self.library, "MCP_GREL_Work")).intersection(
                name for name, _ in libs
            ),
            "fixed_libraries",
        )
        libs.append((self.library, self.owned))
        libs.append(extra)
        return "".join(
            "DEFINE %s %s\n" % (rt.rendering.token(name), rt.copying.path(path))
            for name, path in libs
        ).encode("ascii")

    def run(self, session, work, program, definitions, phase, markers):
        rt = self.rt
        rt.eda.write(work + "/cds.lib", definitions)
        rt.eda.write(work + "/fixed.ocn", program)
        limit = self.guard(session)
        tool = rt.profile["tools"]["ocean"]
        require(
            rt.modules["probe"].digest_file(os.path.realpath(tool["path"])) == tool["sha256"],
            "ocean_identity",
        )
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
        journal = type("RegisteredMosEditJob", (object,), dict(job=self.job, work=work))()
        rt.eda.program(session, journal, argv, phase, 45, limit)
        require(not self.h.read(work + "/" + phase + ".stderr", 32768), "ocean_stderr")
        output = self.h.read(work + "/" + phase + ".stdout", 65536).splitlines()
        require(
            all(output.count(mark.encode("ascii")) == 1 for mark in markers), "ocean_phase_markers"
        )
        if len(markers) == 2:
            require(
                output.index(markers[0].encode("ascii")) < output.index(markers[1].encode("ascii")),
                "ocean_phase_order",
            )

    def values(self, work):
        return {
            "@LIB@": self.library,
            "@OWNED@": self.owned,
            "@SOURCE@": self.source,
            "@WORK@": work,
            "@OP@": self.operation,
            "@BEFORE@": skill_check(self.route["before"]),
            "@AFTER@": skill_check(self.route["after"]),
            "@NETLISTCELL@": "Grel_" + self.operation.replace("-", "_"),
        }

    def snapshot(self, work, stage, views, expected):
        raw = self.h.read(work + "/" + stage + ".properties", 8192)
        result = dict(
            stage=stage,
            revision_sha256=views["dut"],
            testbench_revision_sha256=views["tb"],
            footprint_sha256=self.h.sha(self.h.read(work + "/footprint.txt", 65536)),
            properties=read_properties(raw),
        )
        require(result["properties"] == self.route[expected], "physical_property_readback")
        result["receipt_sha256"] = self.digest_doc(result)
        return result

    def outside_dut(self):
        return [
            row
            for row in self.rt.copying.snapshot(self.owned)["metadata"]
            if row[1] not in ("", DUT, DUT + "/schematic")
            and not row[1].startswith(DUT + "/schematic/")
        ]

    def phase(self, session, phase, prior):
        self.guard(session)
        rt, h = self.rt, self.h
        before = self.views(self.owned)
        if phase == PHASES[0]:
            require(
                prior is None
                and not os.path.lexists(self.job)
                and not os.path.lexists(self.copy_claim)
                and self.tree(self.owned) == self.pin["owned_library_tree_sha256"]
                and before
                == dict(
                    dut=self.subject["owned_before_view_tree_sha256"],
                    symbol=self.pin["owned_symbol_tree_sha256"],
                    tb=self.subject["owned_before_testbench_tree_sha256"],
                ),
                "fresh_owned_revision",
            )
            self.save_document(
                self.copy_claim,
                dict(operation_id=self.operation, scope_sha256=self.digest, retry=False),
            )
            rt.operations.directory(self.job, rt.accounting)
            selected = self.job + "/edit"
        else:
            edit = self.job + "/edit"
            saved = h.parse(h.pinned(h.read(edit + "/receipt.json", 16384), prior))
            require(
                h.parse(h.read(edit + "/complete.json", 4096)) == dict(receipt_sha256=prior)
                and not os.path.lexists(edit + "/failure.json")
                and h.parse(h.read(self.copy_claim, 4096))
                == dict(operation_id=self.operation, scope_sha256=self.digest, retry=False)
                and before["dut"] == saved["saved"]["revision_sha256"]
                and before["tb"] == saved["saved"]["testbench_revision_sha256"]
                and before["symbol"] == self.pin["owned_symbol_tree_sha256"],
                "saved_phase_binding",
            )
            selected = self.job + "/" + self.operation
        outside = self.outside_dut()
        rt.operations.directory(selected, rt.accounting)
        self.save_document(
            selected + "/intent.json", dict(phase=phase, previous_receipt_sha256=prior, retry=False)
        )
        work = selected + "/work"
        rt.operations.directory(work, rt.accounting)
        try:
            if phase == PHASES[0]:
                receipt = self.edit(session, work, before)
                result = receipt
            else:
                receipt, result = self.reopen(session, selected, work, before, saved)
            require(outside == self.outside_dut(), "non_target_owned_tree")
            self.guard(session)
            digest = self.save_document(selected + "/receipt.json", receipt)
            self.guard(session)
            self.save_document(selected + "/complete.json", dict(receipt_sha256=digest))
            return result
        except Exception as exc:
            self.save_document(
                selected + "/failure.json",
                dict(
                    status="OUTCOME_UNKNOWN",
                    phase=phase,
                    error_type=type(exc).__name__,
                    operation_id=self.operation,
                ),
            )
            raise

    def edit(self, session, work, before):
        program = render(COMMON + EDIT, self.values(work))
        self.run(
            session,
            work,
            program,
            self.library_lines((SOURCE, self.source)),
            "edit",
            ["C6_MOS_EDIT_SAVED|" + self.operation],
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

    def reopen(self, session, selected, work, before, saved):
        rt, h = self.rt, self.h
        tb = rt.copying.snapshot(self.owned + "/" + TB)
        ade = rt.copying.snapshot(self.state)
        require(ade["tree_sha256"] == self.pin["source_ade_tree_sha256"], "source_ade")
        rt.eda.copy_capacity({"testbench": tb, "state": ade}, self.job, self.guard(session))
        cell = self.values(work)["@NETLISTCELL@"]
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
        rt.copying.copy_owned(self.owned + "/" + TB, library + "/" + cell, tb["tree_sha256"])
        rt.copying.copy_owned(self.state, target, ade["tree_sha256"])
        info = target + "/ADE_state.info"
        original = h.read(info, 65536)
        data = rt.copying.remap_ade_info(
            original,
            ("M2Owned_SourceV3", "Owned_Inverter_TB", "schematic"),
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
        frozen = rt.copying.snapshot(target)
        collector = self.collector.decode("ascii")
        needle = 'outfile("cdf-frame.txt")'
        require(collector.count(needle) == 1, "cdf_output")
        collector = collector.replace(needle, 'outfile("@WORK@/cdf-frame.txt")')
        netlist = rt.modules["rendering"].netlist(
            self.job,
            "schematic",
            "state1",
            [("m2_vin", "0")],
            self.analysis["ade"]["inputs"],
            self.digest,
            self.operation,
        )
        prefix = (
            'unless(ddGetObj("MCP_GREL_Work") || ddCreateLib("MCP_GREL_Work" "%s") exit(1))\n'
            'unless(ddGetObj("MCP_GREL_Work")~>readPath=="%s" exit(1))\n'
        ) % (library, library)
        program = render(prefix + COMMON + collector + REOPEN, self.values(work)) + netlist
        self.run(
            session,
            work,
            program,
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
            and rt.copying.snapshot(self.owned + "/" + TB) == tb,
            "reopened_revision",
        )
        reopened = self.snapshot(work, "reopened", before, "after")
        require(
            reopened["footprint_sha256"] == saved["saved"]["footprint_sha256"], "reopened_footprint"
        )
        cdf = h.read(work + "/cdf-frame.txt", 262144)
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
            netlist_sha256=h.sha(raw),
            cdf_frame_sha256=h.sha(cdf),
        )
        receipt["netlist_receipt_sha256"] = self.digest_doc(receipt)
        return receipt, dict(
            readback=receipt,
            input_base64=base64.b64encode(raw).decode("ascii"),
            cdf_frame_base64=base64.b64encode(cdf).decode("ascii"),
        )


def main():
    import pwd

    require(
        sys.version_info[:2] == (2, 6) and os.getuid() != 0 and not sys.flags.optimize,
        "native_identity",
    )
    require(len(sys.argv) == 3 and sys.argv[2] in PHASES, "phase")
    digest, phase = sys.argv[1:]
    raw = sys.stdin.read(LIMIT + 1)
    require(0 < len(raw) <= LIMIT, "request_bound")
    packet = json.loads(raw)
    require(
        set(packet)
        == set(
            (
                "managed_root",
                "scope_base64",
                "authority_base64",
                "baseline_base64",
                "native_safety_base64",
                "previous_receipt_sha256",
                "support_base64",
                "cdf_collector_base64",
            )
        ),
        "request_fields",
    )
    support = read_encoded(packet, "support", 65536)
    require(hashlib.sha256(support).hexdigest() == SUPPORT_SHA256, "support_digest")
    helper = types.ModuleType("registered_mos_fixed_support")
    eval(compile(support, "_amp_pm0_default_phase.py", "exec"), helper.__dict__)
    require(helper.parse(raw) == packet, "canonical_packet")
    scope = helper.parse(helper.pinned(read_encoded(packet, "scope", 32768), digest))
    require(scope["schema_version"] == 1 and scope["route"] == "registered_mos_edit", "scope")
    subject = scope["subject"]
    require(
        helper.sha(helper.canonical(scope["plan"])) == subject["plan_sha256"]
        and helper.sha(helper.canonical(scope["route_qualification"])) == subject["route_sha256"],
        "scope_hashes",
    )
    approval = read_encoded(packet, "authority", 4096)
    require(
        helper.parse(approval)
        == dict(
            owner="C0",
            operation_id=subject["operation_id"],
            scope_sha256=digest,
            approved_phases=list(PHASES),
            valid_until_unix=scope["valid_until_unix"],
        )
        and type(scope["valid_until_unix"]) is int
        and time.time() < scope["valid_until_unix"],
        "authority_binding",
    )
    helper.pinned(read_encoded(packet, "baseline", 32768), SOURCE_NETLIST)
    pin = helper.parse(
        helper.pinned(read_encoded(packet, "native_safety", 65536), scope["native_safety_sha256"])
    )
    require(set(pin) == set(SAFETY_FIELDS) and pin["schema_version"] == 1, "native_safety_fields")
    collector = helper.pinned(read_encoded(packet, "cdf_collector", 32768), CDF_SHA256)
    prior = packet["previous_receipt_sha256"]
    require(prior is None if phase == PHASES[0] else helper.hex_digest(prior), "prior")
    operator = pwd.getpwuid(os.getuid())
    root = helper.private_path(packet["managed_root"], operator.pw_dir)
    layout_scope = dict(
        scope,
        native=dict(
            layout_manifest_sha256=pin["layout_manifest_sha256"],
            layout_worker_sha256=pin["layout_worker_sha256"],
        ),
    )
    _, runtime = helper.load_runtime(root, layout_scope)
    os.umask(63)
    with runtime.accounting.ReservationSession(root) as session:
        job = Source9MosJob(runtime, helper, operator, scope, pin, digest, approval, collector)
        output = helper.canonical(job.phase(session, phase, prior))
        require(len(output) <= LIMIT, "response_bound")
        session.check()
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
