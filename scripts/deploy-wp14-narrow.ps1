#requires -Version 7.5
[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$packageHash = "7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87"
$packageRelativePath = "docs/approvals/WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE_V1.json"
$authorizationRelativePath = "docs/approvals/WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V2.json"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$packagePath = Join-Path $projectRoot $packageRelativePath
$authorizationPath = Join-Path $projectRoot $authorizationRelativePath
$lineagePath = Join-Path $projectRoot "remote/config/runner-lineage.json"
$sshAlias = "cadence-vm"
$remoteRoot = "/home/buet/cds_work/.cadence_mcp"
$snapshotRoot = "$remoteRoot/deployment-snapshots/wp14-7d93fefb-runner-0.19.0"
$maximumOutputBytes = 65536
$maximumWallClockSeconds = 300
$stopwatch = [Diagnostics.Stopwatch]::StartNew()

$assets = @(
    [pscustomobject]@{ Path = "remote/bin/cadence-runner"; Hash = "fc644dc4f463d89d6b51e3e607a5495390f7c0e3aac2c6dc9ddd896923e0f0f8"; PackageMode = "0700"; Mode = "700" },
    [pscustomobject]@{ Path = "remote/lib/runner-common.sh"; Hash = "a2f83de6560476687d97fcc73274d6fd2720dd93892bbcabce286e8b61c7e995"; PackageMode = "0700"; Mode = "700" },
    [pscustomobject]@{ Path = "remote/lib/run-ade-profile-introspection.sh"; Hash = "4f68ba74f5bbe2f04428668d95075f9ba4a3a792480c94fde9cdd308ffc0ce2f"; PackageMode = "0700"; Mode = "700" },
    [pscustomobject]@{ Path = "remote/lib/run-wp14-role-discovery.sh"; Hash = "0736d588484d26c5fa98629bc3f04f5c200a1f45e473ac555f64631ac15234ba"; PackageMode = "0700"; Mode = "700" },
    [pscustomobject]@{ Path = "remote/py26/actual_profile_audit.py"; Hash = "d947a911a26613e7c5a9822a0e7e554e1db9656393ce94f7995928bf66b8281c"; PackageMode = "0700"; Mode = "700" },
    [pscustomobject]@{ Path = "remote/py26/ade_profile_introspection.py"; Hash = "c34fac9e4aebc061f1610739085ac0ba0a4579600f4700c416840219a383f87a"; PackageMode = "0700"; Mode = "700" },
    [pscustomobject]@{ Path = "remote/py26/wp14_role_discovery.py"; Hash = "dc14b6fec53a27d401e222551502d7e894f5e35a9b29b53d802e890998ecd48e"; PackageMode = "0700"; Mode = "700" },
    [pscustomobject]@{ Path = "remote/discovery/ade-profile-introspection.il"; Hash = "47ae77075416783eccf4e96bf06537202a4d65630aebd8fc29b606ff28f3861b"; PackageMode = "0600"; Mode = "600" },
    [pscustomobject]@{ Path = "remote/discovery/wp14-role-discovery.il"; Hash = "9dcdef026bc3191acd0c9256c32a8cc0875778e65d21479e80067de70daa8586"; PackageMode = "0600"; Mode = "600" },
    [pscustomobject]@{ Path = "remote/config/runner-lineage.json"; Hash = "02d43c54e7bc314e5ae17a845c40f9d02aba998c0ddbea9f918d0ceaeb365bed"; PackageMode = "0600"; Mode = "600" },
    [pscustomobject]@{ Path = "remote/profiles/actual-differential-amplifier-tb2-transient/profile.json"; Hash = "619106e02d0662d3a2b39b29252d445f6e5eae41fd865c7d1a782366accf1bdb"; PackageMode = "0600"; Mode = "600" }
)

function Get-NormalizedLfBytes {
    param([Parameter(Mandatory)][string]$LiteralPath)
    $text = [IO.File]::ReadAllText($LiteralPath)
    $normalized = $text.Replace("`r`n", "`n").Replace("`r", "`n")
    return [Text.UTF8Encoding]::new($false).GetBytes($normalized)
}

function Get-NormalizedLfSha256 {
    param([Parameter(Mandatory)][string]$LiteralPath)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $algorithm.ComputeHash((Get-NormalizedLfBytes -LiteralPath $LiteralPath))
        return ([BitConverter]::ToString($hashBytes)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $algorithm.Dispose()
    }
}

function Assert-WallClock {
    if ($stopwatch.Elapsed.TotalSeconds -ge $maximumWallClockSeconds) {
        throw "WP-14 narrow deployment exceeded its fixed wall-clock limit. No retry is allowed."
    }
}

function Assert-RepositoryLeaf {
    param([Parameter(Mandatory)][string]$RelativePath)
    if ($RelativePath -notmatch '\A(?:remote|docs)/[A-Za-z0-9._/-]+\z' -or $RelativePath.Contains("..")) {
        throw "Invalid fixed repository asset path."
    }
    $candidate = Join-Path $projectRoot $RelativePath
    Assert-NoReparseAncestors $candidate
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "A required fixed asset is missing: $RelativePath"
    }
    $item = Get-Item -LiteralPath $candidate -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "A fixed asset must not be a reparse point: $RelativePath"
    }
    $rootPrefix = $projectRoot.TrimEnd('\') + '\'
    if (-not $item.FullName.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "A fixed asset resolved outside the repository root."
    }
    return $item.FullName
}

