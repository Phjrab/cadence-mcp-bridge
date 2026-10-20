"""Storage export, one-shot failure recovery and owned POSIX namespace evidence.

Portable machine tests are synthetic. The opt-in hosted mount case uses only a
fresh disposable image and never contacts a configured Cadence VM.
"""

import ast
import copy
import ctypes
import errno
import importlib.util
import json
import os
import stat
import struct
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

import pytest

from cadence_mcp_bridge import binding_storage_admin as exporter
from cadence_mcp_bridge.environments import EnvironmentProfile

SOURCE = Path(str(files("cadence_mcp_bridge").joinpath("_binding_storage_admin.py")))


@pytest.fixture
def resource():
    spec = importlib.util.spec_from_file_location("private_storage_admin_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def subject(inspection_request):  # noqa: F811 - imported pytest fixture
    # Reuse the inspector's same profile contract; this is synthetic evidence.
    profile = EnvironmentProfile.model_validate_json(json.dumps(inspection_request["profile"]))
    formatter = {"path": "/sbin/mke2fs", "sha256": "a" * 64}
    facts = dict(
        schema_version=1, kind="FIXED_STORAGE_PREREQUISITE_FACTS", status="OBSERVATIONS_ONLY",
        profile_canonical_sha256=exporter._sha(exporter._canonical(profile.model_dump(mode="json"))),
        resource_domain_sha256=inspection_request["resource_domain_sha256"],
        identity_manifest_sha256="b" * 64, errors=[], execution_authorized=False,
        runtime_trust_assessed=False, ready_for_apply=False, system_commands_executed=0,
        eda_starts=0, new_simulations=0, reserved_bytes=0, intentional_remote_writes=0,
        records=[dict(role="stage", status="MISSING", errno=2),
                 dict(role="backing-image", status="MISSING", errno=2),
                 dict(role="mke2fs-sbin", status="OBSERVED", sha256=formatter["sha256"],
                      metadata={"nlink": 5},
                      resolved_path_sha256=exporter._sha(formatter["path"].encode()),
                      root_owned=True, executable=True, shared_write=False)],
    )
    review = dict(
        schema_version=1, kind="STANDARD_VM_STORAGE_ADMIN_EXTERNAL_REVIEW",
        subject={key: facts[key] for key in (
            "profile_canonical_sha256", "resource_domain_sha256", "identity_manifest_sha256"
        )},
        review_reference="SYNTHETIC_NOT_ACTUAL_TRUST",
        trust_categories=[dict(category=name, evidence_sha256="c" * 64)
                          for name in sorted(exporter.CATEGORIES)],
        reviewed_formatter=formatter, unresolved_dependencies=[],
    )
    review["subject"]["storage_facts_sha256"] = exporter._sha(exporter._canonical(facts))
    return profile, facts, review


# The shared inspector fixture is imported as a pytest fixture, not executed code.
from test_binding_storage_inspection import inspection_request  # noqa: E402, F401


@pytest.mark.parametrize("change", [
    "none", "extra-review", "missing-category", "duplicate-category", "unresolved",
    "different-facts", "formatter-alias", "formatter-content", "shared-write", "old-identity",
    "existing-stage", "bool-count", "positive-authority",
])
def test_export_requires_bound_external_review_without_minting_trust(subject, change):
    profile, facts, review = copy.deepcopy(subject)
    if change == "extra-review":
        review["approval"] = True
    elif change == "missing-category":
        review["trust_categories"].pop()
    elif change == "duplicate-category":
        review["trust_categories"][0] = review["trust_categories"][1]
    elif change == "unresolved":
        review["unresolved_dependencies"] = ["unknown-loader"]
    elif change == "different-facts":
        review["subject"]["storage_facts_sha256"] = "d" * 64
    elif change == "formatter-alias":
        review["reviewed_formatter"]["path"] = "/tmp/formatter"
    elif change == "formatter-content":
        review["reviewed_formatter"]["sha256"] = "d" * 64
    elif change == "shared-write":
        facts["records"][-1]["shared_write"] = True
    elif change == "old-identity":
        review["subject"]["identity_manifest_sha256"] = "d" * 64
    elif change == "existing-stage":
        facts["records"][0]["status"] = "OBSERVED"
    elif change == "bool-count":
        facts["new_simulations"] = False
    elif change == "positive-authority":
        facts["execution_authorized"] = True
    if change == "none":
        config = exporter.prepare_configuration(profile, facts, review)
        assert config["managed_root"] == profile.paths.managed_root
        assert config["runtime_review_sha256"] == exporter._sha(exporter._canonical(review))
    else:
        with pytest.raises(ValueError):
            exporter.prepare_configuration(profile, facts, review)


def test_export_is_inert_local_new_directory_and_authenticates_exact_helper(subject, tmp_path):
    output = tmp_path / "export"
    manifest = exporter.export(*subject, output)
    source = (output / "storage-admin.py").read_bytes()
    assert manifest["helper_sha256"] == exporter._sha(source)
    assert manifest["execution_authorized"] is False and manifest["remote_contact"] is False
    parsed = ast.parse(source)
    assignment = next(node for node in parsed.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "CONFIG_JSON"
                              for target in node.targets))
    config = json.loads(ast.literal_eval(assignment.value))
    assert exporter._sha(exporter._canonical(config)) == manifest["configuration_sha256"]
    assert config["user"] == subject[0].host.user
    with pytest.raises(FileExistsError):
        exporter.export(*subject, output)


