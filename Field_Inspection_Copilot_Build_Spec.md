# Field Inspection Copilot — Build Spec for Claude Code

## Project Context

This is a **new mode** being added to the existing Surface NPU Demo Flask application. It is NOT a separate app. It integrates with the existing infrastructure: Foundry Local runtime (localhost:5272), Phi-4 Mini model, the Two-Brain Router, Trust Receipt system, and Tokenomics counter.

**Target event:** MWC Barcelona, March 2–5, 2026
**Target hardware:** Surface Laptop with Intel Core Ultra processor (NPU)
**Runtime:** Foundry Local serving Phi-4 Mini on localhost:5272 using OpenAI-compatible Python client
**Framework:** Flask (existing app, ~6,800+ lines)
**Key constraint:** Everything runs in airplane mode. Zero network calls during the demo flow.

---

## Existing App Architecture (Reference)

Before building, familiarize yourself with the existing codebase structure:

- **Main Flask app:** `app.py` (or equivalent entry point)
- **Templates:** `templates/` directory with Jinja2 HTML templates
- **Static assets:** `static/` directory (CSS, JS, images)
- **Existing modes:** AI Agent chat, My Day briefing, Clean Room Auditor, ID Verification
- **Shared modules:**
  - Router module (Two-Brain escalation logic)
  - Trust Receipt system (local processing confirmation UI)
  - Tokenomics counter (tracks local vs cloud token usage and cost)
  - Foundry Local client wrapper (OpenAI Python client pointed at localhost:5272)
  - NPU auto-detection (Intel/Qualcomm hardware detection)

**Important:** Study the existing route patterns, template inheritance, and client wrapper before starting. Match the existing code style, naming conventions, and module organization.

---

## Build Milestones

Each milestone is designed to be a standalone, testable increment. Complete and test each one before moving to the next. They are ordered by dependency — later milestones build on earlier ones.

---

### Milestone 1: Inspection Mode Scaffold

**Goal:** New "Field Inspection" mode accessible from the app nav, with an empty workspace UI that loads and renders correctly.

**Routes to add:**
```
GET /inspection → renders the inspection workspace template
```

**Template:** `templates/inspection.html`
- Extends the base template (same as other modes)
- Navigation link added to the shared nav bar alongside existing modes
- Workspace layout with four panel areas (stubbed with placeholder content):
  - **Left panel:** Structured form with empty fields: Location, Date/Time, Reported Issue, Source
  - **Center panel:** Photo grid area (empty state: "No photos captured")
  - **Right panel:** Findings log + Report draft area (empty state)
  - **Bottom bar:** Tokenomics counter (reuse existing component), status indicators

**Static assets:**
- `static/css/inspection.css` — workspace layout styles
- `static/js/inspection.js` — empty JS file, will be populated in later milestones

**Acceptance criteria:**
- [ ] `/inspection` loads without errors
- [ ] Nav bar shows "Field Inspection" alongside existing modes
- [ ] Four-panel layout renders responsively on Surface screen resolution (2880x1920 or similar)
- [ ] Tokenomics counter displays in bottom bar with 0/0/$0.00 initial state
- [ ] Page works in airplane mode (no external resource dependencies)

---

### Milestone 2: Voice Capture + Transcription + Field Extraction

**Goal:** User taps a mic button, speaks, and the app transcribes speech locally then extracts structured fields into the form.

**Routes to add:**
```
POST /inspection/transcribe
  Input: audio blob (WAV or WebM from MediaRecorder)
  Output: JSON {
    "transcript": "full text",
    "fields": {
      "location": "Building C, 2nd Floor, North Corridor",
      "datetime": "2026-03-03T10:15:00",
      "reported_issue": "Water Staining",
      "source": "Property Manager Report"
    }
  }
```

**Implementation approach — two-pass inference:**

1. **Pass 1 — Transcription:** Send audio to Phi-4 Mini for speech-to-text. If Phi-4 Mini doesn't support direct audio input via Foundry Local, use a local Whisper-compatible model or browser-side Web Speech API as the transcription layer, then pass the text to Phi-4 Mini for field extraction.

2. **Pass 2 — Field extraction:** Send the raw transcript to Phi-4 Mini with a system prompt that constrains output to a JSON schema:
```
System: You are a field extraction engine for inspection reports. Given a spoken
transcript, extract structured fields. Respond ONLY with valid JSON matching this
schema: {"location": string, "datetime": string, "reported_issue": string,
"source": string}. If a field cannot be determined, use null.
```

