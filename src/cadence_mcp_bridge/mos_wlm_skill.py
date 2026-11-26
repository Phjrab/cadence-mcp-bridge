"""Render the IC615/GPDK090 single-finger W/L/m adapter for an owned instance."""

from typing import Literal

from .mos_wl_skill import _length_token


def render_mos_wlm_skill(
    master: Literal["nmos1v", "pmos1v"],
    *,
    length_nm: str | None = None,
    width_nm: str | None = None,
    multiplier: int | None = None,
) -> bytes:
    """Render only changed fields in L, total W, multiplier order.

    Input dimensions are normalized nanometers. The registered host and guest
    separately bind the approved target, candidate values, and runtime. The
    guest must provide the live callback identity verifier and inspect, save,
    and independently reopen the owned schematic after this fragment returns.
    """
    if master not in ("nmos1v", "pmos1v"):
        raise ValueError("unsupported GPDK090 MOS master")
    if multiplier is not None and (type(multiplier) is not int or multiplier not in (1, 6)):
        raise ValueError("the single-finger adapter accepts multiplier 1 or 6")
    values = (
        ("l", _length_token(length_nm) if length_nm is not None else None),
        ("w", _length_token(width_nm) if width_nm is not None else None),
        ("m", str(multiplier) if multiplier is not None else None),
    )
    steps = [f'list("{field}" "{value}")' for field, value in values if value is not None]
    if not steps:
        raise ValueError("at least one changed MOS field is required")
    entry = (
        "procedure(mcpMosApplyWL(inst)\n"
        f' mcpMosWlmApply(inst "{master}" list({" ".join(steps)})))\n'
    )
    return (_BODY + entry).encode("ascii")


