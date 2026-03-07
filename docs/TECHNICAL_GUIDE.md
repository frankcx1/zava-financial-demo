# Local NPU AI Assistant — Technical Guide

## Overview

A single-file Flask application (`npu_demo_flask.py`, ~11,100 lines) that demonstrates five AI-powered capabilities running entirely on-device using the NPU on Microsoft Surface Copilot+ PCs. Supports both Intel Core Ultra (Lunar Lake) and Qualcomm Snapdragon X (ARM64) — silicon is auto-detected at startup. Zero cloud dependencies. Zero data egress.

**Architecture:**
```
Browser (localhost:5000)
    |
Flask backend (npu_demo_flask.py)
    |
    +-- Foundry Local runtime (dynamic port via SDK)
    |       +-- Intel: Phi-4 Mini 3.8B (OpenVINO NPU)
    |       +-- Qualcomm: Phi-3.5 Mini (QNN NPU)
    |
    +-- Vision Service (localhost:5100, C# MSIX)
            +-- Phi Silica ImageDescriptionGenerator
```

---

## How to Run

```
python npu_demo_flask.py
```

**Prerequisites:**
- Foundry Local installed (`winget install Microsoft.FoundryLocal`) — runtime auto-starts on first model call
- Python 3.10+ with Flask, OpenAI SDK, `foundry-local-sdk` (NOT the squatted `foundry-local` pip package)
- Tesseract.js files bundled in `tesseract/` directory (included)
- Demo data in `demo_data/` within the project directory
- Vision Service MSIX installed and running for camera classification (optional — text fallback available)

**Ports:**
| Service | Port | Notes |
|---------|------|-------|
| Flask app | `127.0.0.1:5000` | Bound to localhost only |
| Foundry Local | Dynamic (via SDK) | OpenAI-compatible `/v1` API |
| Vision Service | `127.0.0.1:5100` | C# MSIX, Phi Silica Vision |

**Cross-platform detection:**
On Windows-on-ARM, `platform.machine()` and `PROCESSOR_ARCHITECTURE` may report `AMD64`/`X64` due to emulation. The app uses WMI CPU name (`Win32_Processor`) as the authoritative source for silicon detection.

---

## Tab 1: Device Intelligence — IT Pro Device Posture

### Value Proposition
Enterprise IT security and health assessment running entirely on-device. Three chips replace the previous generic AI Agent interface to focus on the IT Pro story.

### Chips

| Chip | Endpoint | Description |
|------|----------|-------------|
| Device Health | `POST /demo/device-health` | 9 PowerShell collectors + AI narrative |
| Security Audit | `POST /demo/security-audit` | 24 security checks + weighted grading |
| Device Search | `POST /demo/device-search` | Natural language file search |

### Device Health

Runs 9 deterministic PowerShell collectors:

| # | Check | Collector | Rating Logic |
|---|-------|-----------|-------------|
| 1 | Disk Space | `Win32_LogicalDisk` | FAIL <10%, WARN <20%, PASS otherwise |
| 2 | Battery | `Win32_Battery` | Level + AC/battery status |
| 3 | System Info | `Win32_OperatingSystem` | Uptime threshold |
| 4 | Network | `Get-NetAdapter` | Active adapters, link speed |
| 5 | Defender AV | `Get-MpComputerStatus` | Enabled, real-time, signature age |
| 6 | Firewall | `Get-NetFirewallProfile` | Domain/Private/Public status |
| 7 | Listening Ports | `Get-NetTCPConnection` | Open ports with process names |
| 8 | Windows Updates | `Get-HotFix` | Last 3 hotfixes |
| 9 | System Errors | `Get-WinEvent` | Recent Critical/Error/Warning events |

**Architecture:** Python computes threshold-based ratings (PASS/WARN/FAIL). AI receives only the compact ratings text and produces an executive summary with per-area assessments and priority actions. This prevents the small model from hallucinating numerical comparisons.

**Learn More:** WARN/FAIL findings generate clickable buttons that auto-send contextual questions to the `/knowledge` endpoint for deeper AI explanation.

### Security Audit — 24 Checks