function Assert-PackageAndAssets {
    Assert-NoReparseAncestors $packagePath
    if ((Get-NormalizedLfSha256 -LiteralPath $packagePath) -ne $packageHash) {
        throw "WP-14 approval package hash mismatch."
    }
    $package = Get-Content -LiteralPath $packagePath -Raw | ConvertFrom-Json
    if ($package.package_id -ne "WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE" -or
        $package.package_version -ne 1 -or $package.record_kind -ne "approval_request_not_grant") {
        throw "WP-14 approval package identity mismatch."
    }
    foreach ($property in $package.authority.PSObject.Properties) {
        if ($property.Value -ne $false) {
            throw "The immutable request package unexpectedly grants authority."
        }
    }
    if (@($package.deployment_asset_allowlist).Count -ne $assets.Count) {
        throw "WP-14 deployment allowlist count mismatch."
    }
    $expectedByPath = @{}
    foreach ($asset in $assets) {
        if ($expectedByPath.ContainsKey($asset.Path)) { throw "Duplicate fixed deployment path." }
        $expectedByPath[$asset.Path] = $asset
    }
    foreach ($entry in $package.deployment_asset_allowlist) {
        if (-not $expectedByPath.ContainsKey($entry.path)) {
            throw "The approval package contains an unexpected deployment path."
        }
        $expected = $expectedByPath[$entry.path]
        if ($entry.normalized_lf_sha256 -ne $expected.Hash -or
            $entry.remote_mode -ne $expected.PackageMode) {
            throw "The approval package identity does not match the fixed deployer."
        }
    }
    foreach ($binding in $package.bound_contracts) {
        $bindingPath = Assert-RepositoryLeaf -RelativePath $binding.path
        if ((Get-NormalizedLfSha256 -LiteralPath $bindingPath) -ne $binding.normalized_lf_sha256) {
            throw "A bound WP-14 plan hash does not match the approval package."
        }
    }
    foreach ($asset in $assets) {
        $assetPath = Assert-RepositoryLeaf -RelativePath $asset.Path
        if ((Get-NormalizedLfSha256 -LiteralPath $assetPath) -ne $asset.Hash) {
            throw "A fixed deployment asset hash does not match the package: $($asset.Path)"
        }
    }
}

