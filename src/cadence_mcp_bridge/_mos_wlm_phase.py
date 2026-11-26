"""Finite W/L/m policy and SKILL checks for the registered native phase."""

# mypy: ignore-errors
# ruff: noqa: UP031, UP032

import re

WLM_AXES = ("l", "w", "m")

VERIFY_WLM_CALLBACKS = r"""
procedure(mcpMosVerifyCallbacks(inst rows)
 let((master base expected frame field body param child)
  master="@MASTER@"
  expected='(@AXES@)
  mosRequire(and(inst~>name=="@TARGET@" inst~>libName=="gpdk090"
                 inst~>cellName==master inst~>viewName=="symbol"
                 equal(mapcar('car rows) expected)))
  base=cdfGetBaseCellCDF(ddGetObj("gpdk090" master))
  mosRequire(base)
  frame=sprintf(nil "headless_wlm_v1|%s|%s\n" master "@AXISTOKEN@")
  foreach(row rows
   mosRequire(length(row)==2)
   field=car(row) body=cadr(row)
   mosRequire(and(stringp(body) 0<strlen(body) strlen(body)<=4096))
   param=cdfFindParamByName(base field)
   mosRequire(and(param param~>callback==body))
   frame=strcat(frame sprintf(nil "%s|%d\n" field strlen(body)) body "\n"))
  child=ipcBeginProcess("/usr/bin/python -E -s -B @WORK@/verify-wlm-callbacks.py")
  mosRequire(child)
  ipcWriteProcess(child strcat(frame "END\n"))
  ipcWait(child)
  mosRequire(and(!ipcIsAliveProcess(child) ipcGetExitStatus(child)==0
                 ipcReadProcess(child 1)=="C1_WLM_CALLBACKS_VERIFIED\n"))
  t))
"""


def wlm_overrides(native, axes):
    derived = (
        native.WIDTH_SIZING_OVERRIDES[1:]
        if "w" in axes
        else native.SIZING_OVERRIDES[1:]
        if "l" in axes
        else ()
    )
    return tuple(axes) + derived


def wlm_route(native, scope):
    route, plan, subject = scope["route_qualification"], scope["plan"], scope["subject"]
    target, support = route["target"], route["support"]
    master = target["instance"]["master_cell"]
    native.require(master in native.SLOTS, "wlm_master")
    slot, rail = native.SLOTS[master]
    path = "DUT/" + slot
    anchor = target["instance"]["property_name"]
    allowed_m = support.get("m")
    native.require(
        (route["source_library"], route["source_cell"], route["testbench_cell"])
        == (native.SOURCE, native.DUT, native.TB)
        and target["instance"]
        == dict(
            instance_path=path,
            master_library="gpdk090",
            master_cell=master,
            master_view="symbol",
            property_name=anchor,
        )
        and (target["netlist_path"], target["netlist_model"]) == (path, "gpdk090_" + master)
        and target["netlist_terminals"] == ["vout", "vin", rail, rail]
        and (support["cadence_version"], support["pdk_release"]) == ("6.1.5.500.15", "4.6")
        and support["pdk_identity_sha256"] == native.SIZING_PDK_TREE_SHA256
        and support["adapter_sha256"] == native.WLM_RENDERER_SHA256
        and anchor in WLM_AXES
        and support.get(anchor) is not None
        and plan["baseline"] == route["baseline"]
        and plan["target"] == target
        and plan["route_sha256"] == subject["route_sha256"]
        and subject["owned_cell"] == native.DUT
        and subject["owned_view"] == "schematic"
        and re.match(r"^CmosLongMos[A-Za-z0-9]{3,40}\Z", subject["owned_library"]),
        "wlm_route",
    )
    current, requested, expected = plan["current"], plan["requested"], plan["expected"]
    required = set(WLM_AXES)
    native.require(
        set(current) == set(expected) == required and set(requested).issubset(required),
        "wlm_dimension_fields",
    )
    for axis in WLM_AXES:
        chosen = requested.get(axis)
        native.require(
            expected[axis] == (current[axis] if chosen is None else chosen), "wlm_held_axis"
        )
        if axis == "m":
            native.require(
                type(expected[axis]) is int and expected[axis] in (1, 6), "wlm_multiplier"
            )
            if chosen is not None:
                native.require(
                    isinstance(allowed_m, list)
                    and bool(allowed_m)
                    and all(type(item) is int and item in (1, 6) for item in allowed_m)
                    and len(allowed_m) == len(set(allowed_m))
                    and chosen in allowed_m,
                    "wlm_multiplier_admission",
                )
        else:
            if chosen is not None:
                native.require(isinstance(support.get(axis), dict), "wlm_length_admission")
            for dimension in (current[axis], expected[axis]):
                native.require(
                    set(dimension) == set(("value", "unit")) and dimension["unit"] == "nm",
                    "wlm_normalized_dimension",
                )
                native.finite_length(dimension["value"], dimension["unit"])
    native.require(type(current["m"]) is int and current["m"] == 1, "wlm_baseline_multiplier")
    axes = [axis for axis in WLM_AXES if expected[axis] != current[axis]]
    overrides = wlm_overrides(native, axes)
    native.require(
        axes
        and plan["changed"] == axes
        and plan["allowed_derived"] == list(overrides[len(axes) :]),
        "wlm_change_set",
    )
    before = route["before"]
    native.require(
        set(before) == set(native.PROPERTIES)
        and before["model"]["cdf_value"] == target["netlist_model"]
        and before["dfm"]["cdf_value"] == "Minimum"
        and all(value is None for value in before["nf"].values()),
        "wlm_baseline",
    )
    wlm_readback(native, before, before, current, ())
    return route


