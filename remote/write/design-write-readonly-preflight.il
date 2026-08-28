sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"
workLib = "MCP_WorkLib"
targetCell = "Differential_Amplifier_TB2_MCP_TEST_V2"
backupCell = "Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP"
propertyName = "mcpMutationTest"

procedure(mcpPreflightFail(message)
  printf("MCP_WRITE_PREFLIGHT_FAILURE|%s\n" message)
  exit(1)
)

unless(ddGetObj(sourceLib sourceCell sourceView)
  mcpPreflightFail("source cellview unavailable")
)
unless(ddGetObj(workLib)
  mcpPreflightFail("work library unavailable")
)
when(ddGetObj(workLib targetCell sourceView)
  mcpPreflightFail("V2 target already exists")
)
when(ddGetObj(workLib backupCell sourceView)
  mcpPreflightFail("V2 backup already exists")
)

sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")
unless(sourceCv mcpPreflightFail("source open failed"))
when(dbFindProp(sourceCv propertyName)
  mcpPreflightFail("approved property already exists on source")
)
foreach(prop sourceCv~>prop
  unless(prop~>valueType
    mcpPreflightFail("property valueType unavailable")
  )
)
printf("MCP_WRITE_PREFLIGHT|true|%d|%d|%d|%d\n"
  length(sourceCv~>instances)
  length(sourceCv~>nets)
  length(sourceCv~>terminals)
  length(sourceCv~>prop))
dbClose(sourceCv)
exit()