| # | Category | Check ID | What it checks |
|---|----------|----------|----------------|
| 1 | Hardware | `tpm` | TPM presence and version |
| 2 | Hardware | `secureboot` | Secure Boot enabled |
| 3 | Disk | `bitlocker` | BitLocker encryption status |
| 4 | VBS | `vbs` | Virtualization-Based Security |
| 5 | VBS | `credguard` | Credential Guard (decoded from SecurityServicesRunning) |
| 6 | VBS | `hvci` | Hypervisor-enforced Code Integrity |
| 7 | Defender | `defender_av` | AV enabled, real-time, signatures, quick scan (4 layers) |
| 8 | Defender | `defender_edr` | Sense service (EDR) running |
| 9 | Defender | `smartscreen` | SmartScreen via `Get-MpPreference` |
| 10 | Defender | `network_protection` | Network Protection enabled |
| 11 | Defender | `asr_rules` | Attack Surface Reduction rules |
| 12 | Defender | `controlled_folders` | Controlled Folder Access |
| 13 | Network | `firewall` | All three profiles enabled |
| 14 | Network | `smbv1` | SMBv1 disabled |
| 15 | Network | `network_profile` | Network profile type |
| 16 | Network | `winrm` | WinRM service status |
| 17 | Network | `rdp` | RDP access status |
| 18 | Policy | `execution_policy` | PowerShell Execution Policy |
| 19 | Policy | `applocker` | AppLocker or WDAC status |
| 20 | Policy | `autoplay` | AutoPlay/AutoRun (HKLM + HKCU) |
| 21 | Identity | `local_admins` | Local Administrators group members |
| 22 | Identity | `local_users` | Local users with stale account detection |
| 23 | Identity | `windows_hello` | Windows Hello enrollment |
| 24 | Identity | `uac` | UAC configuration |
| 25 | Maintenance | `patch_health` | Last hotfix age |
| 26 | Maintenance | `cert_health` | Certificate store health |
| 27 | Maintenance | `lsass` | LSASS protection + WDigest |
| 28 | Policy | `password_policy` | Minimum length, complexity, lockout |

**Weighted grading:** Critical IDs (`secureboot`, `bitlocker`, `defender_av`, `firewall`, `tpm`, `uac`, `lsass`) count heavier — 2 critical FAILs = automatic F grade. AI receives only `pre_text` (compact ratings string), not raw PowerShell output, to stay within 4K context budget.

**Parse bug notes:** UAC and Password Policy lambdas use `re.search()` with `\s*:\s*` to handle variable PowerShell whitespace formatting. SmartScreen swapped to `Get-MpPreference`. AutoRun checks both HKLM and HKCU.

**JS element prefix:** Security audit uses `sc-` element IDs (vs `hc-` for health checks).

### Device Search

Two-model-call pattern:
1. `POST /demo/device-search` receives natural language query
2. First AI call: extract keywords, file extensions, and recency from query
3. PowerShell `Get-ChildItem` searches Documents, Desktop, Downloads under `$env:USERPROFILE`
4. Second AI call: summarize search results into human-readable response
5. Fallback: if AI extraction fails, splits query into keywords and searches common extensions

Results capped at 20, sorted by modified date. Inline search bar UI with Enter key + Search button.

### Additional Agent Features

| Feature | Endpoint | Description |
|---------|----------|-------------|
| Document upload | `POST /upload-to-demo` | Upload PDF/DOCX/TXT/MD, extract text, save to Demo folder |
| Summarize document | `POST /summarize-doc` | Single-step AI summarization of uploaded file |
| Detect PII | `POST /detect-pii` | Single-step PII detection (SSNs, emails, phones, names) |
| Knowledge Q&A | `POST /knowledge` | Pure AI explanation — no tool access |
| Agent chat | `POST /chat` | Free-form chat routed through tool-calling pipeline |
| Audit log | `GET /audit-log` | Return audit trail entries |
| Session stats | `GET /session-stats` | Computed savings for Local AI Savings widget |

### Tool-Calling Shim

