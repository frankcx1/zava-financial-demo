# Surface Copilot+ PC — Local NPU AI Demo

A branded demo application showcasing on-device AI document analysis using the Neural Processing Unit (NPU) on Microsoft Surface Copilot+ PCs.

**Features:**
- 📄 Document upload and analysis (PDF, DOCX, TXT)
- 💬 Chat with AI locally
- 🔒 100% offline capable — no data leaves the device
- ⚡ Powered by Phi Silica via Windows AI API
- ⏱️ Response time display
- 🔄 Multiple model support

---

## Prerequisites

- **Windows 11** on a Copilot+ PC (Snapdragon X Elite/Plus with NPU)
- **Administrator access** for installations

---

## Quick Start (Automated)

1. **Open PowerShell as Administrator**
2. **Navigate to this folder:**
   ```powershell
   cd "C:\Surface-NPU-Demo"
   ```
3. **Run the setup script:**
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   .\setup.ps1
   ```
4. **Complete the manual steps** for VS Code AI Toolkit (see below)
5. **Run the demo:**
   ```powershell
   python npu_demo_flask.py
   ```
6. **Open browser:** http://localhost:5000

---

## Manual Setup (Step-by-Step)

### Step 1: Install Python (ARM64)

```powershell
# Download Python ARM64 installer
Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-arm64.exe" -OutFile "$env:TEMP\python-arm64.exe"

# Run installer (check "Add to PATH")
Start-Process "$env:TEMP\python-arm64.exe" -Wait

# Verify installation (restart PowerShell first)
python --version
```

**Or** download manually from: https://www.python.org/downloads/windows/
> ⚠️ Choose the **ARM64** version, NOT x64

### Step 2: Install VS Code

```powershell
# Using winget (recommended)
winget install Microsoft.VisualStudioCode
```

**Or** download from: https://code.visualstudio.com/

### Step 3: Install AI Toolkit Extension

1. Open VS Code
2. Press `Ctrl+Shift+X` to open Extensions
3. Search for **"AI Toolkit"**
4. Install **"AI Toolkit for Visual Studio Code"** by Microsoft
5. Restart VS Code

### Step 4: Activate Phi Silica

1. In VS Code, click the **AI Toolkit** icon in the left sidebar
2. Click **"Local Models"** at the top
3. Select the **"Windows AI API"** tab
4. Find **"Phi Silica"** and click **"Add"**
5. Wait for activation to complete (shows ✓ Added)

> This enables the Phi Silica model via Windows AI APIs — it's built into Windows on Copilot+ PCs.

### Step 5: Start Foundry Local

The AI Toolkit should auto-start Foundry Local. Verify it's running:

```powershell
# Check if Foundry Local is responding
Invoke-RestMethod -Uri "http://localhost:5272/v1/models"
```

You should see a list of available models including `phi-silica`.

### Step 6: Install Python Dependencies

```powershell
# Navigate to demo folder
cd "C:\Surface-NPU-Demo"

# Install required packages
pip install flask openai pypdf python-docx --break-system-packages
```

### Step 7: Run the Demo

```powershell
python npu_demo_flask.py
```

Open your browser to: **http://localhost:5000**

---

## Demo Script for Customer Presentations

### Opening
*"This demo was built in a few hours using Claude — I'm in marketing, not engineering. That's cloud AI as a productivity multiplier. But what this app DOES is show on-device AI for your regulated data."*

### Flow
1. **Show the interface** — branded Surface + Copilot+ PC
2. **Enable Airplane Mode** — watch the badge change to "✈️ Offline Mode"
3. **Upload the sample PDF** — Enterprise_AI_Strategy_2026.pdf
4. **Click Summarize** — show the ~20-30s local generation
5. **Ask a follow-up question** — demonstrates context retention
6. **Switch models** — show flexibility with different model options

### Key Talking Points
- *"All processing happened on the NPU — no data left this device"*
- *"No cloud API calls to audit or secure"*
- *"Works completely offline for air-gapped environments"*
- *"Your M&A docs, client data, legal contracts — analyzed locally"*

---

## Troubleshooting

### "Foundry Local not responding"
```powershell
# Check if the service is running
Get-Process -Name "foundry*" -ErrorAction SilentlyContinue

# Restart VS Code and AI Toolkit
```

### "Model not found: phi-silica"
- Ensure you activated Phi Silica in AI Toolkit (Step 4)
- Check available models:
  ```powershell
  (Invoke-RestMethod -Uri "http://localhost:5272/v1/models").data
  ```

### "Python not recognized"
- Restart PowerShell after Python installation
- Verify PATH includes Python:
  ```powershell
  $env:PATH -split ";" | Where-Object { $_ -like "*Python*" }
  ```

### "pip install fails"
Try with the `--break-system-packages` flag:
```powershell
pip install flask openai pypdf python-docx --break-system-packages
```

---

## Files Included

| File | Description |
|------|-------------|
| `npu_demo_flask.py` | Main Flask application |
| `setup.ps1` | Automated setup script |
| `requirements.txt` | Python dependencies |
| `surface-logo.png` | Microsoft Surface logo |
| `copilot-logo.avif` | Copilot+ PC logo |
| `Enterprise_AI_Strategy_2026.pdf` | Sample document for demos |

---

## Technical Details

- **Framework:** Flask (Python)
- **AI Backend:** Foundry Local + Windows AI API
- **Model:** Phi Silica (optimized for NPU)
- **Endpoint:** OpenAI-compatible API at `localhost:5272`

---

## Credits

Built with ❤️ and Claude by Microsoft Surface Field Marketing

*Demonstrating the power of cloud AI for development + on-device AI for secure deployment*
