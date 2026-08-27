[CmdletBinding()]
param(
    [string]$Owner = "Phjrab",
    [string]$Repository = "cadence-mcp-bridge",
    [string]$Destination = "C:\work\cadence-mcp-bridge",
    [string]$FeatureBranch = "wp/WP-00-bootstrap"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-Command {
    param([Parameter(Mandatory)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found."
    }
}

Assert-Command git
Assert-Command gh

gh auth status
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated. Run 'gh auth login' interactively and rerun this script."
}

$repoFullName = "$Owner/$Repository"
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

& gh repo view $repoFullName --json nameWithOwner,isPrivate,url,defaultBranchRef *> $null
$repoExists = ($LASTEXITCODE -eq 0)

if (-not $repoExists) {
    gh repo create $repoFullName --private --add-readme
    if ($LASTEXITCODE -ne 0) {
        throw "Private GitHub repository creation failed."
    }
}

$repoInfo = gh repo view $repoFullName --json nameWithOwner,isPrivate,url,defaultBranchRef | ConvertFrom-Json
if (-not $repoInfo.isPrivate) {
    throw "Repository exists but is not private. Refusing to continue."
}
if ($repoInfo.defaultBranchRef.name -ne "main") {
    throw "Default branch is '$($repoInfo.defaultBranchRef.name)', expected 'main'."
}

if (Test-Path $Destination) {
    $items = Get-ChildItem -Force $Destination -ErrorAction SilentlyContinue
    if ($items) {
        throw "Destination is not empty: $Destination"
    }
} else {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
}

# Clone the GitHub-created main branch. The agent never writes directly to main.
gh repo clone $repoFullName $Destination
if ($LASTEXITCODE -ne 0) {
    throw "Repository clone failed."
}

Set-Location $Destination
git switch -c $FeatureBranch
if ($LASTEXITCODE -ne 0) {
    throw "Feature branch creation failed."
}

# Copy the prepared starter files into the feature branch checkout.
Get-ChildItem -Force $sourceRoot | Where-Object { $_.Name -ne '.git' } | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $Destination -Recurse -Force
}

git add --all
$pending = git status --porcelain
if (-not $pending) {
    throw "No project files were staged for WP-00."
}

git diff --cached --check
if ($LASTEXITCODE -ne 0) {
    throw "git diff --cached --check failed."
}

git commit -m "chore(bootstrap): initialize private Cadence MCP bridge project"
if ($LASTEXITCODE -ne 0) {
    throw "WP-00 commit failed."
}

git push -u origin $FeatureBranch
if ($LASTEXITCODE -ne 0) {
    throw "Feature branch push failed."
}

$head = git rev-parse HEAD
$base = git rev-parse origin/main
$dirty = git status --porcelain
if ($dirty) {
    throw "Working tree is not clean after push.`n$dirty"
}

Write-Host "Private repository verified: $repoFullName"
Write-Host "Base origin/main: $base"
Write-Host "Pushed feature branch: $FeatureBranch"
Write-Host "Feature commit: $head"
Write-Host "STOP: do not merge or start WP-01 in this run."
