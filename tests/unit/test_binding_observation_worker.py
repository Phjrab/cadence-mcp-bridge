"""Disposable helper pieces; no actual VM, Cadence, authority or source deployment."""

import copy
import errno
import os
import platform
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_shared_reservations import root

from cadence_mcp_bridge import _binding_observation as observer
from cadence_mcp_bridge import _native_copy as copying

__all__ = ["root"]


def assets():
    base = Path(observer.__file__).parent
    return {
        name: (base / source).read_bytes().replace(b"\r\n", b"\n")
        for name, source in (
            ("copy.py", "_native_copy.py"),
            ("reservations.py", "_shared_reservations.py"),
            ("process.py", "_native_eda_worker.py"),
        )
    }


@pytest.fixture
def selected(tmp_path, root):
    source = tmp_path / "source" / "Cell"
    state = tmp_path / "state"
    source.mkdir(mode=0o700, parents=True)
    state.mkdir(mode=0o700)
    (source / "sch.oa").write_bytes(b"synthetic OA placeholder")
    (state / "ADE_state.info").write_bytes(b"synthetic state placeholder")
    scan = dict(
        schema_version=1, observation_id=str(uuid4()), nonce="a" * 64,
        library="Synthetic", cell="Cell", view="schematic",
        variables=[dict(logical_id="input-plus", cadence_binding="qa_vp")],
    )
    profile = dict(
        paths=dict(managed_root=str(root), protected_roots=[str(tmp_path)]),
        host=dict(hostname=platform.node(), architecture=platform.machine(),
                  os=platform.system(), python_version=platform.python_version(),
                  user="synthetic"),
        limits=dict(disk_floor_bytes=0, disk_floor_percent=0),
        tools=dict(ocean=dict(path=str(tmp_path / "ocean"), sha256="f" * 64)),
    )
    if os.name == "posix":
        import pwd

        profile["host"]["user"] = pwd.getpwuid(os.getuid()).pw_name
    profile_raw = observer.canonical(profile)
    route = dict(
        design_id="synthetic", analysis_id="synthetic-dc",
        profile=dict(binding=dict(library="Synthetic", cell="Cell", view="schematic")),
        source_cell=str(source), source_state=str(state), variables=scan["variables"],
        libraries=[dict(name="Synthetic", path=str(source.parent),
                        tree_sha256=copying.dependency_snapshot(str(source.parent))["tree_sha256"])],
        ade=dict(source_tree_sha256=copying.snapshot(str(source))["tree_sha256"],
                 ade_state_tree_sha256=copying.snapshot(str(state))["tree_sha256"]),
    )
    registration_raw = observer.canonical(dict(
        environment_sha256=observer.digest(profile_raw), routes=[route],
    ))
    selection = dict(
        schema_version=1, design_id="synthetic", analysis_id="synthetic-dc",
        profile_sha256=observer.digest(profile_raw),
        registration_sha256=observer.digest(registration_raw),
        request_sha256=observer.digest(observer.canonical(scan)),
        collector_sha256=observer.digest(observer.render_collector(scan)),
        helper_sha256=observer.digest(Path(observer.__file__).read_bytes().replace(b"\r\n", b"\n")),
    )
    worker = observer.BindingObservationWorker(
        profile_raw, registration_raw, selection, assets(), observer.HELPER_PINS,
    )
    return worker, scan, (profile_raw, registration_raw, selection)


@pytest.fixture
def controlled_inventory(selected, monkeypatch):
    # Only the external conflicting-work inventory is synthetic. The dedicated
    # child's /proc identity, group ownership and termination remain real.
    worker, _, _ = selected
    monkeypatch.setattr(worker, "_check_conflicting_processes", lambda: None)


