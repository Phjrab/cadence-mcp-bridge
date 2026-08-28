[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$serverName = "cadence-mcp-bridge"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = (Resolve-Path (Join-Path $projectRoot ".venv\Scripts\python.exe")).Path
$codexCommand = Get-Command "codex" -ErrorAction Stop
$codexHome = Join-Path $env:USERPROFILE ".codex"
$configPath = Join-Path $codexHome "config.toml"
$newline = [Environment]::NewLine

foreach ($value in @($projectRoot, $pythonPath, $codexHome)) {
    if ($value.IndexOfAny(@([char]0, [char]10, [char]13, [char]39)) -ge 0) {
        throw "A required path cannot be represented safely in TOML."
    }
}

$canonicalLines = @(
    "[mcp_servers.$serverName]",
    "command = '$pythonPath'",
    'args = ["-m", "cadence_mcp_bridge"]',
    "cwd = '$projectRoot'",
    "startup_timeout_sec = 20",
    "tool_timeout_sec = 180",
    "enabled = true",
    "required = true",
    'default_tools_approval_mode = "writes"',
    "",
    "[mcp_servers.$serverName.tools.cadence_submit_smoke]",
    'approval_mode = "prompt"',
    "",
    "[mcp_servers.$serverName.tools.cadence_cancel_job]",
    'approval_mode = "prompt"'
)
$canonicalBlock = $canonicalLines -join $newline

$existing = ""
if (Test-Path -LiteralPath $configPath -PathType Leaf) {
    $existing = [System.IO.File]::ReadAllText($configPath)
}

$kept = New-Object System.Collections.Generic.List[string]
$skipTargetTable = $false
foreach ($line in ($existing -split "`r?`n")) {
    if ($line -match '^\s*\[[^\]]+\]\s*$') {
        $skipTargetTable = $line -match (
            '^\s*\[mcp_servers\.' + [regex]::Escape($serverName) + '(?:\..*)?\]\s*$'
        )
    }
    if (-not $skipTargetTable) {
        $kept.Add($line)
    }
}

$prefix = (($kept -join $newline).TrimEnd())
$updated = if ($prefix.Length -eq 0) {
    $canonicalBlock + $newline
} else {
    $prefix + $newline + $newline + $canonicalBlock + $newline
}

if ($existing -ne $updated) {
    if (-not $PSCmdlet.ShouldProcess($configPath, "Register $serverName with backup")) {
        return
    }
    New-Item -ItemType Directory -Path $codexHome -Force | Out-Null
    if (Test-Path -LiteralPath $configPath -PathType Leaf) {
        $timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
        $backupPath = Join-Path $codexHome "config.toml.WP06-$timestamp.bak"
        Copy-Item -LiteralPath $configPath -Destination $backupPath
        Write-Output "Backup: $backupPath"
    }
    $temporaryPath = Join-Path $codexHome ("config.toml.WP06-{0}.tmp" -f [Guid]::NewGuid())
    try {
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($temporaryPath, $updated, $utf8)
        Move-Item -LiteralPath $temporaryPath -Destination $configPath -Force
    } finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
} else {
    Write-Output "Registration already matches the reviewed configuration."
}

$previousCodexHome = $env:CODEX_HOME
try {
    $env:CODEX_HOME = $codexHome
    $registrationJson = & $codexCommand.Source mcp get $serverName --json
    if ($LASTEXITCODE -ne 0) {
        throw "Codex CLI could not read the registered MCP server."
    }
} finally {
    $env:CODEX_HOME = $previousCodexHome
}

$registration = $registrationJson | ConvertFrom-Json
if (
    $registration.name -ne $serverName -or
    $registration.enabled -ne $true -or
    $registration.transport.type -ne "stdio" -or
    $registration.transport.command -ne $pythonPath -or
    $registration.transport.cwd -ne $projectRoot -or
    ($registration.transport.args -join " ") -ne "-m cadence_mcp_bridge" -or
    $registration.startup_timeout_sec -ne 20 -or
    $registration.tool_timeout_sec -ne 180
) {
    throw "Codex MCP registration did not match the reviewed configuration."
}

Write-Output "Registered: $serverName"
Write-Output "Command: $pythonPath -m cadence_mcp_bridge"
Write-Output "Approval mode: prompt for submit and cancel"
