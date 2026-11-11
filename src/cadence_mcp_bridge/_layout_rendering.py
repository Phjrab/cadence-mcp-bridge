"""Fixed layout SKILL renderer shared with the Python 2.6 worker.

Only registered cellview names, collector selectors and integer DBU commands
enter this module. It accepts no expression, command, file path or SKILL text.
"""

# mypy: ignore-errors
# ruff: noqa: UP031
import json
import re
from decimal import Decimal, localcontext

NAME = r"^[A-Za-z][A-Za-z0-9_#-]{0,63}$"
LOGICAL = r"^[a-z][a-z0-9-]{0,63}$"
ORIENTATIONS = ("R0", "R90", "R180", "R270", "MX", "MY", "MXR90", "MYR90")


def token(value, pattern=NAME):
    try:
        strings = (basestring,)
    except NameError:
        strings = (str,)
    if not isinstance(value, strings):
        raise ValueError("layout_name_required")
    match = re.match(pattern, value)
    if match is None or match.end() != len(value):
        raise ValueError("layout_name_rejected")
    return value


def quote(value, logical=False):
    return json.dumps(token(value, LOGICAL if logical else NAME), ensure_ascii=True)


def integer(value):
    try:
        integers = (int, long)
    except NameError:
        integers = (int,)
    if type(value) not in integers or not -2147483647 <= value <= 2147483647:
        raise ValueError("layout_integer_dbu_required")
    return value


def coordinate(value, dbu):
    integer(value)
    if type(dbu) is not int or not 0 < dbu <= 1000000000:
        raise ValueError("layout_dbu_required")
    # Exact decimal division, never binary float rounding before emitting SKILL.
    with localcontext() as context:
        context.prec = 128
        return format(Decimal(value) / Decimal(dbu), "f")


def point(value, dbu):
    if set(value) != set(("x", "y")):
        raise ValueError("layout_point_shape")
    return "list(%s %s)" % (coordinate(value["x"], dbu), coordinate(value["y"], dbu))


def bbox(value, dbu):
    if set(value) != set(("lower_left", "upper_right")):
        raise ValueError("layout_bbox_shape")
    low, high = value["lower_left"], value["upper_right"]
    if low["x"] >= high["x"] or low["y"] >= high["y"]:
        raise ValueError("layout_positive_area_required")
    return "list(%s %s)" % (point(low, dbu), point(high, dbu))


def binding(value):
    if set(value) != set(("library", "cell", "view")) or value["view"] != "layout":
        raise ValueError("layout_cellview_binding")
    return " ".join(quote(value[key]) for key in ("library", "cell", "view"))