**Frontend:**
- Mic button in the form area — uses `navigator.mediaDevices.getUserMedia({audio: true})` + `MediaRecorder` API
- Recording state indicator (pulsing red dot or similar)
- On stop: send audio blob to `/inspection/transcribe`
- On response: animate field population — each field fills sequentially with a subtle fade/slide-in (150ms stagger between fields)
- Full transcript appears in a collapsible panel below the form
- Update tokenomics counter with tokens consumed

**Critical UX detail:** The field population must be **visibly animated** — fields appearing one by one, not all at once. This is the "it understood me" moment. Use CSS transitions or JS animations to stagger the field fills.

**Fallback strategy:** If speech-to-text is unreliable during testing, implement a "retry" button that loads a pre-scripted transcript and runs only the field extraction pass. This serves as both a dev shortcut and a live demo safety net.

**Acceptance criteria:**
- [ ] Mic button captures audio and sends to backend
- [ ] Transcription returns readable text from spoken input
- [ ] Structured fields extract correctly from the transcript
- [ ] Form fields animate in sequentially on the frontend
- [ ] Tokenomics counter updates after transcription completes
- [ ] Fallback "retry with scripted input" button works

---

### Milestone 3: Camera Capture + Constrained Vision Classification

**Goal:** User photographs a prop image with the Surface camera. The local vision model classifies the image into a constrained category with severity and confidence.

**Routes to add:**
```
POST /inspection/classify
  Input: image file (JPEG from camera capture)
  Output: JSON {
    "category": "Water Damage",          // enum: see below
    "severity": "Moderate",               // enum: Low, Moderate, High, Critical
    "confidence": 82,                     // integer 0-100
    "explanation": "Discoloration pattern consistent with slow water leak"
  }
```

**Constrained category set (non-negotiable):**
- Water Damage
- Structural Crack
- Mold
- Electrical Hazard
- Trip Hazard

**System prompt for vision classification:**
```
System: You are a building inspection image classifier. Analyze the image and
classify the visible issue. Respond ONLY with valid JSON matching this schema:
{
  "category": one of ["Water Damage", "Structural Crack", "Mold", "Electrical Hazard", "Trip Hazard"],
  "severity": one of ["Low", "Moderate", "High", "Critical"],
  "confidence": integer 0-100,
  "explanation": string (one sentence max)
}
Do not include any text outside the JSON object.
```

**Frontend:**
- "Capture Photo" button that opens the device camera via `navigator.mediaDevices.getUserMedia({video: {facingMode: "environment"}})`
- Live camera preview in the center panel
- Tap to capture → snapshot saved as JPEG
- Photo appears in the photo grid
- Classification card appears below/beside the photo after inference returns:
  - Category label (large, color-coded by type)
  - Severity badge
  - Confidence percentage with visual indicator (progress bar or ring)
  - One-line explanation
- Update tokenomics counter

**Confidence threshold logic (for Step 6 integration later):**
- confidence >= 75 → finding proceeds normally (green indicator)
- confidence 60-74 → flagged for potential escalation (amber indicator)
- confidence < 60 → flagged as unreliable (red indicator, suggest re-capture)

Store the confidence value in the finding data — it will drive the Router escalation in Milestone 7.

**Acceptance criteria:**
- [ ] Camera opens and displays live preview
- [ ] Photo capture works and image appears in grid
- [ ] Classification returns valid constrained JSON
- [ ] Classification card renders with category, severity, confidence, explanation
- [ ] Confidence badge color-codes correctly by threshold
- [ ] Tokenomics counter updates
- [ ] Works with printed photo props (test with actual prop images)

---

### Milestone 4: Pen Annotation Overlay + Handwriting Extraction

**Goal:** User annotates the captured photo with Surface Pen — circles, arrows, handwritten notes. The app captures the ink layer and extracts handwritten text.

**Routes to add:**
```
POST /inspection/annotate
  Input: JSON {
    "image_id": "finding_001",
    "ink_strokes": [...],           // array of stroke data from canvas
    "ink_image": base64_png         // rendered ink overlay as image
  }
  Output: JSON {
    "extracted_text": "Check pipe above",
    "annotation_type": "Freehand circle + directional arrow + margin note",
    "linked_finding": "finding_001"
  }
```

**Frontend — Canvas annotation layer:**
- When a photo is selected in the grid, it opens in a full-width annotation canvas
- Canvas sits on top of the photo image as a transparent overlay
- Pen input captured via Pointer Events API (`pointerdown`, `pointermove`, `pointerup`)
  - Use `pointerType === "pen"` to detect Surface Pen specifically
  - Also support touch/mouse for testing without pen hardware
- Ink rendering: red stroke, 3px width for visibility
- Store stroke data as coordinate arrays for each stroke
- "Done Annotating" button → renders the ink layer to a PNG, sends to backend
- Side panel shows extracted text result with "Linked to Finding #1" label

