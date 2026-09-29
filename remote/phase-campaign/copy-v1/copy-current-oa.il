; Copy exactly the current WP-14 schematic into a new work-library cell.
; Source and PDK are opened only for reading; no overwrite or cleanup.
sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
workLib = "MCP_WorkLib"
targetCell = "WP14_AUTO_PHASE_01_TB2"
sourceView = "schematic"

procedure(mcpWp14Topology(cv)
  list(length(cv~>instances) length(cv~>nets) length(cv~>terminals))
)

procedure(mcpWp14InstanceSignature(cv)
  let((records netName)
    records = nil
    foreach(inst cv~>instances
      records = cons(sprintf(nil "I|%s|%s|%s"
        inst~>name inst~>master~>libName inst~>master~>cellName) records)
      foreach(instTerm inst~>instTerms
        netName = if(instTerm~>net then instTerm~>net~>name else "UNCONNECTED")
        records = cons(sprintf(nil "T|%s|%s|%s"
          inst~>name instTerm~>term~>name netName) records)
      )
      foreach(prop inst~>prop
        records = cons(sprintf(nil "P|%s|%s|%s|%L"
          inst~>name prop~>name prop~>valueType prop~>value) records)
      )
    )
    sort(records 'alphalessp)
  )
)

procedure(mcpWp14NetSignature(cv)
  let((records netName)
    records = nil
    foreach(net cv~>nets
      records = cons(strcat("N|" net~>name) records)
    )
    foreach(term cv~>terminals
      netName = if(term~>net then term~>net~>name else "UNCONNECTED")
      records = cons(sprintf(nil "C|%s|%L|%s"
        term~>name term~>direction netName) records)
    )
    sort(records 'alphalessp)
  )
)

let((sourceCv targetCv existingCv copyResult sourceTopology targetTopology
  sameInstances sameNets closedTarget closedSource)
  sourceCv = dbOpenCellViewByType(sourceLib sourceCell sourceView "" "r")
  unless(sourceCv exit(1))
  sourceTopology = mcpWp14Topology(sourceCv)
  unless(equal(sourceTopology list(35 14 8))
    dbClose(sourceCv)
    exit(1)
  )
  existingCv = dbOpenCellViewByType(workLib targetCell sourceView "schematic" "r")
  when(existingCv
    dbClose(existingCv)
    dbClose(sourceCv)
    exit(1)
  )
  copyResult = errset(
    dbCopyCellView(sourceCv workLib targetCell sourceView nil nil nil)
    t
  )
  unless(copyResult
    dbClose(sourceCv)
    exit(1)
  )
  targetCv = car(copyResult)
  unless(targetCv
    dbClose(sourceCv)
    exit(1)
  )
  targetTopology = mcpWp14Topology(targetCv)
  sameInstances = equal(
    mcpWp14InstanceSignature(sourceCv)
    mcpWp14InstanceSignature(targetCv)
  )
  sameNets = equal(
    mcpWp14NetSignature(sourceCv)
    mcpWp14NetSignature(targetCv)
  )
  closedTarget = dbClose(targetCv)
  closedSource = dbClose(sourceCv)
  if(equal(sourceTopology targetTopology) && sameInstances && sameNets &&
      closedTarget && closedSource then
    printf("MCP_WP14_COPY|true|35|14|8|true|true|true\n")
    exit(0)
  else
    exit(1)
  )
)