PRELUDE = r"""
procedure(mcpLayoutFail(reason)
  printf("MCP_LAYOUT_ERROR|%s\n" reason)
  exit(1)
)
procedure(mcpLayoutId(obj)
  let((p)
    p=dbFindProp(obj "mcpLayoutObjectId")
    if(p then p~>value else "-")
  )
)
procedure(mcpLayoutBox(b dbu)
  printf("|%d|%d|%d|%d" round(xCoord(car(b))*dbu)
    round(yCoord(car(b))*dbu) round(xCoord(cadr(b))*dbu)
    round(yCoord(cadr(b))*dbu))
)
procedure(mcpLayoutCollect(cv)
  let((tf dbu grid count)
    tf=techGetTechFile(cv)
    unless(tf mcpLayoutFail("technology_missing"))
    dbu=cv~>DBUPerUU
    grid=techGetMfgGridResolution(tf)
    unless(numberp(dbu) && dbu>0 && numberp(grid) && grid>0
      mcpLayoutFail("technology_units_missing"))
    unless(abs(grid*dbu-round(grid*dbu))<0.0000001
      mcpLayoutFail("manufacturing_grid_not_integral_dbu"))
    printf("MCP_LAYOUT_FRAME|1\nTECH|%d|%d\n" dbu round(grid*dbu))
    foreach(lp cv~>lpps
      printf("LPP|%s|%s\n" lp~>layerName lp~>purpose)
    )
    count=0
    foreach(inst cv~>instances
      count=count+1
      when(count>4096 mcpLayoutFail("instance_limit"))
      printf("I|%s|%s|%s|%s|%s|%s|%d|%d|%s"
        mcpLayoutId(inst) inst~>name inst~>libName inst~>cellName
        inst~>viewName inst~>orient round(xCoord(inst~>xy)*dbu)
        round(yCoord(inst~>xy)*dbu) if(inst~>master~>isParamCell then "1" else "0"))
      mcpLayoutBox(inst~>bBox dbu)
      printf("\n")
    )
    count=0
    foreach(shape cv~>shapes
      unless(shape~>pin
        count=count+1
        when(count>4096 mcpLayoutFail("shape_limit"))
        unless(shape~>objType=="rect" mcpLayoutFail("unsupported_source_shape"))
        printf("S|%s|rect|%s|%s" mcpLayoutId(shape) shape~>layerName shape~>purpose)
        mcpLayoutBox(shape~>bBox dbu)
        printf("\n")
      )
    )
    count=0
    foreach(term cv~>terminals
      foreach(pin term~>pins
        foreach(fig pin~>figs
          count=count+1
          when(count>1024 mcpLayoutFail("pin_limit"))
          unless(fig~>objType=="rect" mcpLayoutFail("unsupported_source_pin"))
          unless(term~>net && pin~>net && eq(term~>net pin~>net)
            mcpLayoutFail("pin_connection_not_verified"))
          printf("P|%s|%s|%s|%s|%s" mcpLayoutId(fig) fig~>layerName
            fig~>purpose term~>net~>name term~>name)
          mcpLayoutBox(fig~>bBox dbu)
          printf("\n")
        )
      )
    )
    printf("END_LAYOUT_FRAME\n")
  )
)
"""


def inspect_script(cellview):
    return (
        PRELUDE + '\ncv=dbOpenCellViewByType(%s "maskLayout" "r")\n'
        'unless(cv mcpLayoutFail("source_open_failed"))\n'
        "mcpLayoutCollect(cv)\ndbClose(cv)\nexit()\n" % binding(cellview)
    ).encode("ascii")


def selector_expression(selector, dbu):
    """Re-resolve by semantic selector within this opened revision, never a handle."""
    kind = selector.get("kind")
    if kind == "instance" and set(selector) == set(("kind", "name")):
        return "setof(o cv~>instances equal(o~>name %s))" % quote(selector["name"])
    if kind in ("rect", "pin") and set(selector) == set(("kind", "layer", "purpose", "bbox_dbu")):
        return (
            'setof(o cv~>shapes o~>objType=="rect" && equal(o~>layerName %s) '
            "&& equal(o~>purpose %s) && equal(o~>bBox %s))"
            % (
                quote(selector["layer"]),
                quote(selector["purpose"]),
                bbox(selector["bbox_dbu"], dbu),
            )
        )
    raise ValueError("layout_selector_not_supported")


def tags_script(selectors, dbu):
    lines = []
    for object_id in sorted(selectors):
        lines.extend(
            [
                "matches=%s" % selector_expression(selectors[object_id], dbu),
                'unless(length(matches)==1 mcpLayoutFail("ambiguous_object_selector"))',
                'dbReplaceProp(car(matches) "mcpLayoutObjectId" "string" %s)'
                % quote(object_id, True),
            ]
        )
    return "\n".join(lines) + "\n"


