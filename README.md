# Zava Financial — On-Device AI Banking Demo

A complete banking demo application showcasing on-device AI capabilities using the Neural Processing Unit (NPU) on Microsoft Surface Copilot+ PCs. Supports both **Intel Core Ultra (Lunar Lake)** and **Qualcomm Snapdragon X (ARM64)** -- silicon is auto-detected at startup.

**100% local AI processing -- customer data never leaves the device.**

## What This Demo Shows

A bank advisor walks through their entire day using a Surface Pro with on-device AI:

1. **Morning Briefing** -- AI summarizes calendar, email, and tasks from live Outlook (Microsoft Graph)
2. **Client Prep** -- AI pulls the next meeting from Outlook + customer profile from D365 via MCP
3. **ID Verification** -- Camera/OCR scans a driver license, AI validates, D365 pulls customer record
4. **Check Deposit** -- AI scans and verifies a check, logs the transaction to D365
5. **Live Client Meeting** -- Real-time AI prompter with sentiment analysis during the conversation
6. **Meeting Notes** -- Voice dictation, document capture, pen signatures, AI-generated report posted to D365
7. **Knowledge Queries** -- Advisor asks about 529 plans, Roth IRA rules, compliance -- answered locally on NPU

**Three live enterprise systems, one device, zero cloud AI:**
- **Microsoft Graph** -- live Outlook calendar and email
- **Dynamics 365 Dataverse** -- customer profiles, activities, check-in queue (via MCP server)
- **Phi-4 Mini on NPU** -- all AI inference runs locally on the device

---

## Quick Start

### Option 1: PowerShell Scripts (recommended for development)

```powershell
# One-time setup (run as Administrator)
.\setup.ps1

# Daily launch (starts all 3 services + opens browser)
.\start-demo.ps1

# Stop everything
.\stop-demo.ps1
```

### Option 2: Standalone Installer

Run `NPU-Demo-Setup.exe` -- installs the app with Start Menu shortcuts, no Python required.

Build the installer yourself:
```powershell
# Build the PyInstaller exe
pyinstaller npu-demo.spec --noconfirm

# Build the InnoSetup installer
& "C:\Users\$env:USERNAME\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

### Option 3: ZIP Kit

Distribute `NPU-Demo-Kit.zip` -- unzip, run `setup.ps1`, then `start-demo.ps1`.

---

## Requirements

- Windows 11 25H2 or later
- Copilot+ PC with NPU (Surface Pro, Surface Laptop, or equivalent)
  - Intel Core Ultra (Lunar Lake) or Qualcomm Snapdragon X
- ~4 GB free disk space (for AI model download)
- Edge or Chrome browser
- Python 3.10+ (for development; standalone exe doesn't need it)

### Dependencies

```
pip install flask openai pypdf python-docx foundry-local-sdk msal requests mcp
```

Foundry Local runtime:
```
winget install Microsoft.FoundryLocal
```

---

## Architecture

```
Surface Copilot+ PC
+--------------------------------------------------+
|  Browser (localhost:5000)                         |
|    Flask App (npu_demo_flask.py)                  |
|      |                                            |
|      +-- Phi-4 Mini on NPU (Foundry Local)       |
|      |     All AI inference runs here             |
|      |                                            |
|      +-- MCP D365 Server (mcp-d365/server.py)    |
|      |     Queries live Dynamics 365 Dataverse    |
|      |                                            |
|      +-- Microsoft Graph API                      |
|      |     Live Outlook calendar + email          |
|      |                                            |
|      +-- Phi Silica Vision (vision-service/)      |
|            Image classification on NPU            |
+--------------------------------------------------+
        |                    |
   D365 Dataverse      Microsoft Graph
   (structured data)   (calendar/email)

   AI inference: LOCAL on NPU
   Business data: YOUR existing cloud systems
   Customer PII: NEVER leaves the device
