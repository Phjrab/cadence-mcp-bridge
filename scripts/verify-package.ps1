[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$uv = (Get-Command uv -ErrorAction Stop).Source
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$temporaryRoot = Join-Path $temporaryBase ("cadence-mcp-package-{0}" -f [Guid]::NewGuid().ToString("N"))
$resolvedTemporaryRoot = [IO.Path]::GetFullPath($temporaryRoot)
if (-not $resolvedTemporaryRoot.StartsWith($temporaryBase, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Temporary package path escaped the system temporary directory."
}

New-Item -ItemType Directory -Path $resolvedTemporaryRoot | Out-Null
try {
    $distributionDirectory = Join-Path $resolvedTemporaryRoot "dist"
    & $uv build --out-dir $distributionDirectory $projectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Package build failed."
    }

    $wheel = @(Get-ChildItem -LiteralPath $distributionDirectory -Filter "*.whl")
    if ($wheel.Count -ne 1) {
        throw "Expected exactly one wheel."
    }

    $environmentDirectory = Join-Path $resolvedTemporaryRoot "venv"
    & $uv venv --python 3.12 $environmentDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Temporary verification environment creation failed."
    }

    $python = Join-Path $environmentDirectory "Scripts\python.exe"
    & $uv pip install --python $python $wheel[0].FullName
    if ($LASTEXITCODE -ne 0) {
        throw "Package installation failed."
    }
    $installedVersion = (& $python -m cadence_mcp_bridge --version).Trim()
    if ($LASTEXITCODE -ne 0 -or $installedVersion -ne "1.0.0") {
        throw "Installed CLI version verification failed."
    }

    & $uv pip uninstall --python $python cadence-mcp-bridge
    if ($LASTEXITCODE -ne 0) {
        throw "Package uninstall failed."
    }
    & $python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('cadence_mcp_bridge') is None else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Package remained importable after uninstall."
    }

    Write-Output "Package build, install, CLI version, and uninstall verification passed."
}
finally {
    if (Test-Path -LiteralPath $resolvedTemporaryRoot -PathType Container) {
        Remove-Item -LiteralPath $resolvedTemporaryRoot -Recurse -Force
    }
}
