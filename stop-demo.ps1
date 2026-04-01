# ============================================================
# Copilot+ PC -- NPU Demo Shutdown
# Cleanly stops all services
# ============================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Copilot+ PC - NPU Demo Shutdown" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# --- Stop Flask App ---
Write-Host "Stopping Flask app..." -ForegroundColor Yellow
# Check for standalone exe first, then Python
$exeProcs = Get-Process -Name "npu-demo" -ErrorAction SilentlyContinue
$flaskProcs = Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    try {
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
        $cmdLine -match "npu_demo_flask"
    } catch { $false }
}

if ($exeProcs) {
    $exeProcs | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] Flask app stopped (exe)" -ForegroundColor Green
} elseif ($flaskProcs) {
    $flaskProcs | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] Flask app stopped (python)" -ForegroundColor Green
} else {
    Write-Host "  [--] Flask app was not running" -ForegroundColor Gray
}

# --- Stop Vision Service ---
Write-Host "Stopping Vision Service..." -ForegroundColor Yellow
$visionProcs = Get-Process -Name "vision-service" -ErrorAction SilentlyContinue
if ($visionProcs) {
    $visionProcs | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] Vision Service stopped" -ForegroundColor Green
} else {
    Write-Host "  [--] Vision Service was not running" -ForegroundColor Gray
}

# --- Stop Foundry Local ---
Write-Host "Stopping Foundry Local..." -ForegroundColor Yellow
try {
    $status = foundry service status 2>&1
    if ($status -match "running") {
        foundry service stop 2>&1 | Out-Null
        Write-Host "  [OK] Foundry Local stopped" -ForegroundColor Green
    } else {
        Write-Host "  [--] Foundry Local was not running" -ForegroundColor Gray
    }
} catch {
    Write-Host "  [--] Foundry Local was not running" -ForegroundColor Gray
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  All services stopped" -ForegroundColor Cyan
Write-Host "  To restart: .\start-demo.ps1" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
