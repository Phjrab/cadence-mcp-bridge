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
# Mathematical candidate convention, matching layout_transforms. Native compound
# mirror semantics remain unqualified; this table does not advertise capability.
ORIENTATION_MATRICES = {
    "R0": (1, 0, 0, 1),
    "R90": (0, -1, 1, 0),
    "R180": (-1, 0, 0, -1),
    "R270": (0, 1, -1, 0),
    "MX": (1, 0, 0, -1),
    "MY": (-1, 0, 0, 1),
    "MXR90": (0, 1, 1, 0),
    "MYR90": (0, -1, -1, 0),
}


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


def layer_policy(value):
    if not isinstance(value, dict) or set(value) != set(("technology_library", "layer_purposes")):
        raise ValueError("layout_layer_policy_shape")
    library = token(value["technology_library"])
    pairs = value["layer_purposes"]
    if not isinstance(pairs, (list, tuple)) or len(pairs) > 32:
        raise ValueError("layout_layer_policy_bounds")
    result = []
    for pair in pairs:
        if not isinstance(pair, dict) or set(pair) != set(("layer", "purpose")):
            raise ValueError("layout_layer_policy_pair")
        result.append((token(pair["layer"]), token(pair["purpose"])))
    if result != sorted(set(result)):
        raise ValueError("layout_layer_policy_order")
    return library, result


def layer_policy_call(policy, cellview="cv", collect=False):
    if policy is None:
        return "mcpLayoutCollect(%s)" % cellview if collect else ""
    library, pairs = layer_policy(policy)
    layers = (
        "list(%s)" % " ".join("list(%s %s)" % (quote(a), quote(b)) for a, b in pairs)
        if pairs
        else "nil"
    )
    procedure = "mcpLayoutCollectPolicy" if collect else "mcpLayoutCheckLayerPolicy"
    return "%s(%s %s %s)" % (procedure, cellview, quote(library), layers)


def grid_point(value, grid):
    if not isinstance(value, dict) or set(value) != set(("x", "y")):
        raise ValueError("layout_orientation_point")
    for axis in ("x", "y"):
        if integer(value[axis]) % grid:
            raise ValueError("layout_orientation_off_grid")


def grid_bbox(value, grid):
    if not isinstance(value, dict) or set(value) != set(("lower_left", "upper_right")):
        raise ValueError("layout_orientation_bbox")
    low, high = value["lower_left"], value["upper_right"]
    grid_point(low, grid)
    grid_point(high, grid)
    if low["x"] >= high["x"] or low["y"] >= high["y"]:
        raise ValueError("layout_positive_area_required")


def orientation_command(edit, technology):
    if (
        not isinstance(edit, dict)
        or set(edit)
        != set(("kind", "object_id", "before_sha256", "orientation", "origin_dbu", "bbox_dbu"))
        or edit["kind"] != "orient"
    ):
        raise ValueError("layout_orientation_command_shape")
    token(edit["object_id"], LOGICAL)
    token(edit["before_sha256"], r"^[0-9a-f]{64}$")
    target = token(edit["orientation"])
    if target not in ORIENTATIONS or target not in technology["supported_orientations"]:
        raise ValueError("layout_orientation_not_registered")
    grid = integer(technology["manufacturing_grid_dbu"])
    if grid <= 0:
        raise ValueError("layout_edit_bounds")
    grid_point(edit["origin_dbu"], grid)
    grid_bbox(edit["bbox_dbu"], grid)


