# ============================================================
# Copilot+ PC — NPU Demo Setup Script
# Works on Intel Core Ultra (x64) and Qualcomm Snapdragon (ARM64)
# ============================================================
# Run in PowerShell (admin NOT required — all installs are user-scope)
# ============================================================

# --- Detect silicon ---
# NOTE: On Windows-on-ARM, OSArchitecture may report X64 when running
# under emulation. Use CPU name from WMI as the authoritative source.
$cpuName = (Get-CimInstance Win32_Processor).Name
$isARM = ($cpuName -match "Qualcomm|Snapdragon")

if ($isARM) {
    $silicon = "Qualcomm"
    $chipLabel = "Snapdragon X NPU"
    $modelAlias = "qwen2.5-7b"
    $modelLabel = "Qwen 2.5 7B"
} elseif ($cpuName -match "Intel") {
    $silicon = "Intel"
    $chipLabel = "Intel Core Ultra NPU"
    $modelAlias = "phi-4-mini"
    $modelLabel = "Phi-4 Mini"
} else {
    # Fallback: check OS architecture
    $osArch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    if ($osArch -eq [System.Runtime.InteropServices.Architecture]::Arm64) {
        $silicon = "ARM64"
        $chipLabel = "ARM64 NPU"
        $isARM = $true
        $modelAlias = "qwen2.5-7b"
        $modelLabel = "Qwen 2.5 7B"
    } else {
        $silicon = "Intel"
        $chipLabel = "Intel Core Ultra NPU"
        $modelAlias = "phi-4-mini"
        $modelLabel = "Phi-4 Mini"
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Copilot+ PC - NPU Demo Setup" -ForegroundColor Cyan
Write-Host "  Detected: $cpuName" -ForegroundColor Cyan
Write-Host "  Platform: $silicon — $chipLabel" -ForegroundColor Cyan
Write-Host "  Model: $modelLabel ($modelAlias)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

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
    # Guard against the Windows Store stub, which prints an error
    # string instead of "Python 3.x.x" and returns non-zero.
    if ($LASTEXITCODE -eq 0 -and $pythonVersion -match "Python 3") {
        Write-Host "[OK] Python already installed: $pythonVersion" -ForegroundColor Green
        $pythonInstalled = $true
    }
} catch {
    $pythonInstalled = $false
}

if (-not $pythonInstalled) {
    # winget auto-detects ARM64 vs x64 and picks the right installer
    Write-Host "Installing Python 3.11 via winget (auto-detects architecture)..." -ForegroundColor Cyan
    try {
        winget install Python.Python.3.11 --accept-source-agreements --accept-package-agreements --scope user 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Python installed" -ForegroundColor Green
        } else {
            throw "winget returned non-zero"
        }
    } catch {
        Write-Host "[WARN] winget install failed. Trying direct download..." -ForegroundColor Yellow
        if ($isARM) {
            $pythonUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-arm64.exe"
        } else {
            $pythonUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
        }
        $pythonInstaller = "$env:TEMP\python-installer.exe"
        try {
            Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonInstaller -UseBasicParsing
            Write-Host "Installing Python..." -ForegroundColor Cyan
            Start-Process $pythonInstaller -ArgumentList "/passive", "InstallAllUsers=0", "PrependPath=1" -Wait
            Write-Host "[OK] Python installed" -ForegroundColor Green
        } catch {
            Write-Host "[FAIL] Could not install Python. Please install manually:" -ForegroundColor Red
            Write-Host "   https://www.python.org/downloads/windows/" -ForegroundColor Yellow
            Write-Host "   (Choose ARM64 for Snapdragon, x64 for Intel)" -ForegroundColor Yellow
        }
    }

    # Refresh PATH so python/pip are available in this session
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
}

Write-Host ""

# ============================================================
# Step 2: Install Foundry Local (if not already installed)
# ============================================================
Write-Host "Step 2: Checking Foundry Local installation..." -ForegroundColor Yellow

$foundryInstalled = $false
try {
    $foundryCheck = foundry --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Foundry Local CLI already installed: $foundryCheck" -ForegroundColor Green
        $foundryInstalled = $true
    }
} catch {
    $foundryInstalled = $false
}

