"""Fixed SKILL augmentations for the separately owned OTA v2 holder (Python 2.6)."""

# mypy: ignore-errors

import re

_PROTECTION = r"""
procedure(otaTrace(step state)
 printf("OTA17_RT_DIAG|%s|%s\n" step state)
 drain(poport))
procedure(otaAssert(step ok)
 if(ok then otaTrace(step "OK")
  else otaTrace(step "FAILED") error("OTA17_RETARGET_DIAGNOSTIC_FAILURE"))
 ok)
procedure(otaEqualFoot(step expected actual)
 let((same)
  same=equal(mosEncode(expected 0) mosEncode(actual 0))
  foreach(field '("INSTANCES" "TERMINALS" "NETS" "FIGURES" "CV_PROPERTIES")
   unless(equal(mosEncode(car(expected) 0) mosEncode(car(actual) 0))
    otaTrace(step field))
   expected=cdr(expected) actual=cdr(actual))
  otaAssert(step same)))
procedure(otaSameExcept(step before after metadata)
 otaEqualFoot(step
  list(car(before) cadr(before) caddr(before) cadddr(before)
   setof(row nth(4 before) !member(car(row) metadata)))
  list(car(after) cadr(after) caddr(after) cadddr(after)
   setof(row nth(4 after) !member(car(row) metadata)))))
procedure(otaExtraction(before after counterBefore counterAfter runStarted observedEnd)
 let((startRows endRows oldConn newConn oldTime newTime)
  startRows=nth(4 before) endRows=nth(4 after)
  oldConn=assoc("connectivityLastUpdated" startRows)
  newConn=assoc("connectivityLastUpdated" endRows)
  oldTime=assoc("lastSchematicExtraction" startRows)
  newTime=assoc("lastSchematicExtraction" endRows)
  otaAssert("EXTRACT_COUNTERS_TYPED"
   and(oldConn newConn cadr(oldConn)=="int" cadr(newConn)=="int"
    fixp(caddr(oldConn)) fixp(caddr(newConn)) fixp(counterBefore) fixp(counterAfter)))
  printf("OTA17_RT_COUNTER|%d|%d|%d|%d\n"
    counterBefore counterAfter caddr(oldConn) caddr(newConn)) drain(poport)
  otaAssert("EXTRACT_COUNTERS"
   and(caddr(oldConn)==counterBefore counterAfter>=counterBefore
    caddr(newConn)>=caddr(oldConn) caddr(newConn)==counterAfter))
  otaAssert("EXTRACT_TIME_TYPED"
   and(oldTime newTime cadr(oldTime)=="time" cadr(newTime)=="time"
    stringp(caddr(oldTime)) stringp(caddr(newTime))
    strlen(caddr(oldTime))<=64 strlen(caddr(newTime))<=64))
  printf("OTA17_RT_CLOCK|%s|%s|%s|%s\n" runStarted observedEnd caddr(oldTime) caddr(newTime))
  drain(poport)
  otaAssert("EXTRACT_TIME_RANGE"
   and(compareTime(caddr(newTime) caddr(oldTime))>=0
    compareTime(caddr(newTime) runStarted)>=0 compareTime(observedEnd caddr(newTime))>=0))
  otaSameExcept("POST_FOOTPRINT" before after
    '("connectivityLastUpdated" "lastSchematicExtraction"))))
procedure(otaSaved(before after live)
 let((old new conn)
  old=assoc("schGeometryLastUpdated" nth(4 before))
  new=assoc("schGeometryLastUpdated" nth(4 after))
  conn=assoc("connectivityLastUpdated" nth(4 after))
  otaAssert("SAVE_COUNTER_TYPED"
   and(old new conn cadr(old)=="int" cadr(new)=="int" cadr(conn)=="int"
    fixp(caddr(old)) fixp(caddr(new)) fixp(caddr(conn)) fixp(live)))
  printf("OTA17_RT_SAVE_COUNTER|%d|%d|%d|%d\n" caddr(old) caddr(new) caddr(conn) live)
  drain(poport)
  otaAssert("SAVE_COUNTER"
   and(caddr(conn)==live caddr(new)<=live
    or(equal(old new)
       and(caddr(old)<live caddr(new)==live))))
  otaSameExcept("SAVE_FOOTPRINT" before after '("schGeometryLastUpdated"))))
procedure(otaStableWriterFoot(full)
 list(car(full) cadr(full) caddr(full) cadddr(full)
  setof(row nth(4 full)
    !member(car(row)
     '("connectivityLastUpdated" "lastSchematicExtraction" "schGeometryLastUpdated")))))
procedure(otaWriterMeta(step full live)
 let((rows conn stamp geometry)
  rows=nth(4 full)
  conn=assoc("connectivityLastUpdated" rows)
  stamp=assoc("lastSchematicExtraction" rows)
  geometry=assoc("schGeometryLastUpdated" rows)
  otaAssert(step and(conn stamp geometry cadr(conn)=="int" cadr(stamp)=="time"
   cadr(geometry)=="int" fixp(caddr(conn)) fixp(caddr(geometry)) fixp(live)
   caddr(conn)==live caddr(geometry)<=live stringp(caddr(stamp))
   strlen(caddr(stamp))<=64))
  printf("OTA17_RT_META|%s|%d|%d|%s\n" step live caddr(geometry) caddr(stamp))
  drain(poport)))
"""

