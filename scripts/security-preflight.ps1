[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $projectRoot
try {
    $candidateFiles = @(& git ls-files --cached --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to enumerate tracked files."
    }

    $forbiddenNames = @(".pem", ".key", ".p12", ".pfx", "id_rsa", "id_ed25519")
    foreach ($path in $candidateFiles) {
        $leaf = [IO.Path]::GetFileName($path)
        $extension = [IO.Path]::GetExtension($path)
        if ($forbiddenNames -contains $leaf -or $forbiddenNames -contains $extension) {
            throw "Secret preflight rejected a credential-like tracked filename: $path"
        }
    }

    $patterns = @(
        '-----BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY-----',
        '\bgh[pousr]_[A-Za-z0-9]{20,}\b',
        '\bgithub_pat_[A-Za-z0-9_]{20,}\b',
        '(?i)\b(?:CDS_LIC_FILE|LM_LICENSE_FILE)\s*=\s*["'']?\d{2,6}@',
        '(?i)\b(?:CDS_LIC_FILE|LM_LICENSE_FILE)\s*=\s*["'']?(?:[A-Z]:\\|/)'
    )
    foreach ($path in $candidateFiles) {
        $fullPath = Join-Path $projectRoot $path
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            continue
        }
        foreach ($pattern in $patterns) {
            $match = Select-String -LiteralPath $fullPath -Pattern $pattern -AllMatches
            if ($match) {
                throw "Secret preflight found a forbidden value in $path."
            }
        }
    }
    Write-Output "Secret preflight passed for $($candidateFiles.Count) repository files."
}
finally {
    Pop-Location
}
