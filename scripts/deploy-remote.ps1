[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$sshAlias = "cadence-vm"
$remoteRoot = "/home/buet/cds_work/.cadence_mcp"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sshOptions = @(
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=10"
)
$scpOptions = $sshOptions

$files = @(
    @{ Local = "remote/bin/cadence-runner"; Remote = "$remoteRoot/bin/cadence-runner"; Mode = "700" },
    @{ Local = "remote/lib/runner-common.sh"; Remote = "$remoteRoot/lib/runner-common.sh"; Mode = "700" },
    @{ Local = "remote/lib/run-smoke-job.sh"; Remote = "$remoteRoot/lib/run-smoke-job.sh"; Mode = "700" },
    @{ Local = "remote/lib/run-profile-job.sh"; Remote = "$remoteRoot/lib/run-profile-job.sh"; Mode = "700" },
    @{ Local = "remote/lib/run-design-write-validation.sh"; Remote = "$remoteRoot/lib/run-design-write-validation.sh"; Mode = "700" },
    @{ Local = "remote/lib/run-design-write-v2-recovery.sh"; Remote = "$remoteRoot/lib/run-design-write-v2-recovery.sh"; Mode = "700" },
    @{ Local = "remote/lib/run-design-write-v3-validation.sh"; Remote = "$remoteRoot/lib/run-design-write-v3-validation.sh"; Mode = "700" },
    @{ Local = "remote/lib/run-design-write-v3-forensic.sh"; Remote = "$remoteRoot/lib/run-design-write-v3-forensic.sh"; Mode = "700" },
    @{ Local = "remote/lib/run-design-write-v3-deep-forensic.sh"; Remote = "$remoteRoot/lib/run-design-write-v3-deep-forensic.sh"; Mode = "700" },
    @{ Local = "remote/lib/run-design-write-v3-exact-rollback.sh"; Remote = "$remoteRoot/lib/run-design-write-v3-exact-rollback.sh"; Mode = "700" },
    @{ Local = "remote/py26/result_json.py"; Remote = "$remoteRoot/py26/result_json.py"; Mode = "700" },
    @{ Local = "remote/py26/discovery_json.py"; Remote = "$remoteRoot/py26/discovery_json.py"; Mode = "700" },
    @{ Local = "remote/py26/profile_json.py"; Remote = "$remoteRoot/py26/profile_json.py"; Mode = "700" },
    @{ Local = "remote/py26/write_validation_json.py"; Remote = "$remoteRoot/py26/write_validation_json.py"; Mode = "700" },
    @{ Local = "remote/py26/v2_recovery_json.py"; Remote = "$remoteRoot/py26/v2_recovery_json.py"; Mode = "700" },
    @{ Local = "remote/py26/v3_validation_json.py"; Remote = "$remoteRoot/py26/v3_validation_json.py"; Mode = "700" },
    @{ Local = "remote/py26/v3_forensic_json.py"; Remote = "$remoteRoot/py26/v3_forensic_json.py"; Mode = "700" },
    @{ Local = "remote/py26/v3_deep_forensic_json.py"; Remote = "$remoteRoot/py26/v3_deep_forensic_json.py"; Mode = "700" },
    @{ Local = "remote/py26/v3_exact_rollback_json.py"; Remote = "$remoteRoot/py26/v3_exact_rollback_json.py"; Mode = "700" },
    @{ Local = "remote/config/discovery-allowlist.json"; Remote = "$remoteRoot/config/discovery-allowlist.json"; Mode = "600" },
    @{ Local = "remote/config/design-write-policy.json"; Remote = "$remoteRoot/config/design-write-policy.json"; Mode = "600" },
    @{ Local = "remote/config/design-write-v3-plan.json"; Remote = "$remoteRoot/config/design-write-v3-plan.json"; Mode = "600" },
    @{ Local = "remote/config/design-write-v3-exact-conditional-rollback-plan.json"; Remote = "$remoteRoot/config/design-write-v3-exact-conditional-rollback-plan.json"; Mode = "600" },
    @{ Local = "remote/discovery/ocean-smoke.ocn"; Remote = "$remoteRoot/discovery/ocean-smoke.ocn"; Mode = "600" },
    @{ Local = "remote/discovery/skill-smoke.il"; Remote = "$remoteRoot/discovery/skill-smoke.il"; Mode = "600" },
    @{ Local = "remote/write/design-write-validation.il"; Remote = "$remoteRoot/write/design-write-validation.il"; Mode = "600" },
    @{ Local = "remote/write/design-write-readonly-preflight.il"; Remote = "$remoteRoot/write/design-write-readonly-preflight.il"; Mode = "600" },
    @{ Local = "remote/write/design-write-v2-forensic.il"; Remote = "$remoteRoot/write/design-write-v2-forensic.il"; Mode = "600" },
    @{ Local = "remote/write/design-write-v2-property-diff.il"; Remote = "$remoteRoot/write/design-write-v2-property-diff.il"; Mode = "600" },
    @{ Local = "remote/write/design-write-v2-rollback.il"; Remote = "$remoteRoot/write/design-write-v2-rollback.il"; Mode = "600" },
    @{ Local = "remote/write/design-write-v3-validation.il"; Remote = "$remoteRoot/write/design-write-v3-validation.il"; Mode = "600" },
    @{ Local = "remote/write/design-write-v3-property-diff.il"; Remote = "$remoteRoot/write/design-write-v3-property-diff.il"; Mode = "600" },
    @{ Local = "remote/write/design-write-v3-deep-forensic.il"; Remote = "$remoteRoot/write/design-write-v3-deep-forensic.il"; Mode = "600" },
    @{ Local = "remote/write/design-write-v3-exact-rollback.il"; Remote = "$remoteRoot/write/design-write-v3-exact-rollback.il"; Mode = "600" },
    @{ Local = "remote/profiles/spectre-smoke/smoke.scs"; Remote = "$remoteRoot/profiles/spectre-smoke/smoke.scs"; Mode = "600" },
    @{ Local = "remote/profiles/fixture-rc-transient/profile.json"; Remote = "$remoteRoot/profiles/fixture-rc-transient/profile.json"; Mode = "600" },
    @{ Local = "remote/profiles/actual-differential-amplifier-tb2-transient/profile.json"; Remote = "$remoteRoot/profiles/actual-differential-amplifier-tb2-transient/profile.json"; Mode = "600" }
)

foreach ($command in @("ssh", "scp")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command '$command' was not found."
    }
}

