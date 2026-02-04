# ============================================================
# Surface Copilot+ PC — NPU Demo Setup Script
# ============================================================
# Run as Administrator in PowerShell
# ============================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Surface Copilot+ PC - NPU Demo Setup" -ForegroundColor Cyan
Write-Host "  Powered by Foundry Local + Phi-4 Mini" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "!! Please run this script as Administrator!" -ForegroundColor Yellow
    Write-Host "   Right-click PowerShell -> Run as Administrator" -ForegroundColor Yellow
    exit 1
}

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Working directory: $ScriptDir" -ForegroundColor Gray
Write-Host ""

# ============================================================
# Step 1: Check/Install Python
# ============================================================
Write-Host "Step 1: Checking Python installation..." -ForegroundColor Yellow

$pythonInstalled = $false
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python 3") {
        Write-Host "[OK] Python already installed: $pythonVersion" -ForegroundColor Green
        $pythonInstalled = $true
    }
} catch {
    $pythonInstalled = $false
}

if (-not $pythonInstalled) {
    Write-Host "Downloading Python ARM64..." -ForegroundColor Cyan
    $pythonUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-arm64.exe"
    $pythonInstaller = "$env:TEMP\python-arm64.exe"

    try {
        Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonInstaller -UseBasicParsing
        Write-Host "Installing Python (this may take a minute)..." -ForegroundColor Cyan
        Write-Host "   CHECK 'Add Python to PATH' in the installer!" -ForegroundColor Yellow
        Start-Process $pythonInstaller -ArgumentList "/passive", "InstallAllUsers=1", "PrependPath=1" -Wait
        Write-Host "[OK] Python installed" -ForegroundColor Green

        # Refresh PATH
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
    } catch {
        Write-Host "[FAIL] Failed to install Python. Please install manually from python.org" -ForegroundColor Red
        Write-Host "   Download ARM64 version: https://www.python.org/downloads/windows/" -ForegroundColor Yellow
    }
}

Write-Host ""

# ============================================================
# Step 2: Install Python Dependencies
# ============================================================
Write-Host "Step 2: Installing Python dependencies..." -ForegroundColor Yellow

$requirementsPath = Join-Path $ScriptDir "requirements.txt"

try {
    pip install -r $requirementsPath --break-system-packages 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Python dependencies installed" -ForegroundColor Green
    } else {
        Write-Host "   Trying individual package install..." -ForegroundColor Gray
        pip install flask openai pypdf python-docx foundry-local --break-system-packages
        Write-Host "[OK] Python dependencies installed" -ForegroundColor Green
    }
} catch {
    Write-Host "[WARN] Some packages may have failed. Try manually:" -ForegroundColor Yellow
    Write-Host "   pip install flask openai pypdf python-docx foundry-local" -ForegroundColor Cyan
}

Write-Host ""

# ============================================================
# Step 3: Verify demo files exist
# ============================================================
Write-Host "Step 3: Verifying demo files..." -ForegroundColor Yellow

$requiredFiles = @(
    "npu_demo_flask.py",
    "surface-logo.png",
    "copilot-logo.avif"
)

$missingFiles = @()
foreach ($file in $requiredFiles) {
    $filePath = Join-Path $ScriptDir $file
    if (Test-Path $filePath) {
        Write-Host "[OK] $file" -ForegroundColor Green
    } else {
        Write-Host "[MISSING] $file" -ForegroundColor Red
        $missingFiles += $file
    }
}

# Check tesseract directory
$tesseractDir = Join-Path $ScriptDir "tesseract"
if (Test-Path $tesseractDir) {
    Write-Host "[OK] tesseract/ (offline OCR)" -ForegroundColor Green
} else {
    Write-Host "[WARN] tesseract/ not found (ID Verification tab will need online OCR)" -ForegroundColor Yellow
}

Write-Host ""

# ============================================================
# Step 4: Setup demo data
# ============================================================
Write-Host "Step 4: Setting up demo data..." -ForegroundColor Yellow

$demoDir = Join-Path $env:USERPROFILE "Documents\Demo"
$myDayDir = Join-Path $demoDir "My_Day"
$inboxDir = Join-Path $myDayDir "Inbox"

if (Test-Path $myDayDir) {
    Write-Host "[OK] Demo data directory exists: $myDayDir" -ForegroundColor Green
} else {
    Write-Host "[INFO] Creating demo data directory: $myDayDir" -ForegroundColor Cyan
    New-Item -Path $inboxDir -ItemType Directory -Force | Out-Null
    Write-Host "[OK] Demo data directory created" -ForegroundColor Green
    Write-Host "[WARN] You'll need to copy demo data files (calendar.ics, tasks.csv, emails)" -ForegroundColor Yellow
}

Write-Host ""

# ============================================================
# Step 5: Test Foundry Local
# ============================================================
Write-Host "Step 5: Testing Foundry Local SDK..." -ForegroundColor Yellow

try {
    $testResult = python -c "from foundry_local import FoundryLocalManager; print('OK')" 2>&1
    if ($testResult -match "OK") {
        Write-Host "[OK] Foundry Local SDK installed" -ForegroundColor Green
        Write-Host "   The app will automatically download and start phi-4-mini on first run" -ForegroundColor Gray
    } else {
        Write-Host "[WARN] Foundry Local SDK test failed" -ForegroundColor Yellow
        Write-Host "   Try: pip install foundry-local" -ForegroundColor Cyan
    }
} catch {
    Write-Host "[WARN] Could not verify Foundry Local SDK" -ForegroundColor Yellow
    Write-Host "   Try: pip install foundry-local" -ForegroundColor Cyan
}

Write-Host ""

# ============================================================
# Summary
# ============================================================
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Setup Complete" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if ($missingFiles.Count -gt 0) {
    Write-Host "[WARN] Missing files: $($missingFiles -join ', ')" -ForegroundColor Red
    Write-Host ""
}

Write-Host "To run the demo:" -ForegroundColor Green
Write-Host ""
Write-Host "   cd `"$ScriptDir`"" -ForegroundColor Cyan
Write-Host "   python npu_demo_flask.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Or double-click: run.bat" -ForegroundColor Cyan
Write-Host ""
Write-Host "Then open: http://localhost:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "No VS Code or AI Toolkit required!" -ForegroundColor Green
Write-Host "Foundry Local handles model download and runtime automatically." -ForegroundColor Gray
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