**Handwriting extraction approach:**
- Render the ink strokes to a clean PNG (white background, black strokes for contrast)
- Send to Phi-4 Mini vision with prompt:
```
System: Extract any handwritten text visible in this image. Return ONLY the
extracted text as a plain string. If no readable text is found, return "No text detected".
```

**Acceptance criteria:**
- [ ] Pen strokes render on the canvas overlay in real time
- [ ] Ink overlay preserves position relative to the underlying photo
- [ ] "Done Annotating" captures the ink layer correctly
- [ ] Handwriting extraction returns readable text from written notes
- [ ] Extracted text appears in the side panel linked to the finding
- [ ] Annotated photo (original + ink overlay composited) is stored for the report
- [ ] Works with Surface Pen, touch input, and mouse

---

### Milestone 5: Report Generation

**Goal:** All inputs (voice transcript, structured fields, photo + classification, pen annotations) are synthesized into a structured inspection report.

**Routes to add:**
```
POST /inspection/report
  Input: JSON {
    "fields": { location, datetime, reported_issue, source },
    "findings": [
      {
        "id": "finding_001",
        "classification": { category, severity, confidence, explanation },
        "photo_base64": "...",
        "annotations": { extracted_text, annotation_type },
        "transcript_excerpt": "..."
      }
    ]
  }
  Output: JSON {
    "report_html": "<div class='report'>...</div>",
    "report_text": "plain text version",
    "summary": "Executive summary paragraph",
    "risk_rating": "Moderate",
    "next_steps": ["Schedule plumber inspection", "Document for insurance claim"]
  }
```

**System prompt for report generation:**
```
System: You are an inspection report generator. Given structured inspection data,
produce a professional inspection report. Include: executive summary, finding
details with severity and confidence, risk rating, and recommended next steps.
Output as clean HTML with semantic tags. Keep language professional and concise.
```

**Frontend — Report panel:**
- "Generate Report" button becomes active when at least one finding exists
- Report renders in the right panel as a styled HTML preview that looks like a professional document:
  - Header block: Property, date, inspector, report ID
  - Executive summary paragraph
  - Finding detail cards (reusing the classification card layout + adding photo and annotation)
  - Risk rating section
  - Recommended next steps
- Tokenomics counter updates with final generation token count
- Display cumulative totals: "X local tokens processed, $0.00 cloud cost, 0 bytes transmitted"

**Acceptance criteria:**
- [ ] Report generates from all collected data
- [ ] Report HTML renders as a professional-looking document in the panel
- [ ] All inputs are represented: transcript, classification, annotated photo, extracted notes
- [ ] Risk rating and next steps are contextually appropriate
- [ ] Tokenomics counter shows cumulative totals
- [ ] Report generation works with 1 finding and with 2+ findings

---

### Milestone 6: Translation

**Goal:** One-tap translation of the complete report into Spanish (or other target language).

**Routes to add:**
```
POST /inspection/translate
  Input: JSON {
    "report_text": "...",
    "target_language": "Spanish"
  }
  Output: JSON {
    "translated_html": "<div class='report'>...</div>",
    "source_language": "English",
    "target_language": "Spanish"
  }
```

**System prompt:**
```
System: Translate the following inspection report into {target_language}. Maintain
the exact same structure, formatting, and section organization. Use professional
{target_language} appropriate for a construction/inspection context. Output as
clean HTML matching the source structure.
```

**Frontend:**
- "Translate to Spanish" button below the report panel
- On click: report panel transitions to Spanish version
- Brief side-by-side flash (500ms) showing EN | ES before settling on the translated version
- Language toggle to switch back to English
- Tokenomics counter updates
- Visual indicator: "Translated locally — no cloud API call"

**Acceptance criteria:**
- [ ] Translation produces readable Spanish output
- [ ] Report structure and sections are preserved
- [ ] Language toggle switches between EN and ES
- [ ] Tokenomics counter updates
- [ ] No network calls made (verify in dev tools)

---

### Milestone 7: Router Escalation + Dashboard Tally

**Goal:** Integrate the existing Two-Brain Router for low-confidence findings, and add the closing dashboard tally view.

**This milestone has two parts:**

#### Part A: Router Escalation

**No new routes needed** — reuse the existing Router module/logic.

**Trigger:** When a finding has confidence between 60-74% (set in Milestone 3), display the escalation decision dialog.

**Escalation dialog UI:**
- Modal or inline panel with two clear options side by side:
- **Left: "Escalate to Cloud"**
  - "Send this photo to a frontier vision model for detailed analysis"
  - Payload preview: "Sending: 1 photo (XXX KB)"
  - Withheld preview: "Withheld: voice transcript, pen annotations, report draft"
