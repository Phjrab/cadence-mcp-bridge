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
    @{ Local = "remote/py26/result_json.py"; Remote = "$remoteRoot/py26/result_json.py"; Mode = "700" },
    @{ Local = "remote/profiles/spectre-smoke/smoke.scs"; Remote = "$remoteRoot/profiles/spectre-smoke/smoke.scs"; Mode = "600" }
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

$setupCommand = "umask 077; mkdir -p '$remoteRoot/bin' '$remoteRoot/lib' '$remoteRoot/py26' '$remoteRoot/profiles/spectre-smoke' '$remoteRoot/jobs'; chmod 700 '$remoteRoot' '$remoteRoot/bin' '$remoteRoot/lib' '$remoteRoot/py26' '$remoteRoot/profiles' '$remoteRoot/profiles/spectre-smoke' '$remoteRoot/jobs'"
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

$verifyCommand = "bash -n '$remoteRoot/bin/cadence-runner' '$remoteRoot/lib/runner-common.sh' '$remoteRoot/lib/run-smoke-job.sh'; /usr/bin/python -m py_compile '$remoteRoot/py26/result_json.py'; rm -f '$remoteRoot/py26/result_json.pyc'; '$remoteRoot/bin/cadence-runner' version"
& ssh @sshOptions $sshAlias $verifyCommand
if ($LASTEXITCODE -ne 0) {
    throw "Remote syntax or version verification failed."
}