if (-not $foundryInstalled) {
    Write-Host "Installing Foundry Local via winget..." -ForegroundColor Cyan
    try {
        winget install Microsoft.FoundryLocal --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Foundry Local installed" -ForegroundColor Green
            $foundryInstalled = $true
        } else {
            throw "winget returned non-zero"
        }
    } catch {
        Write-Host "[FAIL] Could not install Foundry Local." -ForegroundColor Red
        Write-Host "   Try manually: winget install Microsoft.FoundryLocal" -ForegroundColor Yellow
    }

    # Refresh PATH
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
}

Write-Host ""

# ============================================================
# Step 3: Install Python Dependencies
# ============================================================
Write-Host "Step 3: Installing Python dependencies..." -ForegroundColor Yellow

$requirementsPath = Join-Path $ScriptDir "requirements.txt"

try {
    pip install -r $requirementsPath 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Python dependencies installed" -ForegroundColor Green
    } else {
        Write-Host "   Trying individual package install..." -ForegroundColor Gray
        pip install flask openai pypdf python-docx foundry-local-sdk
        Write-Host "[OK] Python dependencies installed" -ForegroundColor Green
    }
} catch {
    Write-Host "[WARN] Some packages may have failed. Try manually:" -ForegroundColor Yellow
    Write-Host "   pip install flask openai pypdf python-docx foundry-local-sdk" -ForegroundColor Cyan
}

Write-Host ""

# ============================================================
# Step 4: Verify demo files exist
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
# Step 5: Setup demo data
# ============================================================
Write-Host "Step 5: Setting up demo data..." -ForegroundColor Yellow

# Demo data lives inside the project repo (demo_data/) so it's self-contained
$demoDir = Join-Path $PSScriptRoot "demo_data"
$myDayDir = Join-Path $demoDir "My_Day"
$inboxDir = Join-Path $myDayDir "Inbox"

if (Test-Path $myDayDir) {
    Write-Host "[OK] Demo data directory exists: $myDayDir" -ForegroundColor Green
} else {
    Write-Host "[INFO] Creating demo data directory: $myDayDir" -ForegroundColor Cyan
    New-Item -Path $inboxDir -ItemType Directory -Force | Out-Null
    Write-Host "[OK] Demo data directory created" -ForegroundColor Green
    Write-Host "[WARN] Add demo data files (calendar.ics, tasks.csv, emails) to $myDayDir" -ForegroundColor Yellow
}

Write-Host ""

# ============================================================
# Step 6: Test Foundry Local SDK
# ============================================================
Write-Host "Step 6: Testing Foundry Local SDK..." -ForegroundColor Yellow

try {
    $testResult = python -c "from foundry_local import FoundryLocalManager; print('OK')" 2>&1
    if ($testResult -match "OK") {
        Write-Host "[OK] Foundry Local SDK is importable" -ForegroundColor Green
        Write-Host "   The app will auto-download $modelAlias on first run" -ForegroundColor Gray
    } else {
        Write-Host "[WARN] Foundry Local SDK import failed" -ForegroundColor Yellow
        Write-Host "   Try: pip install foundry-local-sdk" -ForegroundColor Cyan
    }
} catch {
    Write-Host "[WARN] Could not verify Foundry Local SDK" -ForegroundColor Yellow
    Write-Host "   Try: pip install foundry-local-sdk" -ForegroundColor Cyan
}

Write-Host ""

# ============================================================
# Step 7: Vision Service (Phi Silica MSIX)
# ============================================================
Write-Host "Step 7: Setting up Vision Service (Phi Silica)..." -ForegroundColor Yellow

$visionServiceDir = Join-Path $ScriptDir "vision-service"
$msixTestDir = Join-Path $visionServiceDir "AppPackages\vision-service_1.0.0.0_x64_Test"
$msixPath = Join-Path $msixTestDir "vision-service_1.0.0.0_x64.msix"