RETARGET_BODY = r"""
procedure(otaRetarget(runStarted)
 let((origin copy srcSymbol dstSymbol dut original
      counterBefore counterAfter observedEnd checked saved checkResult)
  otaTrace("PATHS" "BEGIN") otaPaths() otaTrace("PATHS" "OK")
  otaTrace("SYMBOLS_OPEN" "BEGIN")
  srcSymbol=mosView("@SOURCEALIAS@" "self_cascode_ota_17mos" "symbol" "r")
  dstSymbol=mosView("@LIB@" "self_cascode_ota_17mos" "symbol" "r")
  otaPorts(srcSymbol) otaPorts(dstSymbol)
  otaEqualFoot("SYMBOL_FOOTPRINT" otaFootFields(srcSymbol nil nil nil)
    otaFootFields(dstSymbol nil nil nil))
  otaTrace("DUT_READ" "BEGIN")
  origin=mosOpen("@SOURCEALIAS@" "self_cascode_ota_17mos" "r")
  copy=mosOpen("@LIB@" "self_cascode_ota_17mos" "r")
  otaDut(origin) otaDut(copy)
  otaAssert("DUT_CONNECTED" and(dbIsConnCurrent(origin) dbIsConnCurrent(copy)))
  otaEqualFoot("DUT_FOOTPRINT" otaFootFields(origin nil nil nil) otaFootFields(copy nil nil nil))
  otaAssert("BASE_DUT_CLOSE" dbClose(origin)) otaAssert("CHILD_DUT_CLOSE" dbClose(copy))
  otaTrace("BASE_TB_READ" "BEGIN")
  origin=mosOpen("@SOURCEALIAS@" "self_cascode_ota_tb" "r")
  otaTbMasterBound(origin "@SOURCEALIAS@" srcSymbol "BASE_TB")
  otaAssert("BASE_TB_CONNECTED" dbIsConnCurrent(origin))
  original=otaFootFields(origin nil nil t)
  otaAssert("BASE_TB_CLOSE" dbClose(origin))
  otaTrace("CHILD_TB_READ" "BEGIN")
  copy=mosOpen("@LIB@" "self_cascode_ota_tb" "r")
  otaTbMasterBound(copy "@SOURCEALIAS@" srcSymbol "COPY_READ")
  otaAssert("COPY_READ_CONNECTED" dbIsConnCurrent(copy))
  otaEqualFoot("CHILD_TB_READ_FOOTPRINT" original otaFootFields(copy nil nil t))
  otaAssert("CHILD_TB_READ_CLOSE" dbClose(copy))
  otaTrace("CHILD_TB_APPEND" "BEGIN")
  copy=mosOpen("@LIB@" "self_cascode_ota_tb" "a")
  otaTrace("CHILD_TB_APPEND" "OK")
  dut=otaTbMasterBound(copy "@SOURCEALIAS@" srcSymbol "COPY_APPEND")
  otaEqualFoot("BEFORE_FOOTPRINT" original otaFootFields(copy nil nil t))
  counterBefore=dbGetCellViewCounter(copy)
  otaTrace("MASTER_ASSIGN" "BEGIN")
  dut~>master=dstSymbol
  otaAssert("MASTER_ASSIGN" eq(dut~>master dstSymbol))
  otaTrace("SCH_CHECK" "BEGIN")
  checkResult=schCheck(copy)
  observedEnd=getCurrentTime()
  otaAssert("SCH_CHECK" equal(checkResult list(0 0)))
  otaAssert("POST_CONNECTED" dbIsConnCurrent(copy))
  counterAfter=dbGetCellViewCounter(copy)
  otaTbMasterBound(copy "@LIB@" dstSymbol "POST_TB")
  checked=otaFootFields(copy nil nil t)
  otaExtraction(original checked counterBefore counterAfter runStarted observedEnd)
  otaTrace("SAVE" "BEGIN") otaAssert("SAVE" dbSave(copy))
  otaAssert("SAVE_CONNECTED" dbIsConnCurrent(copy))
  saved=otaFootFields(copy nil nil t)
  otaSaved(checked saved dbGetCellViewCounter(copy))
  otaAssert("SAVED_CLOSE" dbClose(copy))
  otaTrace("REOPEN" "BEGIN")
  copy=mosOpen("@LIB@" "self_cascode_ota_tb" "r")
  otaTbMasterBound(copy "@LIB@" dstSymbol "REOPEN_TB")
  otaAssert("REOPEN_CONNECTED" dbIsConnCurrent(copy))
  otaEqualFoot("REOPEN_FOOTPRINT" saved otaFootFields(copy nil nil t))
  otaAssert("REOPEN_CLOSE" dbClose(copy))
  otaAssert("CHILD_SYMBOL_CLOSE" dbClose(dstSymbol))
  otaAssert("SOURCE_SYMBOL_CLOSE" dbClose(srcSymbol))
  printf("OTA17_CANDIDATE_BENCH_RETARGETED|@OP@\n")
  drain(poport) t))

procedure(otaRetargetBodyReady() t)
"""