@pytest.mark.parametrize("field,value", [
    ("user", "operator\n"), ("managed_root", "/home/operator/../other/.cadence_mcp"),
    ("formatter_path", "/tmp/mke2fs"), ("resource_domain_sha256", "a" * 64),
    ("disk_floor_bytes", False), ("disk_floor_percent", 100),
])
def test_fixed_configuration_closes_path_command_and_domain_choices(
    resource, subject, field, value,
):
    config = exporter.prepare_configuration(*subject)
    config[field] = value
    with pytest.raises(ValueError):
        resource.valid_config(config)


@pytest.fixture
def machine(resource, subject, tmp_path, monkeypatch):
    config = exporter.prepare_configuration(*subject)
    paths, descriptors = {}, {}
    events = []
    fake_parent = -1
    real_os = resource.os
    root = tmp_path / "managed"
    backing = tmp_path / "backing"
    root.mkdir()
    backing.mkdir()
    descriptors[fake_parent] = root

    class Machine(resource.StorageAdmin):
        def __init__(self):
            super().__init__(config)
            self.uid, self.gid = 500, 500
            self.directories[self.root] = (fake_parent, [])
            self.protected = {"counter": "retained"}
            self.fixed_plan = {"loop": {"number": 0, "metadata": [1]}, "fixture": "fixed"}
            self.format_count = 0
            self.fail_mount = False

        def guard(self):
            events.append("guard")

        def check(self):
            pass

        def directory(self, path, owner, create=False):
            return fake_parent

        def plan(self):
            return copy.deepcopy(self.fixed_plan)

        def exclusive(self, path, value):
            target = backing / Path(path).name
            with target.open("xb") as stream:
                stream.write(resource.canonical(value))
            events.append("claim" if path == self.claim else "receipt")

        def leaf(self, path, flags=os.O_RDONLY, mode=0o600):
            if path == self.stage:
                return fake_parent
            target = backing / Path(path).name
            paths[path] = target
            fd = real_os.open(target, flags, mode)
            descriptors[fd] = target
            self.fds.append(fd)
            return fd

        def formatter(self, fd):
            assert (backing / Path(self.claim).name).is_file()
            self.format_count += 1
            events.append("format")

        def image_state(self, fd, require_clean=False):
            return {"synthetic_superblock": "retained"}

        def loop(self, number):
            return -2, None, [1]

        def mount(self, *args, **kwargs):
            events.append("mount")
            if self.fail_mount:
                raise ValueError("synthetic_mount_failed")
            return 7

    def metadata(fd):
        if fd < 0:
            return SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o700)
        actual = real_os.fstat(fd)
        return SimpleNamespace(st_size=actual.st_size, st_blocks=actual.st_size // 512,
                               st_uid=0, st_gid=0, st_mode=stat.S_IFREG | 0o600,
                               st_nlink=1, st_dev=actual.st_dev, st_ino=actual.st_ino, st_rdev=0)

    proxy = SimpleNamespace(**{name: getattr(real_os, name) for name in dir(real_os)})
    proxy.fstat = metadata
    proxy.O_DIRECTORY = getattr(real_os, "O_DIRECTORY", 0)
    proxy.fsync = lambda fd: None if fd < 0 else real_os.fsync(fd)
    monkeypatch.setattr(resource, "os", proxy)
    monkeypatch.setattr(resource, "fdname", lambda fd: str(descriptors[fd]))
    value = Machine()
    yield value, events, backing
    for fd in value.fds:
        real_os.close(fd)


