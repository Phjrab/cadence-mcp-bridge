"""Generated entry dispatch with in-memory modules only; no VM/admin execution."""

import base64
import builtins
import copy
import hashlib
import io
import json
import sys
import types
from types import SimpleNamespace

import pytest

from cadence_mcp_bridge import binding_initializer as exporter

LIMIT = 16_777_216
PROFILE = {
    "host": {"hostname": "owned-standard-vm", "architecture": "i686", "user": "operator"},
    "paths": {"managed_root": "/home/operator/work/.cadence_mcp"},
}
REGISTRATION = {"schema_version": 1, "identity_manifest_sha256": "a" * 64, "routes": []}

CORE = b'''import hashlib
import json
LIMIT = 16777216
TEXT = (str,)
def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()
'''
RECIPE = b'''def inventory(profile, registration, copying, core):
    _events.append(("inventory", profile, registration, copying.ROLE))
    return dict(kind="IN_MEMORY_INVENTORY", execution_authorized=False)
def verify_delta(plan, copying, core):
    _events.append(("postcheck", plan, copying.ROLE))
    return dict(kind="IN_MEMORY_POSTCHECK", execution_authorized=False)
class Accounting(object):
    def enter(self):
        _events.append(("accounting_enter",))
    def close(self):
        _events.append(("accounting_close",))
def build_accounting(profile, registration, storage):
    _events.append(("build_accounting", profile, registration, storage.ROLE))
    return Accounting()
def mutate(request, copying, core, rollback=False, accounting=None):
    _events.append(("receipt_and_mutation_dispatch", rollback, request["operator_authority"]))
    if _mutation_failure is not None:
        raise _mutation_failure
    return dict(kind="IN_MEMORY_ROLLBACK" if rollback else "IN_MEMORY_APPLY",
                execution_authorized=False)
'''


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class BoundedInput(io.StringIO):
    def __init__(self, value):
        super().__init__(value)
        self.requests = []

    def read(self, size=-1):
        self.requests.append(size)
        return super().read(size)


@pytest.fixture
def entry(monkeypatch):
    """Run actual ENTRY guards, replacing every executable helper with pure stubs."""
    events = []
    resources = {"core": CORE, "copying": b'ROLE = "copying"\n',
                 "storage": b'ROLE = "storage"\n', "recipe": RECIPE}
    config = {"profile": copy.deepcopy(PROFILE), "registration": copy.deepcopy(REGISTRATION)}
    source = exporter.ENTRY.replace("__CONFIG_LITERAL__", repr(base64.b64encode(
        canonical(config)).decode("ascii")))
    source = source.replace("__SOURCE_LITERAL__", repr({
        name: base64.b64encode(raw).decode("ascii") for name, raw in resources.items()}))
    source = source.replace("__PINS_LITERAL__", repr({
        name: hashlib.sha256(raw).hexdigest() for name, raw in resources.items()}))
    namespace = {"__name__": "in_memory_initializer_entry"}
    exec(compile(source, "in_memory_initializer_entry.py", "exec"), namespace)
    state = SimpleNamespace(uid=500, euid=500, operator_uid=500, failure=None)
    account_module = types.ModuleType("pwd")
    account_module.getpwnam = lambda name: SimpleNamespace(pw_uid=state.operator_uid)
    monkeypatch.setitem(sys.modules, "pwd", account_module)

    def compile_helper(raw, filename, mode):
        events.append(("compile", filename))
        return builtins.compile(raw, filename, mode)

    def module(name):
        result = types.ModuleType(name)
        result._events = events
        result._mutation_failure = state.failure
        return result

    namespace.update(
        os=SimpleNamespace(name="posix", uname=lambda: (
            "Linux", PROFILE["host"]["hostname"], "unused", "unused", "i686"),
            getuid=lambda: state.uid, geteuid=lambda: state.euid),
        signal=SimpleNamespace(SIGALRM=14,
            signal=lambda *args: events.append(("signal_handler",)),
            alarm=lambda seconds: events.append(("alarm", seconds))),
        types=SimpleNamespace(ModuleType=module), compile=compile_helper,
    )

    def run(operation, *, authority=None, raw=None, plan=None, argv_digest=None,
            request_digest=None):
        plan = copy.deepcopy(config if plan is None else plan)
        expected = digest(plan)
        request = dict(plan=plan, expected_plan_sha256=(
            expected if request_digest is None else request_digest), operator_authority=authority)
        stream = BoundedInput(canonical(request).decode("ascii") if raw is None else raw)
        args = ["initializer-admin.py", operation]
        if operation != "plan":
            args.append(expected if argv_digest is None else argv_digest)
        output = io.StringIO()
        namespace["sys"] = SimpleNamespace(argv=args, stdin=stream, stdout=output)
        state.stdin, state.stdout = stream, output
        namespace["main"]()
        return json.loads(output.getvalue())

    return SimpleNamespace(run=run, namespace=namespace, events=events, state=state,
                           config=config)


def names(entry):
    return [event[0] for event in entry.events]


@pytest.mark.parametrize("uid", [0, 500])
def test_valid_plan_dispatch_is_frozen_readonly_and_does_not_read_stdin(entry, uid):
    entry.state.uid = entry.state.euid = uid
    assert entry.run("plan") == dict(kind="IN_MEMORY_INVENTORY", execution_authorized=False)
    inventory = next(event for event in entry.events if event[0] == "inventory")
    assert inventory[1:] == (PROFILE, REGISTRATION, "copying")
    assert entry.state.stdin.requests == []
    assert "accounting_enter" not in names(entry)
    assert entry.events[-1] == ("alarm", 0)