def wlm_readback(native, before, actual, expected, axes):
    overrides = wlm_overrides(native, axes)
    for name in native.PROPERTIES:
        row, old = actual[name], before[name]
        native.require(
            (row["cdf_type"], row["cdf_units"]) == (old["cdf_type"], old["cdf_units"])
            and (name in overrides or row == old),
            "sizing_property_conservation",
        )
        if name in native.SIZING_OVERRIDES[1:]:
            native.cdf_geometry(row, name)
            if row != old:
                native.require(
                    row["oa_type"] == "string" and row["oa_value"] == row["cdf_value"],
                    "sizing_geometry_persistence",
                )
    for name in ("w", "fw", "l"):
        native.sizing_dimension(actual[name], expected["w" if name == "fw" else name])
    for name, value in (("m", expected["m"]), ("fingers", 1)):
        row = actual[name]
        native.require(
            row["cdf_type"] == "instData"
            and row["cdf_value"] == str(value)
            and row["oa_type"] == "string"
            and row["oa_value"] == str(value),
            "wlm_count_readback",
        )


def wlm_skill_expected(expected, axes):
    dimensions = []
    for name in axes:
        if name == "m":
            dimensions.append('("m" "%d")' % expected["m"])
        else:
            dimensions.append('("%s" "%sn")' % (name, expected[name]["value"]))
            if name == "w":
                dimensions.append('("fw" "%sn")' % expected[name]["value"])
    return (
        "let((param prop target effective stored)\n"
        " foreach(row '(" + " ".join(dimensions) + ")\n"
        "  param=cdfFindParamByName(batchCdf car(row)) prop=dbFindProp(inst car(row))\n"
        '  mosRequire(and(param prop stringp(param~>value) prop~>valueType=="string"))\n'
        '  if(car(row)=="m" then\n'
        "   mosRequire(and(param~>value==cadr(row) prop~>value==cadr(row)))\n"
        "  else\n"
        "   target=cdfParseFloatString(cadr(row))\n"
        "   effective=cdfParseFloatString(param~>value) stored=cdfParseFloatString(prop~>value)\n"
        "   mosRequire(and(numberp(target) numberp(effective) numberp(stored)\n"
        "      abs(effective-target)<=target*1e-12 abs(stored-target)<=target*1e-12)))))"
    )
