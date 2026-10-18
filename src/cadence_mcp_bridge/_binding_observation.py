"""Review-only fixed OA binding observation pieces, Python2.6 stdlib only.

There is deliberately no CLI, remote dispatcher or activation switch. observe()
remains fail-closed because OCEAN transitive dependencies and library init side
effects have not been independently qualified. Private owned-file/process pieces
are testable without giving caller JSON a script, path, command or trust flag.
"""

# mypy: ignore-errors
# Python2.6 is a qualified guest requirement, so modernizing this asset is unsafe.
import hashlib
import json
import os
import platform
import re
import select
import signal
import stat
import subprocess
import time
import types

try:
    STRINGS = (basestring,)  # noqa: F821
except NameError:
    STRINGS = (str,)

SNAPSHOT_ENTRIES = 64
SNAPSHOT_BYTES = 1048576
DEPENDENCY_LIBRARIES = 8
DEPENDENCY_ENTRIES = 8192
DEPENDENCY_BYTES = 67108864
FRAME_BYTES = 65536
STAGE_BYTES = 8388608
PROCESS_SECONDS = 45
OUTER_SECONDS = 60
HELPER_PINS = {
    "copy.py": "97e3805a6c407617bc588c20907d8804bd0a251bc315ca7f47a16918c44f94e7",
    "reservations.py": "959712af7bacb06fac9dda204fe4ab9db3a8e51c8e51743805eb5f7d61e5b372",
    "process.py": "e54b182be1cce49df2fc0cde9dfb70388747ec3ecf06afbadb33b4ac5f9062c0",
}
SELECTION_KEYS = (
    "schema_version", "design_id", "analysis_id", "profile_sha256",
    "registration_sha256", "request_sha256", "collector_sha256", "helper_sha256",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def token(value, pattern):
    if not isinstance(value, STRINGS):
        raise ValueError("binding_observation_token")
    found = re.match(pattern, value)
    if found is None or found.end() != len(value):
        raise ValueError("binding_observation_token")
    return value


def validate_request(request):
    if not isinstance(request, dict) or set(request) != set((
        "schema_version", "observation_id", "nonce", "library", "cell", "view", "variables",
    )) or type(request["schema_version"]) is not int or request["schema_version"] != 1:
        raise ValueError("binding_observation_request_shape")
    token(request["observation_id"],
          r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    token(request["nonce"], r"^[0-9a-f]{64}$")
    for name in ("library", "cell"):
        token(request[name], r"^[A-Za-z][A-Za-z0-9_#-]{0,63}$")
    if request["view"] != "schematic":
        raise ValueError("binding_observation_top_level_schematic_only")
    variables = request["variables"]
    if not isinstance(variables, list) or not 1 <= len(variables) <= 4:
        raise ValueError("binding_observation_variable_bound")
    for variable in variables:
        if not isinstance(variable, dict) or set(variable) != set(
            ("logical_id", "cadence_binding")
        ):
            raise ValueError("binding_observation_variable_shape")
        token(variable["logical_id"], r"^[a-z][a-z0-9-]{0,63}$")
        token(variable["cadence_binding"], r"^[A-Za-z][A-Za-z0-9_#-]{0,63}$")
    for name in ("logical_id", "cadence_binding"):
        if len(set(v[name] for v in variables)) != len(variables):
            raise ValueError("binding_observation_variable_alias")
    if len(canonical(request)) > 4096:
        raise ValueError("binding_observation_request_bound")
    return request


def render_collector(request):
    # Single reviewed template; no caller text is code.
    validate_request(request)
    variables = "list(" + " ".join(
        'list("%s" "%s")' % (v["logical_id"], v["cadence_binding"])
        for v in request["variables"]
    ) + ")"
    replacements = (
        ("OBSERVATION_ID", request["observation_id"]), ("NONCE", request["nonce"]),
        ("REQUEST_SHA256", digest(canonical(request))), ("LIBRARY", request["library"]),
        ("CELL", request["cell"]), ("VARIABLE_LIST", variables),
    )
    text = COLLECTOR_TEMPLATE
    for key, value in replacements:
        text = text.replace("@" + key + "@", value)
    return text.encode("ascii")


COLLECTOR_TEMPLATE = r"""; Fixed owned-copy binding observation. Closed token placeholders only.
; No hierarchy traversal, expression/callback evaluation or save/write OA API.
bindingCv=nil
bindingPort=nil
bindingBytes=0
procedure(bindingEmit(line)
 bindingBytes=bindingBytes+strlen(line)+1
 when(bindingBytes>65536 error("BINDING_FRAME_BOUND"))
 fprintf(bindingPort "%s\n" line))
procedure(bindingName(value)
 unless(and(stringp(value) strlen(value)>0 strlen(value)<=64
  rexMatchp("^[A-Za-z][A-Za-z0-9_#-]*$" value))
  error("BINDING_UNSUPPORTED_NAME")) value)
procedure(bindingField(object field)
 let((probe value)
  if(null(object) then list("missing" nil)
   else
   probe=errset(get(object field) nil)
   if(null(probe) then list("read_error" nil)
    else
    value=car(probe)
    if(null(value) then list("missing" nil) else list("observed" value)))
  )))
procedure(bindingCdf(inst property binding)
 let((probe cdf parameter typeField unitsField valueField ptype units value vtype text status)
  probe=errset(cdfGetInstCDF(inst) nil)
  cond(
   ((null(probe)) list("read_error" "-" "-" "-" "-"))
   ((null(car(probe))) list("missing" "-" "-" "-" "-"))
   (t
    cdf=car(probe)
    probe=errset(cdfFindParamByName(cdf property) nil)
    cond(
     ((null(probe)) list("read_error" "-" "-" "-" "-"))
     ((null(car(probe))) list("missing" "-" "-" "-" "-"))
     (t
      parameter=car(probe)
      typeField=bindingField(parameter 'type)
      unitsField=bindingField(parameter 'units)
      valueField=bindingField(parameter 'value)
      status="observed"
      foreach(probe list(typeField unitsField valueField)
       when(car(probe)!="observed" status=car(probe)))
      if(status!="observed" then list(status "-" "-" "-" "-")
       else
       ptype=cadr(typeField) units=cadr(unitsField) value=cadr(valueField)
       if(not(and(stringp(ptype) stringp(units))) then
        list("wrong_type" "-" "-" "-" "-")
        else
        if(not(and(strlen(ptype)>0 strlen(ptype)<=64
                   strlen(units)>0 strlen(units)<=64
                   rexMatchp("^[A-Za-z][A-Za-z0-9_#-]*$" ptype)
                   rexMatchp("^[A-Za-z0-9][A-Za-z0-9_#-]*$" units))) then
         list("unsupported_value" "-" "-" "-" "-")
         else
         vtype=type(value)
         text=cond((stringp(value) value)
                   (symbolp(value) symbolToString(value))
                   (numberp(value) sprintf(nil "%L" value))
                   (t nil))
         if(or(null(text) strlen(text)>64) then
          list("wrong_type" "-" "-" "-" "-")
          else
          if(or(text==binding
                rexMatchp("^[+-]?[0-9]+[.]?[0-9]*([eE][+-]?[0-9]+)?$" text)
                rexMatchp("^[+-]?[.][0-9]+([eE][+-]?[0-9]+)?$" text)) then
           list("observed" ptype units symbolToString(vtype) text)
           else list("unsupported_value" "-" "-" "-" "-"))
        )
       )
      )
     )
    )
   )
  )
 )))
procedure(bindingCollect()
 let((variables ordinal propertyTotal matchTotal inst props count property value text
       variable hits instanceName master library cell view propertyName observation counts)
  variables=@VARIABLE_LIST@
  counts=makeTable('bindingCounts 0)
  bindingPort=outfile("binding-frame.txt")
  unless(bindingPort error("BINDING_OUTPUT_FAILED"))
  bindingEmit("BINDING_OBSERVATION_V1|@OBSERVATION_ID@|@NONCE@|@REQUEST_SHA256@")
  bindingEmit("SOURCE|@LIBRARY@|@CELL@|schematic")
  foreach(variable variables
   bindingEmit(sprintf(nil "VARIABLE|%s|%s" car(variable) cadr(variable))))
  bindingCv=dbOpenCellViewByType("@LIBRARY@" "@CELL@" "schematic" "" "r")
  unless(bindingCv error("BINDING_SOURCE_MISSING"))
  when(length(bindingCv~>instances)>64 error("BINDING_INSTANCE_BOUND"))
  ordinal=0 propertyTotal=0 matchTotal=0
  foreach(inst bindingCv~>instances
   ordinal=ordinal+1
   props=inst~>prop count=length(props)
   when(count>32 error("BINDING_PROPERTY_BOUND"))
   propertyTotal=propertyTotal+count
   bindingEmit(sprintf(nil "SCAN|%d|%d" ordinal count))
   foreach(property props
    value=property~>value
    text=cond((stringp(value) value)
              (and(value symbolp(value)) symbolToString(value))
              (t nil))
    when(text
     foreach(variable variables
      when(text==cadr(variable)
       hits=counts[car(variable)]+1 counts[car(variable)]=hits
       matchTotal=matchTotal+1
       when(or(hits>4 matchTotal>16) error("BINDING_MATCH_BOUND"))
       instanceName=bindingName(inst~>name)
       master=inst~>master unless(master error("BINDING_MASTER_MISSING"))
       library=bindingName(master~>libName) cell=bindingName(master~>cellName)
       view=bindingName(master~>viewName) propertyName=bindingName(property~>name)
       observation=bindingCdf(inst propertyName text)
       bindingEmit(sprintf(nil "BIND|%d|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s"
        ordinal car(variable) cadr(variable) instanceName library cell view propertyName
        symbolToString(type(value)) text car(observation) cadr(observation)
        caddr(observation) cadddr(observation) car(cddddr(observation))))
      )
     )
    )
   )
  )
  foreach(variable variables
   when(counts[car(variable)]<1 error("BINDING_VARIABLE_MISSING")))
  dbClose(bindingCv) bindingCv=nil
  bindingEmit(sprintf(nil "COMPLETE|%d|%d|%d" ordinal propertyTotal matchTotal))
  close(bindingPort) bindingPort=nil t
 ))
let((result)
 result=errset(bindingCollect() t)
 when(bindingCv errset(dbClose(bindingCv) nil) bindingCv=nil)
 when(bindingPort errset(close(bindingPort) nil) bindingPort=nil)
 if(result then exit(0) else exit(1)))
"""


def authenticated_modules(assets, pins):
    # The expected pins are compiled here, not selected by request/config JSON.
    if pins != HELPER_PINS or set(assets) != set(HELPER_PINS):
        raise ValueError("binding_observation_fixed_helper_inventory")
    for name in HELPER_PINS:
        raw = assets[name]
        if not isinstance(raw, bytes) or len(raw) > 131072 or digest(raw) != HELPER_PINS[name]:
            raise ValueError("binding_observation_fixed_helper_digest")
    modules = {}
    for name in ("copy.py", "reservations.py", "process.py"):
        module = types.ModuleType("binding_observation_" + name[:-3])
        module.__dict__["__package__"] = None
        eval(compile(assets[name], name, "exec"), module.__dict__)
        modules[name] = module
    # This is a fresh memory-only copy of authenticated code. Lowering these
    # limits does not mutate the installed shared module or broaden its scope.
    modules["copy.py"].MAX_ENTRIES = SNAPSHOT_ENTRIES
    modules["copy.py"].MAX_BYTES = SNAPSHOT_BYTES
    return modules


class BindingObservationWorker(object):
    def __init__(self, profile_raw, registration_raw, selection, assets, pins):
        if not isinstance(selection, dict) or set(selection) != set(SELECTION_KEYS):
            raise ValueError("binding_observation_selection_shape")
        if type(selection["schema_version"]) is not int or selection["schema_version"] != 1:
            raise ValueError("binding_observation_selection_version")
        for key in SELECTION_KEYS[3:]:
            token(selection[key], r"^[0-9a-f]{64}$")
        for key in ("design_id", "analysis_id"):
            token(selection[key], r"^[a-z][a-z0-9-]{0,63}$")
        if len(profile_raw) > 65536 or len(registration_raw) > 262144 or (
            digest(profile_raw) != selection["profile_sha256"]
            or digest(registration_raw) != selection["registration_sha256"]
        ):
            raise ValueError("binding_observation_manifest_binding")
        self.profile, self.registration = json.loads(profile_raw), json.loads(registration_raw)
        if self.registration["environment_sha256"] != selection["profile_sha256"]:
            raise ValueError("binding_observation_environment_binding")
        routes = [r for r in self.registration["routes"]
                  if (r["design_id"], r["analysis_id"]) ==
                  (selection["design_id"], selection["analysis_id"])]
        if len(routes) != 1:
            raise ValueError("binding_observation_registered_route_required")
        self.route, self.selection = routes[0], dict(selection)
        modules = authenticated_modules(assets, pins)
        self.copying, self.accounting = modules["copy.py"], modules["reservations.py"]
        self.processes = modules["process.py"].EdaWorker(None, None, None, None, None)
        self.root = self.profile["paths"]["managed_root"]
        self._deadline = None

    def _bound(self, request):
        validate_request(request)
        source = self.route["profile"]["binding"]
        registered = dict((v["logical_id"], v["cadence_binding"])
                          for v in self.route["variables"])
        if (request["library"], request["cell"], request["view"]) != (
            source["library"], source["cell"], source["view"],
        ) or any(registered.get(v["logical_id"]) != v["cadence_binding"]
                 for v in request["variables"]) or (
            digest(canonical(request)) != self.selection["request_sha256"]
            or digest(render_collector(request)) != self.selection["collector_sha256"]
        ):
            raise ValueError("binding_observation_registered_request_binding")

    def observe(self, request):
        self._bound(request)
        # No caller argument can turn unqualified dependencies into trust. An
        # operational entry point requires a separately reviewed implementation.
        return {
            "schema_version": 1, "status": "CAPABILITY_NOT_QUALIFIED",
            "observation_id": request["observation_id"], "nonce": request["nonce"],
            "qualified": False, "closure_trust": "NOT_ESTABLISHED",
            "blockers": ["OCEAN_TRANSITIVE_DEPENDENCY_TRUST_NOT_ESTABLISHED",
                         "REGISTERED_LIBRARY_INIT_SIDE_EFFECTS_NOT_QUALIFIED"],
            "remote_execution_enabled": False, "new_eda_starts": 0,
            "new_simulations": 0, "new_extractions": 0, "new_reservations": 0,
        }

    def _snapshots(self):
        self.copying.MAX_ENTRIES, self.copying.MAX_BYTES = SNAPSHOT_ENTRIES, SNAPSHOT_BYTES
        source = self.copying.snapshot(self.route["source_cell"])
        remaining_entries = SNAPSHOT_ENTRIES - source["entries"]
        remaining_bytes = SNAPSHOT_BYTES - source["bytes"]
        if remaining_entries < 1 or remaining_bytes < 0:
            raise ValueError("binding_observation_combined_snapshot_bound")
        self.copying.MAX_ENTRIES, self.copying.MAX_BYTES = remaining_entries, remaining_bytes
        try:
            state = self.copying.snapshot(self.route["source_state"])
        finally:
            self.copying.MAX_ENTRIES, self.copying.MAX_BYTES = SNAPSHOT_ENTRIES, SNAPSHOT_BYTES
        if source["tree_sha256"] != self.route["ade"]["source_tree_sha256"] or (
            state["tree_sha256"] != self.route["ade"]["ade_state_tree_sha256"]
        ):
            raise ValueError("binding_observation_original_registration_drift")
        return {"source": source, "state": state, "libraries": self._dependencies()}

    def _dependencies(self):
        # Conservation, not trust: unchanged library init code may still execute
        # implicitly. Two full bounded passes also catch an earlier tree changing
        # while later registered trees are being read. No new baseline is made.
        libraries = self.route["libraries"]
        if not 1 <= len(libraries) <= DEPENDENCY_LIBRARIES:
            raise ValueError("binding_observation_dependency_library_bound")
        names, paths = set(), set()
        for library in libraries:
            name = token(library["name"], r"^[A-Za-z][A-Za-z0-9_#-]{0,63}$")
            location = self.copying.path(library["path"])
            token(library["tree_sha256"], r"^[0-9a-f]{64}$")
            if name in names or location in paths:
                raise ValueError("binding_observation_dependency_alias")
            names.add(name)
            paths.add(location)
        namespace = self._dependency_namespace(libraries)
        passes = []
        try:
            for unused in range(2):
                remaining_entries, remaining_bytes = DEPENDENCY_ENTRIES, DEPENDENCY_BYTES
                observed = []
                for library in libraries:
                    if remaining_entries < 1 or remaining_bytes < 0:
                        raise ValueError("binding_observation_combined_dependency_bound")
                    self.copying.MAX_ENTRIES = min(4096, remaining_entries)
                    self.copying.MAX_BYTES = remaining_bytes
                    snapshot = self.copying.dependency_snapshot(library["path"])
                    if snapshot["tree_sha256"] != library["tree_sha256"]:
                        raise ValueError("binding_observation_registered_dependency_drift")
                    remaining_entries -= snapshot["entries"]
                    remaining_bytes -= snapshot["bytes"]
                    observed.append((library["name"], library["path"], snapshot))
                passes.append(observed)
            if passes[0] != passes[1] or self._dependency_namespace(libraries) != namespace:
                raise ValueError("binding_observation_dependency_scan_drift")
            return passes[1]
        finally:
            self.copying.MAX_ENTRIES, self.copying.MAX_BYTES = SNAPSHOT_ENTRIES, SNAPSHOT_BYTES

    def _dependency_namespace(self, libraries):
        # Ephemeral identity/ctime guards are deliberately not a new registered
        # content baseline. Recheck the whole union after every content read, so
        # a later library cannot change an earlier tree unnoticed on pass two.
        records, entries = [], [0]

        def record(location):
            self.copying.path(location)
            info = os.lstat(location)
            records.append((location, self.copying.identity(info), info.st_nlink,
                            "%.9f" % info.st_ctime))
            return info

        def tree(location, depth):
            if depth > 16 or entries[0] >= DEPENDENCY_ENTRIES:
                raise ValueError("binding_observation_dependency_namespace_bound")
            entries[0] += 1
            info = record(location)
            if stat.S_ISDIR(info.st_mode):
                names = sorted(os.listdir(location))
                records.append((location, names))
                for name in names:
                    tree(os.path.join(location, name), depth + 1)
                if sorted(os.listdir(location)) != names:
                    raise ValueError("binding_observation_dependency_namespace_drift")
            elif not stat.S_ISREG(info.st_mode):
                raise ValueError("binding_observation_dependency_namespace_type")

        for library in libraries:
            ancestor = os.path.dirname(library["path"])
            for unused in range(128):
                info = record(ancestor)
                if not stat.S_ISDIR(info.st_mode):
                    raise ValueError("binding_observation_dependency_ancestor_type")
                parent = os.path.dirname(ancestor)
                if parent == ancestor:
                    break
                ancestor = parent
            else:
                raise ValueError("binding_observation_dependency_ancestor_bound")
            tree(library["path"], 0)
        return records

    def _stage(self, request, session):
        # Review-only owned-file piece. Not reachable from observe() or a CLI.
        self._bound(request)
        self._deadline = os.times()[4] + OUTER_SECONDS
        self._preflight(session)
        before = self._snapshots()
        parent = self.root + "/binding-observations"
        self.copying.owned_parent(self.root)
        if not os.path.lexists(parent):
            os.mkdir(parent, 448)
            self.copying.sync(self.root)
        self.copying.owned_parent(parent)
        stage = parent + "/" + request["observation_id"]
        if os.path.lexists(stage):
            raise ValueError("binding_observation_attempt_already_exists")
        os.mkdir(stage, 448)
        self.copying.sync(parent)
        for name in ("home", "tmp"):
            os.mkdir(stage + "/" + name, 448)
        self.copying.sync(stage)
        self._write(stage + "/request.json", canonical(request))
        os.mkdir(stage + "/library", 448)
        copied = self.copying.copy_owned(self.route["source_cell"],
                                        stage + "/library/" + request["cell"],
                                        before["source"]["tree_sha256"])
        self._write(stage + "/cds.lib", self._cds_lib(request, stage))
        self._write(stage + "/observer.ocn", render_collector(request))
        if self._snapshots() != before:
            raise ValueError("binding_observation_original_copy_drift")
        self._stage_size(stage)
        session.check()
        return stage, before, copied

    def _cds_lib(self, request, stage):
        # Reconstruct from bound registration at both staging and launch. A
        # staged file is evidence to check, never a new library-map baseline.
        self._bound(request)
        definitions = []
        selected_names = set()
        for library in self.route["libraries"]:
            name = token(library["name"], r"^[A-Za-z][A-Za-z0-9_#-]{0,63}$")
            if name in selected_names:
                raise ValueError("binding_observation_library_alias")
            selected_names.add(name)
            location = self.copying.path(library["path"])
            if any(c in location for c in ("\n", "\r", "\t", " ", '"')):
                raise ValueError("binding_observation_library_path")
            if name != request["library"]:
                definitions.append("DEFINE " + name + " " + location)
        if request["library"] not in selected_names:
            raise ValueError("binding_observation_source_library_missing")
        definitions.append("DEFINE " + request["library"] + " " + stage + "/library")
        return ("\n".join(definitions) + "\n").encode("ascii")

    def _write(self, filename, raw):
        if len(raw) > FRAME_BYTES:
            raise ValueError("binding_observation_record_bound")
        self.copying.owned_parent(os.path.dirname(filename))
        fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 384)
        stream = os.fdopen(fd, "wb")
        try:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
        finally:
            stream.close()
        self.copying.sync(os.path.dirname(filename))

    def _stage_size(self, stage):
        logical, allocated, entries = 0, 0, [0]
        for parent, directories, names in os.walk(stage):
            if self.copying.path(parent) != parent:
                raise ValueError("binding_observation_stage_path")
            for name in [""] + directories + names:
                selected = parent if not name else os.path.join(parent, name)
                info = os.lstat(selected)
                if not stat.S_ISDIR(info.st_mode) and not stat.S_ISREG(info.st_mode):
                    raise ValueError("binding_observation_stage_special")
                if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                    raise ValueError("binding_observation_stage_hardlink")
                entries[0] += 1
                logical += info.st_size if stat.S_ISREG(info.st_mode) else 0
                allocated += getattr(info, "st_blocks", (info.st_size + 511) // 512) * 512
                if entries[0] > 256 or max(logical, allocated) > STAGE_BYTES:
                    raise ValueError("binding_observation_stage_capacity")
        return logical, allocated

    def _ocean_trust(self):
        binding = self.profile["tools"]["ocean"]
        named = binding["path"]
        resolved = os.path.realpath(named)
        if os.path.basename(named) != "ocean" or not os.path.isabs(named) or (
            not any(resolved.startswith(p + os.sep) for p in
                    self.profile["paths"]["protected_roots"])
        ):
            raise ValueError("binding_observation_ocean_path")
        records = []
        for first in (named, resolved):
            current = first
            while True:
                info = os.lstat(current)
                if info.st_uid not in (0, os.getuid()) or (
                    not stat.S_ISLNK(info.st_mode) and info.st_mode & 18
                ):
                    raise ValueError("binding_observation_ocean_permissions")
                records.append((current, self.copying.identity(info),
                                os.readlink(current) if stat.S_ISLNK(info.st_mode) else None))
                parent = os.path.dirname(current)
                if parent == current:
                    break
                current = parent
        info = os.lstat(resolved)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not os.access(resolved, os.X_OK):
            raise ValueError("binding_observation_ocean_executable")
        raw = self.copying.read_leaf(resolved, info, 16777216)
        if digest(raw) != binding["sha256"]:
            raise ValueError("binding_observation_ocean_digest")
        return {"named": named, "resolved": resolved, "sha256": binding["sha256"],
                "records": records, "closure_trust": "NOT_ESTABLISHED"}

    def _ledger(self):
        selected = self.root + "/" + self.accounting.LEDGER
        info = self.accounting.safe(selected)
        raw = self.copying.read_leaf(selected, info, 8192)
        return self.copying.identity(info), digest(raw)

    def _preflight(self, session):
        if os.name != "posix" or os.getuid() == 0 or os.geteuid() != os.getuid():
            raise ValueError("binding_observation_normal_posix_user_required")
        if type(session) is not self.accounting.ReservationSession or session.root != self.root:
            raise ValueError("binding_observation_existing_resource_lock_required")
        import pwd

        host = {"hostname": platform.node(), "user": pwd.getpwuid(os.getuid()).pw_name,
                "os": platform.system(), "architecture": platform.machine(),
                "python_version": platform.python_version()}
        if host != self.profile["host"]:
            raise ValueError("binding_observation_host_binding")
        session.check()
        self.copying.owned_parent(self.root)
        if os.path.lexists(self.root + "/" + self.accounting.JOBS + "/active"):
            raise ValueError("binding_observation_active_work")
        self._check_conflicting_processes()
        fs = os.statvfs(self.root)
        free, total = fs.f_bavail * fs.f_frsize, fs.f_blocks * fs.f_frsize
        limits = self.profile["limits"]
        floor = max(limits["disk_floor_bytes"],
                    (total * limits["disk_floor_percent"] + 99) // 100)
        if free < floor + STAGE_BYTES:
            raise ValueError("binding_observation_disk_floor")
        if self._deadline is not None and os.times()[4] >= self._deadline:
            raise ValueError("binding_observation_outer_deadline")
        return self._ledger()

    def _check_conflicting_processes(self):
        # Kept separate so owned-process component tests can supply a controlled
        # external inventory without replacing /proc used by group identity and
        # termination. Unknown same-UID executables must still fail closed.
        for name in os.listdir("/proc"):
            if not name.isdigit() or int(name) == os.getpid():
                continue
            try:
                info = os.stat("/proc/" + name)
                if info.st_uid != os.getuid():
                    continue
                target = os.path.basename(os.readlink("/proc/" + name + "/exe"))
                if target.lower() in ("ocean", "virtuoso", "spectre", "icfb", "icms"):
                    raise ValueError("binding_observation_active_eda_process")
            except OSError as error:
                if error.errno not in (2, 3):
                    raise

    def _environment(self, stage):
        # This is a fixed review-only launch recipe, not attestation of dynamic
        # Cadence dependencies. Do not inherit loader/site/user startup knobs.
        for name in ("home", "tmp"):
            location = stage + "/" + name
            self.copying.owned_parent(location)
            if stat.S_IMODE(os.lstat(location).st_mode) != 448 or os.listdir(location):
                raise ValueError("binding_observation_private_runtime_directory")
        environment = {
            "HOME": stage + "/home", "TMPDIR": stage + "/tmp",
            "TMP": stage + "/tmp", "TEMP": stage + "/tmp",
            "PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
        }
        # Preserve only existing license routing, without logging/querying it or
        # inventing a fallback. Values are private process inputs, never evidence.
        for name in ("CDS_LIC_FILE", "LM_LICENSE_FILE"):
            if name in os.environ:
                value = os.environ[name]
                if len(value) > 4096 or any(c in value for c in ("\x00", "\r", "\n")):
                    raise ValueError("binding_observation_license_environment_bound")
                environment[name] = value
        return environment

    def _program(self, stage, session, request):
        # Review-only process piece. observe() never calls this while closure and
        # library-init side effects remain unqualified. argv is compiled here.
        if os.name != "posix" or os.getuid() == 0 or os.geteuid() != os.getuid():
            raise ValueError("binding_observation_normal_posix_user_required")
        self._bound(request)
        self.copying.owned_parent(stage)
        if os.path.basename(stage) != request["observation_id"] or (
            os.path.dirname(stage) != self.root + "/binding-observations"
        ):
            raise ValueError("binding_observation_stage_identity")
        marker = stage + "/ocean-start-claimed.json"
        if os.path.lexists(marker):
            raise ValueError("binding_observation_process_attempt_spent")
        if self._read(stage + "/observer.ocn") != render_collector(request):
            raise ValueError("binding_observation_collector_drift")
        ledger = self._preflight(session)
        original = self._snapshots()
        copied_path = stage + "/library/" + request["cell"]
        owned_copy = self.copying.snapshot(copied_path)
        if owned_copy["content_sha256"] != original["source"]["content_sha256"]:
            raise ValueError("binding_observation_owned_copy_drift")
        cds_raw = self._read(stage + "/cds.lib")
        if cds_raw != self._cds_lib(request, stage):
            raise ValueError("binding_observation_registered_library_mapping_drift")
        trust = self._ocean_trust()
        environment = self._environment(stage)
        deadline = min(os.times()[4] + PROCESS_SECONDS,
                       self._deadline - 3 if self._deadline is not None else os.times()[4] + 45)
        self._write(marker, canonical({"schema_version": 1,
                    "observation_id": request["observation_id"],
                    "request_sha256": self.selection["request_sha256"],
                    "collector_sha256": self.selection["collector_sha256"],
                    "semantics": "SPENT_BEFORE_ONE_START_NO_RETRY"}))
        process, identity, null = None, None, None
        streams, data = [], [b"", b""]
        try:
            session.check()
            null = open(os.devnull, "rb")
            process = subprocess.Popen(
                [trust["named"], "-nograph", "-nocdsinit", "-log", stage + "/ocean.log",
                 "-cdslib", stage + "/cds.lib", "-restore", stage + "/observer.ocn"],
                cwd=stage, stdin=null, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                close_fds=True, shell=False, preexec_fn=os.setsid, env=environment,
            )
            identity = self.processes.process_identity(process.pid)
            streams = [process.stdout, process.stderr]
            pending = list(streams)
            while pending or self.processes.group_active(process, identity):
                session.check()
                self._stage_size(stage)
                if os.times()[4] >= deadline:
                    raise ValueError("binding_observation_process_timeout")
                ready = select.select(pending, [], [], 0.02)[0] if pending else []
                for stream in ready:
                    index = streams.index(stream)
                    chunk = os.read(stream.fileno(), FRAME_BYTES + 1 - len(data[index]))
                    if not chunk:
                        pending.remove(stream)
                    else:
                        data[index] += chunk
                        if len(data[index]) > FRAME_BYTES:
                            data[index] = data[index][:FRAME_BYTES]
                            raise ValueError("binding_observation_program_output_bound")
                if not pending:
                    time.sleep(0.02)
            code = process.wait()
            process = None
            if code != 0:
                raise ValueError("binding_observation_program_failed")
            if self._ocean_trust() != trust:
                raise ValueError("binding_observation_ocean_post_drift")
            if self._snapshots() != original or self.copying.snapshot(copied_path) != owned_copy:
                raise ValueError("binding_observation_original_or_copy_post_drift")
            if self._ledger() != ledger or self._read(stage + "/cds.lib") != cds_raw:
                raise ValueError("binding_observation_ledger_or_config_drift")
            frame = self._read(stage + "/binding-frame.txt")
            self._stage_size(stage)
            return {"returncode": code, "frame": frame, "ocean": trust,
                    "qualified": False, "closure_trust": "NOT_ESTABLISHED"}
        finally:
            try:
                if process is not None:
                    if identity is None:
                        identity = self.processes.process_identity(process.pid)
                    if self.processes.group_active(process, identity):
                        self.processes.signal_group(process, identity, signal.SIGTERM)
                        end = os.times()[4] + 2
                        while (
                            self.processes.group_active(process, identity) and os.times()[4] < end
                        ):
                            time.sleep(0.02)
                        if self.processes.group_active(process, identity):
                            self.processes.signal_group(process, identity, signal.SIGKILL)
                        # Match the existing worker: keep lifetime lock held until
                        # our group stops. Kernel-uninterruptible tasks can exceed
                        # the desired outer deadline; never unlock a live writer.
                        while self.processes.group_active(process, identity):
                            time.sleep(0.02)
                    process.wait()
            finally:
                for stream in streams:
                    stream.close()
                if null is not None:
                    null.close()
                for index, name in enumerate(("stdout", "stderr")):
                    self._write(stage + "/ocean." + name, data[index])
                guard = {"schema_version": 1, "originals_preserved": False,
                         "owned_copy_preserved": False, "ledger_preserved": False,
                         "cds_lib_preserved": False, "qualified": False,
                         "closure_trust": "NOT_ESTABLISHED"}
                observations = (
                    ("originals_preserved", lambda: self._snapshots() == original),
                    ("owned_copy_preserved",
                     lambda: self.copying.snapshot(copied_path) == owned_copy),
                    ("ledger_preserved", lambda: self._ledger() == ledger),
                    ("cds_lib_preserved", lambda: self._read(stage + "/cds.lib") == cds_raw),
                )
                for name, check in observations:
                    try:
                        guard[name] = check()
                    except (OSError, IOError, ValueError):
                        guard[name] = False
                self._write(stage + "/protection-check.json", canonical(guard))
                if not all(guard[name] for name, check in observations):
                    raise ValueError("binding_observation_post_process_protection_failed")

    def _read(self, filename):
        info = os.lstat(filename)
        return self.copying.read_leaf(filename, info, FRAME_BYTES)