@pytest.mark.parametrize("fail", [False, True])
def test_apply_spends_before_format_and_repeated_or_partial_apply_never_reformats(machine, fail):
    admin, events, backing = machine
    admin.fail_mount = fail
    plan = admin.plan()
    if fail:
        with pytest.raises(ValueError, match="synthetic_mount_failed"):
            admin.apply(plan)
    else:
        assert admin.apply(plan)["execution_authorized"] is False
    assert events.index("claim") < events.index("format") < events.index("mount")
    assert admin.format_count == 1
    image = backing / Path(admin.image).name
    old = exporter._sha(image.read_bytes())
    with pytest.raises(FileExistsError):
        admin.apply(plan)
    assert admin.format_count == 1 and old == exporter._sha(image.read_bytes())
    assert admin.protected == {"counter": "retained"}
    if fail:
        assert not (backing / Path(admin.receipt).name).exists()


def test_changed_approved_plan_has_no_privileged_side_effect(machine):
    admin, events, backing = machine
    with pytest.raises(ValueError, match="approved_plan_drift"):
        admin.apply({"loop": {"number": 1}})
    assert not list(backing.iterdir()) and admin.format_count == 0


def test_formatter_failure_spends_apply_and_preserves_partial_image(machine):
    admin, events, backing = machine

    def failed(fd):
        admin.format_count += 1
        raise ValueError("formatter_failed")

    admin.formatter = failed
    plan = admin.plan()
    with pytest.raises(ValueError, match="formatter_failed"):
        admin.apply(plan)
    image = backing / Path(admin.image).name
    before = exporter._sha(image.read_bytes())
    with pytest.raises(FileExistsError):
        admin.apply(plan)
    assert admin.format_count == 1 and exporter._sha(image.read_bytes()) == before
    assert not (backing / Path(admin.receipt).name).exists()


@pytest.mark.parametrize("fail", [False, True])
def test_remount_is_separately_spent_and_never_reformats(machine, monkeypatch, fail):
    admin, events, backing = machine
    # This synthetic transition deliberately has no real block device or syscall.
    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace())
    imagefd = admin.leaf(admin.image, os.O_RDWR | os.O_CREAT | os.O_EXCL)
    os.write(imagefd, b"preserved bytes")
    plan = dict(operation="remount", loop={"number": 0, "metadata": [1], "state": None},
                superblock=admin.image_state(imagefd), mounted=False)
    admin.recovery_plan = lambda operation: copy.deepcopy(plan)
    admin.fail_mount = fail
    if fail:
        with pytest.raises(ValueError, match="synthetic_mount_failed"):
            admin.recover(plan)
    else:
        assert admin.recover(plan)["execution_authorized"] is False
    assert admin.format_count == 0
    assert (backing / Path(admin.image).name).read_bytes() == b"preserved bytes"
    with pytest.raises(FileExistsError):
        admin.recover(plan)
    assert events.count("mount") == 1


