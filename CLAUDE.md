# CLAUDE.md - Project Guidelines for Claude Code

## Project Overview

This is a single-file Flask demo app (`npu_demo_flask.py`) showcasing on-device AI capabilities using NPU hardware via Foundry Local. Supports both Intel Core Ultra (Lunar Lake) and Qualcomm Snapdragon X (ARM64) — silicon is auto-detected at startup. Zero cloud dependencies, zero data egress.

**Architecture:** Python Flask backend (localhost:5000) → Foundry Local runtime → SLM on NPU
- Intel: Phi-4 Mini on Intel Core Ultra NPU
- Qualcomm: Phi-3.5 Mini on Snapdragon X NPU (QNN)

## Key Files

| File | Purpose |
|------|---------|
| `npu_demo_flask.py` | Main Flask app (~9,200 lines, single file with HTML/CSS/JS inline) |
| `docs/TECHNICAL_GUIDE.md` | Detailed technical documentation |
| `README.md` | Project overview and setup instructions |
| `docs/specs/` | Feature specifications (Auditor tab, My Day, Save Summary) |
| `docs/moltbot-shim/` | OpenClaw/MoltBot tool-calling shim project (separate from Flask app) |
| `docs/marketing/` | Social posts, exec summaries, demo scripts |
| `Field_Inspection_Copilot_Build_Spec.md` | Build spec for Tab 5 (7 milestones, MWC target) |
| `vision-service/` | C# Phi Silica Vision microservice (localhost:5100) |
| `tests/test_phase1.py` | Test suite (279 tests covering all features) |

## Running the App

```bash
python npu_demo_flask.py
```

**Prerequisites:**
- Foundry Local installed (`winget install Microsoft.FoundryLocal`)
- Python 3.10+ with Flask, OpenAI SDK, `foundry-local-sdk` (NOT the fake `foundry-local` pip package)
- Demo data ships in `demo_data/` within the project directory (self-contained)
- Run `setup.ps1` on a new device to install everything automatically

**Cross-platform notes:**
- On Windows-on-ARM, `platform.machine()` and `PROCESSOR_ARCHITECTURE` may report `AMD64`/`X64` due to emulation. Detection uses WMI CPU name as the authoritative source.
- The pip package `foundry-local` (v0.0.1) is a squatted fake. The real SDK is `foundry-local-sdk`.

## Architecture Notes

### Tool-Calling Shim
Phi Silica doesn't have native tool-calling support. The app uses a `toolsViaPrompt` shim:
1. System prompt defines tools with `[TOOL_CALL]` markers
2. Model outputs `[TOOL_CALL]{"name":"...", "arguments":{...}}[/TOOL_CALL]` blocks
3. Backend parses markers with regex, executes tool, feeds result back
4. Model generates spoken summary of result

### Known Limitation: Two-Step Agent Loop
The model hangs when making consecutive API calls (tool decision → followup summary). **Solution:** Use dedicated single-step endpoints that bypass the agent loop:
- `/summarize-doc` - Single model call for document summarization
- `/detect-pii` - Single model call for PII detection
- `/demo/meeting-agenda` - Single model call for agenda creation
- `/demo/analyze-strategy` - Single model call for strategy analysis
- `/demo/list-documents` - Single model call for directory listing
- `/demo/review-summarize` - Two-phase endpoint with approval gate

### Variable Scoping
Key state variables must be at script level (not inside DOMContentLoaded):
```javascript
var pendingApprovalReview = false;
var pendingSummarize = false;
var lastAssistantResponse = "";
```

## Five Tabs (sidebar navigation)

### Tab 1: AI Agent (default)
Governed tool execution (read, write, exec) with approval gates and audit trail. Demonstrates "AI with hands, but on a leash."

### Tab 2: My Day
Executive morning briefing from calendar, email, and task data. Cross-references data sources for actionable insights.

### Tab 3: Auditor
Dual-mode clean room analysis with mode selector:
- **Contract / Legal Review** — Structured risk analysis of contracts and NDAs with smart escalation to frontier model.
- **Marketing / Campaign Review** — CELA compliance check for marketing assets. Document-first architecture (mirrors contract flow): sends actual document text to the model, which reads it and identifies compliance claims itself. Falls back to hardcoded findings for demo docs or regex+metadata for uploaded docs if model output doesn't parse (< 2 claims). Progressive reveal: claims card → verdict → summary → escalation cascade with status messages and pauses. Emits claims card, verdict (SELF-SERVICE OK / CELA INTAKE REQUIRED), and escalation consent flow.

### Tab 4: ID Verification
On-device OCR (Tesseract.js) + AI analysis for document verification.

### Tab 5: Field Inspection
On-site assessment copilot for MWC Barcelona demo (March 2-5, 2026). Seven-milestone build per `Field_Inspection_Copilot_Build_Spec.md`.

**Architecture:** Four-panel workspace (form, photo, report, bottom bar) with milestone-scoped JS IIFEs.

