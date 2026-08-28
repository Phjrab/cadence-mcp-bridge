[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Run 'uv sync --all-groups' before security verification."
}

& (Join-Path $PSScriptRoot "security-preflight.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "Secret preflight failed."
}

& $python -m pytest tests/unit/test_security.py -v
if ($LASTEXITCODE -ne 0) {
    throw "Security test suite failed."
}

$uv = (Get-Command uv -ErrorAction Stop).Source
$auditRequirements = Join-Path ([IO.Path]::GetTempPath()) ("cadence-mcp-audit-{0}.txt" -f [Guid]::NewGuid().ToString("N"))
try {
    & $uv export --quiet --frozen --all-groups --no-emit-project --no-header --format requirements.txt --output-file $auditRequirements
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency export failed."
    }
    & $python -m pip_audit --requirement $auditRequirements --strict --progress-spinner off
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency vulnerability scan failed."
    }
}
finally {
    if (Test-Path -LiteralPath $auditRequirements -PathType Leaf) {
        Remove-Item -LiteralPath $auditRequirements -Force
    }
}
