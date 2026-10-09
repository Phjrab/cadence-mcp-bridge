"""One fixed renderer for local compiler and standard-VM Python2.6 worker.

Inputs are validated registration primitives. No OCEAN/SKILL source, expression,
command or output path is accepted from MCP input. Authority and provenance are
independently checked by the fixed provider before using these artifacts.
"""

# mypy: ignore-errors
import hashlib
import re
from decimal import Decimal, InvalidOperation, localcontext

try:
    STRINGS = (basestring,)
except NameError:
    STRINGS = (str,)

try:
    INTEGERS = (int, long)
except NameError:
    INTEGERS = (int,)

ADE_TEMPLATE = (
    "; Generic ADE L owned-copy netlist input. No OA/state save and no simulator run.\n"
    'envSetVal("asimenv.startup" "projectDir" \'string @PROJECT@)\n'
    'envSetVal("asimenv.startup" "simulator" \'string "spectre")\n'
    "let((win session sevId cv ana)\n"
    "  unless(sevStartSession(?lib @LIB@ ?cell @CELL@ ?view @VIEW@) exit(1))\n"
    "  win=hiGetCurrentWindow()\n"
    "  session=asiGetSession(win)\n"
    "  sevId=sevSession(win)\n"
    "  unless(session && sevId exit(1))\n"
    "  cv=asiGetTopCellView(session)\n"
    "  unless(cv && cv~>libName==@LIB@ && cv~>cellName==@CELL@ &&\n"
    "    cv~>viewName==@VIEW@ exit(1))\n"
    "  unless(asiLoadState(session ?name @STATE@ ?option 'dir ?stateDir @STATE_ROOT@\n"
    '    ?lib @LIB@ ?cell @CELL@ ?simulator "spectre") exit(1))\n'
    "  foreach(name asiGetAnalysisNameList(session)\n"
    "    unless(asiDisableAnalysis(asiGetAnalysis(session name)) exit(1)))\n"
    "@VARIABLES@\n"
    "  ana=asiGetAnalysis(session '@ANALYSIS@)\n"
    "  unless(ana exit(1))\n"
    "@FIELDS@\n"
    "  unless(asiEnableAnalysis(ana) && asiIsAnalysisEnabled(ana) exit(1))\n"
    "  unless(length(asiGetEnabledAnalysisList(session))==1 exit(1))\n"
    "  unless(sevNetlistFile(sevId 'recreate) exit(1))\n"
    '  printf("MCP_GENERIC_ADE_NETLIST|@PLAN@|@OPERATION@\\n")\n'
    "  unless(asiLoadState(session ?name @STATE@ ?option 'dir ?stateDir @STATE_ROOT@\n"
    '    ?lib @LIB@ ?cell @CELL@ ?simulator "spectre") exit(1))\n'
    "  unless(sevQuit(sevId) exit(1)))\n"
    "exit(0)\n"
)

READER_PREAMBLE = (
    "procedure(mcpGenericData(name alias)\n"
    "  let((data) data=getData(name) unless(data data=getData(alias)) data))\n"
    "procedure(mcpGenericScalar(name alias)\n"
    "  let((data vec)\n"
    "    data=mcpGenericData(name alias)\n"
    "    cond((numberp(data) data)\n"
    "      (drIsWaveform(data)\n"
    "        vec=drGetWaveformYVec(data)\n"
    "        if(equal(drVectorLength(vec) 1) then drGetElem(vec 0) else nil))\n"
    "      (t nil))))\n"
)


def matches(pattern, value):
    if not isinstance(value, STRINGS):
        return False
    found = re.match(pattern, value)
    return found is not None and found.end() == len(value)


def identifier(value):
    if not matches(r"^[A-Za-z][A-Za-z0-9_#-]{0,63}$", value):
        raise ValueError("native_render_identifier")
    return value


def logical(value):
    if not matches(r"^[a-z][a-z0-9-]{0,63}$", value):
        raise ValueError("native_render_logical_id")
    return value


def digest(value):
    if not matches(r"^[0-9a-f]{64}$", value):
        raise ValueError("native_render_digest")
    return value