RETARGET_DRIVER = r"""
procedure(otaDiscardFailedEdit()
 let((views)
  views=setof(ownedCv dbGetOpenCellViews()
   ownedCv~>libName=="Ota17Candidate20261126"
   && ownedCv~>cellName=="self_cascode_ota_tb"
   && ownedCv~>viewName=="schematic" && ownedCv~>mode=="a")
  when(views
   unless(and(length(views)==1
    ddGetObj("Ota17Candidate20261126")~>readPath==
     "/home/buet/cds_work/Ota17CandidateOutputs20261126_v2/Ota17Candidate20261126")
    error("OTA17_DISCARD_IDENTITY"))
   dbPurge(car(views)))
  when(setof(ownedCv dbGetOpenCellViews()
   ownedCv~>libName=="Ota17Candidate20261126"
   && ownedCv~>cellName=="self_cascode_ota_tb"
   && ownedCv~>viewName=="schematic" && ownedCv~>mode=="a")
    error("OTA17_DISCARD_NOT_CLOSED"))
  t))
let((runStarted bodyLoaded retargetResult discardResult)
 runStarted=getCurrentTime()
 printf("OTA17_RT_DIAG|LOAD|BEGIN\n") drain(poport)
 bodyLoaded=errset(load("work/retarget-body.il") t)
 unless(and(bodyLoaded isCallable('otaRetarget) isCallable('otaRetargetBodyReady))
  printf("OTA17_RT_DIAG|LOAD|FAILED\n") drain(poport)
  exit(69))
 printf("OTA17_RT_DIAG|LOAD|OK\n") drain(poport)
 printf("OTA17_RT_DIAG|RUN|BEGIN\n") drain(poport)
 retargetResult=errset(otaRetarget(runStarted) t)
 if(and(retargetResult car(retargetResult)==t)
  then printf("OTA17_RT_DIAG|RUN|OK\n") drain(poport) exit(0)
  else
   printf("OTA17_RT_DIAG|RUN|FAILED\n") drain(poport)
   discardResult=errset(otaDiscardFailedEdit() t)
   printf("OTA17_RT_DIAG|DISCARD|%s\n"
    if(and(discardResult car(discardResult)==t) then "OK" else "FAILED"))
   drain(poport) exit(69)))
"""

V2_PATH = "/home/buet/cds_work/Ota17CandidateOutputs20261126_v2/Ota17Candidate20261126"
_META_PREFIX = b"OTA17_RT_META|"
_META_COUNT = re.compile(b"[0-9]{1,10}\\Z")
_META_TIME = re.compile(
    b"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) +(?:[1-9]|[12][0-9]|3[01]) "
    b"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9] [0-9]{4}\\Z"
)
_WRITER_DISCARD = r"""
procedure(otaDiscardWriterEdit()
 let((views discarded)
  views=setof(ownedCv dbGetOpenCellViews()
   ownedCv~>libName=="@LIB@" && ownedCv~>cellName=="self_cascode_ota_17mos"
   && ownedCv~>viewName=="schematic" && ownedCv~>mode=="a")
  when(views
   otaPaths()
   mosRequire(length(views)==1)
   dbPurge(car(views)))
  discarded=!setof(ownedCv dbGetOpenCellViews()
   ownedCv~>libName=="@LIB@" && ownedCv~>cellName=="self_cascode_ota_17mos"
   && ownedCv~>viewName=="schematic" && ownedCv~>mode=="a")
  mosRequire(discarded)
  t))
"""


