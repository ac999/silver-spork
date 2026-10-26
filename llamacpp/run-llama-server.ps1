<#
.SYNOPSIS
  Start llama-server in router mode with the presets from llamacpp/model.ini.
.DESCRIPTION
  Reads paths from config/local-ai.json (copy config/local-ai.example.json first; parameters override).
  models_max controls how many presets stay loaded at once (1 for a single consumer GPU). Clients pick a
  preset by sending its section name in the "model" field. Per-model context, KV quant, sampling and
  thinking live in llamacpp/model.ini (copy llamacpp/model.ini.example).
  The router reads model.ini only at start. If a router already listens on the port, the new one cannot bind and
  the old one keeps serving the old presets: -Restart stops that llama-server first (any other program on the
  port is never touched).
.EXAMPLE
  .\run-llama-server.ps1
  .\run-llama-server.ps1 -Restart                   # pick up model.ini changes; good target for a desktop shortcut
  .\run-llama-server.ps1 -Port 8081 -ModelsMax 2
#>
param(
    [string]$Config = (Join-Path $PSScriptRoot "..\config\local-ai.json"),
    [string]$LlamaCppDir,
    [int]$Port,
    [int]$ModelsMax,
    [string]$Preset = (Join-Path $PSScriptRoot "model.ini"),
    [switch]$Restart,
    [switch]$NoPause
)
function Exit-Launcher([string]$Message) {
    Write-Host $Message -ForegroundColor Red
    if (-not $NoPause) { Read-Host "Press Enter to close" | Out-Null }
    exit 1
}
if (-not (Test-Path $Config)) { throw "Missing $Config. Copy config/local-ai.example.json to config/local-ai.json and fill it in." }
$cfg = Get-Content $Config -Raw | ConvertFrom-Json
if (-not $LlamaCppDir) { $LlamaCppDir = $cfg.llamacpp_dir }
if (-not $Port)        { $Port = $cfg.server_port }
if (-not $ModelsMax)   { $ModelsMax = $cfg.models_max }
$env:HF_HOME      = $cfg.hf_home
$env:HF_HUB_CACHE = $cfg.hf_cache

$exe = Join-Path $LlamaCppDir "llama-server.exe"
if (-not (Test-Path $Preset)) { throw "Missing $Preset. Copy llamacpp/model.ini.example to llamacpp/model.ini and define your presets." }
if (-not (Test-Path $exe)) { throw "llama-server.exe not found in $LlamaCppDir (check llamacpp_dir in config/local-ai.json)" }

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    if ($owner.ProcessName -ne "llama-server") {
        Exit-Launcher "Port $Port is used by $($owner.ProcessName) (PID $($listener.OwningProcess)). Free it or pass -Port."
    }
    if (-not $Restart) {
        Exit-Launcher ("A llama-server router (PID $($owner.Id), started $($owner.StartTime)) already listens on port $Port " +
                       "and keeps the presets it loaded then. Run with -Restart to replace it.")
    }
    Write-Host "Stopping the running router (PID $($owner.Id)) so the current model.ini is loaded..." -ForegroundColor Yellow
    Stop-Process -Id $owner.Id -Force   # its per-model child processes exit with it
    $owner.WaitForExit(15000) | Out-Null
}

Write-Host "llama-server router: presets=$Preset port=$Port models-max=$ModelsMax" -ForegroundColor Cyan
Push-Location $LlamaCppDir
try {
    & $exe --models-preset $Preset --models-max $ModelsMax --host 127.0.0.1 --port $Port --parallel 1 --no-mmproj
} finally {
    Pop-Location
    if (-not $NoPause) { Read-Host "llama-server exited. Press Enter to close" | Out-Null }
}
