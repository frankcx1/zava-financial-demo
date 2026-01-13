# ============================================================
# Surface Copilot+ PC — NPU Demo Setup Script
# ============================================================
# Run as Administrator in PowerShell
# ============================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Surface Copilot+ PC — NPU Demo Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "⚠️  Please run this script as Administrator!" -ForegroundColor Yellow
    Write-Host "   Right-click PowerShell → Run as Administrator" -ForegroundColor Yellow
    exit 1
}

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "📁 Working directory: $ScriptDir" -ForegroundColor Gray
Write-Host ""

# ============================================================
# Step 1: Check/Install Python
# ============================================================
Write-Host "Step 1: Checking Python installation..." -ForegroundColor Yellow

$pythonInstalled = $false
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python 3") {
        Write-Host "✓ Python already installed: $pythonVersion" -ForegroundColor Green
        $pythonInstalled = $true
    }
} catch {
    $pythonInstalled = $false
}

if (-not $pythonInstalled) {
    Write-Host "📥 Downloading Python ARM64..." -ForegroundColor Cyan
    $pythonUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-arm64.exe"
    $pythonInstaller = "$env:TEMP\python-arm64.exe"
    
    try {
        Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonInstaller -UseBasicParsing
        Write-Host "📦 Installing Python (this may take a minute)..." -ForegroundColor Cyan
        Write-Host "   ⚠️  CHECK 'Add Python to PATH' in the installer!" -ForegroundColor Yellow
        Start-Process $pythonInstaller -ArgumentList "/passive", "InstallAllUsers=1", "PrependPath=1" -Wait
        Write-Host "✓ Python installed" -ForegroundColor Green
        
        # Refresh PATH
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
    } catch {
        Write-Host "✗ Failed to install Python. Please install manually from python.org" -ForegroundColor Red
        Write-Host "   Download ARM64 version: https://www.python.org/downloads/windows/" -ForegroundColor Yellow
    }
}

Write-Host ""

# ============================================================
# Step 2: Check/Install VS Code
# ============================================================
Write-Host "Step 2: Checking VS Code installation..." -ForegroundColor Yellow

$vscodeInstalled = $false
$vscodePaths = @(
    "$env:LOCALAPPDATA\Programs\Microsoft VS Code\Code.exe",
    "$env:ProgramFiles\Microsoft VS Code\Code.exe",
    "${env:ProgramFiles(x86)}\Microsoft VS Code\Code.exe"
)

foreach ($path in $vscodePaths) {
    if (Test-Path $path) {
        Write-Host "✓ VS Code found: $path" -ForegroundColor Green
        $vscodeInstalled = $true
        break
    }
}

if (-not $vscodeInstalled) {
    Write-Host "📥 Installing VS Code via winget..." -ForegroundColor Cyan
    try {
        winget install Microsoft.VisualStudioCode --accept-source-agreements --accept-package-agreements
        Write-Host "✓ VS Code installed" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  Could not auto-install VS Code. Please install manually:" -ForegroundColor Yellow
        Write-Host "   https://code.visualstudio.com/" -ForegroundColor Cyan
    }
}

Write-Host ""

# ============================================================
# Step 3: Install Python Dependencies
# ============================================================
Write-Host "Step 3: Installing Python dependencies..." -ForegroundColor Yellow

# Create requirements.txt if not exists
$requirementsPath = Join-Path $ScriptDir "requirements.txt"
if (-not (Test-Path $requirementsPath)) {
    @"
flask>=3.0.0
openai>=1.0.0
pypdf>=4.0.0
python-docx>=1.0.0
"@ | Out-File -FilePath $requirementsPath -Encoding UTF8
}

try {
    # Try pip install
    $pipResult = pip install -r $requirementsPath --break-system-packages 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Python dependencies installed" -ForegroundColor Green
    } else {
        # Fallback: install individually
        Write-Host "   Trying individual package install..." -ForegroundColor Gray
        pip install flask openai pypdf python-docx --break-system-packages
        Write-Host "✓ Python dependencies installed" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠️  Some packages may have failed. Try manually:" -ForegroundColor Yellow
    Write-Host "   pip install flask openai pypdf python-docx --break-system-packages" -ForegroundColor Cyan
}

Write-Host ""

# ============================================================
# Step 4: Verify files exist
# ============================================================
Write-Host "Step 4: Verifying demo files..." -ForegroundColor Yellow

$requiredFiles = @(
    "npu_demo_flask.py",
    "surface-logo.png",
    "copilot-logo.avif"
)

$missingFiles = @()
foreach ($file in $requiredFiles) {
    $filePath = Join-Path $ScriptDir $file
    if (Test-Path $filePath) {
        Write-Host "✓ $file" -ForegroundColor Green
    } else {
        Write-Host "✗ $file (MISSING)" -ForegroundColor Red
        $missingFiles += $file
    }
}

# Optional file
$samplePdf = Join-Path $ScriptDir "Enterprise_AI_Strategy_2026.pdf"
if (Test-Path $samplePdf) {
    Write-Host "✓ Enterprise_AI_Strategy_2026.pdf (sample doc)" -ForegroundColor Green
} else {
    Write-Host "○ Enterprise_AI_Strategy_2026.pdf (optional sample)" -ForegroundColor Gray
}

Write-Host ""

# ============================================================
# Step 5: Check Foundry Local
# ============================================================
Write-Host "Step 5: Checking Foundry Local / AI Toolkit..." -ForegroundColor Yellow

try {
    $models = Invoke-RestMethod -Uri "http://localhost:5272/v1/models" -TimeoutSec 5
    Write-Host "✓ Foundry Local is running" -ForegroundColor Green
    
    $modelList = $models.data | ForEach-Object { $_.id }
    Write-Host "  Available models: $($modelList -join ', ')" -ForegroundColor Gray
    
    if ($modelList -contains "phi-silica") {
        Write-Host "✓ Phi Silica is available" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Phi Silica not found. Please activate it in AI Toolkit." -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  Foundry Local not responding" -ForegroundColor Yellow
    Write-Host "   Please complete the manual AI Toolkit setup (see README)" -ForegroundColor Yellow
}

Write-Host ""

# ============================================================
# Summary & Next Steps
# ============================================================
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Setup Summary" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if ($missingFiles.Count -gt 0) {
    Write-Host "⚠️  Missing files: $($missingFiles -join ', ')" -ForegroundColor Red
    Write-Host ""
}

Write-Host "📋 MANUAL STEPS REQUIRED:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Open VS Code" -ForegroundColor White
Write-Host "2. Install 'AI Toolkit' extension (Ctrl+Shift+X, search 'AI Toolkit')" -ForegroundColor White
Write-Host "3. Click AI Toolkit icon → Local Models → Windows AI API" -ForegroundColor White
Write-Host "4. Click 'Add' next to Phi Silica" -ForegroundColor White
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Once AI Toolkit is configured, run the demo:" -ForegroundColor Green
Write-Host ""
Write-Host "   cd `"$ScriptDir`"" -ForegroundColor Cyan
Write-Host "   python npu_demo_flask.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "Then open: http://localhost:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