def edits_script(edits, technology):
    dbu = technology["dbu_per_um"]
    allowed = set((p["layer"], p["purpose"]) for p in technology["allowed_layer_purposes"])
    grid = integer(technology["manufacturing_grid_dbu"])
    if grid <= 0 or not isinstance(edits, (tuple, list)) or not 1 <= len(edits) <= 128:
        raise ValueError("layout_edit_bounds")
    lines = []
    for edit in edits:
        object_id = quote(edit["object_id"], True)
        if edit["kind"] == "move":
            dx, dy = integer(edit["dx_dbu"]), integer(edit["dy_dbu"])
            if dx % grid or dy % grid:
                raise ValueError("layout_move_off_grid")
            lines.extend(
                [
                    "matches=append(setof(o cv~>instances equal(mcpLayoutId(o) %s)) "
                    "setof(o cv~>shapes equal(mcpLayoutId(o) %s)))" % (object_id, object_id),
                    'unless(length(matches)==1 mcpLayoutFail("move_identity_not_unique"))',
                    'unless(dbMoveFig(car(matches) cv list(list(%s %s) "R0" 1)) '
                    'mcpLayoutFail("move_failed"))' % (coordinate(dx, dbu), coordinate(dy, dbu)),
                ]
            )
            continue
        if edit["kind"] not in ("add_rect", "add_pin"):
            raise ValueError("layout_operation_not_supported")
        obj = edit["shape"] if edit["kind"] == "add_rect" else edit["pin"]
        if edit["kind"] == "add_pin" and obj.get("label") is not None:
            raise ValueError("layout_pin_label_not_supported")
        if (obj["layer"], obj["purpose"]) not in allowed:
            raise ValueError("layout_layer_purpose_not_registered")
        for corner in (obj["bbox_dbu"]["lower_left"], obj["bbox_dbu"]["upper_right"]):
            if integer(corner["x"]) % grid or integer(corner["y"]) % grid:
                raise ValueError("layout_rectangle_off_grid")
        lines.extend(
            [
                "fig=dbCreateRect(cv list(%s %s) %s)"
                % (quote(obj["layer"]), quote(obj["purpose"]), bbox(obj["bbox_dbu"], dbu)),
                'unless(fig mcpLayoutFail("rectangle_create_failed"))',
                'dbReplaceProp(fig "mcpLayoutObjectId" "string" %s)' % object_id,
            ]
        )
        if edit["kind"] == "add_pin":
            lines.extend(
                [
                    "net=dbFindNetByName(cv %s)" % quote(obj["net_id"], True),
                    "unless(net net=dbCreateNet(cv %s))" % quote(obj["net_id"], True),
                    'when(dbFindTermByName(cv %s) mcpLayoutFail("terminal_already_exists"))'
                    % quote(obj["terminal_id"], True),
                    'term=dbCreateTerm(net %s "inputOutput")' % quote(obj["terminal_id"], True),
                    "unless(term && dbCreatePin(net fig %s term) "
                    'mcpLayoutFail("pin_create_failed"))' % quote(obj["terminal_id"], True),
                ]
            )
    return "\n".join(lines) + "\n"


def terminals_preflight(edits):
    terminals, lines = set(), []
    for edit in edits:
        if edit["kind"] == "add_pin":
            name = token(edit["pin"]["terminal_id"], LOGICAL)
            if name in terminals:
                raise ValueError("layout_duplicate_terminal")
            terminals.add(name)
            lines.append(
                "when(dbFindTermByName(cv %s) "
                'mcpLayoutFail("terminal_already_exists"))' % quote(name, True)
            )
    return "\n".join(lines) + "\n"