def test_observe_is_unconditionally_blocked_and_never_writes_or_starts(selected, monkeypatch):
    worker, scan, _ = selected
    monkeypatch.setattr(observer.subprocess, "Popen", lambda *a, **k: pytest.fail("EDA start"))
    before = {p: p.read_bytes() for p in Path(worker.root).rglob("*") if p.is_file()}
    outcome = worker.observe(scan)
    assert outcome["status"] == "CAPABILITY_NOT_QUALIFIED"
    assert outcome["qualified"] is False and outcome["closure_trust"] == "NOT_ESTABLISHED"
    assert outcome["new_eda_starts"] == outcome["new_simulations"] == 0
    assert outcome["new_extractions"] == outcome["new_reservations"] == 0
    assert not (Path(worker.root) / "binding-observations").exists()
    assert before == {p: p.read_bytes() for p in Path(worker.root).rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="request_shape"):
        worker.observe({**scan, "closure_trust": "TRUSTED"})


@pytest.mark.parametrize("change", ["expression", "command", "view", "alias", "nonce", "bool"])
def test_fixed_renderer_rejects_untrusted_fields_and_expressions(selected, change):
    _, request, _ = selected
    scan = copy.deepcopy(request)
    if change == "expression":
        scan["variables"][0]["cadence_binding"] = "qa_vp+1"
    elif change == "command":
        scan["command"] = "anything"
    elif change == "view":
        scan["view"] = "layout"
    elif change == "alias":
        scan["variables"].append({"logical_id": "other", "cadence_binding": "qa_vp"})
    elif change == "nonce":
        scan["nonce"] = "a" * 32
    else:
        scan["schema_version"] = True
    with pytest.raises(ValueError):
        observer.render_collector(scan)


def test_rendering_is_fixed_and_bound_to_source_nonce_and_request(selected):
    _, scan, _ = selected
    raw = observer.render_collector(scan)
    assert b"@" not in raw and raw.isascii() and len(raw) < observer.FRAME_BYTES
    assert observer.digest(observer.canonical(scan)).encode() in raw
    assert scan["nonce"].encode() in raw and scan["observation_id"].encode() in raw
    assert b'dbOpenCellViewByType("Synthetic" "Cell" "schematic" "" "r")' in raw
    assert b'list(list("input-plus" "qa_vp"))' in raw
    assert b'outfile("binding-frame.txt")' in raw
    assert b"dbSave" not in raw and b"evalstring" not in raw and b"dbCreate" not in raw


@pytest.mark.parametrize("change", ["extra", "digest", "replacement-pins"])
def test_only_compiled_fixed_helpers_can_be_memory_loaded(selected, change, tmp_path):
    _, _, arguments = selected
    bundle, pins = assets(), dict(observer.HELPER_PINS)
    marker = tmp_path / "untrusted-module-executed"
    if change == "extra":
        bundle["anything.py"] = b"raise RuntimeError('must not execute')"
    else:
        bundle["copy.py"] = f"open({str(marker)!r}, 'w').write('bad')".encode()
        if change == "replacement-pins":
            pins["copy.py"] = observer.digest(bundle["copy.py"])
    with pytest.raises(ValueError, match="fixed_helper"):
        observer.BindingObservationWorker(*arguments, bundle, pins)
    assert not marker.exists()


def test_lower_copy_limits_are_private_and_combined_across_source_and_state(selected):
    worker, _, _ = selected
    assert copying.MAX_ENTRIES == 4096 and copying.MAX_BYTES == 67108864
    assert worker.copying.MAX_ENTRIES == 64 and worker.copying.MAX_BYTES == 1048576
    before = worker._snapshots()
    state = Path(worker.route["source_state"])
    for index in range(62):
        (state / str(index)).write_bytes(b"")
    with pytest.raises(ValueError, match="tree_bound|tree_or_link_bound"):
        worker._snapshots()
    assert copying.MAX_ENTRIES == 4096 and worker.copying.MAX_ENTRIES == 64
    assert before["source"]["bytes"] == len(b"synthetic OA placeholder")


def test_combined_byte_bound_and_original_content_metadata_drift_reject(selected):
    worker, _, _ = selected
    state = Path(worker.route["source_state"]) / "ADE_state.info"
    state.write_bytes(b"x" * observer.SNAPSHOT_BYTES)
    with pytest.raises(ValueError, match="drift_or_size"):
        worker._snapshots()
    state.write_bytes(b"changed")
    with pytest.raises(ValueError, match="original_registration_drift"):
        worker._snapshots()


