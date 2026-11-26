"""Fixed OTA candidate SKILL templates for the registered native worker.

The worker supplies checked operation and copy identities, a closed 17-row
inventory, and the existing WLM mutation and readback checks. No caller SKILL
or ad hoc source path is accepted by the registered operator.
"""


def compose_common(legacy):
    # type: (str) -> str
    """Share the pinned legacy helpers without its Source9-only procedures."""
    target = legacy.index("procedure(mosTarget(cv)")
    links = legacy.index("procedure(mosLinks(terms)")
    bench = legacy.index("procedure(mosTbMaster(cv lib)")
    encode = legacy.index("procedure(mosEncode(value depth)")
    footprint = legacy.index("procedure(mosFoot(cv omit)")
    tuple_reader = legacy.index("procedure(mosBoundValue(key value)")
    return (
        legacy[:target]
        + legacy[links:bench]
        + legacy[encode:footprint]
        + legacy[tuple_reader:]
        + COMMON
    )


# Retarget uses the literal prepared inventory without selecting a W/L target.
COMMON = r"""
procedure(otaInst(cv name)
 let((matches)
  matches=setof(item cv~>instances item~>name==name)
  mosRequire(length(matches)==1)
  car(matches)))
procedure(otaNet(owner)
 if(owner~>net then owner~>net~>name else nil))
procedure(otaNamedRows(actual expected)
 mosRequire(length(actual)==length(expected))
 foreach(row expected mosRequire(equal(row assoc(car(row) actual))))
 t)
procedure(otaMosLinks(inst)
 let((links entry)
  links=mosLinks(inst~>instTerms)
  mosRequire(length(links)==4)
  foreach(mapcar terminal '("D" "G" "S" "B")
   entry=assoc(terminal links)
   mosRequire(and(entry stringp(cadr(entry))))
   entry)))
procedure(otaMaster(inst lib cell)
 mosRequire(and(inst~>libName==lib inst~>cellName==cell
                inst~>viewName=="symbol" inst~>orient=="R0")))
procedure(otaPorts(cv)
 let((rows)
  rows=foreach(mapcar term cv~>terminals
   list(term~>name term~>direction otaNet(term)))
  otaNamedRows(rows '(("VDD" "inputOutput" "VDD")
   ("VSS" "inputOutput" "VSS") ("inn" "input" "inn") ("inp" "input" "inp")
   ("out" "output" "out")))
  t))
procedure(otaDut(cv)
 let((rows inst pins pin fig)
  rows=@OTA_INVENTORY@
  mosRequire(and(length(rows)==17 length(cv~>instances)==22 length(cv~>terminals)==5))
  otaPorts(cv)
  foreach(row rows
   inst=otaInst(cv car(row))
   otaMaster(inst "gpdk090" cadr(row))
   mosRequire(equal(otaMosLinks(inst) caddr(row))))
  pins=setof(inst cv~>instances inst~>libName=="basic" && inst~>cellName=="iopin")
  mosRequire(length(pins)==5)
  foreach(term cv~>terminals
   mosRequire(length(term~>pins)==1)
   pin=car(term~>pins)
   mosRequire(and(pin~>term==term length(pin~>figs)==1))
   fig=car(pin~>figs)
   otaMaster(fig "basic" "iopin")
   mosRequire(and(member(fig pins) fig~>pin==pin)))
  t))
procedure(otaPropsMatch(inst key value)
 let((prop)
  prop=dbFindProp(inst key)
  mosRequire(and(prop prop~>valueType=="string" prop~>value==value))))
procedure(otaBenchSource(cv name cell positive)
 let((inst)
  inst=otaInst(cv name)
  otaMaster(inst "analogLib" cell)
  mosRequire(equal(mosLinks(inst~>instTerms)
   list(list("MINUS" "gnd!") list("PLUS" positive))))
  inst))
procedure(otaTbMaster(cv lib)
 let((inst symbol plus minus)
  mosRequire(and(length(cv~>instances)==5 !cv~>terminals))
  inst=otaInst(cv "DUT")
  otaMaster(inst lib "self_cascode_ota_17mos")
  symbol=mosView(lib "self_cascode_ota_17mos" "symbol" "r")
  otaPorts(symbol)
  mosRequire(eq(inst~>master symbol))
  otaNamedRows(mosLinks(inst~>instTerms) '(("VDD" "vdd") ("VSS" "gnd!")
    ("inn" "inn") ("inp" "inp") ("out" "out")))
  mosRequire(dbClose(symbol))
  otaPropsMatch(otaBenchSource(cv "VSUP" "vdc" "vdd") "vdc" "1")
  otaPropsMatch(otaBenchSource(cv "CL" "cap" "out") "c" "0.000000000001")
  plus=otaBenchSource(cv "VINP" "vsin" "inp")
  minus=otaBenchSource(cv "VINN" "vsin" "inn")
  foreach(source list(plus minus)
   otaPropsMatch(source "vdc" "500m") otaPropsMatch(source "va" "50m")
   otaPropsMatch(source "freq" "1K") otaPropsMatch(source "filenums" "none")
   mosRequire(!dbFindProp(source "acp")))
  otaPropsMatch(plus "acm" "500m")
  mosRequire(!dbFindProp(plus "sinephase"))
  otaPropsMatch(minus "acm" "-500m")
  otaPropsMatch(minus "sinephase" "180")
  inst))
procedure(otaFigure(shape)
 list(shape~>objType shape~>layerName shape~>purpose shape~>bBox
  if(member(shape~>objType '("line" "polygon" "path")) then shape~>points else nil)
  if(shape~>objType=="label" then shape~>theLabel else nil)
  otaNet(shape) mosProps(shape nil)))
procedure(otaFoot(cv target omit normalizeBench)
 let((rows figures terminals)
  mosRequire(and(length(cv~>instances)<=22 length(cv~>terminals)<=5
                 length(cv~>nets)<=64 length(cv~>shapes)<=256))
  rows=foreach(mapcar inst cv~>instances
   list(inst~>name
    if(and(normalizeBench inst~>name=="DUT") then nil else inst~>libName)
    inst~>cellName inst~>viewName inst~>orient inst~>xy
    mosLinks(inst~>instTerms) mosProps(inst if(inst~>name==target then omit else nil))))
  figures=foreach(mapcar shape cv~>shapes mosEncode(otaFigure(shape) 0))
  terminals=foreach(mapcar term cv~>terminals
   list(term~>name term~>direction otaNet(term)
    sort(foreach(mapcar pin term~>pins
     mosEncode(list(mosProps(pin nil) foreach(mapcar fig pin~>figs
      if(fig~>objType=="inst" then list("inst" fig~>name) else otaFigure(fig)))) 0))
      'alphalessp)
    mosProps(term nil)))
  mosEncode(list(sort(rows 'mosByName) sort(terminals 'mosByName)
   sort(foreach(mapcar net cv~>nets
    list(net~>name mosProps(net nil))) 'mosByName)
   sort(figures 'alphalessp) mosProps(cv nil)) 0)))
procedure(otaBench(lib)
 let((cv inventory)
  cv=mosOpen(lib "self_cascode_ota_tb" "r")
  otaTbMaster(cv lib)
  mosRequire(dbIsConnCurrent(cv))
  inventory=otaFoot(cv nil nil t)
  mosRequire(dbClose(cv))
  inventory))
procedure(otaSymbol(lib)
 let((cv inventory)
  cv=mosView(lib "self_cascode_ota_17mos" "symbol" "r")
  otaPorts(cv)
  inventory=otaFoot(cv nil nil nil)
  mosRequire(dbClose(cv))
  inventory))
procedure(otaPaths()
 mosRequire(and("@LIB@"!="@SOURCEALIAS@" "@OWNED@"!="@SOURCE@"
    ddGetObj("@LIB@")~>readPath=="@OWNED@"
    ddGetObj("@SOURCEALIAS@")~>readPath=="@SOURCE@")))
"""

