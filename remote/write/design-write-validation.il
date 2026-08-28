sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"
workLib = "MCP_WorkLib"
workPath = "/home/buet/cds_work/MCP_WorkLib"
targetCell = "Differential_Amplifier_TB2_MCP_TEST"
backupCell = "Differential_Amplifier_TB2_MCP_TEST_BACKUP_V1"
targetView = "schematic"
propertyName = "mcpMutationTest"
propertyValue = "validated-v1"

procedure(mcpWriteFail(message)
  printf("MCP_WRITE_FAILURE|%s\n" message)
  exit(1)
)

procedure(mcpTopology(cellView)
  list(length(cellView~>instances) length(cellView~>nets) length(cellView~>terminals))
)

procedure(mcpFindPropertyByName(cellView name)
  foreach(prop cellView~>prop
    when(equal(prop~>name name)
      return(prop)
    )
  )
  nil
)

procedure(mcpPropertiesEqual(leftCv rightCv)
  when(length(leftCv~>prop) != length(rightCv~>prop)
    return(nil)
  )
  foreach(leftProp leftCv~>prop
    rightProp = mcpFindPropertyByName(rightCv leftProp~>name)
    unless(rightProp && equal(rightProp~>type leftProp~>type)
      && equal(rightProp~>value leftProp~>value)
      return(nil)
    )
  )
  t
)

procedure(mcpPropertiesContained(baselineCv candidateCv)
  foreach(baselineProp baselineCv~>prop
    candidateProp = mcpFindPropertyByName(candidateCv baselineProp~>name)
    unless(candidateProp && equal(candidateProp~>type baselineProp~>type)
      && equal(candidateProp~>value baselineProp~>value)
      return(nil)
    )
  )
  t
)

sourceObject = ddGetObj(sourceLib sourceCell sourceView)
unless(sourceObject mcpWriteFail("source cellview unavailable"))
when(ddGetObj(workLib targetCell targetView)
  mcpWriteFail("target cellview already exists")
)
when(ddGetObj(workLib backupCell targetView)
  mcpWriteFail("backup cellview already exists")
)

unless(ddGetObj(workLib)
  unless(ddCreateLib(workLib workPath)
    mcpWriteFail("work library creation failed")
  )
)
unless(ddGetObj(workLib) mcpWriteFail("work library registration failed"))

sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpWriteFail("source open failed"))
copyResult = errset(
  dbCopyCellView(sourceCv workLib targetCell targetView nil nil nil)
  t
)
unless(copyResult
  mcpWriteFail("source copy failed")
)
targetCv = car(copyResult)
unless(targetCv mcpWriteFail("source copy returned no target"))

sourceTopology = mcpTopology(sourceCv)
baselineTopology = mcpTopology(targetCv)
baselinePropertyCount = length(targetCv~>prop)
unless(equal(sourceTopology baselineTopology)
  mcpWriteFail("copy topology differs from source")
)
unless(mcpPropertiesEqual(sourceCv targetCv)
  mcpWriteFail("copy properties differ from source")
)
when(mcpFindPropertyByName(targetCv propertyName)
  mcpWriteFail("approved property already exists")
)
printf("MCP_STAGE|copy|%d|%d|%d\n" car(sourceTopology) cadr(sourceTopology) caddr(sourceTopology))
printf("MCP_STAGE|baseline|%d|%d|%d\n" car(baselineTopology) cadr(baselineTopology) caddr(baselineTopology))
printf("MCP_STAGE|dry_run|absent|validated-v1|1|0|false\n")
dbClose(targetCv)
dbClose(sourceCv)

targetCv = dbOpenCellViewByType(workLib targetCell targetView "schematic" "r")
unless(targetCv mcpWriteFail("dry-run verification open failed"))
when(mcpFindPropertyByName(targetCv propertyName)
  mcpWriteFail("dry-run changed target database")
)
unless(equal(mcpTopology(targetCv) baselineTopology)
  mcpWriteFail("dry-run changed target topology")
)
dbClose(targetCv)
printf("MCP_STAGE|dry_run_unchanged|true\n")

