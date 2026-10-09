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

    & $sourcePython -I -X utf8 (Join-Path $projectRoot "scripts\verify-distribution.py") `
        --project $projectRoot --artifacts $distributionDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "License or distribution-content audit failed."
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
    # Isolate DLL file identity from the active source environment/cache on Windows.
    # Shared uv hardlinks can keep a temporary DLL undeletable while tests import it.
    $runtimeRequirements = Join-Path $resolvedTemporaryRoot "locked-runtime.txt"
    & $uv export --quiet --locked --no-dev --no-emit-project --no-header `
        --format requirements.txt --output-file $runtimeRequirements
    if ($LASTEXITCODE -ne 0) { throw "Locked runtime export failed." }
    & $uv pip install --link-mode copy --python $python --requirement $runtimeRequirements `
        $wheel[0].FullName
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

    $contextAcceptance = Join-Path $projectRoot "scripts\verify-runtime-context-install.py"
    & $python -I -X utf8 $contextAcceptance `
        --examples (Join-Path $projectRoot "docs\examples\onboarding") `
        --workspace (Join-Path $resolvedTemporaryRoot "runtime-acceptance")
    if ($LASTEXITCODE -ne 0) { throw "Installed operator context acceptance failed." }

    & $python -I -X utf8 (Join-Path $projectRoot "scripts\verify-operation-install.py") `
        --examples (Join-Path $projectRoot "docs\examples\onboarding") `
        --workspace (Join-Path $resolvedTemporaryRoot "operation-acceptance")
    if ($LASTEXITCODE -ne 0) { throw "Installed local operation form acceptance failed." }

    $bootstrapAcceptance = Join-Path $projectRoot "scripts\verify-bootstrap-install.py"
    $operatorWorkspace = Join-Path $resolvedTemporaryRoot "operator-state-acceptance"
    & $python -I -X utf8 $bootstrapAcceptance `
        --examples (Join-Path $projectRoot "docs\examples\onboarding") `
        --workspace $operatorWorkspace
    if ($LASTEXITCODE -ne 0) { throw "Installed fixed bootstrap acceptance failed." }

    # Same-version artifact reinstall is preservation evidence, not N-to-N+1 qualification.
    & $uv pip install --no-deps --reinstall-package cadence-mcp-bridge --link-mode copy `
        --python $python $wheel[0].FullName
    if ($LASTEXITCODE -ne 0) { throw "Isolated candidate reinstall failed." }
    & $python -I -X utf8 $bootstrapAcceptance --workspace $operatorWorkspace --verify-preserved
    if ($LASTEXITCODE -ne 0) { throw "Reinstall changed synthetic operator state." }

    & $uv pip uninstall --python $python cadence-mcp-bridge
    if ($LASTEXITCODE -ne 0) {
        throw "Package uninstall failed."
    }
    & $python -I -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('cadence_mcp_bridge') is None else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Package remained importable after uninstall."
    }

    & $python -I -X utf8 $bootstrapAcceptance --workspace $operatorWorkspace --verify-preserved
    if ($LASTEXITCODE -ne 0) { throw "Uninstall changed synthetic operator state." }

    Write-Output "Package build, installed protocol/bootstrap, reinstall and uninstall preservation passed."
}
finally {
    if (Test-Path -LiteralPath $resolvedTemporaryRoot -PathType Container) {
        Remove-Item -LiteralPath $resolvedTemporaryRoot -Recurse -Force
    }
}