- **Right: "Keep Local" (highlighted as preferred)**
  - "Proceed with local classification. Flag for manual expert review."
  - "Data leaving device: None"
  - "Cost: $0.00"

**On "Keep Local" (demo default path):**
1. Lock animation plays (reuse existing Trust Receipt animation)
2. Banner: "Inspection completed locally"
3. Finding is flagged in the report as "Flagged for on-site expert review"
4. Tokenomics counter confirms zero cloud usage

**On "Escalate" (optional demo path, requires connectivity):**
1. Show what WOULD be sent (just the photo)
2. In airplane mode: graceful failure message "No connectivity — keeping data local"
3. This becomes a natural demonstration of the offline resilience story

#### Part B: Dashboard Tally

**Frontend component:** Full-screen or large-panel summary view.

**Layout:**
```
┌──────────────────────────┬──────────────────────────┐
│   LOCAL AI TASKS          │   CLOUD TASKS            │
│   ✓ Speech-to-text       │                          │
│   ✓ Field extraction     │         0                │
│   ✓ Vision classification│                          │
│   ✓ Handwriting recog    │                          │
│   ✓ Report generation    │                          │
│   ✓ Translation          │                          │
│   ✓ Routing logic        │                          │
├──────────────────────────┴──────────────────────────┤
│ Total tokens: ~520 | Cost: $0.00 | Transmitted: 0B  │
└─────────────────────────────────────────────────────┘
```

- Green left panel with checkmarks for each completed local task
- Red/empty right panel with large "0" for cloud tasks
- Bottom summary bar with cumulative tokenomics
- "Close" button returns to the inspection workspace

**Trigger:** Automatically appears after report generation + escalation decision are complete, OR via a "Show Summary" button.

**Acceptance criteria:**
- [ ] Low-confidence finding triggers escalation dialog
- [ ] "Keep Local" path fires Trust Receipt animation and updates report
- [ ] "Escalate" path in airplane mode fails gracefully
- [ ] Payload diff (what would be sent vs withheld) displays correctly
- [ ] Dashboard tally renders with all completed task checkmarks
- [ ] Tokenomics totals are accurate and match the bottom bar counters
- [ ] Dashboard is visually clean enough to photograph from 15 feet away

---

## Testing & Validation Checklist

Before considering the feature MWC-ready:

### Functional
- [ ] Complete end-to-end flow (Steps 1-7) works in airplane mode
- [ ] All prop images classified correctly with expected confidence ranges
- [ ] Voice transcription handles the scripted demo phrases reliably
- [ ] Pen annotation works with Surface Pen on Intel Core Ultra device
- [ ] Report generates with all inputs synthesized
- [ ] Translation produces clean Spanish output
- [ ] Router escalation dialog triggers at correct confidence threshold
- [ ] Dashboard tally accurately reflects all completed tasks

### Hardware-Specific
- [ ] Tested on Intel Core Ultra (target MWC hardware) — not just Qualcomm
- [ ] Camera capture works with Surface device camera
- [ ] Microphone capture works with Surface device mic
- [ ] Pen input works with Surface Pen via Pointer Events
- [ ] Foundry Local model loading is pre-warmed before demo start
- [ ] First inference call after warm-up responds within 3 seconds

### Demo Reliability
- [ ] Run full demo flow 10 consecutive times without failure
- [ ] Fallback "scripted input" works for voice step
- [ ] Pre-captured photo fallback works for camera step
- [ ] Loading states display contextual messages during inference ("Analyzing image...", "Generating report...")
- [ ] No external resource dependencies (fonts, CDN scripts, API calls)

---

## Notes for Claude Code Sessions

- **Work iteratively by milestone.** Don't try to build everything at once. Complete Milestone 1, test it, then move to Milestone 2.
- **Match existing code patterns.** Study the existing Flask routes, Jinja2 templates, and JS modules before writing new code. Consistency matters more than cleverness.
- **Test in airplane mode early and often.** If something loads an external font, CDN script, or makes any network call, it will break the demo.
- **The Foundry Local client pattern** is already established in the codebase — it's an OpenAI Python client pointed at `http://localhost:5272/v1`. Reuse the existing wrapper.
- **Constrained JSON output** from Phi-4 Mini is achieved via system prompts with explicit schema instructions. The model is generally compliant but add JSON parsing with error handling and retry logic.
- **When in doubt, hardcode a fallback.** For a live demo, a reliable fallback beats a brittle dynamic path every time. Pre-baked responses for each step are not cheating — they're professionalism.
