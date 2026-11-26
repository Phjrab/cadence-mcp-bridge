"""Render the bounded IC615/GPDK090 single-finger MOS edit fragment.

The trusted guest owns the durable claim, installed runtime pin, registered OA
binding, callback identity verifier, footprint checks, save, and detached reopen.
This fragment never opens a view, saves, or dispatches work on its own.
"""

import re
from typing import Literal

_NM = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", re.ASCII)


def _length_token(nm: str) -> str:
    if not isinstance(nm, str) or len(nm) > 24 or not _NM.fullmatch(nm):
        raise ValueError("expected a bounded decimal nanometer value")
    if not nm.strip("0."):
        raise ValueError("expected a positive nanometer value")
    return nm + "n"


def render_mos_wl_skill(
    master: Literal["nmos1v", "pmos1v"],
    *,
    length_nm: str | None = None,
    width_nm: str | None = None,
    width_field: Literal["w", "fw"] | None = None,
) -> bytes:
    """Bind normalized request values to a fixed guest-side entry point.

    The guest must select the approved width driver from its registered route.
    The initial length-only route does not need a width driver. The two-axis
    order is length then width and requires separate native qualification.
    """
    if master not in ("nmos1v", "pmos1v"):
        raise ValueError("unsupported GPDK090 MOS master")
    if length_nm is None and width_nm is None:
        raise ValueError("at least one MOS dimension is required")
    if width_nm is not None and width_field not in ("w", "fw"):
        raise ValueError("requested width requires an approved width field")
    if width_nm is None and width_field is not None:
        raise ValueError("a width field requires a width request")

    length = f'"{_length_token(length_nm)}"' if length_nm is not None else "nil"
    width = f'"{_length_token(width_nm)}"' if width_nm is not None else "nil"
    steps = []
    if length_nm is not None:
        steps.append(f'list("l" {length})')
    if width_nm is not None:
        steps.append(f'list("{width_field}" {width})')
    entry = (
        f"procedure(mcpMosApplyWL(inst)\n"
        f' mcpMosWlApply(inst "{master}" {length} {width} list({" ".join(steps)})))\n'
    )
    return (_BODY + entry).encode("ascii")