def test_scan_must_match_registered_route_and_reviewed_digest(selected):
    worker, request, _ = selected
    scan = copy.deepcopy(request)
    scan["variables"][0]["cadence_binding"] = "Unregistered"
    with pytest.raises(ValueError, match="registered_request_binding"):
        worker.observe(scan)


def test_whole_registered_library_drift_is_separate_from_selected_cell(selected):
    worker, _, _ = selected
    before = worker._snapshots()
    library = Path(worker.route["libraries"][0]["path"])
    (library / "libInit.il").write_bytes(b"synthetic init placeholder")
    assert worker.copying.snapshot(worker.route["source_cell"]) == before["source"]
    with pytest.raises(ValueError, match="registered_dependency_drift"):
        worker._snapshots()
    assert worker.copying.MAX_ENTRIES == observer.SNAPSHOT_ENTRIES
    assert worker.copying.MAX_BYTES == observer.SNAPSHOT_BYTES


def test_dependency_budget_is_aggregate_and_always_restored(selected, tmp_path, monkeypatch):
    worker, _, _ = selected
    extra = tmp_path / "dependency"
    extra.mkdir()
    (extra / "code").write_bytes(b"synthetic dependency")
    snapshot = copying.dependency_snapshot(str(extra))
    worker.route["libraries"].append(dict(
        name="Other", path=str(extra), tree_sha256=snapshot["tree_sha256"],
    ))
    total = sum(s[2]["bytes"] for s in worker._dependencies())
    monkeypatch.setattr(observer, "DEPENDENCY_BYTES", total - 1)
    with pytest.raises(ValueError, match="drift_or_size|combined_dependency_bound"):
        worker._dependencies()
    assert (worker.copying.MAX_ENTRIES, worker.copying.MAX_BYTES) == (
        observer.SNAPSHOT_ENTRIES, observer.SNAPSHOT_BYTES,
    )


def test_dependency_scan_rechecks_earlier_library_after_later_read(selected, tmp_path, monkeypatch):
    worker, _, _ = selected
    extra = tmp_path / "dependency"
    extra.mkdir()
    tree_sha256 = copying.dependency_snapshot(str(extra))["tree_sha256"]
    worker.route["libraries"].append(dict(
        name="Other", path=str(extra), tree_sha256=tree_sha256,
    ))
    real_snapshot = worker.copying.dependency_snapshot

    def drifting(path):
        observed = real_snapshot(path)
        if path == str(extra):
            library = Path(worker.route["libraries"][0]["path"])
            (library / "late-init.il").write_bytes(b"synthetic late drift")
        return observed

    monkeypatch.setattr(worker.copying, "dependency_snapshot", drifting)
    with pytest.raises(ValueError, match="registered_dependency_drift"):
        worker._dependencies()


@pytest.mark.parametrize("change", ["new-leaf", "same-size-restored-mtime", "mode"])
def test_second_pass_late_dependency_drift_is_checked_over_whole_union(
    selected, tmp_path, monkeypatch, change,
):
    worker, _, _ = selected
    extra = tmp_path / "later-dependency"
    extra.mkdir()
    worker.route["libraries"].append(dict(
        name="Later", path=str(extra),
        tree_sha256=copying.dependency_snapshot(str(extra))["tree_sha256"],
    ))
    leaf = Path(worker.route["source_cell"]) / "sch.oa"
    original = leaf.stat()
    if change == "same-size-restored-mtime" and os.name != "posix":
        pytest.skip("POSIX change time, not Windows creation time")
    real_snapshot = worker.copying.dependency_snapshot
    later_reads = 0

    def late_drift(path):
        nonlocal later_reads
        snapshot = real_snapshot(path)
        if path == str(extra):
            later_reads += 1
            if later_reads == 2:
                if change == "new-leaf":
                    (leaf.parent.parent / "late-init.il").write_bytes(b"synthetic")
                elif change == "mode":
                    leaf.chmod(0o400)
                else:
                    leaf.write_bytes(b"x" * original.st_size)
                    os.utime(leaf, ns=(original.st_atime_ns, original.st_mtime_ns))
        return snapshot

    monkeypatch.setattr(worker.copying, "dependency_snapshot", late_drift)
    with pytest.raises(ValueError, match="dependency_scan_drift"):
        worker._dependencies()
    assert later_reads == 2
    assert worker.copying.MAX_ENTRIES == observer.SNAPSHOT_ENTRIES


