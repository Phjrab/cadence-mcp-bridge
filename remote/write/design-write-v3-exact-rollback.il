sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"
workLib = "MCP_WorkLib"
targetCell = "Differential_Amplifier_TB2_MCP_TEST_V3"
backupCell = "Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP"
propertyName = "mcpMutationTest"
propertyValue = "validated-v1"
geometryName = "schGeometryLastUpdated"

procedure(mcpV3RollbackFail(message)
  printf("MCP_V3_ROLLBACK_FAILURE|%s\n" message)
  exit(1)
)

procedure(mcpV3RollbackTopology(cellView)
  list(length(cellView~>instances) length(cellView~>nets) length(cellView~>terminals))
)

procedure(mcpV3RollbackPropertiesEqual(leftCv rightCv)
  matches = t
  when(length(leftCv~>prop) != length(rightCv~>prop) matches = nil)
  foreach(leftProp leftCv~>prop
    rightProp = dbFindProp(rightCv leftProp~>name)
    unless(rightProp && equal(rightProp~>valueType leftProp~>valueType)
      && equal(rightProp~>value leftProp~>value)
      matches = nil
    )
  )
  matches
)

procedure(mcpV3RollbackEmit(scope cellView)
  printf("MCP_V3_ROLLBACK_TOPOLOGY|%s|%d|%d|%d\n"
    scope length(cellView~>instances) length(cellView~>nets) length(cellView~>terminals))
  foreach(prop cellView~>prop
    printf("MCP_V3_ROLLBACK_PROPERTY|%s|%s|%s|%L\n"
      scope prop~>name prop~>valueType prop~>value)
  )
  foreach(inst cellView~>instances
    printf("MCP_V3_ROLLBACK_INSTANCE|%s|%s|%s|%s|%s\n"
      scope inst~>name inst~>master~>libName inst~>master~>cellName inst~>master~>viewName)
  )
  foreach(net cellView~>nets
    printf("MCP_V3_ROLLBACK_NET|%s|%s\n" scope net~>name)
  )
  foreach(term cellView~>terminals
    printf("MCP_V3_ROLLBACK_TERMINAL|%s|%s|%L\n" scope term~>name term~>direction)
  )
)

sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpV3RollbackFail("source read-only open failed"))
targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV3RollbackFail("V3 target read-only open failed"))
backupCv = dbOpenCellViewByType(workLib backupCell sourceView "schematic" "r")
unless(backupCv mcpV3RollbackFail("V3 backup read-only open failed"))

foreach(cv list(sourceCv targetCv backupCv)
  unless(equal(mcpV3RollbackTopology(cv) list(35 14 8))
    mcpV3RollbackFail("fixed topology precondition failed")
  )
)
unless(mcpV3RollbackPropertiesEqual(sourceCv backupCv)
  mcpV3RollbackFail("backup no longer equals source baseline")
)
unless(length(sourceCv~>prop) == 8 && length(backupCv~>prop) == 8
  && length(targetCv~>prop) == 9
  mcpV3RollbackFail("fixed property count precondition failed")
)
when(dbFindProp(sourceCv propertyName) || dbFindProp(backupCv propertyName)
  mcpV3RollbackFail("approved property exists in protected baseline")
)
approvedProp = dbFindProp(targetCv propertyName)
unless(approvedProp && equal(approvedProp~>valueType "string")
  && equal(approvedProp~>value propertyValue)
  mcpV3RollbackFail("approved target property precondition failed")
)
sourceGeometry = dbFindProp(sourceCv geometryName)
targetGeometry = dbFindProp(targetCv geometryName)
backupGeometry = dbFindProp(backupCv geometryName)
unless(sourceGeometry && targetGeometry && backupGeometry
  && equal(sourceGeometry~>valueType "int")
  && equal(targetGeometry~>valueType "int")
  && equal(backupGeometry~>valueType "int")
  && equal(sourceGeometry~>value 107168)
  && equal(backupGeometry~>value 107168)
  && equal(targetGeometry~>value 107169)
  mcpV3RollbackFail("baseline property precondition failed")
)
foreach(backupProp backupCv~>prop
  targetProp = dbFindProp(targetCv backupProp~>name)
  unless(targetProp mcpV3RollbackFail("target baseline property missing"))
  unless(equal(backupProp~>name geometryName)
    unless(equal(targetProp~>valueType backupProp~>valueType)
      && equal(targetProp~>value backupProp~>value)
      mcpV3RollbackFail("unexpected target property difference")
    )
  )
)
mcpV3RollbackEmit("source_before" sourceCv)
mcpV3RollbackEmit("target_before" targetCv)
mcpV3RollbackEmit("backup_before" backupCv)
printf("MCP_V3_ROLLBACK_STAGE|read_only_preconditions|true\n")
printf("MCP_V3_ROLLBACK_STAGE|dry_run|true|2|0|false\n")

dbClose(targetCv)
rollbackResult = errset(
  dbCopyCellView(backupCv workLib targetCell sourceView nil nil t)
  t
)
unless(rollbackResult mcpV3RollbackFail("fixed V3 backup restore failed"))
restoredCv = car(rollbackResult)
unless(restoredCv mcpV3RollbackFail("fixed V3 backup restore returned no target"))
unless(mcpV3RollbackPropertiesEqual(restoredCv backupCv)
  mcpV3RollbackFail("restored target differs from fixed backup")
)
when(dbFindProp(restoredCv propertyName)
  mcpV3RollbackFail("restored target retained approved property")
)
unless(equal(mcpV3RollbackTopology(restoredCv) list(35 14 8))
  mcpV3RollbackFail("restored target topology mismatch")
)
printf("MCP_V3_ROLLBACK_STAGE|rollback|true\n")
dbClose(restoredCv)
dbClose(backupCv)
dbClose(sourceCv)

sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpV3RollbackFail("source final read-only open failed"))
targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV3RollbackFail("target final read-only open failed"))
backupCv = dbOpenCellViewByType(workLib backupCell sourceView "schematic" "r")
unless(backupCv mcpV3RollbackFail("backup final read-only open failed"))
unless(mcpV3RollbackPropertiesEqual(sourceCv backupCv)
  && mcpV3RollbackPropertiesEqual(targetCv backupCv)
  mcpV3RollbackFail("post-rollback property equality failed")
)
foreach(cv list(sourceCv targetCv backupCv)
  unless(equal(mcpV3RollbackTopology(cv) list(35 14 8))
    mcpV3RollbackFail("post-rollback topology mismatch")
  )
)
mcpV3RollbackEmit("source_after" sourceCv)
mcpV3RollbackEmit("target_after" targetCv)
mcpV3RollbackEmit("backup_after" backupCv)
printf("MCP_V3_ROLLBACK_STAGE|post_verify|true\n")
printf("MCP_V3_ROLLBACK_COMPLETE|V3_ROLLBACK_VERIFIED\n")
dbClose(backupCv)
dbClose(targetCv)
dbClose(sourceCv)
exit()