def test_valid_postcheck_uses_ordinary_user_and_does_not_start_accounting(entry):
    assert entry.run("postcheck")["kind"] == "IN_MEMORY_POSTCHECK"
    assert entry.state.stdin.requests == [LIMIT + 1]
    assert "postcheck" in names(entry) and "build_accounting" not in names(entry)
    assert "receipt_and_mutation_dispatch" not in names(entry)


@pytest.mark.parametrize("operation", ["apply", "rollback"])
def test_valid_administrator_dispatch_closes_guard_without_claiming_real_execution(
    entry, operation,
):
    entry.state.uid = entry.state.euid = 0
    result = entry.run(operation, authority="separately authorized synthetic operation")
    assert result == dict(kind="IN_MEMORY_" + operation.upper(), execution_authorized=False)
    assert [name for name in names(entry) if name in (
        "build_accounting", "accounting_enter", "receipt_and_mutation_dispatch", "accounting_close",
    )] == ["build_accounting", "accounting_enter", "receipt_and_mutation_dispatch",
           "accounting_close"]
    mutation = next(event for event in entry.events if event[0] == "receipt_and_mutation_dispatch")
    assert mutation[1] is (operation == "rollback")


def test_guard_is_closed_when_in_memory_mutation_raises(entry):
    entry.state.uid = entry.state.euid = 0
    entry.state.failure = RuntimeError("synthetic interruption")
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        entry.run("apply", authority="synthetic authorization")
    assert entry.events[-1] == ("accounting_close",)


@pytest.mark.parametrize("name", ["core", "copying", "storage", "recipe"])
def test_source_pin_tampering_rejects_before_any_helper_compile(entry, name):
    entry.namespace["SOURCES"][name] = base64.b64encode(b"raise RuntimeError('tamper')\n")
    with pytest.raises(ValueError, match="fixed_initializer_source_pin"):
        entry.run("plan")
    assert "compile" not in names(entry)
    assert "inventory" not in names(entry)


@pytest.mark.parametrize("change", ["profile", "registration", "argv-digest", "request-digest"])
def test_exact_frozen_configuration_and_independent_digest_reject_drift(entry, change):
    plan = copy.deepcopy(entry.config)
    arguments = {}
    if change == "profile":
        plan["profile"]["host"]["hostname"] = "another-vm"
    elif change == "registration":
        plan["registration"]["identity_manifest_sha256"] = "b" * 64
    elif change == "argv-digest":
        arguments["argv_digest"] = "c" * 64
    else:
        arguments["request_digest"] = "d" * 64
    with pytest.raises(ValueError, match="initializer_configuration_and_plan_binding"):
        entry.run("postcheck", plan=plan, **arguments)
    assert "postcheck" not in names(entry) and "build_accounting" not in names(entry)


def test_stdin_reads_at_most_sixteen_mib_plus_sentinel_then_rejects(entry):
    with pytest.raises(ValueError, match="initializer_request_bound"):
        entry.run("postcheck", raw=" " * (LIMIT + 9))
    assert entry.state.stdin.requests == [LIMIT + 1]
    assert entry.state.stdin.tell() == LIMIT + 1
    assert "postcheck" not in names(entry) and "build_accounting" not in names(entry)


@pytest.mark.parametrize("operation", ["apply", "rollback"])
@pytest.mark.parametrize("authority", [None, "", 7, True, [], {}, "a" * 513])
def test_invalid_authority_rejects_before_accounting_or_receipt_dispatch(
    entry, operation, authority,
):
    entry.state.uid = entry.state.euid = 0
    with pytest.raises(ValueError, match="explicit_operator_authority_required"):
        entry.run(operation, authority=authority)
    assert not {"build_accounting", "accounting_enter", "receipt_and_mutation_dispatch"} & set(
        names(entry))


@pytest.mark.parametrize("operation", ["apply", "rollback"])
def test_registered_ordinary_user_cannot_enter_administrator_dispatch(entry, operation):
    with pytest.raises(ValueError, match="explicit_administrator_entry_required"):
        entry.run(operation, authority="synthetic authorization")
    assert "compile" not in names(entry) and "build_accounting" not in names(entry)


@pytest.mark.parametrize("uid,authority", [(0, None), (500, "synthetic authorization")])
def test_postcheck_rejects_root_and_nonempty_authority(entry, uid, authority):
    entry.state.uid = entry.state.euid = uid
    with pytest.raises(ValueError, match="ordinary_user_postcheck_only"):
        entry.run("postcheck", authority=authority)
    assert "postcheck" not in names(entry) and "build_accounting" not in names(entry)


@pytest.mark.parametrize("uid,euid,operator_uid", [(501, 501, 500), (500, 0, 500), (0, 0, 0)])
def test_unregistered_mixed_identity_and_root_operator_reject_before_helper_compile(
    entry, uid, euid, operator_uid,
):
    entry.state.uid, entry.state.euid, entry.state.operator_uid = uid, euid, operator_uid
    with pytest.raises(ValueError, match="registered_operator_or_administrator_required"):
        entry.run("plan")
    assert "compile" not in names(entry)
