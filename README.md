# Surface NPU Demo — Local AI Assistant

A branded demo application showcasing on-device AI capabilities using the Neural Processing Unit (NPU) on Microsoft Surface Copilot+ PCs. Supports both **Intel Core Ultra (Lunar Lake)** and **Qualcomm Snapdragon X (ARM64)** — silicon is auto-detected at startup.

**100% local processing — your data never leaves the device.**

---

## Features

### Collapsible Sidebar Navigation
App-shell layout with a Claude/ChatGPT-style collapsible sidebar for tab navigation. Sidebar state persists across sessions via localStorage. Mobile-responsive with hamburger menu + backdrop overlay.

### Five Tabs

| Tab | Description |
|-----|-------------|
| **Device Intelligence** *(default)* | IT Pro device posture — health checks, security audit, and natural language file search |
| **My Day** | Executive morning briefing from calendar, email, and task data with cross-referenced insights |
| **Auditor** | Dual-mode clean room analysis: contract/NDA risk analysis + marketing CELA compliance review |
| **ID Verification** | Camera capture + OCR + AI parsing of driver licenses — fully offline |
| **Field Inspection** | On-site assessment copilot with voice capture, camera, pen annotation, reports, translation, and escalation |

---

### Tab 1: Device Intelligence (AI Agent)

Three capability chips for IT Pro device posture assessment:

#### Device Health
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

**Architecture:** Python does the math (threshold comparisons for disk %, uptime, signature age), AI does the narrative (executive summary + per-area PASS/WARN/FAIL ratings + priority action). Learn More buttons on WARN/FAIL findings route contextual questions to the AI for deeper explanation.

#### Security Audit
24 PowerShell security checks covering chip-to-cloud posture with weighted grading:

| Category | Checks |
|----------|--------|
| Hardware root of trust | TPM, Secure Boot |
| Disk encryption | BitLocker |
| Virtualization-based security | VBS, Credential Guard, HVCI |
| Defender stack | AV (4 layers), EDR (Sense), SmartScreen, Network Protection, ASR rules, Controlled Folder Access |
| Network hardening | Firewall, SMBv1, Network Profile, WinRM, RDP |
| Execution policy | PowerShell Execution Policy, AppLocker/WDAC, AutoPlay |
| Identity & access | Local Admins, Local Users (stale detection), Windows Hello, UAC |
| Maintenance | Patch Health, Certificate Health, LSASS/WDigest |
| Password policy | Minimum length, complexity, lockout |

**Grading:** Weighted scoring with critical checks (Secure Boot, BitLocker, Defender AV, Firewall, TPM, UAC, LSASS) counting heavier — 2 critical FAILs = automatic F. AI receives only compact ratings text (not raw scan data) to stay within 4K context budget. Typical run: ~32s for 24 checks + AI summary.

#### Device Search
Natural language file search using a two-model-call pattern:
1. AI parses natural language query into keywords, extensions, and recency filters
2. PowerShell searches Documents, Desktop, Downloads under USERPROFILE
3. AI summarizes results (capped at 20, sorted by modified date)

Inline search bar UI with Enter key + Search button.

---

### Tab 2: My Day — Executive Morning Briefing

| Feature | What it does |
|---------|-------------|
| **Brief Me** | Cross-references calendar, emails, and tasks into an executive briefing with ACTIONS, PEOPLE TO KNOW, and KEY WARNINGS |
| **Top 3 Focus** | AI identifies the three highest-priority items for the day |
| **Tomorrow Preview** | High-level look at the next day's schedule |
| **Triage Inbox** | Categorizes all emails into URGENT / ACTION NEEDED / FYI |
| **Prep for Next Meeting** | Generates a prep brief for the first substantive meeting |

Data cards at the top show counts (Emails, Events Today, Tasks Due) — click to expand and peek at raw data. Data sources: calendar (.ics), emails (.eml), tasks (.csv) from `demo_data/My_Day/`.

---

### Tab 3: Auditor — Clean Room Analysis

POC disclaimer banner displayed at top of tab.

#### Contract / Legal Review
Structured risk analysis of contracts and NDAs. Upload or load a demo document — AI performs clause-by-clause assessment with risk levels and escalation recommendations.