targetCv = dbOpenCellViewByType(workLib targetCell targetView "schematic" "r")
unless(targetCv mcpWriteFail("backup source open failed"))
backupResult = errset(
  dbCopyCellView(targetCv workLib backupCell targetView nil nil nil)
  t
)
unless(backupResult
  mcpWriteFail("backup copy failed")
)
backupCv = car(backupResult)
unless(backupCv mcpWriteFail("backup open failed"))
unless(equal(mcpTopology(backupCv) baselineTopology)
  mcpWriteFail("backup topology differs from baseline")
)
unless(mcpPropertiesEqual(backupCv targetCv)
  mcpWriteFail("backup properties differ from baseline")
)
when(mcpFindPropertyByName(backupCv propertyName)
  mcpWriteFail("backup contains approved property")
)
dbClose(backupCv)
dbClose(targetCv)
printf("MCP_STAGE|backup|true\n")

targetCv = dbOpenCellViewByType(workLib targetCell targetView "schematic" "a")
unless(targetCv mcpWriteFail("target apply open failed"))
unless(dbReplaceProp(targetCv propertyName "string" propertyValue)
  mcpWriteFail("property apply failed")
)
unless(dbSave(targetCv) mcpWriteFail("target save failed"))
dbClose(targetCv)
printf("MCP_STAGE|apply|validated-v1|1\n")

targetCv = dbOpenCellViewByType(workLib targetCell targetView "schematic" "r")
unless(targetCv mcpWriteFail("apply verification open failed"))
appliedProperty = mcpFindPropertyByName(targetCv propertyName)
unless(appliedProperty mcpWriteFail("applied property missing"))
unless(equal(appliedProperty~>value propertyValue)
  mcpWriteFail("applied property value mismatch")
)
unless(equal(mcpTopology(targetCv) baselineTopology)
  mcpWriteFail("apply changed target topology")
)
unless(length(targetCv~>prop) == baselinePropertyCount + 1
  mcpWriteFail("apply property count mismatch")
)
backupCv = dbOpenCellViewByType(workLib backupCell targetView "schematic" "r")
unless(backupCv mcpWriteFail("apply baseline open failed"))
unless(mcpPropertiesContained(backupCv targetCv)
  mcpWriteFail("apply changed a baseline property")
)
appliedTopology = mcpTopology(targetCv)
printf("MCP_STAGE|verify_apply|true|%d|%d|%d\n"
  car(appliedTopology) cadr(appliedTopology) caddr(appliedTopology))
dbClose(backupCv)
dbClose(targetCv)

targetCv = dbOpenCellViewByType(workLib targetCell targetView "schematic" "a")
unless(targetCv mcpWriteFail("rollback open failed"))
appliedProperty = mcpFindPropertyByName(targetCv propertyName)
unless(appliedProperty mcpWriteFail("rollback property missing"))
dbDeleteProp(appliedProperty)
unless(dbSave(targetCv) mcpWriteFail("rollback save failed"))
dbClose(targetCv)
printf("MCP_STAGE|rollback|true|1\n")

targetCv = dbOpenCellViewByType(workLib targetCell targetView "schematic" "r")
backupCv = dbOpenCellViewByType(workLib backupCell targetView "schematic" "r")
unless(targetCv mcpWriteFail("rollback verification open failed"))
unless(backupCv mcpWriteFail("backup verification open failed"))
when(mcpFindPropertyByName(targetCv propertyName)
  mcpWriteFail("rollback did not remove property")
)
unless(equal(mcpTopology(targetCv) baselineTopology)
  mcpWriteFail("rollback did not restore target topology")
)
unless(equal(mcpTopology(targetCv) mcpTopology(backupCv))
  mcpWriteFail("rollback target differs from backup topology")
)
unless(mcpPropertiesEqual(targetCv backupCv)
  mcpWriteFail("rollback target properties differ from backup")
)
rollbackTopology = mcpTopology(targetCv)
printf("MCP_STAGE|verify_rollback|true|%d|%d|%d\n"
  car(rollbackTopology) cadr(rollbackTopology) caddr(rollbackTopology))
dbClose(backupCv)
dbClose(targetCv)

sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpWriteFail("source final verification open failed"))
unless(equal(mcpTopology(sourceCv) sourceTopology)
  mcpWriteFail("source topology changed")
)
dbClose(sourceCv)
printf("MCP_STAGE|source_unchanged|true\n")
printf("MCP_STAGE|complete|true\n")
exit()
