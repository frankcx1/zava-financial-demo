# CLAUDE.md - Project Guidelines for Claude Code

## Project Overview

This is a single-file Flask demo app (`npu_demo_flask.py`) showcasing on-device AI capabilities using Intel Core Ultra NPU and Microsoft's Phi Silica model via Foundry Local. The app demonstrates three AI-powered capabilities with zero cloud dependencies and zero data egress.

**Architecture:** Python Flask backend (localhost:5000) → Foundry Local runtime (localhost:5272) → Phi Silica 3.8B on NPU

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
- Foundry Local running on `localhost:5272` with `phi-silica` model loaded
- Python 3.10+ with Flask, OpenAI SDK
- Demo data files in `C:\Users\{user}\Documents\Demo\My_Day\`

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

- Calendar: `Documents/Demo/My_Day/calendar.ics`
- Tasks: `Documents/Demo/My_Day/tasks.csv`
- Emails: `Documents/Demo/My_Day/Inbox/*.eml`
- Meeting transcript: `Documents/Demo/Board_Strategy_Review_Transcript_Jan2026.txt`

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