#### Marketing / Campaign Review
CELA compliance check for marketing assets using document-first architecture:
- Sends actual document text to the model (not pre-extracted phrases)
- Model reads the document and identifies compliance claims itself
- Progressive reveal: claims card → verdict (SELF-SERVICE OK / CELA INTAKE REQUIRED) → summary → escalation consent flow
- PII scanner runs on both flows — redacts SSNs, emails, phone numbers, and person names before any escalation

#### Two-Brain Router
Local AI attempts analysis first → knowledge base search → decision card → optional escalation to frontier model with explicit user consent and Trust Receipt logging.

---

### Tab 4: ID Verification — Offline OCR + AI

POC disclaimer banner displayed at top of tab.

| Step | Engine | Location |
|------|--------|----------|
| 1. Image Capture | Browser API | Local |
| 2. Text Extraction (OCR) | Tesseract.js 5.1.1 | Local (bundled) |
| 3. AI Analysis | Phi-4 Mini on NPU | Local |

Camera capture → OCR → AI parsing extracts: name, address, DOB, ID number, expiration, state, class, and validity status. All Tesseract.js files served from Flask — no CDN dependency.

---

### Tab 5: Field Inspection — On-Site Assessment Copilot

Seven-milestone build targeting MWC Barcelona demo (March 2-5, 2026). Four-panel workspace: form, photo, report, bottom bar.

| Milestone | Capability | Key Detail |
|-----------|-----------|------------|
| **M1** | Scaffold | Four-panel grid layout, tab switching, CSS |
| **M2** | Voice Capture + Field Extraction | Win+H dictation → AI extracts location, datetime, issue, source into form fields |
| **M3** | Camera Capture + Classification | getUserMedia camera with front/rear flip, 5 demo presets, three-tier classification (Phi Silica Vision → demo presets → Phi-4 Mini text fallback) |
| **M4** | Pen Annotation | Dual-canvas overlay in photo lightbox, Pointer Events ink drawing, OCR extraction of handwritten notes (three-tier: Phi Silica Vision → Phi-4 Mini → hardcoded fallback) |
| **M5** | Report Generation | AI generates professional HTML report with summary, risk rating, and next steps from collected fields + findings |
| **M6** | Translation | AI translates report to Spanish, language toggle with side-by-side flash |
| **M7** | Router Escalation + Dashboard | Escalation dialog on 60-74% confidence findings, "Escalate to Cloud" vs "Keep Local" options, dashboard tally (7 local AI tasks vs 0 cloud tasks) with cumulative tokenomics |

**Classification three-tier path:**
1. Demo preset → hardcoded classifications (1.5s simulated)
2. Phi Silica Vision → image to Vision Service on localhost:5100 → NPU inference → category mapping
3. Phi-4 Mini text fallback → filename hint → structured JSON classification

---

### Cross-Tab Features

| Feature | Description |
|---------|-------------|
| **Offline Mode** | Go Offline / Go Online toggle in sidebar footer — works with Airplane Mode enabled |
| **Local AI Savings Widget** | Shows cost saved + CO2 avoided vs cloud inference |
| **Approval Gates** | Destructive agent actions require explicit user approval |
| **Audit Trail** | Every tool execution logged with timestamp, tool name, arguments, success/failure, elapsed time |
| **Document Upload** | File picker with inline Summarize and Detect PII buttons |
| **CELA Disclaimers** | POC banners on Auditor + ID Verification tabs; POC footer in sidebar |

---

## Architecture

```
Browser (localhost:5000)
    |
Flask backend (npu_demo_flask.py, ~11,100 lines, single file)
    |
    +-- Foundry Local runtime (dynamic port)
    |       |
    |       +-- Intel: Phi-4 Mini 3.8B on Core Ultra NPU (OpenVINO)
    |       +-- Qualcomm: Phi-3.5 Mini on Snapdragon X NPU (QNN)
    |
    +-- Vision Service (localhost:5100, C# MSIX)
            |
            +-- Phi Silica ImageDescriptionGenerator on NPU
```

- **No VS Code or AI Toolkit required** — Foundry Local SDK handles model download and runtime automatically
- **No cloud dependencies** — everything runs on-device
- **OpenAI-compatible API** — standard chat completions interface via Foundry Local SDK
- **Cross-platform** — auto-detects Intel vs Qualcomm at startup (WMI CPU name as authoritative source on ARM64 where `platform.machine()` may report AMD64 under emulation)

---

## Quick Start