def _replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError("ota_v2_fixed_template_changed")
    return source.replace(old, new, 1)


def parse_writer_metadata(stdout, stage):
    """Return the one saved or reopened metadata tuple, excluding banner bytes."""
    if (
        stage not in ("EDIT_SAVED_META", "EDIT_REOPEN_META")
        or not isinstance(stdout, bytes)
        or not 0 < len(stdout) <= 65536
    ):
        raise ValueError("ota_v2_writer_metadata_bound")
    rows = [line.split(b"|") for line in stdout.splitlines() if line.startswith(_META_PREFIX)]
    if (
        len(rows) != 1
        or len(rows[0]) != 5
        or rows[0][1] != stage.encode("ascii")
        or not _META_COUNT.match(rows[0][2])
        or not _META_COUNT.match(rows[0][3])
        or not _META_TIME.match(rows[0][4])
    ):
        raise ValueError("ota_v2_writer_metadata_row")
    counter, geometry = int(rows[0][2]), int(rows[0][3])
    if geometry > counter or counter > 2147483647:
        raise ValueError("ota_v2_writer_metadata_counter")
    return counter, geometry, rows[0][4]


def common_v2(common):
    """Share the exact v1 comparison and add typed v2 metadata checks."""
    original = common[common.index("procedure(otaFoot(") : common.index("procedure(otaBench(")]
    parts = _replace(original, "procedure(otaFoot(", "procedure(otaFootFields(")
    parts = _replace(parts, "  mosEncode(list(sort(rows", "  list(sort(rows")
    parts = _replace(parts, "mosProps(cv nil)) 0)))", "mosProps(cv nil))))")
    bench = common[common.index("procedure(otaTbMaster(") : common.index("procedure(otaFigure(")]
    bench = _replace(
        bench, "procedure(otaTbMaster(cv lib)", "procedure(otaTbMasterBound(cv lib symbol stage)"
    )
    bench = _replace(bench, "let((inst symbol plus minus)", "let((inst plus minus)")
    bench = _replace(bench, '  symbol=mosView(lib "self_cascode_ota_17mos" "symbol" "r")\n', "")
    bench = _replace(bench, "  mosRequire(dbClose(symbol))\n", "")
    bench = _replace(
        bench, '  inst=otaInst(cv "DUT")', '  otaTrace(stage "DUT")\n  inst=otaInst(cv "DUT")'
    )
    bench = _replace(
        bench,
        "  mosRequire(eq(inst~>master symbol))",
        '  otaAssert(strcat(stage "_MASTER") eq(inst~>master symbol))',
    )
    bench = _replace(
        bench,
        "  otaNamedRows(mosLinks(inst~>instTerms)",
        '  otaTrace(stage "LINKS")\n  otaNamedRows(mosLinks(inst~>instTerms)',
    )
    bench = _replace(
        bench,
        '  otaPropsMatch(otaBenchSource(cv "VSUP"',
        '  otaTrace(stage "PRIMITIVES")\n  otaPropsMatch(otaBenchSource(cv "VSUP"',
    )
    bench = _replace(bench, "  inst))", '  otaTrace(stage "OK")\n  inst))')
    common = _replace(
        common,
        '"@LIB@"!="@SOURCEALIAS@" "@OWNED@"!="@SOURCE@"',
        '"@LIB@"!="@SOURCEALIAS@" "@OWNED@"=="' + V2_PATH + '"',
    )
    return common + _PROTECTION + parts + bench


def edit_begin(template):
    template = _replace(
        template,
        "let((source child inst original stable omit expected base param)",
        "let((source child inst original stable omit expected base param\n"
        "      runStarted counterBefore counterAfter observedEnd checkResult checked saved)\n"
        "  runStarted=getCurrentTime()",
    )
    template = _replace(
        template,
        'stable=otaFoot(child "@TARGET@" omit nil)',
        'stable=otaFootFields(child "@TARGET@" omit nil)',
    )
    return _replace(
        template, "  @MUTATION@", "  counterBefore=dbGetCellViewCounter(child)\n  @MUTATION@"
    )


