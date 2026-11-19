# Installs Kokoro-FastAPI natively on Windows. Run in PowerShell.
$ErrorActionPreference = "Stop"
$dir = if ($env:KOKORO_DIR) { $env:KOKORO_DIR } else { "$HOME\Kokoro-FastAPI" }

winget install -e --id astral-sh.uv
winget install -e --id eSpeak-NG.eSpeak-NG
winget install -e --id Git.Git
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")

if (Test-Path "$dir\.git") { git -C $dir pull --ff-only }
else { git clone https://github.com/remsky/Kokoro-FastAPI.git $dir }

$script = if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { "start-gpu.ps1" } else { "start-cpu.ps1" }
Write-Host "Using $script (first run downloads the model)"
Set-Location $dir
& ".\$script"
