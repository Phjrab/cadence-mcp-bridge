sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"
workLib = "MCP_WorkLib"
targetCell = "Differential_Amplifier_TB2_MCP_TEST_V2"
backupCell = "Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP"
propertyName = "mcpMutationTest"
propertyValue = "validated-v1"

procedure(mcpV2ForensicFail(message)
  printf("MCP_V2_FORENSIC_FAILURE|%s\n" message)
  exit(1)
)

procedure(mcpV2Topology(cellView)
  list(length(cellView~>instances) length(cellView~>nets) length(cellView~>terminals))
)

procedure(mcpV2FindProperty(cellView name)
  dbFindProp(cellView name)
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
unless(sourceCv mcpV2ForensicFail("source open failed"))
targetCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
unless(targetCv mcpV2ForensicFail("V2 target open failed"))
backupCv = dbOpenCellViewByType(workLib backupCell sourceView "schematic" "r")
unless(backupCv mcpV2ForensicFail("V2 backup open failed"))

unless(equal(mcpV2Topology(sourceCv) list(35 14 8))
  mcpV2ForensicFail("source topology mismatch")
)
unless(equal(mcpV2Topology(targetCv) list(35 14 8))
  mcpV2ForensicFail("V2 target topology mismatch")
)
unless(equal(mcpV2Topology(backupCv) list(35 14 8))
  mcpV2ForensicFail("V2 backup topology mismatch")
)
when(mcpV2FindProperty(backupCv propertyName)
  mcpV2ForensicFail("V2 backup contains approved property")
)
unless(length(backupCv~>prop) == 8
  mcpV2ForensicFail("V2 backup baseline property count mismatch")
)
unless(length(targetCv~>prop) == 9
  mcpV2ForensicFail("V2 target property count mismatch")
)
unless(mcpV2PropertiesContained(backupCv targetCv)
  mcpV2ForensicFail("V2 target changed a baseline property")
)
approvedProperty = mcpV2FindProperty(targetCv propertyName)
unless(approvedProperty mcpV2ForensicFail("approved V2 property is missing"))
unless(equal(approvedProperty~>valueType "string")
  mcpV2ForensicFail("approved V2 property type mismatch")
)
unless(equal(approvedProperty~>value propertyValue)
  mcpV2ForensicFail("approved V2 property value mismatch")
)

printf("MCP_V2_FORENSIC|true|35|14|8|8|9|validated-v1\n")
dbClose(backupCv)
dbClose(targetCv)
dbClose(sourceCv)
exit()
