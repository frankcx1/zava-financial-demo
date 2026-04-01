# ============================================================
# Copilot+ PC - NPU Demo Launcher
# Starts all services and opens the browser
# ============================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Copilot+ PC - NPU Demo Launcher" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Start Foundry Local ---
Write-Host "[1/4] Starting Foundry Local..." -ForegroundColor Yellow
$foundryRunning = $false
try {
    $status = foundry service status 2>&1
    if ($status -match "running") {
        Write-Host "  [OK] Foundry Local already running" -ForegroundColor Green
        $foundryRunning = $true
    }
} catch { }

if (-not $foundryRunning) {
    try {
        foundry service start 2>&1 | Out-Null
        $retries = 0
        while ($retries -lt 15) {
            Start-Sleep -Seconds 1
            $retries++
            try {
                $check = foundry service status 2>&1
                if ($check -match "running") {
                    $foundryRunning = $true
                    break
                }
            } catch { }
        }
        if ($foundryRunning) {
            Write-Host "  [OK] Foundry Local started" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] Foundry Local may not be ready yet" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  [FAIL] Could not start Foundry Local" -ForegroundColor Red
        Write-Host "  Try: winget install Microsoft.FoundryLocal" -ForegroundColor Yellow
    }
}

# --- Step 2: Start Vision Service ---
Write-Host "[2/4] Starting Vision Service (Phi Silica)..." -ForegroundColor Yellow
$visionRunning = $false
try {
    $visionCheck = Invoke-RestMethod -Uri "http://127.0.0.1:5100/health" -TimeoutSec 3 -ErrorAction Stop
    if ($visionCheck.status -eq "ok") {
        Write-Host "  [OK] Vision Service already running" -ForegroundColor Green
        $visionRunning = $true
    }
} catch { }

if (-not $visionRunning) {
    $launchScript = Join-Path $ScriptDir "vision-service\scripts\launch-vision.ps1"
    $launchScriptAlt = "C:\temp\launch-vision.ps1"

    $scriptToRun = $null
    if (Test-Path $launchScript) {
        $scriptToRun = $launchScript
    }
    elseif (Test-Path $launchScriptAlt) {
        $scriptToRun = $launchScriptAlt
    }

    if ($scriptToRun) {
        try {
            Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$scriptToRun`"" -WindowStyle Hidden
            $retries = 0
            while ($retries -lt 20) {
                Start-Sleep -Seconds 1
                $retries++
                try {
                    $vCheck = Invoke-RestMethod -Uri "http://127.0.0.1:5100/health" -TimeoutSec 2 -ErrorAction Stop
                    if ($vCheck.status -eq "ok") {
                        $visionRunning = $true
                        break
                    }
                } catch { }
            }
            if ($visionRunning) {
                Write-Host "  [OK] Vision Service started" -ForegroundColor Green
            } else {
                Write-Host "  [WARN] Vision Service launched but not responding yet" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "  [WARN] Could not launch Vision Service" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [SKIP] Vision Service launch script not found" -ForegroundColor Gray
        Write-Host "  Field Inspection vision features will use text fallback" -ForegroundColor Gray
    }
}

# --- Step 3: Start Flask App ---
Write-Host "[3/4] Starting Flask app..." -ForegroundColor Yellow
$flaskRunning = $false
try {
    $flaskCheck = Invoke-RestMethod -Uri "http://127.0.0.1:5000/health" -TimeoutSec 3 -ErrorAction Stop
    if ($flaskCheck.ready -eq $true) {
        Write-Host "  [OK] Flask app already running" -ForegroundColor Green
        $flaskRunning = $true
    }
} catch { }

if (-not $flaskRunning) {
    # Find the exe: check app/ (kit layout) then dist/npu-demo/ (dev layout)
    $exePath = Join-Path $ScriptDir "app\npu-demo.exe"
    if (-not (Test-Path $exePath)) {
        $exePath = Join-Path $ScriptDir "dist\npu-demo\npu-demo.exe"
    }
    $appPath = Join-Path $ScriptDir "npu_demo_flask.py"

    if (Test-Path $exePath) {
        Write-Host "  Using standalone exe: $exePath" -ForegroundColor Gray
        Start-Process $exePath -WorkingDirectory (Split-Path $exePath) -WindowStyle Minimized
    } else {
        # Clear stale bytecode
        $pycache = Join-Path $ScriptDir "__pycache__"
        if (Test-Path $pycache) {
            Remove-Item "$pycache\npu_demo_flask.cpython-*.pyc" -Force -ErrorAction SilentlyContinue
        }
        Start-Process python -ArgumentList "`"$appPath`"" -WorkingDirectory $ScriptDir -WindowStyle Minimized
    }

    # Wait for model warmup + Flask to respond
    Write-Host "  Warming up model (this may take 10-20 seconds on first run)..." -ForegroundColor Gray
    $retries = 0
    while ($retries -lt 30) {
        Start-Sleep -Seconds 1
        $retries++
        try {
            $fCheck = Invoke-RestMethod -Uri "http://127.0.0.1:5000/health" -TimeoutSec 2 -ErrorAction Stop
            if ($fCheck.ready -eq $true) {
                $flaskRunning = $true
                break
            }
        } catch { }
    }
    if ($flaskRunning) {
        Write-Host "  [OK] Flask app started (model: $($fCheck.model))" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Flask app launched but not responding yet" -ForegroundColor Yellow
    }
}

# --- Step 4: Open Browser ---
Write-Host "[4/4] Opening browser..." -ForegroundColor Yellow
if ($flaskRunning) {
    Start-Process "http://localhost:5000"
    Write-Host "  [OK] Browser opened to http://localhost:5000" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] Open http://localhost:5000 manually when ready" -ForegroundColor Yellow
}

# --- Summary ---
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Service Status" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if ($foundryRunning) { Write-Host "  [OK] Foundry Local (NPU inference)" -ForegroundColor Green }
else { Write-Host "  [--] Foundry Local (NPU inference)" -ForegroundColor Yellow }

if ($visionRunning) { Write-Host "  [OK] Vision Service (Phi Silica, localhost:5100)" -ForegroundColor Green }
else { Write-Host "  [--] Vision Service (Phi Silica, localhost:5100)" -ForegroundColor Yellow }

if ($flaskRunning) { Write-Host "  [OK] Flask App (localhost:5000)" -ForegroundColor Green }
else { Write-Host "  [--] Flask App (localhost:5000)" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  To stop all services: .\stop-demo.ps1" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