@pytest.mark.parametrize("change", ["alias", "link", "missing", "count", "entries"])
def test_dependency_namespace_and_entry_bounds_reject(selected, tmp_path, monkeypatch, change):
    worker, _, _ = selected
    library = worker.route["libraries"][0]
    if change == "alias":
        worker.route["libraries"].append(dict(library))
    elif change == "link":
        if os.name == "nt":
            pytest.skip("symlink creation privilege is not required for Windows fixtures")
        (Path(library["path"]) / "linked").symlink_to(tmp_path / "state", target_is_directory=True)
    elif change == "missing":
        library["path"] = str(tmp_path / "nonexistent")
    elif change == "count":
        worker.route["libraries"] *= observer.DEPENDENCY_LIBRARIES + 1
    else:
        monkeypatch.setattr(observer, "DEPENDENCY_ENTRIES", 1)
    with pytest.raises((ValueError, OSError)):
        worker._dependencies()
    assert worker.copying.MAX_ENTRIES == observer.SNAPSHOT_ENTRIES


def test_library_map_is_reconstructed_from_registration_and_owned_stage(selected):
    worker, scan, _ = selected
    stage = "/synthetic-owned-stage/" + scan["observation_id"]
    expected = ("DEFINE Synthetic " + stage + "/library\n").encode("ascii")
    assert worker._cds_lib(scan, stage) == expected
    assert b"INCLUDE" not in expected and worker.route["source_cell"].encode() not in expected


@pytest.mark.skipif(os.name != "posix", reason="actual private owned stage and prelaunch guards")
@pytest.mark.parametrize("replacement", [
    b"DEFINE Synthetic /unregistered/other-library\n",
    b"INCLUDE /unregistered/cds.lib\n",
])
def test_staged_mapping_tamper_rejects_before_any_ocean_start(
    selected, controlled_inventory, monkeypatch, replacement,
):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")

    def forbidden(*args, **kwargs):
        pytest.fail("tampered library mapping must reject before OCEAN")

    monkeypatch.setattr(observer.subprocess, "Popen", forbidden)
    monkeypatch.setattr(worker, "_ocean_trust", forbidden)
    before = worker._ledger()
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, _, _ = worker._stage(scan, session)
        (Path(stage) / "cds.lib").write_bytes(replacement)
        with pytest.raises(ValueError, match="registered_library_mapping_drift"):
            worker._program(stage, session, scan)
        assert not (Path(stage) / "ocean-start-claimed.json").exists()
        assert (Path(stage) / "cds.lib").read_bytes() == replacement
    assert worker._ledger() == before


