; Fixed read-only OA topology probe for the approved actual ADE profile.
let((cv instanceCount netCount terminalCount closed)
  cv = dbOpenCellViewByType(
    "MyDesignLib"
    "Differential_Amplifier_TB2"
    "schematic"
    ""
    "r"
  )
  unless(cv
    printf("MCP_ADE_OA|false|0|0|0\n")
    exit(1)
  )
  instanceCount = length(cv~>instances)
  netCount = length(cv~>nets)
  terminalCount = length(cv~>terminals)
  closed = dbClose(cv)
  unless(closed
    printf("MCP_ADE_OA|false|0|0|0\n")
    exit(1)
  )
  printf("MCP_ADE_OA|true|%d|%d|%d\n" instanceCount netCount terminalCount)
)
exit(0)
