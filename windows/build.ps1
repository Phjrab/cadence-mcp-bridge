param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [Parameter(Mandatory=$true)][string]$DownloadCache,
    [Parameter(Mandatory=$true)][string]$InnoCompiler
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not [Environment]::Is64BitOperatingSystem -or -not $IsWindows) { throw 'Windows x64 build required' }
$repo = Split-Path $PSScriptRoot -Parent
$destination = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $destination) { throw 'New output directory required; preserve previous builds' }
$pins = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'inputs.lock.json') -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Force $DownloadCache | Out-Null
foreach ($pin in @($pins.python, $pins.inno)) {
    $file = Join-Path $DownloadCache $pin.filename
    if (-not (Test-Path -LiteralPath $file)) { Invoke-WebRequest -Uri $pin.url -OutFile $file }
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pin.sha256) { throw 'Pinned input hash mismatch' }
}
$compilerRoot = Split-Path (Get-Item -LiteralPath $InnoCompiler).FullName -Parent
foreach ($entry in $pins.inno.compiler_files.PSObject.Properties) {
    $compilerFile = Join-Path $compilerRoot $entry.Name
    if ((Get-FileHash -LiteralPath $compilerFile).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw 'Pinned compiler content mismatch'
    }
}
$python = Join-Path $repo '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Build environment missing: uv sync --locked --all-groups' }
$version = (& $python -I -c 'import cadence_mcp_bridge; print(cadence_mcp_bridge.__version__)').Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^2\.2\.0a1$') { throw 'Unreviewed installer version' }
$payload = Join-Path $destination 'payload'
$packages = Join-Path $destination 'packages'
$wheelhouse = Join-Path $destination 'wheelhouse'
$runtime = Join-Path $payload 'runtime'
New-Item -ItemType Directory -Force $payload,$packages,$wheelhouse,$runtime | Out-Null
Push-Location $repo
try {
    & uv export --locked --no-dev --no-emit-project --format requirements-txt --output-file (Join-Path $packages 'locked-runtime.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Lock export failed' }
    & uv build --out-dir $packages
    if ($LASTEXITCODE -ne 0) { throw 'Package build failed' }
    & $python -I -X utf8 -m pip download --require-hashes --only-binary=:all: --platform win_amd64 --python-version 3.13 --implementation cp --dest $wheelhouse -r (Join-Path $packages 'locked-runtime.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency download failed' }
    Expand-Archive -LiteralPath (Join-Path $DownloadCache $pins.python.filename) -DestinationPath $runtime
    $site = Join-Path $runtime 'Lib/site-packages'
    & $python -I -X utf8 -m pip install --no-index --find-links $wheelhouse --require-hashes --no-compile --only-binary=:all: --platform win_amd64 --python-version 3.13 --implementation cp --target $site -r (Join-Path $packages 'locked-runtime.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Offline dependency assembly failed' }
    $wheel = Join-Path $packages ("cadence_mcp_bridge-" + $version + '-py3-none-any.whl')
    & $python -I -X utf8 -m pip install --no-index --no-deps --no-compile --target $site $wheel
    if ($LASTEXITCODE -ne 0) { throw 'Bridge assembly failed' }
    & $python -I -X utf8 (Join-Path $PSScriptRoot 'sanitize_payload.py') --site $site
    if ($LASTEXITCODE -ne 0) { throw 'Build-origin sanitization failed' }
    [IO.File]::WriteAllText((Join-Path $runtime 'python313._pth'), "python313.zip`n.`nLib/site-packages`nimport site`n", [Text.UTF8Encoding]::new($false))
    $csc = Join-Path $env:SystemRoot 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    & $csc /nologo /target:exe /platform:x64 /optimize+ /reference:System.Web.Extensions.dll ("/out:" + (Join-Path $payload 'CadenceMCPBridge.exe')) (Join-Path $PSScriptRoot 'Launcher.cs') (Join-Path $PSScriptRoot 'PayloadGuard.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed' }
    & $csc /nologo /target:winexe /platform:x64 /optimize+ /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll ("/out:" + (Join-Path $payload 'CadenceMCPBridgeSetup.exe')) (Join-Path $PSScriptRoot 'SetupGui.cs') (Join-Path $PSScriptRoot 'PayloadGuard.cs')
    if ($LASTEXITCODE -ne 0) { throw 'GUI build failed' }
    Copy-Item -LiteralPath (Join-Path $repo 'LICENSE'),(Join-Path $repo 'NOTICE'),(Join-Path $repo 'THIRD_PARTY_NOTICES.md'),(Join-Path $PSScriptRoot 'INSTALL.md') -Destination $payload
    & $python -I -X utf8 (Join-Path $PSScriptRoot 'manifest.py') --root $payload --repository $repo --inputs (Join-Path $PSScriptRoot 'inputs.lock.json') --version $version
    if ($LASTEXITCODE -ne 0) { throw 'Manifest generation failed' }
    & (Join-Path $runtime 'python.exe') -I -B -X utf8 -m cadence_mcp_bridge.windows_host.verify
    if ($LASTEXITCODE -ne 0) { throw 'Embedded runtime verification failed' }
    & $InnoCompiler ("/DPayload=" + $payload) ("/DOutput=" + $destination) ("/DAppVersion=" + $version) (Join-Path $PSScriptRoot 'installer.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Windows installer compile failed' }
    $hashLines = @(Get-ChildItem -LiteralPath $destination -File | Where-Object Extension -eq '.exe' | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant() + '  ' + $_.Name })
    $hashLines += @(Get-ChildItem -LiteralPath $packages -File | Where-Object Name -ne '.gitignore' | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant() + '  packages/' + $_.Name })
    $hashLines += @(Get-ChildItem -LiteralPath $payload -File | Where-Object Name -in @('INSTALL-MANIFEST.json','DEPENDENCY-LICENSES.json') | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant() + '  payload/' + $_.Name })
    [IO.File]::WriteAllLines((Join-Path $destination 'SHA256SUMS'), $hashLines, [Text.UTF8Encoding]::new($false))
    foreach ($line in [IO.File]::ReadAllLines((Join-Path $destination 'SHA256SUMS'))) {
        if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw 'Malformed checksum line' }
        if ((Get-FileHash -LiteralPath (Join-Path $destination $Matches[2])).Hash.ToLowerInvariant() -ne $Matches[1]) { throw 'Checksum inventory mismatch' }
    }
    Write-Output "WINDOWS_INSTALLER_BUILT: $destination"
} finally { Pop-Location }