if (Test-Path $msixPath) {
    # Check if already installed
    $existingPkg = Get-AppxPackage -Name 'Microsoft.NPUDemo.VisionService' -ErrorAction SilentlyContinue
    if ($existingPkg) {
        Write-Host "[OK] Vision Service already installed" -ForegroundColor Green
        Write-Host "   PFN: $($existingPkg.PackageFamilyName)" -ForegroundColor Gray
    } else {
        Write-Host "Installing Vision Service MSIX..." -ForegroundColor Cyan

        # Step 7a: Create and trust the signing certificate
        Write-Host "   Setting up signing certificate..." -ForegroundColor Gray
        $certScript = Join-Path $visionServiceDir "scripts\setup-cert.ps1"
        if (Test-Path $certScript) {
            try {
                & $certScript
                Write-Host "   [OK] Certificate configured" -ForegroundColor Green
            } catch {
                Write-Host "   [WARN] Certificate setup needs admin. Run manually:" -ForegroundColor Yellow
                Write-Host "      powershell -ExecutionPolicy Bypass -File `"$certScript`"" -ForegroundColor Cyan
            }
        }

        # Step 7b: Install Windows App Runtime 1.8 dependency
        Write-Host "   Installing Windows App Runtime 1.8..." -ForegroundColor Gray
        try {
            winget install Microsoft.WindowsAppRuntime.1.8 --accept-source-agreements --accept-package-agreements --silent 2>&1 | Out-Null
            Write-Host "   [OK] Windows App Runtime 1.8 installed" -ForegroundColor Green
        } catch {
            Write-Host "   [WARN] Could not install via winget. Trying MSIX dependency..." -ForegroundColor Yellow
            $runtimeMsix = Join-Path $msixTestDir "Dependencies\x64\Microsoft.WindowsAppRuntime.1.8.msix"
            if (Test-Path $runtimeMsix) {
                try {
                    Add-AppxPackage -Path $runtimeMsix -ErrorAction SilentlyContinue
                    Write-Host "   [OK] Windows App Runtime installed from MSIX" -ForegroundColor Green
                } catch {
                    Write-Host "   [WARN] Runtime install failed — Vision Service may not start" -ForegroundColor Yellow
                }
            }
        }

        # Step 7c: Install the Vision Service MSIX
        Write-Host "   Installing Vision Service package..." -ForegroundColor Gray
        try {
            Add-AppxPackage -Path $msixPath
            $pkg = Get-AppxPackage -Name 'Microsoft.NPUDemo.VisionService' -ErrorAction SilentlyContinue
            if ($pkg) {
                Write-Host "   [OK] Vision Service installed" -ForegroundColor Green
                Write-Host "   PFN: $($pkg.PackageFamilyName)" -ForegroundColor Gray
            } else {
                Write-Host "   [WARN] Install command ran but package not found" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "   [FAIL] Could not install MSIX. Common fixes:" -ForegroundColor Red
            Write-Host "      1. Trust the signing cert (run vision-service\scripts\setup-cert.ps1 as admin)" -ForegroundColor Yellow
            Write-Host "      2. Enable Developer Mode (Settings > For developers)" -ForegroundColor Yellow
            Write-Host "      3. Rebuild from source: vision-service\scripts\rebuild-msix.ps1" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[SKIP] Pre-built MSIX not found at: $msixPath" -ForegroundColor Gray
    Write-Host "   To build from source: vision-service\scripts\rebuild-msix.ps1" -ForegroundColor Cyan
}

Write-Host ""

# ============================================================
# Step 8: Pre-download model (optional but saves time on first run)
# ============================================================
Write-Host "Step 8: Checking model availability..." -ForegroundColor Yellow

if ($foundryInstalled) {
    try {
        $modelList = foundry model list 2>&1
        if ($modelList -match $modelAlias) {
            Write-Host "[OK] $modelLabel ($modelAlias) is available in Foundry catalog" -ForegroundColor Green
            Write-Host "   First run will download the model (~3 GB) if not already cached" -ForegroundColor Gray
        } else {
            Write-Host "[WARN] $modelAlias not found in catalog" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[SKIP] Could not check model catalog" -ForegroundColor Gray
    }
} else {
    Write-Host "[SKIP] Foundry Local not installed — skipping model check" -ForegroundColor Gray
}

Write-Host ""

# ============================================================
# Summary
# ============================================================
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Setup Complete" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Silicon:  $cpuName" -ForegroundColor White
Write-Host "  Platform: $silicon — $chipLabel" -ForegroundColor White
Write-Host "  Model:    $modelLabel ($modelAlias)" -ForegroundColor White
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
Write-Host "For Field Inspection vision features, also launch the Vision Service:" -ForegroundColor Green
Write-Host "   powershell -File `"$ScriptDir\vision-service\scripts\launch-vision.ps1`"" -ForegroundColor Cyan
Write-Host ""
Write-Host "No VS Code or AI Toolkit required!" -ForegroundColor Green
Write-Host "Silicon auto-detected: the app will brand itself for $chipLabel." -ForegroundColor Gray
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
