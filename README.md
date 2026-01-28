# Surface NPU Demo — Local AI Assistant

A branded demo application showcasing on-device AI capabilities using the Neural Processing Unit (NPU) on Microsoft Surface Copilot+ PCs.

**100% local processing — your data never leaves the device.**

---

## Features

| Feature | Description |
|---------|-------------|
| 📄 **Document Analysis** | Upload PDF, DOCX, TXT files for summarization, key points, Q&A, and simplification |
| 🔐 **PII Detection** | Scan documents for SSN, credit cards, addresses, phone numbers, emails |
| 🌐 **Translation** | Translate documents to 15 languages (Spanish, French, German, Chinese, etc.) |
| 📷 **ID Verification** | Camera capture + OCR + AI parsing of driver licenses — fully offline |
| 💬 **Chat** | Conversational AI assistant running entirely on-device |
| ✈️ **Offline Mode** | Works with Airplane Mode enabled — the "wow" demo moment |

---

## Supported Hardware

| Platform | NPU Performance | Example Devices |
|----------|-----------------|-----------------|
| Qualcomm Snapdragon X Elite/Plus | 45 TOPS | Surface Pro 11, Surface Laptop 7 (ARM) |
| Intel Core Ultra Series 2 (Lunar Lake) | 48 TOPS | Surface Laptop 7 (Intel) |
| Intel Core Ultra Series 1 (Meteor Lake) | 10-11 TOPS | Various OEM devices |

---

## Quick Start

### Prerequisites

- Windows 11 24H2 on a Copilot+ PC
- Python 3.10+ (Microsoft Store or python.org)
- VS Code with AI Toolkit extension

### Installation

1. **Install Python dependencies:**
   ```powershell
   pip install flask openai pypdf python-docx
   ```

2. **Set up VS Code AI Toolkit:**
   - Install "AI Toolkit" extension in VS Code
   - Open AI Toolkit → Catalog → Load "Phi Silica"
   - Foundry Local will start automatically on localhost:5272

3. **Run the demo:**
   ```powershell
   cd "C:\Path\To\NPU-Demo"
   python npu_demo_flask.py
   ```

4. **Open browser:** http://localhost:5000

---

## Files

| File | Description |
|------|-------------|
| `npu_demo_flask.py` | Main demo application (Intel version) |
| `npu_demo_flask_qualcomm.py` | Qualcomm Snapdragon version with QNN models |
| `surface-logo.png` | Microsoft Surface logo |
| `copilot-logo.avif` | Copilot+ PC logo |
| `Sample_Loan_Application_With_PII.txt` | Test document for PII detection demo |
| `Enterprise_AI_Strategy_2026.pdf` | Sample document for analysis demos |
| `Surface_NPU_Demo_Install_Guide.docx` | Detailed installation guide |
| `setup.ps1` | Automated setup script |
| `requirements.txt` | Python dependencies |

---

## Demo Flow

### Document Analysis + PII Detection
1. Upload `Sample_Loan_Application_With_PII.txt`
2. Click **"Detect PII"** — watch it find SSNs, credit cards, names, addresses
3. Click **"Summarize"** to show document comprehension
4. Select a language and click **"Translate"**

### ID Verification (Bank Teller Use Case)
1. Click the **"ID Verification"** tab
2. Select your camera from the dropdown
3. Click **"Start Camera"** and position a driver license
4. Click **"Capture ID"** then **"Analyze ID"**
5. Watch the 3-step pipeline: Capture → OCR → AI Analysis

### The "Wow" Moment
1. **Turn on Airplane Mode**
2. Repeat any demo above
3. **Everything still works** — the AI never needed the cloud

---

## Key Talking Points

### Privacy & Security
> "Your ID image and sensitive documents never leave this device. The entire AI pipeline — capture, OCR, analysis — runs 100% locally. There's no data to breach because nothing was transmitted."

### Local AI Capability  
> "Local AI models can handle 80% of typical enterprise AI tasks: summarization, extraction, translation, classification. For workflows processing PII, that's not a limitation — it's the right tool for the job."

### NPU Performance
> "The NPU delivers 45-48 TOPS of dedicated AI processing. Unlike GPU-based AI, it runs without draining your battery or spinning up fans. It's always-on, always-ready AI."

### Cloud vs. Local
> "Cloud AI is like hiring a PhD for data entry — it works, but you're overpaying and sending documents off-premises. Local AI is purpose-fit: dedicated silicon doing exactly what the task requires."

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Connection refused" error | Ensure Foundry Local is running (check AI Toolkit in VS Code) |
| Model not responding | Restart VS Code and reload Phi Silica model |
| Camera not detected | Check browser permissions, try different camera from dropdown |
| OCR quality poor | Improve lighting, hold ID flat, ensure camera is focused |
| JavaScript errors | Hard refresh with Ctrl+Shift+R |

---

## Technical Details

- **Framework:** Flask (Python)
- **AI Backend:** Foundry Local + Windows AI API
- **Model:** Phi Silica (optimized for NPU)
- **OCR:** Tesseract.js (runs in browser, no server needed)
- **Endpoint:** OpenAI-compatible API at `localhost:5272`

---

## Credits

Built with ❤️ and Claude by Microsoft Surface GTM Corp Marketing

*Demonstrating cloud AI for development + on-device AI for secure deployment*