RETARGET = r"""
procedure(otaRetarget()
 let((source child symbol dut original)
  otaPaths()
  mosRequire(equal(otaSymbol("@SOURCEALIAS@") otaSymbol("@LIB@")))
  source=mosOpen("@SOURCEALIAS@" "self_cascode_ota_17mos" "r")
  child=mosOpen("@LIB@" "self_cascode_ota_17mos" "r")
  otaDut(source) otaDut(child)
  mosRequire(and(dbIsConnCurrent(source) dbIsConnCurrent(child)
                 equal(otaFoot(source nil nil nil) otaFoot(child nil nil nil))))
  mosRequire(dbClose(source)) mosRequire(dbClose(child))
  original=otaBench("@SOURCEALIAS@")
  child=mosOpen("@LIB@" "self_cascode_ota_tb" "r")
  otaTbMaster(child "@SOURCEALIAS@")
  mosRequire(and(dbIsConnCurrent(child) equal(original otaFoot(child nil nil t))))
  mosRequire(dbClose(child))
  child=mosOpen("@LIB@" "self_cascode_ota_tb" "a")
  dut=otaTbMaster(child "@SOURCEALIAS@")
  mosRequire(equal(original otaFoot(child nil nil t)))
  symbol=mosView("@LIB@" "self_cascode_ota_17mos" "symbol" "r")
  dut~>master=symbol
  mosRequire(dbClose(symbol))
  mosRequire(and(schCheck(child) dbIsConnCurrent(child)))
  otaTbMaster(child "@LIB@")
  mosRequire(equal(original otaFoot(child nil nil t)))
  mosRequire(dbSave(child)) mosRequire(dbClose(child))
  mosRequire(equal(original otaBench("@LIB@")))
  printf("OTA17_CANDIDATE_BENCH_RETARGETED|@OP@\n")
  drain(poport) t))
if(errset(otaRetarget() t) then exit(0) else exit(1))
"""