function Assert-SeparateRemoteAuthorization {
    if (-not (Test-Path -LiteralPath $authorizationPath -PathType Leaf)) {
        throw "Remote preflight and deployment are not authorized. The required separate hash-bound authorization record is absent; no remote command was invoked."
    }
    Assert-NoReparseAncestors $authorizationPath
    if ((Get-Item -LiteralPath $authorizationPath).Length -gt 32768) {
        throw "Remote authorization exceeds the local size bound."
    }
    try {
        $json = Get-Content -LiteralPath $authorizationPath -Raw
        $document = [Text.Json.JsonDocument]::Parse($json)
        try { Assert-JsonTree $document.RootElement 0 }
        finally { $document.Dispose() }
        $authorization = $json | ConvertFrom-Json -AsHashtable -DateKind String
    }
    catch { throw "Invalid or Duplicate authorization JSON; content suppressed." }
    Assert-ExactKeys $authorization @('schema_version', 'record_kind', 'status',
        'package_normalized_lf_sha256', 'deployer_normalized_lf_sha256',
        'remote_preflight_authorized', 'remote_deployment_authorized', 'max_uses',
        'authorization_id', 'not_before', 'expires_at', 'executor_binding',
        'remote_identity', 'preimages', 'evidence_sha256', 'observed_at')
    foreach ($key in @('record_kind', 'status', 'package_normalized_lf_sha256',
        'deployer_normalized_lf_sha256', 'executor_binding')) {
        # PowerShell comparisons on arrays filter elements; require scalar strings first.
        if ($authorization[$key] -isnot [string]) { throw "Invalid scalar authorization field." }
    }
    $selfHash = Get-NormalizedLfSha256 -LiteralPath $PSCommandPath
    if ($authorization.schema_version -isnot [long] -or $authorization.schema_version -ne 2 -or
        $authorization.record_kind -cne "explicit_remote_preflight_and_deployment_authorization" -or
        $authorization.status -cne "APPROVED" -or
        $authorization.package_normalized_lf_sha256 -cne $packageHash -or
        $authorization.deployer_normalized_lf_sha256 -cne $selfHash -or
        $authorization.remote_preflight_authorized -isnot [bool] -or
        $authorization.remote_preflight_authorized -ne $true -or
        $authorization.remote_deployment_authorized -isnot [bool] -or
        $authorization.remote_deployment_authorized -ne $true -or
        $authorization.max_uses -isnot [long] -or $authorization.max_uses -ne 1) {
        throw "The separate remote authorization is invalid or not bound to this exact deployer."
    }
    if ($authorization.authorization_id -isnot [string] -or
        $authorization.authorization_id -cnotmatch '\A[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}\z' -or
        $authorization.evidence_sha256 -isnot [string] -or
        $authorization.evidence_sha256 -cnotmatch '\A[0-9a-f]{64}\z' -or
        $authorization.evidence_sha256 -ceq ('0' * 64) -or
        $authorization.executor_binding -cne (Get-ExecutorBinding)) {
        throw "Unverified authorization identity or evidence binding."
    }
    $start = Convert-FixedTimestamp $authorization.not_before
    $end = Convert-FixedTimestamp $authorization.expires_at
    $observed = Convert-FixedTimestamp $authorization.observed_at
    $now = [DateTimeOffset]::UtcNow
    if ($start -gt $now -or $end -le $now -or $end -le $start -or
        ($end - $start).TotalHours -gt 24 -or $observed -gt $start -or
        ($now - $observed).TotalHours -gt 24) { throw "Authorization or evidence is stale." }
    Assert-ExactKeys $authorization.remote_identity @('hostname', 'user', 'root', 'verified')
    foreach ($key in @('hostname', 'user', 'root')) {
        if ($authorization.remote_identity[$key] -isnot [string]) { throw "Invalid scalar identity." }
    }
    if ($authorization.remote_identity.hostname -cne 'cadence' -or
        $authorization.remote_identity.user -cne 'buet' -or
        $authorization.remote_identity.root -cne $remoteRoot -or
        $authorization.remote_identity.verified -isnot [bool] -or
        $authorization.remote_identity.verified -ne $true) { throw "Unverified remote identity." }
    if ($authorization.preimages -isnot [array] -or $authorization.preimages.Count -ne 11) {
        throw "Incomplete preimage evidence."
    }
    $script:preimages = @{}
    foreach ($entry in $authorization.preimages) {
        Assert-ExactKeys $entry @('path', 'presence', 'sha256', 'mode')
        if ($entry.presence -isnot [string]) { throw "Invalid scalar preimage presence." }
        if ($entry.path -isnot [string] -or
            $entry.path -cnotin @($assets.Path) -or $script:preimages.ContainsKey($entry.path)) {
            throw "Unexpected or duplicate preimage."
        }
        if ($entry.presence -ceq 'absent') {
            if ($null -ne $entry.sha256 -or $null -ne $entry.mode -or
                $entry.path -cin @('remote/bin/cadence-runner', 'remote/lib/runner-common.sh')) {
                throw "Invalid absent preimage."
            }
        }
        elseif ($entry.presence -ceq 'file') {
            if ($entry.sha256 -isnot [string] -or $entry.sha256 -cnotmatch '\A[0-9a-f]{64}\z' -or
                $entry.sha256 -ceq ('0' * 64) -or $entry.mode -isnot [string] -or
                $entry.mode -cnotmatch '\A[67]00\z') { throw "Unverified preimage hash or mode." }
        }
        else { throw "Unverified preimage presence." }
        $script:preimages[$entry.path] = $entry
    }
    $script:authorization = $authorization
    $script:authorizationExpiry = $end
}

