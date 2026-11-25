"""Fixed registered inverter MOS edit and independent verification (Python 2.6)."""

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
from decimal import Decimal, localcontext

try:
    STRING_TYPES = (basestring,)
except NameError:
    STRING_TYPES = (str,)

SUPPORT_SHA256 = "71de4c49873c8c40b04c6482432390daa7a6aa4ef9092d2a762f4657a9d68d61"
CDF_SHA256 = "2563fca0a14f557317e69ec31a326642ee00c4f1dfd7af29ee08683542a25372"
SOURCE = "CmosLong20261111"
DUT, TB = "InvLong", "InvLongTb"
PHASES = ("EDIT_SAVE", "INDEPENDENT_REOPEN_NETLIST")
CONFIRMATIONS = "registered-mos-confirmations"
LIMIT = 524288
OVERRIDES = ("w", "fw", "l", "as", "ad", "ps", "pd")
SLOTS = {"pmos1v": ("MP", "vdd"), "nmos1v": ("MN", "vss")}
PROPERTIES = ("w", "fw", "l", "m", "fingers", "as", "ad", "ps", "pd", "nf", "model", "dfm")
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
procedure(mosView(lib cell view mode)
 let((cv)
  cv=dbOpenCellViewByType(lib cell view "" mode)
  mosRequire(and(cv cv~>libName==lib cv~>cellName==cell
                 cv~>viewName==view cv~>mode==mode)) cv))
procedure(mosOpen(lib cell mode) mosView(lib cell "schematic" mode))
procedure(mosTarget(cv)
 let((matches inst)
  matches=setof(item cv~>instances item~>name=="@TARGET@")
  mosRequire(length(matches)==1)
  inst=car(matches)
  mosRequire(and(inst~>libName=="gpdk090" inst~>cellName=="@MASTER@" inst~>viewName=="symbol"))
  mosRequire(equal(mosLinks(inst~>instTerms)
     list(list("B" "@RAIL@") list("D" "vout") list("G" "vin") list("S" "@RAIL@"))))
  inst))