_BODY = r"""; Fixed length/width adapter. Only the guest wrapper calls mcpMosApplyWL.
procedure(mcpMosWlParam(cdf field)
 let((param)
  param=cdfFindParamByName(cdf field)
  unless(param && stringp(param~>value)
    && strlen(param~>value)>0 && strlen(param~>value)<=128
   error("MCP_MOS_WL_CDF_VALUE"))
  param))

procedure(mcpMosWlValue(cdf field)
 mcpMosWlParam(cdf field)~>value)

procedure(mcpMosWlSameLength(actual expected)
 let((a b)
  a=cdfParseFloatString(actual)
  b=cdfParseFloatString(expected)
  ; Round-off guard only. The host compares exact normalized values.
  numberp(a) && numberp(b) && a>0 && b>0 && abs(a-b)<=b*1e-12))

procedure(mcpMosWlCheckGeometry(cdf expectedL expectedW)
 unless(mcpMosWlSameLength(mcpMosWlValue(cdf "l") expectedL)
   && mcpMosWlSameLength(mcpMosWlValue(cdf "w") expectedW)
   && mcpMosWlSameLength(mcpMosWlValue(cdf "fw") expectedW)
   && mcpMosWlValue(cdf "m")=="1" && mcpMosWlValue(cdf "fingers")=="1"
  error("MCP_MOS_WL_GEOMETRY")))

procedure(mcpMosWlApply(mcpInst mcpMaster mcpRequestedL mcpRequestedW mcpSteps)
 let((cdfgData cdfgForm mcpFields mcpOriginal mcpCallbacks mcpEffective mcpParam mcpBody
      mcpField mcpStep mcpPair mcpOldValue mcpNewValue mcpExpectedL mcpExpectedW mcpProp)
  unless(mcpInst && mcpInst~>libName=="gpdk090" && mcpInst~>cellName==mcpMaster
    && mcpInst~>viewName=="symbol" error("MCP_MOS_WL_MASTER"))
  cdfgData=cdfGetInstCDF(mcpInst)
  cdfgForm=nil
  unless(cdfgData && cdfgData~>formInitProc=="PasCdfFormInit"
    && cdfgData~>doneProc=="PasCdfDone"
    && isCallable('PasCdfFormInit) && isCallable('PasCdfDone)
   error("MCP_MOS_WL_HOOK_IDENTITY"))
  mcpFields=list("l" "w" "fw" "as" "ad" "ps" "pd")
  mcpOriginal=foreach(mapcar mcpField mcpFields mcpMosWlValue(cdfgData mcpField))
  mcpMosWlCheckGeometry(cdfgData car(mcpOriginal) cadr(mcpOriginal))
  mcpExpectedL=if(mcpRequestedL then mcpRequestedL else car(mcpOriginal))
  mcpExpectedW=if(mcpRequestedW then mcpRequestedW else cadr(mcpOriginal))
  when(mcpMosWlSameLength(car(mcpOriginal) mcpExpectedL)
    && mcpMosWlSameLength(cadr(mcpOriginal) mcpExpectedW) error("MCP_MOS_WL_NO_CHANGE"))

  mcpCallbacks=foreach(mapcar mcpStep mcpSteps
   mcpField=car(mcpStep)
   mcpBody=mcpMosWlParam(cdfgData mcpField)~>callback
   unless(stringp(mcpBody) && strlen(mcpBody)>0 && strlen(mcpBody)<=4096
    error("MCP_MOS_WL_CALLBACK_VALUE"))
   list(mcpField mcpBody))
  ; The wrapper compares each live body with the reviewed digest before init.
  unless(mcpMosVerifyCallbacks(mcpInst mcpCallbacks)==t error("MCP_MOS_WL_CALLBACK_IDENTITY"))
  printf("MCP_MOS_WL_STAGE|INIT\n")
  unless(errset(PasCdfFormInit(cdfgData) t) error("MCP_MOS_WL_INIT"))

  foreach(mcpStep mcpSteps
   mcpField=car(mcpStep)
   mcpPair=assoc(mcpField mcpCallbacks)
   mcpParam=mcpMosWlParam(cdfgData mcpField)
   unless(mcpParam~>callback==cadr(mcpPair) error("MCP_MOS_WL_CALLBACK_CHANGED"))
   printf("MCP_MOS_WL_STAGE|FIELD|%s\n" mcpField)
   mcpParam~>value=cadr(mcpStep)
   unless(mcpMosWlSameLength(mcpParam~>value cadr(mcpStep)) error("MCP_MOS_WL_ASSIGNMENT"))
   unless(mcpParam~>callback==cadr(mcpPair) error("MCP_MOS_WL_CALLBACK_CHANGED"))
   unless(errset(evalstring(cadr(mcpPair)) t) error("MCP_MOS_WL_CALLBACK")))
  mcpMosWlCheckGeometry(cdfgData mcpExpectedL mcpExpectedW)

  printf("MCP_MOS_WL_STAGE|COMMIT\n")
  foreach(mcpField mcpFields
   mcpOldValue=car(mcpOriginal)
   mcpOriginal=cdr(mcpOriginal)
   mcpNewValue=mcpMosWlValue(cdfgData mcpField)
   mcpProp=dbFindProp(mcpInst mcpField)
   when(mcpProp && mcpProp~>valueType!="string" error("MCP_MOS_WL_OA_TYPE"))
   when(mcpNewValue!=mcpOldValue && (!mcpProp || mcpProp~>value!=mcpNewValue)
    unless(dbReplaceProp(mcpInst mcpField "string" mcpNewValue) error("MCP_MOS_WL_OA_COMMIT"))
    mcpProp=dbFindProp(mcpInst mcpField)
    unless(mcpProp error("MCP_MOS_WL_OA_READBACK")))
   when(mcpProp && (mcpProp~>valueType!="string" || mcpProp~>value!=mcpNewValue)
    error("MCP_MOS_WL_OA_READBACK")))
  mcpEffective=cdfGetInstCDF(mcpInst)
  unless(mcpEffective && mcpEffective~>doneProc=="PasCdfDone"
   error("MCP_MOS_WL_DONE_IDENTITY"))
  mcpMosWlCheckGeometry(mcpEffective mcpExpectedL mcpExpectedW)

  printf("MCP_MOS_WL_STAGE|DONE\n")
  unless(errset(PasCdfDone(mcpInst) t) error("MCP_MOS_WL_DONE"))
  mcpEffective=cdfGetInstCDF(mcpInst)
  unless(mcpEffective error("MCP_MOS_WL_DONE_READBACK"))
  mcpMosWlCheckGeometry(mcpEffective mcpExpectedL mcpExpectedW)
  foreach(mcpField mcpFields mcpMosWlValue(mcpEffective mcpField))
  printf("MCP_MOS_WL_READY_FOR_SAVE_CHECK\n")
  t))

"""