@pytest.mark.parametrize("outcome", ["foreign-association", "busy", "still-associated", "clear"])
def test_detach_rechecks_held_loop_and_never_retries_unknown_effect(machine, monkeypatch, outcome):
    admin, events, backing = machine
    imagefd = admin.leaf(admin.image, os.O_RDWR | os.O_CREAT | os.O_EXCL)
    os.write(imagefd, b"preserved bytes")
    plan = dict(operation="detach", loop={"number": 0, "metadata": [1], "state": "ours"},
                superblock=admin.image_state(imagefd), mounted=False)
    admin.recovery_plan = lambda operation: copy.deepcopy(plan)
    admin.loop = lambda number: (-2, "ours", [1])
    admin.association = lambda state, fd: state == "ours"
    states = iter(["foreign"] if outcome == "foreign-association" else [
        "ours", "ours" if outcome == "still-associated" else None,
    ])
    admin.loop_status = lambda fd: next(states)
    admin.mounted = lambda number: False
    clean_checks = []
    admin.image_state = lambda fd, require_clean=False: (
        clean_checks.append(require_clean) or {"synthetic_superblock": "retained"})
    calls = []

    def ioctl(fd, command, arg):
        calls.append(command)
        if outcome == "busy":
            raise OSError(errno.EBUSY, "synthetic occupied loop")

    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(ioctl=ioctl))
    if outcome == "clear":
        assert admin.recover(plan)["execution_authorized"] is False
        assert clean_checks[-1] is True
    else:
        with pytest.raises((ValueError, OSError)):
            admin.recover(plan)
        assert not any(backing.glob("*.done.json"))
    assert len(calls) == (0 if outcome == "foreign-association" else 1)
    assert (backing / Path(admin.image).name).read_bytes() == b"preserved bytes"
    with pytest.raises(FileExistsError):
        admin.recover(plan)
    assert admin.format_count == 0


@pytest.mark.parametrize("state", [0, 1, 2, 3])
def test_unclean_image_is_preserved_and_requires_separate_recovery(
    resource, subject, tmp_path, monkeypatch, state,
):
    admin = resource.StorageAdmin(exporter.prepare_configuration(*subject))
    image = tmp_path / "retained.ext2"
    header = bytearray(256)
    struct.pack_into("<II", header, 0, 128, 8192)
    struct.pack_into("<HH", header, 56, 0xEF53, state)
    image.write_bytes(b"\0" * 1024 + header)
    before = exporter._sha(image.read_bytes())
    actual_os = resource.os
    fd = actual_os.open(image, os.O_RDONLY)
    info = SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o600,
                           st_uid=0, st_gid=0, st_rdev=0, st_nlink=1,
                           st_size=resource.IMAGE_BYTES, st_blocks=resource.IMAGE_BYTES // 512)
    proxy = SimpleNamespace(**{name: getattr(actual_os, name) for name in dir(actual_os)})
    proxy.fstat = lambda fd: info
    proxy.lstat = lambda path: info
    monkeypatch.setattr(resource, "os", proxy)
    admin.check = lambda: None
    admin.named = lambda path: str(image)
    try:
        retained = admin.image_state(fd)
        if state == 1:
            assert admin.image_state(fd, require_clean=True) == retained
        else:
            with pytest.raises(ValueError, match="unclean_image_requires_separate_recovery"):
                admin.image_state(fd, require_clean=True)
        assert exporter._sha(image.read_bytes()) == before
    finally:
        actual_os.close(fd)


