[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Run 'uv sync --all-groups' before E2E verification."
}

& $python -m cadence_mcp_bridge.e2e
if ($LASTEXITCODE -ne 0) {
    throw "MCP-to-Spectre E2E verification failed."
}
