; Fixed read-only IC6.1.5 OA source fingerprint for the allowlisted ADE profile.
let((cv instanceCount netCount terminalCount)
  cv = dbOpenCellViewByType(
    "MyDesignLib"
    "Differential_Amplifier_TB2"
    "schematic"
    ""
    "r"
  )
  if(cv then
    instanceCount = length(cv~>instances)
    netCount = length(cv~>nets)
    terminalCount = length(cv~>terminals)
    printf(
      "MCP_ADE_OA|true|%d|%d|%d\n"
      instanceCount
      netCount
      terminalCount
    )
    dbClose(cv)
    exit(0)
  else
    printf("MCP_ADE_OA|false|0|0|0\n")
    exit(1)
  )
)