**New to this?** See the **[Quick Start Guide for Non-Developers](docs/QUICK_START.md)** — step-by-step instructions with no coding required, plus a troubleshooting prompt you can paste into any AI assistant if you get stuck.

### Prerequisites

- Windows 11 24H2 on a Copilot+ PC (Intel Core Ultra or Snapdragon X)
- Python 3.10+
- Foundry Local (`winget install Microsoft.FoundryLocal`)

### Option 1: One-Click Setup

1. Run `setup.ps1` (installs Python, Foundry Local, dependencies, and Vision Service)
2. Double-click `run.bat`
3. Open http://localhost:5000

### Option 2: Manual Setup

```powershell
pip install -r requirements.txt
python npu_demo_flask.py
```

On first run, Foundry Local will download the Phi-4 Mini model (~3 GB). Subsequent launches start in seconds.

**Important:** The pip package `foundry-local` (v0.0.1) is a squatted fake. The real SDK is `foundry-local-sdk`.

---

## Files

| File | Description |
|------|-------------|
| `npu_demo_flask.py` | Main demo application (~11,100 lines, single file with HTML/CSS/JS inline) |
| `run.bat` | One-click launcher — installs deps and copies demo data if needed |
| `setup.ps1` | First-time setup script (Python, Foundry Local, Vision Service, all deps) |
| `requirements.txt` | Python dependencies |
| `vision-service/` | C# Phi Silica Vision microservice (MSIX, localhost:5100) |
| `tests/` | Test suites (283 tests across 3 files) |
| `docs/QUICK_START.md` | Non-developer setup guide with troubleshooting AI prompt |
| `docs/TECHNICAL_GUIDE.md` | Detailed technical documentation |
| `docs/FIELD_INSPECTION_WORKFLOW.md` | Field Inspection on-device AI workflow write-up |
| `docs/DEMO_SCRIPT.md` | Demo flow script |
| `docs/specs/` | Feature specifications |
| `docs/marketing/` | Social posts, exec summaries, demo scripts |
| `Field_Inspection_Copilot_Build_Spec.md` | Build spec for Field Inspection (7 milestones) |
| `surface-logo.png` | Microsoft Surface logo |
| `copilot-logo.avif` | Copilot+ PC logo |
| `tesseract/` | Offline OCR engine (Tesseract.js + English training data) |
| `demo_data/` | Sample calendar, emails, tasks, contracts, inspection photos |

---

## Demo Data

The `demo_data/` folder ships with the repo and is read directly by the app:

| Path | Contents |
|------|----------|
| `My_Day/calendar.ics` | Executive calendar for Feb 7-8, 2026 |
| `My_Day/tasks.csv` | Priority task list (3 high, 3 medium, 1 low) |
| `My_Day/Inbox/*.eml` | 15 sample emails |
| `contract_nda_vertex_pinnacle.txt` | NDA contract for Auditor demo |
| `Board_Strategy_Review_Transcript_Jan2026.txt` | Meeting transcript |
| `inspection_photos/` | 5 preset photos (water damage, structural crack, mold, electrical hazard, trip hazard) |
| `*.txt`, `*.pdf` | Additional contracts, transcripts, strategy documents |

---

## Demo Flow

### Device Intelligence (Default Tab)
1. Click **Device Health** — watch 9 PowerShell checks stream in, then AI assessment with Learn More buttons
2. Click **Security Audit** — 24 checks with weighted grading and AI posture summary
3. Click **Device Search** — type a natural language query like "find PowerPoint files from last week"
4. Upload a document → click **Summarize** or **Detect PII** inline

### My Day — Executive Briefing
1. Navigate to **My Day** in the sidebar
2. Click **Brief Me** — AI cross-references calendar, emails, and tasks
3. Click **Top 3 Focus** for prioritized action items
4. Click **Tomorrow** for next day preview

### Auditor — Clean Room Analysis
1. Navigate to **Auditor** in the sidebar
2. Choose **Contract / Legal Review** or **Marketing / Campaign Review**
3. Go offline (toggle in sidebar footer) for clean room compliance
4. Upload or load a demo document — watch progressive analysis flow

### ID Verification — Offline OCR
1. Navigate to **ID Verification** in the sidebar
2. Select camera → **Start Camera** → position a driver license
3. **Capture ID** → **Analyze ID** — 3-step pipeline runs entirely on-device

