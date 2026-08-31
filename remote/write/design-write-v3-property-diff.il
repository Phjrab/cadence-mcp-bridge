sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"
workLib = "MCP_WorkLib"
targetCell = "Differential_Amplifier_TB2_MCP_TEST_V3"
backupCell = "Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP"
approvedPropertyName = "mcpMutationTest"
approvedPropertyValue = "validated-v1"

procedure(mcpV3ForensicFail(message)
  printf("MCP_V3_FORENSIC_FAILURE|%s\n" message)
  exit(1)
)

procedure(mcpV3ForensicTopology(cellView)
  list(length(cellView~>instances) length(cellView~>nets) length(cellView~>terminals))
)

procedure(mcpV3ForensicPropertiesEqual(leftCv rightCv)
  propertiesMatch = t
  when(length(leftCv~>prop) != length(rightCv~>prop)
    propertiesMatch = nil
  )
  foreach(leftProp leftCv~>prop
    rightProp = dbFindProp(rightCv leftProp~>name)
    unless(rightProp && equal(rightProp~>valueType leftProp~>valueType)
      && equal(rightProp~>value leftProp~>value)
      propertiesMatch = nil
    )
  )
  propertiesMatch
)

sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpV3ForensicFail("source open failed"))
targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV3ForensicFail("V3 target open failed"))
backupCv = dbOpenCellViewByType(workLib backupCell sourceView "schematic" "r")
unless(backupCv mcpV3ForensicFail("V3 backup open failed"))

unless(equal(mcpV3ForensicTopology(sourceCv) list(35 14 8))
  mcpV3ForensicFail("source topology mismatch")
)
unless(equal(mcpV3ForensicTopology(targetCv) list(35 14 8))
  mcpV3ForensicFail("V3 target topology mismatch")
)
unless(equal(mcpV3ForensicTopology(backupCv) list(35 14 8))
  mcpV3ForensicFail("V3 backup topology mismatch")
)
unless(mcpV3ForensicPropertiesEqual(sourceCv backupCv)
  mcpV3ForensicFail("V3 backup differs from source baseline")
)
when(dbFindProp(backupCv approvedPropertyName)
  mcpV3ForensicFail("V3 backup contains approved property")
)

printf("MCP_V3_FORENSIC_BASELINE|true|35|14|8|%d\n" length(backupCv~>prop))
diffCount = 0
foreach(backupProp backupCv~>prop
  targetProp = dbFindProp(targetCv backupProp~>name)
  if(targetProp then
    unless(equal(targetProp~>valueType backupProp~>valueType)
      && equal(targetProp~>value backupProp~>value)
      if(equal(targetProp~>value backupProp~>value) then
        printf("MCP_V3_FORENSIC_DIFF|%s|%s|%s|true|true|true|na\n"
          backupProp~>name backupProp~>valueType targetProp~>valueType)
      else
        printf("MCP_V3_FORENSIC_DIFF|%s|%s|%s|true|true|false|na\n"
          backupProp~>name backupProp~>valueType targetProp~>valueType)
      )
      diffCount = diffCount + 1
    )
  else
    printf("MCP_V3_FORENSIC_DIFF|%s|%s|absent|true|false|false|na\n"
      backupProp~>name backupProp~>valueType)
    diffCount = diffCount + 1
  )
)

foreach(targetProp targetCv~>prop
  backupProp = dbFindProp(backupCv targetProp~>name)
  unless(backupProp
    if(equal(targetProp~>name approvedPropertyName) then
      if(equal(targetProp~>valueType "string")
        && equal(targetProp~>value approvedPropertyValue) then
        approvedEqual = "true"
      else
        approvedEqual = "false"
      )
    else
      approvedEqual = "na"
    )
    printf("MCP_V3_FORENSIC_DIFF|%s|absent|%s|false|true|false|%s\n"
      targetProp~>name targetProp~>valueType approvedEqual)
    diffCount = diffCount + 1
  )
)

printf("MCP_V3_FORENSIC_SUMMARY|true|%d|35|14|8\n" diffCount)
dbClose(backupCv)
dbClose(targetCv)
dbClose(sourceCv)
exit()
