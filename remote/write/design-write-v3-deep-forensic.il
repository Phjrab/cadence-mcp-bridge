sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"
workLib = "MCP_WorkLib"
targetCell = "Differential_Amplifier_TB2_MCP_TEST_V3"
backupCell = "Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP"

procedure(mcpV3DeepFail(message)
  printf("MCP_V3_DEEP_FAILURE|%s\n" message)
  exit(1)
)

procedure(mcpV3DeepEmit(scope cellView)
  printf("MCP_V3_DEEP_TOPOLOGY|%s|%d|%d|%d\n"
    scope
    length(cellView~>instances)
    length(cellView~>nets)
    length(cellView~>terminals))
  foreach(prop cellView~>prop
    when(equal(prop~>valueType "string") && rexMatchp("[\n\r]" prop~>value)
      mcpV3DeepFail("multiline property value is not permitted")
    )
    printf("MCP_V3_DEEP_PROPERTY|%s|cellview|%s|%s|%L\n"
      scope prop~>name prop~>valueType prop~>value)
  )
  foreach(inst cellView~>instances
    printf("MCP_V3_DEEP_INSTANCE|%s|%s|%s|%s|%s\n"
      scope inst~>name inst~>master~>libName inst~>master~>cellName inst~>master~>viewName)
  )
  foreach(net cellView~>nets
    printf("MCP_V3_DEEP_NET|%s|%s\n" scope net~>name)
  )
  foreach(term cellView~>terminals
    printf("MCP_V3_DEEP_TERMINAL|%s|%s|%L\n" scope term~>name term~>direction)
  )
)

sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpV3DeepFail("source read-only open failed"))
targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV3DeepFail("V3 target read-only open failed"))
backupCv = dbOpenCellViewByType(workLib backupCell sourceView "schematic" "r")
unless(backupCv mcpV3DeepFail("V3 backup read-only open failed"))

unless(equal(list(length(sourceCv~>instances) length(sourceCv~>nets)
  length(sourceCv~>terminals)) list(35 14 8))
  mcpV3DeepFail("BLOCKED_SOURCE_CHANGED")
)

mcpV3DeepEmit("source" sourceCv)
mcpV3DeepEmit("target" targetCv)
mcpV3DeepEmit("backup" backupCv)
printf("MCP_V3_DEEP_COMPLETE|true\n")

dbClose(backupCv)
dbClose(targetCv)
dbClose(sourceCv)
exit()
