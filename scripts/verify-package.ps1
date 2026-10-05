[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$uv = (Get-Command uv -ErrorAction Stop).Source
$sourcePython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$expectedVersion = (& $sourcePython -I -c "import pathlib,sys,tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))['project']['version'])" (Join-Path $projectRoot "pyproject.toml")).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($expectedVersion)) {
    throw "Source metadata version could not be read."
}
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
    $installedVersion = (& $python -I -m cadence_mcp_bridge --version).Trim()
    if ($LASTEXITCODE -ne 0 -or $installedVersion -ne $expectedVersion) {
        throw "Installed CLI version verification failed."
    }

    $acceptance = Join-Path $projectRoot "scripts\verify-installed-package.py"
    & $python -I -X utf8 $acceptance --expected-version $expectedVersion `
        --examples (Join-Path $projectRoot "docs\examples\onboarding") `
        --baseline (Join-Path $projectRoot "docs\contracts\MCP_V1_COMPATIBILITY_SNAPSHOT.json") `
        --workspace (Join-Path $resolvedTemporaryRoot "acceptance")
    if ($LASTEXITCODE -ne 0) {
        throw "Installed onboarding/stdio acceptance failed."
    }

    & $uv pip uninstall --python $python cadence-mcp-bridge
    if ($LASTEXITCODE -ne 0) {
        throw "Package uninstall failed."
    }
    & $python -I -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('cadence_mcp_bridge') is None else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Package remained importable after uninstall."
    }

    Write-Output "Package build, installed onboarding/stdio, CLI version, and uninstall verification passed."
}
finally {
    if (Test-Path -LiteralPath $resolvedTemporaryRoot -PathType Container) {
        Remove-Item -LiteralPath $resolvedTemporaryRoot -Recurse -Force
    }
}
