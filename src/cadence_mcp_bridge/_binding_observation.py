"""Fixed owned-copy OA observer, Python2.6 stdlib only.

The diagnostic observe() never grants execution. The separate operator entry
requires a finite externally pinned admission and reviewed standard-VM execution
attestation. Declared-file integrity alone is neither complete closure nor approval.
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
try:
    INTEGERS = (int, long)  # noqa: F821
except NameError:
    INTEGERS = (int,)

SNAPSHOT_ENTRIES = 64
SNAPSHOT_BYTES = 1048576
DEPENDENCY_LIBRARIES = 8
DEPENDENCY_ENTRIES = 8192
DEPENDENCY_BYTES = 67108864
FRAME_BYTES = 65536
STAGE_BYTES = 8388608
PROCESS_SECONDS = 45
OUTER_SECONDS = 60
PROCESS_INVENTORY_ENTRIES = 4096
STAGE_INODES = 256
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
        self._process_module = modules["process.py"]
        self.processes = self._process_module.EdaWorker(None, None, None, None, None)
        self.root = self.profile["paths"]["managed_root"]
        self._deadline = None
        self._cancelled = lambda: False
        self._execution_guard = None
        self._launch_guard = None
        self._protection_receipt = None
        self._process_receipt = {"start_attempted": False, "new_eda_starts": 0,
                                 "returncode": None, "cleanup_complete": True}

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

    def _closed_document(self, raw, limit):
        if type(raw) is not bytes or not 1 <= len(raw) <= limit:
            raise ValueError("binding_observation_document_bound")
        try:
            value = json.loads(raw.decode("ascii"))
            if type(value) is not dict or canonical(value) != raw:
                raise ValueError("binding_observation_canonical_document_required")
        except (UnicodeError, ValueError, RuntimeError, OverflowError):
            raise ValueError("binding_observation_invalid_document")
        return value

    def _admission(self, request, admission_raw, manifest_raw, closure_raw):
        # Expected hashes originate in the external operator invocation, not in
        # the documents themselves. The fixed host bootstrap pins the entire
        # envelope. This validates its finite scope, not whether a human spoke.
        self._bound(request)
        admission = self._closed_document(admission_raw, 16384)
        closure = self._closed_document(closure_raw, 32768)
        subject = dict((key, self.selection[key]) for key in (
            "profile_sha256", "registration_sha256", "request_sha256",
            "collector_sha256", "helper_sha256"))
        fields = set(subject) | set((
            "schema_version", "kind", "authority_reference", "approval_receipt_sha256",
            "prepared_plan_sha256", "package_sha256", "resource_domain_sha256",
            "identity_manifest_sha256", "expected_counter", "declared_members_sha256",
            "execution_attestation_sha256", "predecessor", "valid_from_unix",
            "valid_until_unix", "limits",
        ))
        limits = {"remote_attempts": 1, "ocean_starts": 1, "outer_seconds": OUTER_SECONDS,
                  "ocean_seconds": PROCESS_SECONDS, "stage_bytes": STAGE_BYTES,
                  "new_simulations": 0, "new_extractions": 0, "new_reserved_bytes": 0}
        if set(admission) != fields or type(admission["schema_version"]) is not int or (
            admission["schema_version"] != 1 or admission["kind"] != "FINITE_BINDING_OBSERVATION"
            or canonical(admission["limits"]) != canonical(limits)
            or any(admission[key] != value for key, value in subject.items())
        ):
            raise ValueError("binding_observation_admission_scope")
        for key in fields:
            if key.endswith("_sha256"):
                token(admission[key], r"^[0-9a-f]{64}$")
        token(admission["authority_reference"], r"^[A-Za-z0-9][A-Za-z0-9_:. /#-]{0,255}$")
        predecessor = admission["predecessor"]
        if type(predecessor) is not dict or set(predecessor) != set((
            "predecessor_collector_sha256", "predecessor_plan_sha256",
            "predecessor_host_request_sha256", "predecessor_remote_request_sha256",
        )):
            raise ValueError("binding_observation_predecessor_shape")
        for value in predecessor.values():
            token(value, r"^[0-9a-f]{64}$")
        counter = admission["expected_counter"]
        if type(counter) is not dict or set(counter) != set((
            "campaign_id", "count", "result_reserved_bytes",
        )) or not isinstance(counter["campaign_id"], STRINGS) or not counter["campaign_id"] or (
            len(counter["campaign_id"]) > 128
            or any(type(counter[key]) not in INTEGERS or counter[key] < 0
                   for key in ("count", "result_reserved_bytes"))
        ):
            raise ValueError("binding_observation_expected_counter")
        now = time.time()
        for document in (admission, closure):
            if any(type(document.get(key)) is not int for key in (
                "valid_from_unix", "valid_until_unix",
            )) or not (0 < document["valid_from_unix"] <= now < document["valid_until_unix"]
                        < 4102444800) or (
                document["valid_until_unix"] - document["valid_from_unix"] > 3600
            ):
                raise ValueError("binding_observation_authority_not_current")
        if len(manifest_raw) > 262144 or digest(manifest_raw) != (
            admission["declared_members_sha256"]
        ) or digest(closure_raw) != admission["execution_attestation_sha256"]:
            raise ValueError("binding_observation_execution_evidence_binding")
        if set(closure) != set((
            "schema_version", "kind", "subject", "declared_members_sha256", "launch_recipe",
            "review_reference", "trust_categories", "runtime_roots", "libraries",
            "permitted_effects", "unresolved_dependencies", "valid_from_unix", "valid_until_unix",
        )) or type(closure["schema_version"]) is not int or closure["schema_version"] != 1 or (
            closure["kind"] != "STANDARD_VM_BINDING_OBSERVER_EXECUTION_ATTESTATION"
            or closure["subject"] != subject
            or closure["declared_members_sha256"] != admission["declared_members_sha256"]
            or closure["launch_recipe"] != "OWNED_COPY_NOGRAPH_NOCDSINIT_V1"
            or closure["permitted_effects"] != "PRIVATE_STAGE_ONLY"
            or closure["unresolved_dependencies"] != []
            or closure["runtime_roots"] != sorted(self.profile["paths"]["protected_roots"])
            or closure["libraries"] != sorted(self.route["libraries"], key=lambda x: x["name"])
        ):
            raise ValueError("binding_observation_execution_attestation_scope")
        token(closure["review_reference"], r"^[A-Za-z0-9][A-Za-z0-9_:. /#-]{0,255}$")
        categories = closure["trust_categories"]
        required = set(("system_interpreter_and_startup", "os_loader_and_libraries",
                        "cadence_launchers_runtime_and_contexts",
                        "registered_library_initializers"))
        if type(categories) is not list or len(categories) != 4 or any(
            type(item) is not dict or set(item) != set(("category", "evidence_sha256"))
            for item in categories
        ) or set(item["category"] for item in categories) != required:
            raise ValueError("binding_observation_execution_trust_categories")
        for item in categories:
            token(item["evidence_sha256"], r"^[0-9a-f]{64}$")
        return admission

    def _cancel_check(self):
        if self._cancelled():
            raise ValueError("binding_observation_cancelled")

    def observe_authorized(self, request, admission_raw, manifest_raw, closure_raw):
        """One finite operator operation; never called by import/doctor/MCP.

        Installation/init behavior is externally reviewed operator trust, not a
        dynamic dependency proof or electrical qualification. Failure evidence,
        both spent claims and the existing ledger always remain in place.
        """
        admission = self._admission(request, admission_raw, manifest_raw, closure_raw)
        self._deadline = os.times()[4] + OUTER_SECONDS
        self._launch_guard = None
        self._protection_receipt = None
        self._process_receipt = {"start_attempted": False, "new_eda_starts": 0,
                                 "returncode": None, "cleanup_complete": True}
        result = {
            "schema_version": 1, "kind": "BINDING_OBSERVATION_TERMINAL", "status": "REJECTED",
            "observation_id": request["observation_id"],
            "request_sha256": self.selection["request_sha256"],
            "collector_sha256": self.selection["collector_sha256"],
            "worker_sha256": self.selection["helper_sha256"],
            "admission_sha256": digest(admission_raw),
            "declared_members_sha256": admission["declared_members_sha256"],
            "execution_attestation_sha256": admission["execution_attestation_sha256"],
            "execution_trust": "NOT_ESTABLISHED", "qualification_established": False,
            "start_attempted": False, "new_eda_starts": 0, "returncode": None,
            "frame": None, "frame_sha256": None, "counter_before": None, "counter_after": None,
            "originals_preserved": False, "owned_copy_preserved": False,
            "ledger_preserved": False, "cds_lib_preserved": False, "cleanup_complete": True,
            "failure_code": None, "retry_permitted": False, "new_simulations": 0,
            "new_extractions": 0, "new_reserved_bytes": 0,
        }
        stage = None
        binding = {"root_sha256": digest(self.root.encode("utf-8")),
                   "resource_domain_sha256": admission["resource_domain_sha256"],
                   "ledger_ref": self.accounting.LEDGER,
                   "identity_manifest_sha256": admission["identity_manifest_sha256"]}
        # Do not create a replacement ledger/lock. The existing identity audit
        # checks every retained reservation and enforces the active resource policy.
        with self.accounting.ReservationSession(self.root) as session:
            try:
                self._preflight(session)
                counter, records = session.observe(binding)
                if counter != admission["expected_counter"] or (
                    self.registration["identity_manifest_sha256"] != (
                        binding["identity_manifest_sha256"])
                ):
                    raise ValueError("binding_observation_live_accounting_mismatch")
                result["counter_before"] = counter
                result["counter_after"] = counter
                storage = self._bounded_storage()
                self._declared_code_members(manifest_raw, admission["declared_members_sha256"])
                self._snapshots()
                result["execution_trust"] = "OPERATOR_ATTESTED_STANDARD_VM"

                def guard():
                    self._cancel_check()
                    self._admission(request, admission_raw, manifest_raw, closure_raw)
                    if self._bounded_storage() != storage:
                        raise ValueError("binding_observation_storage_identity_drift")
                    self._declared_code_members(manifest_raw, admission["declared_members_sha256"])
                    session.check()
                    if session.observe(binding)[0] != counter:
                        raise ValueError("binding_observation_live_accounting_drift")

                guard()
                # A fixed remote campaign claim also prevents another host or
                # fresh observation ID from retrying this single allowance.
                claim = self.root + "/binding-observation-01.private.json"
                if os.path.lexists(claim):
                    raise ValueError("binding_observation_remote_attempt_spent")
                self._write(claim, canonical({
                    "schema_version": 1, "status": "ATTEMPT_SPENT_NO_RETRY",
                    "observation_id": request["observation_id"],
                    "admission_sha256": digest(admission_raw),
                    "request_sha256": self.selection["request_sha256"],
                }))
                self._execution_guard = guard
                # Recheck pure admission immediately before launch as well as
                # at the expensive integrity boundaries. Durable marker fsync
                # can outlast either authority window or the process deadline.
                def launch_guard():
                    self._admission(request, admission_raw, manifest_raw, closure_raw)
                    if self._bounded_storage() != storage:
                        raise ValueError("binding_observation_storage_identity_drift")
                self._launch_guard = launch_guard
                stage, before, copied = self._stage(request, session)
                guard()
                value = self._program(stage, session, request)
                guard()
                result.update(status="PROCESS_COMPLETED", frame=value["frame"].decode("ascii"),
                              frame_sha256=digest(value["frame"]))
            except BaseException as error:
                message = str(error)
                code = message if re.match(r"^binding_observation_[a-z0-9_]+$", message) else (
                    "binding_observation_internal_failure")
                result["failure_code"] = code
                if self._process_receipt["start_attempted"]:
                    result["status"] = "TIMED_OUT" if code.endswith("timeout") else "FAILED"
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    result["status"] = "UNKNOWN"
            finally:
                self._execution_guard = None
                self._launch_guard = None
                result.update(self._process_receipt)
                try:
                    result["counter_after"] = session.observe(binding)[0]
                except Exception:
                    result["counter_after"] = None
                # Only parent-owned checks can establish conservation. The child
                # may create a colliding evidence leaf; retain that leaf, but
                # never promote its contents into the terminal receipt.
                if self._protection_receipt is not None:
                    for name in ("originals_preserved", "owned_copy_preserved",
                                 "ledger_preserved", "cds_lib_preserved"):
                        result[name] = self._protection_receipt.get(name) is True
                if result["status"] == "PROCESS_COMPLETED" and (
                    not all(result[key] for key in ("originals_preserved", "owned_copy_preserved",
                                                   "ledger_preserved", "cds_lib_preserved",
                                                   "cleanup_complete"))
                    or result["counter_before"] != result["counter_after"]
                ):
                    result.update(status="FAILED", frame=None, frame_sha256=None,
                                  failure_code="binding_observation_terminal_conservation_failed")
                if stage is not None:
                    # Keep the full frame in its original fixed leaf. A maximal
                    # escaped frame does not fit the 64KiB evidence-record bound.
                    disk_result = dict(result)
                    disk_result.pop("frame")
                    try:
                        self._write_evidence(stage, "terminal.json", canonical(disk_result))
                    except Exception:
                        result.update(status="UNKNOWN", frame=None, frame_sha256=None,
                                      failure_code="binding_observation_terminal_publication_failed")
        return result

    def _snapshots(self):
        self.copying.MAX_ENTRIES, self.copying.MAX_BYTES = SNAPSHOT_ENTRIES, SNAPSHOT_BYTES
        source = self._bounded_copy_call("snapshot", self.route["source_cell"])
        remaining_entries = SNAPSHOT_ENTRIES - source["entries"]
        remaining_bytes = SNAPSHOT_BYTES - source["bytes"]
        if remaining_entries < 1 or remaining_bytes < 0:
            raise ValueError("binding_observation_combined_snapshot_bound")
        self.copying.MAX_ENTRIES, self.copying.MAX_BYTES = remaining_entries, remaining_bytes
        try:
            state = self._bounded_copy_call("snapshot", self.route["source_state"])
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
                    snapshot = self._bounded_copy_call("dependency_snapshot", library["path"])
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
        records, entries, library_entries = [], [0], [0]

        def record(location):
            self.copying.path(location)
            info = os.lstat(location)
            records.append((location, self.copying.identity(info), info.st_nlink,
                            "%.9f" % info.st_ctime))
            return info

        def tree(location, depth):
            if depth > 16:
                raise ValueError("binding_observation_dependency_namespace_bound")
            info = record(location)
            if stat.S_ISDIR(info.st_mode):
                names = self._bounded_directory_names(
                    location, min(DEPENDENCY_ENTRIES - entries[0], 4096 - library_entries[0]),
                    "binding_observation_dependency_namespace_bound",
                )
                # Claim discovered children before visiting any subtree, so a
                # nested directory cannot spend already-listed sibling entries.
                entries[0] += len(names)
                library_entries[0] += len(names)
                records.append((location, names))
                for name in names:
                    tree(os.path.join(location, name), depth + 1)
                if self._bounded_directory_names(
                    location, len(names), "binding_observation_dependency_namespace_drift",
                ) != names:
                    raise ValueError("binding_observation_dependency_namespace_drift")
            elif not stat.S_ISREG(info.st_mode):
                raise ValueError("binding_observation_dependency_namespace_type")

        for library in libraries:
            if entries[0] >= DEPENDENCY_ENTRIES:
                raise ValueError("binding_observation_dependency_namespace_bound")
            entries[0] += 1
            library_entries[0] = 1
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

    def _bounded_directory_names(self, location, maximum, rejection):
        # Sort only an already bounded collection. The iterator itself never
        # materializes os.listdir/os.walk, including on the Python2.6 VM.
        names = []
        entries = self._stage_directory_entries(location)
        try:
            for name in entries:
                if len(names) >= maximum:
                    raise ValueError(rejection)
                names.append(name)
        finally:
            entries.close()
        return sorted(names)

    def _bounded_copy_call(self, operation, *arguments):
        # Preserve the authenticated helper's exact metadata/digest format and
        # read/byte/depth/link rules. Only this fresh memory module's listdir is
        # replaced for this call; the process-wide os module is never mutated.
        original_os = self.copying.os
        bounded_os = types.ModuleType("binding_observation_dependency_os")
        bounded_os.__dict__.update(original_os.__dict__)
        if operation not in ("snapshot", "dependency_snapshot", "copy_owned"):
            raise ValueError("binding_observation_copy_operation")
        roots = arguments[:2] if operation == "copy_owned" else arguments[:1]
        discovered, directories = dict((root, 1) for root in roots), {}

        def bounded_listdir(path):
            matches = [root for root in roots if path == root or path.startswith(root + os.sep)]
            if len(matches) != 1:
                raise ValueError("binding_observation_copy_enumeration_root")
            root = matches[0]
            maximum = directories.get(path, self.copying.MAX_ENTRIES - discovered[root])
            names = self._bounded_directory_names(path, maximum, "native_copy_tree_bound")
            if path not in directories:
                discovered[root] += len(names)
                directories[path] = len(names)
            return names

        bounded_os.listdir = bounded_listdir
        self.copying.os = bounded_os
        try:
            return getattr(self.copying, operation)(*arguments)
        finally:
            self.copying.os = original_os

    def _stage(self, request, session):
        # The operational caller has already established finite admission/trust.
        self._bound(request)
        if self._deadline is None:
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
        copied = self._bounded_copy_call("copy_owned", self.route["source_cell"],
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

    def _write_evidence(self, stage, leaf, raw):
        # Reserve before every exclusive publication, including a fallback after
        # a partial write. Existing child evidence is never a replaceable leaf.
        if len(raw) > FRAME_BYTES:
            raise ValueError("binding_observation_record_bound")
        filename = stage + "/" + leaf
        if os.path.lexists(filename):
            raise ValueError("binding_observation_evidence_leaf_exists")
        self.copying.owned_parent(stage)
        unit = max(512, getattr(os.lstat(stage), "st_blksize", 4096))
        if hasattr(os, "statvfs"):
            fs = os.statvfs(stage)
            unit = max(unit, fs.f_bsize, fs.f_frsize)
        # Charge rounded content allocation and two directory blocks, rather
        # than treating sparse logical size or an empty leaf as free capacity.
        # This is a bounded local precheck, not atomic exclusion of another
        # same-UID writer changing the filesystem after the observation.
        reservation = ((len(raw) + unit - 1) // unit + 2) * unit
        self._stage_size(stage, 1, reservation)
        self._write(filename, raw)

    def _stage_size(self, stage, reserved_entries=0, reserved_bytes=0):
        sizes, entries = [0, 0], [0]

        def account(selected):
            # Preserve the prior conservative accounting: a directory is
            # charged as a child and again when its own entries are visited.
            # Mutable counters avoid Python3-only nonlocal syntax.
            info = os.lstat(selected)
            if not stat.S_ISDIR(info.st_mode) and not stat.S_ISREG(info.st_mode):
                raise ValueError("binding_observation_stage_special")
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError("binding_observation_stage_hardlink")
            entries[0] += 1
            sizes[0] += info.st_size if stat.S_ISREG(info.st_mode) else 0
            sizes[1] += getattr(info, "st_blocks", (info.st_size + 511) // 512) * 512
            if entries[0] + reserved_entries > 256 or (
                max(sizes) + reserved_bytes > STAGE_BYTES
            ):
                raise ValueError("binding_observation_stage_capacity")
            return info

        pending = [stage]
        while pending:
            parent = pending.pop()
            if self.copying.path(parent) != parent:
                raise ValueError("binding_observation_stage_path")
            account(parent)
            names = self._stage_directory_entries(parent)
            try:
                for name in names:
                    selected = os.path.join(parent, name)
                    info = account(selected)
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(selected)
            finally:
                names.close()
        return tuple(sizes)

    def _stage_directory_entries(self, path):
        # Stream names: Python2.6 os.walk/listdir materialize an unbounded child
        # directory before the stage's 257th-entry rejection can take effect.
        if os.name == "nt":
            names = os.scandir(path)
            try:
                for entry in names:
                    yield entry.name
            finally:
                names.close()
            return
        if platform.system() != "Linux" or platform.machine() not in ("i686", "x86_64"):
            raise ValueError("binding_observation_directory_platform")
        import ctypes

        # Linux dirent64 uses the same fixed offsets on the standard i686 VM
        # and x86_64 CI. Configure libc before opening any owned descriptor.
        libc = ctypes.CDLL(None, use_errno=True)
        libc.fdopendir.argtypes, libc.fdopendir.restype = [ctypes.c_int], ctypes.c_void_p
        libc.readdir64.argtypes, libc.readdir64.restype = [ctypes.c_void_p], ctypes.c_void_p
        libc.closedir.argtypes, libc.closedir.restype = [ctypes.c_void_p], ctypes.c_int
        before = os.lstat(path)
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stream = None
        try:
            if self.copying.identity(os.fstat(fd)) != self.copying.identity(before):
                raise ValueError("binding_observation_directory_drift")
            stream = libc.fdopendir(fd)
            if not stream:
                raise OSError(ctypes.get_errno(), "binding_observation_directory_stream")
            while True:
                ctypes.set_errno(0)
                entry = libc.readdir64(stream)
                if not entry:
                    if ctypes.get_errno():
                        raise OSError(ctypes.get_errno(), "binding_observation_directory_stream")
                    break
                length = ctypes.c_ushort.from_address(entry + 16).value
                if not 20 <= length <= 280:
                    raise ValueError("binding_observation_directory_record")
                raw = ctypes.string_at(entry + 19, length - 19).split(b"\x00", 1)[0]
                if raw not in (b".", b".."):
                    yield raw.decode("utf-8")
            if (self.copying.identity(os.fstat(fd)) != self.copying.identity(before) or
                    self.copying.identity(os.lstat(path)) != self.copying.identity(before)):
                raise ValueError("binding_observation_directory_drift")
        finally:
            if stream:
                if libc.closedir(stream) != 0:
                    raise OSError(ctypes.get_errno(), "binding_observation_directory_close")
            else:
                os.close(fd)

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

    def _declared_code_members(self, manifest_raw, expected_sha256):
        # A pinned finite list is not a complete dynamic loader/init closure or
        # execution authority. This private check is not called by observe().
        token(expected_sha256, r"^[0-9a-f]{64}$")
        if type(manifest_raw) is not bytes or not 1 <= len(manifest_raw) <= 262144:
            raise ValueError("binding_observation_declared_manifest_bound")
        if digest(manifest_raw) != expected_sha256:
            raise ValueError("binding_observation_declared_manifest_digest")

        def invalid_constant(value):
            raise ValueError("binding_observation_declared_manifest_constant")

        try:
            text = manifest_raw.decode("ascii")
            depth, quoted, escaped = 0, False, False
            for character in text:
                if quoted:
                    if escaped:
                        escaped = False
                    elif character == "\\":
                        escaped = True
                    elif character == '"':
                        quoted = False
                elif character == '"':
                    quoted = True
                elif character in ("{", "["):
                    depth += 1
                    if depth > 8:
                        raise ValueError("binding_observation_declared_manifest_depth")
                elif character in ("}", "]"):
                    depth -= 1
                    if depth < 0:
                        raise ValueError("binding_observation_declared_manifest_depth")
            manifest = json.loads(text, parse_constant=invalid_constant)
            # Python2.6 has no object_pairs_hook. Equality with the canonical
            # encoding also rejects every duplicate key before filesystem work.
            if canonical(manifest) != manifest_raw:
                raise ValueError("binding_observation_declared_manifest_canonical")
        except (ValueError, TypeError, RuntimeError, OverflowError, UnicodeError):
            raise ValueError("binding_observation_declared_manifest_json")
        keys = ("schema_version", "scope", "profile_sha256", "registration_sha256",
                "worker_sha256", "request_sha256", "members", "directories")
        if not isinstance(manifest, dict) or set(manifest) != set(keys) or (
            type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
            or manifest["scope"] != "DECLARED_MEMBERS_ONLY"
        ):
            raise ValueError("binding_observation_declared_manifest_shape")
        for key in keys[2:6]:
            token(manifest[key], r"^[0-9a-f]{64}$")
        if (manifest["profile_sha256"] != self.selection["profile_sha256"] or
                manifest["profile_sha256"] != digest(canonical(self.profile)) or
                manifest["registration_sha256"] != self.selection["registration_sha256"] or
                manifest["registration_sha256"] != digest(canonical(self.registration)) or
                manifest["worker_sha256"] != self.selection["helper_sha256"] or
                manifest["request_sha256"] != self.selection["request_sha256"]):
            raise ValueError("binding_observation_declared_manifest_binding")
        routes = [route for route in self.registration["routes"] if (
            route["design_id"], route["analysis_id"]
        ) == (self.selection["design_id"], self.selection["analysis_id"])]
        if len(routes) != 1 or self.route != routes[0]:
            raise ValueError("binding_observation_declared_route_binding")
        if (not isinstance(manifest["members"], list) or
                not 1 <= len(manifest["members"]) <= 128 or
                not isinstance(manifest["directories"], list) or
                not 1 <= len(manifest["directories"]) <= 1024):
            raise ValueError("binding_observation_declared_member_bound")

        def valid_path(value):
            if value != "/":
                token(value, r"^/[A-Za-z0-9_#./-]{1,511}$")
                parts = value.split("/")[1:]
                if len(parts) > 64 or any(part in ("", ".", "..") for part in parts):
                    raise ValueError("binding_observation_declared_path")
            elif not isinstance(value, STRINGS):
                raise ValueError("binding_observation_declared_path")
            return value

        try:
            integers = (int, long)  # noqa: F821
        except NameError:
            integers = (int,)
        uid = os.getuid() if os.name == "posix" else None
        fields = ("device", "inode", "mode", "uid", "gid", "nlink", "size", "mtime", "ctime")

        def valid_metadata(value, directory):
            if not isinstance(value, dict) or set(value) != set(fields):
                raise ValueError("binding_observation_declared_metadata_shape")
            for key in fields[:7]:
                if type(value[key]) not in integers or not 0 <= value[key] <= 9223372036854775807:
                    raise ValueError("binding_observation_declared_metadata_integer")
            for key in fields[7:]:
                number = value[key]
                if not isinstance(number, STRINGS) or not 1 <= len(number) <= 32:
                    raise ValueError("binding_observation_declared_metadata_time")
                try:
                    parsed = float(number)
                except (ValueError, OverflowError):
                    raise ValueError("binding_observation_declared_metadata_time")
                if parsed != parsed or abs(parsed) == float("inf") or "%.17g" % parsed != number:
                    raise ValueError("binding_observation_declared_metadata_time")
            mode = value["mode"]
            if value["uid"] not in (0, uid) or mode & 18 or (
                not stat.S_ISDIR(mode) if directory else
                not stat.S_ISREG(mode) or value["nlink"] != 1 or value["size"] > 16777216
            ):
                raise ValueError("binding_observation_declared_metadata_trust")
            return value

        def inside(path, root):
            return root == "/" or path == root or path.startswith(root + "/")

        runtime_roots = [valid_path(root) for root in self.profile["paths"]["protected_roots"]]
        init_roots = [valid_path(library["path"]) for library in routes[0]["libraries"]]
        members, directories, ancestors, total, runtime = {}, {}, set(), 0, []
        previous = None
        for member in manifest["members"]:
            if not isinstance(member, dict) or set(member) != set(
                ("role", "path", "sha256", "metadata")
            ):
                raise ValueError("binding_observation_declared_member_shape")
            path = valid_path(member["path"])
            token(member["sha256"], r"^[0-9a-f]{64}$")
            if previous is not None and path <= previous:
                raise ValueError("binding_observation_declared_member_order")
            previous = path
            roots = runtime_roots if member["role"] == "runtime" else init_roots
            if member["role"] not in ("runtime", "library_init") or not any(
                inside(path, root) for root in roots
            ):
                raise ValueError("binding_observation_declared_member_scope")
            valid_metadata(member["metadata"], False)
            total += member["metadata"]["size"]
            if total > 67108864:
                raise ValueError("binding_observation_declared_content_bound")
            members[path] = member
            if member["role"] == "runtime":
                runtime.append(member)
            current = os.path.dirname(path)
            while True:
                ancestors.add(current)
                if current == "/":
                    break
                current = os.path.dirname(current)
        previous = None
        for directory in manifest["directories"]:
            if not isinstance(directory, dict) or set(directory) != set(("path", "metadata")):
                raise ValueError("binding_observation_declared_directory_shape")
            path = valid_path(directory["path"])
            if previous is not None and path <= previous:
                raise ValueError("binding_observation_declared_directory_order")
            previous = path
            directories[path] = valid_metadata(directory["metadata"], True)
        if set(directories) != ancestors or set(members) & ancestors or not runtime:
            raise ValueError("binding_observation_declared_ancestor_union")
        # All manifest/schema/baseline checks above are filesystem-free.
        if (os.name != "posix" or platform.system() != "Linux" or uid == 0 or
                os.geteuid() != uid):
            raise ValueError("binding_observation_declared_normal_linux_user_required")
        deadline = os.times()[4] + OUTER_SECONDS
        if self._deadline is not None:
            deadline = min(deadline, self._deadline)

        def check_deadline():
            if os.times()[4] >= deadline:
                raise ValueError("binding_observation_declared_deadline")

        def metadata(info):
            return dict(zip(fields, (
                info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_nlink, info.st_size, "%.17g" % info.st_mtime, "%.17g" % info.st_ctime,
            )))

        def check_info(info, expected):
            check_deadline()
            if metadata(info) != expected:
                raise ValueError("binding_observation_declared_metadata_drift")

        def open_checked(path, directory):
            # /proc magic links address retained parents; every untrusted path
            # component is still opened separately with O_NOFOLLOW. At most a
            # parent and its child remain held after each component check.
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            current, child = None, None
            try:
                check_deadline()
                current = os.open("/", flags | os.O_DIRECTORY)
                check_info(os.fstat(current), directories["/"])
                check_info(os.lstat("/"), directories["/"])
                if path == "/":
                    result, current = (current, None, None), None
                    return result
                named, parts = "", path.split("/")[1:]
                for index, part in enumerate(parts):
                    check_deadline()
                    named += "/" + part
                    last = index == len(parts) - 1
                    is_directory = not last or directory
                    expected = directories[named] if is_directory else members[named]["metadata"]
                    selected = "/proc/self/fd/%d/%s" % (current, part)
                    child = os.open(selected, flags | (os.O_DIRECTORY if is_directory else 0))
                    check_info(os.fstat(child), expected)
                    check_info(os.lstat(named), expected)
                    if last:
                        result, child, current = (child, current, selected), None, None
                        return result
                    os.close(current)
                    current, child = child, None
            finally:
                try:
                    if child is not None:
                        os.close(child)
                finally:
                    if current is not None:
                        os.close(current)

        def close_checked(opened):
            try:
                os.close(opened[0])
            finally:
                if opened[1] is not None:
                    os.close(opened[1])

        def guarded_read(operation, *arguments):
            # The authenticated helper transfers its opened descriptor to a
            # stream only when fdopen returns. Close an otherwise orphaned raw
            # descriptor on that failure; successful streams keep sole ownership
            # and the unchanged helper closes them. The process-wide os module
            # is never changed, and every exception restores this fresh module.
            original_os = self.copying.os
            safe_os = types.ModuleType("binding_observation_declared_read_os")
            safe_os.__dict__.update(original_os.__dict__)

            def fdopen(fd, mode):
                try:
                    return original_os.fdopen(fd, mode)
                except BaseException:
                    try:
                        original_os.close(fd)
                    except OSError as error:
                        if error.errno != 9:  # fdopen may already have closed it.
                            raise
                    raise

            safe_os.fdopen = fdopen
            self.copying.os = safe_os
            try:
                return operation(*arguments)
            finally:
                self.copying.os = original_os

        def check_union():
            for path in sorted(directories):
                opened = open_checked(path, True)
                try:
                    check_info(os.fstat(opened[0]), directories[path])
                    check_info(os.lstat(path), directories[path])
                finally:
                    close_checked(opened)
            for path in sorted(members):
                opened = open_checked(path, False)
                try:
                    check_info(os.fstat(opened[0]), members[path]["metadata"])
                    check_info(os.lstat(path), members[path]["metadata"])
                finally:
                    close_checked(opened)

        check_deadline()
        binding = self.profile["tools"]["ocean"]
        resolved = os.path.realpath(binding["path"])
        if not any(member["path"] == resolved and member["sha256"] == binding["sha256"]
                   for member in runtime):
            raise ValueError("binding_observation_declared_ocean_member")
        check_union()
        check_deadline()
        ocean = guarded_read(self._ocean_trust)
        check_deadline()
        if not any(member["path"] == ocean["resolved"] and member["sha256"] == ocean["sha256"]
                   for member in runtime):
            raise ValueError("binding_observation_declared_ocean_member")
        for path in sorted(members):
            member = members[path]
            opened = open_checked(path, False)
            try:
                info = os.fstat(opened[0])
                check_info(info, member["metadata"])
                raw = guarded_read(
                    self.copying.read_leaf, opened[2], info, member["metadata"]["size"],
                )
                check_deadline()
                check_info(os.fstat(opened[0]), member["metadata"])
                check_info(os.lstat(path), member["metadata"])
                check_info(os.fstat(opened[1]), directories[os.path.dirname(path)])
                check_info(os.lstat(os.path.dirname(path)), directories[os.path.dirname(path)])
                if len(raw) != member["metadata"]["size"] or digest(raw) != member["sha256"]:
                    raise ValueError("binding_observation_declared_content_drift")
            finally:
                close_checked(opened)
        # Existing named entry validation performs at most two additional16MiB
        # reads in total. Finish both before the last metadata-only union check.
        if guarded_read(self._ocean_trust) != ocean:
            raise ValueError("binding_observation_declared_ocean_drift")
        check_deadline()
        check_union()
        return {
            "schema_version": 1, "scope": "DECLARED_MEMBERS_ONLY",
            "status": "EXACT_MEMBER_INTEGRITY_VERIFIED", "manifest_sha256": expected_sha256,
            "member_count": len(members), "directory_count": len(directories),
            "content_bytes": total,
            "qualified": False, "closure_trust": "NOT_ESTABLISHED", "execution_authorized": False,
            "new_eda_starts": 0, "new_simulations": 0, "new_extractions": 0,
            "new_reservations": 0, "new_claims": 0,
        }

    def _ledger(self):
        selected = self.root + "/" + self.accounting.LEDGER
        info = self.accounting.safe(selected)
        raw = self.copying.read_leaf(selected, info, 8192)
        return self.copying.identity(info), digest(raw)

    def _preflight(self, session):
        self._cancel_check()
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
        names = self._stage_directory_entries("/proc")
        try:
            for count, name in enumerate(names):
                self._cancel_check()
                if self._deadline is not None and os.times()[4] >= self._deadline:
                    raise ValueError("binding_observation_outer_deadline")
                if count >= PROCESS_INVENTORY_ENTRIES:
                    raise ValueError("binding_observation_process_inventory_bound")
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
        finally:
            names.close()

    def _group_active(self, process, identity, cleanup=False):
        # Preserve the pinned helper's identity/UID/group semantics, but give only
        # its fresh private module a bounded streaming listdir. Normal polling
        # honors the observation deadline/cancellation; cleanup needs a fresh
        # finite scan even after those expire, and must never infer an empty group
        # from an incomplete inventory. A persistently unknown writer keeps the
        # caller's lifetime lock held rather than turning a timeout into success.
        deadline = os.times()[4] + OUTER_SECONDS
        if not cleanup and self._deadline is not None:
            deadline = min(deadline, self._deadline)

        def check():
            if not cleanup:
                self._cancel_check()
            if os.times()[4] >= deadline:
                raise ValueError("binding_observation_process_inventory_deadline")

        original_os = self._process_module.os
        bounded_os = types.ModuleType("binding_observation_process_os")
        bounded_os.__dict__.update(original_os.__dict__)
        inventories = []

        def enumerate_names(path):
            names = self._stage_directory_entries(path)
            try:
                for count, name in enumerate(names):
                    check()
                    if count >= PROCESS_INVENTORY_ENTRIES:
                        raise ValueError("binding_observation_process_inventory_bound")
                    yield name
                check()
            finally:
                names.close()

        def bounded_listdir(path):
            if path != "/proc":
                raise ValueError("binding_observation_process_inventory_path")
            names = enumerate_names(path)
            inventories.append(names)
            return names

        bounded_os.listdir = bounded_listdir
        self._process_module.os = bounded_os
        try:
            check()
            active = self.processes.group_active(process, identity)
            check()
            return active
        finally:
            try:
                for names in inventories:
                    names.close()
            finally:
                self._process_module.os = original_os

    def _mount_type(self, location):
        # Kernel-owned mount metadata, bounded before materialization. An ordinary
        # user cannot substitute a FUSE filesystem that merely reports small limits.
        fd = os.open("/proc/self/mountinfo", os.O_RDONLY | os.O_NOFOLLOW)
        stream = None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid()) or (
                info.st_mode & 146
            ):
                raise ValueError("binding_observation_storage_mount_metadata")
            stream = os.fdopen(fd, "rb")
            raw = stream.read(65537)
            if len(raw) > 65536 or not raw.endswith(b"\n"):
                raise ValueError("binding_observation_storage_mount_bound")
        finally:
            if stream is None:
                os.close(fd)
            else:
                stream.close()
        found = []
        for line in raw.decode("utf-8").splitlines():
            fields = line.split()
            if len(fields) < 10 or "-" not in fields:
                raise ValueError("binding_observation_storage_mount_metadata")
            named = re.sub(r"\\([0-7]{3})", lambda item: chr(int(item.group(1), 8)), fields[4])
            if named == location:
                separator = fields.index("-")
                if separator < 6 or separator + 3 >= len(fields):
                    raise ValueError("binding_observation_storage_mount_metadata")
                found.append(fields[separator + 1])
        if len(found) != 1 or found[0] not in ("ext2", "ext3", "ext4"):
            raise ValueError("binding_observation_persistent_bounded_filesystem_required")
        return found[0]

    def _bounded_storage(self):
        # A directory scan cannot cap aggregate writes or open-unlinked files.
        # Require an already provisioned, persistent, separately mounted small
        # filesystem. Its kernel block/inode ceilings include every writer and
        # unlinked-open inode. This read-only guard never mounts/formats/resizes.
        location = self.root + "/binding-observations"
        if not os.path.lexists(location):
            raise ValueError("binding_observation_bounded_filesystem_required")
        self.copying.owned_parent(location)
        before = os.lstat(location)
        fd = os.open(location, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(fd)
            def identity(item):
                return item.st_dev, item.st_ino, item.st_uid, item.st_gid, item.st_mode
            if not stat.S_ISDIR(before.st_mode) or stat.S_IMODE(before.st_mode) != 448 or (
                before.st_dev == os.lstat(self.root).st_dev
            ) or identity(before) != identity(opened):
                raise ValueError("binding_observation_bounded_filesystem_required")
            kind = self._mount_type(location)
            fs = os.fstatvfs(fd)
            capacity = fs.f_blocks * fs.f_frsize
            if not 0 < capacity <= STAGE_BYTES or not 0 < fs.f_files <= STAGE_INODES:
                raise ValueError("binding_observation_bounded_filesystem_required")
            if identity(os.fstat(fd)) != identity(before) or (
                identity(os.lstat(location)) != identity(before)
            ):
                raise ValueError("binding_observation_storage_identity_drift")
            return identity(before), kind, capacity, fs.f_files
        finally:
            os.close(fd)

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
        # argv is compiled here; no operator-supplied script/command is accepted.
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
        owned_copy = self._bounded_copy_call("snapshot", copied_path)
        if owned_copy["content_sha256"] != original["source"]["content_sha256"]:
            raise ValueError("binding_observation_owned_copy_drift")
        cds_raw = self._read(stage + "/cds.lib")
        if cds_raw != self._cds_lib(request, stage):
            raise ValueError("binding_observation_registered_library_mapping_drift")
        trust = self._ocean_trust()
        environment = self._environment(stage)
        if self._execution_guard is not None:
            self._execution_guard()
        deadline = min(os.times()[4] + PROCESS_SECONDS,
                       self._deadline - 3 if self._deadline is not None else os.times()[4] + 45)
        self._write(marker, canonical({"schema_version": 1,
                    "observation_id": request["observation_id"],
                    "request_sha256": self.selection["request_sha256"],
                    "collector_sha256": self.selection["collector_sha256"],
                    "semantics": "SPENT_BEFORE_ONE_START_NO_RETRY"}))
        process, identity, null = None, None, None
        streams, data = [], [b"", b""]
        body_failed = False
        self._process_receipt = {"start_attempted": False, "new_eda_starts": 0,
                                 "returncode": None, "cleanup_complete": True}
        try:
            session.check()
            self._cancel_check()
            null = open(os.devnull, "rb")
            if self._launch_guard is not None:
                self._launch_guard()
            if os.times()[4] >= deadline:
                raise ValueError("binding_observation_process_timeout")
            self._process_receipt["start_attempted"] = True
            self._process_receipt["cleanup_complete"] = False
            process = subprocess.Popen(
                [trust["named"], "-nograph", "-nocdsinit", "-log", stage + "/ocean.log",
                 "-cdslib", stage + "/cds.lib", "-restore", stage + "/observer.ocn"],
                cwd=stage, stdin=null, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                close_fds=True, shell=False, preexec_fn=os.setsid, env=environment,
            )
            self._process_receipt["new_eda_starts"] = 1
            streams = [process.stdout, process.stderr]
            identity = self.processes.process_identity(process.pid)
            pending = list(streams)
            while pending or self._group_active(process, identity):
                self._cancel_check()
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
            self._process_receipt["returncode"] = code
            process = None
            if code != 0:
                raise ValueError("binding_observation_program_failed")
            if self._ocean_trust() != trust:
                raise ValueError("binding_observation_ocean_post_drift")
            if self._snapshots() != original or (
                self._bounded_copy_call("snapshot", copied_path) != owned_copy
            ):
                raise ValueError("binding_observation_original_or_copy_post_drift")
            if self._ledger() != ledger or self._read(stage + "/cds.lib") != cds_raw:
                raise ValueError("binding_observation_ledger_or_config_drift")
            if self._execution_guard is not None:
                self._execution_guard()
            frame = self._read(stage + "/binding-frame.txt")
            self._stage_size(stage)
            return {"returncode": code, "frame": frame, "ocean": trust,
                    "qualified": False, "closure_trust": "NOT_ESTABLISHED"}
        except BaseException:
            body_failed = True
            raise
        finally:
            cleanup_failed = False
            try:
                if process is not None:
                    try:
                        if identity is None:
                            identity = self.processes.process_identity(process.pid)
                        if self._group_active(process, identity, cleanup=True):
                            self.processes.signal_group(process, identity, signal.SIGTERM)
                            end = os.times()[4] + 2
                            while (
                                self._group_active(process, identity, cleanup=True)
                                and os.times()[4] < end
                            ):
                                time.sleep(0.02)
                            if self._group_active(process, identity, cleanup=True):
                                self.processes.signal_group(process, identity, signal.SIGKILL)
                            # Keep the leader unreaped and the lifetime lock held
                            # until its entire owned group has stopped writing.
                            while self._group_active(process, identity, cleanup=True):
                                time.sleep(0.02)
                    except Exception:
                        # Successful Popen plus setsid pins this direct child's
                        # PID/PGID while it remains unreaped, even if /proc reads
                        # fail. Kill only that kernel-confirmed group, then keep
                        # the lifetime lock until the normal identity/group check
                        # can verify termination. Persistent inspection failure
                        # may exceed the host deadline; it must not unlock a live
                        # or unverified writer. Never poll()/wait() in this loop.
                        while True:
                            try:
                                if os.getpgid(process.pid) == process.pid:
                                    os.killpg(process.pid, signal.SIGKILL)
                            except OSError:
                                pass
                            try:
                                if identity is None:
                                    identity = self.processes.process_identity(process.pid)
                                if not self._group_active(process, identity, cleanup=True):
                                    break
                            except Exception:
                                pass
                            time.sleep(0.02)
                    self._process_receipt["returncode"] = process.wait()
                self._process_receipt["cleanup_complete"] = True
            except BaseException:
                cleanup_failed = True
                raise
            finally:
                self._finalize_evidence(
                    stage, streams, null, data, original, copied_path, owned_copy,
                    ledger, cds_raw, body_failed or cleanup_failed, cleanup_failed,
                )

    def _finalize_evidence(self, stage, streams, null, data, original, copied_path,
                           owned_copy, ledger, cds_raw, failure_active, cleanup_failed):
        # Every close/publication is independent: a child-created evidence name
        # must not skip conservation or replace the original process failure.
        errors = []
        for index, stream in enumerate(streams + ([null] if null is not None else [])):
            try:
                stream.close()
            except Exception:
                errors.append("close_stream_" + str(index))
        publications = {}
        for index, name in enumerate(("stdout", "stderr")):
            try:
                self._write_evidence(stage, "ocean." + name, data[index])
                publications[name] = "PRIMARY"
            except Exception:
                errors.append("publish_" + name)
                try:
                    self._write_evidence(stage, "ocean." + name + "-fallback", data[index])
                    publications[name] = "FALLBACK"
                except Exception:
                    errors.append("publish_" + name + "_fallback")
                    publications[name] = "FAILED"
        guard = {"schema_version": 1, "originals_preserved": False,
                 "owned_copy_preserved": False, "ledger_preserved": False,
                 "cds_lib_preserved": False, "qualified": False,
                 "closure_trust": "NOT_ESTABLISHED", "failure_active": failure_active,
                 "cleanup_failed": cleanup_failed,
                 "finalization_errors": errors, "stream_publication": publications,
                 "protection_record": "PRIMARY"}
        observations = (
            ("originals_preserved", lambda: self._snapshots() == original),
            ("owned_copy_preserved", lambda:
             self._bounded_copy_call("snapshot", copied_path) == owned_copy),
            ("ledger_preserved", lambda: self._ledger() == ledger),
            ("cds_lib_preserved", lambda: self._read(stage + "/cds.lib") == cds_raw),
        )
        for name, check in observations:
            try:
                guard[name] = check()
            except Exception:
                guard[name] = False
        # Independent of publication: a child-created primary or fallback must
        # not replace these parent observations in the terminal response.
        self._protection_receipt = guard
        try:
            self._write_evidence(stage, "protection-check.json", canonical(guard))
        except Exception:
            errors.append("publish_protection")
            guard["protection_record"] = "FALLBACK"
            try:
                # Exactly one fixed, exclusive fallback. Never overwrite a
                # child-created record or search for another retry filename.
                self._write_evidence(stage, "protection-check-fallback.json", canonical(guard))
            except Exception:
                errors.append("publish_protection_fallback")
        if not failure_active:
            if not all(guard[name] for name, check in observations):
                raise ValueError("binding_observation_post_process_protection_failed")
            if errors:
                raise ValueError("binding_observation_evidence_publication_failed")

    def _read(self, filename):
        info = os.lstat(filename)
        return self.copying.read_leaf(filename, info, FRAME_BYTES)