```

### Key Files

| File | Purpose |
|------|---------|
| `npu_demo_flask.py` | Main Flask app (~12,000 lines, single file with inline HTML/CSS/JS) |
| `mcp-d365/server.py` | MCP server for Dynamics 365 Dataverse (4 tools) |
| `setup.ps1` | One-time setup (Python, Foundry Local, model download, MSIX) |
| `start-demo.ps1` | Daily launcher (starts all 3 services + browser) |
| `stop-demo.ps1` | Clean shutdown |
| `demo_data/` | Banking demo data (calendar, emails, tasks, demo IDs, checks) |
| `fonts/` | Urbanist font (bundled locally for offline use) |
| `vision-service/` | C# Phi Silica Vision microservice (MSIX package) |
| `installer.iss` | InnoSetup script for building the standalone installer |
| `npu-demo.spec` | PyInstaller spec for building the standalone exe |

---

## Six Tabs

| Tab | Description |
|-----|-------------|
| **Advisor Assistant** | AI agent with MCP D365 tools, Graph calendar, dynamic follow-up chips |
| **Morning Briefing** | AI morning brief from calendar, email, and tasks |
| **PII Guard** | Document PII detection and compliance pre-screening |
| **ID & Check Verify** | Camera/OCR ID scan + check deposit with D365 integration |
| **Live Assist** | Real-time AI prompter during client meetings with translation |
| **Meeting Notes** | Voice capture, document classification, pen signatures, D365 posting |

---

## MCP D365 Server

The MCP server (`mcp-d365/server.py`) exposes Dynamics 365 as tools for any MCP-compatible AI client:

| Tool | Description |
|------|-------------|
| `d365_customer_lookup(name)` | Search contacts by name, return profile |
| `d365_check_in_queue()` | Get branch check-in queue from kiosk Power App |
| `d365_log_activity(customer_name, note)` | Create task/note on a contact record |
| `d365_recent_activities(customer_name)` | Get recent timeline entries |

**Reusable across customers** -- swap the org URL and tenant in environment variables:

```
D365_ORG_URL=https://your-org.crm.dynamics.com
D365_TENANT=your-tenant.onmicrosoft.com
```

---

## Microsoft Graph Integration

The app connects to live Outlook via Microsoft Graph for calendar and email:

- **My Calendar** chip: pulls today's real Outlook events
- **Prep Next Client** chip: Graph calendar + D365 MCP combined
- App registration: public client with Calendars.ReadWrite, Mail.Read, User.Read
- Token cached locally, renews silently

### Setup

1. Register an app in Azure AD with Graph permissions
2. Run the app and visit `/d365/authenticate` to connect
3. Calendar events appear in the Advisor Assistant via the My Calendar chip

---

## DEMO_CONFIG Layer

Re-skin the entire app by editing one dictionary:

```python
DEMO_CONFIG = {
    "app_title": "Your Bank Name",
    "brand_accent": "#your-color",
    "brand_theme": "light",  # or "dark"
    "tabs": { ... },
    "personas": [ ... ],
}
```

All colors, tab names, persona badges, icons, and POC text are driven from this config.

---

## Demo Assets

| Asset | Description |
|-------|-------------|
| McLovin ID | Superbad fake Hawaii DL -- AI flags it with 4 issues (gets laughs) |
| Jackie Rodriguez ID | Valid Michigan DL -- passes verification, triggers D365 flow |
| Jackie's Check | $245.89 refund from Michigan Power & Light |
| 403(b) Statement | Quarterly retirement statement for document capture |
| Beneficiary Form | Zava Financial beneficiary designation form for pen signing |

---

## Security

- File system jailing: all reads/writes restricted to `demo_data/`
- PowerShell allowlist: only approved cmdlets
- Flask bound to localhost only (127.0.0.1)
- Path traversal prevention on all static routes
- PII scanner with SSN/email/phone/name detection
- No customer biometrics or ID images sent to cloud

---

## License

This is a Microsoft demo application for Copilot+ PC showcases. All fictional characters, companies, and financial data are for demonstration purposes only.

Contact: Frank Buchholz (frankbu@microsoft.com)