@pytest.mark.parametrize("change", ["valid", "subtree", "readonly", "duplicate", "bound"])
def test_mount_inventory_reads_to_eof_and_rejects_unexpected_mounts(
    resource, subject, monkeypatch, change,
):
    admin = resource.StorageAdmin(exporter.prepare_configuration(*subject))
    admin.check = lambda: None
    admin.leaf = lambda path: -1
    admin.release = lambda fd: None
    admin.named = lambda path: path
    info = SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o444,
                           st_uid=0, st_gid=0, st_rdev=0)
    ordinary = b"10 1 8:1 / / rw - ext4 /dev/root rw\n"
    mount = (f"11 10 7:0 / {admin.stage} rw,nodev,nosuid,noexec - ext4 /dev/loop0 rw\n").encode()
    if change == "subtree":
        mount = mount.replace(b"7:0 / ", b"7:0 /other ")
    elif change == "readonly":
        mount = mount.replace(b" rw,nodev", b" ro,nodev")
    elif change == "duplicate":
        mount += mount
    elif change == "bound":
        mount += b"x" * 65537
    # The first read ends in a newline but is not EOF. Missing the second read
    # would silently report an absent stage and permit an incorrect transition.
    chunks = iter([ordinary, mount, b""])
    proxy = SimpleNamespace(**{name: getattr(resource.os, name) for name in dir(resource.os)})
    proxy.fstat = lambda fd: info
    proxy.lstat = lambda path: info
    proxy.read = lambda fd, bound: next(chunks)
    monkeypatch.setattr(resource, "os", proxy)

    def fstatfs(fd, buffer):
        ctypes.c_long.from_buffer(buffer).value = 0x9FA0
        return 0

    monkeypatch.setattr(ctypes, "CDLL", lambda *a, **kw: SimpleNamespace(fstatfs=fstatfs))
    if change == "valid":
        assert admin.mounted(0) is True
    else:
        with pytest.raises(ValueError, match="kernel_mount|stage_mount"):
            admin.mounted(0)


def test_import_is_inert_and_resource_has_no_delete_transport_or_module_loading():
    tree = ast.parse(SOURCE.read_bytes())
    forbidden = {"unlink", "remove", "rmdir", "system", "execvp", "execve"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and isinstance(node.func.value, ast.Name) and node.func.value.id == "os"
                   and node.func.attr in forbidden for node in ast.walk(tree))
    assert "modprobe" not in SOURCE.read_text()
    assert "fstab" not in SOURCE.read_text().split("\n", 7)[7]


@pytest.mark.skipif(sys.platform != "linux", reason="owned POSIX path and hardlink guards")
def test_owned_namespace_refuses_symlink_parent_and_hardlinked_leaf(resource, subject, tmp_path):
    admin = resource.StorageAdmin(exporter.prepare_configuration(*subject))
    import pwd
    admin.config["user"] = pwd.getpwuid(os.getuid()).pw_name
    admin.uid = os.getuid()
    admin.root = str(tmp_path)
    path = tmp_path / "leaf"
    path.write_bytes(b"retained")
    path.chmod(0o600)
    hardlink = tmp_path / "hard"
    os.link(path, hardlink)
    try:
        with pytest.raises(ValueError, match="regular_file_trust_required"):
            admin.raw(str(path), os.getuid(), 16)
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(OSError):
            admin.raw(str(alias / "leaf"), os.getuid(), 16)
    finally:
        admin.close()