_TARGET = r"""
procedure(otaTarget(cv)
 let((inst)
  otaDut(cv)
  inst=otaInst(cv "@TARGET@")
  otaMaster(inst "gpdk090" "@MASTER@")
  mosRequire(equal(otaMosLinks(inst) @TARGET_LINKS@))
  inst))
procedure(otaMask(omit)
 mosRequire(or(equal(omit '("l" "as" "ad" "ps" "pd"))
               equal(omit '("w" "fw" "as" "ad" "ps" "pd")))))
"""

EDIT_BEGIN = (
    _TARGET
    + r"""
procedure(mosEdit()
 let((source child inst original stable omit expected base param)
  otaPaths()
  mosRequire(equal(otaSymbol("@SOURCEALIAS@") otaSymbol("@LIB@")))
  mosRequire(equal(otaBench("@SOURCEALIAS@") otaBench("@LIB@")))
  omit=@OVERRIDES@
  otaMask(omit)
  source=mosOpen("@SOURCEALIAS@" "self_cascode_ota_17mos" "r")
  child=mosOpen("@LIB@" "self_cascode_ota_17mos" "r")
  otaTarget(source)
  inst=otaTarget(child)
  mosRequire(and(dbIsConnCurrent(source) dbIsConnCurrent(child)))
  original=otaFoot(source nil nil nil)
  mosRequire(equal(original otaFoot(child nil nil nil)))
  mosRequire(dbClose(source))
  stable=otaFoot(child "@TARGET@" omit nil)
  mosTuple("@WORK@/baseline.properties" inst)
  mosRequire(dbClose(child))
  child=mosOpen("@LIB@" "self_cascode_ota_17mos" "a")
  mosRequire(equal(original otaFoot(child nil nil nil)))
  inst=otaTarget(child)
  @BEFORE@
  @MUTATION@
"""
)

EDIT_CHECKS = r"""  mosSizingTrace("SCH_CHECK" "STARTED")
  mosSizingCheck("SCH_CHECK" schCheck(child))
  mosSizingTrace("FOOTPRINT" "STARTED")
  inst=otaTarget(child)
  mosSizingCheck("FOOTPRINT" and(dbIsConnCurrent(child)
    equal(stable otaFoot(child "@TARGET@" omit nil))))
  mosSizingTrace("HELD_PROPERTIES" "STARTED")
  @AFTER@
  mosSizingTrace("HELD_PROPERTIES" "RETURNED_OK")
  mosSizingTrace("EVIDENCE" "STARTED")
  mosTuple("@WORK@/saved.properties" inst)
  mosText("@WORK@/footprint.txt" stable)
  mosSizingTrace("EVIDENCE" "RETURNED_OK")
  mosSizingTrace("DB_SAVE" "STARTED")
  mosSizingCheck("DB_SAVE" dbSave(child))
  mosSizingTrace("DB_CLOSE" "STARTED")
  mosSizingCheck("DB_CLOSE" dbClose(child))
"""

EDIT_END = r"""  printf("C6_MOS_EDIT_SAVED|@OP@\n")
  drain(poport) t))
if(errset(mosEdit() t) then exit(0) else exit(1))
"""

REOPEN = (
    _TARGET
    + r"""
procedure(mosReopen()
 let((child inst copied omit)
  otaPaths()
  omit=@OVERRIDES@
  otaMask(omit)
  mosRequire(equal(otaSymbol("@SOURCEALIAS@") otaSymbol("@LIB@")))
  mosRequire(equal(otaBench("@SOURCEALIAS@") otaBench("@LIB@")))
  child=mosOpen("@LIB@" "self_cascode_ota_17mos" "r")
  inst=otaTarget(child)
  mosRequire(dbIsConnCurrent(child))
  @AFTER@
  mosTuple("@WORK@/reopened.properties" inst)
  mosText("@WORK@/footprint.txt" otaFoot(child "@TARGET@" omit nil))
  mosRequire(m2ReopenedMosFrame(inst))
  mosRequire(dbClose(child))
  copied=mosOpen("MCP_GREL_Work" "@NETLISTCELL@" "r")
  otaTbMaster(copied "@LIB@")
  mosRequire(equal(otaBench("@LIB@") otaFoot(copied nil nil t)))
  mosRequire(dbClose(copied))
  printf("C6_MOS_READ_ONLY_CLOSED|@OP@\n")
  drain(poport) t))
unless(errset(mosReopen() t) exit(1))
"""
)