@pytest.mark.skipif(os.name != "posix", reason="actual ordinary-user resource flock and process")
@pytest.mark.parametrize("case", ["success", "nonzero", "timeout", "stdout", "stderr"])
def test_private_program_piece_bounds_own_synthetic_process_and_preserves_ledger(
    selected, controlled_inventory, monkeypatch, case,
):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("worker intentionally rejects root; hosted ordinary-user POSIX test required")
    executable = Path(worker.profile["tools"]["ocean"]["path"])
    body = {
        "success": "open('binding-frame.txt','wb').write(b'synthetic complete frame\\n')",
        "nonzero": "raise SystemExit(3)",
        "timeout": "import time;time.sleep(30)",
        "stdout": "import os;os.write(1,b'x'*65537)",
        "stderr": "import os;os.write(2,b'x'*65537)",
    }[case]
    executable.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
    executable.chmod(0o700)
    worker.profile["tools"]["ocean"]["sha256"] = observer.digest(executable.read_bytes())
    launches = []
    real_popen = observer.subprocess.Popen

    def launch(argv, **options):
        launches.append((argv, options["env"]))
        return real_popen(argv, **options)

    monkeypatch.setattr(observer.subprocess, "Popen", launch)
    ledger = (Path(worker.root) / worker.accounting.LEDGER).read_bytes()
    original = worker._snapshots()
    monkeypatch.setattr(observer, "PROCESS_SECONDS", 0.2 if case == "timeout" else 5)
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, snapshots, copied = worker._stage(scan, session)
        assert snapshots == original and copied["source_preserved"]
        if case == "success":
            result = worker._program(stage, session, scan)
            assert result["frame"] == b"synthetic complete frame\n"
            assert result["qualified"] is False and result["closure_trust"] == "NOT_ESTABLISHED"
        else:
            reason = "program_failed" if case == "nonzero" else (
                "process_timeout" if case == "timeout" else "program_output_bound"
            )
            with pytest.raises(ValueError, match=reason):
                worker._program(stage, session, scan)
        with pytest.raises(ValueError, match="process_attempt_spent"):
            worker._program(stage, session, scan)
        session.check()
        with pytest.raises(ValueError, match="attempt_already_exists"):
            worker._stage(scan, session)
    assert len(launches) == 1
    assert launches[0][0] == [
        str(executable), "-nograph", "-nocdsinit", "-log", stage + "/ocean.log",
        "-cdslib", stage + "/cds.lib", "-restore", stage + "/observer.ocn",
    ]
    assert launches[0][1]["HOME"] == stage + "/home"
    assert launches[0][1]["TMPDIR"] == stage + "/tmp"
    assert (Path(worker.root) / worker.accounting.LEDGER).read_bytes() == ledger
    assert worker._snapshots() == original
    assert all((Path(stage) / ("ocean." + stream)).stat().st_size <= observer.FRAME_BYTES
               for stream in ("stdout", "stderr"))


@pytest.mark.skipif(os.name != "posix", reason="owned POSIX runtime directories")
@pytest.mark.parametrize("case", ["clean", "content", "mode", "license"])
def test_private_environment_excludes_inherited_loader_and_init_inputs(
    selected, controlled_inventory, monkeypatch, case,
):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    for name in ("LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONPATH", "CDS_SITE", "CDS_LOAD_ENV",
                 "CDS_LIB_PATH", "DISPLAY", "HOME", "PATH"):
        monkeypatch.setenv(name, "synthetic-untrusted-setting")
    monkeypatch.setenv("CDS_LIC_FILE", "synthetic-private-route")
    monkeypatch.delenv("LM_LICENSE_FILE", raising=False)
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, _, _ = worker._stage(scan, session)
        if case == "content":
            (Path(stage) / "home" / ".cdsinit").write_bytes(b"synthetic")
        elif case == "mode":
            (Path(stage) / "tmp").chmod(0o750)
        elif case == "license":
            monkeypatch.setenv("CDS_LIC_FILE", "x" * 4097)
        if case == "clean":
            environment = worker._environment(stage)
            assert environment == dict(
                HOME=stage + "/home", TMPDIR=stage + "/tmp", TMP=stage + "/tmp",
                TEMP=stage + "/tmp", PATH="/usr/bin:/bin", LANG="C", LC_ALL="C",
                CDS_LIC_FILE="synthetic-private-route",
            )
        else:
            with pytest.raises(ValueError, match="runtime_directory|license_environment_bound"):
                worker._environment(stage)


