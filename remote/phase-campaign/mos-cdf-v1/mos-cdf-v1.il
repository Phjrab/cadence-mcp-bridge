; Fixed read-only CDF inventory for the fourteen gpdk090 MOS instances.
sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"
selectedNames = list("w" "l" "m" "nf" "fw" "width" "length"
  "fingers" "totalWidth")

let((cv mosCount cdfCount instCDF masterLib masterCell)
  cv = dbOpenCellViewByType(sourceLib sourceCell sourceView "" "r")
  unless(cv exit(1))
  mosCount = 0
  cdfCount = 0
  printf("MCP_MOS_CDF_BEGIN|true\n")
  foreach(inst cv~>instances
    masterLib = inst~>master~>libName
    masterCell = inst~>master~>cellName
    when(equal(masterLib "gpdk090") &&
      member(masterCell list("nmos1v" "pmos1v"))
      mosCount = mosCount + 1
      instCDF = cdfGetInstCDF(inst)
      if(instCDF then
        cdfCount = cdfCount + 1
        printf("MCP_MOS_CDF_INST|%s|%s|true\n" inst~>name masterCell)
        foreach(param instCDF~>parameters
          when(member(param~>name selectedNames)
            printf("MCP_MOS_CDF_PARAM|%s|%s|%L|%L\n"
              inst~>name param~>name param~>value param~>defValue)
          )
        )
      else
        printf("MCP_MOS_CDF_INST|%s|%s|false\n" inst~>name masterCell)
      )
    )
  )
  printf("MCP_MOS_CDF_COUNTS|%d|%d|%d|%d\n"
    length(cv~>instances) length(cv~>nets) mosCount cdfCount)
  if(dbClose(cv) then
    printf("MCP_MOS_CDF_COMPLETE|true|true\n")
    exit(0)
  else
    exit(1)
  )
)