def oriented_bbox(obj, target, technology):
    """Independent Python-2.6 exact new * inverse(old) bbox prediction."""
    old = obj["orientation"]
    supported = technology["supported_orientations"]
    if old not in ORIENTATIONS or old not in supported or target not in supported:
        raise ValueError("layout_orientation_not_registered")
    if target not in ORIENTATIONS or old == target:
        raise ValueError("layout_orientation_no_change")
    grid = integer(technology["manufacturing_grid_dbu"])
    if grid <= 0:
        raise ValueError("layout_edit_bounds")
    origin, box = obj["origin_dbu"], obj["bbox_dbu"]
    grid_point(origin, grid)
    grid_bbox(box, grid)
    a, b, c, d = ORIENTATION_MATRICES[target]
    e, f, g, h = ORIENTATION_MATRICES[old]
    # Orthogonal inverse is the transpose. Compose before applying, keeping
    # unbounded integer intermediates; only final DBU coordinates are bounded.
    matrix = (a * e + b * f, a * g + b * h, c * e + d * f, c * g + d * h)
    a, b, c, d = matrix
    points = []
    for x in (box["lower_left"]["x"], box["upper_right"]["x"]):
        for y in (box["lower_left"]["y"], box["upper_right"]["y"]):
            dx, dy = x - origin["x"], y - origin["y"]
            points.append({"x": origin["x"] + a * dx + b * dy, "y": origin["y"] + c * dx + d * dy})
    result = {
        "lower_left": dict((axis, min(p[axis] for p in points)) for axis in ("x", "y")),
        "upper_right": dict((axis, max(p[axis] for p in points)) for axis in ("x", "y")),
    }
    grid_bbox(result, grid)
    return result


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
procedure(mcpLayoutCheckLayerPolicy(cv library lpps)
  let((lib tf)
    lib=ddGetObj(library)
    tf=techGetTechFile(cv)
    unless(lib && tf && eq(tf techGetTechFile(lib))
      mcpLayoutFail("layer_policy_technology_mismatch"))
    foreach(lpp lpps
      unless(techGetLP(tf lpp) mcpLayoutFail("layer_policy_pair_missing")))
  )
)
procedure(mcpLayoutCollectPolicy(cv library lpps)
  let((tf dbu grid count)
    tf=techGetTechFile(cv)
    unless(tf mcpLayoutFail("technology_missing"))
    dbu=round(cv~>DBUPerUU)
    grid=techGetMfgGridResolution(tf)
    unless(numberp(dbu) && dbu>0 && numberp(grid) && grid>0
      mcpLayoutFail("technology_units_missing"))
    unless(abs(grid*dbu-round(grid*dbu))<0.0000001
      mcpLayoutFail("manufacturing_grid_not_integral_dbu"))
    printf("MCP_LAYOUT_FRAME|1\nTECH|%d|%d\n" dbu round(grid*dbu))
    if(library then
      mcpLayoutCheckLayerPolicy(cv library lpps)
      foreach(lpp lpps printf("LPP|%s|%s\n" car(lpp) cadr(lpp)))
    else
      foreach(lp cv~>lpps printf("LPP|%s|%s\n" lp~>layerName lp~>purpose)))
    count=0
    foreach(inst cv~>instances
      count=count+1
      when(count>4096 mcpLayoutFail("instance_limit"))
      printf("I|%s|%s|%s|%s|%s|%s|%d|%d|%s"
        mcpLayoutId(inst) inst~>name inst~>libName inst~>cellName
        inst~>viewName inst~>orient round(xCoord(inst~>xy)*dbu)
        round(yCoord(inst~>xy)*dbu) if(inst~>master~>superMaster then "1" else "0"))
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
procedure(mcpLayoutCollect(cv)
  mcpLayoutCollectPolicy(cv nil nil)
)
"""

# Kept out of legacy scripts. Absolute instance attribute assignment is a local
# native candidate, not an installed/qualified Cadence API claim. No parameter
# callbacks or master writes are permitted; unusual property types fail closed.
ORIENT_PRELUDE = r"""
procedure(mcpLayoutOrientState(inst)
  let((props)
    when(inst~>master~>superMaster || inst~>master~>isParamCell
      mcpLayoutFail("orientation_pcell_unsupported"))
    props=nil
    foreach(p inst~>prop
      when(length(props)>=256 mcpLayoutFail("orientation_property_bound"))
      unless(member(p~>valueType list("string" "int" "float" "boolean"))
        mcpLayoutFail("orientation_property_type_unsupported"))
      props=cons(list(p~>name p~>valueType p~>value) props)
    )
    list(inst~>name inst~>libName inst~>cellName inst~>viewName
      list(xCoord(inst~>xy) yCoord(inst~>xy))
      sort(props lambda((a b) alphalessp(car(a) car(b)))))
  )
)
procedure(mcpLayoutOrientBox(inst dbu)
  let((b)
    b=inst~>bBox
    list(mcpLayoutOrientPoint(car(b) dbu) mcpLayoutOrientPoint(cadr(b) dbu))
  )
)
procedure(mcpLayoutOrientPoint(p dbu)
  list(round(xCoord(p)*dbu) round(yCoord(p)*dbu))
)
procedure(mcpLayoutOrientVerify(cv checks dbu)
  let((matches inst)
    foreach(check checks
      matches=setof(o cv~>instances equal(mcpLayoutId(o) car(check)))
      unless(length(matches)==1 mcpLayoutFail("orientation_identity_not_unique"))
      inst=car(matches)
      unless(equal(mcpLayoutOrientState(inst) cadr(check)) &&
        equal(inst~>orient caddr(check)) &&
        equal(mcpLayoutOrientBox(inst dbu) cadddr(check))
        mcpLayoutFail("orientation_preservation_or_bbox_mismatch"))
    )
  )
)
"""


def has_orientation(edits):
    return edits is not None and any(e["kind"] == "orient" for e in edits)


def inspect_script(cellview, policy=None):
    return (
        PRELUDE + '\ncv=dbOpenCellViewByType(%s "maskLayout" "r")\n'
        'unless(cv mcpLayoutFail("source_open_failed"))\n'
        "%s\ndbClose(cv)\nexit()\n" % (binding(cellview), layer_policy_call(policy, collect=True))
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


def edits_script(edits, technology, policy=None):
    dbu = technology["dbu_per_um"]
    allowed = set((p["layer"], p["purpose"]) for p in technology["allowed_layer_purposes"])
    if policy is not None:
        allowed.intersection_update(layer_policy(policy)[1])
    grid = integer(technology["manufacturing_grid_dbu"])
    if grid <= 0 or not isinstance(edits, (tuple, list)) or not 1 <= len(edits) <= 128:
        raise ValueError("layout_edit_bounds")
    lines = ["orientChecks=nil"] if has_orientation(edits) else []
    for edit in edits:
        object_id = quote(edit["object_id"], True)
        if edit["kind"] == "orient":
            orientation_command(edit, technology)
            # Render only integers; check units before constructing the SKILL.
            coordinate(0, dbu)
            origin = edit["origin_dbu"]
            low, high = edit["bbox_dbu"]["lower_left"], edit["bbox_dbu"]["upper_right"]
            box = "list(list(%d %d) list(%d %d))" % (low["x"], low["y"], high["x"], high["y"])
            lines.extend(
                [
                    "matches=setof(o cv~>instances equal(mcpLayoutId(o) %s))" % object_id,
                    'unless(length(matches)==1 mcpLayoutFail("orientation_identity_not_unique"))',
                    "fig=car(matches)",
                    "unless(equal(mcpLayoutOrientPoint(fig~>xy %d) list(%d %d)) "
                    'mcpLayoutFail("orientation_origin_changed"))'
                    % (dbu, origin["x"], origin["y"]),
                    "orientChecks=cons(list(%s mcpLayoutOrientState(fig) %s %s) orientChecks)"
                    % (object_id, quote(edit["orientation"]), box),
                    "fig~>orient=%s" % quote(edit["orientation"]),
                ]
            )
            continue
        if edit["kind"] == "move":
            dx, dy = integer(edit["dx_dbu"]), integer(edit["dy_dbu"])
            if dx % grid or dy % grid:
                raise ValueError("layout_move_off_grid")
            lines.extend(
                [
                    "matches=append(setof(o cv~>instances equal(mcpLayoutId(o) %s)) "
                    "setof(o cv~>shapes equal(mcpLayoutId(o) %s)))" % (object_id, object_id),
                    'unless(length(matches)==1 mcpLayoutFail("move_identity_not_unique"))',
                    'unless(dbMoveFig(car(matches) nil list(list(%s %s) "R0" 1)) '
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


def write_script(source, target, selectors, technology, edits=None, policy=None):
    if source == target:
        raise ValueError("layout_distinct_cellview_required")
    if has_orientation(edits):
        raise ValueError("layout_orientation_requires_owned_apply")
    source_text, target_text = binding(source), binding(target)
    lines = [
        PRELUDE,
        'when(ddGetObj(%s) mcpLayoutFail("destination_already_exists"))' % target_text,
        'src=dbOpenCellViewByType(%s "maskLayout" "r")' % source_text,
        'unless(src mcpLayoutFail("source_open_failed"))',
        layer_policy_call(policy, "src"),
        # Copy never overwrites. Source stays read-only for the whole session.
        "cv=dbCopyCellView(src %s nil nil nil)" % target_text,
        'unless(cv mcpLayoutFail("copy_failed"))',
        "dbClose(src)",
        layer_policy_call(policy),
        tags_script(selectors, technology["dbu_per_um"]),
    ]
    if edits is not None:
        lines.append(edits_script(edits, technology, policy))
    lines.extend(
        [
            'unless(dbSave(cv) mcpLayoutFail("save_failed"))',
            "dbClose(cv)",
            'cv=dbOpenCellViewByType(%s "maskLayout" "r")' % target_text,
            'unless(cv mcpLayoutFail("reopen_failed"))',
            layer_policy_call(policy, collect=True),
            "dbClose(cv)",
            'printf("MCP_LAYOUT_SAVED_REOPENED|1\\n")',
            "exit()",
        ]
    )
    return ("\n".join(lines) + "\n").encode("ascii")


def apply_script(target, selectors, technology, edits, policy=None):
    """One exact-baseline edit of a registered, freshly forked owned revision."""
    target_text = binding(target)
    orient = has_orientation(edits)
    verify = (
        ["mcpLayoutOrientVerify(cv orientChecks %d)" % technology["dbu_per_um"]] if orient else []
    )
    lines = (
        [
            PRELUDE + (ORIENT_PRELUDE if orient else ""),
            'cv=dbOpenCellViewByType(%s "maskLayout" "a")' % target_text,
            'unless(cv mcpLayoutFail("working_revision_open_failed"))',
            layer_policy_call(policy),
            terminals_preflight(edits),
            tags_script(selectors, technology["dbu_per_um"]),
            edits_script(edits, technology, policy),
        ]
        + verify
        + [
            'unless(dbSave(cv) mcpLayoutFail("save_failed"))',
            'unless(dbClose(cv) mcpLayoutFail("close_failed"))' if orient else "dbClose(cv)",
            'cv=dbOpenCellViewByType(%s "maskLayout" "r")' % target_text,
            'unless(cv mcpLayoutFail("reopen_failed"))',
        ]
        + verify
        + [
            layer_policy_call(policy, collect=True),
            "dbClose(cv)",
            'printf("MCP_LAYOUT_SAVED_REOPENED|1\\n")',
            "exit()",
        ]
    )
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
                '    printf("TECHLIB|%s|%%d|%%.12g\\n" round(techGetDBUPerUU(tf "maskLayout")) '
                "techGetMfgGridResolution(tf))" % token(library),
                "    count=0",
                "    foreach(layer techGetLayerFunctions(tf)",
                '      when(count<32 && techGetLP(tf list(car(layer) "drawing"))',
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


def seed_script(
    library, library_path, technology_library, master_cell, seed_cell, technology, lpp, policy=None
):
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
    if policy is not None:
        policy_library, pairs = layer_policy(policy)
        if policy_library != technology_library or (lpp["layer"], lpp["purpose"]) not in pairs:
            raise ValueError("layout_seed_layer_policy_mismatch")
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
        'unless(tf && techGetDBUPerUU(tf "maskLayout")==%d && '
        "abs(techGetMfgGridResolution(tf)*%d-%d)<0.0000001 && "
        'techGetLP(tf list(%s %s)) mcpLayoutFail("seed_technology_observation_changed"))'
        % (dbu, dbu, grid, quote(lpp["layer"]), quote(lpp["purpose"])),
        layer_policy_call(policy, "lib"),
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
        layer_policy_call(policy, collect=True),
        "dbClose(cv)",
        'printf("MCP_LAYOUT_SAVED_REOPENED|1\\n")',
        "exit()",
    ]
    return ("\n".join(lines) + "\n").encode("ascii")


def execution_script(script):
    """Use the installed qualified generator's errset/procedure/exit idiom."""
    text = script.decode("ascii")
    if not text.startswith(PRELUDE) or not text.rstrip().endswith("exit()"):
        raise ValueError("layout_fixed_program_shape")
    prelude = PRELUDE + ORIENT_PRELUDE if text.startswith(PRELUDE + ORIENT_PRELUDE) else PRELUDE
    body = text[len(prelude) :].rstrip()[: -len("exit()")]
    return (
        prelude + "\nprocedure(mcpLayoutRun()\n" + body + "\nt)\n"
        "let((result) result=errset(mcpLayoutRun() t) "
        'if(result then exit(0) else mcpLayoutFail("skill_evaluation_failed")))\n'
    ).encode("ascii")
