[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$sshAlias = "cadence-vm"
$runner = "/home/buet/cds_work/.cadence_mcp/bin/cadence-runner"
$sshOptions = @(
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=10"
)

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw "Required command 'ssh' was not found."
}

# WP-07 intentionally exposes planning only. No switch can enable deletion.
& ssh @sshOptions $sshAlias $runner cleanup-dry-run
if ($LASTEXITCODE -ne 0) {
    throw "Remote retention dry-run failed."
}