@pytest.mark.skipif(os.name != "posix", reason="actual dependency prelaunch guards")
def test_dependency_drift_prevents_private_program_start(
    selected, controlled_inventory, monkeypatch,
):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    monkeypatch.setattr(observer.subprocess, "Popen", lambda *a, **k: pytest.fail("EDA start"))
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, _, _ = worker._stage(scan, session)
        library = Path(worker.route["libraries"][0]["path"])
        (library / "libInit.il").write_bytes(b"synthetic changed init")
        with pytest.raises(ValueError, match="registered_dependency_drift"):
            worker._program(stage, session, scan)
        assert not (Path(stage) / "ocean-start-claimed.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="actual synthetic child postfailure guards")
@pytest.mark.parametrize("exit_code", [0, 3])
def test_private_child_dependency_drift_is_retained_even_on_failure(
    selected, controlled_inventory, monkeypatch, exit_code,
):
    import json

    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    changed = Path(worker.route["libraries"][0]["path"]) / "libInit.il"
    executable = Path(worker.profile["tools"]["ocean"]["path"])
    executable.write_text(
        f"#!{sys.executable}\nopen({str(changed)!r},'wb').write(b'synthetic drift')\n"
        f"raise SystemExit({exit_code})\n", encoding="utf-8",
    )
    executable.chmod(0o700)
    worker.profile["tools"]["ocean"]["sha256"] = observer.digest(executable.read_bytes())
    monkeypatch.setattr(observer, "PROCESS_SECONDS", 5)
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, _, _ = worker._stage(scan, session)
        ledger = worker._ledger()
        with pytest.raises(ValueError, match="post_process_protection_failed"):
            worker._program(stage, session, scan)
        guard = json.loads((Path(stage) / "protection-check.json").read_bytes())
        assert guard["originals_preserved"] is False
        assert guard["owned_copy_preserved"] is guard["ledger_preserved"] is True
        assert changed.read_bytes() == b"synthetic drift"
        assert worker._ledger() == ledger
        assert (Path(stage) / "ocean-start-claimed.json").is_file()
        assert (Path(stage) / "ocean.stderr").is_file()
        with pytest.raises(ValueError, match="process_attempt_spent"):
            worker._program(stage, session, scan)


@pytest.mark.skipif(os.name != "posix", reason="actual permissions and ordinary-user preflight")
def test_preflight_rejects_active_work_and_disk_floor_without_start(
    selected, controlled_inventory, monkeypatch,
):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    before = worker._ledger()
    with worker.accounting.ReservationSession(worker.root) as session:
        marker = Path(worker.root) / worker.accounting.JOBS / "active"
        marker.write_bytes(b"retained active evidence")
        with pytest.raises(ValueError, match="active_work"):
            worker._stage(scan, session)
        assert not (Path(worker.root) / "binding-observations").exists()
        # Synthetic fixture action only; actual observer never removes markers.
        marker.unlink()
        worker.profile["limits"]["disk_floor_bytes"] = 10**30
        with pytest.raises(ValueError, match="disk_floor"):
            worker._stage(scan, session)
    assert worker._ledger() == before


@pytest.mark.parametrize("case", ["eda", "benign", "other-uid", "denied", "vanished", "gone"])
def test_conflicting_process_inventory_is_fail_closed(selected, monkeypatch, case):
    worker, _, _ = selected
    uid = 12345
    with monkeypatch.context() as patch:
        patch.setattr(observer.os, "getuid", lambda: uid, raising=False)
        patch.setattr(observer.os, "getpid", lambda: 98764)
        patch.setattr(observer.os, "listdir", lambda path: ["self", "98764", "98765"])
        patch.setattr(observer.os, "stat", lambda path: SimpleNamespace(
            st_uid=uid + (case == "other-uid")))

        def target(path):
            assert path == "/proc/98765/exe"
            if case in ("denied", "vanished", "gone"):
                code = {"denied": errno.EACCES, "vanished": errno.ENOENT,
                        "gone": errno.ESRCH}[case]
                raise OSError(code, "synthetic process visibility")
            assert case != "other-uid"
            return "/synthetic/Spectre" if case == "eda" else "/synthetic/python"

        patch.setattr(observer.os, "readlink", target)
        if case == "eda":
            with pytest.raises(ValueError, match="active_eda_process"):
                worker._check_conflicting_processes()
        elif case == "denied":
            with pytest.raises(PermissionError) as raised:
                worker._check_conflicting_processes()
            assert raised.value.errno == errno.EACCES
        else:
            worker._check_conflicting_processes()


@pytest.mark.skipif(os.name != "posix", reason="ordinary-user POSIX prelaunch failure")
def test_unknown_same_uid_process_prevents_stage_and_start(selected, monkeypatch):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    before = worker._ledger()

    def denied():
        raise OSError(errno.EACCES, "synthetic protected same-UID process")

    monkeypatch.setattr(worker, "_check_conflicting_processes", denied)
    monkeypatch.setattr(observer.subprocess, "Popen", lambda *a, **k: pytest.fail("EDA start"))
    with (
        worker.accounting.ReservationSession(worker.root) as session,
        pytest.raises(PermissionError),
    ):
        worker._stage(scan, session)
    assert not (Path(worker.root) / "binding-observations").exists()
    assert worker._ledger() == before
