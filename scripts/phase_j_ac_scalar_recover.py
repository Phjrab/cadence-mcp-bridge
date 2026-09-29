"""Recover exact candidate AC scalar bytes without another OCEAN or Spectre run."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import phase_b_role_campaign as v1
import phase_campaign as parent
import phase_e_copied_dc_v1 as dc_v1
import phase_i_ac_scalars_v2 as previous

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_J_AC_SCALAR_RECOVERY_V1.json"
DELEGATION = ROOT / ".codex/phase-j-ac-scalar-recovery-v1-delegation.json"
PRIVATE = ROOT / ".codex/ac-scalar-v2-failed"
OPERATION = "phasej-ac-scalar-local-recovery-v1"
PARENT_POLICY_SHA256 = "b9e48b62cda8d0b354a97d86c8dbe7f2cdeb4c7cfe02edc890666d4fa019922e"
PRIVATE_HASHES = {
    "scalars.txt": "c42b7b72aaa7dd8bfd15b40a569b29ee94cd43cd1315886f69bf395f392dd77d",
    "before.json": "328a81742fb811764b51b387da0638facb48b27025ded1bfbe538607fc34f466",
    "ocean.log": "5318effdf51c744f82a3e44948bd945ceeecb89d54a91f14ec2b88fc16e5b7ce",
    "attempt-status.txt": "3528516a2442265db26599ad9491046363d6200a97285c51ea6eb717de5211d0",
    "result.json": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}
PSF_FILES = {
    "ac1.ac": "802adcb41b6d70f61ece8df85de264dd093937a215ae4f77d0fec1f42930d4f4",
    "logFile": "18df4d2fe3061e31f5d57e476ebef65b2aa0cbaac6aa1ab44bb661b7f74e8071",
}
SIGNALS = ("Vop", "Vom", "Vp", "Vm")
FREQUENCIES = (1000.0, 10000.0)
STAGES = (
    "MCP_AC_STAGE|file_open",
    "MCP_AC_STAGE|results_open",
    "MCP_AC_STAGE|ac_selected",
)
POINT = re.compile(
    r"^MCP_AC_POINT[|](Vop|Vom|Vp|Vm)[|]([01])[|]"
    r"([-+0-9.eE]+)[|]([-+0-9.eE]+)[|]([-+0-9.eE]+)$"
)
VECTOR = re.compile(r"^MCP_AC_VECTOR[|](Vop|Vom|Vp|Vm)[|]([0-9]+)[|]([0-9]+)$")


class AcScalarRecoveryError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    old_policy, old_digest, state_root, base_policy = previous._authority()
    if old_digest != PARENT_POLICY_SHA256:
        raise AcScalarRecoveryError("DENY_OUT_OF_SCOPE: reviewed v2 scalar policy changed")
    deploy = parent._read_json(previous._record_path(state_root, "deploy"))
    read = parent._read_json(previous._record_path(state_root, "read"))
    if (
        deploy.get("state") != "succeeded"
        or deploy.get("policy_sha256") != old_digest
        or read.get("state") != "reserved"
        or read.get("policy_sha256") != old_digest
        or (state_root / (previous.OPERATIONS["read"] + ".output")).exists()
    ):
        raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: v2 read state changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "operation_id": OPERATION,
        "v2_scalar_files": old_policy["files"],
        "private_artifact_sha256": PRIVATE_HASHES,
        "ac_psf_file_sha256": PSF_FILES,
        "ac_psf_tree_sha256": old_policy["psf_tree_sha256"],
        "source_fingerprint_sha256": old_policy["source_fingerprint_sha256"],
        "copy_target_sha256": old_policy["copy_target_sha256"],
        "state_tree_sha256": old_policy["state_tree_sha256"],
        "model_sha256": old_policy["model_sha256"],
        "frequencies_hz": [1000, 10000],
        "spectre_attempt_count": 3,
        "new_eda_execution": False,
        "remote_write": False,
    }
    if policy != expected:
        raise AcScalarRecoveryError("DENY_OUT_OF_SCOPE: local recovery policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise AcScalarRecoveryError("DENY_OUT_OF_SCOPE: local recovery delegation absent")
    if PRIVATE.is_symlink() or not PRIVATE.is_dir():
        raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: private evidence directory absent")
    for name, expected_hash in PRIVATE_HASHES.items():
        path = PRIVATE / name
        if path.is_symlink() or not path.is_file() or _sha(path.read_bytes()) != expected_hash:
            raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: private evidence changed")
    if (PRIVATE / "result.json").stat().st_size != 0:
        raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: v2 result unexpectedly present")
    if (PRIVATE / "attempt-status.txt").read_bytes() != b"ocean_exit=0\n":
        raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: v2 OCEAN status changed")
    return policy, digest, state_root, base_policy


def _remote_preflight(base_policy: dict[str, Any]) -> None:
    dc_v1._preflight(parent._read_json(dc_v1.POLICY), base_policy)
    previous._failed_v1_remote_state()
    v1._ssh("cd " + previous.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    runtime = previous.RUNTIME
    v1._ssh(
        "set -e; test -d "
        + runtime
        + '; test "$(stat -c %s '
        + runtime
        + '/scalars.txt)" = 505'
        + '; test "$(stat -c %s '
        + runtime
        + '/result.json)" = 0'
        + "; grep -qx 'ocean_exit=0' "
        + runtime
        + "/attempt-status.txt"
    )
    names = tuple(PRIVATE_HASHES)
    actual = v1._ssh("sha256sum " + " ".join(runtime + "/" + name for name in names))
    hashes = [line.split(b" ", 1)[0].decode("ascii") for line in actual.splitlines()]
    if hashes != [PRIVATE_HASHES[name] for name in names]:
        raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: v2 remote evidence changed")
    psf = previous.REMOTE_ROOT + "/wp14-candidate-ac-v1/psf"
    listed = v1._ssh("find " + psf + " -mindepth 1 -maxdepth 1 -type f -printf '%f %s\\n'")
    if set(listed.decode("ascii").splitlines()) != {"ac1.ac 3952", "logFile 604"}:
        raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: AC PSF entries changed")
    actual = v1._ssh("sha256sum " + " ".join(psf + "/" + name for name in PSF_FILES))
    hashes = [line.split(b" ", 1)[0].decode("ascii") for line in actual.splitlines()]
    if hashes != list(PSF_FILES.values()):
        raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: AC PSF bytes changed")


def _parse_scalars(raw: bytes) -> list[dict[str, float | None]]:
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: non-ASCII AC scalars") from exc
    if len(lines) != 16 or tuple(lines[:3]) != STAGES or lines[-1] != "MCP_AC_POINT_COMPLETE|true":
        raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: AC scalar frame changed")
    values: dict[tuple[str, int], complex] = {}
    cursor = 3
    for signal in SIGNALS:
        header = VECTOR.fullmatch(lines[cursor])
        if header is None or header.group(1) != signal:
            raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: AC vector header changed")
        x_length, y_length = int(header.group(2)), int(header.group(3))
        if x_length != y_length or not 2 <= x_length <= 1024:
            raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: AC vector length changed")
        cursor += 1
        for index in (0, 1):
            match = POINT.fullmatch(lines[cursor])
            if match is None or match.group(1) != signal or int(match.group(2)) != index:
                raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: AC point order changed")
            freq, real_part, imag_part = (float(match.group(i)) for i in (3, 4, 5))
            if (
                not all(math.isfinite(v) for v in (freq, real_part, imag_part))
                or abs(freq - FREQUENCIES[index]) > FREQUENCIES[index] * 1e-6
            ):
                raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: AC point invalid")
            values[(signal, index)] = complex(real_part, imag_part)
            cursor += 1
    points: list[dict[str, float | None]] = []
    for index, freq in enumerate(FREQUENCIES):
        input_diff = values[("Vp", index)] - values[("Vm", index)]
        output_diff = values[("Vop", index)] - values[("Vom", index)]
        if abs(abs(input_diff) - 1.0) > 1e-6:
            raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: AC input magnitude changed")
        gain = output_diff / input_diff
        gain_abs = abs(gain)
        if not math.isfinite(gain_abs) or gain_abs > 1e12:
            raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: AC gain invalid")
        points.append(
            {
                "frequency_hz": freq,
                "input_diff_mag_v": abs(input_diff),
                "output_diff_mag_v": abs(output_diff),
                "gain_v_per_v": gain_abs,
                "gain_db": 20 * math.log10(gain_abs) if gain_abs > 0 else None,
                "gain_phase_deg": math.degrees(math.atan2(gain.imag, gain.real)),
            }
        )
    return points


def recover() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    _remote_preflight(base_policy)
    claim = state_root / (OPERATION + ".json")
    try:
        with claim.open("x", encoding="utf-8") as stream:
            json.dump(
                {"state": "reserved", "policy_sha256": digest, "at": datetime.now(UTC).isoformat()},
                stream,
            )
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise AcScalarRecoveryError("BLOCKED_UNCERTAIN_STATE: recovery already reserved") from exc
    points = _parse_scalars((PRIVATE / "scalars.txt").read_bytes())
    result = {
        "schema_version": 1,
        "plan_id": "WP14_CANDIDATE_AC_SCALAR_LOCAL_RECOVERY_V1",
        "status": "observed",
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "psf_tree_sha256": policy["ac_psf_tree_sha256"],
        "raw_scalar_sha256": PRIVATE_HASHES["scalars.txt"],
        "points": points,
        "simulation_run": False,
        "ocean_run": False,
        "protected_and_psf_unchanged": True,
    }
    raw = (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    output = state_root / (OPERATION + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    value = {
        "state": "succeeded",
        "operation": OPERATION,
        "policy_sha256": digest,
        "result_status": "observed",
        "raw_sha256": _sha(raw),
        "raw_local_file": str(output),
        "at": datetime.now(UTC).isoformat(),
    }
    parent._replace_record(claim, value)
    return value


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "recover":
        print("usage: phase_j_ac_scalar_recover.py recover", file=sys.stderr)
        return 2
    try:
        value = recover()
    except (
        AcScalarRecoveryError,
        previous.AcScalarsV2Error,
        dc_v1.CopiedDcV1Error,
        v1.PhaseBError,
        parent.CampaignError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
