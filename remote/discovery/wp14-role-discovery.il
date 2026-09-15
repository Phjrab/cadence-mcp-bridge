; Fixed WP-14 names-only discovery. Private markers are consumed by the
; redaction helper through an anonymous pipe and are never persisted.
sourceLib = "MyDesignLib"
sourceCell = "Differential_Amplifier_TB2"
sourceView = "schematic"

procedure(mcpWp14SafeToken(value)
  stringp(value) && strlen(value) > 0 && strlen(value) <= 128 &&
    rexMatchp("^[A-Za-z0-9_!$<>/+.:@-]+$" value)
)

procedure(mcpWp14MasterClass(inst)
  let((libName cellName)
    libName = inst~>master~>libName
    cellName = inst~>master~>cellName
    cond(
      (equal(libName "analogLib") && member(cellName list("vdc" "vsource" "vpulse" "vsin"))
        "independent_voltage_source")
      (equal(libName "analogLib") && member(cellName list("idc" "isource" "ipulse" "isin"))
        "independent_current_source")
      (equal(libName "analogLib") && equal(cellName "res") "resistor")
      (equal(libName "analogLib") && equal(cellName "cap") "capacitor")
      (t nil)
    )
  )
)

procedure(mcpWp14AllowedSlots(masterClass)
  cond(
    (equal(masterClass "independent_voltage_source") list("dc" "vdc"))
    (equal(masterClass "independent_current_source") list("dc" "idc"))
    (equal(masterClass "resistor") list("r"))
    (equal(masterClass "capacitor") list("c"))
    (t nil)
  )
)

procedure(mcpWp14SlotClass(masterClass)
  cond(
    (equal(masterClass "independent_voltage_source") "voltage_dc_slot")
    (equal(masterClass "independent_current_source") "current_dc_slot")
    (equal(masterClass "resistor") "resistance_slot")
    (equal(masterClass "capacitor") "capacitance_slot")
    (t nil)
  )
)

procedure(mcpWp14EmitBlocker(role)
  printf("MCP_WP14_BLOCKER|%s|unsupported_candidate\n" role)
)

procedure(mcpWp14EmitCandidate(role masterClass connectionRole slotClass instName
  masterLib masterCell masterView pairString slotName)
  printf("MCP_WP14_PRIVATE|%s|%s|%s|%s|2|%s|%s|%s|%s|%s|%s\n"
    role masterClass connectionRole slotClass instName masterLib masterCell
    masterView pairString slotName)
)

let((cv instanceCount netCount terminalCount propertyCount masterClass allowedSlots
  selectedSlots slotClass pairTokens pairString unsafePrivate hasReference hasVdd
  hasVcm outputCount connectionRole lowerName closeResult)
  cv = dbOpenCellViewByType(sourceLib sourceCell sourceView "" "r")
  unless(cv
    mcpWp14EmitBlocker("VDD")
    mcpWp14EmitBlocker("VCM")
    mcpWp14EmitBlocker("load_condition")
    exit(1)
  )
  instanceCount = length(cv~>instances)
  netCount = length(cv~>nets)
  terminalCount = length(cv~>terminals)
  propertyCount = 0

  foreach(inst cv~>instances
    propertyCount = propertyCount + length(inst~>prop)
    masterClass = mcpWp14MasterClass(inst)
    if(masterClass then
      allowedSlots = mcpWp14AllowedSlots(masterClass)
      selectedSlots = nil
      foreach(prop inst~>prop
        when(member(prop~>name allowedSlots) &&
          member(prop~>valueType list("string" "float" "int"))
          selectedSlots = cons(prop~>name selectedSlots)
        )
      )
      if(length(selectedSlots) != 1 || length(inst~>instTerms) != 2 then
        if(equal(masterClass "independent_voltage_source") then
          mcpWp14EmitBlocker("VDD")
          mcpWp14EmitBlocker("VCM")
        else
          mcpWp14EmitBlocker("load_condition")
        )
      else
        pairTokens = nil
        unsafePrivate = nil
        hasReference = nil
        hasVdd = nil
        hasVcm = nil
        outputCount = 0
        foreach(instTerm inst~>instTerms
          if(instTerm~>net then
            lowerName = lowerCase(instTerm~>net~>name)
            unless(mcpWp14SafeToken(instTerm~>term~>name) &&
              mcpWp14SafeToken(instTerm~>net~>name)
              unsafePrivate = t
            )
            pairTokens = cons(strcat(instTerm~>term~>name ":" instTerm~>net~>name) pairTokens)
            when(member(lowerName list("0" "gnd" "gnd!")) hasReference = t)
            when(rexMatchp("vdd" lowerName) hasVdd = t)
            when(rexMatchp("vcm" lowerName) hasVcm = t)
            when(rexMatchp("out\|vop\|von\|vo" lowerName) outputCount = outputCount + 1)
          else
            unsafePrivate = t
          )
        )
        unless(mcpWp14SafeToken(inst~>name) &&
          mcpWp14SafeToken(inst~>master~>libName) &&
          mcpWp14SafeToken(inst~>master~>cellName) &&
          mcpWp14SafeToken(inst~>master~>viewName) &&
          mcpWp14SafeToken(car(selectedSlots))
          unsafePrivate = t
        )
        if(unsafePrivate then
          if(equal(masterClass "independent_voltage_source") then
            mcpWp14EmitBlocker("VDD")
            mcpWp14EmitBlocker("VCM")
          else
            mcpWp14EmitBlocker("load_condition")
          )
        else
          pairTokens = sort(pairTokens 'alphalessp)
          pairString = strcat(car(pairTokens) "," cadr(pairTokens))
          slotClass = mcpWp14SlotClass(masterClass)
          if(equal(masterClass "independent_voltage_source") then
            connectionRole = if(hasVdd then "global_supply_candidate"
              else if(hasReference then "reference_connected_two_terminal"
                else "nonreference_two_terminal"))
            mcpWp14EmitCandidate("VDD" masterClass connectionRole slotClass inst~>name
              inst~>master~>libName inst~>master~>cellName inst~>master~>viewName
              pairString car(selectedSlots))
            connectionRole = if(hasVcm then "common_mode_stimulus_candidate"
              else if(hasReference then "reference_connected_two_terminal"
                else "nonreference_two_terminal"))
            mcpWp14EmitCandidate("VCM" masterClass connectionRole slotClass inst~>name
              inst~>master~>libName inst~>master~>cellName inst~>master~>viewName
              pairString car(selectedSlots))
          else
            connectionRole = cond(
              (outputCount == 2 "differential_output_load_candidate")
              (outputCount == 1 "single_ended_output_load_candidate")
              (hasReference "reference_connected_two_terminal")
              (t "nonreference_two_terminal")
            )
            mcpWp14EmitCandidate("load_condition" masterClass connectionRole slotClass
              inst~>name inst~>master~>libName inst~>master~>cellName
              inst~>master~>viewName pairString car(selectedSlots))
          )
        )
      )
    else
      ; Non-allowlisted device masters are never interpreted as load roles.
      mcpWp14EmitBlocker("load_condition")
    )
    when(propertyCount > 1024
      mcpWp14EmitBlocker("VDD")
      mcpWp14EmitBlocker("VCM")
      mcpWp14EmitBlocker("load_condition")
    )
  )
  printf("MCP_WP14_TOPOLOGY|%d|%d|%d|%d\n"
    instanceCount netCount terminalCount propertyCount)
  closeResult = dbClose(cv)
  if(closeResult then
    printf("MCP_WP14_COMPLETE|true|true\n")
    exit(0)
  else
    exit(1)
  )
)