foreach ($file in $files) {
    $localPath = Join-Path $projectRoot $file.Local
    if (-not (Test-Path -LiteralPath $localPath -PathType Leaf)) {
        throw "Required deployment source is missing: $($file.Local)"
    }
}

if (-not $PSCmdlet.ShouldProcess("${sshAlias}:$remoteRoot", "Deploy restricted Cadence runner")) {
    return
}

$setupCommand = "umask 077; mkdir -p '$remoteRoot/bin' '$remoteRoot/lib' '$remoteRoot/py26' '$remoteRoot/config' '$remoteRoot/discovery' '$remoteRoot/discovery-runtime' '$remoteRoot/write' '$remoteRoot/write-validation' '$remoteRoot/write-rollback-v3' '$remoteRoot/profiles/spectre-smoke' '$remoteRoot/profiles/fixture-rc-transient' '$remoteRoot/profiles/actual-differential-amplifier-tb2-transient' '$remoteRoot/jobs'; chmod 700 '$remoteRoot' '$remoteRoot/bin' '$remoteRoot/lib' '$remoteRoot/py26' '$remoteRoot/config' '$remoteRoot/discovery' '$remoteRoot/discovery-runtime' '$remoteRoot/write' '$remoteRoot/write-validation' '$remoteRoot/write-rollback-v3' '$remoteRoot/profiles' '$remoteRoot/profiles/spectre-smoke' '$remoteRoot/profiles/fixture-rc-transient' '$remoteRoot/profiles/actual-differential-amplifier-tb2-transient' '$remoteRoot/jobs'"
& ssh @sshOptions $sshAlias $setupCommand
if ($LASTEXITCODE -ne 0) {
    throw "Remote layout creation failed."
}

foreach ($file in $files) {
    $localPath = Join-Path $projectRoot $file.Local
    $temporaryPath = "$($file.Remote).new"
    & scp @scpOptions $localPath "${sshAlias}:$temporaryPath"
    if ($LASTEXITCODE -ne 0) {
        throw "Upload failed for $($file.Local)."
    }
    $installCommand = "chmod $($file.Mode) '$temporaryPath'; mv -f '$temporaryPath' '$($file.Remote)'"
    & ssh @sshOptions $sshAlias $installCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Atomic install failed for $($file.Local)."
    }
}

$verifyCommand = "bash -n '$remoteRoot/bin/cadence-runner' '$remoteRoot/lib/runner-common.sh' '$remoteRoot/lib/run-smoke-job.sh' '$remoteRoot/lib/run-profile-job.sh' '$remoteRoot/lib/run-design-write-validation.sh' '$remoteRoot/lib/run-design-write-v2-recovery.sh' '$remoteRoot/lib/run-design-write-v3-validation.sh' '$remoteRoot/lib/run-design-write-v3-forensic.sh' '$remoteRoot/lib/run-design-write-v3-deep-forensic.sh' '$remoteRoot/lib/run-design-write-v3-exact-rollback.sh'; /usr/bin/python -m py_compile '$remoteRoot/py26/result_json.py' '$remoteRoot/py26/discovery_json.py' '$remoteRoot/py26/profile_json.py' '$remoteRoot/py26/write_validation_json.py' '$remoteRoot/py26/v2_recovery_json.py' '$remoteRoot/py26/v3_validation_json.py' '$remoteRoot/py26/v3_forensic_json.py' '$remoteRoot/py26/v3_deep_forensic_json.py' '$remoteRoot/py26/v3_exact_rollback_json.py'; rm -f '$remoteRoot/py26/result_json.pyc' '$remoteRoot/py26/discovery_json.pyc' '$remoteRoot/py26/profile_json.pyc' '$remoteRoot/py26/write_validation_json.pyc' '$remoteRoot/py26/v2_recovery_json.pyc' '$remoteRoot/py26/v3_validation_json.pyc' '$remoteRoot/py26/v3_forensic_json.pyc' '$remoteRoot/py26/v3_deep_forensic_json.pyc' '$remoteRoot/py26/v3_exact_rollback_json.pyc'; '$remoteRoot/bin/cadence-runner' version"
& ssh @sshOptions $sshAlias $verifyCommand
if ($LASTEXITCODE -ne 0) {
    throw "Remote syntax or version verification failed."
}