Phi-4 Mini doesn't have native tool-calling support. The app uses a `toolsViaPrompt` shim:
1. Compact system prompt defines available tools with `[TOOL_CALL]` markers
2. Model outputs `[TOOL_CALL]{"name":"...", "arguments":{...}}[/TOOL_CALL]` blocks
3. Backend parses markers with regex, executes the tool, feeds result back
4. Model generates a spoken summary of the result

**Known limitation:** The model hangs when making consecutive API calls (tool decision → followup summary). Solution: use dedicated single-step endpoints that bypass the agent loop.

### Available Tools (Agent Chat)

| Tool | What It Does | Constraints |
|------|-------------|-------------|
| `read` | Read a file and return contents (max 5,000 chars) | Path must resolve within `demo_data/` |
| `write` | Create or overwrite a file | Path must resolve within `demo_data/` |
| `exec` | Run a PowerShell command | Allowlisted cmdlets only |

---

## Tab 2: My Day — Executive Morning Briefing

### Value Proposition
Transforms raw calendar, email, and task data into a cross-referenced executive briefing — the "chief of staff in your pocket" story.

### Data Sources

| Source | Format | Location | Parser |
|--------|--------|----------|--------|
| Calendar | iCalendar (.ics) | `demo_data/My_Day/calendar.ics` | `parse_ics()` — regex-based, no external libs |
| Tasks | CSV | `demo_data/My_Day/tasks.csv` | `parse_tasks_csv()` — built-in `csv.DictReader` |
| Emails | RFC 5322 (.eml) | `demo_data/My_Day/Inbox/*.eml` | `parse_eml()` — built-in `email` module |

### Features

#### Data Cards (click to peek)
Three cards at the top showing counts (Emails, Events Today, Tasks Due). Click any card to expand a dropdown:
- **Emails**: sender name + subject line
- **Events**: time range, title, location
- **Tasks**: color-coded priority tag (red/yellow/green) + task name

Data fetched from `GET /my-day-data` on first click and cached.

#### Brief Me
`POST /brief-me` — streaming JSONL response.

**Flow:**
1. Backend parses all data sources (progress streamed to UI)
2. `compress_for_briefing()` compresses ~32 data items into ~3,600 characters:
   - Calendar events with up to 3 description lines each
   - Tasks with priority and truncated notes
   - First 6 emails get body snippets, remainder get subject only
   - Hard cap at 3,600 chars for Phi's ~4K context window
3. Combined with `BRIEFING_SYSTEM_PROMPT` (~723 chars) coaching the model to cross-reference
4. Model generates structured output: narrative summary → ACTIONS → PEOPLE TO KNOW → KEY WARNINGS
5. Frontend splits into executive summary card + collapsible breakdown sections
6. Footer: "Analyzed 15 emails, 10 events, 7 tasks in Xs on NPU"

**Token Budget:** ~1,084 input tokens + 800 max output = ~1,884 total

#### Triage Inbox
`POST /triage-inbox` — Categorizes all 15 emails into URGENT / ACTION NEEDED / FYI with recommended actions.

#### Prep for Next Meeting
`POST /prep-next-meeting` — Skips logistics events and generates prep brief for first substantive meeting.

#### Top 3 Focus
`POST /top-3-focus` — AI identifies three highest-priority items across all data sources.

#### Tomorrow Preview
`POST /tomorrow-preview` — High-level overview of next day's schedule.

---

## Tab 3: Auditor — Clean Room Analysis

### Value Proposition
Demonstrates secure, on-device document review for legal and marketing compliance — the "confidential documents never leave the device" story.

### Dual Mode

| Mode | Use Case | Demo Doc |
|------|----------|----------|
| Contract / Legal Review | NDA and contract risk analysis | `GET /auditor-demo-doc` or `GET /auditor-escalation-demo-doc` |
| Marketing / Campaign Review | CELA compliance for marketing assets | `GET /auditor-marketing-demo-doc` or `GET /auditor-marketing-escalation-demo-doc` |

### Contract Review Flow
1. Load or upload a contract document
2. AI performs structured clause-by-clause risk analysis
3. Risk levels assigned per clause
4. Escalation recommendation if high-risk clauses found
5. Escalation consent flow with PII redaction

### Marketing CELA Review Flow
**Document-first architecture** — mirrors the contract review flow:

