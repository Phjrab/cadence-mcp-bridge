# Fixture-only harness. The copied deployer is rewritten to use a local fake Python process.
param([string]$Scenario = 'success')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$env:PATH = Join-Path $PSScriptRoot 'empty-bin'
$env:TEMP = Join-Path $PSScriptRoot 'scratch'
$env:TMP = $env:TEMP
$env:WP14_FAKE_SCENARIO = $Scenario
$result = [ordered]@{ success = $false; error = $null; output = @(); calls = @() }
try {
    $deployer = Join-Path $PSScriptRoot 'scripts/deploy-wp14-narrow.ps1'
    if ($Scenario -ceq 'whatif') { $result.output = @(& $deployer -WhatIf) }
    else { $result.output = @(& $deployer -Confirm:$false) }
    $result.success = $true
}
catch { $result.error = $_.Exception.Message }
$calls = Join-Path $PSScriptRoot 'calls.jsonl'
if (Test-Path -LiteralPath $calls) {
    $result.calls = @(Get-Content -LiteralPath $calls -Encoding utf8 | ForEach-Object { $_ | ConvertFrom-Json })
}
Write-Output ('WP14_TEST_RESULT=' + ($result | ConvertTo-Json -Depth 6 -Compress))