def write_script(source, target, selectors, technology, edits=None):
    if source == target:
        raise ValueError("layout_distinct_cellview_required")
    source_text, target_text = binding(source), binding(target)
    lines = [
        PRELUDE,
        'when(ddGetObj(%s) mcpLayoutFail("destination_already_exists"))' % target_text,
        'src=dbOpenCellViewByType(%s "maskLayout" "r")' % source_text,
        'unless(src mcpLayoutFail("source_open_failed"))',
        # Copy never overwrites. Source stays read-only for the whole session.
        "cv=dbCopyCellView(src %s nil nil nil)" % target_text,
        'unless(cv mcpLayoutFail("copy_failed"))',
        "dbClose(src)",
        tags_script(selectors, technology["dbu_per_um"]),
    ]
    if edits is not None:
        lines.append(edits_script(edits, technology))
    lines.extend(
        [
            'unless(dbSave(cv) mcpLayoutFail("save_failed"))',
            "dbClose(cv)",
            'cv=dbOpenCellViewByType(%s "maskLayout" "r")' % target_text,
            'unless(cv mcpLayoutFail("reopen_failed"))',
            "mcpLayoutCollect(cv)",
            "dbClose(cv)",
            'printf("MCP_LAYOUT_SAVED_REOPENED|1\\n")',
            "exit()",
        ]
    )
    return ("\n".join(lines) + "\n").encode("ascii")


def apply_script(target, selectors, technology, edits):
    """One exact-baseline edit of a registered, freshly forked owned revision."""
    target_text = binding(target)
    lines = [
        PRELUDE,
        'cv=dbOpenCellViewByType(%s "maskLayout" "a")' % target_text,
        'unless(cv mcpLayoutFail("working_revision_open_failed"))',
        terminals_preflight(edits),
        tags_script(selectors, technology["dbu_per_um"]),
        edits_script(edits, technology),
        'unless(dbSave(cv) mcpLayoutFail("save_failed"))',
        "dbClose(cv)",
        'cv=dbOpenCellViewByType(%s "maskLayout" "r")' % target_text,
        'unless(cv mcpLayoutFail("reopen_failed"))',
        "mcpLayoutCollect(cv)",
        "dbClose(cv)",
        'printf("MCP_LAYOUT_SAVED_REOPENED|1\\n")',
        "exit()",
    ]
    return ("\n".join(lines) + "\n").encode("ascii")


def probe_script(libraries, candidates):
    """Operator-only bounded API/technology/source-existence observation."""
    if not 1 <= len(libraries) <= 8 or len(candidates) > 8:
        raise ValueError("layout_probe_scope_bound")
    apis = (
        "dbOpenCellViewByType",
        "dbCopyCellView",
        "dbMoveFig",
        "dbCreateRect",
        "dbCreateNet",
        "dbCreateTerm",
        "dbCreatePin",
        "dbCreateInst",
        "dbSave",
        "dbClose",
        "techGetTechFile",
        "techGetMfgGridResolution",
        "techGetDBUPerUU",
        "techGetLayerFunctions",
        "techGetLP",
        "techBindTechFile",
    )
    lines = [PRELUDE, 'printf("MCP_LAYOUT_PROBE|1\\n")']
    for api in apis:
        lines.append('printf("API|%s|%%L\\n" isCallable(\'%s))' % (api, api))
    for library in libraries:
        name = quote(library)
        lines.extend(
            [
                "lib=ddGetObj(%s)" % name,
                "when(lib && isCallable('techGetDBUPerUU) && isCallable('techGetLayerFunctions)",
                "  tf=techGetTechFile(lib)",
                "  when(tf",
                '    printf("TECHLIB|%s|%%d|%%.12g\\n" techGetDBUPerUU(tf) '
                "techGetMfgGridResolution(tf))" % token(library),
                "    count=0",
                "    foreach(layer techGetLayerFunctions(tf)",
                '      when(count<32 && techGetLP(tf car(layer) "drawing")',
                '        printf("LPP|%s|%%s|drawing\\n" car(layer))' % token(library),
                "        count=count+1)",
                "    )",
                "  )",
                ")",
            ]
        )
    for candidate in candidates:
        lines.append(
            'printf("VIEW|%s|%s|%%s\\n" if(ddGetObj(%s) then "1" else "0"))'
            % (token(candidate["library"]), token(candidate["cell"]), binding(candidate))
        )
    lines.extend(['printf("END_LAYOUT_PROBE\\n")', "exit()"])
    return ("\n".join(lines) + "\n").encode("ascii")