**Milestones (completed):**
- **M1 — Scaffold:** Nav item, tab button, four-panel grid layout, CSS, tab switching
- **M2 — Voice Capture + Field Extraction:** Web Speech API mic button, scripted input fallback ("Inspector Sarah Chen at Building C..."), `POST /inspection/transcribe` sends transcript to Phi-4 Mini for JSON field extraction (location, datetime, issue, source), staggered field animation
- **M3 — Camera Capture + Classification:** getUserMedia camera, demo photo button cycling 5 presets (water_damage 82%, structural_crack 72%, mold 88%, electrical_hazard 91%, trip_hazard 85%), `POST /inspection/classify` with three-tier path (demo presets → Phi Silica Vision via localhost:5100 → Phi-4 Mini text fallback), classification card with confidence thresholds (green ≥75, amber 60-74, red <60), findings log, photo grid with severity badges
- **M4 — Pen Annotation:** Deferred pending LAF token for handwriting extraction
- **M5 — Report Generation:** `POST /inspection/report` sends fields + findings to Phi-4 Mini, generates professional HTML report with summary/risk rating/next steps, hardcoded fallback on error, report draft panel, "Regenerate Report" button
- **M6 — Translation:** `POST /inspection/translate` sends report HTML for Spanish translation, language toggle (EN/ES), 500ms side-by-side flash before settling, "no cloud API call" status
- **M7 — Router Escalation + Dashboard Tally:** Escalation dialog triggers on 60-74% confidence findings (structural_crack at 72% demos this), two options: "Escalate to Cloud" (shows payload preview, graceful offline failure) and "Keep Local" (lock animation, flags for expert review). Dashboard tally overlay: 6 local AI tasks with checkmarks vs 0 cloud tasks, cumulative tokenomics.

**Key JS patterns:**
- Each milestone is a self-contained IIFE: `// ── Field Inspection: Milestone N — ... ──`
- Cross-milestone communication via `window._inspFindings`, `window._inspReportData`, `window._inspCompletedTasks`, `window._inspCheckEscalation`, `window._inspShowDashboard`
- Status bar shared: `inspStatusDot`, `inspStatusText`, `inspTokenCount`

**Vision Service** (`vision-service/`):
- C# ASP.NET Core on localhost:5100, wraps Phi Silica `ImageDescriptionGenerator` (Windows App SDK 1.7 experimental3)
- Endpoints: `/health`, `/describe`, `/classify`, `/extract-text`
- `ImageDescriptionGenerator` is in `Microsoft.Windows.AI.Generative` namespace (not Imaging)
- `ImageBuffer` is in `Microsoft.Graphics.Imaging`
- LAF token integrated, PFN: `Microsoft.NPUDemo.VisionService_5z9edc3e9tzrc`
- Awaiting confirmation from Phi Silica team on feature ID for vision API + MSIX packaging requirement
- Currently runs unpackaged; `Package.appxmanifest` and assets ready for MSIX switch

## Security Measures

1. **File System Jailing:** All read/write operations restricted to `DEMO_DIR` via `os.path.realpath()` validation
2. **PowerShell Allowlist:** Only approved cmdlets (get-childitem, get-content, etc.)
3. **Network Binding:** Flask bound to `127.0.0.1` only
4. **Path Traversal Prevention:** Static file routes reject `..` and validate realpath
5. **Upload Restrictions:** Extension allowlist, secure_filename(), 16MB limit
6. **PII Scanner:** `_scan_pii()` detects SSNs, emails, phone numbers, and person names (curated list via `_DEMO_PERSON_NAMES` regex). Runs on both marketing and contract flows. `_redact_text()` replaces findings with `[REDACTED Type]` before any escalation to frontier models.

## Demo Data Location

All demo data lives in `demo_data/` within the project directory (self-contained, no external paths):

- Calendar: `demo_data/My_Day/calendar.ics`
- Tasks: `demo_data/My_Day/tasks.csv`
- Emails: `demo_data/My_Day/Inbox/*.eml`
- Meeting transcript: `demo_data/Board_Strategy_Review_Transcript_Jan2026.txt`
- NDA contract: `demo_data/contract_nda_vertex_pinnacle.txt`

## Common Debugging

### Model Hangs on Second API Call
Use dedicated single-step endpoints instead of the agent loop.

### Save Button Not Appearing
Check that `pendingSummarize` and `lastAssistantResponse` are at script level.

### Markdown Not Rendering
Apply `mdToHtml()` function to all code paths rendering model output.

### Model Hallucinating File Paths
Use dedicated endpoints that control file paths directly instead of letting the model choose paths.

### Flask Serving Stale Code After Edits
Delete `__pycache__/npu_demo_flask.cpython-*.pyc` and restart. Flask debug mode's auto-reloader doesn't always pick up changes reliably.

## Token Budget

Phi Silica has ~4K context window:
- Brief Me: ~1,084 input + 800 output = ~1,884 total
- Agent chat: ~1,824 max tokens
- Compression hard cap: 3,600 chars for data payloads
- Marketing CELA review: ~500 input + 800 output = ~1,300 total (Intel); ~1,650 input + 1,200 output = ~2,850 total on Qualcomm

## Performance

| Operation | Typical Latency |
|-----------|----------------|
| Brief Me | 40-50s |
| Agent chat (simple) | 5-10s |
| Agent chat (tool + summary) | 15-25s |
| Marketing CELA review | 15-35s |
| OCR | 3-8s |
| Field Inspection: transcribe | 5-10s |
| Field Inspection: classify (demo) | 1.5s (simulated) |
| Field Inspection: report | 10-20s |
| Field Inspection: translate | 10-20s |

Power draw: ~5W sustained on NPU (~0.06 Wh per briefing)
