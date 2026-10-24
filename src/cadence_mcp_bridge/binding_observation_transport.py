"""Bounded operator transport for the fixed installed binding observer.

This module neither approves nor claims an operation. Its caller must persist the
account/campaign one-shot claim before dispatch. A lost reply is unknown and may
never be retried; no transport recovery starts another observer.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shlex
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from importlib.resources import files
from typing import Any

from cadence_mcp_bridge import binding_observation_bootstrap as factory
from cadence_mcp_bridge.binding_observation import BindingScanRequest, parse_frame
from cadence_mcp_bridge.environments import EnvironmentProfile
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

INPUT_LIMIT = 2_097_152
STREAM_LIMIT = 131_072
TIMEOUT_SECONDS = 60
_DOCUMENTS = {
    "profile": 65_536, "registration": 262_144, "selection": 4096, "request": 4096,
    "admission": 65_536, "manifest": 262_144, "closure": 262_144,
}
_TERMINAL_KEYS = frozenset({
    "schema_version", "kind", "status", "observation_id", "request_sha256",
    "collector_sha256", "worker_sha256", "admission_sha256", "declared_members_sha256",
    "execution_attestation_sha256", "execution_trust", "qualification_established",
    "new_eda_starts", "start_attempted", "returncode", "frame", "frame_sha256",
    "counter_before", "counter_after", "originals_preserved", "owned_copy_preserved",
    "ledger_preserved", "cds_lib_preserved", "cleanup_complete", "failure_code",
    "retry_permitted", "new_simulations", "new_extractions", "new_reserved_bytes",
})


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pin(value: str) -> None:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("binding_transport_digest")


def _installed() -> tuple[bytes, dict[str, bytes]]:
    package = files("cadence_mcp_bridge")
    retained: dict[str, bytes] = {}
    for name in (factory._WORKER, *(item[0] for item in factory._HELPERS.values())):
        with package.joinpath(name).open("rb") as stream:
            raw = stream.read(factory._CODE_LIMIT + 1)
        if type(raw) is not bytes or not raw or len(raw) > factory._CODE_LIMIT:
            raise ValueError("binding_transport_installed_code_bound")
        retained[name] = raw.replace(b"\r\n", b"\n")
    helpers = {name: retained[source] for name, (source, _) in factory._HELPERS.items()}
    if any(_digest(helpers[name]) != pin for name, (_, pin) in factory._HELPERS.items()):
        raise ValueError("binding_transport_installed_helper_digest")
    return retained[factory._WORKER], helpers


def _decode(value: Any) -> bytes:
    if type(value) is not str:
        raise ValueError("binding_transport_base64")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise ValueError("binding_transport_base64") from None
    if base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("binding_transport_canonical_base64")
    return raw


def _retained_payload(raw: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Authenticate retained descriptions as inert data, never evaluate old code."""
    envelope = factory._document(raw, INPUT_LIMIT)
    if set(envelope) != {"schema_version", "documents", "worker", "helpers"} or (
        type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1
    ):
        raise ValueError("binding_transport_envelope_shape")
    docs = envelope["documents"]
    if type(docs) is not dict or set(docs) != set(_DOCUMENTS):
        raise ValueError("binding_transport_documents_shape")
    retained: dict[str, bytes] = {}
    for name, limit in _DOCUMENTS.items():
        if type(docs[name]) is not str:
            raise ValueError("binding_transport_document_string")
        retained[name] = docs[name].encode("ascii")
        factory._document(retained[name], limit)
    helpers = envelope["helpers"]
    if type(helpers) is not dict or set(helpers) != set(factory._HELPERS):
        raise ValueError("binding_transport_helper_inventory")
    worker = _decode(envelope["worker"])
    if not worker or len(worker) > factory._CODE_LIMIT:
        raise ValueError("binding_transport_retained_code_bound")
    for name, (_, pin) in factory._HELPERS.items():
        helper = _decode(helpers[name])
        if not helper or len(helper) > factory._CODE_LIMIT or _digest(helper) != pin:
            raise ValueError("binding_transport_retained_helper_digest")
    profile = EnvironmentProfile.model_validate_json(retained["profile"])
    registration = factory._Registration.model_validate_json(retained["registration"])
    selection = factory._Selection.model_validate_json(retained["selection"])
    request = BindingScanRequest.model_validate_json(retained["request"])
    if (_digest(retained["profile"]), _digest(retained["registration"]),
        _digest(retained["request"]), _digest(worker)) != (
        selection.profile_sha256, selection.registration_sha256,
        selection.request_sha256, selection.helper_sha256,
    ) or registration.environment_sha256 != selection.profile_sha256:
        raise ValueError("binding_transport_retained_selection_binding")
    factory._registered_request(profile, registration, selection, request)
    selected = selection.model_dump(mode="json")
    subject = {name: selected[name] for name in (
        "profile_sha256", "registration_sha256", "request_sha256",
        "collector_sha256", "helper_sha256",
    )}
    admission, closure = json.loads(retained["admission"]), json.loads(retained["closure"])
    if (any(admission.get(name) != value for name, value in subject.items())
        or admission.get("declared_members_sha256") != _digest(retained["manifest"])
        or admission.get("execution_attestation_sha256") != _digest(retained["closure"])
        or closure.get("subject") != subject
        or closure.get("declared_members_sha256") != _digest(retained["manifest"])):
        raise ValueError("binding_transport_retained_admission_binding")
    return envelope, retained


