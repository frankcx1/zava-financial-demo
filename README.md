# Surface NPU Demo — Local AI Assistant

A branded demo application showcasing on-device AI capabilities using the Neural Processing Unit (NPU) on Microsoft Surface Copilot+ PCs.

**100% local processing — your data never leaves the device.**

---

## Features

| Tab | Description |
|-----|-------------|
| **My Day** | Executive morning briefing from calendar, email, and task data with cross-referenced insights |
| **AI Agent** | Governed tool execution (read, write, exec) with approval gates and audit trail |
| **ID Verification** | Camera capture + OCR + AI parsing of driver licenses — fully offline |
| **Clean Room Auditor** | NDA/contract analysis with structured legal risk assessment |

Additional capabilities across tabs:
- Document summarization, PII detection, and key point extraction
- File upload with inline analysis buttons
- Offline mode — works with Airplane Mode enabled

---

## Architecture

```
Browser (localhost:5000)
    |
Flask backend (npu_demo_flask.py)
    |
Foundry Local runtime (dynamic port)
    |
Phi-4 Mini 3.8B on NPU
```

- **No VS Code or AI Toolkit required** — Foundry Local SDK handles model download and runtime automatically
- **No cloud dependencies** — everything runs on-device
- **OpenAI-compatible API** — standard chat completions interface

---

## Quick Start

### Prerequisites

- Windows 11 24H2 on a Copilot+ PC (Intel Core Ultra or Snapdragon X)
- Python 3.10+

### Option 1: One-Click Setup

1. Run `setup.ps1` as Administrator (installs Python dependencies + verifies Foundry Local)
2. Double-click `run.bat`
3. Open http://localhost:5000

### Option 2: Manual Setup

```powershell
pip install -r requirements.txt
python npu_demo_flask.py
```

On first run, Foundry Local will download the Phi-4 Mini model (~2 GB). Subsequent launches start in seconds.

---

## Files

| File | Description |
|------|-------------|
| `npu_demo_flask.py` | Main demo application (~5,100 lines, single file with HTML/CSS/JS inline) |
| `run.bat` | One-click launcher — installs deps and copies demo data if needed |
| `setup.ps1` | First-time setup script (run as Administrator) |
| `requirements.txt` | Python dependencies |
| `surface-logo.png` | Microsoft Surface logo |
| `copilot-logo.avif` | Copilot+ PC logo |
| `tesseract/` | Offline OCR engine (Tesseract.js + English training data) |
| `demo_data/` | Sample calendar, emails, tasks, and documents for the demo |

---

## Demo Data

The `demo_data/` folder contains sample files that `run.bat` auto-copies to `Documents\Demo\` on first launch:

| Path | Contents |
|------|----------|
| `My_Day/calendar.ics` | Executive calendar for Feb 7, 2026 |
| `My_Day/tasks.csv` | Priority task list |
| `My_Day/Inbox/*.eml` | 15 sample emails |
| `*.txt` | Sample contracts, transcripts, loan applications |
| `*.pdf` | Strategy documents |

---

## Demo Flow

### My Day — Executive Briefing
1. Click the **My Day** tab
2. Click **Brief Me** — the AI cross-references your calendar, emails, and tasks
3. Watch it surface conflicts, action items, and relationship context

### AI Agent — Governed Execution
1. Click the **AI Agent** tab
2. Try: *"List files in the Demo folder"* — watch the tool call → approval → execution flow
3. Try: *"Read tasks.csv"* — file content is read and summarized
4. Upload a document → click **Summarize** or **Detect PII** inline

### ID Verification — Offline OCR
1. Click the **ID Verification** tab
2. Select camera → **Start Camera** → position a driver license
3. **Capture ID** → **Analyze ID** — 3-step pipeline runs entirely on-device

### The "Wow" Moment
1. **Turn on Airplane Mode**
2. Repeat any demo above
3. **Everything still works** — the AI never needed the cloud

---

## Security

- **File system jailing** — all read/write restricted to the Demo directory via `os.path.realpath()` validation
- **PowerShell allowlist** — only approved cmdlets (get-childitem, get-content, etc.)
- **Network binding** — Flask bound to `127.0.0.1` only
- **Path traversal prevention** — static file routes reject `..` and validate realpath
- **Upload restrictions** — extension allowlist, `secure_filename()`, 16 MB limit
- **Approval gates** — destructive agent actions require explicit user approval

---

## Technical Details

- **Framework:** Flask (Python)
- **AI Runtime:** Foundry Local SDK (dynamic endpoint)
- **Model:** Phi-4 Mini 3.8B (optimized for NPU via OpenVINO)
- **OCR:** Tesseract.js (runs in browser, no server needed)
- **Tool Calling:** Text-based `[TOOL_CALL]` shim (model parses structured markers in system prompt)
- **Token Budget:** ~1,024 token prompt limit on NPU

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Connection refused" error | Foundry Local may still be starting — wait 10-15 seconds and retry |
| Model not responding | Restart the app — Foundry Local will reinitialize |
| Brief Me timeout | Normal on first run while model loads; subsequent calls are faster |
| Camera not detected | Check browser permissions, try different camera from dropdown |
| OCR quality poor | Improve lighting, hold ID flat, ensure camera is focused |
| Console encoding error | Ensure you're running in a modern terminal (Windows Terminal recommended) |

---

## Credits

Built with Claude by Microsoft Surface GTM Corp Marketing

*Demonstrating cloud AI for development + on-device AI for secure deployment*
