@echo off
title Surface Copilot+ PC - NPU Demo
echo.
echo ============================================================
echo   Surface Copilot+ PC - NPU Demo
echo   Powered by Foundry Local + Phi-4 Mini
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Run setup.ps1 first.
    echo         Or install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Check Flask
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    pip install -r "%~dp0requirements.txt"
    echo.
)

:: Setup demo data if needed
if not exist "%USERPROFILE%\Documents\Demo\My_Day" (
    echo [INFO] Setting up demo data...
    if exist "%~dp0demo_data" (
        xcopy "%~dp0demo_data" "%USERPROFILE%\Documents\Demo\" /E /I /Y >nul 2>&1
        echo [OK] Demo data copied to Documents\Demo
    ) else (
        echo [WARN] demo_data folder not found. Create Documents\Demo\My_Day manually.
    )
    echo.
)

echo Starting NPU Demo on http://localhost:5000
echo Press Ctrl+C to stop.
echo.

:: Launch the app
cd /d "%~dp0"
python npu_demo_flask.py

pause
