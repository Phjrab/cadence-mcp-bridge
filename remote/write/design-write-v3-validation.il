sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"
workLib = "MCP_WorkLib"
targetCell = "Differential_Amplifier_TB2_MCP_TEST_V3"
backupCell = "Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP"
propertyName = "mcpMutationTest"
propertyValue = "validated-v1"

procedure(mcpV3Fail(message)
  printf("MCP_V3_FAILURE|%s\n" message)
  exit(1)
)

procedure(mcpV3Topology(cellView)
  list(length(cellView~>instances) length(cellView~>nets) length(cellView~>terminals))
)

procedure(mcpV3PropertiesEqual(leftCv rightCv)
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

procedure(mcpV3PropertiesContained(baselineCv candidateCv)
  propertiesMatch = t
  foreach(baselineProp baselineCv~>prop
    candidateProp = dbFindProp(candidateCv baselineProp~>name)
    unless(candidateProp && equal(candidateProp~>valueType baselineProp~>valueType)
      && equal(candidateProp~>value baselineProp~>value)
      propertiesMatch = nil
    )
  )
  propertiesMatch
)

procedure(mcpV3EmitFingerprint(stage cellView)
  printf("MCP_V3_FINGERPRINT|%s|topology|%d|%d|%d|%d\n"
    stage
    length(cellView~>instances)
    length(cellView~>nets)
    length(cellView~>terminals)
    length(cellView~>prop))
  foreach(prop cellView~>prop
    printf("MCP_V3_FINGERPRINT|%s|property|%s|%s\n"
      stage prop~>name prop~>valueType)
  )
)

sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpV3Fail("source open failed"))
sourceTopology = mcpV3Topology(sourceCv)
unless(equal(sourceTopology list(35 14 8))
  mcpV3Fail("source topology mismatch")
)
printf("MCP_V3_STAGE|source_verify|true|35|14|8\n")

when(ddGetObj(workLib targetCell sourceView)
  mcpV3Fail("V3 target already exists")
)
printf("MCP_V3_STAGE|V3_destination_absence_check|true\n")
when(ddGetObj(workLib backupCell sourceView)
  mcpV3Fail("V3 backup already exists")
)
printf("MCP_V3_STAGE|V3_backup_absence_check|true\n")

copyResult = errset(
  dbCopyCellView(sourceCv workLib targetCell sourceView nil nil nil)
  t
)
unless(copyResult mcpV3Fail("V3 source copy failed"))
targetCv = car(copyResult)
unless(targetCv mcpV3Fail("V3 source copy returned no target"))
unless(equal(mcpV3Topology(targetCv) sourceTopology)
  mcpV3Fail("V3 copy topology mismatch")
)
unless(mcpV3PropertiesEqual(sourceCv targetCv)
  mcpV3Fail("V3 copy properties mismatch")
)
when(dbFindProp(targetCv propertyName)
  mcpV3Fail("approved property already exists in V3 baseline")
)
baselinePropertyCount = length(targetCv~>prop)
printf("MCP_V3_STAGE|V3_copy|true|35|14|8\n")
mcpV3EmitFingerprint("baseline" targetCv)
printf("MCP_V3_STAGE|baseline_fingerprint|true|%d\n" baselinePropertyCount)

printf("MCP_V3_STAGE|dry_run|true|absent|1|0|false\n")
dbClose(targetCv)
dbClose(sourceCv)

targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV3Fail("V3 dry-run target open failed"))
sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpV3Fail("V3 dry-run source open failed"))
when(dbFindProp(targetCv propertyName)
  mcpV3Fail("V3 dry-run mutated target")
)
unless(equal(mcpV3Topology(targetCv) sourceTopology)
  mcpV3Fail("V3 dry-run topology mismatch")
)
unless(mcpV3PropertiesEqual(sourceCv targetCv)
  mcpV3Fail("V3 dry-run properties mismatch")
)
mcpV3EmitFingerprint("dry_run" targetCv)
dbClose(sourceCv)
dbClose(targetCv)
printf("MCP_V3_STAGE|unchanged_verification|true\n")

targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV3Fail("V3 backup source open failed"))
backupResult = errset(
  dbCopyCellView(targetCv workLib backupCell sourceView nil nil nil)
  t
)
unless(backupResult mcpV3Fail("V3 backup copy failed"))
backupCv = car(backupResult)
unless(backupCv mcpV3Fail("V3 backup copy returned no view"))
unless(equal(mcpV3Topology(backupCv) sourceTopology)
  mcpV3Fail("V3 backup topology mismatch")
)
unless(mcpV3PropertiesEqual(backupCv targetCv)
  mcpV3Fail("V3 backup properties mismatch")
)
when(dbFindProp(backupCv propertyName)
  mcpV3Fail("V3 backup contains approved property")
)
mcpV3EmitFingerprint("backup" backupCv)
dbClose(backupCv)
dbClose(targetCv)
printf("MCP_V3_STAGE|backup|true\n")

targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "a")
unless(targetCv mcpV3Fail("V3 target apply open failed"))
unless(dbReplaceProp(targetCv propertyName "string" propertyValue)
  mcpV3Fail("V3 property apply failed")
)
unless(dbSave(targetCv) mcpV3Fail("V3 target save failed"))
dbClose(targetCv)
printf("MCP_V3_STAGE|apply|true|1\n")

targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV3Fail("V3 apply verification target open failed"))
backupCv = dbOpenCellViewByType(workLib backupCell sourceView "schematic" "r")
unless(backupCv mcpV3Fail("V3 apply verification backup open failed"))
approvedProperty = dbFindProp(targetCv propertyName)
unless(approvedProperty && equal(approvedProperty~>valueType "string")
  && equal(approvedProperty~>value propertyValue)
  mcpV3Fail("V3 approved property mismatch")
)
unless(length(targetCv~>prop) == baselinePropertyCount + 1
  mcpV3Fail("V3 apply property count mismatch")
)
unless(equal(mcpV3Topology(targetCv) sourceTopology)
  mcpV3Fail("V3 apply topology mismatch")
)
unless(mcpV3PropertiesContained(backupCv targetCv)
  mcpV3Fail("V3 apply changed a baseline property")
)
when(dbFindProp(backupCv propertyName)
  mcpV3Fail("V3 apply changed backup")
)
printf("MCP_V3_STAGE|exact_diff_verification|true|1\n")
dbClose(targetCv)

rollbackResult = errset(
  dbCopyCellView(backupCv workLib targetCell sourceView nil nil t)
  t
)
unless(rollbackResult mcpV3Fail("V3 backup restore failed"))
restoredCv = car(rollbackResult)
unless(restoredCv mcpV3Fail("V3 backup restore returned no target"))
dbClose(backupCv)
printf("MCP_V3_STAGE|rollback|true\n")

backupCv = dbOpenCellViewByType(workLib backupCell sourceView "schematic" "r")
unless(backupCv mcpV3Fail("V3 final backup open failed"))
when(dbFindProp(restoredCv propertyName)
  mcpV3Fail("V3 rollback retained approved property")
)
unless(equal(mcpV3Topology(restoredCv) sourceTopology)
  mcpV3Fail("V3 rollback topology mismatch")
)
unless(mcpV3PropertiesEqual(restoredCv backupCv)
  mcpV3Fail("V3 rollback baseline mismatch")
)
mcpV3EmitFingerprint("rollback" restoredCv)
mcpV3EmitFingerprint("backup_final" backupCv)
dbClose(restoredCv)
dbClose(backupCv)
printf("MCP_V3_STAGE|baseline_restoration_verification|true\n")

sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpV3Fail("V3 final source open failed"))
targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV3Fail("V3 final target open failed"))
unless(equal(mcpV3Topology(sourceCv) list(35 14 8))
  mcpV3Fail("V3 final source topology mismatch")
)
unless(mcpV3PropertiesEqual(sourceCv targetCv)
  mcpV3Fail("V3 final target differs from source baseline")
)
dbClose(targetCv)
dbClose(sourceCv)
printf("MCP_V3_STAGE|source_unchanged_verification|true\n")
exit()
