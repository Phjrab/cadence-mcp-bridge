; Read-only bounded current OA instance/connection/property observation.
; Raw markers flow only to a private Python parser; no cellview is saved.
sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"
allowedProperties = list("dc" "vdc" "idc" "r" "c" "l" "acmag" "ampl"
  "freq" "v1" "v2" "type" "val")

let((cv instCount netCount terminalCount instName masterLib masterCell
  termName netName propertyCount)
  cv = dbOpenCellViewByType(sourceLib sourceCell sourceView "" "r")
  unless(cv exit(1))
  instCount = length(cv~>instances)
  netCount = length(cv~>nets)
  terminalCount = length(cv~>terminals)
  propertyCount = 0
  printf("MCP_WP14_FACT_BEGIN|true\n")
  foreach(inst cv~>instances
    instName = inst~>name
    masterLib = inst~>master~>libName
    masterCell = inst~>master~>cellName
    printf("MCP_WP14_INST|%s|%s|%s|%d\n"
      instName masterLib masterCell length(inst~>instTerms))
    foreach(instTerm inst~>instTerms
      termName = instTerm~>term~>name
      netName = if(instTerm~>net then instTerm~>net~>name else "UNCONNECTED")
      printf("MCP_WP14_TERM|%s|%s|%s\n" instName termName netName)
    )
    foreach(prop inst~>prop
      propertyCount = propertyCount + 1
      when(member(prop~>name allowedProperties) &&
        member(prop~>valueType list("string" "float" "int"))
        printf("MCP_WP14_PROP|%s|%s|%s|%L\n"
          instName prop~>name prop~>valueType prop~>value)
      )
    )
  )
  printf("MCP_WP14_TOPOLOGY|%d|%d|%d|%d\n"
    instCount netCount terminalCount propertyCount)
  if(dbClose(cv) then
    printf("MCP_WP14_FACT_COMPLETE|true|true\n")
    exit(0)
  else
    exit(1)
  )
)
