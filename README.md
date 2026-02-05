# Surface NPU Demo — Local AI Assistant

A branded demo application showcasing on-device AI capabilities using the Neural Processing Unit (NPU) on Microsoft Surface Copilot+ PCs.

**100% local processing — your data never leaves the device.**

---

## Features

### Collapsible Sidebar Navigation
App-shell layout with a Claude/ChatGPT-style collapsible sidebar for tab navigation. Sidebar state persists across sessions via localStorage. Mobile-responsive with hamburger menu + backdrop overlay.

### Tabs

| Tab | Description |
|-----|-------------|
| **AI Agent** *(default)* | Governed tool execution (read, write, exec) with approval gates, audit trail, and suggestion chips |
| **My Day** | Executive morning briefing from calendar, email, and task data with cross-referenced insights |
| **Clean Room Auditor** | NDA/contract analysis with structured legal risk assessment |
| **ID Verification** | Camera capture + OCR + AI parsing of driver licenses — fully offline |

### AI Agent Capabilities
- **Meeting Agenda** — AI generates a professional agenda and saves it to the Demo folder
- **Analyze Strategy** — reads a strategy document and extracts key takeaways
- **List Documents** — lists files in the Demo folder with AI summary
- **Summarize a Document** — file picker with approval gate for confidential files
- **Device Health** — 9 PowerShell health checks with AI assessment and "Learn More" follow-ups (see below)

### My Day Capabilities
- **Brief Me** — cross-references calendar, emails, and tasks into an executive briefing
- **Top 3 Focus** — AI identifies the three highest-priority items for the day
- **Tomorrow Preview** — high-level look at the next day's schedule

### Device Health (AI Endpoint Agent)
Runs 9 deterministic PowerShell collectors, then a single AI call to produce an enterprise IT health assessment:

| Check | What it collects |
|-------|-----------------|
| Disk Space | Drive usage percentage via `Win32_LogicalDisk` |
| Battery | Charge level and AC/battery status |
| System Info | OS version, boot time, uptime in days |
| Network Adapters | Active adapters, link speed, status |
| Defender Antivirus | AV enabled, real-time protection, signature age, last scan |
| Firewall Profiles | Domain/Private/Public profile status and inbound/outbound actions |
| Listening Ports | Open TCP ports with owning process names |
| Windows Updates | Last 3 installed hotfixes |
| System Errors | Recent Critical/Error/Warning events from the System log |

**Architecture:** Python does the math (threshold comparisons for disk %, uptime, signature age), AI does the narrative (executive summary + per-area PASS/WARN/FAIL ratings + priority action). This prevents the small model from hallucinating numerical comparisons.

**Learn More:** WARN/FAIL findings generate clickable follow-up buttons that auto-send contextual questions to the AI Agent chat for deeper explanation.

### Additional Capabilities
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
| `npu_demo_flask.py` | Main demo application (~5,900 lines, single file with HTML/CSS/JS inline) |
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
| `My_Day/calendar.ics` | Executive calendar for Feb 7-8, 2026 (includes Super Bowl LX demo data) |
| `My_Day/tasks.csv` | Priority task list (includes Super Bowl prep tasks) |
| `My_Day/Inbox/*.eml` | 15 sample emails |
| `*.txt` | Sample contracts, transcripts, loan applications |
| `*.pdf` | Strategy documents |

---

## Demo Flow

### AI Agent — Governed Execution (Default Tab)
1. Click a suggestion chip (Meeting Agenda, Analyze Strategy, List Documents, Summarize, or **Device Health**)
2. Watch tool execution with approval gates and audit trail
3. For Device Health: watch 9 PowerShell checks stream in real-time, then AI assessment with Learn More buttons
4. Upload a document → click **Summarize** or **Detect PII** inline

### My Day — Executive Briefing
1. Navigate to **My Day** in the sidebar
2. Click **Brief Me** — the AI cross-references your calendar, emails, and tasks
3. Click **Top 3 Focus** for prioritized action items
4. Click **Tomorrow** for a preview of the next day's schedule

### Clean Room Auditor
1. Navigate to **Auditor** in the sidebar
2. Go offline (toggle in sidebar footer) for clean room compliance
3. Upload or load a demo document for legal risk analysis

### ID Verification — Offline OCR
1. Navigate to **ID Verification** in the sidebar
2. Select camera → **Start Camera** → position a driver license
3. **Capture ID** → **Analyze ID** — 3-step pipeline runs entirely on-device

### The "Wow" Moment
1. **Turn on Airplane Mode**
2. Repeat any demo above
3. **Everything still works** — the AI never needed the cloud

---

## Security

- **File system jailing** — all read/write restricted to the Demo directory via `os.path.realpath()` validation
- **PowerShell allowlist** — only approved cmdlets for agent tool calls (get-childitem, get-content, etc.)
- **Device Health bypass** — health check endpoint runs hardcoded commands directly (not through agent allowlist)
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
- **Token Budget:** ~1,000 input tokens (~4K chars), 1,536 max output tokens on NPU
- **UI:** Collapsible sidebar with app-shell layout, mobile-responsive

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
| Device Health check fails | Some checks (Defender, Firewall) may require standard user permissions |

---

## Credits

Built with Claude Code by Microsoft Surface GTM Corp Marketing

*Demonstrating cloud AI for development + on-device AI for secure deployment*