def edit_checks(template):
    template = _replace(
        template,
        '  mosSizingCheck("SCH_CHECK" schCheck(child))',
        "  checkResult=schCheck(child)\n  observedEnd=getCurrentTime()\n"
        '  mosSizingCheck("SCH_CHECK" equal(checkResult list(0 0)))',
    )
    template = _replace(
        template,
        '  mosSizingCheck("FOOTPRINT" and(dbIsConnCurrent(child)\n'
        '    equal(stable otaFoot(child "@TARGET@" omit nil))))',
        '  otaAssert("EDIT_CONNECTED" dbIsConnCurrent(child))\n'
        "  counterAfter=dbGetCellViewCounter(child)\n"
        '  checked=otaFootFields(child "@TARGET@" omit nil)\n'
        "  otaExtraction(stable checked counterBefore counterAfter runStarted observedEnd)\n"
        '  mosSizingCheck("FOOTPRINT" t)',
    )
    template = _replace(
        template,
        '  mosSizingTrace("EVIDENCE" "STARTED")\n'
        '  mosTuple("@WORK@/saved.properties" inst)\n'
        '  mosText("@WORK@/footprint.txt" stable)\n'
        '  mosSizingTrace("EVIDENCE" "RETURNED_OK")\n',
        "",
    )
    return _replace(
        template,
        '  mosSizingCheck("DB_SAVE" dbSave(child))',
        "  checked=otaFootFields(child nil nil nil)\n"
        '  otaAssert("EDIT_SAVE_RESULT" dbSave(child))\n'
        '  otaAssert("EDIT_SAVE_CONNECTED" dbIsConnCurrent(child))\n'
        "  saved=otaFootFields(child nil nil nil)\n"
        "  otaSaved(checked saved dbGetCellViewCounter(child))\n"
        '  otaWriterMeta("EDIT_SAVED_META" saved dbGetCellViewCounter(child))\n'
        '  mosSizingCheck("DB_SAVE" t)\n'
        '  mosSizingTrace("EVIDENCE" "STARTED")\n'
        "  inst=otaTarget(child)\n"
        '  mosTuple("@WORK@/saved.properties" inst)\n'
        '  saved=otaFootFields(child "@TARGET@" omit nil)\n'
        '  mosText("@WORK@/footprint.txt" mosEncode(otaStableWriterFoot(saved) 0))\n'
        '  mosSizingTrace("EVIDENCE" "RETURNED_OK")',
    )


def edit_end(template):
    return _replace(
        template,
        "if(errset(mosEdit() t) then exit(0) else exit(1))",
        _WRITER_DISCARD
        + r"""let((editResult discardResult)
 editResult=errset(mosEdit() t)
 if(and(editResult car(editResult)==t) then exit(0)
  else
   otaTrace("WRITER_RUN" "FAILED")
   discardResult=errset(otaDiscardWriterEdit() t)
   otaTrace("WRITER_DISCARD" if(and(discardResult car(discardResult)==t) then "OK" else "FAILED"))
   exit(69)))""",
    )


def reopen(template):
    template = _replace(
        template, "let((child inst copied omit)", "let((child inst copied omit observed)"
    )
    template = _replace(
        template,
        "  mosRequire(dbIsConnCurrent(child))",
        "  mosRequire(dbIsConnCurrent(child))\n"
        '  observed=otaFootFields(child "@TARGET@" omit nil)\n'
        '  otaWriterMeta("EDIT_REOPEN_META" observed dbGetCellViewCounter(child))',
    )
    template = _replace(
        template,
        '/footprint.txt" otaFoot(child "@TARGET@" omit nil))',
        '/footprint.txt" mosEncode(otaStableWriterFoot(observed) 0))',
    )
    return _replace(
        template,
        "  mosRequire(dbClose(copied))\n",
        '  otaAssert("AC_COPY_CLOSE" dbClose(copied))\n'
        '  otaTrace("DC_COPY_OPEN" "BEGIN")\n'
        '  copied=mosOpen("MCP_GREL_WorkDc" "@NETLISTCELL@" "r")\n'
        '  otaTbMaster(copied "@LIB@")\n'
        '  otaAssert("DC_COPY_FOOTPRINT" equal(otaBench("@LIB@") otaFoot(copied nil nil t)))\n'
        '  otaAssert("DC_COPY_CLOSE" dbClose(copied))\n',
    )