def _payload(raw: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    envelope, retained = _retained_payload(raw)
    worker, assets = _installed()
    if _decode(envelope["worker"]) != worker or any(
        _decode(envelope["helpers"][name]) != source for name, source in assets.items()
    ):
        raise ValueError("binding_transport_fixed_installed_code_required")
    factory.construct_worker(*(retained[name] for name in (
        "profile", "registration", "selection", "request",
    )))
    return envelope, retained


def build_payload(
    profile_raw: bytes, registration_raw: bytes, selection_raw: bytes, request_raw: bytes,
    admission_raw: bytes, manifest_raw: bytes, closure_raw: bytes,
) -> bytes:
    """Retain only fixed installed code and canonical descriptions; no I/O beyond reads."""
    documents = dict(zip(_DOCUMENTS, (
        profile_raw, registration_raw, selection_raw, request_raw,
        admission_raw, manifest_raw, closure_raw,
    ), strict=True))
    for name, raw in documents.items():
        factory._document(raw, _DOCUMENTS[name])
    worker, helpers = _installed()
    raw = factory._canonical({
        "schema_version": 1,
        "documents": {name: value.decode("ascii") for name, value in documents.items()},
        "worker": base64.b64encode(worker).decode("ascii"),
        "helpers": {
            name: base64.b64encode(source).decode("ascii") for name, source in helpers.items()
        },
    })
    _payload(raw)
    return raw


def _bootstrap(expected: str, worker_sha256: str, helper_pins: dict[str, str]) -> str:
    """Generate a short Python2.6 entry with immutable authenticated source hashes."""
    _pin(expected)
    _pin(worker_sha256)
    if helper_pins != {name: pin for name, (_, pin) in factory._HELPERS.items()}:
        raise ValueError("binding_transport_fixed_helper_pins")
    return (
        "import sys\n"
        "entry=sys.path[0] if sys.path else None\n"
        "sys.path[:]=[p for p in sys.path if p and p!=entry]\n"
        "import os\n"
        "sys.path[:]=[p for p in sys.path if os.path.isabs(p) and "
        "os.path.realpath(p)!=os.path.realpath(os.getcwd())]\n"
        "import json,hashlib,base64,types,signal\n"
        "cancelled=[False]\n"
        "def cancel(signum,frame):\n cancelled[0]=True\n"
        "for sig in (signal.SIGHUP,signal.SIGTERM,signal.SIGINT):\n"
        " signal.signal(sig,cancel)\n"
        "def require(value):\n"
        " if not value: raise ValueError('binding_transport_rejected')\n"
        "def canonical(value):\n"
        " return json.dumps(value,sort_keys=True,separators=(',',':'),"
        "ensure_ascii=True,allow_nan=False).encode('ascii')\n"
        "def sha(raw):\n return hashlib.sha256(raw).hexdigest()\n"
        "try:\n"
        " raw=sys.stdin.read(2097153).encode('ascii')\n"
        f" require(len(raw)<=2097152 and sha(raw)=={expected!r})\n"
        " data=json.loads(raw.decode('ascii'))\n"
        " require(canonical(data)==raw and set(data)=="
        "set(('schema_version','documents','worker','helpers')))\n"
        " require(type(data['schema_version']) is int and data['schema_version']==1)\n"
        f" bounds={_DOCUMENTS!r}\n"
        " docs=data['documents']\n"
        " require(type(docs) is dict and set(docs)==set(bounds))\n"
        " retained={}\n"
        " for name in bounds:\n"
        "  source=docs[name].encode('ascii')\n"
        "  require(0<len(source)<=bounds[name] and canonical(json.loads(source))==source)\n"
        "  retained[name]=source\n"
        f" pins={helper_pins!r}\n"
        " require(type(data['helpers']) is dict and set(data['helpers'])==set(pins))\n"
        " assets={}\n"
        " for name in pins:\n"
        "  source=base64.b64decode(data['helpers'][name])\n"
        "  require(0<len(source)<=131072 and sha(source)==pins[name] and "
        "base64.b64encode(source).decode('ascii')==data['helpers'][name])\n"
        "  assets[name]=source\n"
        " source=base64.b64decode(data['worker'])\n"
        f" require(0<len(source)<=131072 and sha(source)=={worker_sha256!r} and "
        "base64.b64encode(source).decode('ascii')==data['worker'])\n"
        " selection=json.loads(retained['selection'])\n"
        f" require(selection['helper_sha256']=={worker_sha256!r})\n"
        " require(not cancelled[0])\n"
        # Every source and the entire request are authenticated before evaluation.
        " module=types.ModuleType('_binding_observation_retained_remote')\n"
        " module.__dict__['__package__']=None\n"
        " eval(compile(source,'_binding_observation.py','exec'),module.__dict__)\n"
        " require(module.HELPER_PINS==pins)\n"
        " worker=module.BindingObservationWorker(retained['profile'],"
        "retained['registration'],selection,assets,pins)\n"
        " worker._cancelled=lambda:cancelled[0]\n"
        " result=worker.observe_authorized(json.loads(retained['request']),"
        "retained['admission'],retained['manifest'],retained['closure'])\n"
        " body=canonical(result)\n"
        " require(len(body)<=131072)\n"
        " sys.stdout.write(body.decode('ascii'))\n"
        "except Exception:\n sys.exit(71)\n"
    )


def _run(argv: list[str], payload: bytes, environment: dict[str, str]) -> tuple[int, bytes, bytes]:
    """Independent fixed stdin/output ceilings; kill local SSH only after its deadline."""
    process = subprocess.Popen(
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=environment, shell=False,
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    writer, reader, errors = process.stdin, process.stdout, process.stderr

    def send() -> None:
        try:
            writer.write(payload)
            writer.flush()
        finally:
            writer.close()

    deadline = time.monotonic() + TIMEOUT_SECONDS
    with ThreadPoolExecutor(max_workers=3) as pool:
        sent = pool.submit(send)
        out = pool.submit(reader.read, STREAM_LIMIT + 1)
        err = pool.submit(errors.read, STREAM_LIMIT + 1)
        try:
            pending: set[Future[Any]] = {sent, out, err}
            while pending:
                ready, pending = wait(
                    pending, timeout=max(0.01, deadline - time.monotonic()),
                    return_when=FIRST_COMPLETED,
                )
                if not ready:
                    raise TimeoutError
                for future in ready:
                    value = future.result()
                    if isinstance(value, bytes) and len(value) > STREAM_LIMIT:
                        raise ValueError("binding_transport_stream_bound_unknown_no_retry")
            status = process.wait(timeout=max(0.01, deadline - time.monotonic()))
            return status, out.result(), err.result()
        except (OSError, TimeoutError, subprocess.TimeoutExpired):
            raise ValueError("binding_transport_unavailable_or_timeout_unknown_no_retry") from None
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            reader.close()
            errors.close()


def dispatch(
    environment: EnvironmentProfile, envelope: bytes, expected_payload_sha256: str,
    worker_sha256: str, helper_pins: dict[str, str],
) -> tuple[int, bytes, bytes]:
    """Dispatch once after the caller's durable claim; never approve, claim or retry."""
    _pin(expected_payload_sha256)
    _pin(worker_sha256)
    _, docs = _payload(envelope)
    if _digest(envelope) != expected_payload_sha256 or _digest(_installed()[0]) != worker_sha256:
        raise ValueError("binding_transport_payload_or_worker_digest")
    if docs["profile"] != factory._canonical(environment.model_dump(mode="json")):
        raise ValueError("binding_transport_environment_binding")
    entry = _bootstrap(expected_payload_sha256, worker_sha256, helper_pins)
    return _run(
        _ssh(environment) + ["-c", shlex.quote(entry)], envelope,
        OpenSshBackend._ssh_environment(),
    )


def validate_terminal(stdout: bytes, envelope: bytes) -> dict[str, Any]:
    """Bind terminal process evidence; completed frames require the existing parser."""
    _, docs = _retained_payload(envelope)
    result = factory._document(stdout, STREAM_LIMIT)
    if set(result) != _TERMINAL_KEYS:
        raise ValueError("binding_transport_terminal_shape")
    selection, request = json.loads(docs["selection"]), json.loads(docs["request"])
    expected = {
        "schema_version": 1, "kind": "BINDING_OBSERVATION_TERMINAL",
        "observation_id": request["observation_id"], "request_sha256": _digest(docs["request"]),
        "collector_sha256": selection["collector_sha256"],
        "worker_sha256": selection["helper_sha256"], "admission_sha256": _digest(docs["admission"]),
        "declared_members_sha256": _digest(docs["manifest"]),
        "execution_attestation_sha256": _digest(docs["closure"]),
    }
    if any(type(result[key]) is not type(value) or result[key] != value
           for key, value in expected.items()):
        raise ValueError("binding_transport_terminal_binding")
    statuses = {"PROCESS_COMPLETED", "REJECTED", "FAILED", "TIMED_OUT", "UNKNOWN"}
    if (type(result["status"]) is not str or result["status"] not in statuses
        or type(result["execution_trust"]) is not str or result["execution_trust"] not in {
            "OPERATOR_ATTESTED_STANDARD_VM", "NOT_ESTABLISHED",
        } or result["qualification_established"] is not False
        or result["retry_permitted"] is not False):
        raise ValueError("binding_transport_terminal_scope")
    for name in ("new_simulations", "new_extractions", "new_reserved_bytes"):
        if type(result[name]) is not int or result[name] != 0:
            raise ValueError("binding_transport_terminal_activity")
    if type(result["new_eda_starts"]) is not int or result["new_eda_starts"] not in (0, 1):
        raise ValueError("binding_transport_terminal_starts")
    for name in ("start_attempted", "originals_preserved", "owned_copy_preserved",
                 "ledger_preserved", "cds_lib_preserved", "cleanup_complete"):
        if type(result[name]) is not bool:
            raise ValueError("binding_transport_terminal_boolean")
    if result["new_eda_starts"] and not result["start_attempted"]:
        raise ValueError("binding_transport_terminal_start_identity")
    if result["returncode"] is not None and type(result["returncode"]) is not int:
        raise ValueError("binding_transport_terminal_returncode")
    failure = result["failure_code"]
    if failure is not None and (type(failure) is not str or
                               re.fullmatch(r"[A-Za-z0-9_]{1,128}", failure) is None):
        raise ValueError("binding_transport_terminal_failure_token")
    before, after = result["counter_before"], result["counter_after"]
    for counter in (before, after):
        if counter is not None and (
            type(counter) is not dict or set(counter) != {"campaign_id", "count",
                                                         "result_reserved_bytes"}
            or type(counter["campaign_id"]) is not str or not counter["campaign_id"]
            or len(counter["campaign_id"]) > 64 or any(
                type(counter[name]) is not int or counter[name] < 0
                for name in ("count", "result_reserved_bytes")
            )
        ):
            raise ValueError("binding_transport_terminal_counter")
    if result["ledger_preserved"] and (before is None or before != after):
        raise ValueError("binding_transport_terminal_ledger_preservation")
    admission = json.loads(docs["admission"])
    if before is not None and before != admission.get("expected_counter"):
        raise ValueError("binding_transport_terminal_admitted_counter")
    frame, frame_sha256 = result["frame"], result["frame_sha256"]
    if result["status"] == "PROCESS_COMPLETED":
        if (result["execution_trust"] != "OPERATOR_ATTESTED_STANDARD_VM"
            or result["new_eda_starts"] != 1 or result["returncode"] != 0 or failure is not None
            or not all(result[name] for name in (
                "start_attempted", "originals_preserved", "owned_copy_preserved",
                "ledger_preserved", "cds_lib_preserved", "cleanup_complete",
            )) or type(frame) is not str):
            raise ValueError("binding_transport_terminal_completion")
        frame_raw = frame.encode("ascii")
        if frame_sha256 != _digest(frame_raw):
            raise ValueError("binding_transport_terminal_frame_digest")
        parse_frame(frame_raw, BindingScanRequest.model_validate_json(docs["request"]))
    elif frame is not None or frame_sha256 is not None:
        raise ValueError("binding_transport_failed_terminal_frame")
    return result
