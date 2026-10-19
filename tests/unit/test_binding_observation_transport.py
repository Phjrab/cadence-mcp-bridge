"""Disposable installed-source and subprocess boundaries; no VM or EDA contact."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shlex
import subprocess
import sys
from typing import Any

import pytest
from test_binding_observation_admission import documents as synthetic_documents
from test_binding_observation_admission import encoded as synthetic_encoded
from test_binding_observation_bootstrap import descriptions, operator, operator_base, registered

from cadence_mcp_bridge import binding_observation_transport as transport
from cadence_mcp_bridge.environments import EnvironmentProfile

__all__ = ["descriptions", "operator", "operator_base", "registered"]


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("ascii")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def forbidden(*args: Any, **kwargs: Any) -> Any:
    pytest.fail("rejected or local-only input must not contact a remote or start EDA")


@pytest.fixture
def payload(descriptions: list[bytes]) -> bytes:
    return transport.build_payload(*descriptions, *authority_documents(descriptions))


def authority_documents(descriptions: list[bytes]) -> tuple[bytes, bytes, bytes]:
    worker = transport.factory.construct_worker(*descriptions)
    admission, manifest, closure = synthetic_documents(worker)
    return synthetic_encoded(admission, manifest, closure)


def pins() -> dict[str, str]:
    return {name: pin for name, (_, pin) in transport.factory._HELPERS.items()}


def environment(payload: bytes) -> EnvironmentProfile:
    return EnvironmentProfile.model_validate_json(json.loads(payload)["documents"]["profile"])


def worker_pin(payload: bytes) -> str:
    return json.loads(json.loads(payload)["documents"]["selection"])["helper_sha256"]


def test_payload_contains_only_seven_canonical_documents_and_fixed_installed_sources(
    descriptions: list[bytes], monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    raw = transport.build_payload(*descriptions, *authority_documents(descriptions))
    assert len(raw) <= transport.INPUT_LIMIT
    value = json.loads(raw)
    assert value["schema_version"] == 1 and canonical(value) == raw
    assert set(value["documents"]) == set(transport._DOCUMENTS)
    assert [value["documents"][key].encode("ascii") for key in (
        "profile", "registration", "selection", "request",
    )] == descriptions
    source, assets = transport._installed()
    assert base64.b64decode(value["worker"]) == source
    assert {name: base64.b64decode(data) for name, data in value["helpers"].items()} == assets


@pytest.mark.parametrize("index", range(7))
@pytest.mark.parametrize("bad", [b"{}\n", b"[]", b'{"x":NaN}', b'{"x":1,"x":2}', b"\xff"])
def test_each_document_is_canonical_bounded_before_dispatch(
    descriptions: list[bytes], index: int, bad: bytes, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    documents = [*descriptions, *authority_documents(descriptions)]
    documents[index] = bad
    with pytest.raises(ValueError):
        transport.build_payload(*documents)


@pytest.mark.parametrize("tamper", ["worker", "helper", "helper_name", "extra", "request"])
def test_recomputed_envelope_hash_never_admits_caller_code_or_extra_resource(
    payload: bytes, tamper: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transport, "_ssh", forbidden)
    monkeypatch.setattr(transport, "_run", forbidden)
    value = json.loads(payload)
    if tamper == "worker":
        value["worker"] = base64.b64encode(b"raise RuntimeError('caller code')").decode("ascii")
    elif tamper == "helper":
        value["helpers"]["copy.py"] = base64.b64encode(b"raise RuntimeError").decode("ascii")
    elif tamper == "helper_name":
        value["helpers"]["extra.py"] = value["helpers"]["copy.py"]
    elif tamper == "extra":
        value["command"] = "ignored"
    else:
        request = json.loads(value["documents"]["request"])
        request["cell"] = "OtherCell"
        value["documents"]["request"] = canonical(request).decode("ascii")
    changed = canonical(value)
    with pytest.raises(ValueError):
        transport.dispatch(
            environment(payload), changed, digest(changed), worker_pin(payload), pins(),
        )


@pytest.mark.parametrize("tamper", ["payload", "worker", "helper", "profile"])
def test_external_pins_and_environment_are_checked_before_contact(
    payload: bytes, tamper: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transport, "_ssh", forbidden)
    monkeypatch.setattr(transport, "_run", forbidden)
    env, expected, worker, helpers = (
        environment(payload), digest(payload), worker_pin(payload), pins(),
    )
    if tamper == "payload":
        expected = "0" * 64
    elif tamper == "worker":
        worker = "0" * 64
    elif tamper == "helper":
        helpers["copy.py"] = "0" * 64
    else:
        env = env.model_copy(update={"ssh_alias": "another-alias"})
    with pytest.raises(ValueError):
        transport.dispatch(env, payload, expected, worker, helpers)


def test_dispatch_has_one_fixed_isolated_short_entry_and_never_retries(
    payload: bytes, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(transport, "_ssh", lambda env: [
        "ssh.exe", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", env.ssh_alias,
        "/usr/bin/python", "-E", "-s", "-B",
    ])

    def run(argv: list[str], raw: bytes, env: dict[str, str]) -> Any:
        calls.append((argv, raw, env))
        raise ValueError("synthetic lost reply")

    monkeypatch.setattr(transport, "_run", run)
    with pytest.raises(ValueError, match="lost reply"):
        transport.dispatch(
            environment(payload), payload, digest(payload), worker_pin(payload), pins(),
        )
    assert len(calls) == 1
    argv, raw, _ = calls[0]
    assert raw == payload and argv[-2] == "-c"
    assert sum(map(len, argv)) < 8192
    entry = shlex.split(argv[-1])[0]
    assert "signal.alarm" not in entry and "cancelled[0]=True" in entry
    assert "worker._cancelled=lambda:cancelled[0]" in entry
    assert entry.index("sha(source)==") < entry.index("eval(compile(")


def terminal(payload: bytes) -> dict[str, Any]:
    value = json.loads(payload)
    documents = value["documents"]
    request, selection = json.loads(documents["request"]), json.loads(documents["selection"])
    lines = [
        f"BINDING_OBSERVATION_V1|{request['observation_id']}|{request['nonce']}|"
        f"{digest(documents['request'].encode('ascii'))}",
        f"SOURCE|{request['library']}|{request['cell']}|schematic",
        *[f"VARIABLE|{var['logical_id']}|{var['cadence_binding']}" for var in request["variables"]],
    ]
    for number, variable in enumerate(request["variables"], 1):
        binding = variable["cadence_binding"]
        lines.extend([
            f"SCAN|{number}|1",
            f"BIND|{number}|{variable['logical_id']}|{binding}|V{number}|analogLib|vdc|symbol|dc|"
            f"string|{binding}|missing|-|-|-|-",
        ])
    number = len(request["variables"])
    frame = "\n".join([*lines, f"COMPLETE|{number}|{number}|{number}", ""])
    counter = json.loads(documents["admission"])["expected_counter"]
    return {
        "schema_version": 1, "kind": "BINDING_OBSERVATION_TERMINAL",
        "status": "PROCESS_COMPLETED", "observation_id": request["observation_id"],
        "request_sha256": digest(documents["request"].encode("ascii")),
        "collector_sha256": selection["collector_sha256"], "worker_sha256": worker_pin(payload),
        "admission_sha256": digest(documents["admission"].encode("ascii")),
        "declared_members_sha256": digest(documents["manifest"].encode("ascii")),
        "execution_attestation_sha256": digest(documents["closure"].encode("ascii")),
        "execution_trust": "OPERATOR_ATTESTED_STANDARD_VM", "qualification_established": False,
        "new_eda_starts": 1, "start_attempted": True, "returncode": 0,
        "frame": frame, "frame_sha256": digest(frame.encode("ascii")),
        "counter_before": counter, "counter_after": dict(counter),
        "originals_preserved": True, "owned_copy_preserved": True, "ledger_preserved": True,
        "cds_lib_preserved": True, "cleanup_complete": True, "failure_code": None,
        "retry_permitted": False, "new_simulations": 0, "new_extractions": 0,
        "new_reserved_bytes": 0,
    }


def test_terminal_binds_complete_process_frame_and_unchanged_ledger(payload: bytes) -> None:
    value = terminal(payload)
    assert transport.validate_terminal(canonical(value), payload) == value
    assert value["qualification_established"] is False


def test_retained_terminal_read_never_loads_current_or_executes_historical_code(
    payload: bytes, monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = json.loads(payload)
    historical = b"raise RuntimeError('retained code must remain inert on read')\n"
    envelope["worker"] = base64.b64encode(historical).decode("ascii")
    documents = envelope["documents"]
    selection = json.loads(documents["selection"])
    selection["helper_sha256"] = digest(historical)
    documents["selection"] = canonical(selection).decode("ascii")
    closure = json.loads(documents["closure"])
    closure["subject"]["helper_sha256"] = digest(historical)
    documents["closure"] = canonical(closure).decode("ascii")
    admission = json.loads(documents["admission"])
    admission["helper_sha256"] = digest(historical)
    admission["execution_attestation_sha256"] = digest(documents["closure"].encode("ascii"))
    documents["admission"] = canonical(admission).decode("ascii")
    retained = canonical(envelope)
    value = terminal(retained)
    monkeypatch.setattr(transport, "_installed", forbidden)
    monkeypatch.setattr(transport.factory, "construct_worker", forbidden)
    monkeypatch.setattr(transport.factory, "compile", forbidden, raising=False)
    assert transport.validate_terminal(canonical(value), retained) == value


def test_terminal_counter_must_equal_the_admitted_retained_consumption(payload: bytes) -> None:
    value = terminal(payload)
    value["counter_before"]["count"] += 1
    value["counter_after"]["count"] += 1
    with pytest.raises(ValueError, match="admitted_counter"):
        transport.validate_terminal(canonical(value), payload)


@pytest.mark.parametrize("field", [
    "observation_id", "request_sha256", "collector_sha256", "worker_sha256", "admission_sha256",
    "declared_members_sha256", "execution_attestation_sha256", "frame_sha256",
])
def test_terminal_rejects_other_request_code_or_authority(payload: bytes, field: str) -> None:
    value = terminal(payload)
    value[field] = "0" * 64
    with pytest.raises(ValueError):
        transport.validate_terminal(canonical(value), payload)


@pytest.mark.parametrize("field,bad", [
    ("schema_version", True), ("new_simulations", True), ("new_eda_starts", True),
    ("new_eda_starts", 2), ("new_eda_starts", 0), ("qualification_established", True),
    ("retry_permitted", True), ("returncode", 1), ("returncode", False),
    ("start_attempted", False), ("execution_trust", "NOT_ESTABLISHED"),
    ("originals_preserved", False), ("owned_copy_preserved", False),
    ("cleanup_complete", False), ("counter_after", None), ("frame", None),
    ("failure_code", "private/path"), ("failure_code", "failure"),
    ("status", []), ("execution_trust", {}),
])
def test_terminal_never_promotes_incomplete_or_drifted_process(
    payload: bytes, field: str, bad: Any,
) -> None:
    value = terminal(payload)
    value[field] = bad
    with pytest.raises(ValueError):
        transport.validate_terminal(canonical(value), payload)


def test_frame_identity_and_parser_remain_required_after_valid_digest(payload: bytes) -> None:
    value = terminal(payload)
    value["frame"] = value["frame"].replace("COMPLETE|", "INCOMPLETE|")
    value["frame_sha256"] = digest(value["frame"].encode("ascii"))
    with pytest.raises(ValueError, match="incomplete binding frame"):
        transport.validate_terminal(canonical(value), payload)


@pytest.mark.parametrize("status", ["REJECTED", "FAILED", "TIMED_OUT", "UNKNOWN"])
def test_failure_and_unknown_receipts_are_retained_without_frame_or_retry(
    payload: bytes, status: str,
) -> None:
    value = terminal(payload)
    value.update(
        status=status, frame=None, frame_sha256=None, returncode=None,
        originals_preserved=False, cleanup_complete=False, failure_code="controlled_failure",
    )
    assert transport.validate_terminal(canonical(value), payload)["status"] == status
    value["frame"] = "retained frame cannot turn failure into success"
    with pytest.raises(ValueError, match="failed_terminal_frame"):
        transport.validate_terminal(canonical(value), payload)


@pytest.mark.skipif(os.name != "posix", reason="guest signal/startup is POSIX")
@pytest.mark.parametrize("tamper", [None, "payload", "worker", "helper"])
def test_real_bootstrap_authenticates_every_byte_before_source_evaluation(
    payload: bytes, tmp_path: Any, tamper: str | None,
) -> None:
    marker = tmp_path / "compiled-marker"
    shadow = tmp_path / "shadowed-import-marker"
    (tmp_path / "json.py").write_text(f"open({str(shadow)!r},'w').write('untrusted')")
    fake = (
        f"HELPER_PINS={pins()!r}\n"
        f"open({str(marker)!r},'w').write('evaluated')\n"
        "class BindingObservationWorker(object):\n"
        " def __init__(self,profile,registration,selection,assets,pins):\n"
        "  self.profile=profile\n"
        " def observe_authorized(self,request,admission,manifest,closure):\n"
        "  return {'request':request,'admission':admission.decode('ascii'),"
        "'manifest':manifest.decode('ascii'),'closure':closure.decode('ascii'),"
        "'cancelled':self._cancelled()}\n"
    ).encode("ascii")
    value = json.loads(payload)
    value["worker"] = base64.b64encode(fake).decode("ascii")
    selected = json.loads(value["documents"]["selection"])
    selected["helper_sha256"] = digest(fake)
    value["documents"]["selection"] = canonical(selected).decode("ascii")
    original = canonical(value)
    if tamper == "worker":
        value["worker"] = base64.b64encode(fake.replace(b"evaluated", b"corrupted")).decode("ascii")
    elif tamper == "helper":
        helper = base64.b64decode(value["helpers"]["copy.py"])
        value["helpers"]["copy.py"] = base64.b64encode(helper + b"\n").decode("ascii")
    raw = canonical(value) + (b"\n" if tamper == "payload" else b"")
    # Pin changed envelopes deliberately except the explicit outer tamper: each
    # individual source hash must independently reject before any compile.
    expected = digest(original if tamper == "payload" else raw)
    entry = transport._bootstrap(expected, digest(fake), pins())
    result = subprocess.run(
        [sys.executable, "-E", "-s", "-B", "-c", entry], input=raw,
        capture_output=True, check=False, timeout=10, cwd=tmp_path,
    )
    assert not shadow.exists()
    if tamper is None:
        assert result.returncode == 0 and result.stderr == b""
        receipt = json.loads(result.stdout)
        assert receipt["request"] == json.loads(value["documents"]["request"])
        assert receipt["admission"] == value["documents"]["admission"]
        assert receipt["manifest"] == value["documents"]["manifest"]
        assert receipt["closure"] == value["documents"]["closure"]
        assert receipt["cancelled"] is False and marker.read_text() == "evaluated"
    else:
        assert result.returncode == 71 and result.stdout == result.stderr == b""
        assert not marker.exists()


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_bounded_local_transport_rejects_overflow_without_retry(stream: str) -> None:
    code = f"import sys;sys.{stream}.write('x'*131073);sys.{stream}.flush()"
    with pytest.raises(ValueError, match="stream_bound_unknown_no_retry"):
        transport._run([sys.executable, "-I", "-c", code], b"{}", dict(os.environ))


def test_bounded_transport_preserves_nonzero_and_separate_streams() -> None:
    result = transport._run(
        [sys.executable, "-I", "-c",
         "import sys;print('a');print('b',file=sys.stderr);sys.exit(3)"],
        b"{}", dict(os.environ),
    )
    assert result == (3, b"a\n" if os.name == "posix" else b"a\r\n",
                      b"b\n" if os.name == "posix" else b"b\r\n")


def test_bounded_transport_timeout_remains_unknown_and_starts_only_once(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "started"
    code = f"import time;open({str(marker)!r},'x').write('one');time.sleep(3)"
    monkeypatch.setattr(transport, "TIMEOUT_SECONDS", 0.2)
    with pytest.raises(ValueError, match="timeout_unknown_no_retry"):
        transport._run([sys.executable, "-I", "-c", code], b"{}", dict(os.environ))
    assert marker.read_text() == "one"
