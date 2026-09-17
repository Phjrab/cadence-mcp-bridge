# Test-only harness: copied into a pytest temporary repository; never invokes a native transport.
param(
    [ValidateSet('success', 'whatif', 'fail-preflight', 'fail-snapshot', 'fail-install',
        'fail-verify', 'fail-scp', 'wrong-preflight', 'wrong-snapshot', 'wrong-install',
        'wrong-verify', 'overflow-ssh', 'overflow-scp')]
    [string]$Scenario = 'success'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$env:PATH = Join-Path $PSScriptRoot 'empty-bin'
$env:TEMP = Join-Path $PSScriptRoot 'scratch'
$env:TMP = $env:TEMP
$global:Wp14FakeScenario = $Scenario
$global:Wp14FakeCalls = [Collections.Generic.List[object]]::new()

function Assert-FakeTransportOptions {
    param([object[]]$TransportArgs)
    $expected = @('-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15',
        '-o', 'ServerAliveCountMax=2')
    # PowerShell consumes -- when calling these functions, unlike native executables.
    if ($TransportArgs.Count -ne 12) { throw 'Unexpected fake transport argument count' }
    for ($index = 0; $index -lt $expected.Count; $index++) {
        if ($TransportArgs[$index] -cne $expected[$index]) {
            throw 'Unexpected fake transport options'
        }
    }
}

function global:ssh {
    $transportArgs = @($args)
    Assert-FakeTransportOptions $transportArgs
    if ($transportArgs[10] -cne 'cadence-vm') { throw 'Unexpected fake SSH alias' }
    $command = [string]$transportArgs[11]
    $match = [regex]::Match($command, "printf '(WP14_NARROW_[^']*)'")
    if (-not $match.Success) { throw 'Unrecognized fixed command in fake SSH' }
    $format = $match.Groups[1].Value
    $marker = $format -replace '\\.*$', ''
    $stage = switch ($marker) {
        'WP14_NARROW_PREFLIGHT_OK' { 'preflight' }
        'WP14_NARROW_SNAPSHOT_OK' { 'snapshot' }
        'WP14_NARROW_INSTALL_OK' { 'install' }
        'WP14_NARROW_DEPLOYMENT_VERIFIED' { 'verify' }
        default { throw 'Unexpected fixed stage in fake SSH' }
    }
    $global:Wp14FakeCalls.Add([pscustomobject]@{
        kind = 'ssh'; stage = $stage; command = $command
    })
    $global:LASTEXITCODE = 0
    if ($global:Wp14FakeScenario -ceq "fail-$stage") {
        $global:LASTEXITCODE = 42
        return
    }
    if ($global:Wp14FakeScenario -ceq "wrong-$stage") { return 'UNEXPECTED_MARKER' }
    if ($global:Wp14FakeScenario -ceq 'overflow-ssh') { return ('X' * 65537) }
    # Decode only the fixed printf format; NEVER evaluate the supplied command.
    return [regex]::Unescape($format)
}

function global:scp {
    $transportArgs = @($args)
    Assert-FakeTransportOptions $transportArgs
    $source = [string]$transportArgs[10]
    $destination = [string]$transportArgs[11]
    $prefix = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
    if (-not ([IO.Path]::GetFullPath($source)).StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Fake SCP source escaped the test scratch directory'
    }
    if (-not $destination.StartsWith('cadence-vm:/home/buet/cds_work/.cadence_mcp/') -or
        -not $destination.EndsWith('.wp14-v1-new')) {
        throw 'Unexpected fake SCP destination'
    }
    $global:Wp14FakeCalls.Add([pscustomobject]@{
        kind = 'scp'; stage = 'upload'; destination = $destination
        sha256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    })
    $global:LASTEXITCODE = 0
    if ($global:Wp14FakeScenario -ceq 'fail-scp') { $global:LASTEXITCODE = 42 }
    if ($global:Wp14FakeScenario -ceq 'overflow-scp') { return ('X' * 65537) }
}

if ((Get-Command ssh).CommandType -ne 'Function' -or
    (Get-Command scp).CommandType -ne 'Function') { throw 'Fake transports not installed' }
$result = [ordered]@{ success = $false; error = $null; output = @(); calls = @() }
try {
    $deployer = Join-Path $PSScriptRoot 'scripts/deploy-wp14-narrow.ps1'
    if ($Scenario -ceq 'whatif') {
        $result.output = @(& $deployer -WhatIf)
    }
    else {
        $result.output = @(& $deployer -Confirm:$false)
    }
    $result.success = $true
}
catch {
    $result.error = $_.Exception.Message
}
$result.calls = @($global:Wp14FakeCalls.ToArray())
Write-Output ('WP14_TEST_RESULT=' + ($result | ConvertTo-Json -Depth 6 -Compress))
