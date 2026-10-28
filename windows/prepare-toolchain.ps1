param([Parameter(Mandatory=$true)][string]$Cache, [Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$pins = Get-Content (Join-Path $PSScriptRoot 'inputs.lock.json') -Raw | ConvertFrom-Json
if (Test-Path -LiteralPath $Destination) { throw 'Use a new compiler destination' }
New-Item -ItemType Directory -Force $Cache | Out-Null
$file = Join-Path $Cache $pins.inno.filename
if (-not (Test-Path -LiteralPath $file)) { Invoke-WebRequest -Uri $pins.inno.url -OutFile $file }
if ((Get-FileHash -LiteralPath $file).Hash.ToLowerInvariant() -ne $pins.inno.sha256) { throw 'Pinned compiler installer mismatch' }
if ((Get-AuthenticodeSignature -LiteralPath $file).Status -ne 'Valid') { throw 'Compiler publisher signature unavailable' }
$p = Start-Process -FilePath $file -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS',('/DIR="'+[IO.Path]::GetFullPath($Destination)+'"')) -WindowStyle Hidden -PassThru -Wait
if ($p.ExitCode -ne 0) { throw 'Compiler setup failed' }
