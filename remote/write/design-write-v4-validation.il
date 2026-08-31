sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"
workLib = "MCP_WorkLib"
v3TargetCell = "Differential_Amplifier_TB2_MCP_TEST_V3"
v3BackupCell = "Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP"
targetCell = "Differential_Amplifier_TB2_MCP_TEST_V4"
backupCell = "Differential_Amplifier_TB2_MCP_TEST_V4_BACKUP"
propertyName = "mcpMutationTest"
propertyValue = "validated-v1"
geometryName = "schGeometryLastUpdated"

procedure(mcpV4Fail(message)
  printf("MCP_V4_FAILURE|%s\n" message)
  exit(1)
)

procedure(mcpV4Topology(cellView)
  list(length(cellView~>instances) length(cellView~>nets) length(cellView~>terminals))
)

procedure(mcpV4PropertiesEqual(leftCv rightCv)
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

procedure(mcpV4Emit(scope cellView)
  printf("MCP_V4_TOPOLOGY|%s|%d|%d|%d\n"
    scope length(cellView~>instances) length(cellView~>nets) length(cellView~>terminals))
  foreach(prop cellView~>prop
    printf("MCP_V4_PROPERTY|%s|%s|%s|%L\n"
      scope prop~>name prop~>valueType prop~>value)
  )
  foreach(inst cellView~>instances
    printf("MCP_V4_INSTANCE|%s|%s|%s|%s|%s\n"
      scope inst~>name inst~>master~>libName inst~>master~>cellName inst~>master~>viewName)
  )
  foreach(net cellView~>nets
    printf("MCP_V4_NET|%s|%s\n" scope net~>name)
  )
  foreach(term cellView~>terminals
    printf("MCP_V4_TERMINAL|%s|%s|%L\n" scope term~>name term~>direction)
  )
)

sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpV4Fail("source read-only open failed"))
v3TargetCv = dbOpenCellViewByType(workLib v3TargetCell sourceView "schematic" "r")
unless(v3TargetCv mcpV4Fail("restored V3 target read-only open failed"))
v3BackupCv = dbOpenCellViewByType(workLib v3BackupCell sourceView "schematic" "r")
unless(v3BackupCv mcpV4Fail("V3 backup read-only open failed"))
foreach(cv list(sourceCv v3TargetCv v3BackupCv)
  unless(equal(mcpV4Topology(cv) list(35 14 8))
    mcpV4Fail("protected baseline topology mismatch")
  )
)
unless(mcpV4PropertiesEqual(sourceCv v3TargetCv)
  && mcpV4PropertiesEqual(sourceCv v3BackupCv)
  mcpV4Fail("restored V3 baseline equality failed")
)
when(dbFindProp(sourceCv propertyName) || dbFindProp(v3TargetCv propertyName)
  || dbFindProp(v3BackupCv propertyName)
  mcpV4Fail("approved property exists in protected baseline")
)
printf("MCP_V4_STAGE|source_read_only_verify|true|35|14|8|V3_BASELINE_EQUAL\n")

when(ddGetObj(workLib targetCell sourceView)
  mcpV4Fail("V4 target already exists")
)
when(ddGetObj(workLib backupCell sourceView)
  mcpV4Fail("V4 backup already exists")
)
copyResult = errset(
  dbCopyCellView(sourceCv workLib targetCell sourceView nil nil nil)
  t
)
unless(copyResult mcpV4Fail("V4 source copy failed"))
targetCv = car(copyResult)
unless(targetCv mcpV4Fail("V4 source copy returned no target"))
unless(equal(mcpV4Topology(targetCv) list(35 14 8))
  && mcpV4PropertiesEqual(sourceCv targetCv)
  mcpV4Fail("V4 copy baseline mismatch")
)
when(dbFindProp(targetCv propertyName)
  mcpV4Fail("approved property already exists in V4 baseline")
)
baselineCount = length(targetCv~>prop)
baselineGeometry = dbFindProp(targetCv geometryName)
unless(baselineGeometry && equal(baselineGeometry~>valueType "int")
  mcpV4Fail("V4 baseline geometry metadata missing")
)
printf("MCP_V4_STAGE|V4_copy_from_source|true|35|14|8\n")
mcpV4Emit("baseline" targetCv)
printf("MCP_V4_STAGE|baseline_structural_and_property_fingerprint|true\n")
printf("MCP_V4_STAGE|non_mutating_dry_run|true|absent|1|0|false\n")
dbClose(targetCv)
dbClose(v3BackupCv)
dbClose(v3TargetCv)
dbClose(sourceCv)

targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV4Fail("V4 dry-run target open failed"))
sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpV4Fail("V4 dry-run source open failed"))
when(dbFindProp(targetCv propertyName)
  mcpV4Fail("V4 dry-run mutated target")
)
unless(equal(mcpV4Topology(targetCv) list(35 14 8))
  && mcpV4PropertiesEqual(sourceCv targetCv)
  mcpV4Fail("V4 dry-run baseline mismatch")
)
mcpV4Emit("dry_run" targetCv)
dbClose(sourceCv)
printf("MCP_V4_STAGE|dry_run_unchanged_verification|true\n")

backupResult = errset(
  dbCopyCellView(targetCv workLib backupCell sourceView nil nil nil)
  t
)
unless(backupResult mcpV4Fail("V4 backup copy failed"))
backupCv = car(backupResult)
unless(backupCv mcpV4Fail("V4 backup copy returned no view"))
unless(equal(mcpV4Topology(backupCv) list(35 14 8))
  && mcpV4PropertiesEqual(backupCv targetCv)
  mcpV4Fail("V4 backup baseline mismatch")
)
when(dbFindProp(backupCv propertyName)
  mcpV4Fail("V4 backup contains approved property")
)
mcpV4Emit("backup" backupCv)
dbClose(backupCv)
dbClose(targetCv)
printf("MCP_V4_STAGE|V4_backup_from_baseline|true\n")

targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "a")
unless(targetCv mcpV4Fail("V4 target apply open failed"))
unless(dbReplaceProp(targetCv propertyName "string" propertyValue)
  mcpV4Fail("V4 property apply failed")
)
unless(dbSave(targetCv) mcpV4Fail("V4 target save failed"))
dbClose(targetCv)
printf("MCP_V4_STAGE|apply_approved_property_once|true|1\n")

targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV4Fail("V4 apply verification target open failed"))
backupCv = dbOpenCellViewByType(workLib backupCell sourceView "schematic" "r")
unless(backupCv mcpV4Fail("V4 apply verification backup open failed"))
approvedProperty = dbFindProp(targetCv propertyName)
unless(approvedProperty && equal(approvedProperty~>valueType "string")
  && equal(approvedProperty~>value propertyValue)
  mcpV4Fail("V4 approved property mismatch")
)
unless(length(targetCv~>prop) == baselineCount + 1
  && equal(mcpV4Topology(targetCv) list(35 14 8))
  mcpV4Fail("V4 apply object boundary mismatch")
)
beforeGeometry = dbFindProp(backupCv geometryName)
afterGeometry = dbFindProp(targetCv geometryName)
unless(beforeGeometry && afterGeometry
  && equal(beforeGeometry~>valueType "int")
  && equal(afterGeometry~>valueType "int")
  mcpV4Fail("V4 bounded metadata side effect mismatch")
)
foreach(backupProp backupCv~>prop
  targetProp = dbFindProp(targetCv backupProp~>name)
  unless(targetProp mcpV4Fail("V4 baseline property missing after apply"))
  unless(equal(backupProp~>name geometryName)
    unless(equal(targetProp~>valueType backupProp~>valueType)
      && equal(targetProp~>value backupProp~>value)
      mcpV4Fail("V4 unexpected baseline property change")
    )
  )
)
printf("MCP_V4_METADATA|%s|int|%L|%L\n"
  geometryName beforeGeometry~>value afterGeometry~>value)
mcpV4Emit("apply" targetCv)
printf("MCP_V4_STAGE|exact_semantic_and_bounded_metadata_diff_verification|true|1|1\n")
dbClose(targetCv)

rollbackResult = errset(
  dbCopyCellView(backupCv workLib targetCell sourceView nil nil t)
  t
)
unless(rollbackResult mcpV4Fail("V4 backup restore failed"))
restoredCv = car(rollbackResult)
unless(restoredCv mcpV4Fail("V4 backup restore returned no target"))
unless(mcpV4PropertiesEqual(restoredCv backupCv)
  && equal(mcpV4Topology(restoredCv) list(35 14 8))
  mcpV4Fail("V4 rollback baseline mismatch")
)
when(dbFindProp(restoredCv propertyName)
  mcpV4Fail("V4 rollback retained approved property")
)
printf("MCP_V4_STAGE|rollback_V4_target_from_V4_backup|true\n")
mcpV4Emit("rollback" restoredCv)
mcpV4Emit("backup_final" backupCv)
dbClose(restoredCv)
dbClose(backupCv)
printf("MCP_V4_STAGE|baseline_restoration_and_property_absence_verification|true\n")
printf("MCP_V4_COMPLETE|V4_CLEAN_VALIDATION_VERIFIED\n")
exit()