function Assert-JsonTree($Element, [int]$Depth) {
    if ($Depth -gt 8) { throw "Authorization nesting exceeds bound." }
    if ($Element.ValueKind -eq [Text.Json.JsonValueKind]::Object) {
        $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($property in $Element.EnumerateObject()) {
            if (-not $names.Add($property.Name)) { throw "Duplicate authorization key." }
            Assert-JsonTree $property.Value ($Depth + 1)
        }
    }
    elseif ($Element.ValueKind -eq [Text.Json.JsonValueKind]::Array) {
        if ($Element.GetArrayLength() -gt 32) { throw "Authorization array exceeds bound." }
        foreach ($item in $Element.EnumerateArray()) { Assert-JsonTree $item ($Depth + 1) }
    }
}

function Assert-ExactKeys($Record, [string[]]$Keys) {
    if ($Record -isnot [System.Collections.IDictionary] -or
        $Record.Count -ne $Keys.Count -or
        @($Record.Keys | Where-Object { $_ -cnotin $Keys }).Count -ne 0) {
        throw "Invalid closed authorization schema."
    }
}

function Convert-FixedTimestamp($Value) {
    if ($Value -isnot [string] -or $Value -cnotmatch '\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\z') {
        throw "Invalid authorization timestamp."
    }
    return [DateTimeOffset]::ParseExact($Value, "yyyy-MM-dd'T'HH:mm:ss'Z'",
        [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal)
}

function Get-ExecutorBinding {
    if (-not $IsWindows) { throw "This fixed deployer requires Windows." }
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $machine = (Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Cryptography').MachineGuid
    $bytes = [Text.Encoding]::UTF8.GetBytes("$sid|$machine")
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
}

function Assert-NoReparseAncestors([string]$Path) {
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if (((Get-Item -LiteralPath $cursor -Force).Attributes -band
                [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse path rejected." }
        }
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
}

function Claim-OneAttempt {
    # One operator/machine ledger shared by all checkouts, never inside a git worktree.
    $stateRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'CadenceMcpBridge\wp14-narrow'
    Assert-NoReparseAncestors $stateRoot
    [IO.Directory]::CreateDirectory($stateRoot) | Out-Null
    Assert-NoReparseAncestors $stateRoot
    $lockPath = Join-Path $stateRoot 'operation.lock'
    $claimPath = Join-Path $stateRoot ("attempt-" + $packageHash + ".json")
    Assert-NoReparseAncestors $lockPath
    Assert-NoReparseAncestors $claimPath
    try {
        $script:operationLock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate,
            [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        # CreateNew consumes the attempt even if writing, flushing or process startup then fails.
        $claim = [IO.FileStream]::new($claimPath, [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write, [IO.FileShare]::None, 4096, [IO.FileOptions]::WriteThrough)
        try {
            $record = [ordered]@{
                state = 'consumed_before_transport'
                authorization_id = $authorization.authorization_id
                authorization_sha256 = Get-NormalizedLfSha256 $authorizationPath
                package_sha256 = $packageHash
                deployer_sha256 = Get-NormalizedLfSha256 $PSCommandPath
                consumed_at = [DateTimeOffset]::UtcNow.ToString('o')
            }
            $bytes = [Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json -Compress))
            $claim.Write($bytes, 0, $bytes.Length)
            $claim.Flush($true)
        }
        finally { $claim.Dispose() }
    }
    catch { throw "WP-14 attempt already consumed, concurrent, or ledger unavailable. No retry." }
}

function Invoke-BoundedTransport {
    param([ValidateSet('ssh', 'scp')][string]$Kind, [string]$First, [string]$Second)
    Assert-WallClock
    if ([DateTimeOffset]::UtcNow -ge $authorizationExpiry) { throw "Authorization expired." }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo.FileName = Join-Path ([Environment]::GetFolderPath('Windows')) "System32\OpenSSH\$Kind.exe"
    Assert-NoReparseAncestors $process.StartInfo.FileName
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    foreach ($argument in @(
        "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=2", "--", $First, $Second
    )) { $process.StartInfo.ArgumentList.Add($argument) }
    $started = $false
    $output = [IO.MemoryStream]::new()
    try {
        $started = $process.Start()
        if (-not $started) { throw "Transport could not start." }
        $streams = @($process.StandardOutput.BaseStream, $process.StandardError.BaseStream)
        $buffers = @([byte[]]::new(4096), [byte[]]::new(4096))
        $reads = @($streams[0].ReadAsync($buffers[0], 0, 4096),
            $streams[1].ReadAsync($buffers[1], 0, 4096))
        $done = @($false, $false)
        $total = 0
        $stderrBytes = 0
        while (-not ($done[0] -and $done[1] -and $process.HasExited)) {
            Assert-WallClock
            if ([DateTimeOffset]::UtcNow -ge $authorizationExpiry) { throw "Authorization expired." }
            for ($i = 0; $i -lt 2; $i++) {
                if (-not $done[$i] -and $reads[$i].IsCompleted) {
                    $count = $reads[$i].GetAwaiter().GetResult()
                    if ($count -eq 0) { $done[$i] = $true; continue }
                    $total += $count
                    if ($total -gt $maximumOutputBytes) { throw "Transport exceeded the output limit." }
                    if ($i -eq 0) { $output.Write($buffers[$i], 0, $count) }
                    else { $stderrBytes += $count }
                    $reads[$i] = $streams[$i].ReadAsync($buffers[$i], 0, 4096)
                }
            }
            [Threading.Thread]::Sleep(5)
        }
        Assert-WallClock
        if ($process.ExitCode -ne 0 -or $stderrBytes -ne 0) {
            throw "A fixed WP-14 transport failed. No retry, cleanup, or fallback was attempted."
        }
        return [Text.UTF8Encoding]::new($false, $true).GetString($output.ToArray()).Trim()
    }
    catch {
        # No untrusted output, command, path, or underlying process exception is surfaced.
        if ($_.Exception.Message -match 'wall-clock limit|output limit|Authorization expired|No retry, cleanup') {
            throw $_.Exception.Message
        }
        throw "WP-14 transport failed closed; remote outcome unknown. No retry."
    }
    finally {
        if ($started -and -not $process.HasExited) {
            try {
                $process.Kill($true)
                if (-not $process.WaitForExit(1000)) { throw "Local transport termination unconfirmed." }
            }
            catch { throw "Local transport termination unconfirmed; remote outcome unknown. No retry." }
        }
        $output.Dispose()
        $process.Dispose()
    }
}

function Invoke-FixedSsh {
    param([Parameter(Mandatory)][string]$FixedCommand)
    return Invoke-BoundedTransport -Kind ssh -First $sshAlias -Second $FixedCommand
}

function Get-PreimageCheck([string]$AssetPath) {
    $entry = $preimages[$AssetPath]
    $destination = $remoteDestinations[$AssetPath]
    if ($entry.presence -ceq 'absent') {
        return "test ! -e '$destination' && test ! -L '$destination' || exit 42"
    }
    return "test -f '$destination' && test ! -L '$destination' || exit 42; test `"`$(stat -c '%U:%h:%a' '$destination')`" = 'buet:1:$($entry.mode)'; test `"`$(sha256sum '$destination' | awk '{print `$1}')`" = '$($entry.sha256)'"
}

function Send-FixedAsset {
    param(
        [Parameter(Mandatory)][string]$LocalPath,
        [Parameter(Mandatory)][string]$RemoteTemporaryPath
    )
    $response = Invoke-BoundedTransport -Kind scp -First $LocalPath -Second "${sshAlias}:$RemoteTemporaryPath"
    if ($response.Length -ne 0) { throw "Unexpected upload response." }
}

Assert-PackageAndAssets

$lineage = Get-Content -LiteralPath $lineagePath -Raw | ConvertFrom-Json
if ($lineage.repository_runner_version -ne "0.19.0" -or
    $lineage.observed_remote_runner_version -ne "0.18.0" -or
    $lineage.deployment_enabled -ne $false) {
    throw "Runner lineage or deployment_enabled=false does not match WP-14."
}

Assert-SeparateRemoteAuthorization

if (-not $PSCmdlet.ShouldProcess("${sshAlias}:$remoteRoot", "Deploy the exact WP-14 allowlist once")) {
    return
}

$script:operationLock = $null
try {
Claim-OneAttempt

$remoteDestinations = @{}
foreach ($asset in $assets) {
    $remoteDestinations[$asset.Path] = "$remoteRoot/$($asset.Path.Substring('remote/'.Length))"
}

$preflight = [Collections.Generic.List[string]]::new()
$preflight.Add("set -eu")
$preflight.Add("test `"`$(hostname)`" = 'cadence' && test `"`$(id -un)`" = 'buet' || exit 42")
$preflight.Add("root='$remoteRoot'")
$preflight.Add("test -d `"`$root`" && test ! -L `"`$root`" || exit 42")
$preflight.Add("test `"`$(readlink -f `"`$root`")`" = `"`$root`"")
$preflight.Add("if ps -ef | grep -E '[v]irtuoso|[o]cean' >/dev/null 2>&1; then exit 42; fi")
$preflight.Add("test -x '$remoteRoot/bin/cadence-runner'")
$preflight.Add("if test -e '$remoteRoot/deployment-snapshots'; then test -d '$remoteRoot/deployment-snapshots' && test ! -L '$remoteRoot/deployment-snapshots' && test `"`$(readlink -f '$remoteRoot/deployment-snapshots')`" = '$remoteRoot/deployment-snapshots' || exit 42; fi")
$preflight.Add("test ! -e '$snapshotRoot' && test ! -L '$snapshotRoot' || exit 42")
foreach ($asset in $assets) {
    $destination = $remoteDestinations[$asset.Path]
    $parent = $destination.Substring(0, $destination.LastIndexOf('/'))
    $temporary = "$destination.wp14-v1-new"
    $preflight.Add("test -d '$parent' && test ! -L '$parent' || exit 42")
    $preflight.Add("test `"`$(readlink -f '$parent')`" = '$parent'")
    $preflight.Add("test ! -L '$destination' && test ! -e '$temporary' && test ! -L '$temporary' || exit 42")
    $preflight.Add((Get-PreimageCheck $asset.Path))
}
$preflight.Add("test `"`$('$remoteRoot/bin/cadence-runner' version)`" = '0.18.0'")
$preflight.Add("printf 'WP14_NARROW_PREFLIGHT_OK\n'")
if ((Invoke-FixedSsh -FixedCommand ($preflight -join "; ")) -ne "WP14_NARROW_PREFLIGHT_OK") {
    throw "The fixed WP-14 preflight returned an unexpected response."
}

$snapshot = [Collections.Generic.List[string]]::new()
$snapshot.Add("set -eu")
$snapshot.Add("umask 077")
$snapshot.Add("mkdir -p '$remoteRoot/deployment-snapshots'")
$snapshot.Add("test ! -L '$remoteRoot/deployment-snapshots'")
$snapshot.Add("mkdir '$snapshotRoot'")
$snapshot.Add("test ! -e '$snapshotRoot/before.tsv'")
$snapshot.Add(": > '$snapshotRoot/before.tsv'")
foreach ($asset in $assets) {
    $destination = $remoteDestinations[$asset.Path]
    $relative = $asset.Path.Substring('remote/'.Length)
    $copy = "$snapshotRoot/$relative"
    $copyParent = $copy.Substring(0, $copy.LastIndexOf('/'))
    $snapshot.Add((Get-PreimageCheck $asset.Path))
    $snapshot.Add("mkdir -p '$copyParent'")
    $snapshot.Add("if test -f '$destination'; then sha=`$(sha256sum '$destination' | awk '{print `$1}'); mode=`$(stat -c '%a' '$destination'); printf '%s\t%s\t%s\n' '$relative' `"`$sha`" `"`$mode`" >> '$snapshotRoot/before.tsv'; cp -p '$destination' '$copy'; chmod 400 '$copy'; else printf '%s\tABSENT\tABSENT\n' '$relative' >> '$snapshotRoot/before.tsv'; fi")
    if ($preimages[$asset.Path].presence -ceq 'file') {
        $snapshot.Add("test `"`$(sha256sum '$copy' | awk '{print `$1}')`" = '$($preimages[$asset.Path].sha256)'")
    }
}
$snapshot.Add("chmod 400 '$snapshotRoot/before.tsv'")
$snapshot.Add("find '$snapshotRoot' -type d -exec chmod 500 {} \;")
$snapshot.Add("printf 'WP14_NARROW_SNAPSHOT_OK\n'")
if ((Invoke-FixedSsh -FixedCommand ($snapshot -join "; ")) -ne "WP14_NARROW_SNAPSHOT_OK") {
    throw "The package-bound before snapshot was not verified."
}

$stagingRoot = Join-Path ([IO.Path]::GetTempPath()) ("cadence-mcp-wp14-" + [Guid]::NewGuid().ToString("N"))
$stagingRoot = [IO.Path]::GetFullPath($stagingRoot)
$tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
if (-not $stagingRoot.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    -not ([IO.Path]::GetFileName($stagingRoot)).StartsWith("cadence-mcp-wp14-", [StringComparison]::Ordinal)) {
    throw "Local staging containment validation failed."
}
New-Item -ItemType Directory -Path $stagingRoot | Out-Null
try {
    foreach ($asset in $assets) {
        $source = Assert-RepositoryLeaf -RelativePath $asset.Path
        $staged = Join-Path $stagingRoot $asset.Path
        New-Item -ItemType Directory -Path (Split-Path -Parent $staged) -Force | Out-Null
        [IO.File]::WriteAllBytes($staged, (Get-NormalizedLfBytes -LiteralPath $source))
        if ((Get-FileHash -LiteralPath $staged -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.Hash) {
            throw "Local normalized staging hash mismatch."
        }
        $destination = $remoteDestinations[$asset.Path]
        $temporary = "$destination.wp14-v1-new"
        Send-FixedAsset -LocalPath $staged -RemoteTemporaryPath $temporary
        $oldCheck = Get-PreimageCheck $asset.Path
        $install = "set -eu; $oldCheck; test -f '$temporary' && test ! -L '$temporary' || exit 42; test `"`$(sha256sum '$temporary' | awk '{print `$1}')`" = '$($asset.Hash)'; chmod '$($asset.Mode)' '$temporary'; mv '$temporary' '$destination'; test `"`$(sha256sum '$destination' | awk '{print `$1}')`" = '$($asset.Hash)'; test `"`$(stat -c '%a' '$destination')`" = '$($asset.Mode)'; printf 'WP14_NARROW_INSTALL_OK\n'"
        if ((Invoke-FixedSsh -FixedCommand $install) -ne "WP14_NARROW_INSTALL_OK") {
            throw "An exact WP-14 asset install was not verified."
        }
    }
}
finally {
    if (Test-Path -LiteralPath $stagingRoot -PathType Container) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}

$verify = [Collections.Generic.List[string]]::new()
$verify.Add("set -eu")
$verify.Add("if ps -ef | grep -E '[v]irtuoso|[o]cean' >/dev/null 2>&1; then exit 42; fi")
foreach ($asset in $assets) {
    $destination = $remoteDestinations[$asset.Path]
    $verify.Add("test -f '$destination' && test ! -L '$destination' || exit 42")
    $verify.Add("test `"`$(sha256sum '$destination' | awk '{print `$1}')`" = '$($asset.Hash)'")
    $verify.Add("test `"`$(stat -c '%a' '$destination')`" = '$($asset.Mode)'")
}
foreach ($relative in @('bin/cadence-runner', 'lib/runner-common.sh',
    'lib/run-ade-profile-introspection.sh', 'lib/run-wp14-role-discovery.sh')) {
    $verify.Add("bash -n '$remoteRoot/$relative'")
}
$verify.Add("/usr/bin/python -c 'import sys; compile(open(sys.argv[1], `"rb`").read(), sys.argv[1], `"exec`")' '$remoteRoot/py26/actual_profile_audit.py'")
$verify.Add("/usr/bin/python -c 'import sys; compile(open(sys.argv[1], `"rb`").read(), sys.argv[1], `"exec`")' '$remoteRoot/py26/ade_profile_introspection.py'")
$verify.Add("/usr/bin/python -c 'import sys; compile(open(sys.argv[1], `"rb`").read(), sys.argv[1], `"exec`")' '$remoteRoot/py26/wp14_role_discovery.py'")
$verify.Add("test `"`$('$remoteRoot/bin/cadence-runner' version)`" = '0.19.0'")
$verify.Add("grep -F 'inspect-ade-profile) runner_inspect_ade_profile' '$remoteRoot/bin/cadence-runner' >/dev/null")
$verify.Add("grep -F 'wp14-role-discovery) runner_wp14_role_discovery' '$remoteRoot/bin/cadence-runner' >/dev/null")
$verify.Add("grep -F 'deployment_enabled' '$remoteRoot/config/runner-lineage.json' >/dev/null")
$verify.Add("printf 'WP14_NARROW_DEPLOYMENT_VERIFIED\n'")
if ((Invoke-FixedSsh -FixedCommand ($verify -join "; ")) -ne "WP14_NARROW_DEPLOYMENT_VERIFIED") {
    throw "The exact WP-14 deployment verification response was not accepted."
}

Write-Output "WP14_NARROW_DEPLOYMENT_VERIFIED"
}
finally {
    if ($null -ne $script:operationLock) { $script:operationLock.Dispose() }
    # Never remove/truncate the permanent claim, including failure and uncertain outcomes.
}
