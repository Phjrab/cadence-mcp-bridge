"""Fixed, read-only bounded CDF observation for the operator M2 inverter phase.

No MCP registration, transport, execution authority or callback evaluation. The
operator binds these names to an existing registered library set. Raw frames
are private observation evidence, never public tool output or production bounds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")


def _name(value: str) -> str:
    if not isinstance(value, str) or _NAME.fullmatch(value) is None:
        raise ValueError("invalid registered Cadence name")
    return value


@dataclass(frozen=True)
class CdfSource:
    library: str
    cell: str

    def __post_init__(self) -> None:
        _name(self.library)
        _name(self.cell)


_CDF_PROCEDURES = r"""
procedure(m2ReadField(object field)
 let((probe value)
  if(null(object) then list("missing" 'nil nil)
   else if(or(stringp(object) numberp(object)) then list("wrong_type" type(object) nil)
    else
    probe=errset(get(object field) nil)
    if(probe then
     value=car(probe)
     if(null(value) then list("missing" 'nil nil)
      else list("observed" type(value) value))
     else list("read_error" 'nil nil))
   ))
 ))
procedure(m2Meta(port scope field observation data)
 fprintf(port "META|%L|%L|%L|%L|%L\n" scope field
  car(observation) cadr(observation) if(data then caddr(observation) else nil)))
procedure(m2Scope(port scope cdf)
 let((info simulator field observation component terminals)
  info=m2ReadField(cdf 'simInfo)
  m2Meta(port scope "simInfo" info nil)
  simulator=m2ReadField(caddr(info) 'spectre)
  m2Meta(port scope "spectre" simulator nil)
  foreach(field list('componentName 'termOrder 'namePrefix 'modelName
                     'instParameters 'netlistProcedure)
   observation=m2ReadField(caddr(simulator) field)
   m2Meta(port scope symbolToString(field) observation t)
   when(field=='componentName component=caddr(observation))
   when(field=='termOrder terminals=caddr(observation)))
  fprintf(port "SIM|%L|%L|%L\n" scope component terminals)
 ))
procedure(m2CdfDump(port lib cell inst)
 let((master base effective count)
  master=dbOpenCellViewByType(lib cell "symbol" "" "r")
  unless(master error("M2_SYMBOL_MISSING"))
  fprintf(port "DEVICE|%L|%L|%L\n" lib cell if(inst then inst~>name else nil))
  count=0
  foreach(term master~>terminals
   count=count+1 when(count>8 error("M2_TERMINAL_BOUND"))
   fprintf(port "TERM|%L\n" term~>name))
  base=cdfGetBaseCellCDF(ddGetObj(lib cell))
  unless(base error("M2_CDF_MISSING"))
  effective=if(inst then cdfGetInstCDF(inst) else base)
  unless(effective error("M2_EFFECTIVE_CDF_MISSING"))
  foreach(scope list(list("base" base) list("effective" effective))
   count=0
   foreach(param cadr(scope)~>parameters
    count=count+1 when(count>128 error("M2_PARAMETER_BOUND"))
    fprintf(port "PARAM|%L|%L|%L|%L|%L|%L\n"
     car(scope) param~>name param~>type param~>units param~>defValue param~>value))
   m2Scope(port car(scope) cadr(scope)))
  dbClose(master)
  fprintf(port "END\n")
 ))
"""


def render_collector(source: CdfSource) -> bytes:
    """Emit the corrected fixed collector; output is a fixed cwd leaf.

    The runner must set an exclusive owned cwd, registered cds.lib, trusted
    OCEAN executable and -nocdsinit, shared lock, snapshots and process limits.
    The source is opened in r mode; no callback or CDF/save API is invoked.
    """
    library, cell = _name(source.library), _name(source.cell)
    program = _CDF_PROCEDURES + r"""procedure(m2Collect()
 let((cv port count)
 port=outfile("cdf-frame.txt") unless(port error("M2_OUTPUT_FAILED"))
 fprintf(port "M2_CDF_V2\n")
 cv=dbOpenCellViewByType("@LIB@" "@CELL@" "schematic" "" "r")
 unless(cv error("M2_SOURCE_MISSING"))
 count=0
 foreach(inst cv~>instances
  count=count+1 when(count>8 error("M2_INSTANCE_BOUND"))
  unless(and(inst~>libName=="basic"
             member(inst~>cellName list("ipin" "opin" "iopin")))
   m2CdfDump(port inst~>libName inst~>cellName inst)))
 dbClose(cv)
 foreach(cell list("vdc" "vpulse" "cap") m2CdfDump(port "analogLib" cell nil))
 fprintf(port "COMPLETE\n") close(port) t))
let((result) result=errset(m2Collect() t)
 if(result then exit(0) else exit(1)))
"""
    return program.replace("@LIB@", library).replace("@CELL@", cell).encode("ascii")


_MOS_PARAMETERS = (
    "w", "fw", "l", "m", "fingers", "as", "ad", "ps", "pd", "nf", "model", "dfm",
    "simW", "simM",
)
_FACT_DEVICES = (
    ("gpdk090", "nmos1v", _MOS_PARAMETERS),
    ("gpdk090", "pmos1v", _MOS_PARAMETERS),
    ("analogLib", "vdc", ("vdc", "dc", "voltage", "acm", "acp")),
    ("analogLib", "vsource", ("type", "dc", "voltage", "acm", "acp")),
    ("analogLib", "cap", ("c", "capacitance")),
)


def _selected_cdf_procedures() -> str:
    dump = "procedure(m2CdfDump(port lib cell inst)"
    parameters = "foreach(param cadr(scope)~>parameters"
    return _CDF_PROCEDURES.replace(dump, dump[:-1] + " names)").replace(
        parameters,
        "foreach(param setof(candidate cadr(scope)~>parameters member(candidate~>name names))",
    )


def _skill_names(names: tuple[str, ...]) -> str:
    return "list(" + " ".join(f'"{_name(name)}"' for name in names) + ")"


def render_research_cdf_facts(
    *, amp_source: CdfSource | None = None, mos_source: CdfSource | None = None
) -> bytes:
    """Collect five fixed base CDFs in one process without executing callbacks."""
    reads = "\n".join(
        f'  m2CdfDump(port "{lib}" "{cell}" nil {_skill_names(names)})'
        for lib, cell, names in _FACT_DEVICES
    )
    sources = []
    for source, kind in ((amp_source, "amp"), (mos_source, "mos")):
        if source is not None:
            sources.append(
                f'  m2ResearchInstances(port bindings "{_name(source.library)}" '
                f'"{_name(source.cell)}" "{kind}")'
            )
    body = r"""procedure(m2ResearchInstances(port bindings library cell kind)
 let((cv names fields found inst property)
  cv=dbOpenCellViewByType(library cell "schematic" "" "r")
  unless(and(cv cv~>mode=="r" cv~>libName==library cv~>cellName==cell
             cv~>viewName=="schematic" length(cv~>instances)<=128)
   error("M2_SOURCE_MISSING"))
  if(kind=="amp" then
   names=list("V1" "V2")
   fields=list("vdc" "voltage" "dc" "acm" "acp" "type" "ampl" "amplitude" "freq" "sinephase")
   else names=list("MN" "MP") fields=@MOS_PROPERTIES@)
  foreach(name names
   found=setof(candidate cv~>instances candidate~>name==name)
   unless(length(found)==1 error("M2_WRONG_INSTANCE"))
   inst=car(found)
   unless(and(inst~>viewName=="symbol"
              if(kind=="amp" then
               and(inst~>libName=="analogLib" member(inst~>cellName list("vdc" "vsin" "vsource")))
               else and(inst~>libName=="gpdk090"
                        inst~>cellName==if(name=="MN" then "nmos1v" else "pmos1v"))))
    error("M2_WRONG_INSTANCE_MASTER"))
   fprintf(bindings "INSTANCE|%L|%L|%L|%L|%L\n"
    kind name inst~>libName inst~>cellName inst~>viewName)
   unless(length(inst~>instTerms)==if(kind=="amp" then 2 else 4)
    error("M2_WRONG_INSTANCE_TERMINALS"))
   foreach(term inst~>instTerms
    unless(term~>net error("M2_UNCONNECTED_INSTANCE"))
    fprintf(bindings "NET|%L|%L|%L|%L\n" kind name term~>name term~>net~>name))
   foreach(field fields
    property=dbFindProp(inst field)
    fprintf(bindings "OA|%L|%L|%L|%L|%L\n" kind name field
     if(property then property~>valueType else nil) if(property then property~>value else nil)))
   m2CdfDump(port inst~>libName inst~>cellName inst fields))
  unless(dbClose(cv) error("M2_CLOSE_FAILED")) t))
procedure(m2ResearchConstraints(port cell)
 let((base param observation value)
  base=cdfGetBaseCellCDF(ddGetObj("gpdk090" cell))
  unless(base error("M2_CDF_MISSING"))
  foreach(name list("w" "fw" "l" "m" "fingers")
   param=cdfFindParamByName(base name)
   foreach(field list('paramType 'minVal 'maxVal 'parseAsNumber 'parseAsCEL 'editable 'callback)
    observation=m2ReadField(param field)
    value=caddr(observation)
    ; Omit callback bodies and non-scalar data. Keep type and observation status.
    unless(and(field!='callback
               or(numberp(value)
                  and(stringp(value) strlen(value)<=32
                      rexMatchp("^[-+0-9A-Za-z.]*$" value)))) value=nil)
    fprintf(port "LIMIT|%L|%L|%L|%L|%L|%L\n"
     cell name symbolToString(field) car(observation) cadr(observation) value))))
 t)
procedure(m2ResearchFacts()
 let((port bounds bindings)
  port=outfile("cdf-frame.txt") unless(port error("M2_OUTPUT_FAILED"))
  fprintf(port "M2_CDF_V2\n")
@READS@
  bindings=outfile("cdf-instance-bindings.txt") unless(bindings error("M2_OUTPUT_FAILED"))
  fprintf(bindings "M2_CDF_INSTANCE_BINDINGS_V1\n")
@INSTANCES@
  fprintf(bindings "COMPLETE\n") unless(close(bindings) error("M2_CLOSE_FAILED"))
  fprintf(port "COMPLETE\n") unless(close(port) error("M2_CLOSE_FAILED"))
  bounds=outfile("cdf-constraints.txt") unless(bounds error("M2_OUTPUT_FAILED"))
  fprintf(bounds "M2_CDF_CONSTRAINTS_V1\n")
  m2ResearchConstraints(bounds "nmos1v")
  m2ResearchConstraints(bounds "pmos1v")
  fprintf(bounds "COMPLETE\n") unless(close(bounds) error("M2_CLOSE_FAILED")) t))
if(errset(m2ResearchFacts() t) then exit(0) else exit(1))
"""
    body = (body.replace("@READS@", reads).replace("@INSTANCES@", "\n".join(sources))
            .replace("@MOS_PROPERTIES@", _skill_names(_MOS_PARAMETERS)))
    return (_selected_cdf_procedures() + body).encode("ascii")


def render_reopened_mos_cdf() -> bytes:
    """Definitions for the independent reopen phase to call on its exact target."""
    body = r"""procedure(m2ReopenedMosFrame(inst)
 let((port)
  unless(and(inst inst~>libName=="gpdk090" inst~>viewName=="symbol"
             member(inst~>cellName list("nmos1v" "pmos1v")))
   error("M2_WRONG_MOS_TARGET"))
  port=outfile("cdf-frame.txt") unless(port error("M2_OUTPUT_FAILED"))
  fprintf(port "M2_CDF_V2\n")
  m2CdfDump(port inst~>libName inst~>cellName inst @PROPERTIES@)
  fprintf(port "COMPLETE\n") unless(close(port) error("M2_CLOSE_FAILED")) t))
"""
    return (
        _selected_cdf_procedures() + body.replace("@PROPERTIES@", _skill_names(_MOS_PARAMETERS))
    ).encode("ascii")


def _atoms(text: str) -> tuple[object, ...]:
    """Parse bounded SKILL printed *data*, without eval or a general reader."""
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|[()]|[^\s()]+', text)
    if len(tokens) > 64:
        raise ValueError("CDF field exceeds bound")
    index = 0

    def read(depth: int = 0) -> object:
        nonlocal index
        if depth > 4 or index >= len(tokens):
            raise ValueError("invalid CDF data")
        token = tokens[index]
        index += 1
        if token == "(":
            items = []
            while index < len(tokens) and tokens[index] != ")":
                items.append(read(depth + 1))
            if index >= len(tokens):
                raise ValueError("unterminated CDF list")
            index += 1
            return tuple(items)
        if token == ")":
            raise ValueError("unexpected CDF list end")
        if token.startswith('"'):
            # Only the printer's unambiguous string escapes; preserve all other
            # strings as untrusted data, never numeric or executable expressions.
            if not token.endswith('"') or re.search(r'\\[^"\\nt]', token):
                raise ValueError("unsupported CDF escape")
            return re.sub(
                r'\\(["\\nt])', lambda m: {"n": "\n", "t": "\t"}.get(m[1], m[1]), token[1:-1]
            )
        if re.fullmatch(r"[A-Za-z0-9_+.,:/!<>?=\-]+", token) is None:
            raise ValueError("unsupported CDF atom")
        return None if token == "nil" else token

    result = []
    while index < len(tokens):
        result.append(read())
    return tuple(result)


def parse_frame(raw: bytes) -> tuple[dict[str, object], ...]:
    """Validate complete private output. This is observation, not qualification."""
    if len(raw) > 262144 or b"\x00" in raw:
        raise ValueError("CDF frame exceeds bound")
    lines = raw.decode("ascii").splitlines()
    if not lines or lines[0] not in ("M2_CDF_V1", "M2_CDF_V2") or lines[-1] != "COMPLETE":
        raise ValueError("incomplete CDF frame")
    devices: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    terminals: list[object] = []
    params: list[tuple[object, ...]] = []
    sims: list[tuple[object, ...]] = []
    metadata: list[tuple[object, ...]] = []
    for line in lines[1:-1]:
        if len(line) > 4096:
            raise ValueError("CDF line exceeds bound")
        fields = line.split("|")
        kind = fields.pop(0)
        values = []
        for index, field in enumerate(fields):
            # %L can print a symbol-headed list as a(b c). Recognize only the
            # observed typed instParameters data position, never expressions.
            if (
                kind == "META"
                and index == 4
                and len(fields) == 5
                and fields[1:4] == ['"instParameters"', '"observed"', "list"]
            ):
                printed = re.fullmatch(r"([A-Za-z][A-Za-z0-9_]*)\(([A-Za-z0-9_ ]*)\)", field)
                if printed:
                    field = "(" + printed[1] + " " + printed[2] + ")"
            value = _atoms(field)
            if len(value) != 1:
                raise ValueError("invalid CDF field")
            values.append(value[0])
        if kind == "DEVICE" and current is None and len(values) == 3:
            current = dict(zip(("library", "cell", "instance"), values, strict=True))
            terminals, params, sims = [], [], []
            metadata = []
        elif current is not None and kind == "TERM" and len(values) == 1:
            if values[0] in terminals or len(terminals) >= 8:
                raise ValueError("duplicate or excessive CDF terminal")
            terminals.append(values[0])
        elif current is not None and kind == "PARAM" and len(values) == 6:
            if values[0] not in ("base", "effective") or len(params) >= 256:
                raise ValueError("invalid CDF parameter scope/bound")
            if any(row[:2] == tuple(values[:2]) for row in params):
                raise ValueError("duplicate CDF parameter")
            params.append(tuple(values))
        elif current is not None and kind == "SIM" and len(values) == 3:
            if values[0] not in ("base", "effective") or any(row[0] == values[0] for row in sims):
                raise ValueError("invalid duplicate CDF simulation scope")
            sims.append(tuple(values))
        elif current is not None and kind == "META" and len(values) == 5:
            if (
                lines[0] != "M2_CDF_V2"
                or values[0] not in ("base", "effective")
                or values[1]
                not in (
                    "simInfo",
                    "spectre",
                    "componentName",
                    "termOrder",
                    "namePrefix",
                    "modelName",
                    "instParameters",
                    "netlistProcedure",
                )
                or values[2] not in ("observed", "missing", "wrong_type", "read_error")
                or any(row[:2] == tuple(values[:2]) for row in metadata)
                or (values[2] != "observed" and values[4] is not None)
            ):
                raise ValueError("invalid CDF metadata observation")
            metadata.append(tuple(values))
        elif current is not None and kind == "END" and not values:
            if not terminals or len(sims) != 2 or len(devices) >= 11:
                raise ValueError("incomplete/excessive CDF device")
            current.update(
                terminals=tuple(terminals), parameters=tuple(params), spectre=tuple(sims)
            )
            if lines[0] == "M2_CDF_V2":
                if len(metadata) != 16:
                    raise ValueError("incomplete typed CDF metadata")
                for scope, component, order in sims:
                    for name, sim_value in (("componentName", component), ("termOrder", order)):
                        observed = next(row for row in metadata if row[:2] == (scope, name))
                        if observed[4] != sim_value:
                            raise ValueError("conflicting CDF simulation metadata")
                current["metadata_fields"] = tuple(metadata)
            devices.append(current)
            current = None
        else:
            raise ValueError("unexpected CDF frame record")
    if current is not None or not devices:
        raise ValueError("incomplete CDF device")
    return tuple(devices)