1. Sends actual document text to model (not pre-extracted phrases)
2. Model reads document and identifies compliance claims itself
3. Fallback: hardcoded findings for demo docs, regex+metadata for uploaded docs (if < 2 claims parsed)
4. SSE events: `claims` → `verdict` → `summary` → `escalation_available` → `audit` → `complete`
5. Verdict: **SELF-SERVICE OK** or **CELA INTAKE REQUIRED**

**Parser:** `_parse_marketing_response()` handles model output parsing.
**Hardcoded findings:** `_MARKETING_CLEAN_FINDINGS` (clean doc), `_MARKETING_RISKY_FINDINGS` (escalation doc).

### PII Scanner
`_scan_pii()` detects SSNs, emails, phone numbers, and person names (curated list via `_DEMO_PERSON_NAMES` regex). Runs on both marketing and contract flows. `_redact_text()` replaces findings with `[REDACTED Type]` before any escalation to frontier models.

### Two-Brain Router
| Endpoint | Purpose |
|----------|---------|
| `POST /router/analyze` | Local attempt → knowledge search → decision card → escalation consent |
| `POST /router/decide` | Record user's decision and generate Trust Receipt |
| `GET /router/log` | Return full Router decision log |

---

## Tab 4: ID Verification — On-Device OCR + AI Analysis

### Value Proposition
Extends the local AI pattern to vision/OCR use cases in regulated industries. Camera capture, text extraction, and AI analysis all happen on-device.

### Flow
1. **Camera Selection**: Enumerates available cameras, labels Front/Rear/Built-in
2. **Image Capture**: Live video preview → capture frame to canvas → display as PNG
3. **OCR (Tesseract.js)**: Locally-bundled Tesseract.js v5.1.1 extracts text. All files served from Flask — no CDN.
4. **AI Analysis**: `POST /analyze-id` sends OCR text to model. Returns: name, address, DOB, ID number, expiration, state, class, validity status
5. **Result Display**: Styled card with status badge (Valid/Expired/Review Needed) and extracted fields table

### Tesseract.js Local Bundle
All OCR files served via `/tesseract/<path>` route:
```
tesseract/
  tesseract.min.js          66 KB
  worker.min.js            121 KB
  core/*.wasm.js           3.8-4.6 MB (SIMD/LSTM variants)
  lang/eng.traineddata.gz  10.9 MB
```

---

## Tab 5: Field Inspection — On-Site Assessment Copilot

### Value Proposition
Demonstrates a complete field inspection workflow — from voice dictation to translated reports — running entirely on-device. Targeting MWC Barcelona demo (March 2-5, 2026).

### Architecture
- **Layout:** Four-panel workspace (form, photo, report, bottom bar)
- **Code pattern:** Each milestone is a self-contained IIFE: `// -- Field Inspection: Milestone N -- ...`
- **Cross-milestone communication:** Via `window._inspFindings`, `window._inspReportData`, `window._inspCompletedTasks`, `window._inspCheckEscalation`, `window._inspShowDashboard`
- **Status bar:** Shared `inspStatusDot`, `inspStatusText`, `inspTokenCount`

### Milestone 1 — Scaffold
Nav item, tab button, four-panel grid layout, CSS, tab switching integration.

### Milestone 2 — Voice Capture + Field Extraction
- **Input:** Win+H (Windows 11 on-device speech recognition) via standard textarea, or scripted input button ("Inspector Sarah Chen at Building C...")
- **Endpoint:** `POST /inspection/transcribe` sends transcript to Phi-4 Mini
- **Output:** JSON fields: location, datetime, issue, source, inspector_name
- **UI:** Staggered field animation as fields populate the form
- **Inspector name:** Dedicated `inspInspector` input field; backend fallback provides default

### Milestone 3 — Camera Capture + Classification
- **Camera:** `getUserMedia` with `facingMode: "user"` default (Surface Pro front camera), flip button for rear
- **Demo presets:** 5 photos cycling through: water_damage (82%), structural_crack (72%), mold (88%), electrical_hazard (91%), trip_hazard (85%)
- **Endpoint:** `POST /inspection/classify` with three-tier fallback:
  1. Demo preset → hardcoded `_DEMO_CLASSIFICATIONS` (1.5s simulated)
  2. Phi Silica Vision → image to Vision Service :5100 → NPU inference → keyword-based category mapping
  3. Phi-4 Mini text fallback → filename hint → structured JSON classification