@pytest.mark.skipif(
    sys.platform != "linux" or os.environ.get("CADENCE_TEST_STORAGE_ADMIN") != "1",
    reason="explicit disposable hosted administrator fixture only; no configured VM",
)
def test_actual_disposable_admin_apply_detach_remount_preserves_files_and_accounting(
    resource, subject, tmp_path,
):
    import pwd

    assert os.getuid() != 0
    profile, facts, review = subject
    config = exporter.prepare_configuration(profile, facts, review)
    root = tmp_path / ".cadence_mcp"
    root.mkdir(mode=0o700)
    for name in ("sim-mcp-v2-jobs", "reservation-identity"):
        (root / name).mkdir(mode=0o700)
    config.update(hostname=os.uname().nodename, architecture=os.uname().machine,
                  user=pwd.getpwuid(os.getuid()).pw_name, managed_root=str(root),
                  formatter_path="/usr/sbin/mke2fs", disk_floor_bytes=0, disk_floor_percent=0)
    config["resource_domain_sha256"] = resource.digest(resource.canonical(dict(
        hostname=config["hostname"].lower().rstrip("."), architecture=config["architecture"])))
    formatter = Path(config["formatter_path"])
    config["mke2fs_sha256"] = resource.digest(formatter.read_bytes())
    config["formatter_nlink"] = formatter.stat().st_nlink
    anchor = dict(root_sha256=resource.digest(str(root).encode()),
                  resource_domain_sha256=config["resource_domain_sha256"],
                  ledger_ref="sim-mcp-v2-jobs/counter.json")
    config["identity_manifest_sha256"] = resource.digest(resource.canonical(anchor))
    protected = {"run.lock": b"", "reservation-identity/manifest.json": resource.canonical(anchor),
                 "sim-mcp-v2-jobs/counter.json": b'{"count":3,"synthetic":true}'}
    for name, raw in protected.items():
        (root / name).write_bytes(raw)
        (root / name).chmod(0o600)
    source = SOURCE.read_bytes().replace(b"\r\n", b"\n").replace(
        b"CONFIG_JSON = None  # Replaced only by the local package exporter.",
        b"CONFIG_JSON = " + repr(resource.canonical(config)).encode())
    helper = tmp_path / "synthetic-admin.py"
    helper.write_bytes(source)
    helper.chmod(0o600)

    def invoke(operation, plan=None, check=True):
        args = ["sudo", "-n", sys.executable, "-E", "-s", "-B", str(helper), operation]
        raw = None
        if plan is not None:
            raw = resource.canonical(plan)
            args.append(resource.digest(raw))
        process = subprocess.run(args, input=raw, capture_output=True, timeout=90)
        if check:
            assert process.returncode == 0, process.stderr.decode(errors="replace")
            return json.loads(process.stdout)
        return process

    initial = invoke("plan")["plan"]
    apply = invoke("apply", initial)
    assert apply["execution_authorized"] is False and apply["new_reserved_bytes"] == 0
    stage = root / "binding-observations"
    assert stage.stat().st_uid == os.getuid() and stat.S_IMODE(stage.stat().st_mode) == 0o700
    fs = os.statvfs(stage)
    assert 0 < fs.f_blocks * fs.f_frsize <= resource.IMAGE_BYTES and 0 < fs.f_files <= 256
    retained = stage / "preserve.txt"
    retained.write_bytes(b"synthetic retained result")
    assert invoke("apply", initial, check=False).returncode != 0
    assert retained.read_bytes() == b"synthetic retained result"
    first = invoke("detach-plan")["plan"]
    invoke("recover", first)
    second = invoke("remount-plan")["plan"]
    invoke("recover", second)
    assert retained.read_bytes() == b"synthetic retained result"
    assert invoke("recover", second, check=False).returncode != 0
    # A later legitimate detach has a new history pin, unlike an unknown retry.
    third = invoke("detach-plan")["plan"]
    assert third["completed_history_sha256"] != first["completed_history_sha256"]
    invoke("recover", third)
    for name, raw in protected.items():
        assert (root / name).read_bytes() == raw
    image = Path(resource.BACKING) / (config["resource_domain_sha256"] + ".ext2")
    assert subprocess.run(["sudo", "-n", "test", "-f", str(image)]).returncode == 0
    stage.rmdir()  # Empty disposable mountpoint only; image and receipts remain.
    # This fixture intentionally leaves its image and root-owned receipts on the
    # disposable hosted runner. Production code never deletes them either.
