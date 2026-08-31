sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"
workLib = "MCP_WorkLib"
targetCell = "Differential_Amplifier_TB2_MCP_TEST_V2"
backupCell = "Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP"
propertyName = "mcpMutationTest"
propertyValue = "validated-v1"

procedure(mcpV2RollbackFail(message)
  printf("MCP_V2_ROLLBACK_FAILURE|%s\n" message)
  exit(1)
)

procedure(mcpV2Topology(cellView)
  list(length(cellView~>instances) length(cellView~>nets) length(cellView~>terminals))
)

procedure(mcpV2FindProperty(cellView name)
  dbFindProp(cellView name)
)

procedure(mcpV2PropertiesEqual(leftCv rightCv)
  propertiesMatch = t
  when(length(leftCv~>prop) != length(rightCv~>prop)
    propertiesMatch = nil
  )
  foreach(leftProp leftCv~>prop
    rightProp = mcpV2FindProperty(rightCv leftProp~>name)
    unless(rightProp && equal(rightProp~>valueType leftProp~>valueType)
      && equal(rightProp~>value leftProp~>value)
      propertiesMatch = nil
    )
  )
  propertiesMatch
)

procedure(mcpV2PropertiesContained(baselineCv candidateCv)
  propertiesMatch = t
  foreach(baselineProp baselineCv~>prop
    candidateProp = mcpV2FindProperty(candidateCv baselineProp~>name)
    unless(candidateProp && equal(candidateProp~>valueType baselineProp~>valueType)
      && equal(candidateProp~>value baselineProp~>value)
      propertiesMatch = nil
    )
  )
  propertiesMatch
)

sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpV2RollbackFail("source open failed"))
unless(equal(mcpV2Topology(sourceCv) list(35 14 8))
  mcpV2RollbackFail("source topology mismatch")
)
dbClose(sourceCv)

targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV2RollbackFail("V2 target open failed"))
backupCv = dbOpenCellViewByType(workLib backupCell sourceView "schematic" "r")
unless(backupCv mcpV2RollbackFail("V2 backup open failed"))
unless(equal(mcpV2Topology(targetCv) list(35 14 8))
  mcpV2RollbackFail("V2 target topology mismatch")
)
unless(equal(mcpV2Topology(backupCv) list(35 14 8))
  mcpV2RollbackFail("V2 backup topology mismatch")
)
when(mcpV2FindProperty(backupCv propertyName)
  mcpV2RollbackFail("V2 backup contains approved property")
)
unless(length(backupCv~>prop) == 8
  mcpV2RollbackFail("V2 backup baseline property count mismatch")
)
unless(length(targetCv~>prop) == 9
  mcpV2RollbackFail("V2 target property count mismatch")
)
unless(mcpV2PropertiesContained(backupCv targetCv)
  mcpV2RollbackFail("V2 target changed a baseline property")
)
approvedProperty = mcpV2FindProperty(targetCv propertyName)
unless(approvedProperty && equal(approvedProperty~>valueType "string")
  && equal(approvedProperty~>value propertyValue)
  mcpV2RollbackFail("V2 target approved property mismatch")
)

dbClose(targetCv)
rollbackResult = errset(
  dbCopyCellView(backupCv workLib targetCell sourceView nil nil t)
  t
)
unless(rollbackResult mcpV2RollbackFail("V2 backup restore failed"))
restoredCv = car(rollbackResult)
unless(restoredCv mcpV2RollbackFail("V2 backup restore returned no target"))
when(mcpV2FindProperty(restoredCv propertyName)
  mcpV2RollbackFail("rollback did not remove approved property")
)
unless(equal(mcpV2Topology(restoredCv) list(35 14 8))
  mcpV2RollbackFail("rollback topology mismatch")
)
unless(mcpV2PropertiesEqual(restoredCv backupCv)
  mcpV2RollbackFail("rollback target differs from backup")
)
dbClose(restoredCv)
dbClose(backupCv)

targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV2RollbackFail("rollback verification target open failed"))
backupCv = dbOpenCellViewByType(workLib backupCell sourceView "schematic" "r")
unless(backupCv mcpV2RollbackFail("rollback verification backup open failed"))
when(mcpV2FindProperty(targetCv propertyName)
  mcpV2RollbackFail("rollback verification found approved property")
)
unless(equal(mcpV2Topology(targetCv) list(35 14 8))
  mcpV2RollbackFail("rollback verification topology mismatch")
)
unless(mcpV2PropertiesEqual(targetCv backupCv)
  mcpV2RollbackFail("rollback verification differs from backup")
)
printf("MCP_V2_ROLLBACK|true|35|14|8|8|8|absent\n")
dbClose(backupCv)
dbClose(targetCv)
exit()