def seed_script(library, library_path, technology_library, master_cell, seed_cell, technology, lpp):
    """Create a NEW owned basic master+instance seed; no vendor PCell inference."""
    if not re.match(r"^/[A-Za-z0-9_./-]{1,511}$", library_path) or any(
        p in ("", ".", "..") for p in library_path[1:].split("/")
    ):
        raise ValueError("layout_seed_registered_path_required")
    if library == technology_library or master_cell == seed_cell:
        raise ValueError("layout_seed_identity_collision")
    allowed = [(p["layer"], p["purpose"]) for p in technology["allowed_layer_purposes"]]
    if (lpp["layer"], lpp["purpose"]) not in allowed:
        raise ValueError("layout_seed_observed_lpp_required")
    dbu, grid = technology["dbu_per_um"], integer(technology["manufacturing_grid_dbu"])
    if grid <= 0:
        raise ValueError("layout_seed_observed_grid_required")
    extent, offset = coordinate(grid * 10, dbu), coordinate(grid * 20, dbu)
    rect = "list(list(0 0) list(%s %s))" % (extent, extent)
    master = {"library": library, "cell": master_cell, "view": "layout"}
    seed = {"library": library, "cell": seed_cell, "view": "layout"}
    lines = [
        PRELUDE,
        'when(ddGetObj(%s) mcpLayoutFail("seed_library_already_exists"))' % quote(library),
        "lib=ddCreateLib(%s %s)" % (quote(library), json.dumps(library_path)),
        'unless(lib mcpLayoutFail("seed_library_create_failed"))',
        'unless(techBindTechFile(lib %s) mcpLayoutFail("seed_technology_bind_failed"))'
        % quote(technology_library),
        "tf=techGetTechFile(lib)",
        "unless(tf && techGetDBUPerUU(tf)==%d && "
        "abs(techGetMfgGridResolution(tf)*%d-%d)<0.0000001 && "
        'techGetLP(tf %s %s) mcpLayoutFail("seed_technology_observation_changed"))'
        % (dbu, dbu, grid, quote(lpp["layer"]), quote(lpp["purpose"])),
        'master=dbOpenCellViewByType(%s "maskLayout" "w")' % binding(master),
        'unless(master mcpLayoutFail("seed_master_create_failed"))',
        "fig=dbCreateRect(master list(%s %s) %s)"
        % (quote(lpp["layer"]), quote(lpp["purpose"]), rect),
        'unless(fig && dbSave(master) mcpLayoutFail("seed_master_save_failed"))',
        "dbClose(master)",
        'master=dbOpenCellViewByType(%s "maskLayout" "r")' % binding(master),
        'unless(master mcpLayoutFail("seed_master_reopen_failed"))',
        'cv=dbOpenCellViewByType(%s "maskLayout" "w")' % binding(seed),
        'unless(cv mcpLayoutFail("seed_view_create_failed"))',
        'inst=dbCreateInst(cv master "I0" list(%s 0) "R0")' % offset,
        'unless(inst mcpLayoutFail("seed_instance_create_failed"))',
        "fig=dbCreateRect(cv list(%s %s) %s)" % (quote(lpp["layer"]), quote(lpp["purpose"]), rect),
        'unless(fig && dbSave(cv) mcpLayoutFail("seed_save_failed"))',
        "dbClose(cv)",
        "dbClose(master)",
        'cv=dbOpenCellViewByType(%s "maskLayout" "r")' % binding(seed),
        'unless(cv mcpLayoutFail("seed_reopen_failed"))',
        'unless(cv~>DBUPerUU==%d mcpLayoutFail("seed_dbu_mismatch"))' % dbu,
        "mcpLayoutCollect(cv)",
        "dbClose(cv)",
        'printf("MCP_LAYOUT_SAVED_REOPENED|1\\n")',
        "exit()",
    ]
    return ("\n".join(lines) + "\n").encode("ascii")