- **UI:** Classification card with confidence thresholds (green >= 75, amber 60-74, red < 60), findings log, photo grid with severity badges
- **Source label:** Shows "Phi Silica Vision on NPU" / "Demo Preset" / "Phi-4 Mini (text)"

### Milestone 4 — Pen Annotation
- **Canvas:** Dual-canvas overlay in photo lightbox (base canvas + transparent ink canvas)
- **Drawing:** Pointer Events for pen/mouse/touch, red ink (#ef4444, 3px, round cap/join)
- **Toolbar:** Undo (pop last stroke), Clear (erase all), Done (submit), Cancel
- **Done handler:** Composites base+ink → JPEG thumbnail, ink-on-white → PNG for OCR
- **Endpoint:** `POST /inspection/annotate` with three-tier fallback:
  1. Phi Silica Vision `/extract-text` on localhost:5100
  2. Phi-4 Mini text model (generates plausible inspector note)
  3. Hardcoded fallback: "Check pipe above - possible leak source"
- **Storage:** `finding.annotations.extracted_text`, shown as "Inspector Note"
- **UI:** Pen icon on thumbnails (bottom-left), annotation badge (red, top-left) on annotated photos
- **Cross-milestone:** `window._inspOpenAnnotation(findingId)` exposed for access

### Milestone 5 — Report Generation
- **Endpoint:** `POST /inspection/report` sends fields + findings to Phi-4 Mini
- **Output:** Professional HTML report with summary, risk rating, next steps
- **Fallback:** Hardcoded report on model error
- **UI:** Report draft panel, "Regenerate Report" button

### Milestone 6 — Translation
- **Endpoint:** `POST /inspection/translate` sends report HTML for Spanish translation
- **UI:** Language toggle (EN/ES), 500ms side-by-side flash before settling
- **Status:** "no cloud API call" confirmation

### Milestone 7 — Router Escalation + Dashboard Tally
- **Trigger:** 60-74% confidence findings (structural_crack at 72% demos this)
- **Escalation dialog:** Two options:
  - "Escalate to Cloud" — payload preview, graceful offline failure
  - "Keep Local" — lock animation, flags for expert review
- **Dashboard tally:** 7 local AI tasks with checkmarks vs 0 cloud tasks
- **Tokenomics:** Cumulative token usage display

---

## Sidebar & Global UI

### Sidebar
- Replaces old horizontal header + tab bar (both hidden via `display:none`)
- Hidden `.tab-btn` div preserved inside `<main>` for backward compat with `switchToTab()` and `querySelectorAll(".tab-btn")`
- Nav items use `data-tab` attribute mapping to `switchToTab()`
- Collapse state persisted in `localStorage("sidebarCollapsed")`
- Mobile: hamburger + backdrop overlay at < 768px

### Sidebar Footer
- Status controls: offline badge, Go Offline/Online buttons, model select
- POC disclaimer footer (`.poc-footer`): general POC disclaimer, muted style (0.75em), hides when collapsed

### CELA Disclaimers
- `.poc-banner` class: yellow #FFF3CD background, dark #856404 text, non-dismissible
- Auditor tab: POC disclaimer about compliance tool limitations
- ID Verification tab: POC disclaimer about identity verification limitations

### Local AI Savings Widget
- `.savings-stat-hero` class: 1.35em, bold, green (#22c55e), text-shadow glow
- Shows cost saved + CO2 avoided (hero numbers)
- `.tool-time` base style: 0.88em, cyan-blue `rgba(0,188,242,0.7)`

### Warmup Overlay
- `position:fixed; z-index:10000` — independent of layout changes
- Shown on first page load while model loads, dismissed when `/health` returns ready

---

## Vision Service

### Overview
C# ASP.NET Core microservice on localhost:5100, wraps Phi Silica `ImageDescriptionGenerator` (Windows App SDK 1.8 stable). MSIX-packaged with `systemAIModels` capability.

### API Surface (Stable 1.8.5)

| Namespace | Class | Notes |
|-----------|-------|-------|
| `Microsoft.Windows.AI.Imaging` | `ImageDescriptionGenerator` | Was in `Generative` namespace in exp1 |
| `Microsoft.Windows.AI.ContentSafety` | `ContentFilterOptions` | Was `ContentModeration` in exp1 |
| `Microsoft.Graphics.Imaging` | `ImageBuffer` | Factory: `CreateForSoftwareBitmap()` |

| Enum/Property | Values |
|---------------|--------|
| `ImageDescriptionKind` | `BriefDescription`, `DetailedDescription`, `DiagramDescription`, `AccessibleDescription` |
| `AIFeatureReadyState` | `Ready`, `NotReady`, `NotSupportedOnCurrentSystem`, `DisabledByUser` |

### Endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/health` | Service + model readiness |
| POST | `/describe` | Image description generation |
| POST | `/classify` | Image classification |
| POST | `/extract-text` | OCR / handwriting extraction |

### Packaging & Deployment

| Item | Value |
|------|-------|
| NuGet | `Microsoft.WindowsAppSDK 1.8.260209005` (stable 1.8.5) |
| PFN | `Microsoft.NPUDemo.VisionService_r0xr04974zwaa` |
| Cert | `CN=FrankBu`, thumbprint `D105059461CAEB607A40723E92CBDFB91917A570` |
| LAF feature | `com.microsoft.windows.ai.languagemodel` |
| LAF token | Covers both text (LanguageModel) and vision (ImageDescriptionGenerator) |
| MinVersion | `10.0.26100.0` (Windows 11 24H2) |

**Critical manifest fix:** Must include `Windows.Universal` TargetDeviceFamily alongside `Windows.Desktop`. Without it, LAF token is accepted but `GetReadyState()` throws "Not declared by app" COMException. Ref: GitHub issue microsoft/WindowsAppSDK#5580.

### Build/Deploy Pipeline
```
dotnet publish -c Release -p:GenerateAppxPackageOnBuild=true
signtool sign /fd SHA256 /a /sha1 {thumbprint} {msix_path}
Add-AppxPackage {msix_path}  # framework deps from Dependencies\x64\ first
shell:AppsFolder\Microsoft.NPUDemo.VisionService_r0xr04974zwaa!App
```

Scripts: `C:\temp\rebuild-msix.ps1`, `C:\temp\launch-vision.ps1`, `C:\temp\test-vision.ps1`
Log: `C:\temp\vision-service-init.log`

---

## Security Measures

### 1. File System Jailing
All `read` and `write` tool operations restricted to `demo_data/`:
```python
def _path_in_demo_dir(path):
    resolved = os.path.realpath(os.path.normpath(path))
    demo_resolved = os.path.realpath(DEMO_DIR)
    return resolved.startswith(demo_resolved + os.sep) or resolved == demo_resolved
```
Uses `os.path.realpath()` (resolves symlinks) for stronger guarantees.

### 2. PowerShell Command Allowlist
Only these cmdlets are permitted for agent tool calls:

| Allowed Command | Purpose |
|----------------|---------|
| `get-childitem` | List directory contents |
| `get-content` | Read file contents |
| `set-content` | Write file contents |
| `add-content` | Append to file |
| `out-file` | Redirect output to file |
| `get-date` | Get current date/time |
| `get-location` | Get current directory |
| `write-output` | Echo output |
| `select-object` | Filter object properties |
| `format-list` | Format output |
| `get-netadapter` | Check network adapter status |
| `disable-netadapter` | Go offline |
| `enable-netadapter` | Go online |

Device health and security audit endpoints run hardcoded commands directly (not through agent allowlist).

### 3. Network Binding
Flask bound to `127.0.0.1` only.

### 4. Static File Path Traversal Prevention
`/logos/<path>` and `/tesseract/<path>` routes reject `..`, validate starting character, verify realpath resolves within expected directory, and restrict to allowed MIME types.

### 5. Upload Restrictions
Extension allowlist (`.pdf`, `.docx`, `.txt`, `.md`), `secure_filename()` sanitization, 16 MB size limit.

### 6. PII Scanner
`_scan_pii()` detects SSNs, emails, phone numbers, and person names (curated `_DEMO_PERSON_NAMES` regex). `_redact_text()` replaces with `[REDACTED Type]` before any frontier model escalation.

### 7. Approval Gates
Review & Summarize flow requires explicit user approval before AI accesses files. Both approval and denial logged to audit trail.

### 8. Audit Trail
Every tool execution logged with timestamp, tool name, arguments, success/failure, and elapsed time.

---

## API Endpoints Reference

### Core

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/` | Serve main HTML page |
| GET | `/logos/<path>` | Serve logo images |
| GET | `/tesseract/<path>` | Serve Tesseract.js files |
| GET | `/health` | Model readiness for warmup overlay |
| GET | `/demo-mode-status` | Check if demo mode is enabled |

### Device Intelligence (AI Agent)

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/chat` | Agent chat (streaming JSONL, tool-calling pipeline) |
| POST | `/demo/device-health` | 9 PowerShell health checks + AI summary |
| POST | `/demo/security-audit` | 24 security checks + weighted grading + AI posture |
| POST | `/demo/device-search` | Natural language file search (two AI calls) |
| POST | `/knowledge` | Knowledge Q&A — pure AI, no tools |
| POST | `/knowledge/search` | Search local knowledge index |
| POST | `/knowledge/refresh` | Rebuild local knowledge index |
| POST | `/upload-to-demo` | Upload file, extract text, save to Demo folder |
| POST | `/summarize-doc` | Single-step document summarization |
| POST | `/detect-pii` | Single-step PII detection |
| POST | `/save-summary` | Direct file write of summary |
| GET | `/demo/list-files` | List Demo folder files with confidentiality metadata |
| POST | `/demo/review-summarize` | Two-phase review with approval gate |
| GET | `/audit-log` | Return audit trail |
| DELETE | `/audit-log` | Clear audit trail |
| GET | `/session-stats` | Computed savings for widget |

### My Day

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/brief-me` | Full morning briefing (streaming JSONL) |
| POST | `/triage-inbox` | Email triage (streaming JSONL) |
| POST | `/prep-next-meeting` | Next meeting prep (streaming JSONL) |
| POST | `/top-3-focus` | Top 3 priority items |
| POST | `/tomorrow-preview` | Next day schedule overview |
| GET | `/my-day-counts` | Card counts {events, tasks, emails} |
| GET | `/my-day-data` | Full parsed data for peek windows |

### Auditor

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/auditor-demo-doc` | Pre-staged NDA for contract review |
| GET | `/auditor-escalation-demo-doc` | Cross-border IP license for escalation demo |
| GET | `/auditor-marketing-demo-doc` | Clean marketing doc for self-service OK |
| GET | `/auditor-marketing-escalation-demo-doc` | Risky marketing doc for CELA intake |
| POST | `/router/analyze` | Two-Brain Router analysis |
| POST | `/router/decide` | Record escalation decision + Trust Receipt |
| GET | `/router/log` | Router decision log |

### ID Verification

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/analyze-id` | Analyze OCR text, extract structured fields |

### Field Inspection

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/inspection/fluid-dictation` | Toggle Windows Voice Typing |
| POST | `/inspection/transcribe` | Extract inspection fields from transcript |
| GET | `/inspection/demo-photo/<type>` | Serve demo inspection photo |
| POST | `/inspection/classify` | Classify photo (3-tier fallback) |
| POST | `/inspection/annotate` | Extract text from annotated photo (3-tier fallback) |
| POST | `/inspection/report` | Generate inspection report |
| POST | `/inspection/translate` | Translate report to target language |

### System

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/connectivity-check` | Check Wi-Fi + NPU status |
| POST | `/network-toggle` | Enable/disable network adapters |

**Total: 45 endpoints**

---

## Key Constants

| Constant | Value |
|----------|-------|
| `DEMO_DIR` | `<project_root>/demo_data` |
| `MY_DAY_DIR` | `<project_root>/demo_data/My_Day` |
| `MY_DAY_INBOX` | `<project_root>/demo_data/My_Day/Inbox` |
| `MAX_CONTENT_LENGTH` | 16 MB |
| Flask host | `127.0.0.1` |
| Flask port | `5000` |
| `max_tokens` (Brief Me) | 800 |
| `max_tokens` (Triage) | 800 |
| `max_tokens` (Prep) | 500 |
| `max_tokens` (Agent chat) | 1024 |
| Compression hard cap | 3,600 chars |
| PowerShell timeout | 15s (general) / 30s (network) |

---

## Performance Characteristics

| Operation | Typical Latency | Token Budget | Power Draw |
|-----------|----------------|--------------|------------|
| Brief Me | 40-50s | ~1,884 tokens | ~5W |
| Agent chat (simple) | 5-10s | ~1,824 tokens max | ~5W |
| Agent chat (tool + summary) | 15-25s | Two model calls | ~5W |
| Security Audit (24 checks + AI) | ~32s | Compact ratings only | ~5W |
| Triage Inbox | 30-40s | ~1,800 tokens | ~5W |
| Prep for Next Meeting | 15-25s | ~1,300 tokens | ~5W |
| Marketing CELA review | 15-35s | ~1,300-2,850 tokens | ~5W |
| OCR (Tesseract.js) | 3-8s | N/A (CPU/WASM) | Varies |
| ID Analysis | 5-10s | ~1,024 tokens | ~5W |
| Field: transcribe | 5-10s | — | ~5W |
| Field: classify (demo) | 1.5s | Simulated | — |
| Field: classify (vision) | 3-8s | — | ~5W |
| Field: report | 10-20s | — | ~5W |
| Field: translate | 10-20s | — | ~5W |

**Energy:** ~0.06 Wh per briefing (~0.1% of a 58 Wh battery).

**Token budget notes:**
- Phi-4 Mini: ~4K context window total
- Marketing CELA: ~500 input + 800 output = ~1,300 (Intel); ~1,650 input + 1,200 output = ~2,850 (Qualcomm)
- Context budget: Do NOT send raw PowerShell output with 17+ checks to model — only send pre-computed ratings text

---

## Variable Scoping

Key state variables must be at script level (not inside DOMContentLoaded):
```javascript
var pendingApprovalReview = false;
var pendingSummarize = false;
var lastAssistantResponse = "";
```

---

## Common Debugging

| Issue | Cause | Fix |
|-------|-------|-----|
| Model hangs on second API call | Consecutive calls in agent loop | Use dedicated single-step endpoints |
| Save button not appearing | Variables inside DOMContentLoaded | Move to script level |
| Markdown not rendering | Missing `mdToHtml()` call | Apply to all code paths rendering model output |
| Model hallucinating file paths | Model choosing paths | Use dedicated endpoints that control paths directly |
| Flask serving stale code | `__pycache__` not invalidated | Delete `__pycache__/npu_demo_flask.cpython-*.pyc` and restart |
| Vision Service not responding | MSIX not running | Run `C:\temp\launch-vision.ps1` |
| `request.json` 415 error | Multipart form upload in Flask 3.x | Use `request.is_json` guard before `request.json` |
| Security audit context overflow | Raw PS data sent to model | Send only `pre_text` (compact ratings) |

---

## Demo Data Inventory

### My Day Data (17 files)

**Calendar** (`calendar.ics`): 10 events for Saturday Feb 7, 2026
- Breakfast with Kevin, Call with Rachel Martinez, Team Huddle, Prep Window, Car to Mountain Winery, Dry Run, Guest Arrival & Wine Tasting, Dinner & Fireside Discussion, Demo Stations, Late Dinner with David Park

**Tasks** (`tasks.csv`): 7 items (3 High, 3 Medium, 1 Low priority)

**Emails** (`Inbox/`): 15 .eml files spanning urgent, action, and FYI categories

### Agent Demo Data
- `contract_nda_vertex_pinnacle.txt` — NDA contract for Auditor demo
- `Board_Strategy_Review_Transcript_Jan2026.txt` — Meeting transcript
- `loan_application_sample.txt` — Sample document with PII

### Field Inspection Photos
- `inspection_photos/` — 5 preset photos: water_damage, structural_crack, mold, electrical_hazard, trip_hazard
