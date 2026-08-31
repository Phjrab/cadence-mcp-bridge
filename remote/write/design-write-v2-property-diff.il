sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"
workLib = "MCP_WorkLib"
targetCell = "Differential_Amplifier_TB2_MCP_TEST_V2"
backupCell = "Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP"

procedure(mcpV2PropertyDiffFail(message)
  printf("MCP_V2_PROPERTY_DIFF_FAILURE|%s\n" message)
  exit(1)
)

procedure(mcpV2PropertyDiffTopology(cellView)
  list(length(cellView~>instances) length(cellView~>nets) length(cellView~>terminals))
)

sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpV2PropertyDiffFail("source open failed"))
targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV2PropertyDiffFail("V2 target open failed"))
backupCv = dbOpenCellViewByType(workLib backupCell sourceView "schematic" "r")
unless(backupCv mcpV2PropertyDiffFail("V2 backup open failed"))

unless(equal(mcpV2PropertyDiffTopology(sourceCv) list(35 14 8))
  mcpV2PropertyDiffFail("source topology mismatch")
)
unless(equal(mcpV2PropertyDiffTopology(targetCv) list(35 14 8))
  mcpV2PropertyDiffFail("V2 target topology mismatch")
)
unless(equal(mcpV2PropertyDiffTopology(backupCv) list(35 14 8))
  mcpV2PropertyDiffFail("V2 backup topology mismatch")
)

diffCount = 0
foreach(backupProp backupCv~>prop
  targetProp = dbFindProp(targetCv backupProp~>name)
  if(targetProp then
    unless(equal(targetProp~>valueType backupProp~>valueType)
      && equal(targetProp~>value backupProp~>value)
      if(equal(targetProp~>value backupProp~>value) then
        printf("MCP_V2_PROPERTY_DIFF|%s|%s|%s|true|true|true\n"
          backupProp~>name backupProp~>valueType targetProp~>valueType)
      else
        printf("MCP_V2_PROPERTY_DIFF|%s|%s|%s|true|true|false\n"
          backupProp~>name backupProp~>valueType targetProp~>valueType)
      )
      diffCount = diffCount + 1
    )
  else
    printf("MCP_V2_PROPERTY_DIFF|%s|%s|absent|true|false|false\n"
      backupProp~>name backupProp~>valueType)
    diffCount = diffCount + 1
  )
)

foreach(targetProp targetCv~>prop
  backupProp = dbFindProp(backupCv targetProp~>name)
  unless(backupProp
    printf("MCP_V2_PROPERTY_DIFF|%s|absent|%s|false|true|false\n"
      targetProp~>name targetProp~>valueType)
    diffCount = diffCount + 1
  )
)

printf("MCP_V2_PROPERTY_DIFF_SUMMARY|true|%d|35|14|8\n" diffCount)
dbClose(backupCv)
dbClose(targetCv)
dbClose(sourceCv)
exit()
