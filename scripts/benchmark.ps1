<#
.SYNOPSIS
  Benchmark every GGUF in your Hugging Face cache with llama-bench (dense: full GPU offload; MoE: n-cpu-moe sweep).
.DESCRIPTION
  Paths and thread count come from config/local-ai.json (copy config/local-ai.example.json first); parameters override.
  Hardware is detected and written into the log header. Appends UTF-8 markdown tables to the results file.
  Dense models run -ngl 99 with q8_0 KV cache, pp512/tg128 plus an agent-sized pp4096/tg64.
  MoE models (A3B/A4B in the file name) sweep --n-cpu-moe: lower = more experts on GPU = faster until VRAM overflows.
.EXAMPLE
  ./benchmark.ps1                                   # everything in the cache
  ./benchmark.ps1 -Filter <model-name> -Reps 2
  ./benchmark.ps1 -Filter <moe-model-name> -MoeSweep "20,24,28,32,36,40"
#>
param(
    [string]$Config = (Join-Path $PSScriptRoot "..\config\local-ai.json"),
    [string]$Filter = "",
    [string]$MoeSweep = "20,24,28,32,36",   # comma-separated; string so it works with pwsh -File
    [int]$Reps = 3,
    [string]$LogFile
)
if (-not (Test-Path $Config)) { throw "Missing $Config. Copy config/local-ai.example.json to config/local-ai.json and fill it in." }
$cfg = Get-Content $Config -Raw | ConvertFrom-Json
$CacheDir   = $cfg.hf_cache
$LlamaBench = Join-Path $cfg.llamacpp_dir "llama-bench.exe"
$Threads    = [string]$cfg.threads
if (-not $LogFile) { $LogFile = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".." $cfg.results_dir "benchmark_results.md")) }
$gpu = if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { (nvidia-smi --query-gpu=name,memory.total --format=csv,noheader) -join "; " } else { "GPU: unknown" }
$cpuInfo = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1
$Hardware = "$gpu | $($cpuInfo.Name.Trim()) ($($cpuInfo.NumberOfCores) cores) | RAM $([math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB)) GB"
$MoeSweepList = @($MoeSweep -split "[,; ]+" | Where-Object { $_ } | ForEach-Object { [int]$_ })
$Utf8       = New-Object System.Text.UTF8Encoding($false)

function Log([string]$Text) { [System.IO.File]::AppendAllText($LogFile, $Text + "`n", $Utf8) }

function Run-Bench([string]$Label, [string[]]$BenchArgs) {
    Write-Host "  $Label" -ForegroundColor Yellow
    $out = & $LlamaBench @BenchArgs -o md -r $Reps 2>&1 | ForEach-Object { "$_" }
    $rows = @()
    foreach ($line in $out) {
        if ($line -like "|*" -and $line -notlike "| model*" -and $line -notlike "| ---*") {
            $rows += $line
            Write-Host "    $line"
        }
    }
    if ($rows.Count -eq 0) {
        $err = ($out | Where-Object { $_ -match 'error|failed|out of memory|CUDA' } | Select-Object -First 2) -join ' / '
        Write-Host "    no result: $err" -ForegroundColor Red
    }
    return ,$rows
}

$Models = Get-ChildItem -Path $CacheDir -Recurse -Filter "*.gguf" |
          Where-Object { $_.Name -notmatch '^mmproj' -and ($Filter -eq "" -or $_.Name -like "*$Filter*") }
if ($Models.Count -eq 0) { Write-Host "No GGUF models found in $CacheDir" -ForegroundColor Red; exit 1 }

$ver = (& $LlamaBench --version 2>&1 | ForEach-Object { "$_" } | Select-Object -First 1) -replace '^version: ', ''
Log ""
Log "# Local LLM Benchmark Results - $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
Log "Host: $Hardware. llama.cpp $ver"
Log "Columns: pp = prompt processing t/s, tg = generation t/s. KV cache q8_0, flash attention on, $Reps repetitions."
Log ""

Write-Host "Found $($Models.Count) model(s)" -ForegroundColor Green
foreach ($Model in $Models) {
    $name = $Model.Name
    $sizeGB = [math]::Round($Model.Length / 1GB, 2)
    Write-Host "`n=== $name ($sizeGB GB) ===" -ForegroundColor Cyan
    Log "## $name ($sizeGB GiB)"
    $isMoe = $name -match 'A\dB'
    if ($isMoe) {
        Log "| model | size | params | backend | ngl | n_cpu_moe | type_k | type_v | fa | test | t/s |"
        Log "|---|---|---|---|---|---|---|---|---|---|---|"
    } else {
        Log "| model | size | params | backend | ngl | type_k | type_v | fa | test | t/s |"
        Log "|---|---|---|---|---|---|---|---|---|---|"
    }

    $common = @("-m", $Model.FullName, "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0", "-t", $Threads, "-b", "2048", "-ub", "512")

    if ($isMoe) {
        foreach ($ncmoe in $MoeSweepList) {
            $rows = Run-Bench "ngl=99 ncmoe=$ncmoe  pp512/tg128" ($common + @("-ngl", "99", "-ncmoe", "$ncmoe", "-p", "512", "-n", "128"))
            if ($rows.Count -eq 0) { Log "| $name | | | CUDA | 99 | $ncmoe | q8_0 | q8_0 | 1 | FAILED (OOM?) | |" } else { $rows | ForEach-Object { Log $_ } }
        }
    } else {
        $rows = Run-Bench "ngl=99  pp512/tg128" ($common + @("-ngl", "99", "-p", "512", "-n", "128"))
        if ($rows.Count -eq 0) { Log "| $name | | | CUDA | 99 | q8_0 | q8_0 | 1 | FAILED (OOM?) | |" } else { $rows | ForEach-Object { Log $_ } }
        $rows = Run-Bench "ngl=99  pp4096/tg64 (agent-sized prompt)" ($common + @("-ngl", "99", "-p", "4096", "-n", "64"))
        if ($rows.Count -eq 0) { Log "| $name | | | CUDA | 99 | q8_0 | q8_0 | 1 | FAILED pp4096 (OOM?) | |" } else { $rows | ForEach-Object { Log $_ } }
    }
    Log ""
}
Write-Host "`nDone. Results appended to $LogFile" -ForegroundColor Green
