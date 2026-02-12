# Local NPU AI Assistant — Technical Guide

## Overview

A single-file Flask application (`npu_demo_flask.py`) that demonstrates three AI-powered capabilities running entirely on-device using the Intel Core Ultra NPU and Microsoft's Phi Silica model via Foundry Local. Zero cloud dependencies. Zero data egress.

**Architecture:** Python Flask backend (localhost:5000) → Foundry Local runtime (localhost:5272) → Phi Silica 3.8B on NPU

**File:** `C:\Users\frankbu\OneDrive - Microsoft\NPU\npu_demo_flask.py` (~2,676 lines, single file)

---

## How to Run

```
python npu_demo_flask.py
```

**Prerequisites:**
- Foundry Local running on `localhost:5272` with the `phi-silica` model loaded
- Python 3.10+ with Flask, OpenAI SDK installed
- Tesseract.js files bundled in `tesseract/` directory (included)
- Demo data files in `C:\Users\{user}\Documents\Demo\My_Day\` (calendar.ics, tasks.csv, Inbox/*.eml)

**Ports:**
- App: `http://127.0.0.1:5000` (bound to localhost only)
- Foundry Local: `http://localhost:5272/v1` (OpenAI-compatible API)

---

## Tab 1: My Day — Executive Morning Briefing

### Value Proposition
Transforms raw calendar, email, and task data into a cross-referenced executive briefing — the "chief of staff in your pocket" story. This is the emotional closer for CEO audiences: their world, reflected back by AI running on the device in their hand.

### Data Sources
| Source | Format | Location | Parser |
|--------|--------|----------|--------|
| Calendar | iCalendar (.ics) | `Demo/My_Day/calendar.ics` | `parse_ics()` — regex-based, no external libs |
| Tasks | CSV | `Demo/My_Day/tasks.csv` | `parse_tasks_csv()` — built-in `csv.DictReader` |
| Emails | RFC 5322 (.eml) | `Demo/My_Day/Inbox/*.eml` | `parse_eml()` — built-in `email` module |

### Features

#### Data Cards (click to peek)
Three cards at the top showing counts (Emails, Events Today, Tasks Due). Click any card to expand a dropdown showing the actual data:
- **Emails**: sender name + subject line for each message
- **Events**: time range, title, location
- **Tasks**: color-coded priority tag (red/yellow/green) + task name

Data is fetched from `GET /my-day-data` on first click and cached. Click again or click outside to close.

#### Brief Me
The primary feature. Reads all three data sources, compresses them into a single prompt, and sends to Phi Silica for a structured executive briefing.

**Flow:**
1. `POST /brief-me` triggers streaming JSONL response
2. Backend parses all data sources (progress streamed to UI)
3. `compress_for_briefing()` compresses ~32 data items into ~3,600 characters:
   - Calendar events with up to 3 description lines each
   - Tasks with priority and truncated notes
   - First 6 emails get body snippets, remainder get subject only
   - Hard cap at 3,600 chars to stay within Phi Silica's ~4K context window
4. Combined with `BRIEFING_SYSTEM_PROMPT` (~723 chars) coaching the model to cross-reference across data sources
5. Phi Silica generates structured output: narrative summary → ACTIONS → PEOPLE TO KNOW → KEY WARNINGS
6. Frontend splits output into executive summary card + collapsible breakdown sections
7. Footer pulses with: "Analyzed 15 emails, 10 events, 7 tasks in Xs on NPU"

