<#
.SYNOPSIS
  Start llama-server in router mode with the presets from llamacpp/model.ini.
.DESCRIPTION
  Reads paths from config/local-ai.json (copy config/local-ai.example.json first; parameters override).
  models_max controls how many presets stay loaded at once (1 for a single consumer GPU). Clients pick a
  preset by sending its section name in the "model" field. Per-model context, KV quant, sampling and
  thinking live in llamacpp/model.ini (copy llamacpp/model.ini.example).
.EXAMPLE
  .\run-llama-server.ps1
  .\run-llama-server.ps1 -Port 8081 -ModelsMax 2
#>
param(
    [string]$Config = (Join-Path $PSScriptRoot "..\config\local-ai.json"),
    [string]$LlamaCppDir,
    [int]$Port,
    [int]$ModelsMax,
    [string]$Preset = (Join-Path $PSScriptRoot "model.ini"),
    [switch]$NoPause
)
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
Write-Host "llama-server router: presets=$Preset port=$Port models-max=$ModelsMax" -ForegroundColor Cyan
Push-Location $LlamaCppDir
try {
    & $exe --models-preset $Preset --models-max $ModelsMax --host 127.0.0.1 --port $Port --parallel 1 --no-mmproj
} finally {
    Pop-Location
    if (-not $NoPause) { Read-Host "llama-server exited. Press Enter to close" | Out-Null }
}