procedure(mosLinks(terms)
 sort(foreach(mapcar term terms
      list(term~>name if(term~>net then term~>net~>name else nil))) 'mosByName))
procedure(mosTbMaster(cv lib)
 let((targets inst symbol)
  targets=setof(item cv~>instances item~>name=="DUT")
  mosRequire(and(length(cv~>instances)==4 length(targets)==1))
  inst=car(targets)
  symbol=mosView(lib "InvLong" "symbol" "r")
  mosRequire(and(inst~>libName==lib inst~>cellName=="InvLong"
                 inst~>viewName=="symbol" length(inst~>instTerms)==4
                 eq(inst~>master symbol)))
  mosRequire(dbClose(symbol))))
procedure(mosTb(lib)
 let((cv)
  cv=mosOpen(lib "InvLongTb" "r")
  mosRequire(mosTbMaster(cv lib))
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
        mosLinks(inst~>instTerms) mosProps(inst if(inst~>name=="@TARGET@" then omit else nil))))
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
procedure(mosLiteralValue(key value)
 if(member(key '("m" "fingers")) && fixp(value) then sprintf(nil "%d" value) else value))
procedure(mosTuple(path inst)
 let((port cdf prop param raw value)
  cdf=cdfGetInstCDF(inst)
  mosRequire(cdf)
  port=outfile(path)
  mosRequire(port)
  foreach(key '("w" "fw" "l" "m" "fingers" "as" "ad" "ps" "pd" "nf" "model" "dfm")
   prop=dbFindProp(inst key)
   param=cdfFindParamByName(cdf key)
   raw=if(prop then mosLiteralValue(key prop~>value) else nil)
   value=if(param then mosLiteralValue(key param~>value) else nil)
   when(prop mosRequire(and(stringp(prop~>valueType) stringp(raw))))
   when(param mosRequire(and(stringp(param~>type) stringp(value)
                             (null(param~>units) || stringp(param~>units)))))
   fprintf(port "%s|%L|%L|%L|%L|%L\n" key
     if(prop then prop~>valueType else nil) raw
     if(param then param~>type else nil) if(param then param~>units else nil)
     value))
  fprintf(port "COMPLETE\n")
  mosRequire(close(port))))
procedure(mosText(path text)
 let((port)
  port=outfile(path) mosRequire(port)
  fprintf(port "%s\n" text) mosRequire(close(port))))
"""

EDIT = r"""
procedure(mosEdit()
 let((source child inst original stable omit expected base param)
  mosRequire(and(ddGetObj("@LIB@")~>readPath=="@OWNED@"
                 ddGetObj("@SOURCEALIAS@")~>readPath=="@SOURCE@"))
  mosTb("@SOURCEALIAS@")
  mosTb("@LIB@")
  omit=@OVERRIDES@
  source=mosOpen("@SOURCEALIAS@" "InvLong" "r")
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
  @BEFORE@
  @MUTATION@
  mosRequire(and(schCheck(child) equal(stable mosFoot(child omit))))
  @AFTER@
  mosTuple("@WORK@/saved.properties" inst)
  mosText("@WORK@/footprint.txt" stable)
  mosRequire(and(dbSave(child) dbClose(child)))
  printf("C6_MOS_EDIT_SAVED|@OP@\n")
  drain(poport) t))
if(errset(mosEdit() t) then exit(0) else exit(1))
"""

RESTORE = r"""
  expected=cdfGetInstCDF(inst)
  foreach(row @DEFAULTS@
   let((prop param)
    prop=dbFindProp(inst car(row))
    param=cdfFindParamByName(expected car(row))
    mosRequire(and(prop prop~>valueType=="string" prop~>value==cadr(row)
      param param~>value==cadr(row) param~>defValue==caddr(row)))))
  foreach(key omit
   dbDeletePropByName(inst key)
   mosRequire(!dbFindProp(inst key)))
"""

SET_EXPLICIT = r"""
  base=cdfGetBaseCellCDF(ddGetObj("gpdk090" "@MASTER@"))
  mosRequire(and(base isCallable('dbReplaceProp)))
  foreach(row @CDFWRITE@
   param=cdfFindParamByName(base car(row))
   mosRequire(and(param param~>paramType==cadr(row)
    equal(mosLiteralValue(car(row) param~>minVal) nth(2 row))
    equal(mosLiteralValue(car(row) param~>maxVal) nth(3 row))
    equal(if(param~>callback then "present" else "absent") nth(4 row)))))
  foreach(row @WRITES@
   mosRequire(dbReplaceProp(inst car(row) cadr(row) caddr(row))))
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
  mosText("@WORK@/footprint.txt" mosFoot(child @OVERRIDES@))
  mosRequire(m2ReopenedMosFrame(inst))
  mosRequire(dbClose(child))
  copied=mosOpen("MCP_GREL_Work" "@NETLISTCELL@" "r")
  mosRequire(mosTbMaster(copied "@LIB@"))
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


def finite_length(value, unit):
    require(
        unit in ("nm", "um") and len(value) <= 48 and re.match(r"^[0-9]+(?:\.[0-9]+)?\Z", value),
        "registered_length",
    )
    number = Decimal(value)
    require(number > 0, "registered_length")
    with localcontext() as context:
        context.prec = 64
        return number * Decimal("1e-9" if unit == "nm" else "1e-6")


def cdf_length(row):
    value = row["cdf_value"]
    require(
        row["cdf_type"] == "instData"
        and row["cdf_units"] == "lengthMetric"
        and isinstance(value, STRING_TYPES)
        and value.endswith(("u", "n")),
        "cdf_length",
    )
    return finite_length(value[:-1], "nm" if value[-1] == "n" else "um")


def cdf_geometry(row, name):
    value = row["cdf_value"]
    units = "lengthMetric" if name in ("ps", "pd") else None
    require(
        row["cdf_type"] == "instData"
        and row["cdf_units"] == units
        and isinstance(value, STRING_TYPES)
        and len(value) <= 32
        and re.match(r"^[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,2})?[afpnum]?\Z", value)
        and Decimal(value.rstrip("afpnum")) > 0,
        "registered_cdf_geometry",
    )


def exact_route(scope):
    route = scope["route_qualification"]
    q = route["qualification"]
    plan, target = scope["plan"], q["target"]
    subject = scope["subject"]
    instance = target["instance"]
    prop = instance["property_name"]
    scalar = "w" if prop == "fw" else prop
    master = instance["master_cell"]
    require(master in SLOTS, "registered_mos_master")
    slot, rail = SLOTS[master]
    path, model = "DUT/" + slot, "gpdk090_" + master
    setter = route.get("explicit_set")
    allowed = ("w", "fw", "l") if setter is None else ("w", "fw", "l", "m")
    units = ("count",) if scalar == "m" else ("nm", "um")
    require(
        prop in allowed
        and (setter is not None or master == "pmos1v")
        and (
            instance["instance_path"],
            instance["master_library"],
            instance["master_cell"],
            instance["master_view"],
        )
        == (path, "gpdk090", master, "symbol")
        and (
            target["quantity"],
            target["scalar_option"],
            target["netlist_path"],
            target["netlist_model"],
            target["netlist_terminals"],
        )
        == (
            "count" if scalar == "m" else "length",
            scalar,
            path,
            model,
            ["vout", "vin", rail, rail],
        )
        and target["scalar_unit"] in units
        and plan["old"] == q["old"]
        and plan["requested"] == plan["expected"] == q["expected"]
        and plan["target"] == target
        and plan["baseline"] == q["baseline"]
        and q["baseline"]["revision"]["design_id"] == "cmos-long-inverter"
        and subject["owned_cell"] == DUT
        and subject["owned_view"] == "schematic"
        and re.match(r"^CmosLongMos[A-Za-z0-9]{3,40}\Z", subject["owned_library"]),
        "registered_inverter_route",
    )
    before, after = route["before"], route["after"]
    for field, value in ((before, q["old"]), (after, q["expected"])):
        require(
            set(field) == set(PROPERTIES)
            and cdf_length(field["w"]) == cdf_length(field["fw"])
            and field["w"]["cdf_value"] == field["fw"]["cdf_value"]
            and cdf_length(field["l"]) > 0
            and field["model"]["cdf_value"] == model
            and field["fingers"]["cdf_value"] == "1"
            and field["m"]["cdf_type"] == "instData"
            and field["m"]["cdf_units"] is None
            and re.match(r"^[1-9][0-9]{0,5}\Z", field["m"]["cdf_value"] or "")
            and (setter is not None or field["m"]["cdf_value"] == "1")
            and all(val is None for val in field["nf"].values())
            and (
                (
                    value["unit"] == "count"
                    and Decimal(field["m"]["cdf_value"]) == Decimal(value["value"])
                )
                if scalar == "m"
                else cdf_length(field[scalar]) == finite_length(value["value"], value["unit"])
            ),
            "registered_cdf_tuple",
        )
        for name in ("as", "ad", "ps", "pd"):
            cdf_geometry(field[name], name)
    keys = restoration_keys(route) if setter is None else explicit_keys(route)
    require(
        scalar in keys and before[scalar]["cdf_value"] != after[scalar]["cdf_value"],
        "registered_cdf_scalar_change",
    )
    return route


def explicit_keys(route):
    before, after = route["before"], route["after"]
    fields = route["explicit_set"]["fields"]
    keys = tuple(name for name in PROPERTIES if before[name] != after[name])
    scalars = set(("w", "fw", "l", "m"))
    require(
        set(keys).issubset(set(OVERRIDES) | set(("m",)))
        and set(fields) == set(keys).intersection(scalars),
        "explicit_set_property_inventory",
    )
    for key in keys:
        old, new = before[key], after[key]
        spec = fields.get(key, {})
        storage = spec.get("param_type", "string")
        require(
            (storage == "string" or (storage == "int" and key == "m"))
            and new["oa_type"] == storage
            and new["oa_value"] == new["cdf_value"]
            and old["cdf_type"] == new["cdf_type"] == "instData"
            and old["cdf_units"] == new["cdf_units"]
            and old["cdf_value"] != new["cdf_value"],
            "reviewed_explicit_property",
        )
    return keys


def restoration_keys(route):
    before, after = route["before"], route["after"]
    keys = tuple(name for name in PROPERTIES if before[name] != after[name])
    require(set(keys).issubset(OVERRIDES), "restore_only_width_length_geometry")
    for name in keys:
        old, new = before[name], after[name]
        require(
            old["oa_type"] == "string"
            and old["oa_value"] == old["cdf_value"]
            and new["oa_type"] is None
            and new["oa_value"] is None
            and old["cdf_type"] == new["cdf_type"] == "instData"
            and old["cdf_units"] == new["cdf_units"]
            and old["cdf_value"] is not None
            and new["cdf_value"] is not None,
            "observed_override_to_default",
        )
    return keys


def skill_token(value):
    if value is None:
        return "nil"
    if type(value) is int:
        require(1 <= value <= 999999, "skill_count")
        return str(value)
    require(re.match(r"^[A-Za-z0-9_. +-]{1,128}\Z", value), "skill_tuple_literal")
    return '"' + value + '"'


def skill_restore(route):
    keys = restoration_keys(route)
    omit = "'(" + " ".join(skill_token(key) for key in keys) + ")"
    table = (
        "'("
        + " ".join(
            "("
            + " ".join(
                skill_token(value)
                for value in (
                    key,
                    route["before"][key]["cdf_value"],
                    route["after"][key]["cdf_value"],
                )
            )
            + ")"
            for key in keys
        )
        + ")"
    )
    return omit, table


def skill_mutation(route, master):
    setter = route.get("explicit_set")
    if setter is None:
        omit, table = skill_restore(route)
        return omit, render(RESTORE, {"@DEFAULTS@": table}).decode("ascii")
    keys = explicit_keys(route)
    omit = "'(" + " ".join(skill_token(key) for key in keys) + ")"
    proof, writes = [], []
    for key in keys:
        row = route["after"][key]
        storage, value = row["oa_type"], row["oa_value"]
        writes.append((key, storage, int(value) if storage == "int" else value))
        spec = setter["fields"].get(key)
        if spec is not None:
            proof.append(
                (
                    key,
                    spec["param_type"],
                    spec["minimum"],
                    spec["maximum"],
                    "present" if spec["callback_present"] else "absent",
                )
            )

    def table(rows):
        return (
            "'("
            + " ".join("(" + " ".join(skill_token(value) for value in row) + ")" for row in rows)
            + ")"
        )

    return omit, render(
        SET_EXPLICIT,
        {
            "@MASTER@": master,
            "@CDFWRITE@": table(proof),
            "@WRITES@": table(writes),
        },
    ).decode("ascii")


def skill_check(rows):
    result = []
    for key in PROPERTIES:
        row = rows[key]
        result.append(
            "("
            + " ".join(
                skill_token(value)
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
        "     if(prop then mosLiteralValue(car(row) prop~>value) else nil)\n"
        "     if(param then param~>type else nil) if(param then param~>units else nil)\n"
        "     if(param then mosLiteralValue(car(row) param~>value) else nil)) cdr(row)))))"
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
        proof = self.route.get("explicit_set")
        if proof is not None:
            witness = proof["witness_operation_id"]
            require(
                helper.job_id(witness)
                and witness not in (self.operation, copy_id)
                and proof["witness_input_sha256"] != scope["plan"]["baseline"]["netlist_sha256"],
                "independent_set_witness",
            )
        self.library = self.subject["owned_library"]
        self.source_alias = pin.get("source_library", SOURCE)
        require(
            re.match(r"^CmosLong[A-Za-z0-9]{3,40}\Z", self.source_alias)
            and self.source_alias != self.library,
            "distinct_original_and_owned_aliases",
        )
        self.jobs = rt.root + "/" + rt.accounting.JOBS
        self.job, self.copy = self.jobs + "/" + self.operation, self.jobs + "/" + copy_id
        self.owned = self.copy + "/" + self.library
        self.source = helper.private_path(
            rt.root + "/layout-owned-20261111/" + self.source_alias, rt.root
        )
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
        baseline = self.scope["plan"]["baseline"]
        require(
            self.tree(self.source) == baseline["revision_sha256"]
            and source["tb"] == baseline["testbench_revision_sha256"],
            "registered_physical_baseline",
        )
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
            and not set((self.source_alias, self.library, "MCP_GREL_Work")).intersection(
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
        master = self.route["qualification"]["target"]["instance"]["master_cell"]
        slot, rail = SLOTS[master]
        omit, mutation = skill_mutation(self.route, master)
        return {
            "@LIB@": self.library,
            "@OWNED@": self.owned,
            "@SOURCE@": self.source,
            "@SOURCEALIAS@": self.source_alias,
            "@WORK@": work,
            "@OP@": self.operation,
            "@BEFORE@": skill_check(self.route["before"]),
            "@AFTER@": skill_check(self.route["after"]),
            "@OVERRIDES@": omit,
            "@MUTATION@": mutation,
            "@TARGET@": slot,
            "@MASTER@": master,
            "@RAIL@": rail,
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
            self.library_lines((self.source_alias, self.source)),
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
    helper.pinned(
        read_encoded(packet, "baseline", 32768), scope["plan"]["baseline"]["netlist_sha256"]
    )
    pin = helper.parse(
        helper.pinned(read_encoded(packet, "native_safety", 65536), scope["native_safety_sha256"])
    )
    require(
        set(pin).difference(("source_library",)) == set(SAFETY_FIELDS)
        and pin["schema_version"] == 1,
        "native_safety_fields",
    )
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