### Field Inspection — On-Site Copilot
1. Navigate to **Field Inspection** in the sidebar
2. Dictate inspection notes (Win+H) or click scripted input → watch AI extract fields
3. Capture or load demo photos → AI classifies with confidence scores
4. Annotate photos with pen → AI extracts handwritten notes
5. Generate report → translate to Spanish → review escalation flow
6. View dashboard tally: 7 local AI tasks, 0 cloud tasks

### The "Wow" Moment
1. **Turn on Airplane Mode**
2. Repeat any demo above
3. **Everything still works** — the AI never needed the cloud

---

## Vision Service

C# ASP.NET Core microservice on localhost:5100 wrapping Phi Silica `ImageDescriptionGenerator` (Windows App SDK 1.8 stable). MSIX-packaged with `systemAIModels` capability.

| Endpoint | Purpose |
|----------|---------|
| `/health` | Service and model readiness check |
| `/describe` | Generate image description |
| `/classify` | Classify image into categories |
| `/extract-text` | OCR/handwriting extraction from images |

Build/deploy scripts at `C:\temp\rebuild-msix.ps1` and `C:\temp\launch-vision.ps1`.

---

## Security

| Measure | Detail |
|---------|--------|
| **File system jailing** | All read/write restricted to `demo_data/` via `os.path.realpath()` validation |
| **PowerShell allowlist** | Only approved cmdlets for agent tool calls |
| **Network binding** | Flask bound to `127.0.0.1` only |
| **Path traversal prevention** | Static routes reject `..` and validate realpath |
| **Upload restrictions** | Extension allowlist, `secure_filename()`, 16 MB limit |
| **PII scanner** | Detects SSNs, emails, phone numbers, person names; redacts before escalation |
| **Approval gates** | Destructive agent actions require explicit user approval |
| **Audit trail** | Every tool execution logged with timestamp, tool, args, result, elapsed time |

---

## Technical Details

| Detail | Value |
|--------|-------|
| **Framework** | Flask (Python) |
| **AI Runtime** | Foundry Local SDK (dynamic endpoint) |
| **Text Model (Intel)** | Phi-4 Mini 3.8B (OpenVINO, NPU) |
| **Text Model (Qualcomm)** | Phi-3.5 Mini (QNN, NPU) |
| **Vision Model** | Phi Silica ImageDescriptionGenerator (Windows App SDK 1.8) |
| **OCR** | Tesseract.js 5.1.1 (runs in browser, bundled locally) |
| **Tool Calling** | Text-based `[TOOL_CALL]` shim (model parses structured markers) |
| **Token Budget** | ~1,000 input tokens (~4K chars), 1,536 max output tokens |
| **UI** | Collapsible sidebar, app-shell layout, mobile-responsive |
| **Tests** | 283 tests across 3 test files |

---

## Performance

| Operation | Typical Latency | Power Draw |
|-----------|----------------|------------|
| Brief Me | 40-50s | ~5W sustained |
| Agent chat (simple) | 5-10s | ~5W |
| Security Audit (24 checks + AI) | ~32s | ~5W |
| Marketing CELA review | 15-35s | ~5W |
| OCR (Tesseract.js) | 3-8s | Varies (CPU/WASM) |
| Field Inspection: transcribe | 5-10s | ~5W |
| Field Inspection: classify (demo) | 1.5s | Simulated |
| Field Inspection: report | 10-20s | ~5W |
| Field Inspection: translate | 10-20s | ~5W |

Energy: ~0.06 Wh per briefing (~0.1% of a 58 Wh battery).

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Connection refused" error | Foundry Local may still be starting — wait 10-15 seconds and retry |
| Model not responding | Restart the app — Foundry Local will reinitialize |
| Brief Me timeout | Normal on first run while model loads; subsequent calls are faster |
| Camera not detected | Check browser permissions, try different camera from dropdown |
| OCR quality poor | Improve lighting, hold ID flat, ensure camera is focused |
| Stale code after edits | Delete `__pycache__/npu_demo_flask.cpython-*.pyc` and restart |
| Security audit checks fail | Some checks require standard user permissions |
| Vision Service not responding | Check MSIX is installed and running: `C:\temp\launch-vision.ps1` |

---

## Credits

Built with Claude Code by Microsoft Surface GTM Corp Marketing

*Demonstrating cloud AI for development + on-device AI for secure deployment*