**Token Budget:** ~1,084 input tokens + 800 max output tokens = ~1,884 total (~2,100 tokens headroom in Phi's 4K window)

**Cross-references the model surfaces:**
- Sarah Chen's late-night email → Q4 APAC numbers action item
- Jessica Torres' NDA flag → warning about David Park at dinner
- James Liu's governance question → Alex Kim's updated deck
- Rachel Martinez's birthday → Mountain Winery wine case opportunity

#### Triage Inbox
`POST /triage-inbox` — Categorizes all 15 emails into URGENT / ACTION NEEDED / FYI with recommended actions for each.

#### Prep for Next Meeting
`POST /prep-next-meeting` — Skips logistics events (breakfast, car, prep window) and generates a prep brief for the first substantive meeting with attendees. Cross-references related emails and tasks.

---

## Tab 2: AI Agent — Governed Tool Execution

### Value Proposition
Demonstrates AI that can act — read files, write documents, run system commands — under explicit policy controls with full auditability. This is the "governed delegation" story: AI with hands, but on a leash.

### Architecture
Uses a "toolsViaPrompt" shim since Phi Silica doesn't have native tool-calling:
1. Compact system prompt defines available tools with `[TOOL_CALL]` markers
2. Model outputs plan text or a `[TOOL_CALL]{"name":"...", "arguments":{...}}[/TOOL_CALL]` block
3. Backend parses markers with regex, executes the tool, feeds result back
4. Model generates a spoken summary of the result

### Available Tools
| Tool | What It Does | Constraints |
|------|-------------|-------------|
| `read` | Read a file and return contents (max 5,000 chars) | Path must resolve within `DEMO_DIR` |
| `write` | Create or overwrite a file | Path must resolve within `DEMO_DIR` |
| `exec` | Run a PowerShell command | Allowlisted cmdlets only (see Security) |

### Sidebar Buttons

#### Demo Flow
| Button | Action | Demo Purpose |
|--------|--------|-------------|
| Meeting Agenda | Creates `board_meeting_prep.txt` with a full agenda | "AI that can act, not just talk" |
| Analyze Strategy | Reads `strategy_2026.txt`, extracts 3 key takeaways | File reading + summarization |
| List Documents | Runs `Get-ChildItem` on Demo folder | System command under policy |
| Review & Summarize | **Approval gate flow** — see below | Governance showcase |

#### Documents
- **Load File (+)**: Upload PDF/DOCX/TXT/MD via file picker (also available as + button in chat input). Backend extracts text, saves as .txt in Demo folder for agent access.
- **Summarize Doc**: Asks AI to summarize the loaded document
- **Detect PII**: Scans loaded document for personally identifiable information

#### Session
- **AI Action Log**: Shows trust receipt banner (deterministic counts) then asks AI for 5-bullet executive summary of all actions taken
- **Clear Chat**: Resets chat and audit trail

### Approval Gate (Review & Summarize)

The governance centerpiece. When clicked:

1. Prompt instructs model to output a `[PLAN]...[/PLAN]` block listing files it wants to access
2. Frontend detects plan markers (or heuristic: bullet list + no tool call + pending flag)
3. Renders an **approval card** with amber border:
   - "This action requires approval" header
   - Parsed plan body showing files and intent
   - Large Approve (green) and Deny (red) buttons
   - Policy footer: "Read-only within approved folder. All actions logged."
4. **Approve**: Card turns green, sends "APPROVED. Proceed..." to agent, logged to audit trail
5. **Deny**: Card turns red, "Action denied by user. No files were accessed.", logged to audit trail

### Trust Receipt

When "AI Action Log" is clicked:
1. Fetches audit log from `GET /audit-log`
2. Computes deterministic summary: "X files accessed, Y documents created, Z system commands"
3. Displays styled banner: count summary + "All actions local. No network calls. No data egress."
4. Sends detailed log to AI for a 5-bullet executive briefing

### Audit Trail
Every tool execution is logged with timestamp, tool name, arguments, success/failure, and elapsed time. Displayed in a collapsible panel labeled "AI Actions (Logged)" with the subheading "All actions recorded locally for review."

---

## Tab 3: ID Verification — On-Device OCR + AI Analysis

### Value Proposition
Demonstrates that the same local AI pattern extends to vision/OCR use cases in regulated industries (healthcare, government, financial services). Camera capture, text extraction, and AI analysis all happen on-device — no image data transmitted anywhere.

### Flow
1. **Camera Selection**: Enumerates available cameras, labels Front/Rear/Built-in
2. **Image Capture**: Live video preview → capture frame to canvas → display as PNG
3. **OCR (Tesseract.js)**: Locally-bundled Tesseract.js v5.1.1 extracts text from the captured image. All files served from Flask — no CDN dependency. Works fully offline.
4. **AI Analysis (Phi Silica)**: `POST /analyze-id` sends OCR text to the model with a structured extraction prompt. Returns: name, address, DOB, ID number, expiration, state, class, and validity status.
5. **Result Display**: Styled card with status badge (Valid/Expired/Review Needed), extracted fields table, and notes.

### Processing Steps (visible in UI)
| Step | Engine | Location |
|------|--------|----------|
| 1. Image Capture | Browser API | Local |
| 2. Text Extraction (OCR) | Tesseract.js 5.1.1 | Local (bundled) |
| 3. AI Analysis | Phi Silica on NPU | Local |

### Tesseract.js Local Bundle
All OCR files served from `tesseract/` directory via `/tesseract/<path>` route:
```
tesseract/
  tesseract.min.js          66 KB   Browser entry point
  worker.min.js            121 KB   Web worker
  core/
    tesseract-core-simd-lstm.wasm.js    3.8 MB   WASM (SIMD+LSTM)
    tesseract-core-simd.wasm.js         4.6 MB   WASM (SIMD)
    tesseract-core-lstm.wasm.js         3.8 MB   WASM (LSTM)
    tesseract-core.wasm.js              4.6 MB   WASM (fallback)
  lang/
    eng.traineddata.gz      10.9 MB  English language data
```

---

## Header Controls (All Tabs)

### Go Offline / Go Online
Two buttons in the header, visible on all tabs. Directly call `POST /network-toggle` which runs PowerShell `Disable-NetAdapter` / `Enable-NetAdapter` on Wi-Fi and Cellular adapters. Buttons show "Disabling..." / "Enabling..." during execution, then auto-refresh connectivity status.

### Offline Badge
Shows "Online" (green) or "Offline Mode" (amber). Updated by `GET /connectivity-check` which polls Wi-Fi adapter status and Foundry Local availability.

### Tab Transition Toasts
Subtle toast at bottom of viewport on tab switch:
- My Day: "Same local AI — now reading your day"
- AI Agent: "Same local AI — now with execution tools"
- ID Verification: "Same local AI — now verifying identity"

Reinforces that one NPU engine powers all three capabilities.

---

## Security Measures

### 1. File System Jailing
All `read` and `write` tool operations are restricted to `DEMO_DIR` (`C:\Users\{user}\Documents\Demo`).

```python
def _path_in_demo_dir(path):
    resolved = os.path.realpath(os.path.normpath(path))
    demo_resolved = os.path.realpath(DEMO_DIR)
    return resolved.startswith(demo_resolved + os.sep) or resolved == demo_resolved
```

Uses `os.path.realpath()` (resolves symlinks) rather than `os.path.abspath()` for stronger guarantees. Any path outside the approved folder returns: "Security Policy Violation: Access restricted to approved folder."

### 2. PowerShell Command Allowlist
Replaced blocklist with allowlist — only these cmdlets are permitted:

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
| `disable-netadapter` | Go offline (airplane mode demo) |
| `enable-netadapter` | Go online |

Everything else returns: "Security Policy: Only approved commands are permitted."

### 3. Network Binding
Flask bound to `127.0.0.1` only — not accessible from other devices on the same network.

### 4. Static File Path Traversal Prevention
Both `/logos/<path>` and `/tesseract/<path>` routes:
- Reject paths containing `..`
- Reject paths starting with `/` or `\`
- Validate `realpath` resolves within the expected directory
- Restrict to allowed MIME types (images for logos, JS/WASM/GZ for tesseract)

### 5. Upload Restrictions
- Extension allowlist: `.pdf`, `.docx`, `.txt`, `.md` only
- `secure_filename()` sanitization
- 16 MB size limit
- Uploaded files extracted to text, originals deleted

### 6. No External Dependencies at Runtime
- Foundry Local runs on `localhost:5272` (on-device)
- Tesseract.js fully bundled locally (no CDN)
- Flask serves all assets
- Zero outbound network calls during operation

### 7. Approval Gate
The Review & Summarize flow requires explicit user approval before the AI accesses files. Both approval and denial are logged to the audit trail.

### 8. Audit Trail
Every tool execution is logged with timestamp, tool name, arguments, success/failure, and elapsed time. The trust receipt provides a deterministic summary independent of the AI model.

---

## Key Constants

| Constant | Value |
|----------|-------|
| `DEFAULT_MODEL` | `phi-silica` |
| `OPENAI_BASE_URL` | `http://localhost:5272/v1` |
| `DEMO_DIR` | `~/Documents/Demo` |
| `MY_DAY_DIR` | `~/Documents/Demo/My_Day` |
| `MY_DAY_INBOX` | `~/Documents/Demo/My_Day/Inbox` |
| `MAX_CONTENT_LENGTH` | 16 MB |
| `Flask host` | `127.0.0.1` |
| `Flask port` | `5000` |
| `max_tokens (Brief Me)` | 800 |
| `max_tokens (Triage)` | 800 |
| `max_tokens (Prep)` | 500 |
| `max_tokens (Agent chat)` | 1024 |
| `Compression hard cap` | 3,600 chars |
| `PowerShell timeout` | 15s (general) / 30s (network) |

---

## API Endpoints Reference

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/` | Serve main HTML page |
| POST | `/chat` | Agent chat (streaming JSONL) |
| POST | `/brief-me` | Full morning briefing (streaming JSONL) |
| POST | `/triage-inbox` | Email triage (streaming JSONL) |
| POST | `/prep-next-meeting` | Next meeting prep (streaming JSONL) |
| GET | `/my-day-counts` | Card counts {events, tasks, emails} |
| GET | `/my-day-data` | Full parsed data for peek windows |
| POST | `/upload-to-demo` | File upload + text extraction |
| POST | `/analyze-id` | ID document AI analysis |
| GET | `/audit-log` | Return audit trail entries |
| DELETE | `/audit-log` | Clear audit trail |
| GET | `/connectivity-check` | Check Wi-Fi + NPU status |
| POST | `/network-toggle` | Enable/disable network adapters |
| GET | `/logos/<path>` | Serve logo images |
| GET | `/tesseract/<path>` | Serve Tesseract.js files |

---

## Performance Characteristics

| Operation | Typical Latency | Token Budget | Power Draw |
|-----------|----------------|--------------|------------|
| Brief Me | 40-50s | ~1,884 tokens total | ~5W sustained, ~225 joules |
| Agent chat (simple) | 5-10s | ~1,824 tokens max | ~5W |
| Agent chat (tool + summary) | 15-25s | Two model calls | ~5W |
| Triage Inbox | 30-40s | ~1,800 tokens | ~5W |
| Prep for Next Meeting | 15-25s | ~1,300 tokens | ~5W |
| OCR (Tesseract.js) | 3-8s | N/A (CPU/WASM) | Varies |
| ID Analysis | 5-10s | ~1,024 tokens | ~5W |

**Energy comparison:** A Brief Me briefing uses ~0.06 Wh — approximately 0.1% of a 58 Wh laptop battery. The equivalent cloud inference on a 300W GPU rack uses datacenter power, cooling, and network infrastructure.

---

## Demo Data Inventory

### My Day Data (17 files)

**Calendar** (`calendar.ics`): 10 events for Saturday Feb 7, 2026
- Breakfast with Kevin (AV walkthrough)
- Call with Rachel Martinez, CEO Apex Dynamics
- Team Huddle (Sandra, Jack, Kevin)
- Prep Window (priority items)
- Car to Mountain Winery
- Dry Run at Mountain Winery
- Guest Arrival & Wine Tasting
- Dinner & Fireside Discussion
- Demo Stations & Device Showcase
- Late Dinner with David Park (The Plumed Horse)

**Tasks** (`tasks.csv`): 7 items
- 3 High priority: Q4 APAC numbers, NDA flag, demo app test
- 3 Medium priority: governance deck, guest list, wine order
- 1 Low priority: Super Bowl suite details

**Emails** (`Inbox/`): 15 .eml files
- Urgent: Sarah Chen (Q4 numbers), Jessica Torres (NDA flag), Sandra Mitchell (event details)
- Action: James Liu (governance question), Alex Kim (deck update), Lisa Wang (David Park's EA)
- FYI: Travel desk, hotel, AV confirmation, demo stations, dress code, Super Bowl suite, flight, Dr. Patel reply, AI newsletter

### Agent Demo Data
- `strategy_2026.txt` — Corporate strategy document for agent to analyze
- `loan_application_sample.txt` — Sample document with PII for detection demo
- `board_meeting_prep.txt` — Created by the Meeting Agenda button during demo
