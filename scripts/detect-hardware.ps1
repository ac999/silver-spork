<#
.SYNOPSIS
  Detect the hardware facts needed to configure this framework and print sizing guidance.
.DESCRIPTION
  Reports GPU(s) (name, VRAM, driver), CPU (physical cores -> `threads`), RAM, free disk per drive,
  the Python launcher, and the llama.cpp version if config/local-ai.json already points to it.
  Then prints rules of thumb: the largest GGUF that fits fully in VRAM at your context size, and
  mixture-of-experts offload guidance. Nothing is written. Use -Json for machine-readable output (AI agents).
.EXAMPLE
  pwsh -File scripts/detect-hardware.ps1
  pwsh -File scripts/detect-hardware.ps1 -Json | ConvertFrom-Json
  pwsh -File scripts/detect-hardware.ps1 -ContextTokens 65536
#>
param(
    [switch]$Json,
    [int]$ContextTokens = 32768,
    [string]$Config = (Join-Path $PSScriptRoot "..\config\local-ai.json")
)
$ErrorActionPreference = "SilentlyContinue"
$info = [ordered]@{}

# ---- GPU -------------------------------------------------------------------
$gpus = @()
if (Get-Command nvidia-smi) {
    nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv,noheader,nounits | ForEach-Object {
        $p = $_ -split ",\s*"
        $gpus += [ordered]@{ name = $p[0]; vram_total_mib = [int]$p[1]; vram_free_mib = [int]$p[2]; driver = $p[3]; backend = "CUDA" }
    }
} else {
    Get-CimInstance Win32_VideoController | Where-Object { $_.AdapterRAM -gt 0 } | ForEach-Object {
        $gpus += [ordered]@{ name = $_.Name; vram_total_mib = [int]($_.AdapterRAM / 1MB); vram_free_mib = $null; driver = $_.DriverVersion; backend = "unknown (no nvidia-smi; use a ROCm or Vulkan llama.cpp build)" }
    }
}
$info.gpus = $gpus

# ---- CPU / RAM -------------------------------------------------------------
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$info.cpu = [ordered]@{ name = $cpu.Name.Trim(); physical_cores = [int]$cpu.NumberOfCores; logical_threads = [int]$cpu.NumberOfLogicalProcessors }
$info.ram_gb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)

# ---- Disks -----------------------------------------------------------------
$info.drives = @(Get-PSDrive -PSProvider FileSystem | Where-Object { $null -ne $_.Free } | ForEach-Object {
    [ordered]@{ drive = $_.Name; free_gb = [math]::Round($_.Free / 1GB, 1); used_gb = [math]::Round($_.Used / 1GB, 1) } })

# ---- Tooling ---------------------------------------------------------------
$py = if (Get-Command py) { "py" } elseif (Get-Command python3) { "python3" } elseif (Get-Command python) { "python" } else { $null }
$info.python_cmd = $py
$info.node = (node --version)
$info.hf_cli = (hf --version 2>$null | Select-Object -Last 1)
$info.llamacpp_version = $null
if (Test-Path $Config) {
    $cfg = Get-Content $Config -Raw | ConvertFrom-Json
    $exe = Join-Path $cfg.llamacpp_dir "llama-server.exe"
    if (Test-Path $exe) { $info.llamacpp_version = (& $exe --version 2>&1 | Select-Object -First 1) -replace '^version: ', '' }
}

# ---- Guidance --------------------------------------------------------------
$vram = if ($gpus.Count) { $gpus[0].vram_total_mib / 1024 } else { 0 }
$kvGuess = [math]::Round(1.5 * ($ContextTokens / 32768), 1)   # q8_0 KV cache, typical 7-9B dense model; hybrid-attention models need less
$maxFile = [math]::Round($vram - 1.0 - $kvGuess, 1)
$info.guidance = [ordered]@{
    threads                  = $info.cpu.physical_cores
    context_tokens           = $ContextTokens
    kv_cache_q8_estimate_gb  = $kvGuess
    max_gguf_fully_on_gpu_gb = $maxFile
    notes = @(
        "VRAM budget = GGUF size + KV cache (q8_0, about $kvGuess GB at $ContextTokens tokens for a 7-9B dense model) + about 1 GB overhead.",
        "Largest GGUF to run fully on this GPU at that context: about $maxFile GB. Verify with scripts/benchmark.ps1.",
        "Mixture-of-experts models larger than VRAM: attention on GPU, experts in RAM via n-cpu-moe; needs file size + about 4 GB of free RAM ($($info.ram_gb) GB installed).",
        "Weights: Q4_K_M or better for tool calling, Q5/Q6 if it fits. KV cache: never below q8_0.",
        "threads = physical cores ($($info.cpu.physical_cores)), not logical threads."
    )
}

if ($Json) { $info | ConvertTo-Json -Depth 5; exit 0 }

Write-Host "GPU(s):" -ForegroundColor Cyan
foreach ($g in $gpus) {
    $free = if ($g.vram_free_mib) { "{0:N1} GB free" -f ($g.vram_free_mib / 1024) } else { "free: ?" }
    Write-Host ("  {0}  VRAM {1:N1} GB ({2})  driver {3}  backend {4}" -f $g.name, ($g.vram_total_mib / 1024), $free, $g.driver, $g.backend)
}
Write-Host ("CPU: {0}  physical cores {1}  logical threads {2}" -f $info.cpu.name, $info.cpu.physical_cores, $info.cpu.logical_threads) -ForegroundColor Cyan
Write-Host ("RAM: {0} GB" -f $info.ram_gb) -ForegroundColor Cyan
Write-Host "Drives:" -ForegroundColor Cyan
foreach ($d in $info.drives) { Write-Host ("  {0}:  {1} GB free" -f $d.drive, $d.free_gb) }
Write-Host ("Tooling: python_cmd={0}  node={1}  hf={2}  llama.cpp={3}" -f $py, $info.node, $info.hf_cli, $info.llamacpp_version) -ForegroundColor Cyan
Write-Host "`nGuidance for config/local-ai.json and llamacpp/model.ini:" -ForegroundColor Green
foreach ($n in $info.guidance.notes) { Write-Host "  - $n" }
