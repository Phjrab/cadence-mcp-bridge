# Operator-only local readiness check. No authorization comparison or grant.
# Deliberately no advanced/common parameters: every caller argument is rejected.
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$failureCode = 'LOCAL_CHECK_FAILED'

function Read-FixedIdentity {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    try { $sid = $identity.User.Value }
    finally { $identity.Dispose() }
    $machine = (Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Cryptography').MachineGuid
    return @{ Sid = $sid; Machine = $machine }
}

function Test-IdentityShape($Identity) {
    if ($Identity -isnot [Collections.IDictionary] -or $Identity.Count -ne 2) { return $false }
    if ($Identity.Sid -isnot [string] -or $Identity.Machine -isnot [string]) { return $false }
    # No trimming or case conversion: the deployer hashes the exact original strings.
    return ($Identity.Sid.Length -le 184 -and
        $Identity.Sid -cmatch '\AS-1-5-21-([0-9]{1,10}-){3}[0-9]{1,10}\z' -and
        $Identity.Machine -cmatch '\A[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\z' -and
        $Identity.Machine -ne '00000000-0000-0000-0000-000000000000')
}

function Get-LocalDigest($Identity) {
    $bytes = [Text.Encoding]::UTF8.GetBytes("$($Identity.Sid)|$($Identity.Machine)")
    try { return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant() }
    finally { [Array]::Clear($bytes, 0, $bytes.Length) }
}

try {
    $failureCode = 'ARGUMENTS_NOT_ALLOWED'
    if ($args.Count -ne 0) { throw 'Rejected' }
    $failureCode = 'UNSUPPORTED_RUNTIME'
    if ($PSVersionTable.PSVersion -lt [version]'7.5' -or -not $IsWindows) { throw 'Rejected' }
    $failureCode = 'DEPLOYER_INTEGRITY_FAILED'
    $deployer = Join-Path $PSScriptRoot 'deploy-wp14-recovery.ps1'
    $cursor = [IO.Path]::GetFullPath($deployer)
    while ($cursor) {
        if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Rejected'
        }
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
    $file = Get-Item -LiteralPath $deployer
    if ($file.PSIsContainer -or $file.Length -gt 131072) { throw 'Rejected' }
    $text = [IO.File]::ReadAllText($deployer).Replace("`r`n", "`n").Replace("`r", "`n")
    $hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData(
        [Text.Encoding]::UTF8.GetBytes($text))).ToLowerInvariant()
    if ($hash -cne 'e4ed2610aa0cb6a5b930b0ce6a52f1a6d2273c390195f0b58ff3e17c0d976374') {
        throw 'Rejected'
    }
    $failureCode = 'IDENTITY_UNAVAILABLE'
    $first = Read-FixedIdentity
    $failureCode = 'IDENTITY_INVALID'
    if (-not (Test-IdentityShape $first)) { throw 'Rejected' }
    $failureCode = 'IDENTITY_UNAVAILABLE'
    $second = Read-FixedIdentity
    $failureCode = 'IDENTITY_INVALID'
    if (-not (Test-IdentityShape $second)) { throw 'Rejected' }
    $failureCode = 'IDENTITY_CHANGED'
    if ($first.Sid -cne $second.Sid -or $first.Machine -cne $second.Machine) { throw 'Rejected' }
    $failureCode = 'LOCAL_CHECK_FAILED'
    $binding = Get-LocalDigest $first
    if ($binding -cnotmatch '\A[0-9a-f]{64}\z' -or $binding -cne (Get-LocalDigest $second)) {
        throw 'Rejected'
    }
    # A success proves only stable, supported local inputs and a computable rule.
    # It does not compare an Authorization or establish remote readiness.
    [Console]::Out.WriteLine('{"success":true,"code":"LOCAL_RULE_READY"}')
    exit 0
}
catch {
    [Console]::Out.WriteLine('{"success":false,"code":"' + $failureCode + '"}')
    exit 1
}
finally {
    $first = $null
    $second = $null
    $binding = $null
}