def operation(value):
    if not matches(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", value):
        raise ValueError("native_render_operation")
    return value


def path(value):
    if not matches(r"^/[A-Za-z0-9_#./-]{1,511}$", value) or any(
        part in ("", ".", "..") for part in value[1:].split("/")
    ):
        raise ValueError("native_render_path")
    return value


def numeric(value):
    if not matches(r"^-?(0|[1-9][0-9]{0,63})(\.[0-9]{1,63})?$", value) or len(value) > 48:
        raise ValueError("native_render_number")
    number = Decimal(value)
    if abs(number.adjusted()) > 30 or abs(number.as_tuple().exponent) > 40:
        raise ValueError("native_render_number_bound")
    return value


def quoted(value):
    if not matches(r"^[A-Za-z0-9_#./-]+$", value):
        raise ValueError("native_render_literal")
    return '"' + value + '"'


def netlist(job_root, view, state, variables, inputs, plan_sha, operation_id):
    job = path(job_root) + "/" + operation(operation_id)
    identifier(view)
    identifier(state)
    digest(plan_sha)
    if type(variables) not in (list, tuple) or len(variables) > 32:
        raise ValueError("native_render_variable_inventory")
    names = []
    pairs = []
    for name, value in variables:
        names.append(identifier(name))
        pairs.append("list(" + quoted(name) + " " + quoted(numeric(value)) + ")")
    if len(set(names)) != len(names):
        raise ValueError("native_render_variable_inventory")
    variable_lines = []
    if pairs:
        variable_lines = [
            "  unless(isCallable('asiSetDesignVarList) && asiSetDesignVarList(session list("
            + " ".join(pairs)
            + ")) exit(1))"
        ]
    analysis = inputs.get("analysis")
    fields = []
    if analysis == "dc":
        if set(inputs) != set(("analysis", "mode", "statement_sha256")):
            raise ValueError("native_render_dc_inputs")
        if inputs["mode"] != "saved_operating_point":
            raise ValueError("native_render_dc_inputs")
        digest(inputs["statement_sha256"])
    elif analysis == "ac":
        if set(inputs) != set(("analysis", "start_hz", "stop_hz", "points_per_decade")):
            raise ValueError("native_render_ac_inputs")
        start, stop = numeric(inputs["start_hz"]), numeric(inputs["stop_hz"])
        count = inputs["points_per_decade"]
        if not Decimal("0.000001") <= Decimal(start) < Decimal(stop) <= Decimal("1e12"):
            raise ValueError("native_render_ac_inputs")
        if type(count) not in INTEGERS or not 1 <= count <= 100:
            raise ValueError("native_render_ac_inputs")
        fields = [
            "  unless(asiSetAnalysisFieldVal(ana '" + name + " " + quoted(value) + ") exit(1))"
            for name, value in (
                ("start", start),
                ("stop", stop),
                ("incrType", "Logarithmic"),
                ("dec", str(count)),
            )
        ]
    elif analysis == "tran":
        if set(inputs) != set(("analysis", "stop_s", "maxstep_s", "method")):
            raise ValueError("native_render_tran_inputs")
        stop, step = numeric(inputs["stop_s"]), numeric(inputs["maxstep_s"])
        if not Decimal("1e-12") <= Decimal(step) <= Decimal(stop) <= Decimal("10"):
            raise ValueError("native_render_tran_inputs")
        if inputs["method"] not in ("trap", "gear2only"):
            raise ValueError("native_render_tran_inputs")
        fields = ["  unless(asiSetAnalysisFieldVal(ana 'stop " + quoted(stop) + ") exit(1))"]
        fields.extend(
            "  unless(asiSetAnalysisOptionVal(ana '" + name + " " + quoted(value) + ") exit(1))"
            for name, value in (("maxstep", step), ("method", inputs["method"]))
        )
    else:
        raise ValueError("native_render_analysis")
    replacements = {
        "PROJECT": quoted(job + "/project"),
        "LIB": quoted("MCP_GREL_Work"),
        "CELL": quoted("Grel_" + operation_id.replace("-", "_")),
        "VIEW": quoted(view),
        "STATE": quoted(state),
        "STATE_ROOT": quoted(job + "/state-root"),
        "VARIABLES": "\n".join(variable_lines),
        "FIELDS": "\n".join(fields),
        "ANALYSIS": analysis,
        "PLAN": plan_sha,
        "OPERATION": operation_id,
    }
    script = ADE_TEMPLATE
    for name, value in replacements.items():
        script = script.replace("@" + name + "@", value)
    return script.encode("ascii")


def selector(value, current=False):
    path(value)
    if len(value) > 128 or (current and not value.endswith("/PLUS")):
        raise ValueError("native_render_selector")
    if not current and value.rsplit("/", 1)[-1] in ("PLUS", "MINUS"):
        raise ValueError("native_render_quantity")
    return value


def reader(job_root, analysis, registration, operation_id, plan_sha, input_sha, reader_sha):
    job = path(job_root) + "/" + operation(operation_id) + "/work"
    header = "|".join(
        (
            "MCP_GREL_FRAME",
            "1",
            operation_id,
            digest(plan_sha),
            digest(input_sha),
            digest(reader_sha),
        )
    )
    if analysis not in ("dc", "ac", "tran"):
        raise ValueError("native_render_analysis")
    nodes, sources = registration["nodes"], registration["sources"]
    maximum = registration["maximum_samples"]
    if type(maximum) not in INTEGERS or not 2 <= maximum <= 256:
        raise ValueError("native_render_sample_bound")
    if not 1 <= len(nodes) <= 8 or len(sources) > 8 or (analysis != "dc" and sources):
        raise ValueError("native_render_signal_inventory")
    result = "dcOp" if analysis == "dc" else analysis
    lines = [
        READER_PREAMBLE,
        "let((port data wave xVec yVec count index sample axis)",
        '  port=outfile("' + job + '/generic-frame.txt")',
        "  unless(port exit(1))",
        '  unless(openResults("' + job + '/psf") close(port) exit(1))',
        "  unless(selectResult('" + result + ") close(port) exit(1))",
        '  fprintf(port "' + header + '\\n")',
    ]
    if analysis == "dc":
        for node in nodes:
            name = logical(node["logical_id"])
            selected = selector(node["selector"])
            lines += [
                '  data=mcpGenericScalar("' + selected + '" "' + selected[1:] + '")',
                "  unless(numberp(data) close(port) exit(1))",
                '  fprintf(port "V|' + name + '|%.16g\\n" data)',
            ]
        for source in sources:
            name = logical(source["source_id"])
            selected = selector(source["current_selector"], True)
            lines += [
                '  data=mcpGenericScalar("' + selected + '" "' + selected[1:-5] + ':p")',
                "  unless(numberp(data) close(port) exit(1))",
                '  fprintf(port "I|' + name + '|%.16g\\n" data)',
            ]
    else:
        for node in nodes:
            name = logical(node["logical_id"])
            selected = selector(node["selector"])
            lines += [
                '  wave=mcpGenericData("' + selected + '" "' + selected[1:] + '")',
                "  unless(wave && drIsWaveform(wave) close(port) exit(1))",
                "  xVec=drGetWaveformXVec(wave) yVec=drGetWaveformYVec(wave)",
                "  count=drVectorLength(xVec)",
                "  unless(count>=2 && count<=" + str(maximum) + " && "
                "count==drVectorLength(yVec) close(port) exit(1))",
                "  for(index 0 sub1(count)",
                "    axis=drGetElem(xVec index) sample=drGetElem(yVec index)",
                '    fprintf(port "P|' + name + '|%d|%.16g|%.16g|%.16g\\n" '
                "index axis real(sample) imag(sample)))",
            ]
    lines += ['  fprintf(port "END\\n")', "  close(port))", "exit(0)", ""]
    return "\n".join(lines).encode("ascii")


INPUT_LIMIT = 262144


def full_match(pattern, value):
    found = re.match(pattern, value)
    return found if found is not None and found.end() == len(value) else None


def number_text(value):
    if (
        not isinstance(value, STRINGS)
        or len(value) > 48
        or not matches(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value)
    ):
        raise ValueError("bounded_decimal_text")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError("invalid_decimal")
    if not number.is_finite() or abs(number.as_tuple().exponent) > 40:
        raise ValueError("decimal_exponent_bound")
    if abs(number.adjusted()) > 30:
        raise ValueError("decimal_magnitude_bound")
    with localcontext() as context:
        context.prec = 128
        normalized = "0" if number == 0 else format(number.normalize(), "f")
    if len(normalized) > 48:
        raise ValueError("canonical_decimal_bound")
    return normalized


def statements(data):
    try:
        value = data.decode("ascii")
    except UnicodeError:
        raise ValueError("spectre_dialect_unsupported")
    if len(data) > INPUT_LIMIT or any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise ValueError("spectre_dialect_unsupported")
    lines, pending = [], ""
    for physical in value.splitlines():
        line = physical.strip()
        if not line or line.startswith("//"):
            if pending:
                raise ValueError("spectre_dialect_unsupported")
            continue
        continued = line.endswith(chr(92))
        if continued:
            line = line[:-1].rstrip()
            if not line:
                raise ValueError("spectre_dialect_unsupported")
        if any(token in line for token in (chr(92), ";", "//", "/*", "*/")) or line.startswith("+"):
            raise ValueError("spectre_dialect_unsupported")
        pending += (" " if pending else "") + line
        if len(pending) > 16384:
            raise ValueError("spectre_dialect_unsupported")
        if continued:
            continue
        line, pending = " ".join(pending.split()), ""
        if '"' in line and not line.startswith('include "'):
            # HNL defaults only. Spectre runs with cwd=owned work, making the
            # sensitivity file's single parent traversal remain in the owned job.
            allowed = []
            if line.startswith("simulatorOptions options "):
                allowed = ['sensfile="../psf/sens.output"']
            elif full_match(r"[A-Za-z][A-Za-z0-9_]* dc(?: .*|)", line):
                allowed = ['write="spectre.dc"']
            elif full_match(r"[A-Za-z][A-Za-z0-9_]* tran(?: .*|)", line):
                allowed = ['write="spectre.ic"', 'writefinal="spectre.fc"']
            checked = line
            for pair in allowed:
                checked = re.sub(r"(?<!\S)" + re.escape(pair) + r"(?!\S)", "", checked)
            if '"' in checked:
                raise ValueError("spectre_dialect_unsupported")
        lines.append(line)
    if pending or not lines or lines[0] != "simulator lang=spectre":
        raise ValueError("spectre_dialect_unsupported")
    return lines[1:]


def analysis_options(text):
    pairs = text.split()
    if any(p.count("=") != 1 for p in pairs):
        raise ValueError("spectre_analysis_binding_mismatch")
    observed = dict(p.split("=", 1) for p in pairs)
    if len(observed) != len(pairs):
        raise ValueError("spectre_analysis_binding_mismatch")
    return observed


def static_fingerprint(lines):
    return hashlib.sha256(("\n".join(lines) + "\n").encode("ascii")).hexdigest()


def partition_input(data):
    parameters, includes, analyses, static = {}, [], [], []
    scopes = []
    for line in statements(data):
        words = line.split()
        opening = words[1:] if words[0] == "inline" else words
        if opening and opening[0] == "subckt":
            if len(opening) < 2 or not full_match(r"[A-Za-z][A-Za-z0-9_#-]{0,63}", opening[1]):
                raise ValueError("spectre_scope_unsupported")
            scopes.append(opening[1])
            static.append(line)
            continue
        if words[0] == "ends":
            if not scopes or len(words) > 2 or (len(words) == 2 and words[1] != scopes[-1]):
                raise ValueError("spectre_scope_unsupported")
            scopes.pop()
            static.append(line)
            continue
        if scopes and (
            line.startswith(("parameters ", "include "))
            or re.match(r"[A-Za-z][A-Za-z0-9_]* (dc|ac|tran)(?: |$)", line)
        ):
            raise ValueError("spectre_scoped_inputs_unsupported")
        if line.startswith("parameters "):
            for pair in line.split()[1:]:
                found = full_match(r"([A-Za-z][A-Za-z0-9_#-]{0,63})=(.+)", pair)
                if found is None or found.group(1) in parameters:
                    raise ValueError("spectre_parameters_invalid")
                try:
                    parameters[found.group(1)] = number_text(found.group(2))
                except ValueError:
                    raise ValueError("spectre_scalar_expression_denied")
        elif line.startswith("include "):
            found = full_match(
                r'include "(/[A-Za-z0-9._/-]+)" section=([A-Za-z][A-Za-z0-9_#-]{0,63})', line
            )
            if found is None:
                raise ValueError("spectre_model_binding_mismatch")
            includes.append((found.group(1), found.group(2)))
        else:
            found = full_match(r"[A-Za-z][A-Za-z0-9_]* (dc|ac|tran)(?: (.*))?", line)
            if found:
                analyses.append((found.group(1), found.group(2) or ""))
            else:
                static.append(line)
    if scopes:
        raise ValueError("spectre_scope_unsupported")
    return parameters, includes, analyses, static


def effective_input(data, expected_parameters, expected_includes, inputs, static_sha):
    # The fixed worker must obtain expected primitives from confirmed registration,
    # never from the candidate netlist. Native source/model attestation is separate.
    digest(static_sha)
    parameters, includes, analyses, static = partition_input(data)
    if parameters != expected_parameters:
        raise ValueError("spectre_explicit_parameters_mismatch")
    if includes != list(expected_includes):
        raise ValueError("spectre_model_binding_mismatch")
    if len(analyses) != 1 or analyses[0][0] != inputs["analysis"]:
        raise ValueError("spectre_analysis_binding_mismatch")
    options = analyses[0][1]
    if inputs["analysis"] == "dc":
        observed = analysis_options(options)
        # An exact hash alone must not promote a saved sweep to a DC OP.
        fixed = {"write": '"spectre.dc"', "annotate": "status"}
        if set(observed) - set(("write", "annotate", "save", "maxiters", "maxsteps")):
            raise ValueError("spectre_analysis_binding_mismatch")
        for key, value in observed.items():
            if key in fixed and value != fixed[key]:
                raise ValueError("spectre_analysis_binding_mismatch")
            if key == "save" and value not in ("all", "allpub"):
                raise ValueError("spectre_analysis_binding_mismatch")
            if key in ("maxiters", "maxsteps") and not (
                matches(r"[1-9][0-9]{0,5}", value) and int(value) <= 100000
            ):
                raise ValueError("spectre_analysis_binding_mismatch")
        if (
            hashlib.sha256(("dc " + options).encode("ascii")).hexdigest()
            != inputs["statement_sha256"]
        ):
            raise ValueError("spectre_analysis_binding_mismatch")
    else:
        expected = (
            {
                "start": inputs["start_hz"],
                "stop": inputs["stop_hz"],
                "dec": str(inputs["points_per_decade"]),
            }
            if inputs["analysis"] == "ac"
            else {
                "stop": inputs["stop_s"],
                "maxstep": inputs["maxstep_s"],
                "method": inputs["method"],
            }
        )
        observed = analysis_options(options)
        defaults = {"annotate": "status"}
        if inputs["analysis"] == "tran":
            defaults.update(
                {
                    "maxiters": "5",
                    "errpreset": "moderate",
                    "write": '"spectre.ic"',
                    "writefinal": '"spectre.fc"',
                }
            )
        for key in set(observed) - set(expected):
            if key not in defaults or observed[key] != defaults[key]:
                raise ValueError("spectre_analysis_binding_mismatch")
        if not set(expected).issubset(observed):
            raise ValueError("spectre_analysis_binding_mismatch")
        for key in expected:
            value = observed[key]
            try:
                actual = value if key == "method" else number_text(value)
            except ValueError:
                raise ValueError("spectre_analysis_binding_mismatch")
            if actual != expected[key]:
                raise ValueError("spectre_analysis_binding_mismatch")
    if static_fingerprint(static) != static_sha:
        raise ValueError("spectre_static_inputs_mismatch")
    return {
        "parameter_count": len(parameters),
        "model_count": len(includes),
        "input_sha256": hashlib.sha256(data).hexdigest(),
    }
