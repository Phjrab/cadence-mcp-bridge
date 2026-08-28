[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("APPROVE_MCP_WRITE_VALIDATED_V2")]
    [string]$Confirmation
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Run 'uv sync --all-groups' before design write verification."
}

& $python -m cadence_mcp_bridge.write_validation_cli --confirmation $Confirmation
if ($LASTEXITCODE -ne 0) {
    throw "Design write validation failed. Do not create the v1 tag or release."
}