_BODY = r"""; Trusted worker guards registered source, target, and callback identities.
procedure(mcpMosWlmParam(cdf field)
 let((param)
  param=cdfFindParamByName(cdf field)
  unless(param && stringp(param~>value)
    && strlen(param~>value)>0 && strlen(param~>value)<=128
   error("MCP_MOS_WLM_CDF_VALUE"))
  param))

procedure(mcpMosWlmValue(cdf field)
 mcpMosWlmParam(cdf field)~>value)

procedure(mcpMosWlmEqual(field observed expected)
 let((a b)
  if(field=="m" || field=="fingers" then observed==expected else
   a=cdfParseFloatString(observed)
   b=cdfParseFloatString(expected)
   ; OCEAN roundoff only. The host verifies exact normalized numeric equality.
   numberp(a) && numberp(b) && a>0 && b>0 && abs(a-b)<=b*1e-12)))

procedure(mcpMosWlmCheck(cdf before steps)
 let((field step wanted observed)
  foreach(field '("l" "w" "fw" "m" "fingers")
   step=assoc(if(field=="fw" then "w" else field) steps)
   wanted=if(step then cadr(step) else cadr(assoc(field before)))
   observed=mcpMosWlmValue(cdf field)
   unless(if(step then mcpMosWlmEqual(field observed wanted) else observed==wanted)
    error("MCP_MOS_WLM_GEOMETRY")))
  unless(assoc("l" steps) || assoc("w" steps)
   foreach(field '("as" "ad" "ps" "pd")
    unless(mcpMosWlmValue(cdf field)==cadr(assoc(field before))
     error("MCP_MOS_WLM_HELD_JUNCTION"))))))

procedure(mcpMosWlmApply(mcpInst mcpMaster mcpSteps)
 let((cdfgData cdfgForm mcpCdf mcpGeometry mcpJunctions mcpWritable mcpBefore mcpCallbacks
      mcpField mcpStep mcpPair mcpParam mcpBody mcpPersist mcpValue mcpProp mcpEffective)
  unless(mcpInst && mcpInst~>libName=="gpdk090" && mcpInst~>cellName==mcpMaster
    && mcpInst~>viewName=="symbol" error("MCP_MOS_WLM_MASTER"))
  mcpCdf=cdfGetInstCDF(mcpInst)
  cdfgData=mcpCdf
  cdfgForm=nil
  unless(cdfgData && cdfgData~>formInitProc=="PasCdfFormInit"
    && cdfgData~>doneProc=="PasCdfDone"
    && isCallable('PasCdfFormInit) && isCallable('PasCdfDone)
   error("MCP_MOS_WLM_HOOK_IDENTITY"))
  mcpGeometry='("l" "w" "fw" "m" "fingers")
  mcpJunctions='("as" "ad" "ps" "pd")
  mcpWritable=append(
   append(foreach(mapcar mcpStep mcpSteps car(mcpStep))
    if(assoc("w" mcpSteps) then list("fw") else nil))
   if(assoc("l" mcpSteps) || assoc("w" mcpSteps) then mcpJunctions else nil))
  mcpBefore=foreach(mapcar mcpField append(mcpGeometry mcpJunctions)
   list(mcpField mcpMosWlmValue(cdfgData mcpField)))
  unless(mcpMosWlmValue(cdfgData "fingers")=="1"
    && member(mcpMosWlmValue(cdfgData "m") '("1" "6"))
    && mcpMosWlmEqual("w" mcpMosWlmValue(cdfgData "w") mcpMosWlmValue(cdfgData "fw"))
   error("MCP_MOS_WLM_BASELINE"))

  mcpCallbacks=foreach(mapcar mcpStep mcpSteps
   mcpField=car(mcpStep)
   when(mcpMosWlmEqual(mcpField cadr(assoc(mcpField mcpBefore)) cadr(mcpStep))
    error("MCP_MOS_WLM_NO_CHANGE"))
   mcpBody=mcpMosWlmParam(cdfgData mcpField)~>callback
   unless(stringp(mcpBody) && strlen(mcpBody)>0 && strlen(mcpBody)<=4096
    error("MCP_MOS_WLM_CALLBACK_VALUE"))
   list(mcpField mcpBody))
  unless(mcpMosVerifyCallbacks(mcpInst mcpCallbacks)==t error("MCP_MOS_WLM_CALLBACK_IDENTITY"))
  printf("MCP_MOS_WL_STAGE|INIT\n")
  drain(poport)
  unless(errset(PasCdfFormInit(cdfgData) t) error("MCP_MOS_WLM_INIT"))
  unless(cdfgData==mcpCdf error("MCP_MOS_WLM_CDF_CONTEXT"))

  foreach(mcpStep mcpSteps
   mcpField=car(mcpStep)
   mcpPair=assoc(mcpField mcpCallbacks)
   mcpParam=mcpMosWlmParam(cdfgData mcpField)
   unless(mcpParam~>callback==cadr(mcpPair) error("MCP_MOS_WLM_CALLBACK_CHANGED"))
   printf("MCP_MOS_WL_STAGE|FIELD|%s\n" mcpField)
   drain(poport)
   mcpParam~>value=cadr(mcpStep)
   unless(mcpMosWlmEqual(mcpField mcpParam~>value cadr(mcpStep)) error("MCP_MOS_WLM_ASSIGNMENT"))
   unless(mcpParam~>callback==cadr(mcpPair) error("MCP_MOS_WLM_CALLBACK_CHANGED"))
   unless(errset(evalstring(cadr(mcpPair)) t) error("MCP_MOS_WLM_CALLBACK"))
   unless(cdfgData==mcpCdf error("MCP_MOS_WLM_CDF_CONTEXT")))
  mcpMosWlmCheck(cdfgData mcpBefore mcpSteps)

  ; Snapshot allowed CDF results before any explicit raw OA transfer.
  mcpPersist=foreach(mapcar mcpField mcpWritable
   mcpValue=mcpMosWlmValue(cdfgData mcpField)
   mcpProp=dbFindProp(mcpInst mcpField)
   when(mcpProp && mcpProp~>valueType!="string" error("MCP_MOS_WLM_OA_TYPE"))
   when(member(mcpField mcpJunctions) && !mcpMosWlmEqual(mcpField mcpValue mcpValue)
    error("MCP_MOS_WLM_JUNCTION"))
   list(mcpField mcpValue))
  printf("MCP_MOS_WL_STAGE|COMMIT\n")
  drain(poport)
  foreach(mcpPair mcpPersist
   mcpField=car(mcpPair) mcpValue=cadr(mcpPair)
   mcpProp=dbFindProp(mcpInst mcpField)
   when(mcpValue!=cadr(assoc(mcpField mcpBefore)) && (!mcpProp || mcpProp~>value!=mcpValue)
    unless(dbReplaceProp(mcpInst mcpField "string" mcpValue) error("MCP_MOS_WLM_OA_COMMIT"))
    mcpProp=dbFindProp(mcpInst mcpField)
    unless(mcpProp error("MCP_MOS_WLM_OA_READBACK")))
   when(mcpProp && (mcpProp~>valueType!="string" || mcpProp~>value!=mcpValue)
    error("MCP_MOS_WLM_OA_READBACK")))
  mcpEffective=cdfGetInstCDF(mcpInst)
  unless(mcpEffective && mcpEffective~>doneProc=="PasCdfDone"
   error("MCP_MOS_WLM_DONE_IDENTITY"))
  mcpMosWlmCheck(mcpEffective mcpBefore mcpSteps)

  printf("MCP_MOS_WL_STAGE|DONE\n")
  drain(poport)
  unless(errset(PasCdfDone(mcpInst) t) error("MCP_MOS_WLM_DONE"))
  mcpEffective=cdfGetInstCDF(mcpInst)
  unless(mcpEffective error("MCP_MOS_WLM_DONE_READBACK"))
  mcpMosWlmCheck(mcpEffective mcpBefore mcpSteps)
  foreach(mcpField mcpWritable
   mcpValue=mcpMosWlmValue(mcpEffective mcpField)
   mcpProp=dbFindProp(mcpInst mcpField)
   unless((mcpProp && mcpProp~>valueType=="string" && mcpProp~>value==mcpValue)
     || (!mcpProp && mcpValue==cadr(assoc(mcpField mcpBefore)))
    error("MCP_MOS_WLM_DONE_OA_READBACK"))
   when(member(mcpField mcpJunctions) && !mcpMosWlmEqual(mcpField mcpValue mcpValue)
    error("MCP_MOS_WLM_JUNCTION")))
  printf("MCP_MOS_WL_READY_FOR_SAVE_CHECK\n")
  drain(poport)
  t))

"""
