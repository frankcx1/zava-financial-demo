# CLAUDE.md - Project Guidelines for Claude Code

## Project Overview

This is a single-file Flask demo app (`npu_demo_flask.py`) showcasing on-device AI capabilities using NPU hardware via Foundry Local. Supports both Intel Core Ultra (Lunar Lake) and Qualcomm Snapdragon X (ARM64) — silicon is auto-detected at startup. Zero cloud dependencies, zero data egress.

**Architecture:** Python Flask backend (localhost:5000) → Foundry Local runtime → SLM on NPU
- Intel: Phi-4 Mini on Intel Core Ultra NPU
- Qualcomm: Phi-3.5 Mini on Snapdragon X NPU (QNN)

## Key Files

| File | Purpose |
|------|---------|
| `npu_demo_flask.py` | Main Flask app (~2,700 lines, single file with HTML/CSS/JS inline) |
| `docs/TECHNICAL_GUIDE.md` | Detailed technical documentation |
| `README.md` | Project overview and setup instructions |
| `docs/specs/` | Feature specifications (Auditor tab, My Day, Save Summary) |
| `docs/moltbot-shim/` | OpenClaw/MoltBot tool-calling shim project (separate from Flask app) |
| `docs/marketing/` | Social posts, exec summaries, demo scripts |

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

## Four Tabs (sidebar navigation)

### Tab 1: AI Agent (default)
Governed tool execution (read, write, exec) with approval gates and audit trail. Demonstrates "AI with hands, but on a leash."

### Tab 2: My Day
Executive morning briefing from calendar, email, and task data. Cross-references data sources for actionable insights.

### Tab 3: Auditor
Clean room audit analysis.

### Tab 4: ID Verification
On-device OCR (Tesseract.js) + AI analysis for document verification.

## Security Measures

1. **File System Jailing:** All read/write operations restricted to `DEMO_DIR` via `os.path.realpath()` validation
2. **PowerShell Allowlist:** Only approved cmdlets (get-childitem, get-content, etc.)
3. **Network Binding:** Flask bound to `127.0.0.1` only
4. **Path Traversal Prevention:** Static file routes reject `..` and validate realpath
5. **Upload Restrictions:** Extension allowlist, secure_filename(), 16MB limit

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

## Token Budget

Phi Silica has ~4K context window:
- Brief Me: ~1,084 input + 800 output = ~1,884 total
- Agent chat: ~1,824 max tokens
- Compression hard cap: 3,600 chars for data payloads

## Performance

| Operation | Typical Latency |
|-----------|----------------|
| Brief Me | 40-50s |
| Agent chat (simple) | 5-10s |
| Agent chat (tool + summary) | 15-25s |
| OCR | 3-8s |

Power draw: ~5W sustained on NPU (~0.06 Wh per briefing)
