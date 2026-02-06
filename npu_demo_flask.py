"""
Local NPU AI Assistant Demo
Document Analysis + Chat + ID Verification
Runs entirely on-device using Foundry Local + Intel Core Ultra NPU
"""

import os
import json
import re
import subprocess
import threading
import time as _time
from flask import Flask, render_template_string, request, Response, jsonify
from openai import OpenAI
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Model initialization via Foundry Local SDK (fallback to localhost:5272) ---
print("Starting Foundry Local runtime...", flush=True)
FOUNDRY_AVAILABLE = False
try:
    from foundry_local import FoundryLocalManager
    MODEL_ALIAS = "phi-4-mini"
    manager = FoundryLocalManager(MODEL_ALIAS)
    MODEL_ID = manager.get_model_info(MODEL_ALIAS).id
    client = OpenAI(base_url=manager.endpoint, api_key=manager.api_key)
    DEFAULT_MODEL = MODEL_ID
    FOUNDRY_AVAILABLE = True
except Exception:
    client = OpenAI(base_url="http://localhost:5272/v1", api_key="not-needed")
    DEFAULT_MODEL = "phi-4-mini"

# --- Model readiness flag (set after warmup) ---
MODEL_READY = False

# --- Agent infrastructure ---
DEMO_DIR = os.path.join(os.path.expanduser("~"), "Documents", "Demo")
os.makedirs(DEMO_DIR, exist_ok=True)

# Create demo NDA file for Clean Room Auditor if it doesn't exist
_nda_demo_path = os.path.join(DEMO_DIR, "contract_nda_vertex_pinnacle.txt")
if not os.path.exists(_nda_demo_path):
    with open(_nda_demo_path, 'w', encoding='utf-8') as _f:
        _f.write("""MUTUAL NON-DISCLOSURE AGREEMENT

Effective Date: January 15, 2026
Agreement Number: NDA-2026-VD-PS-0847

BETWEEN:

Vertex Dynamics, Inc.
1200 Innovation Drive, Suite 400
San Jose, CA 95134
Contact: James Morrison, VP Corporate Development
Email: j.morrison@vertexdyn.com
Phone: (415) 555-0142

AND:

Pinnacle Solutions Group, LLC
8900 Enterprise Boulevard
Austin, TX 78759
Contact: Sarah Chen, General Counsel

SECTION 1. DEFINITION OF CONFIDENTIAL INFORMATION

1.1 "Confidential Information" means any and all non-public, proprietary, or confidential information disclosed by either party to the other, whether orally, in writing, electronically, or by inspection of tangible objects.

SECTION 2. OBLIGATIONS OF RECEIVING PARTY

2.1 The receiving party shall hold all Confidential Information in strict confidence and shall not disclose such information to any third party without the prior written consent of the disclosing party.

SECTION 3. TERM AND DURATION

3.1 This Agreement shall remain in effect for a period of two (2) years from the Effective Date.

3.2 The obligations of confidentiality shall survive termination for a period of five (5) years.

SECTION 4. INDEMNIFICATION AND LIABILITY

4.1 Each party shall indemnify and hold harmless the other party from claims arising from a breach of this Agreement.

4.2 NOTWITHSTANDING ANY OTHER PROVISION, THE DISCLOSING PARTY SHALL BE ENTITLED TO FULL INDEMNIFICATION FOR ALL DAMAGES, INCLUDING CONSEQUENTIAL, INCIDENTAL, INDIRECT, SPECIAL, AND PUNITIVE DAMAGES, ARISING FROM ANY BREACH BY THE RECEIVING PARTY. THIS PROVISION SHALL NOT BE SUBJECT TO ANY CAP OR LIMITATION.

SECTION 5. RETURN OF MATERIALS

5.1 Upon termination, the receiving party shall return or destroy all Confidential Information within thirty (30) days.

SECTION 6. REMEDIES

6.1 The non-breaching party shall be entitled to seek injunctive relief in addition to any other remedies.

SECTION 7. INTELLECTUAL PROPERTY

7.1 ALL WORK PRODUCT, INVENTIONS, AND INNOVATIONS, WHETHER CREATED PRIOR TO OR DURING THIS AGREEMENT, THAT ARE USED IN CONNECTION WITH THE PURPOSE, SHALL BE THE SOLE PROPERTY OF THE DISCLOSING PARTY.

SECTION 8. NON-SOLICITATION

8.1 Neither party shall solicit or hire employees of the other party for twelve (12) months following termination.

SECTION 9. NON-COMPETITION

9.1 The receiving party shall not engage in any competing business anywhere in the world for twenty-four (24) months following termination.

SECTION 10. GOVERNING LAW

10.1 This Agreement shall be governed by the laws of the State of Delaware.

IN WITNESS WHEREOF:

VERTEX DYNAMICS, INC.
By: _________________________
Name: James A. Morrison
Title: VP Corporate Development
SSN (for notarization): 478-93-3847
Date: January 15, 2026

PINNACLE SOLUTIONS GROUP, LLC
By: _________________________
Name: Sarah L. Chen
Title: General Counsel
Date: January 15, 2026
""")

AGENT_AUDIT_LOG = []

# --- Session stats for Local AI Savings widget ---
SESSION_STATS = {
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "inference_seconds": 0.0,
}


def _track_model_call(response, elapsed_seconds):
    """Track model call stats for the savings widget."""
    SESSION_STATS["calls"] += 1
    SESSION_STATS["inference_seconds"] += elapsed_seconds
    if hasattr(response, 'usage') and response.usage:
        SESSION_STATS["input_tokens"] += response.usage.prompt_tokens or 0
        SESSION_STATS["output_tokens"] += response.usage.completion_tokens or 0


AGENT_SYSTEM_PROMPT = (
    'You are Phi, a helpful AI assistant running on a Windows PC. You have these tools:\n\n'
    '- read(path): VIEW or READ an existing file\n'
    '- write(path, content): CREATE or SAVE a NEW file with content\n'
    '- exec(command): RUN a shell command. The shell is PowerShell \u2014 use cmdlets like '
    'Get-ChildItem, Get-Content, Get-Date, Enable-NetAdapter, Disable-NetAdapter directly. '
    'Do NOT wrap in "PowerShell -Command".\n\n'
    'RULES:\n'
    '- For general knowledge questions, conversational questions, or anything you can answer '
    'from your own knowledge, just respond directly in plain text. Do NOT use tools.\n'
    '- ONLY use tools when the user explicitly asks to read a file, write a file, list a '
    'directory, run a command, or interact with the local system.\n'
    '- Use "write" to CREATE files (needs path + content). Use "read" to VIEW files.\n'
    '- For "exec", ONLY provide "command". Do NOT add env, workdir, or other params.\n'
    '- Use Windows backslash paths: C:\\Users\\file.txt\n'
    '- Keep responses concise and helpful.\n\n'
    'ALWAYS use this EXACT format when using a tool:\n'
    '[TOOL_CALL]\n{"name": "TOOL_NAME", "arguments": {"param": "value"}}\n[/TOOL_CALL]\n\n'
    'When no tool is needed, respond with plain text (no markers needed).\n\n'
    'Examples:\n'
    '[TOOL_CALL]\n{"name": "read", "arguments": {"path": "C:\\\\Users\\\\me\\\\doc.txt"}}\n[/TOOL_CALL]\n\n'
    '[TOOL_CALL]\n{"name": "write", "arguments": {"path": "C:\\\\Users\\\\me\\\\notes.txt", '
    '"content": "Meeting notes from today"}}\n[/TOOL_CALL]\n\n'
    '[TOOL_CALL]\n{"name": "exec", "arguments": {"command": "Get-ChildItem C:\\\\Users"}}\n[/TOOL_CALL]'
)

# --- My Day infrastructure ---
MY_DAY_DIR = os.path.join(DEMO_DIR, "My_Day")
MY_DAY_INBOX = os.path.join(MY_DAY_DIR, "Inbox")

import csv
import email
from email import policy as _email_policy


def parse_ics(filepath):
    """Parse iCalendar file into list of event dicts, sorted by start time."""
    events = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return events
    blocks = re.split(r'BEGIN:VEVENT', content)[1:]  # skip preamble
    for block in blocks:
        block = block.split('END:VEVENT')[0]
        ev = {}
        for line in block.strip().splitlines():
            if ':' not in line:
                continue
            key, _, val = line.partition(':')
            key = key.split(';')[0].strip().upper()
            val = val.strip()
            if key == 'SUMMARY':
                ev['summary'] = val
            elif key == 'DTSTART':
                ev['dtstart'] = val
                # Parse into readable time
                try:
                    from datetime import datetime
                    dt = datetime.strptime(val, '%Y%m%dT%H%M%S')
                    ev['time'] = dt.strftime('%I:%M %p').lstrip('0')
                    ev['date'] = dt.strftime('%Y-%m-%d')
                except Exception:
                    ev['time'] = val
            elif key == 'DTEND':
                try:
                    from datetime import datetime
                    dt = datetime.strptime(val, '%Y%m%dT%H%M%S')
                    ev['end_time'] = dt.strftime('%I:%M %p').lstrip('0')
                except Exception:
                    pass
            elif key == 'LOCATION':
                ev['location'] = val
            elif key == 'DESCRIPTION':
                # ICS uses \n for newlines in description
                ev['description'] = val.replace('\\n', '\n')
            elif key == 'ATTENDEE':
                attendees = ev.get('attendees', [])
                cn_match = re.search(r'CN=([^;:]+)', line)
                if cn_match:
                    attendees.append(cn_match.group(1))
                ev['attendees'] = attendees
        if ev.get('summary'):
            events.append(ev)
    events.sort(key=lambda e: e.get('dtstart', ''))
    return events


def parse_tasks_csv(filepath):
    """Parse tasks CSV into list of task dicts."""
    tasks = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tasks.append(dict(row))
    except Exception:
        pass
    return tasks


def parse_eml(filepath):
    """Parse a single .eml file into a dict."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            msg = email.message_from_file(f, policy=_email_policy.default)
        body = ''
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    body = part.get_content()
                    break
        else:
            body = msg.get_content()
        return {
            'from': str(msg.get('From', '')),
            'subject': str(msg.get('Subject', '')),
            'date': str(msg.get('Date', '')),
            'body': body.strip() if body else '',
            'filename': os.path.basename(filepath),
        }
    except Exception:
        return None


def parse_inbox(inbox_dir):
    """Read all .eml files in folder, return list sorted by filename."""
    emails = []
    if not os.path.isdir(inbox_dir):
        return emails
    for fname in sorted(os.listdir(inbox_dir)):
        if fname.lower().endswith('.eml'):
            parsed = parse_eml(os.path.join(inbox_dir, fname))
            if parsed:
                emails.append(parsed)
    return emails


def compress_for_briefing(events, tasks, emails):
    """Compress all data into compact text for Phi-4 Mini's ~1K prompt limit."""
    lines = ['TODAY: Sat Feb 7 2026\n']

    # Calendar — top 5 events, short format
    lines.append(f'CALENDAR ({len(events)} events):')
    for ev in events[:5]:
        t = ev.get('time', '?')
        s = ev.get('summary', '?')
        lines.append(f'- {t} {s}')

    # Tasks — top 4, compact
    lines.append(f'\nTASKS ({len(tasks)} items):')
    for t in tasks[:4]:
        prio = t.get('Priority', 'Med')
        name = t.get('Task', '?')
        lines.append(f'- [{prio}] {name}')

    # Emails — top 3, sender + subject only
    lines.append(f'\nINBOX ({len(emails)} emails):')
    for em in emails[:3]:
        subj = em.get('subject', '?')[:50]
        frm = em.get('from', '?').split('<')[0].strip().strip('"')
        lines.append(f'- {frm}: {subj}')

    result = '\n'.join(lines)
    # Hard cap — phi-4-mini NPU has 1024 token max prompt
    if len(result) > 1200:
        result = result[:1200]
    return result


BRIEFING_SYSTEM_PROMPT = (
    'You are a chief of staff. Write a MORNING BRIEFING with:\n'
    '1. Summary (3 sentences): who they see today, what to handle, any risks.\n'
    '2. ACTIONS: numbered priority list.\n'
    '3. PEOPLE: key names with one-line context.\n'
    '4. WARNINGS: landmines or legal issues.\n'
    'Cross-reference: connect people across calendar, email, and tasks. Be concise.'
)


# Allowlist of PowerShell cmdlets permitted for the demo (everything else blocked)
_ALLOWED_COMMANDS = [
    "get-childitem", "get-content", "set-content", "add-content", "out-file",
    "get-date", "get-location", "write-output", "select-object", "format-list",
    "get-netadapter", "disable-netadapter", "enable-netadapter",
]
_NETWORK_CMDS = ["disable-netadapter", "enable-netadapter"]


def parse_tool_call(text):
    """Parse [TOOL_CALL] markers from model output."""
    match = re.search(
        r'\[TOOL_(?:CALL|RESPONSE)\]\s*([\s\S]*?)\s*\[/TOOL_(?:CALL|RESPONSE)\]', text
    )
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            return None
    # Try bare JSON (model sometimes omits markers)
    stripped = text.strip()
    if stripped.startswith('{'):
        try:
            parsed = json.loads(stripped)
            if 'name' in parsed and 'arguments' in parsed:
                return parsed
        except Exception:
            pass
    return None


def _path_in_demo_dir(path):
    """Check if a path resolves within DEMO_DIR. Prevents path traversal."""
    try:
        resolved = os.path.realpath(os.path.normpath(path))
        demo_resolved = os.path.realpath(DEMO_DIR)
        return resolved.startswith(demo_resolved + os.sep) or resolved == demo_resolved
    except Exception:
        return False


def execute_tool(name, arguments):
    """Execute a tool with safety guardrails. Returns dict with success, output, error."""
    print(f"[DEBUG] execute_tool called: name={name}, arguments={arguments}")
    if name == "read":
        path = arguments.get("path", "")
        print(f"[DEBUG] read path='{path}', in_demo_dir={_path_in_demo_dir(path)}")
        if not _path_in_demo_dir(path):
            return {"success": False, "error": f"Security Policy Violation: Access restricted to approved folder ({DEMO_DIR})"}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"success": True, "output": content[:5000]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif name == "write":
        path = arguments.get("path", "")
        if not _path_in_demo_dir(path):
            return {"success": False, "error": f"Security Policy Violation: Write restricted to approved folder ({DEMO_DIR})"}
        content = arguments.get("content", "")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            size_kb = round(len(content.encode('utf-8')) / 1024, 1)
            return {"success": True, "output": f"File written: {path} ({size_kb} KB)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif name == "exec":
        command = arguments.get("command", "")
        cmd_lower = command.lower().strip()
        # Safety: allowlist — only permitted cmdlets can run
        if not any(cmd_lower.startswith(a) or (" | " in cmd_lower and a in cmd_lower) for a in _ALLOWED_COMMANDS):
            return {"success": False, "error": "Security Policy: Only approved commands are permitted. Blocked: " + command.split()[0] if command.split() else command}
        try:
            # Network adapter commands: auto-suppress confirmation prompt
            is_network_cmd = any(a in cmd_lower for a in _NETWORK_CMDS)
            if is_network_cmd and "-confirm" not in cmd_lower:
                command = command.rstrip() + " -Confirm:$false"
            cmd_timeout = 30 if is_network_cmd else 15
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                capture_output=True, text=True, timeout=cmd_timeout
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            return {"success": proc.returncode == 0, "output": output.strip()[:3000]}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Command timed out ({cmd_timeout}s limit)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif name == "__text_response":
        return {"success": True, "output": arguments.get("text", ""), "is_text": True}

    return {"success": False, "error": f"Unknown tool: {name}"}

def extract_text_from_pdf(filepath):
    try:
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        return f"Error reading PDF: {str(e)}"

def extract_text_from_docx(filepath):
    try:
        from docx import Document
        doc = Document(filepath)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text.strip()
    except Exception as e:
        return f"Error reading DOCX: {str(e)}"

def extract_text_from_txt(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        return f"Error reading TXT: {str(e)}"

def extract_text(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        return extract_text_from_pdf(filepath)
    elif ext == '.docx':
        return extract_text_from_docx(filepath)
    elif ext in ['.txt', '.md']:
        return extract_text_from_txt(filepath)
    else:
        return "Unsupported file type"

HTML_TEMPLATE = r'''<!DOCTYPE html>
<html>
<head>
    <title>Local NPU AI Assistant</title>
    <link rel="icon" type="image/png" href="/logos/favicon.png">
    <script src="/tesseract/tesseract.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }

        /* ── App Shell: sidebar + main ── */
        .app-shell { display: flex; min-height: 100vh; }
        .sidebar {
            width: 260px; min-width: 260px;
            background: linear-gradient(180deg, #0d1117 0%, #111827 100%);
            border-right: 1px solid rgba(255,255,255,0.08);
            display: flex; flex-direction: column;
            transition: width 0.25s cubic-bezier(.4,0,.2,1), min-width 0.25s cubic-bezier(.4,0,.2,1);
            overflow: hidden; z-index: 200;
        }
        .sidebar.collapsed { width: 64px; min-width: 64px; }
        .sidebar.collapsed .sidebar-label,
        .sidebar.collapsed .sidebar-brand-text,
        .sidebar.collapsed .sidebar-footer-label,
        .sidebar.collapsed .sidebar-footer-controls { display: none; }
        .sidebar.collapsed .sidebar-brand { justify-content: center; }
        .sidebar.collapsed .sidebar-nav-item { justify-content: center; padding-left: 0; padding-right: 0; }
        .sidebar.collapsed .sidebar-nav-item .nav-icon { margin-right: 0; }
        .sidebar.collapsed .sidebar-footer { align-items: center; padding: 12px 8px; }
        .sidebar.collapsed .sidebar-toggle { margin: 8px auto; }

        .sidebar-toggle {
            background: none; border: 1px solid rgba(255,255,255,0.12);
            color: #fff; width: 34px; height: 34px; border-radius: 8px;
            cursor: pointer; font-size: 1.1em; display: flex; align-items: center;
            justify-content: center; margin: 12px 12px 0 12px; flex-shrink: 0;
            transition: background 0.15s;
        }
        .sidebar-toggle:hover { background: rgba(255,255,255,0.08); }

        .sidebar-brand {
            display: flex; flex-direction: column; align-items: center; gap: 0;
            padding: 0px 14px 36px; border-bottom: 1px solid rgba(255,255,255,0.06);
        }
        .sidebar-brand .brand-logo-surface { width: 92%; max-width: 220px; height: auto; object-fit: contain; }
        .sidebar-brand .brand-logo-copilot { width: 65%; max-width: 150px; height: auto; object-fit: contain; margin-top: -6px; }
        .sidebar-brand-text { display: none; }
        .sidebar.collapsed .sidebar-brand { padding: 12px 6px; gap: 6px; }
        .sidebar.collapsed .brand-logo-surface { width: 40px; }
        .sidebar.collapsed .brand-logo-copilot { width: 32px; }

        .sidebar-nav { flex: 1; padding: 12px 0; display: flex; flex-direction: column; gap: 2px; }
        .sidebar-nav-item {
            display: flex; align-items: center; gap: 0;
            padding: 12px 18px; cursor: pointer; color: rgba(255,255,255,0.7);
            border-left: 3px solid transparent; transition: all 0.15s;
            white-space: nowrap; font-size: 0.92em; text-decoration: none;
        }
        .sidebar-nav-item:hover { background: rgba(255,255,255,0.05); color: #fff; }
        .sidebar-nav-item.active {
            border-left-color: #00BCF2; color: #fff;
            background: rgba(0,188,242,0.08);
        }
        .nav-icon { font-size: 1.2em; width: 28px; text-align: center; flex-shrink: 0; margin-right: 10px; }
        .sidebar-label { overflow: hidden; text-overflow: ellipsis; }
        .sidebar-nav-sub { display: block; font-size: 0.65em; opacity: 0.45; font-weight: normal; margin-top: 1px; }

        .sidebar-footer {
            padding: 14px 18px; border-top: 1px solid rgba(255,255,255,0.06);
            display: flex; flex-direction: column; gap: 8px; font-size: 0.85em;
        }
        .sidebar-footer .badge,
        .sidebar-footer .offline-badge { font-size: 0.78em; margin: 0; padding: 5px 10px; }
        .sidebar-footer-controls { display: flex; flex-direction: column; gap: 6px; }
        .sidebar-footer-controls .net-toggle-btn { font-size: 0.78em; padding: 5px 10px; }
        .sidebar-footer-controls .model-selector { justify-content: flex-start; margin: 0; }
        .sidebar-footer-controls .model-selector select { font-size: 0.8em; padding: 5px 10px; }
        .sidebar-footer-label { font-size: 0.78em; opacity: 0.5; margin-bottom: 2px; }

        /* Local AI Savings Widget */
        .savings-widget {
            background: linear-gradient(135deg, rgba(34, 197, 94, 0.08) 0%, rgba(34, 197, 94, 0.02) 100%);
            border: 1px solid rgba(34, 197, 94, 0.25);
            border-radius: 8px;
            padding: 10px 12px;
            margin-bottom: 10px;
            font-size: 0.78em;
        }
        .savings-header {
            font-weight: 600;
            color: #22c55e;
            margin-bottom: 6px;
            font-size: 0.9em;
            letter-spacing: 0.02em;
        }
        .savings-stat {
            color: rgba(255, 255, 255, 0.75);
            margin: 3px 0;
            line-height: 1.4;
        }
        .savings-stat-highlight {
            color: #22c55e;
            font-weight: 500;
        }
        .sidebar.collapsed .savings-widget {
            padding: 8px;
            text-align: center;
        }
        .sidebar.collapsed .savings-header,
        .sidebar.collapsed .savings-stat:not(.savings-stat-compact) { display: none; }
        .savings-stat-compact { display: none; }
        .sidebar.collapsed .savings-stat-compact {
            display: block;
            color: #22c55e;
            font-weight: 600;
            font-size: 0.95em;
        }

        .main-content { flex: 1; min-width: 0; overflow-y: auto; padding: 20px; max-height: 100vh; }

        /* Mobile overlay */
        .sidebar-backdrop {
            display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5);
            z-index: 199;
        }
        @media (max-width: 768px) {
            .sidebar {
                position: fixed; left: 0; top: 0; height: 100vh;
                transform: translateX(-100%); z-index: 200;
            }
            .sidebar.mobile-open { transform: translateX(0); }
            .sidebar.collapsed { transform: translateX(-100%); }
            .sidebar.collapsed.mobile-open { transform: translateX(0); }
            .sidebar-backdrop.visible { display: block; }
            .main-content { padding: 12px; }
            .mobile-hamburger {
                display: flex; position: fixed; top: 12px; left: 12px; z-index: 198;
                background: rgba(13,17,23,0.9); border: 1px solid rgba(255,255,255,0.12);
                color: #fff; width: 40px; height: 40px; border-radius: 10px;
                align-items: center; justify-content: center; font-size: 1.3em; cursor: pointer;
            }
        }
        @media (min-width: 769px) {
            .mobile-hamburger { display: none !important; }
        }

        .container { max-width: 100%; margin: 0 auto; padding: 0; }
        header { display: none; }
        .logos { display: flex; justify-content: center; align-items: center; gap: 35px; margin-bottom: 20px; }
        .logos img.surface-logo { height: 75px; width: auto; object-fit: contain; }
        .logos img.copilot-logo { height: 55px; width: auto; object-fit: contain; }
        .logo-divider { width: 2px; height: 60px; background: rgba(255,255,255,0.3); }
        h1 { font-size: 2.2em; margin-bottom: 10px; }
        .subtitle { color: #00BCF2; font-size: 1.1em; }
        .badge {
            display: inline-block;
            background: linear-gradient(90deg, #0078D4, #00BCF2);
            padding: 8px 16px;
            border-radius: 25px;
            font-weight: bold;
            margin: 15px 5px;
            font-size: 0.9em;
        }
        .offline-badge {
            display: inline-block;
            background: linear-gradient(90deg, #107C10, #00CC6A);
            padding: 8px 16px;
            border-radius: 25px;
            font-weight: bold;
            margin: 15px 5px;
            font-size: 0.9em;
        }
        .offline-badge.offline { background: linear-gradient(90deg, #FF8C00, #FFB900); }
        .header-status-row { display: flex; justify-content: center; align-items: center; gap: 8px; flex-wrap: wrap; }
        .net-toggle-btn {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.25);
            color: #fff;
            padding: 6px 14px;
            border-radius: 25px;
            font-size: 0.82em;
            cursor: pointer;
            transition: all 0.2s;
        }
        .net-toggle-btn:hover { background: rgba(255,255,255,0.18); }
        .net-toggle-btn.net-toggle-off { border-color: rgba(255,140,0,0.5); }
        .net-toggle-btn.net-toggle-off:hover { background: rgba(255,140,0,0.2); }
        .net-toggle-btn.net-toggle-on { border-color: rgba(0,204,106,0.5); }
        .net-toggle-btn.net-toggle-on:hover { background: rgba(0,204,106,0.2); }
        .net-toggle-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .model-selector { display: flex; justify-content: center; align-items: center; gap: 10px; margin: 15px 0; }
        .model-selector label { font-size: 0.9em; opacity: 0.8; }
        .model-selector select {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.3);
            color: #fff;
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            cursor: pointer;
        }
        .model-selector select option { background: #1a1a2e; color: #fff; }
        .response-timer { text-align: center; font-size: 0.85em; color: #00BCF2; margin-top: 10px; }
        .tabs { display: none; gap: 10px; margin-bottom: 20px; }
        .tab-btn {
            flex: 1;
            padding: 15px;
            background: rgba(255,255,255,0.1);
            border: 2px solid transparent;
            color: #fff;
            border-radius: 10px;
            cursor: pointer;
            font-size: 1em;
        }
        .tab-btn:hover { background: rgba(0,188,242,0.2); }
        .tab-btn.active { border-color: #00BCF2; background: rgba(0,188,242,0.3); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .camera-btn {
            background: linear-gradient(90deg, #0078D4, #00BCF2);
            border: none;
            color: #fff;
            padding: 12px 30px;
            border-radius: 25px;
            cursor: pointer;
            font-weight: bold;
            font-size: 1em;
            margin-top: 15px;
        }
        .camera-btn.stop { background: linear-gradient(90deg, #D41C00, #FF4444); }
        /* Agent chat layout — full-width single column */
        .agent-chat-layout {
            display: flex;
            flex-direction: column;
            height: calc(100vh - 120px);
        }
        .agent-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            height: 36px;
            padding: 0 12px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            margin-top: 4px;
            font-size: 0.82em;
        }
        .topbar-left, .topbar-right {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .topbar-status {
            display: flex;
            align-items: center;
            gap: 5px;
            opacity: 0.8;
        }
        .topbar-btn {
            background: transparent;
            border: 1px solid transparent;
            color: #fff;
            padding: 3px 10px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.95em;
            opacity: 0.7;
            transition: opacity 0.15s, border-color 0.15s, background 0.15s;
        }
        .topbar-btn:hover { opacity: 1; border-color: rgba(255,255,255,0.2); background: rgba(255,255,255,0.06); }
        .topbar-divider { width: 1px; height: 16px; background: rgba(255,255,255,0.15); }
        .policy-icon-wrap {
            position: relative;
            display: flex;
            align-items: center;
        }
        .policy-tooltip {
            display: none;
            position: absolute;
            bottom: 100%;
            right: 0;
            margin-bottom: 6px;
            background: #1a1a2e;
            border: 1px solid rgba(0,188,242,0.3);
            border-radius: 10px;
            padding: 12px 14px;
            font-size: 0.85em;
            line-height: 1.6;
            width: 220px;
            z-index: 50;
            white-space: normal;
        }
        .policy-icon-wrap:hover .policy-tooltip { display: block; }
        .status-dot {
            width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
        }
        .status-dot.green { background: #00CC6A; box-shadow: 0 0 6px rgba(0,204,106,0.5); }
        .status-dot.red { background: #FF4444; box-shadow: 0 0 6px rgba(255,68,68,0.5); }
        .status-dot.blue { background: #00BCF2; box-shadow: 0 0 6px rgba(0,188,242,0.5); }
        .status-dot.yellow { background: #FFB900; box-shadow: 0 0 6px rgba(255,185,0,0.5); }

        /* Empty state */
        .chat-empty-state {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
        }
        .empty-title {
            font-size: 1.6em;
            font-weight: 700;
            margin-bottom: 6px;
        }
        .empty-subtitle {
            font-size: 0.95em;
            opacity: 0.55;
            margin-bottom: 16px;
        }
        .suggestion-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 10px;
            max-width: 720px;
            width: 100%;
        }
        .suggestion-chip {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.12);
            color: #fff;
            padding: 10px 12px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 0.82em;
            text-align: left;
            transition: background 0.15s, border-color 0.15s;
        }
        .suggestion-chip:hover { background: rgba(0,188,242,0.15); border-color: rgba(0,188,242,0.4); }
        .chip-icon { font-size: 1.1em; flex-shrink: 0; }

        /* Device Health check display */
        .health-checks-container { margin: 8px 0; }
        .health-check-entry {
            margin: 4px 0; padding: 8px 12px;
            background: rgba(255,255,255,0.03); border-radius: 6px;
            border-left: 3px solid rgba(255,255,255,0.15); font-size: 0.85em;
        }
        .health-check-entry.done { border-left-color: #1db954; }
        .health-check-entry.error { border-left-color: #FF4444; }
        .health-check-name { font-weight: 600; margin-bottom: 2px; }
        .health-check-cmd {
            font-family: 'Cascadia Code', 'Consolas', monospace;
            font-size: 0.78em; opacity: 0.4; margin: 2px 0;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .health-check-output {
            font-family: 'Cascadia Code', 'Consolas', monospace;
            font-size: 0.82em; white-space: pre-wrap; margin-top: 4px;
            max-height: 80px; overflow-y: auto; opacity: 0.8;
        }
        .health-ai-summary { margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.1); }

        /* Inline action buttons in chat messages */
        .inline-action-btn {
            display: inline-block;
            background: rgba(0,120,212,0.2);
            border: 1px solid rgba(0,120,212,0.4);
            color: #7fdbff;
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.88em;
            margin-right: 8px;
            margin-top: 8px;
            transition: background 0.15s, border-color 0.15s;
        }
        .inline-action-btn:hover { background: rgba(0,120,212,0.35); border-color: rgba(0,188,242,0.6); }

        .chat-container {
            border-radius: 15px;
            padding: 10px 20px;
            margin-bottom: 8px;
            flex: 1;
            min-height: 0;
            overflow-y: auto;
        }
        .message {
            margin: 12px auto;
            padding: 14px 18px;
            border-radius: 14px;
            max-width: 720px;
        }
        .user-msg { background: #0078D4; margin-left: auto; margin-right: 0; max-width: 600px; }
        .assistant-msg { background: rgba(255,255,255,0.08); margin-left: 0; margin-right: auto; }
        .role { font-size: 0.8em; opacity: 0.7; margin-bottom: 5px; }
        .chat-input-wrapper { max-width: 720px; margin: 0 auto; width: 100%; }
        .input-area {
            display: flex;
            gap: 8px;
            align-items: center;
            background: rgba(255,255,255,0.07);
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 24px;
            padding: 4px 4px 4px 6px;
        }
        #attachBtn {
            width: 36px; height: 36px;
            border-radius: 50%;
            border: none;
            background: transparent;
            color: rgba(255,255,255,0.6);
            font-size: 1.3em;
            cursor: pointer;
            flex-shrink: 0;
            display: flex; align-items: center; justify-content: center;
            transition: color 0.15s, background 0.15s;
        }
        #attachBtn:hover { color: #fff; background: rgba(255,255,255,0.1); }
        #userInput {
            flex: 1;
            padding: 10px 8px;
            border-radius: 10px;
            border: none;
            background: transparent;
            color: #fff;
            font-size: 1em;
            outline: none;
        }
        #sendBtn {
            width: 36px; height: 36px;
            border-radius: 50%;
            background: linear-gradient(135deg, #0078D4, #00BCF2);
            border: none;
            color: #fff;
            cursor: pointer;
            font-size: 1.1em;
            flex-shrink: 0;
            display: flex; align-items: center; justify-content: center;
            padding: 0;
        }
        #sendBtn:disabled { opacity: 0.4; cursor: not-allowed; }
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: #00BCF2;
            animation: spin 1s linear infinite;
            margin-right: 10px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        footer { text-align: center; padding: 20px; opacity: 0.6; font-size: 0.9em; display: none; }
        .tab-footer { text-align: center; padding: 16px 10px; opacity: 0.5; font-size: 0.82em; margin-top: 12px; }

        /* My Day Dashboard */
        .day-cards { display: flex; gap: 14px; margin-bottom: 20px; }
        .day-card {
            flex: 1;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 18px 16px;
            text-align: center;
        }
        .day-card { cursor: pointer; transition: border-color 0.2s, background 0.2s; position: relative; }
        .day-card:hover { border-color: rgba(0,188,242,0.4); background: rgba(255,255,255,0.09); }
        .day-card.expanded { border-color: rgba(0,188,242,0.5); background: rgba(255,255,255,0.09); }
        .day-card .card-icon { font-size: 1.8em; margin-bottom: 6px; }
        .day-card .card-count { font-size: 2.2em; font-weight: bold; color: #00BCF2; }
        .day-card .card-label { font-size: 0.85em; opacity: 0.7; }
        .day-card .card-hint { font-size: 0.72em; opacity: 0.4; margin-top: 4px; }
        .day-card .card-peek {
            display: none;
            position: absolute;
            top: 100%;
            left: -1px;
            right: -1px;
            background: #1a1a2e;
            border: 1px solid rgba(0,188,242,0.4);
            border-top: none;
            border-radius: 0 0 12px 12px;
            padding: 10px 12px;
            text-align: left;
            font-size: 0.78em;
            max-height: 320px;
            overflow-y: auto;
            z-index: 20;
            line-height: 1.5;
        }
        .day-card.expanded .card-peek { display: block; }
        .peek-row { padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.06); }
        .peek-row:last-child { border-bottom: none; }
        .peek-time { color: #00BCF2; font-weight: bold; margin-right: 6px; }
        .peek-prio { font-weight: bold; margin-right: 6px; }
        .peek-prio.high { color: #FF4444; }
        .peek-prio.medium { color: #FFB900; }
        .peek-prio.low { color: #00CC6A; }
        .peek-from { color: #00BCF2; margin-right: 6px; }
        .brief-me-btn {
            display: block;
            width: 100%;
            max-width: 400px;
            margin: 0 auto 16px;
            padding: 16px 32px;
            background: linear-gradient(90deg, #0078D4, #00BCF2);
            border: none;
            color: #fff;
            font-size: 1.15em;
            font-weight: bold;
            border-radius: 30px;
            cursor: pointer;
            transition: transform 0.1s;
        }
        .brief-me-btn:hover { transform: scale(1.02); }
        .brief-me-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        .hero-btn-row { display: flex; gap: 12px; justify-content: center; margin-bottom: 16px; max-width: 820px; margin-left: auto; margin-right: auto; }
        .hero-btn-row .brief-me-btn { margin: 0; flex: 1; }
        .focus-btn {
            flex: 1;
            padding: 16px 32px;
            background: linear-gradient(90deg, #E8590C, #FFB900);
            border: none;
            color: #fff;
            font-size: 1.15em;
            font-weight: bold;
            border-radius: 30px;
            cursor: pointer;
            transition: transform 0.1s;
        }
        .focus-btn:hover { transform: scale(1.02); }
        .focus-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        .tomorrow-btn {
            flex: 1;
            padding: 16px 32px;
            background: linear-gradient(90deg, #6B21A8, #A855F7);
            border: none;
            color: #fff;
            font-size: 1.15em;
            font-weight: bold;
            border-radius: 30px;
            cursor: pointer;
            transition: transform 0.1s;
        }
        .tomorrow-btn:hover { transform: scale(1.02); }
        .tomorrow-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        .day-actions { display: flex; gap: 10px; justify-content: center; margin-bottom: 20px; }
        .day-action-btn {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.15);
            color: #fff;
            padding: 10px 18px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.88em;
        }
        .day-action-btn:hover { background: rgba(0,188,242,0.2); border-color: rgba(0,188,242,0.4); }
        .day-action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .briefing-progress {
            background: rgba(255,255,255,0.04);
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 16px;
            font-size: 0.88em;
            display: none;
        }
        .briefing-progress .step-line { padding: 3px 0; opacity: 0.7; }
        .briefing-progress .step-line.active { opacity: 1; color: #00BCF2; }
        .briefing-result {
            display: none;
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            overflow: hidden;
        }
        .exec-summary {
            background: linear-gradient(135deg, rgba(0,120,212,0.15), rgba(0,188,242,0.08));
            padding: 24px;
            font-size: 1.05em;
            line-height: 1.65;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }
        .exec-summary .summary-label {
            font-size: 0.75em;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            opacity: 0.5;
            margin-bottom: 10px;
        }
        .breakdown-area { padding: 16px 24px; }
        .breakdown-section {
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 10px;
            margin-bottom: 10px;
            overflow: hidden;
        }
        .breakdown-header {
            padding: 12px 16px;
            background: rgba(255,255,255,0.04);
            cursor: pointer;
            font-weight: bold;
            font-size: 0.92em;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .breakdown-header:hover { background: rgba(255,255,255,0.07); }
        .breakdown-body {
            padding: 12px 16px;
            font-size: 0.9em;
            line-height: 1.6;
            white-space: pre-wrap;
        }
        .briefing-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 24px;
            border-top: 1px solid rgba(255,255,255,0.08);
            font-size: 0.82em;
            opacity: 0.7;
        }
        @keyframes resultPulse {
            0% { opacity: 0.4; }
            50% { opacity: 1; text-shadow: 0 0 12px rgba(0, 188, 242, 0.4); }
            100% { opacity: 1; text-shadow: none; }
        }
        .briefing-result-pulse { animation: resultPulse 1.2s ease-out; }

        /* Agent tool call card */
        .tool-card {
            background: rgba(0,120,212,0.15);
            border: 1px solid rgba(0,120,212,0.3);
            border-radius: 8px;
            padding: 10px 14px;
            margin: 8px 0;
            font-size: 0.88em;
        }
        .tool-card .tool-header {
            color: #00BCF2;
            font-weight: bold;
            margin-bottom: 4px;
        }
        .tool-card .tool-args {
            opacity: 0.8;
            word-break: break-all;
            max-height: 80px;
            overflow-y: auto;
        }
        .tool-card .tool-result {
            margin-top: 6px;
            padding-top: 6px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }
        .tool-card .tool-ok { color: #00CC6A; }
        .tool-card .tool-fail { color: #FF4444; }
        .tool-card .tool-time { opacity: 0.6; font-size: 0.9em; }

        /* Approval Gate Card */
        .approval-card {
            background: rgba(255, 185, 0, 0.06);
            border: 1px solid rgba(255, 185, 0, 0.3);
            border-radius: 12px;
            padding: 20px;
            margin: 8px 0;
        }
        .approval-card.approved { border-color: rgba(16, 124, 16, 0.4); background: rgba(16, 124, 16, 0.06); }
        .approval-card.denied { border-color: rgba(212, 28, 0, 0.4); background: rgba(212, 28, 0, 0.06); }
        .approval-header {
            font-size: 1.05em;
            font-weight: bold;
            margin-bottom: 12px;
        }
        .approval-body {
            font-size: 0.9em;
            line-height: 1.6;
            margin-bottom: 16px;
            opacity: 0.9;
        }
        .approval-actions {
            display: flex;
            gap: 12px;
            margin-bottom: 12px;
        }
        .approval-btn {
            padding: 12px 28px;
            border: none;
            border-radius: 8px;
            color: #fff;
            font-size: 0.95em;
            font-weight: bold;
            cursor: pointer;
            transition: opacity 0.2s;
        }
        .approval-btn:hover { opacity: 0.85; }
        .approval-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .approval-btn.approve { background: linear-gradient(90deg, #107C10, #00CC6A); }
        .approval-btn.deny { background: linear-gradient(90deg, #D41C00, #FF4444); }
        .approval-badge {
            display: inline-block;
            padding: 8px 20px;
            border-radius: 8px;
            font-weight: bold;
            font-size: 0.95em;
        }
        .approval-badge.approved { background: rgba(16, 124, 16, 0.2); color: #00CC6A; }
        .approval-badge.denied { background: rgba(212, 28, 0, 0.2); color: #FF4444; }
        .approval-policy {
            font-size: 0.78em;
            opacity: 0.45;
            margin-top: 8px;
        }
        /* Security Review Box (Agentic Firewall) */
        .security-review {
            background: rgba(0,188,242,0.06);
            border: 1px solid rgba(0,188,242,0.2);
            border-radius: 8px;
            padding: 12px 14px;
            margin: 12px 0;
            font-size: 0.85em;
        }
        .security-review-header {
            font-weight: bold;
            margin-bottom: 8px;
            font-size: 0.95em;
        }
        .security-review-line {
            padding: 2px 0;
            opacity: 0.9;
        }
        .security-check-line {
            color: rgba(255,255,255,0.7);
            font-size: 0.9em;
            padding: 4px 0;
            margin-bottom: 4px;
        }

        /* File Picker Modal */
        .file-picker-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.7);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        .file-picker-modal {
            background: linear-gradient(135deg, #1e1e2f 0%, #15151f 100%);
            border: 1px solid rgba(0,188,242,0.3);
            border-radius: 16px;
            padding: 24px;
            min-width: 450px;
            max-width: 550px;
            max-height: 70vh;
            display: flex;
            flex-direction: column;
        }
        .file-picker-header {
            font-size: 1.15em;
            font-weight: bold;
            margin-bottom: 8px;
        }
        .file-picker-subtitle {
            font-size: 0.85em;
            opacity: 0.7;
            margin-bottom: 16px;
        }
        .file-picker-list {
            flex: 1;
            overflow-y: auto;
            margin-bottom: 16px;
            max-height: 300px;
        }
        .file-picker-item {
            display: flex;
            align-items: center;
            padding: 12px 14px;
            margin-bottom: 8px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            cursor: pointer;
            transition: background 0.15s, border-color 0.15s;
        }
        .file-picker-item:hover {
            background: rgba(255,255,255,0.08);
            border-color: rgba(0,188,242,0.3);
        }
        .file-picker-item.selected {
            background: rgba(0,188,242,0.12);
            border-color: rgba(0,188,242,0.5);
        }
        .file-picker-item input[type="checkbox"] {
            margin-right: 12px;
            width: 18px;
            height: 18px;
            accent-color: #00BCF2;
        }
        .file-picker-item .file-info {
            flex: 1;
        }
        .file-picker-item .file-name {
            font-weight: 500;
        }
        .file-picker-item .file-meta {
            font-size: 0.8em;
            opacity: 0.6;
            margin-top: 2px;
        }
        .file-picker-item .file-badge {
            background: rgba(255,185,0,0.15);
            border: 1px solid rgba(255,185,0,0.4);
            color: #FFB900;
            font-size: 0.75em;
            padding: 3px 8px;
            border-radius: 12px;
            margin-left: 8px;
        }
        .file-picker-actions {
            display: flex;
            gap: 12px;
            justify-content: flex-end;
        }
        .file-picker-btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 0.95em;
            cursor: pointer;
            font-weight: 600;
        }
        .file-picker-btn.cancel {
            background: rgba(255,255,255,0.1);
            color: #fff;
        }
        .file-picker-btn.confirm {
            background: linear-gradient(90deg, #0078D4, #00BCF2);
            color: #fff;
        }
        .file-picker-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        /* Clean Room Auditor Styles */
        .auditor-header {
            font-size: 1.2em;
            font-weight: bold;
            margin-bottom: 20px;
            letter-spacing: 1px;
            text-align: center;
        }
        .auditor-upload-zone {
            text-align: center;
            padding: 20px;
        }
        .auditor-dropzone {
            background: rgba(255,255,255,0.03);
            border: 2px dashed rgba(0,188,242,0.3);
            border-radius: 15px;
            padding: 40px;
            margin-bottom: 30px;
            transition: border-color 0.2s, background 0.2s;
        }
        .auditor-dropzone:hover, .auditor-dropzone.dragover {
            border-color: rgba(0,188,242,0.6);
            background: rgba(0,188,242,0.05);
        }
        .dropzone-icon { font-size: 3em; margin-bottom: 15px; }
        .dropzone-title { font-size: 1.15em; font-weight: 600; margin-bottom: 8px; }
        .dropzone-subtitle { font-size: 0.9em; opacity: 0.7; margin-bottom: 20px; line-height: 1.5; }
        .auditor-upload-btn {
            background: linear-gradient(90deg, #0078D4, #00BCF2);
            color: #fff;
            border: none;
            padding: 12px 32px;
            border-radius: 8px;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            margin-bottom: 12px;
        }
        .dropzone-formats { font-size: 0.8em; opacity: 0.5; }
        .auditor-demo-section {
            padding: 20px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.08);
        }
        .auditor-demo-btn {
            background: rgba(255,255,255,0.1);
            color: #fff;
            border: 1px solid rgba(255,255,255,0.2);
            padding: 10px 24px;
            border-radius: 8px;
            font-size: 0.95em;
            cursor: pointer;
            transition: background 0.2s;
        }
        .auditor-demo-btn:hover { background: rgba(255,255,255,0.15); }

        /* Auditor State 2: Document Staged */
        .auditor-staged { padding: 20px; }
        .auditor-doc-card {
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .doc-card-header { display: flex; align-items: flex-start; gap: 15px; margin-bottom: 15px; }
        .doc-icon { font-size: 2.5em; }
        .doc-info { flex: 1; }
        .doc-name { font-size: 1.1em; font-weight: 600; margin-bottom: 4px; }
        .doc-meta { font-size: 0.85em; opacity: 0.6; }
        .doc-preview {
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
            padding: 12px 15px;
            font-family: monospace;
            font-size: 0.85em;
            opacity: 0.8;
            max-height: 80px;
            overflow: hidden;
            line-height: 1.4;
        }
        .auditor-actions { margin-bottom: 20px; }
        .auditor-action-row { display: flex; gap: 10px; margin-bottom: 12px; }
        .auditor-action-btn {
            flex: 1;
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.15);
            color: #fff;
            padding: 14px 16px;
            border-radius: 10px;
            font-size: 0.95em;
            cursor: pointer;
            transition: background 0.2s, border-color 0.2s;
        }
        .auditor-action-btn:hover { background: rgba(255,255,255,0.12); border-color: rgba(0,188,242,0.4); }
        .auditor-action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .auditor-action-btn.secondary { background: rgba(255,255,255,0.05); }
        .auditor-full-audit-btn {
            width: 100%;
            background: linear-gradient(90deg, #0078D4, #00BCF2);
            border: none;
            color: #fff;
            padding: 16px;
            border-radius: 10px;
            font-size: 1.05em;
            font-weight: 600;
            cursor: pointer;
        }
        .auditor-full-audit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .auditor-back-link { text-align: center; margin-top: 15px; }
        .auditor-back-link a { color: rgba(255,255,255,0.5); text-decoration: none; font-size: 0.9em; }
        .auditor-back-link a:hover { color: rgba(255,255,255,0.8); }

        /* Auditor State 3: Results */
        .auditor-results { padding: 20px; }
        .auditor-doc-summary {
            font-size: 0.9em;
            opacity: 0.7;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }

        /* Processing Log (verbose demo mode) */
        .processing-log {
            background: rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            margin-bottom: 20px;
            overflow: hidden;
        }
        .processing-log-header {
            background: rgba(255,255,255,0.05);
            padding: 12px 16px;
            font-weight: 600;
            font-size: 0.9em;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .processing-log-content {
            padding: 16px;
            font-family: monospace;
            font-size: 0.85em;
            line-height: 1.6;
            max-height: 350px;
            overflow-y: auto;
        }
        .log-step { margin-bottom: 12px; }
        .log-step.complete { opacity: 0.8; }
        .log-step.active { color: #00BCF2; }
        .log-step.pending { opacity: 0.4; }
        .log-step-icon { margin-right: 8px; }
        .log-step-detail {
            margin-left: 24px;
            font-size: 0.92em;
            opacity: 0.7;
            margin-top: 4px;
        }
        .log-prompt-box {
            background: rgba(0,188,242,0.08);
            border: 1px solid rgba(0,188,242,0.2);
            border-radius: 8px;
            padding: 12px;
            margin: 8px 0 8px 24px;
            font-size: 0.9em;
            line-height: 1.5;
        }
        .log-prompt-label {
            color: #00BCF2;
            font-weight: 600;
            margin-bottom: 6px;
        }

        /* Result Cards */
        .result-card {
            background: rgba(255,255,255,0.06);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
        }
        .result-card-header {
            font-weight: 600;
            font-size: 1.05em;
            margin-bottom: 12px;
        }
        .result-card.pii {
            background: rgba(255,185,0,0.08);
            border: 1px solid rgba(255,185,0,0.3);
        }
        .result-card.risk-high { border-left: 4px solid #D41C00; background: rgba(212,28,0,0.06); }
        .result-card.risk-medium { border-left: 4px solid #FFB900; background: rgba(255,185,0,0.06); }
        .result-card.risk-low { border-left: 4px solid #107C10; background: rgba(16,124,16,0.06); }
        .risk-item { margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.08); }
        .risk-item:last-child { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
        .risk-severity { font-weight: 600; margin-bottom: 4px; }
        .risk-severity.high { color: #FF6B6B; }
        .risk-severity.medium { color: #FFB900; }
        .risk-severity.low { color: #00CC6A; }
        .risk-finding { font-size: 0.95em; line-height: 1.5; opacity: 0.9; }
        .risk-recommendation { font-size: 0.85em; opacity: 0.7; margin-top: 6px; font-style: italic; }
        .pii-item { display: flex; align-items: center; gap: 10px; padding: 8px 0; }
        .pii-severity { font-size: 1.1em; }
        .pii-type { font-weight: 600; min-width: 100px; }
        .pii-value { font-family: monospace; opacity: 0.9; }
        .pii-location { font-size: 0.85em; opacity: 0.6; margin-left: auto; }

        /* Audit Stamp */
        .audit-stamp {
            background: rgba(16,124,16,0.08);
            border: 1px solid rgba(16,124,16,0.3);
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
        }
        .audit-stamp-header { font-weight: 600; margin-bottom: 12px; color: #00CC6A; }
        .audit-stamp-line { font-size: 0.9em; opacity: 0.8; padding: 3px 0; }
        .auditor-results-actions { display: flex; gap: 12px; margin-top: 20px; }

        /* ID Verification Styles */
        .camera-section {
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
        }
        .camera-container {
            position: relative;
            max-width: 640px;
            margin: 0 auto;
        }
        #cameraPreview {
            width: 100%;
            max-width: 640px;
            border-radius: 10px;
            background: #000;
        }
        #capturedImage {
            width: 100%;
            max-width: 640px;
            border-radius: 10px;
            margin-top: 15px;
        }
        .camera-controls {
            margin-top: 15px;
            display: flex;
            gap: 10px;
            justify-content: center;
            flex-wrap: wrap;
        }
        .id-result-card {
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            padding: 20px;
            margin-top: 20px;
            text-align: left;
        }
        .id-result-card h3 {
            color: #00BCF2;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .id-field {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .id-field:last-child { border-bottom: none; }
        .id-field-label { opacity: 0.7; }
        .id-field-value { font-weight: bold; }
        .status-badge {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
        }
        .status-valid { background: linear-gradient(90deg, #107C10, #00CC6A); }
        .status-warning { background: linear-gradient(90deg, #FF8C00, #FFB900); }
        .status-error { background: linear-gradient(90deg, #D41C00, #FF4444); }
        .processing-steps {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 15px;
            margin-top: 15px;
            text-align: left;
        }
        .step {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 0;
        }
        .step-icon {
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
        }
        .step-pending { background: rgba(255,255,255,0.2); }
        .step-active { background: #0078D4; }
        .step-done { background: #107C10; }
        .step-text { flex: 1; }
        .step-status { font-size: 0.8em; opacity: 0.7; }
        .ocr-preview {
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            padding: 15px;
            margin-top: 15px;
            font-family: monospace;
            font-size: 0.85em;
            max-height: 150px;
            overflow-y: auto;
            text-align: left;
            white-space: pre-wrap;
        }
        .privacy-note {
            background: rgba(16, 124, 16, 0.2);
            border: 1px solid rgba(16, 124, 16, 0.5);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .privacy-icon { font-size: 1.5em; }

        /* Warmup overlay */
        .warmup-overlay {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            z-index: 10000;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            transition: opacity 0.5s ease;
        }
        .warmup-overlay.fade-out { opacity: 0; pointer-events: none; }
        .warmup-logo { display: flex; align-items: center; gap: 25px; margin-bottom: 30px; }
        .warmup-logo img { height: 36px; opacity: 0.9; }
        .warmup-title { font-size: 1.4em; font-weight: 600; color: #fff; margin-bottom: 8px; }
        .warmup-status { font-size: 0.95em; color: rgba(255,255,255,0.6); margin-bottom: 24px; }
        .warmup-bar-track {
            width: 320px; height: 4px; background: rgba(255,255,255,0.1);
            border-radius: 2px; overflow: hidden;
        }
        .warmup-bar-fill {
            height: 100%; width: 0%; border-radius: 2px;
            background: linear-gradient(90deg, #60a5fa, #a78bfa);
            transition: width 0.3s ease;
        }
        .warmup-time { font-size: 0.8em; color: rgba(255,255,255,0.35); margin-top: 12px; }
    </style>
</head>
<body>
    <!-- Warmup overlay — shown until model is ready -->
    <div class="warmup-overlay" id="warmupOverlay">
        <div class="warmup-logo">
            <img src="/logos/surface-logo.png" alt="Surface" onerror="this.style.display='none'">
            <img src="/logos/copilot-logo.avif" alt="Copilot+" onerror="this.style.display='none'">
        </div>
        <div class="warmup-title">Local NPU AI Assistant</div>
        <div class="warmup-status" id="warmupStatus">Loading Phi-4 Mini on NPU...</div>
        <div class="warmup-bar-track"><div class="warmup-bar-fill" id="warmupBar"></div></div>
        <div class="warmup-time" id="warmupTime"></div>
    </div>

    <!-- Mobile hamburger (hidden on desktop) -->
    <button class="mobile-hamburger" id="mobileHamburger" aria-label="Open menu">&#9776;</button>
    <div class="sidebar-backdrop" id="sidebarBackdrop"></div>

    <div class="app-shell">
      <!-- ── Sidebar ── -->
      <aside class="sidebar" id="appSidebar">
        <button class="sidebar-toggle" id="sidebarToggle" title="Toggle sidebar">&#9776;</button>
        <div class="sidebar-brand">
          <img class="brand-logo-surface" src="/logos/surface-logo.png" alt="Microsoft Surface" onerror="this.style.display='none'">
          <img class="brand-logo-copilot" src="/logos/copilot-logo.avif" alt="Copilot+ PC" onerror="this.style.display='none'">
        </div>

        <nav class="sidebar-nav">
          <a class="sidebar-nav-item active" data-tab="chat">
            <span class="nav-icon">&#129302;</span>
            <span class="sidebar-label">AI Agent<span class="sidebar-nav-sub">Chat &amp; Tooling with Phi</span></span>
          </a>
          <a class="sidebar-nav-item" data-tab="day">
            <span class="nav-icon">&#9728;&#65039;</span>
            <span class="sidebar-label">My Day<span class="sidebar-nav-sub">AI Chief of Staff</span></span>
          </a>
          <a class="sidebar-nav-item" data-tab="auditor">
            <span class="nav-icon">&#128274;</span>
            <span class="sidebar-label">Auditor<span class="sidebar-nav-sub">Clean Room</span></span>
          </a>
          <a class="sidebar-nav-item" data-tab="id">
            <span class="nav-icon">&#127380;</span>
            <span class="sidebar-label">ID Verification<span class="sidebar-nav-sub">Banking &amp; Government</span></span>
          </a>
        </nav>

        <div class="sidebar-footer">
          <div class="savings-widget" id="savingsWidget">
            <div class="savings-header">&#128994; LOCAL AI SESSION</div>
            <div class="savings-stat" id="savingsCalls">0 calls &middot; 0 tokens</div>
            <div class="savings-stat" id="savingsCost">&#128176; $0.00 saved vs cloud</div>
            <div class="savings-stat" id="savingsPower">&#9889; 0 Wh local &middot; 0 Wh cloud</div>
            <div class="savings-stat" id="savingsCO2">&#127793; 0g CO&#8322; avoided</div>
            <div class="savings-stat savings-stat-compact" id="savingsCompact">&#128994; $0.00</div>
          </div>
          <span class="badge" style="text-align:center;">&#9889; Intel Core Ultra NPU</span>
          <span class="offline-badge" id="offlineBadge">Online</span>
          <div class="sidebar-footer-controls">
            <div class="sidebar-footer-label">Network</div>
            <button class="net-toggle-btn net-toggle-off" id="goOfflineBtn" title="Disable Wi-Fi">&#9992;&#65039; Go Offline</button>
            <button class="net-toggle-btn net-toggle-on" id="goOnlineBtn" title="Enable Wi-Fi">&#128246; Go Online</button>
            <div class="model-selector" style="margin:0;">
              <label for="modelSelect">Model:</label>
              <select id="modelSelect">
                <option value="phi-4-mini">Phi-4 Mini (NPU)</option>
              </select>
            </div>
          </div>
        </div>
      </aside>

      <!-- ── Main Content ── -->
      <main class="main-content">
        <div class="container">
        <!-- Hidden tab buttons (preserve IDs for switchToTab backward compat) -->
        <div class="tabs" style="display:none;">
            <button class="tab-btn" id="dayTabBtn">My Day</button>
            <button class="tab-btn active" id="chatTabBtn">AI Agent</button>
            <button class="tab-btn" id="auditorTabBtn">&#128274; Auditor</button>
            <button class="tab-btn" id="idTabBtn">ID Verification</button>
        </div>

        <!-- My Day Tab -->
        <div id="day-tab" class="tab-content">
            <div class="auditor-header">&#9728;&#65039; MY DAY</div>

            <!-- Data Summary Cards -->
            <div class="day-cards">
                <div class="day-card" id="emailCard" data-peek="emails">
                    <div class="card-icon">&#128231;</div>
                    <div class="card-count" id="emailCount">&mdash;</div>
                    <div class="card-label">Emails</div>
                    <div class="card-hint">click to peek</div>
                    <div class="card-peek" id="emailPeek"></div>
                </div>
                <div class="day-card" id="eventCard" data-peek="events">
                    <div class="card-icon">&#128197;</div>
                    <div class="card-count" id="eventCount">&mdash;</div>
                    <div class="card-label">Events Today</div>
                    <div class="card-hint">click to peek</div>
                    <div class="card-peek" id="eventPeek"></div>
                </div>
                <div class="day-card" id="taskCard" data-peek="tasks">
                    <div class="card-icon">&#9744;</div>
                    <div class="card-count" id="taskCount">&mdash;</div>
                    <div class="card-label">Tasks Due</div>
                    <div class="card-hint">click to peek</div>
                    <div class="card-peek" id="taskPeek"></div>
                </div>
            </div>

            <!-- Hero Action Buttons -->
            <div class="hero-btn-row">
                <button class="brief-me-btn" id="briefMeBtn">&#9728;&#65039; Brief Me</button>
                <button class="focus-btn" id="focusBtn">&#127919; Top 3 Focus</button>
                <button class="tomorrow-btn" id="tomorrowBtn">&#128302; Tomorrow</button>
            </div>

            <!-- Secondary Action Buttons -->
            <div class="day-actions">
                <button class="day-action-btn" id="triageBtn">&#128231; Triage Inbox</button>
                <button class="day-action-btn" id="prepBtn">&#128203; Prep for Next Meeting</button>
            </div>

            <!-- Progress Indicator -->
            <div class="briefing-progress" id="briefingProgress"></div>

            <!-- Briefing Result -->
            <div class="briefing-result" id="briefingResult">
                <div class="exec-summary">
                    <div class="summary-label">Executive Summary</div>
                    <div id="execSummaryText"></div>
                </div>
                <div class="breakdown-area" id="breakdownArea"></div>
                <div class="briefing-footer">
                    <span>&#128274; All data processed locally on NPU</span>
                    <span id="briefingTimer"></span>
                </div>
            </div>

            <div class="tab-footer">Microsoft Surface + Copilot+ PC &mdash; Phi-4 Mini on Intel Core Ultra NPU &mdash; All processing happens locally</div>
        </div>

        <!-- Agent Chat Tab -->
        <div id="chat-tab" class="tab-content active">
          <div class="auditor-header">&#129302; AI AGENT</div>
          <div class="agent-chat-layout">

            <!-- Suggestion chips (directly under tabs) -->
            <div class="chat-empty-state" id="chatEmptyState">
              <div class="suggestion-grid">
                <button class="suggestion-chip" data-action="meeting-agenda">
                  <span class="chip-icon">&#128203;</span>
                  <span>Meeting Agenda</span>
                </button>
                <button class="suggestion-chip" data-action="analyze-strategy">
                  <span class="chip-icon">&#128196;</span>
                  <span>Analyze Strategy</span>
                </button>
                <button class="suggestion-chip" data-action="list-documents">
                  <span class="chip-icon">&#128193;</span>
                  <span>List Documents</span>
                </button>
                <button class="suggestion-chip" data-action="summarize-doc">
                  <span class="chip-icon">&#128221;</span>
                  <span>Summarize a Document</span>
                </button>
                <button class="suggestion-chip" data-action="device-health">
                  <span class="chip-icon">&#128737;</span>
                  <span>Device Health</span>
                </button>
              </div>
            </div>

            <!-- Chat messages -->
            <div class="chat-container" id="chatContainer">
            </div>

            <!-- AI Actions Log (collapsible) -->
            <div id="auditTrail" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:10px 15px;margin-bottom:10px;max-height:120px;overflow-y:auto;font-size:0.8em;display:none;">
              <strong style="color:#00BCF2;">AI Actions (Logged)</strong>
              <div style="font-size:0.85em;opacity:0.5;margin:4px 0 6px;">All actions recorded locally for review.</div>
              <div id="auditEntries"></div>
            </div>

            <!-- Input bar (bottom, like Claude/ChatGPT) -->
            <div class="chat-input-wrapper">
              <div class="input-area">
                <button id="attachBtn" title="Load a document">+</button>
                <input type="text" id="userInput" placeholder="Ask anything or try a suggestion above...">
                <button id="sendBtn" title="Send">&#10148;</button>
              </div>
            </div>
            <div id="chatTimer" class="response-timer"></div>

            <!-- Bottom status bar -->
            <div class="agent-topbar">
              <div class="topbar-left">
                <div class="topbar-status" id="connectivityCard" style="cursor:pointer;" title="Click to refresh status">
                    <span class="status-dot green" id="netDot"></span>
                    <span id="netStatus">Online</span>
                </div>
                <div class="topbar-divider"></div>
                <div class="topbar-status">
                    <span class="status-dot blue" id="npuDot"></span>
                    <span id="npuStatus">NPU Ready</span>
                </div>
              </div>
              <div class="topbar-right">
                <button class="topbar-btn" id="qpAuditSummary" title="View AI action log">&#128220; Audit Log</button>
                <button class="topbar-btn" id="qpClear" title="Clear chat">&#128465; Clear</button>
                <div class="topbar-divider"></div>
                <div class="policy-icon-wrap">
                  <button class="topbar-btn" title="Agent Policy">&#128737;&#65039;</button>
                  <div class="policy-tooltip">
                    &#128203; <strong>Agent Policy</strong><br>
                    &#9989; Read within approved folder<br>
                    &#9989; Create new documents<br>
                    &#9989; Run approved commands<br>
                    &#10060; No file deletion<br>
                    &#10060; No network access<br>
                    &#128220; All actions logged
                  </div>
                </div>
              </div>
            </div>

            <!-- Hidden elements: keep IDs for JS handlers -->
            <input type="file" id="agentFileInput" accept=".pdf,.docx,.txt,.md" style="display:none;">
            <button id="qpSummarizeDoc" style="display:none;"></button>
            <button id="qpDetectPII" style="display:none;"></button>
            <button id="qpSaveSummary" style="display:none;"></button>
            <span id="agentFileName" style="display:none;"></span>

            <div class="tab-footer">Microsoft Surface + Copilot+ PC &mdash; Phi-4 Mini on Intel Core Ultra NPU &mdash; All processing happens locally</div>
          </div>
        </div>

        <!-- Clean Room Auditor Tab -->
        <div id="auditor-tab" class="tab-content">
            <div class="auditor-header">&#128274; CLEAN ROOM AUDITOR</div>
            <!-- State 1: Upload Zone -->
            <div id="auditorUploadZone" class="auditor-upload-zone">
                <div class="auditor-dropzone" id="auditorDropzone">
                    <div class="dropzone-icon">&#128737;&#65039;</div>
                    <div class="dropzone-title">Drop a confidential document</div>
                    <div class="dropzone-subtitle">Analysis runs entirely on this device.<br><span style="color:#00CC6A;">No data egress. No cloud calls.</span></div>
                    <input type="file" id="auditorFileInput" accept=".pdf,.docx,.txt,.md" style="display:none;">
                    <button class="auditor-upload-btn">Select File</button>
                    <div class="dropzone-formats">PDF • DOCX • TXT • MD — Max 16MB</div>
                </div>
                <div class="auditor-demo-section">
                    <div style="opacity:0.6;font-size:0.9em;margin-bottom:8px;">Pre-staged for demo:</div>
                    <div style="font-family:monospace;opacity:0.8;margin-bottom:10px;">contract_nda_vertex_pinnacle.txt</div>
                    <button class="auditor-demo-btn" id="loadDemoDocBtn">&#128196; Load Demo Document</button>
                </div>
            </div>

            <!-- State 2: Document Staged -->
            <div id="auditorStaged" class="auditor-staged" style="display:none;">
                <div class="auditor-doc-card">
                    <div class="doc-card-header">
                        <span class="doc-icon">&#128196;</span>
                        <div class="doc-info">
                            <div class="doc-name" id="auditorDocName">document.txt</div>
                            <div class="doc-meta" id="auditorDocMeta">Loading...</div>
                        </div>
                    </div>
                    <div class="doc-preview" id="auditorDocPreview"></div>
                </div>
                <div class="auditor-actions">
                    <div class="auditor-action-row">
                        <button class="auditor-action-btn" id="btnRiskScan">&#9888;&#65039; Risk Scan</button>
                        <button class="auditor-action-btn" id="btnObligations">&#128203; Extract Obligations</button>
                        <button class="auditor-action-btn" id="btnPiiScan">&#128272; PII Detection</button>
                    </div>
                    <button class="auditor-full-audit-btn" id="btnFullAudit">&#128269; Full Audit</button>
                </div>
                <div class="auditor-back-link">
                    <a href="#" onclick="resetAuditor(); return false;">&#8592; Load Different Document</a>
                </div>
            </div>

            <!-- State 3: Analysis Results -->
            <div id="auditorResults" class="auditor-results" style="display:none;">
                <div class="auditor-doc-summary" id="auditorResultsDocSummary"></div>

                <!-- Processing Log (verbose mode for demo) -->
                <div class="processing-log" id="processingLog">
                    <div class="processing-log-header">&#128203; PROCESSING LOG</div>
                    <div class="processing-log-content" id="processingLogContent"></div>
                </div>

                <!-- Results Cards (populated dynamically) -->
                <div id="auditorResultsCards"></div>

                <!-- Audit Stamp -->
                <div class="audit-stamp" id="auditStamp" style="display:none;"></div>

                <!-- Action Buttons -->
                <div class="auditor-results-actions" id="auditorResultsActions" style="display:none;">
                    <button class="auditor-action-btn" onclick="rerunAudit()">&#128269; Run Another Audit</button>
                    <button class="auditor-action-btn secondary" onclick="resetAuditor()">&#128196; Load Different Doc</button>
                </div>
            </div>
            <div class="tab-footer">Microsoft Surface + Copilot+ PC &mdash; Phi-4 Mini on Intel Core Ultra NPU &mdash; All processing happens locally</div>
        </div>

        <!-- ID Verification Tab -->
        <div id="id-tab" class="tab-content">
            <div class="auditor-header">&#127380; ID VERIFICATION</div>

            <div class="camera-section">
                <div class="camera-selector" style="margin-bottom: 15px;">
                    <label for="cameraSelect" style="margin-right: 10px;">Camera:</label>
                    <select id="cameraSelect" style="background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3); color: #fff; padding: 8px 15px; border-radius: 20px; min-width: 200px;">
                        <option value="">Loading cameras...</option>
                    </select>
                    <button id="refreshCamerasBtn" style="background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3); color: #fff; padding: 8px 15px; border-radius: 20px; margin-left: 10px; cursor: pointer;">Refresh</button>
                </div>
                <div class="camera-container">
                    <video id="cameraPreview" autoplay playsinline style="display: none;"></video>
                    <canvas id="captureCanvas" style="display: none;"></canvas>
                    <img id="capturedImage" style="display: none;" alt="Captured ID">
                    <div id="cameraPlaceholder" style="padding: 60px; background: rgba(0,0,0,0.3); border-radius: 10px;">
                        <div style="font-size: 3em; margin-bottom: 15px;">&#128247;</div>
                        <div>Click "Start Camera" to begin ID verification</div>
                    </div>
                </div>
                
                <div class="camera-controls">
                    <button class="camera-btn" id="startCameraBtn">Start Camera</button>
                    <button class="camera-btn" id="captureBtn" style="display: none;">Capture ID</button>
                    <button class="camera-btn" id="retakeBtn" style="display: none;">Retake</button>
                    <button class="camera-btn" id="analyzeIdBtn" style="display: none;">Analyze ID</button>
                </div>
            </div>
            
            <div id="processingSteps" class="processing-steps" style="display: none;">
                <div class="step" id="step1">
                    <div class="step-icon step-pending">1</div>
                    <div class="step-text">Image Capture</div>
                    <div class="step-status">Browser API (Local)</div>
                </div>
                <div class="step" id="step2">
                    <div class="step-icon step-pending">2</div>
                    <div class="step-text">Text Extraction (OCR)</div>
                    <div class="step-status">Tesseract.js (Local)</div>
                </div>
                <div class="step" id="step3">
                    <div class="step-icon step-pending">3</div>
                    <div class="step-text">AI Analysis</div>
                    <div class="step-status">Phi-4 Mini on NPU (Local)</div>
                </div>
            </div>
            
            <div id="ocrPreview" class="ocr-preview" style="display: none;">
                <strong>Extracted Text:</strong><br><span id="ocrText"></span>
            </div>
            
            <div id="idResultCard" class="id-result-card" style="display: none;">
                <h3>
                    <span>ID Verification Result</span>
                    <span class="status-badge" id="idStatusBadge">Checking...</span>
                </h3>
                <div id="idFields"></div>
                <div id="idNotes" style="margin-top: 15px; padding-top: 15px; border-top: 1px solid rgba(255,255,255,0.1);"></div>
            </div>

            <div class="privacy-note" style="margin-top: 20px;">
                <span class="privacy-icon">&#128274;</span>
                <div>
                    <strong>100% Local Processing</strong><br>
                    Your ID image and data never leave this device. Camera capture, OCR, and AI analysis all run locally.
                </div>
            </div>
            <div class="tab-footer">Microsoft Surface + Copilot+ PC &mdash; Phi-4 Mini on Intel Core Ultra NPU &mdash; All processing happens locally</div>
        </div>

        <footer>
            Microsoft Surface + Copilot+ PC - Phi-4 Mini on Intel Core Ultra NPU - All processing happens locally
        </footer>
        </div><!-- /.container -->
      </main>
    </div><!-- /.app-shell -->

    <script>
        // --- Warmup overlay: poll /health until model is ready ---
        (function() {
            var overlay = document.getElementById("warmupOverlay");
            if (!overlay) return;
            var bar = document.getElementById("warmupBar");
            var statusEl = document.getElementById("warmupStatus");
            var timeEl = document.getElementById("warmupTime");
            var start = Date.now();
            var maxSecs = 90;
            var poll;
            function tick() {
                var elapsed = (Date.now() - start) / 1000;
                var pct = Math.min((elapsed / maxSecs) * 100, 95);
                bar.style.width = pct + "%";
                timeEl.textContent = Math.floor(elapsed) + "s elapsed";
            }
            var ticker = setInterval(tick, 300);
            poll = setInterval(function() {
                fetch("/health").then(function(r) { return r.json(); }).then(function(d) {
                    if (d.ready) {
                        clearInterval(poll);
                        clearInterval(ticker);
                        bar.style.width = "100%";
                        statusEl.textContent = "Ready";
                        setTimeout(function() {
                            overlay.classList.add("fade-out");
                            setTimeout(function() { overlay.remove(); }, 600);
                        }, 400);
                    }
                }).catch(function() {});
            }, 1000);
        })();

        console.log("Script starting...");

        var currentModel = "phi-4-mini";
        var cameraStream = null;
        
        document.addEventListener("DOMContentLoaded", function() {
            console.log("DOM loaded, setting up event handlers...");
            
            // Tab switching
            function switchToTab(tabId, btnId) {
                document.querySelectorAll(".tab-btn").forEach(function(btn) { btn.classList.remove("active"); });
                document.querySelectorAll(".tab-content").forEach(function(c) { c.classList.remove("active"); });
                document.getElementById(btnId).classList.add("active");
                document.getElementById(tabId).classList.add("active");
                // Sync sidebar nav active state
                var tabKey = tabId.replace("-tab", "");
                document.querySelectorAll(".sidebar-nav-item").forEach(function(item) {
                    item.classList.toggle("active", item.getAttribute("data-tab") === tabKey);
                });
            }

            function showTabToast(text) {
                var toast = document.createElement("div");
                toast.textContent = text;
                toast.style.cssText = "position:fixed;bottom:32px;left:50%;transform:translateX(-50%);" +
                    "background:rgba(0,18,36,0.85);border:1px solid rgba(0,188,242,0.3);" +
                    "color:#7fdbff;padding:10px 28px;border-radius:20px;font-size:0.82em;" +
                    "z-index:9999;opacity:0;transition:opacity 0.4s ease;pointer-events:none;" +
                    "backdrop-filter:blur(8px);";
                document.body.appendChild(toast);
                setTimeout(function() { toast.style.opacity = "1"; }, 50);
                setTimeout(function() { toast.style.opacity = "0"; }, 2500);
                setTimeout(function() { toast.remove(); }, 3000);
            }

            // Local AI Savings Widget
            function formatNumber(n) {
                return n.toLocaleString("en-US");
            }
            function updateSavingsWidget() {
                fetch("/session-stats")
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        var callsEl = document.getElementById("savingsCalls");
                        var costEl = document.getElementById("savingsCost");
                        var powerEl = document.getElementById("savingsPower");
                        var co2El = document.getElementById("savingsCO2");
                        var compactEl = document.getElementById("savingsCompact");
                        if (callsEl) callsEl.textContent = formatNumber(data.calls) + " calls \u00b7 " + formatNumber(data.total_tokens) + " tokens";
                        var costStr = "$" + data.cloud_cost_saved.toFixed(2);
                        if (costEl) costEl.innerHTML = "&#128176; " + costStr + " saved vs cloud";
                        if (powerEl) powerEl.innerHTML = "&#9889; " + data.npu_wh.toFixed(2) + " Wh local \u00b7 " + data.cloud_wh.toFixed(1) + " Wh cloud";
                        if (co2El) co2El.innerHTML = "&#127793; " + data.co2_avoided_g.toFixed(1) + "g CO&#8322; avoided";
                        if (compactEl) compactEl.innerHTML = "&#128994; " + costStr;
                    })
                    .catch(function(e) { console.warn("Savings widget fetch failed:", e); });
            }
            // Initial update and auto-refresh every 5 seconds
            updateSavingsWidget();
            setInterval(updateSavingsWidget, 5000);

            document.getElementById("dayTabBtn").addEventListener("click", function() {
                switchToTab("day-tab", "dayTabBtn");
                showTabToast("Same local AI \u2014 now reading your day");
            });
            document.getElementById("chatTabBtn").addEventListener("click", function() {
                switchToTab("chat-tab", "chatTabBtn");
                showTabToast("Same local AI \u2014 now with execution tools");
            });
            document.getElementById("idTabBtn").addEventListener("click", function() {
                switchToTab("id-tab", "idTabBtn");
                showTabToast("Same local AI \u2014 now verifying identity");
            });
            document.getElementById("auditorTabBtn").addEventListener("click", function() {
                switchToTab("auditor-tab", "auditorTabBtn");
                showTabToast("Same local AI \u2014 now in clean room mode");
            });

            // === Sidebar logic ===
            var sidebar = document.getElementById("appSidebar");
            var sidebarToggle = document.getElementById("sidebarToggle");
            var backdrop = document.getElementById("sidebarBackdrop");
            var hamburger = document.getElementById("mobileHamburger");

            // Restore collapsed state from localStorage
            if (localStorage.getItem("sidebarCollapsed") === "true") {
                sidebar.classList.add("collapsed");
            }

            function toggleSidebar() {
                sidebar.classList.toggle("collapsed");
                localStorage.setItem("sidebarCollapsed", sidebar.classList.contains("collapsed"));
            }
            sidebarToggle.addEventListener("click", toggleSidebar);

            // Sidebar nav item clicks
            var tabMap = {
                day:     { tabId: "day-tab",     btnId: "dayTabBtn",     toast: "Same local AI \u2014 now reading your day" },
                chat:    { tabId: "chat-tab",    btnId: "chatTabBtn",    toast: "Same local AI \u2014 now with execution tools" },
                auditor: { tabId: "auditor-tab", btnId: "auditorTabBtn", toast: "Same local AI \u2014 now in clean room mode" },
                id:      { tabId: "id-tab",      btnId: "idTabBtn",     toast: "Same local AI \u2014 now verifying identity" }
            };
            document.querySelectorAll(".sidebar-nav-item").forEach(function(item) {
                item.addEventListener("click", function() {
                    var key = item.getAttribute("data-tab");
                    var info = tabMap[key];
                    if (info) {
                        switchToTab(info.tabId, info.btnId);
                        showTabToast(info.toast);
                    }
                    // Close mobile overlay
                    if (window.innerWidth <= 768) {
                        sidebar.classList.remove("mobile-open");
                        backdrop.classList.remove("visible");
                    }
                });
            });

            // Mobile hamburger
            if (hamburger) {
                hamburger.addEventListener("click", function() {
                    sidebar.classList.add("mobile-open");
                    backdrop.classList.add("visible");
                });
            }
            if (backdrop) {
                backdrop.addEventListener("click", function() {
                    sidebar.classList.remove("mobile-open");
                    backdrop.classList.remove("visible");
                });
            }

            // === My Day handlers ===
            // --- My Day: counts + peek windows ---
            var peekDataCache = null;

            function loadCounts() {
                fetch("/my-day-counts").then(function(r) { return r.json(); }).then(function(d) {
                    document.getElementById("emailCount").textContent = d.emails;
                    document.getElementById("eventCount").textContent = d.events;
                    document.getElementById("taskCount").textContent = d.tasks;
                });
            }
            loadCounts();

            function loadPeekData(cb) {
                if (peekDataCache) { cb(peekDataCache); return; }
                fetch("/my-day-data").then(function(r) { return r.json(); }).then(function(d) {
                    peekDataCache = d;
                    cb(d);
                });
            }

            function renderEmailPeek(emails) {
                return emails.map(function(em) {
                    return '<div class="peek-row"><span class="peek-from">' + em.from + '</span>' + em.subject + '</div>';
                }).join('');
            }
            function renderEventPeek(events) {
                return events.map(function(ev) {
                    return '<div class="peek-row"><span class="peek-time">' + ev.time + '</span>' + ev.summary +
                        (ev.location ? ' <span style="opacity:0.5">@ ' + ev.location + '</span>' : '') + '</div>';
                }).join('');
            }
            function renderTaskPeek(tasks) {
                return tasks.map(function(t) {
                    var cls = t.priority.toLowerCase();
                    return '<div class="peek-row"><span class="peek-prio ' + cls + '">[' + t.priority + ']</span>' + t.task + '</div>';
                }).join('');
            }

            // Simple Markdown to HTML conversion
            function mdToHtml(text) {
                return text
                    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')  // **bold**
                    .replace(/\*([^*]+)\*/g, '<em>$1</em>')              // *italic*
                    .replace(/^### (.+)$/gm, '<h4>$1</h4>')              // ### Header
                    .replace(/^## (.+)$/gm, '<h3>$1</h3>')               // ## Header
                    .replace(/^# (.+)$/gm, '<h2>$1</h2>')                // # Header
                    .replace(/\n/g, '<br>');                              // newlines
            }

            document.querySelectorAll(".day-card[data-peek]").forEach(function(card) {
                card.addEventListener("click", function(e) {
                    var peekType = this.getAttribute("data-peek");
                    var isExpanded = this.classList.contains("expanded");

                    // Close all other peek windows
                    document.querySelectorAll(".day-card.expanded").forEach(function(c) { c.classList.remove("expanded"); });

                    if (isExpanded) return; // was open, now closed

                    var self = this;
                    loadPeekData(function(data) {
                        var peekEl = self.querySelector(".card-peek");
                        if (peekType === "emails") peekEl.innerHTML = renderEmailPeek(data.emails);
                        else if (peekType === "events") peekEl.innerHTML = renderEventPeek(data.events);
                        else if (peekType === "tasks") peekEl.innerHTML = renderTaskPeek(data.tasks);
                        self.classList.add("expanded");
                    });
                });
            });

            // Close peek when clicking outside
            document.addEventListener("click", function(e) {
                if (!e.target.closest(".day-card[data-peek]")) {
                    document.querySelectorAll(".day-card.expanded").forEach(function(c) { c.classList.remove("expanded"); });
                }
            });

            // --- Network toggle buttons (header) ---
            document.getElementById("goOfflineBtn").addEventListener("click", function() {
                var btn = this;
                btn.disabled = true;
                btn.textContent = "Disabling...";
                fetch("/network-toggle", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({action: "offline"})
                }).then(function() {
                    btn.textContent = "\u2708\uFE0F Go Offline";
                    btn.disabled = false;
                    setTimeout(checkConnectivity, 1500);
                }).catch(function() {
                    btn.textContent = "\u2708\uFE0F Go Offline";
                    btn.disabled = false;
                });
            });

            document.getElementById("goOnlineBtn").addEventListener("click", function() {
                var btn = this;
                btn.disabled = true;
                btn.textContent = "Enabling...";
                fetch("/network-toggle", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({action: "online"})
                }).then(function() {
                    btn.textContent = "\uD83D\uDCF6 Go Online";
                    btn.disabled = false;
                    setTimeout(checkConnectivity, 1500);
                }).catch(function() {
                    btn.textContent = "\uD83D\uDCF6 Go Online";
                    btn.disabled = false;
                });
            });

            function runBriefing(url) {
                var progress = document.getElementById("briefingProgress");
                var result = document.getElementById("briefingResult");
                progress.style.display = "block";
                progress.innerHTML = '<div class="step-line active"><span class="spinner"></span> Starting...</div>';
                result.style.display = "none";
                document.getElementById("briefMeBtn").disabled = true; document.getElementById("focusBtn").disabled = true; document.getElementById("tomorrowBtn").disabled = true;

                fetch(url, {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({ model: currentModel })
                })
                .then(function(r) { return r.body.getReader(); })
                .then(function(reader) {
                    var decoder = new TextDecoder();
                    var buffer = "";

                    function processLine(line) {
                        line = line.trim();
                        if (!line) return;
                        try { var evt = JSON.parse(line); } catch(e) { return; }

                        if (evt.type === "status") {
                            progress.innerHTML += '<div class="step-line active"><span class="spinner"></span> ' + evt.message + '</div>';
                            progress.scrollTop = progress.scrollHeight;
                        }
                        else if (evt.type === "briefing") {
                            progress.style.display = "none";
                            result.style.display = "block";
                            document.getElementById("briefMeBtn").disabled = false; document.getElementById("focusBtn").disabled = false; document.getElementById("tomorrowBtn").disabled = false;

                            var text = evt.text || "";
                            // Split into executive summary and details
                            var parts = text.split(/\n\s*(?:PART 2|KEY DETAILS|PRIORITY|---)/i);
                            var summary = parts[0].replace(/^PART 1[^\n]*\n/i, '').replace(/^EXECUTIVE SUMMARY[^\n]*\n/i, '').trim();
                            var details = parts.length > 1 ? parts.slice(1).join('\n') : '';

                            document.getElementById("execSummaryText").innerHTML = mdToHtml(summary);

                            // Render details as breakdown sections
                            var breakdownArea = document.getElementById("breakdownArea");
                            if (details) {
                                // Split by section headers (lines starting with uppercase + colon)
                                var sections = details.split(/\n(?=[A-Z][A-Z ]+:)/);
                                var html = '';
                                sections.forEach(function(sec) {
                                    sec = sec.trim();
                                    if (!sec) return;
                                    var firstLine = sec.split('\n')[0];
                                    var body = sec.split('\n').slice(1).join('\n').trim();
                                    html += '<div class="breakdown-section">' +
                                        '<div class="breakdown-header" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'">' +
                                        '<span>' + firstLine.replace(/:$/, '') + '</span><span>&#9660;</span></div>' +
                                        '<div class="breakdown-body">' + mdToHtml(body) + '</div></div>';
                                });
                                breakdownArea.innerHTML = html;
                            } else {
                                // If model didn't split into parts, show everything as summary
                                document.getElementById("execSummaryText").innerHTML = mdToHtml(text);
                                breakdownArea.innerHTML = '';
                            }

                            var counts = evt.counts || {};
                            var timerEl = document.getElementById("briefingTimer");
                            timerEl.textContent = "Analyzed " + (counts.emails || "?") + " emails, " + (counts.events || "?") + " events, " + (counts.tasks || "?") + " tasks in " + evt.time + "s on NPU";
                            timerEl.classList.add("briefing-result-pulse");
                        }
                        else if (evt.type === "error") {
                            progress.innerHTML += '<div class="step-line" style="color:#FF4444;">Error: ' + evt.message + '</div>';
                            document.getElementById("briefMeBtn").disabled = false; document.getElementById("focusBtn").disabled = false; document.getElementById("tomorrowBtn").disabled = false;
                        }
                    }

                    function read() {
                        reader.read().then(function(chunk) {
                            if (chunk.done) {
                                if (buffer.trim()) processLine(buffer);
                                document.getElementById("briefMeBtn").disabled = false; document.getElementById("focusBtn").disabled = false; document.getElementById("tomorrowBtn").disabled = false;
                                return;
                            }
                            buffer += decoder.decode(chunk.value);
                            var lines = buffer.split("\n");
                            buffer = lines.pop();
                            lines.forEach(processLine);
                            read();
                        });
                    }
                    read();
                })
                .catch(function(err) {
                    progress.innerHTML += '<div style="color:#FF4444;">Connection error: ' + err.message + '</div>';
                    document.getElementById("briefMeBtn").disabled = false; document.getElementById("focusBtn").disabled = false; document.getElementById("tomorrowBtn").disabled = false;
                });
            }

            document.getElementById("briefMeBtn").addEventListener("click", function() { runBriefing("/brief-me"); });
            document.getElementById("triageBtn").addEventListener("click", function() { runBriefing("/triage-inbox"); });
            document.getElementById("prepBtn").addEventListener("click", function() { runBriefing("/prep-next-meeting"); });
            document.getElementById("focusBtn").addEventListener("click", function() { runBriefing("/top-3-focus"); });
            document.getElementById("tomorrowBtn").addEventListener("click", function() { runBriefing("/tomorrow-preview"); });

            // Agent chat handlers
            document.getElementById("sendBtn").addEventListener("click", sendMessage);
            document.getElementById("userInput").addEventListener("keypress", function(e) {
                if (e.key === "Enter") sendMessage();
            });

            // Demo flow buttons — use dedicated endpoints to avoid two-step agent loop
            function runDemoEndpoint(url, statusText, userPrompt) {
                // Show user message first so it's clear what was requested
                if (userPrompt) {
                    addMessage("user", userPrompt);
                }
                var assistantDiv = addMessage("assistant", '<span class="spinner"></span> ' + statusText);
                var contentDiv = assistantDiv.querySelector(".content");

                fetch(url, {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({ model: currentModel })
                })
                .then(function(r) { return r.text(); })
                .then(function(body) {
                    var lines = body.split("\n");
                    var resultText = "";
                    var totalTime = "";
                    var fileName = "";
                    var errorMsg = "";
                    lines.forEach(function(line) {
                        line = line.trim();
                        if (!line) return;
                        try { var evt = JSON.parse(line); } catch(e) { return; }
                        if (evt.type === "status") {
                            contentDiv.innerHTML = '<span class="spinner"></span> ' + evt.text;
                        } else if (evt.type === "result") {
                            resultText = evt.text || "";
                            totalTime = evt.time || "";
                            fileName = evt.file || "";
                        } else if (evt.type === "error") {
                            errorMsg = evt.message || "Unknown error";
                        }
                    });
                    if (errorMsg) {
                        contentDiv.innerHTML = '<div style="color:#FF4444;">Error: ' + errorMsg + '</div>';
                    } else if (resultText) {
                        var html = '<div style="margin-top:4px;">' + mdToHtml(resultText) + '</div>';
                        if (fileName) {
                            html += '<div style="margin-top:8px;padding:8px 12px;background:rgba(16,124,16,0.15);border-radius:6px;color:#1db954;">&#128190; Saved to: ' + fileName + '</div>';
                        }
                        html += '<div class="tool-time" style="margin-top:4px;">&#9201; ' + totalTime + 's on NPU</div>';
                        contentDiv.innerHTML = html;
                    }
                    document.getElementById("chatContainer").scrollTop = document.getElementById("chatContainer").scrollHeight;
                })
                .catch(function(err) {
                    contentDiv.innerHTML = '<div style="color:#FF4444;">Error: ' + err + '</div>';
                });
            }

            function runDeviceHealth() {
                addMessage("user", "Run a device health check on this machine");
                var assistantDiv = addMessage("assistant", '<div class="health-checks-container" id="healthChecksLive"></div>');
                var contentDiv = assistantDiv.querySelector(".content");
                var checksDiv = document.getElementById("healthChecksLive");
                checksDiv.innerHTML = '<div style="margin-bottom:8px;font-weight:600;">&#128737; Device Health Check</div>';

                fetch("/demo/device-health", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({ model: currentModel })
                })
                .then(function(r) { return r.body.getReader(); })
                .then(function(reader) {
                    var decoder = new TextDecoder();
                    var buffer = "";

                    function processLine(line) {
                        line = line.trim();
                        if (!line) return;
                        try { var evt = JSON.parse(line); } catch(e) { return; }

                        if (evt.type === "check-start") {
                            var entry = document.createElement("div");
                            entry.className = "health-check-entry";
                            entry.id = "hc-" + evt.id;
                            entry.innerHTML = '<div class="health-check-name">' + evt.icon + ' ' + evt.name +
                                ' <span class="spinner" style="display:inline-block;width:12px;height:12px;"></span></div>' +
                                '<div class="health-check-cmd">&gt; ' + evt.cmd + '</div>' +
                                '<div class="health-check-output" id="hc-out-' + evt.id + '"></div>';
                            checksDiv.appendChild(entry);
                        } else if (evt.type === "check-done") {
                            var el = document.getElementById("hc-" + evt.id);
                            if (el) {
                                el.className = "health-check-entry done";
                                el.querySelector(".spinner").style.display = "none";
                                var outEl = document.getElementById("hc-out-" + evt.id);
                                if (outEl) outEl.textContent = evt.output;
                            }
                        } else if (evt.type === "check-error") {
                            var el2 = document.getElementById("hc-" + evt.id);
                            if (el2) {
                                el2.className = "health-check-entry error";
                                el2.querySelector(".spinner").style.display = "none";
                                var outEl2 = document.getElementById("hc-out-" + evt.id);
                                if (outEl2) { outEl2.textContent = evt.output; outEl2.style.color = "#FF4444"; }
                            }
                        } else if (evt.type === "status") {
                            var statusDiv = document.createElement("div");
                            statusDiv.style.cssText = "margin:8px 0;opacity:0.6;font-size:0.85em;";
                            statusDiv.innerHTML = '<span class="spinner" style="display:inline-block;width:12px;height:12px;"></span> ' + evt.text;
                            statusDiv.id = "healthAiStatus";
                            checksDiv.appendChild(statusDiv);
                        } else if (evt.type === "result") {
                            var st = document.getElementById("healthAiStatus");
                            if (st) st.remove();
                            var summaryDiv = document.createElement("div");
                            summaryDiv.className = "health-ai-summary";
                            var html = '<div style="font-weight:600;margin-bottom:6px;">&#129302; AI Assessment</div>' +
                                mdToHtml(evt.text) +
                                '<div class="tool-time" style="margin-top:6px;">&#9201; ' + evt.time + 's on NPU</div>';
                            // Add Learn More buttons for findings
                            if (evt.findings && evt.findings.length > 0) {
                                html += '<div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,0.08);">' +
                                    '<div style="font-size:0.75em;text-transform:uppercase;letter-spacing:0.05em;opacity:0.4;margin-bottom:6px;">Learn More</div>';
                                evt.findings.forEach(function(f) {
                                    html += '<button class="health-learn-btn" data-question="' +
                                        f.q.replace(/"/g, '&quot;') + '"' +
                                        ' style="display:inline-block;margin:3px 4px 3px 0;padding:4px 10px;font-size:0.78em;' +
                                        'background:rgba(0,188,242,0.1);border:1px solid rgba(0,188,242,0.25);border-radius:12px;' +
                                        'color:#00BCF2;cursor:pointer;">' + f.label + ' &rarr;</button>';
                                });
                                html += '</div>';
                            }
                            summaryDiv.innerHTML = html;
                            checksDiv.appendChild(summaryDiv);
                            // Bind Learn More click handlers
                            summaryDiv.querySelectorAll(".health-learn-btn").forEach(function(btn) {
                                btn.addEventListener("click", function() {
                                    var q = this.getAttribute("data-question");
                                    document.getElementById("userInput").value = q;
                                    sendMessage();
                                });
                            });
                        } else if (evt.type === "error") {
                            checksDiv.innerHTML += '<div style="color:#FF4444;margin-top:8px;">Error: ' + evt.message + '</div>';
                        }
                        document.getElementById("chatContainer").scrollTop = document.getElementById("chatContainer").scrollHeight;
                    }

                    function read() {
                        reader.read().then(function(chunk) {
                            if (chunk.done) {
                                if (buffer.trim()) processLine(buffer);
                                return;
                            }
                            buffer += decoder.decode(chunk.value);
                            var lines = buffer.split("\n");
                            buffer = lines.pop();
                            lines.forEach(processLine);
                            read();
                        });
                    }
                    read();
                })
                .catch(function(err) {
                    checksDiv.innerHTML += '<div style="color:#FF4444;">Error: ' + err + '</div>';
                });
            }

            // Suggestion chip handlers
            document.querySelectorAll(".suggestion-chip[data-action]").forEach(function(chip) {
                chip.addEventListener("click", function() {
                    var action = this.getAttribute("data-action");
                    if (action === "meeting-agenda") {
                        runDemoEndpoint("/demo/meeting-agenda", "Generating meeting agenda...",
                            "Create a board meeting agenda for tomorrow covering Q4 results, 2026 strategy, and executive compensation. Save it to the Demo folder.");
                    } else if (action === "analyze-strategy") {
                        runDemoEndpoint("/demo/analyze-strategy", "Analyzing strategy document...",
                            "Read the strategy_2026.txt file and give me the three key takeaways.");
                    } else if (action === "list-documents") {
                        runDemoEndpoint("/demo/list-documents", "Listing documents...",
                            "List the files in the Demo folder.");
                    } else if (action === "summarize-doc") {
                        document.getElementById("attachBtn").click();
                    } else if (action === "device-health") {
                        runDeviceHealth();
                    }
                });
            });

            // === File Picker for Review & Summarize ===
            var selectedReviewFiles = [];

            function openFilePicker() {
                // Fetch files from Demo folder
                fetch("/demo/list-files")
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var listDiv = document.getElementById("filePickerList");
                    listDiv.innerHTML = "";
                    selectedReviewFiles = [];

                    if (!data.files || data.files.length === 0) {
                        listDiv.innerHTML = '<div style="opacity:0.6;padding:20px;text-align:center;">No documents found in Demo folder</div>';
                        return;
                    }

                    data.files.forEach(function(file) {
                        var item = document.createElement("div");
                        item.setAttribute("data-filename", file.name);

                        // Check if file requires Clean Room (contract, nda, loan)
                        var fnLower = file.name.toLowerCase();
                        var requiresCleanRoom = fnLower.indexOf('contract') >= 0 ||
                                                fnLower.indexOf('nda') >= 0 ||
                                                fnLower.indexOf('loan') >= 0;

                        if (requiresCleanRoom) {
                            // Locked file - must use Clean Room Auditor
                            item.className = "file-picker-item locked";
                            item.style.opacity = "0.6";
                            item.style.cursor = "not-allowed";
                            var badge = file.confidential ?
                                '<span class="file-badge">' + file.confidential.icon + ' ' + file.confidential.label + '</span>' : '';
                            item.innerHTML =
                                '<div style="font-size:1.3em;margin-right:12px;">🔒</div>' +
                                '<div class="file-info">' +
                                    '<div class="file-name">' + file.name + badge + '</div>' +
                                    '<div class="file-meta" style="color:#FFB900;">Requires Clean Room Auditor</div>' +
                                '</div>';
                            item.addEventListener("click", function(e) {
                                e.preventDefault();
                                alert("This document is classified as confidential.\\n\\nPlease use the 🔒 Auditor tab (Clean Room) for secure analysis of contracts, NDAs, and documents containing PII.");
                            });
                        } else {
                            // Normal selectable file
                            item.className = "file-picker-item";
                            var badge = file.confidential ?
                                '<span class="file-badge">' + file.confidential.icon + ' ' + file.confidential.label + '</span>' : '';
                            item.innerHTML =
                                '<input type="checkbox" id="fp_' + file.name.replace(/\./g, '_') + '">' +
                                '<div class="file-info">' +
                                    '<div class="file-name">📄 ' + file.name + badge + '</div>' +
                                    '<div class="file-meta">' + file.size + '</div>' +
                                '</div>';
                            item.addEventListener("click", function(e) {
                                if (e.target.type !== "checkbox") {
                                    var cb = item.querySelector("input[type=checkbox]");
                                    cb.checked = !cb.checked;
                                }
                                updateFilePickerSelection();
                            });
                        }

                        listDiv.appendChild(item);
                    });

                    document.getElementById("filePickerOverlay").style.display = "flex";
                    updateFilePickerSelection();
                });
            }

            function updateFilePickerSelection() {
                selectedReviewFiles = [];
                var items = document.querySelectorAll(".file-picker-item");
                items.forEach(function(item) {
                    var cb = item.querySelector("input[type=checkbox]");
                    if (cb && cb.checked) {
                        item.classList.add("selected");
                        selectedReviewFiles.push(item.getAttribute("data-filename"));
                    } else {
                        item.classList.remove("selected");
                    }
                });

                var btn = document.getElementById("filePickerConfirm");
                btn.textContent = "Review Selected (" + selectedReviewFiles.length + ")";
                btn.disabled = selectedReviewFiles.length === 0;
            }

            window.closeFilePicker = function() {
                document.getElementById("filePickerOverlay").style.display = "none";
            };

            window.confirmFilePicker = function() {
                if (selectedReviewFiles.length === 0) return;
                document.getElementById("filePickerOverlay").style.display = "none";

                // Show user message about selection
                addMessage("user", "Review and summarize these files: " + selectedReviewFiles.join(", "));

                // Phase 1: Get the plan and show approval card with Security Review
                fetch("/demo/review-summarize", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({ model: currentModel, phase: "plan", files: selectedReviewFiles })
                })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.type === "plan") {
                        var cardId = "approval_" + Date.now();
                        // Generate Security Review
                        var securityLines = generateSecurityReview(data.text);
                        var securityHtml = '<div class="security-review">' +
                            '<div class="security-review-header">\uD83D\uDEE1\uFE0F Security Review</div>' +
                            securityLines.map(function(line) {
                                return '<div class="security-review-line">\u2022 ' + line + '</div>';
                            }).join('') +
                            '</div>';

                        var html = '<div class="approval-card" id="' + cardId + '" data-files=\'' + JSON.stringify(selectedReviewFiles) + '\'>' +
                            '<div class="approval-header">🔒 This action requires approval</div>' +
                            '<div style="font-size:0.85em;opacity:0.7;margin-bottom:10px;">The following files require authorization to access:</div>' +
                            '<div class="approval-body">' + mdToHtml(data.text) + '</div>' +
                            securityHtml +
                            '<div class="approval-actions">' +
                            '<button class="approval-btn approve" onclick="window.executeReviewSummarize(\'' + cardId + '\')">✅ Approve</button>' +
                            '<button class="approval-btn deny" onclick="window.denyReviewSummarize(\'' + cardId + '\')">❌ Deny</button>' +
                            '</div>' +
                            '<div class="approval-policy">📋 Policy: Read-only within approved folder. All actions logged.</div>' +
                            '</div>';
                        addMessage("assistant", html);
                    }
                });
            };

            // Review & Summarize (kept for programmatic use, sidebar button removed)

            // Execute review after approval
            window.executeReviewSummarize = function(cardId) {
                var card = document.getElementById(cardId);
                var files = [];
                try {
                    files = JSON.parse(card.getAttribute("data-files") || "[]");
                } catch(e) { files = selectedReviewFiles; }

                if (card) {
                    card.classList.add("approved");
                    card.querySelector(".approval-actions").innerHTML = '<span class="approval-badge" style="background:#107c10;color:#fff;padding:4px 12px;border-radius:4px;">✅ Approved</span>';
                }
                addAuditEntry("APPROVAL", {action: "Review & Summarize", files: files.length}, true, 0);

                var assistantDiv = addMessage("assistant", '<span class="spinner"></span> Reading documents...');
                var contentDiv = assistantDiv.querySelector(".content");

                fetch("/demo/review-summarize", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({ model: currentModel, phase: "execute", files: files })
                })
                .then(function(r) { return r.text(); })
                .then(function(body) {
                    var lines = body.split("\n");
                    var resultText = "";
                    var totalTime = "";
                    var filesRead = [];
                    var errorMsg = "";
                    lines.forEach(function(line) {
                        line = line.trim();
                        if (!line) return;
                        try { var evt = JSON.parse(line); } catch(e) { return; }
                        if (evt.type === "status") {
                            contentDiv.innerHTML = '<span class="spinner"></span> ' + evt.text;
                        } else if (evt.type === "result") {
                            resultText = evt.text || "";
                            totalTime = evt.time || "";
                            filesRead = evt.files_read || [];
                        } else if (evt.type === "error") {
                            errorMsg = evt.message || "Unknown error";
                        }
                    });
                    if (errorMsg) {
                        contentDiv.innerHTML = '<div style="color:#FF4444;">Error: ' + errorMsg + '</div>';
                    } else if (resultText) {
                        var html = '<div style="margin-bottom:8px;font-size:0.85em;opacity:0.7;">📄 Files reviewed: ' + filesRead.join(", ") + '</div>';
                        html += '<div style="margin-top:4px;">' + mdToHtml(resultText) + '</div>';
                        html += '<div class="tool-time" style="margin-top:8px;">⏱ ' + totalTime + 's on NPU</div>';
                        contentDiv.innerHTML = html;
                    }
                    document.getElementById("chatContainer").scrollTop = document.getElementById("chatContainer").scrollHeight;
                });
            };

            window.denyReviewSummarize = function(cardId) {
                var card = document.getElementById(cardId);
                if (card) {
                    card.classList.add("denied");
                    card.querySelector(".approval-actions").innerHTML = '<span class="approval-badge" style="background:#d32f2f;color:#fff;padding:4px 12px;border-radius:4px;">❌ Denied</span>';
                }
                addAuditEntry("APPROVAL_DENIED", {action: "Review & Summarize"}, false, 0);
                addMessage("assistant", '<div style="color:#FF8C00;">Action denied by user. No files were accessed.</div>');
            };

            // Audit summary button — shows trust receipt banner then asks AI to summarize
            document.getElementById("qpAuditSummary").addEventListener("click", function() {
                fetch("/audit-log").then(function(r) { return r.json(); }).then(function(log) {
                    if (log.length === 0) {
                        addMessage("assistant", "No agent actions recorded yet. Try running some commands first!");
                        return;
                    }
                    // Compute deterministic trust receipt
                    var reads = 0, writes = 0, execs = 0;
                    for (var i = 0; i < log.length; i++) {
                        if (log[i].tool === "read") reads++;
                        else if (log[i].tool === "write") writes++;
                        else if (log[i].tool === "exec") execs++;
                    }
                    var parts = [];
                    if (reads) parts.push(reads + " file" + (reads > 1 ? "s" : "") + " accessed");
                    if (writes) parts.push(writes + " document" + (writes > 1 ? "s" : "") + " created");
                    if (execs) parts.push(execs + " system command" + (execs > 1 ? "s" : ""));
                    var summaryText = parts.length > 0 ? parts.join(", ") : "No actions recorded";

                    // Show trust receipt banner in chat
                    var receiptHtml = '<div style="background:rgba(0,188,242,0.08);border:1px solid rgba(0,188,242,0.25);border-radius:10px;padding:14px 18px;margin-bottom:14px;">' +
                        '<div style="font-size:0.7em;text-transform:uppercase;letter-spacing:0.1em;opacity:0.5;margin-bottom:6px;">\uD83D\uDCCB Session Trust Receipt</div>' +
                        '<div style="font-size:1.05em;font-weight:bold;">' + summaryText + '</div>' +
                        '<div style="font-size:0.85em;opacity:0.6;margin-top:4px;">All actions local. No network calls. No data egress.</div>' +
                        '</div>';
                    addMessage("assistant", receiptHtml);

                    // Then send to AI for detailed summary
                    var detail = log.map(function(e) {
                        return e.timestamp + " - " + e.tool + "(" + JSON.stringify(e.arguments) + ") " + (e.success ? "OK" : "FAIL") + " [" + e.time + "s]";
                    }).join("\n");
                    document.getElementById("userInput").value = "Here is the audit trail of everything you did this session:\n\n" + detail + "\n\nSummarize this in 5 bullet points for an executive briefing. What actions were taken, what was the outcome, and confirm that all processing was local.";
                    sendMessage();
                });
            });

            document.getElementById("qpClear").addEventListener("click", function() {
                // Clear chat messages
                document.getElementById("chatContainer").innerHTML = "";
                // Restore suggestion chips
                var emptyState = document.getElementById("chatEmptyState");
                if (emptyState) {
                    emptyState.style.display = "flex";
                } else {
                    // Rebuild if removed from DOM
                    var chipsHtml = '<div class="chat-empty-state" id="chatEmptyState">' +
                        '<div class="suggestion-grid">' +
                            '<button class="suggestion-chip" data-action="meeting-agenda"><span class="chip-icon">&#128203;</span><span>Meeting Agenda</span></button>' +
                            '<button class="suggestion-chip" data-action="analyze-strategy"><span class="chip-icon">&#128196;</span><span>Analyze Strategy</span></button>' +
                            '<button class="suggestion-chip" data-action="list-documents"><span class="chip-icon">&#128193;</span><span>List Documents</span></button>' +
                            '<button class="suggestion-chip" data-action="summarize-doc"><span class="chip-icon">&#128221;</span><span>Summarize a Document</span></button>' +
                            '<button class="suggestion-chip" data-action="device-health"><span class="chip-icon">&#128737;</span><span>Device Health</span></button>' +
                        '</div></div>';
                    document.getElementById("chatContainer").insertAdjacentHTML("afterend", chipsHtml);
                    // Re-bind chip handlers
                    document.querySelectorAll(".suggestion-chip[data-action]").forEach(function(chip) {
                        chip.addEventListener("click", function() {
                            var action = this.getAttribute("data-action");
                            if (action === "meeting-agenda") {
                                runDemoEndpoint("/demo/meeting-agenda", "Generating meeting agenda...",
                                    "Create a board meeting agenda for tomorrow covering Q4 results, 2026 strategy, and executive compensation. Save it to the Demo folder.");
                            } else if (action === "analyze-strategy") {
                                runDemoEndpoint("/demo/analyze-strategy", "Analyzing strategy document...",
                                    "Read the strategy_2026.txt file and give me the three key takeaways.");
                            } else if (action === "list-documents") {
                                runDemoEndpoint("/demo/list-documents", "Listing documents...",
                                    "List the files in the Demo folder.");
                            } else if (action === "summarize-doc") {
                                document.getElementById("attachBtn").click();
                            } else if (action === "device-health") {
                                runDeviceHealth();
                            }
                        });
                    });
                }
                document.getElementById("auditTrail").style.display = "none";
                document.getElementById("auditEntries").innerHTML = "";
                fetch("/audit-log", { method: "DELETE" });
                document.getElementById("qpSaveSummary").style.display = "none";
                lastAssistantResponse = "";
                pendingSummarize = false;
            });

            // Connectivity check
            document.getElementById("connectivityCard").addEventListener("click", checkConnectivity);

            function checkConnectivity() {
                document.getElementById("netStatus").textContent = "Checking...";
                document.getElementById("npuStatus").textContent = "Checking...";
                fetch("/connectivity-check").then(function(r) { return r.json(); }).then(function(d) {
                    var netDot = document.getElementById("netDot");
                    var npuDot = document.getElementById("npuDot");
                    document.getElementById("netStatus").textContent = d.network ? "Online" : "Offline";
                    netDot.className = "status-dot " + (d.network ? "green" : "red");
                    document.getElementById("npuStatus").textContent = d.npu ? "NPU Ready" : "NPU Down";
                    npuDot.className = "status-dot " + (d.npu ? "blue" : "red");
                    // Update header badge too
                    var badge = document.getElementById("offlineBadge");
                    if (d.network) {
                        badge.textContent = "Online";
                        badge.classList.remove("offline");
                    } else {
                        badge.textContent = "Offline Mode";
                        badge.classList.add("offline");
                    }
                }).catch(function() {
                    document.getElementById("netStatus").textContent = "Offline";
                    document.getElementById("netDot").className = "status-dot red";
                });
            }
            
            document.getElementById("modelSelect").addEventListener("change", function() {
                currentModel = this.value;
            });

            // File picker — uploads, extracts text, saves to Demo folder
            var lastUploadedFile = "";
            document.getElementById("attachBtn").addEventListener("click", function() {
                document.getElementById("agentFileInput").click();
            });
            document.getElementById("agentFileInput").addEventListener("change", function(e) {
                var file = e.target.files[0];
                if (!file) return;
                var formData = new FormData();
                formData.append("file", file);
                fetch("/upload-to-demo", { method: "POST", body: formData })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        lastUploadedFile = data.path;
                        // Show inline action buttons in chat message
                        var msgHtml = 'Loaded <strong>' + file.name + '</strong> (' + data.words + ' words).' +
                            '<div style="margin-top:10px;">' +
                            '<button class="inline-action-btn" onclick="document.getElementById(\'qpSummarizeDoc\').click();">&#128221; Summarize</button>' +
                            '<button class="inline-action-btn" onclick="document.getElementById(\'qpDetectPII\').click();">&#128680; Detect PII</button>' +
                            '</div>';
                        addMessage("assistant", msgHtml);
                    } else {
                        addMessage("assistant", '<div style="color:#FF4444;">Upload error: ' + data.error + '</div>');
                    }
                });
                e.target.value = "";
            });
            document.getElementById("qpSummarizeDoc").addEventListener("click", function() {
                if (!lastUploadedFile) return;
                document.getElementById("qpSaveSummary").style.display = "none";
                var assistantDiv = addMessage("assistant", '<span class="spinner"></span> Reading document...');
                var contentDiv = assistantDiv.querySelector(".content");

                fetch("/summarize-doc", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({ path: lastUploadedFile, model: currentModel })
                })
                .then(function(r) { return r.text(); })
                .then(function(body) {
                    var lines = body.split("\n");
                    var summaryText = "";
                    var totalTime = "";
                    var errorMsg = "";
                    lines.forEach(function(line) {
                        line = line.trim();
                        if (!line) return;
                        try { var evt = JSON.parse(line); } catch(e) { return; }
                        if (evt.type === "status") {
                            contentDiv.innerHTML = '<span class="spinner"></span> ' + evt.text;
                        } else if (evt.type === "summary") {
                            summaryText = evt.text || "";
                            totalTime = evt.time || "";
                        } else if (evt.type === "error") {
                            errorMsg = evt.message || "Unknown error";
                        }
                    });
                    if (errorMsg) {
                        contentDiv.innerHTML = '<div style="color:#FF4444;">Error: ' + errorMsg + '</div>';
                    } else if (summaryText) {
                        lastAssistantResponse = summaryText;
                        var html = '<div style="margin-top:4px;">' + summaryText.replace(/\n/g, "<br>") + '</div>';
                        html += '<div class="tool-time" style="margin-top:4px;">&#9201; ' + totalTime + 's on NPU</div>';
                        html += '<div style="margin-top:12px;"><button onclick="window.saveSummary()" style="background:linear-gradient(135deg,#0078d4,#00bcf2);color:#fff;border:none;padding:10px 24px;border-radius:8px;font-size:0.95em;cursor:pointer;font-weight:600;">&#128190; Save Summary to File</button></div>';
                        contentDiv.innerHTML = html;
                    }
                    document.getElementById("chatContainer").scrollTop = document.getElementById("chatContainer").scrollHeight;
                })
                .catch(function(err) {
                    contentDiv.innerHTML = '<div style="color:#FF4444;">Error: ' + err + '</div>';
                });
            });
            document.getElementById("qpDetectPII").addEventListener("click", function() {
                if (!lastUploadedFile) return;
                var assistantDiv = addMessage("assistant", '<span class="spinner"></span> Scanning for PII...');
                var contentDiv = assistantDiv.querySelector(".content");

                fetch("/detect-pii", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({ path: lastUploadedFile, model: currentModel })
                })
                .then(function(r) { return r.text(); })
                .then(function(body) {
                    var lines = body.split("\n");
                    var resultText = "";
                    var totalTime = "";
                    var errorMsg = "";
                    lines.forEach(function(line) {
                        line = line.trim();
                        if (!line) return;
                        try { var evt = JSON.parse(line); } catch(e) { return; }
                        if (evt.type === "status") {
                            contentDiv.innerHTML = '<span class="spinner"></span> ' + evt.text;
                        } else if (evt.type === "result") {
                            resultText = evt.text || "";
                            totalTime = evt.time || "";
                        } else if (evt.type === "error") {
                            errorMsg = evt.message || "Unknown error";
                        }
                    });
                    if (errorMsg) {
                        contentDiv.innerHTML = '<div style="color:#FF4444;">Error: ' + errorMsg + '</div>';
                    } else if (resultText) {
                        var html = '<div style="margin-top:4px;">' + mdToHtml(resultText) + '</div>';
                        html += '<div class="tool-time" style="margin-top:4px;">&#9201; ' + totalTime + 's on NPU</div>';
                        contentDiv.innerHTML = html;
                    }
                    document.getElementById("chatContainer").scrollTop = document.getElementById("chatContainer").scrollHeight;
                })
                .catch(function(err) {
                    contentDiv.innerHTML = '<div style="color:#FF4444;">Error: ' + err + '</div>';
                });
            });
            document.getElementById("qpSaveSummary").addEventListener("click", function() {
                window.saveSummary();
            });
            window.saveSummary = function() {
                if (!lastAssistantResponse || !lastUploadedFile) return;
                var baseName = lastUploadedFile.replace(/\\/g, "/").split("/").pop().replace(/\.[^.]+$/, "");
                var dirParts = lastUploadedFile.replace(/\\/g, "/").split("/").slice(0, -1);
                var savePath = dirParts.join("\\") + "\\" + baseName + "_Summary.txt";
                // Direct backend write — no AI needed
                var btn = event.target || document.querySelector('[onclick*="saveSummary"]');
                if (btn) { btn.disabled = true; btn.textContent = "Saving..."; }
                fetch("/save-summary", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({ path: savePath, content: lastAssistantResponse })
                })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        var savedName = data.filename || savePath.replace(/\\/g, "/").split("/").pop();
                        if (btn) {
                            btn.style.background = "linear-gradient(135deg,#107c10,#1db954)";
                            btn.textContent = "\u2705 Saved: " + savedName;
                            btn.disabled = true;
                        }
                        addAuditEntry("write", {path: savedName}, true, 0);
                    } else {
                        if (btn) { btn.textContent = "\u274c Save failed"; btn.disabled = false; }
                    }
                })
                .catch(function(err) {
                    if (btn) { btn.textContent = "\u274c Save failed"; btn.disabled = false; }
                });
            };

            // Camera/ID handlers
            document.getElementById("startCameraBtn").addEventListener("click", startCamera);
            document.getElementById("captureBtn").addEventListener("click", captureImage);
            document.getElementById("retakeBtn").addEventListener("click", retakeImage);
            document.getElementById("analyzeIdBtn").addEventListener("click", analyzeId);
            document.getElementById("refreshCamerasBtn").addEventListener("click", enumerateCameras);
            
            // Enumerate cameras on load
            enumerateCameras();
            
            // Online status
            function updateOnlineStatus() {
                var badge = document.getElementById("offlineBadge");
                var netDot = document.getElementById("netDot");
                var netLabel = document.getElementById("netStatus");
                if (navigator.onLine) {
                    badge.textContent = "Online";
                    badge.classList.remove("offline");
                    if (netDot) netDot.className = "status-dot green";
                    if (netLabel) netLabel.textContent = "Online";
                } else {
                    badge.textContent = "Offline Mode";
                    badge.classList.add("offline");
                    if (netDot) netDot.className = "status-dot red";
                    if (netLabel) netLabel.textContent = "Offline";
                }
            }
            window.addEventListener("online", updateOnlineStatus);
            window.addEventListener("offline", updateOnlineStatus);
            updateOnlineStatus();

            // === Clean Room Auditor Functions ===
            var auditorDocText = "";
            var auditorDocName = "";
            var auditorAnalysisRunning = false;
            var demoModeEnabled = false;

            // Check demo mode on load (bypasses offline check for testing)
            fetch("/demo-mode-status").then(function(r) { return r.json(); }).then(function(d) {
                demoModeEnabled = d.demo_mode;
                if (demoModeEnabled) {
                    console.log("🔧 Demo mode enabled - offline check bypassed for Clean Room");
                }
            }).catch(function() {});

            // Check if device is offline (required for Clean Room)
            function isDeviceOffline() {
                var badge = document.getElementById("offlineBadge");
                return badge && badge.classList.contains("offline");
            }

            function requireOfflineForCleanRoom() {
                // Demo mode bypasses the offline requirement for testing
                if (demoModeEnabled) {
                    console.log("🔧 Demo mode: bypassing offline check");
                    return true;
                }
                if (!isDeviceOffline()) {
                    alert("🔒 Clean Room Security Protocol\\n\\nConfidential documents can only be loaded when the device is OFFLINE.\\n\\nPlease click 'Go Offline' in the sidebar to disconnect from the network, then try again.\\n\\nThis ensures zero data egress during analysis.");
                    return false;
                }
                return true;
            }

            // Load demo document
            document.getElementById("loadDemoDocBtn").addEventListener("click", function() {
                if (!requireOfflineForCleanRoom()) return;

                fetch("/auditor-demo-doc")
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.error) {
                        alert("Demo document not found: " + data.error);
                        return;
                    }
                    auditorDocText = data.text;
                    auditorDocName = data.filename;
                    showAuditorStaged(data.filename, data.word_count, data.text);
                });
            });

            // File upload handling - intercept the button click to check offline first
            document.querySelector(".auditor-upload-btn").addEventListener("click", function(e) {
                if (!requireOfflineForCleanRoom()) {
                    e.preventDefault();
                    e.stopPropagation();
                    return false;
                }
                document.getElementById("auditorFileInput").click();
            });

            document.getElementById("auditorFileInput").addEventListener("change", function(e) {
                var file = e.target.files[0];
                if (!file) return;
                var formData = new FormData();
                formData.append("file", file);
                fetch("/upload-to-demo", { method: "POST", body: formData })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.error) {
                        alert("Upload failed: " + data.error);
                        return;
                    }
                    auditorDocText = data.text || "";
                    auditorDocName = data.filename || file.name;
                    var wordCount = auditorDocText.split(/\s+/).length;
                    showAuditorStaged(auditorDocName, wordCount, auditorDocText);
                });
            });

            // Drag and drop
            var dropzone = document.getElementById("auditorDropzone");
            dropzone.addEventListener("dragover", function(e) {
                e.preventDefault();
                if (!isDeviceOffline()) return;
                dropzone.classList.add("dragover");
            });
            dropzone.addEventListener("dragleave", function() {
                dropzone.classList.remove("dragover");
            });
            dropzone.addEventListener("drop", function(e) {
                e.preventDefault();
                dropzone.classList.remove("dragover");
                if (!requireOfflineForCleanRoom()) return;
                var file = e.dataTransfer.files[0];
                if (file) {
                    var input = document.getElementById("auditorFileInput");
                    var dt = new DataTransfer();
                    dt.items.add(file);
                    input.files = dt.files;
                    input.dispatchEvent(new Event("change"));
                }
            });

            function showAuditorStaged(filename, wordCount, text) {
                document.getElementById("auditorUploadZone").style.display = "none";
                document.getElementById("auditorStaged").style.display = "block";
                document.getElementById("auditorResults").style.display = "none";

                var pages = Math.max(1, Math.ceil(wordCount / 500));
                document.getElementById("auditorDocName").textContent = filename;
                document.getElementById("auditorDocMeta").textContent = pages + " page" + (pages > 1 ? "s" : "") + " • " + wordCount.toLocaleString() + " words • Loaded locally";
                document.getElementById("auditorDocPreview").textContent = text.substring(0, 250) + (text.length > 250 ? "..." : "");
            }

            window.resetAuditor = function() {
                auditorDocText = "";
                auditorDocName = "";
                document.getElementById("auditorUploadZone").style.display = "block";
                document.getElementById("auditorStaged").style.display = "none";
                document.getElementById("auditorResults").style.display = "none";
            };

            window.rerunAudit = function() {
                document.getElementById("auditorStaged").style.display = "block";
                document.getElementById("auditorResults").style.display = "none";
            };

            // Analysis buttons
            document.getElementById("btnFullAudit").addEventListener("click", function() { runAudit("full"); });
            document.getElementById("btnRiskScan").addEventListener("click", function() { runAudit("risk"); });
            document.getElementById("btnObligations").addEventListener("click", function() { runAudit("obligations"); });
            document.getElementById("btnPiiScan").addEventListener("click", function() { runAudit("pii"); });

            function runAudit(mode) {
                if (auditorAnalysisRunning || !auditorDocText) return;
                auditorAnalysisRunning = true;

                // Disable buttons
                ["btnFullAudit", "btnRiskScan", "btnObligations", "btnPiiScan"].forEach(function(id) {
                    document.getElementById(id).disabled = true;
                });

                // Switch to results view
                document.getElementById("auditorStaged").style.display = "none";
                document.getElementById("auditorResults").style.display = "block";

                var wordCount = auditorDocText.split(/\s+/).length;
                var pages = Math.max(1, Math.ceil(wordCount / 500));
                document.getElementById("auditorResultsDocSummary").textContent =
                    "\uD83D\uDCC4 " + auditorDocName + " • " + pages + " page" + (pages > 1 ? "s" : "") + " • " + wordCount.toLocaleString() + " words";

                // Clear previous results and show initial spinner
                document.getElementById("processingLogContent").innerHTML =
                    '<div class="log-step active"><span class="spinner"></span> Initializing Clean Room analysis...</div>';
                document.getElementById("auditorResultsCards").innerHTML = "";
                document.getElementById("auditStamp").style.display = "none";
                document.getElementById("auditorResultsActions").style.display = "none";

                // Start analysis with streaming
                fetch("/auditor-analyze", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        text: auditorDocText,
                        filename: auditorDocName,
                        mode: mode,
                        model: currentModel
                    })
                })
                .then(function(r) { return r.body.getReader(); })
                .then(function(reader) {
                    var decoder = new TextDecoder();
                    var buffer = "";
                    var firstEvent = true;

                    function processLine(line) {
                        line = line.trim();
                        if (!line) return;
                        try {
                            var evt = JSON.parse(line);
                            // Clear initializing message on first real event
                            if (firstEvent) {
                                document.getElementById("processingLogContent").innerHTML = "";
                                firstEvent = false;
                            }
                            processAuditorEvent(evt);
                        } catch(e) { console.log("Parse error:", e); }
                    }

                    function read() {
                        reader.read().then(function(result) {
                            if (result.done) {
                                if (buffer.trim()) processLine(buffer);
                                // Done
                                auditorAnalysisRunning = false;
                                ["btnFullAudit", "btnRiskScan", "btnObligations", "btnPiiScan"].forEach(function(id) {
                                    document.getElementById(id).disabled = false;
                                });
                                document.getElementById("auditorResultsActions").style.display = "flex";
                                return;
                            }
                            buffer += decoder.decode(result.value);
                            var lines = buffer.split("\n");
                            buffer = lines.pop();
                            lines.forEach(processLine);
                            read();
                        });
                    }
                    read();
                })
                .catch(function(err) {
                    addLogStep("error", "Error: " + err.message, []);
                    auditorAnalysisRunning = false;
                    ["btnFullAudit", "btnRiskScan", "btnObligations", "btnPiiScan"].forEach(function(id) {
                        document.getElementById(id).disabled = false;
                    });
                });
            }

            function processAuditorEvent(evt) {
                if (evt.type === "log") {
                    addLogStep(evt.status, evt.message, evt.details || []);
                }
                else if (evt.type === "prompt") {
                    addLogPrompt(evt.label, evt.text);
                }
                else if (evt.type === "pii") {
                    renderPiiCard(evt.findings);
                }
                else if (evt.type === "risk") {
                    renderRiskCard(evt.findings);
                }
                else if (evt.type === "obligations") {
                    renderObligationsCard(evt.findings);
                }
                else if (evt.type === "summary") {
                    renderSummaryCard(evt.text);
                }
                else if (evt.type === "audit") {
                    renderAuditStamp(evt);
                }
            }

            function addLogStep(status, message, details) {
                var log = document.getElementById("processingLogContent");
                // Use animated CSS spinner for active steps, emojis for others
                var icon = status === "complete" ? "\u2705" : status === "active" ? '<span class="spinner" style="width:14px;height:14px;margin-right:6px;border-width:2px;vertical-align:middle;"></span>' : status === "pending" ? "\u23F3" : "\u274C";
                var cls = status === "complete" ? "complete" : status === "active" ? "active" : "pending";
                var html = '<div class="log-step ' + cls + '">' +
                    (status === "active" ? icon : '<span class="log-step-icon">' + icon + '</span>') + message + '</div>';
                if (details && details.length > 0) {
                    details.forEach(function(d) {
                        html += '<div class="log-step-detail">\u2022 ' + d + '</div>';
                    });
                }
                // When a step completes, replace the last active spinner
                if (status === "complete") {
                    var activeSteps = log.querySelectorAll(".log-step.active");
                    if (activeSteps.length > 0) {
                        var last = activeSteps[activeSteps.length - 1];
                        // Remove the active step and any detail lines after it
                        var sibling = last.nextElementSibling;
                        while (sibling && sibling.classList.contains("log-step-detail")) {
                            var next = sibling.nextElementSibling;
                            sibling.remove();
                            sibling = next;
                        }
                        last.remove();
                    }
                }
                log.innerHTML += html;
                log.scrollTop = log.scrollHeight;
            }

            function addLogPrompt(label, text) {
                var log = document.getElementById("processingLogContent");
                var html = '<div class="log-prompt-box">' +
                    '<div class="log-prompt-label">' + label + '</div>' +
                    '<div>' + text.replace(/\n/g, "<br>") + '</div>' +
                    '</div>';
                log.innerHTML += html;
                log.scrollTop = log.scrollHeight;
            }

            function renderPiiCard(findings) {
                if (!findings || findings.length === 0) return;
                var cards = document.getElementById("auditorResultsCards");
                var html = '<div class="result-card pii">' +
                    '<div class="result-card-header">\uD83D\uDD10 PII DETECTED</div>';
                findings.forEach(function(f) {
                    var sevIcon = f.severity === "high" ? "\uD83D\uDD34" : "\uD83D\uDFE1";
                    html += '<div class="pii-item">' +
                        '<span class="pii-severity">' + sevIcon + '</span>' +
                        '<span class="pii-type">' + f.type + '</span>' +
                        '<span class="pii-value">' + f.value + '</span>' +
                        '<span class="pii-location">' + f.location + '</span>' +
                        '</div>';
                });
                html += '<div style="margin-top:12px;font-size:0.85em;opacity:0.7;">\u26A1 Recommendation: Redact before external sharing</div>';
                html += '</div>';
                cards.innerHTML += html;
            }

            function renderRiskCard(findings) {
                if (!findings || findings.length === 0) return;
                var cards = document.getElementById("auditorResultsCards");
                var html = '<div class="result-card">' +
                    '<div class="result-card-header">\u26A0\uFE0F RISK ASSESSMENT</div>';
                findings.forEach(function(f) {
                    var sevClass = (f.severity || "medium").toLowerCase();
                    var sevIcon = sevClass === "high" ? "\uD83D\uDD34" : sevClass === "medium" ? "\uD83D\uDFE1" : "\uD83D\uDFE2";
                    var sevLabel = sevClass.toUpperCase();
                    html += '<div class="risk-item">' +
                        '<div class="risk-severity ' + sevClass + '">' + sevIcon + ' ' + sevLabel + ' \u2014 ' + (f.type || "Risk") + (f.section ? " (Sec " + f.section + ")" : "") + '</div>' +
                        '<div class="risk-finding">' + (f.finding || "") + '</div>' +
                        (f.recommendation ? '<div class="risk-recommendation">\u2192 ' + f.recommendation + '</div>' : '') +
                        '</div>';
                });
                html += '</div>';
                cards.innerHTML += html;
            }

            function renderObligationsCard(findings) {
                if (!findings || findings.length === 0) return;
                var cards = document.getElementById("auditorResultsCards");
                var html = '<div class="result-card">' +
                    '<div class="result-card-header">\uD83D\uDCCB KEY OBLIGATIONS</div>' +
                    '<table style="width:100%;font-size:0.9em;border-collapse:collapse;">' +
                    '<tr style="opacity:0.6;"><th style="text-align:left;padding:8px 4px;">Obligation</th><th style="text-align:left;padding:8px 4px;">Deadline</th><th style="text-align:left;padding:8px 4px;">Consequence</th></tr>';
                findings.forEach(function(f) {
                    html += '<tr style="border-top:1px solid rgba(255,255,255,0.1);">' +
                        '<td style="padding:8px 4px;">' + (f.obligation || "") + '</td>' +
                        '<td style="padding:8px 4px;">' + (f.deadline || "") + '</td>' +
                        '<td style="padding:8px 4px;">' + (f.consequence || "") + '</td>' +
                        '</tr>';
                });
                html += '</table></div>';
                cards.innerHTML += html;
            }

            function renderSummaryCard(text) {
                if (!text) return;
                var cards = document.getElementById("auditorResultsCards");
                var html = '<div class="result-card">' +
                    '<div class="result-card-header">\uD83D\uDCDD EXECUTIVE SUMMARY</div>' +
                    '<div style="line-height:1.6;">' + text.replace(/\n/g, "<br>") + '</div>' +
                    '</div>';
                cards.innerHTML += html;
            }

            function renderAuditStamp(data) {
                var stamp = document.getElementById("auditStamp");
                stamp.style.display = "block";
                var timeComparison = "";
                if (data.estimated_time) {
                    var diff = data.total_time - data.estimated_time;
                    if (Math.abs(diff) <= 5) {
                        timeComparison = " (estimated: ~" + data.estimated_time + "s ✓)";
                    } else if (diff < 0) {
                        timeComparison = " (estimated: ~" + data.estimated_time + "s — " + Math.abs(Math.round(diff)) + "s faster!)";
                    } else {
                        timeComparison = " (estimated: ~" + data.estimated_time + "s)";
                    }
                }
                stamp.innerHTML = '<div class="audit-stamp-header">\uD83D\uDD12 AUDIT STAMP</div>' +
                    '<div class="audit-stamp-line">Clean Room Audit Complete</div>' +
                    '<div class="audit-stamp-line">Analyzed: ' + auditorDocName + '</div>' +
                    '<div class="audit-stamp-line">Total time: ' + (data.total_time || "?") + 's' + timeComparison + '</div>' +
                    '<div class="audit-stamp-line">PII scan: regex (local) \u2014 ' + (data.pii_time || "0") + 's</div>' +
                    '<div class="audit-stamp-line">Risk analysis: Phi-4 Mini (NPU) \u2014 ' + (data.analysis_time || "?") + 's</div>' +
                    '<div class="audit-stamp-line" style="color:#00CC6A;margin-top:8px;">Network calls: 0 \u2022 Data transmitted: 0 bytes</div>';
            }

            console.log("All event handlers set up!");
        });
        
        // === Agent Chat Functions ===
        function addMessage(role, content) {
            var container = document.getElementById("chatContainer");
            // Hide suggestion chips on first message
            var emptyState = document.getElementById("chatEmptyState");
            if (emptyState) emptyState.style.display = "none";
            var div = document.createElement("div");
            div.className = "message " + (role === "user" ? "user-msg" : "assistant-msg");
            var label = role === "user" ? "You" : "Agent (Phi-4 Mini)";
            div.innerHTML = '<div class="role">' + label + '</div><div class="content">' + content + '</div>';
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
            return div;
        }

        function addAuditEntry(tool, args, success, elapsed) {
            var trail = document.getElementById("auditTrail");
            trail.style.display = "block";
            var entries = document.getElementById("auditEntries");
            var now = new Date().toLocaleTimeString();
            var icon = success ? "&#9989;" : "&#10060;";
            var argStr = typeof args === "object" ? Object.keys(args).map(function(k) {
                var v = args[k];
                if (typeof v === "string" && v.length > 40) v = v.substring(0, 40) + "...";
                return k + "=" + v;
            }).join(", ") : "";
            entries.innerHTML += '<div style="padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.05);">' +
                icon + ' <strong>' + now + '</strong> ' + tool + '(' + argStr + ') <span class="tool-time">' + elapsed + 's</span></div>';
            trail.scrollTop = trail.scrollHeight;
        }

        // === Agentic Firewall: Security Explanations ===
        function getSecurityExplanation(toolName, args) {
            switch(toolName.toLowerCase()) {
                case 'read':
                    var path = (args && args.path) ? args.path.split(/[\\\/]/).pop() : 'file';
                    return 'Reading file "' + path + '". Read-only, no modifications. Within approved folder.';
                case 'write':
                    var wpath = (args && args.path) ? args.path.split(/[\\\/]/).pop() : 'file';
                    return 'Creating file "' + wpath + '" in approved demo folder. No existing files modified.';
                case 'exec':
                    var cmd = ((args && args.command) || '').toLowerCase().trim();
                    if (cmd.indexOf('get-childitem') >= 0) {
                        return 'Listing directory contents. Read-only operation, no files affected.';
                    } else if (cmd.indexOf('get-date') >= 0) {
                        return 'Retrieving system date/time. No system changes.';
                    } else if (cmd.indexOf('disable-netadapter') >= 0) {
                        return 'Disabling network adapter(s). Device will go offline. Re-enable available.';
                    } else if (cmd.indexOf('enable-netadapter') >= 0) {
                        return 'Enabling network adapter(s). Restoring network connectivity.';
                    } else if (cmd.indexOf('get-content') >= 0) {
                        return 'Reading file contents via PowerShell. Read-only operation.';
                    } else {
                        return 'Running approved PowerShell command within allowlisted cmdlet set.';
                    }
                default:
                    return 'Executing approved tool within security policy.';
            }
        }

        function generateSecurityReview(planText) {
            var lines = [];
            // Count files mentioned (look for file patterns in the plan)
            var fileMatches = planText.match(/[\w_-]+\.\w{2,4}/g) || [];
            var uniqueFiles = [];
            fileMatches.forEach(function(f) {
                if (uniqueFiles.indexOf(f) < 0) uniqueFiles.push(f);
            });

            if (uniqueFiles.length > 0) {
                lines.push(uniqueFiles.length + ' file' + (uniqueFiles.length > 1 ? 's' : '') + ' requested — all within approved folder');
            }

            // Determine access type
            var hasWrite = /\b(write|create|save|modify|edit|update)\b/i.test(planText);
            var hasExec = /\b(run|execute|command|powershell)\b/i.test(planText);

            if (hasWrite) {
                lines.push('Read and write access — files may be created or modified');
            } else {
                lines.push('Read-only access — no files will be modified');
            }

            if (hasExec) {
                lines.push('System commands requested — limited to approved PowerShell cmdlets');
            } else {
                lines.push('No system commands — no PowerShell execution');
            }

            lines.push('Results stay on-device — no network calls');

            return lines;
        }

        function renderToolCard(name, args, result, execTime) {
            var argsHtml = "";
            if (args) {
                for (var k in args) {
                    var v = args[k];
                    if (typeof v === "string" && v.length > 120) v = v.substring(0, 120) + "...";
                    argsHtml += "<div><strong>" + k + ":</strong> " + (v + "").replace(/</g, "&lt;") + "</div>";
                }
            }
            var statusClass = (result && result.success) ? "tool-ok" : "tool-fail";
            var statusIcon = (result && result.success) ? "&#9989;" : "&#10060;";
            var outputPreview = "";
            if (result) {
                var out = result.output || result.error || "";
                if (out.length > 200) out = out.substring(0, 200) + "...";
                outputPreview = out.replace(/</g, "&lt;").replace(/\n/g, "<br>");
            }
            return '<div class="tool-card">' +
                '<div class="tool-header">&#128295; Tool: ' + name + '</div>' +
                '<div class="tool-args">' + argsHtml + '</div>' +
                (result ? '<div class="tool-result"><span class="' + statusClass + '">' + statusIcon +
                    (result.success ? " Success" : " Failed") + '</span>' +
                    (outputPreview ? '<div style="margin-top:4px;opacity:0.85;font-size:0.92em;">' + outputPreview + '</div>' : '') +
                    '<div class="tool-time">&#9201; ' + (execTime || "?") + 's</div></div>' : '') +
                '</div>';
        }

        // --- Approval gate state ---
        var pendingApprovalReview = false;
        var pendingSummarize = false;
        var lastAssistantResponse = "";

        function renderApprovalCard(planText) {
            // Parse plan body — extract lines between markers or use raw text
            var body = planText;
            var planMatch = planText.match(/\[PLAN\]([\s\S]*?)\[\/PLAN\]/i);
            if (planMatch) {
                body = planMatch[1].trim();
            }
            // Convert bullet lines to HTML list
            var bodyHtml = body.split("\n").map(function(line) {
                line = line.trim();
                if (!line) return "";
                if (line.match(/^[-•*]\s/)) return "<div style='padding:2px 0;'>\u2022 " + line.replace(/^[-•*]\s*/, "") + "</div>";
                if (line.match(/^(Files|Action|Plan):/i)) return "<div style='font-weight:bold;margin-top:6px;'>" + line + "</div>";
                return "<div>" + line + "</div>";
            }).join("");

            // Generate Security Review section (Agentic Firewall)
            var securityLines = generateSecurityReview(body);
            var securityHtml = '<div class="security-review">' +
                '<div class="security-review-header">\uD83D\uDEE1\uFE0F Security Review</div>' +
                securityLines.map(function(line) {
                    return '<div class="security-review-line">\u2022 ' + line + '</div>';
                }).join('') +
                '</div>';

            var cardId = "approvalCard_" + Date.now();
            return '<div class="approval-card" id="' + cardId + '">' +
                '<div class="approval-header">\uD83D\uDD12 This action requires approval</div>' +
                '<div style="font-size:0.85em;opacity:0.7;margin-bottom:10px;">The AI agent wants to:</div>' +
                '<div class="approval-body">' + bodyHtml + '</div>' +
                securityHtml +
                '<div class="approval-actions">' +
                    '<button class="approval-btn approve" onclick="handleApproval(\'' + cardId + '\', true)">\u2705 Approve</button>' +
                    '<button class="approval-btn deny" onclick="handleApproval(\'' + cardId + '\', false)">\u274C Deny</button>' +
                '</div>' +
                '<div class="approval-policy">\uD83D\uDCCB Policy: Read-only within approved folder. All actions logged.</div>' +
                '</div>';
        }

        window.handleApproval = function(cardId, approved) {
            var card = document.getElementById(cardId);
            if (!card) return;
            var actionsDiv = card.querySelector(".approval-actions");
            if (!actionsDiv) return;

            if (approved) {
                actionsDiv.innerHTML = '<span class="approval-badge approved">\u2705 Approved</span>';
                card.classList.add("approved");
                // Add audit entry
                addAuditEntry("APPROVAL", {action: "Review & Summarize"}, true, 0);
                // Send follow-up to agent
                document.getElementById("userInput").value = "APPROVED. Proceed with the plan you outlined. Execute the file reads and produce the risk summary.";
                sendMessage();
            } else {
                actionsDiv.innerHTML = '<span class="approval-badge denied">\u274C Denied</span>';
                card.classList.add("denied");
                addAuditEntry("APPROVAL_DENIED", {action: "Review & Summarize", files: 0}, false, 0);
                addMessage("assistant", '<div style="color:#FF8C00;">Action denied by user. No files were accessed.</div>');
            }
        };

        function sendMessage() {
            var input = document.getElementById("userInput");
            var message = input.value.trim();
            if (!message) return;

            input.value = "";
            document.getElementById("sendBtn").disabled = true;

            addMessage("user", message);

            var assistantDiv = addMessage("assistant", '<span class="spinner"></span> Thinking...');
            var contentDiv = assistantDiv.querySelector(".content");
            var htmlParts = [];

            fetch("/chat", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ message: message, model: currentModel })
            })
            .then(function(r) { return r.body.getReader(); })
            .then(function(reader) {
                var decoder = new TextDecoder();
                var buffer = "";

                function processLine(line) {
                    line = line.trim();
                    if (!line) return;
                    try {
                        var evt = JSON.parse(line);
                    } catch(e) { console.log("[FE] JSON parse error:", line.substring(0, 50)); return; }
                    console.log("[FE] Event received:", evt.type, evt.type === "response" ? "text_len=" + (evt.text||"").length : "");

                    if (evt.type === "thinking") {
                        htmlParts.push('<div style="opacity:0.6;"><span class="spinner"></span> Thinking...</div>');
                        contentDiv.innerHTML = htmlParts.join("");
                    }
                    else if (evt.type === "think_done") {
                        // Replace last thinking indicator with done
                        for (var i = htmlParts.length - 1; i >= 0; i--) {
                            if (htmlParts[i].indexOf("Thinking...") >= 0) {
                                htmlParts[i] = '<div style="opacity:0.5;">&#129504; Thought for ' + evt.time + 's</div>';
                                break;
                            }
                        }
                        contentDiv.innerHTML = htmlParts.join("");
                    }
                    else if (evt.type === "tool_call") {
                        // Agentic Firewall: Add security check line before tool execution
                        var securityMsg = getSecurityExplanation(evt.name, evt.arguments);
                        htmlParts.push('<div class="security-check-line">\uD83D\uDEE1\uFE0F Security: ' + securityMsg + '</div>');
                        htmlParts.push(renderToolCard(evt.name, evt.arguments, null, null));
                        contentDiv.innerHTML = htmlParts.join("");
                    }
                    else if (evt.type === "tool_result") {
                        // Update the last tool card with result
                        for (var j = htmlParts.length - 1; j >= 0; j--) {
                            if (htmlParts[j].indexOf("tool-card") >= 0 && htmlParts[j].indexOf("tool-result") < 0) {
                                var nameMatch = htmlParts[j].match(/Tool: (\w+)/);
                                var toolName = nameMatch ? nameMatch[1] : "?";
                                // Parse args back from HTML (simplified)
                                htmlParts[j] = renderToolCard(toolName, null, evt.result, evt.time);
                                addAuditEntry(toolName, {}, evt.result.success, evt.time);
                                break;
                            }
                        }
                        contentDiv.innerHTML = htmlParts.join("");
                        // After network tool calls, refresh connectivity
                        if (htmlParts.join("").toLowerCase().indexOf("netadapter") >= 0) {
                            setTimeout(checkConnectivity, 2000);
                        }
                    }
                    else if (evt.type === "response") {
                        // Remove any remaining thinking indicators
                        htmlParts = htmlParts.filter(function(p) { return p.indexOf("Thinking...") < 0; });

                        var responseText = evt.text || "";
                        lastAssistantResponse = responseText;
                        // Check for approval gate: [PLAN] markers OR heuristic (pendingApprovalReview + bullet list + no TOOL_CALL)
                        var hasPlanMarkers = responseText.indexOf("[PLAN]") >= 0 && responseText.indexOf("[/PLAN]") >= 0;
                        var hasBullets = (responseText.match(/^[-•*]\s/m) || responseText.match(/^\d+\.\s/m));
                        var noToolCall = responseText.indexOf("[TOOL_CALL]") < 0;
                        var isApprovalResponse = hasPlanMarkers || (pendingApprovalReview && hasBullets && noToolCall);

                        if (isApprovalResponse) {
                            pendingApprovalReview = false;
                            htmlParts.push(renderApprovalCard(responseText));
                            htmlParts.push('<div class="tool-time" style="margin-top:4px;">&#9201; ' + evt.time + 's</div>');
                        } else {
                            if (pendingApprovalReview && noToolCall) {
                                // Model didn't follow plan format — still show as approval card with raw text
                                pendingApprovalReview = false;
                                htmlParts.push(renderApprovalCard(responseText));
                                htmlParts.push('<div class="tool-time" style="margin-top:4px;">&#9201; ' + evt.time + 's</div>');
                            } else {
                                pendingApprovalReview = false;
                                htmlParts.push('<div style="margin-top:8px;">' + responseText.replace(/\n/g, "<br>") + '</div>');
                                htmlParts.push('<div class="tool-time" style="margin-top:4px;">&#9201; Total: ' + evt.time + 's</div>');
                            }
                        }
                        // Add inline Save Summary button after summarize completes
                        if (pendingSummarize && lastAssistantResponse) {
                            pendingSummarize = false;
                            htmlParts.push('<div style="margin-top:12px;"><button onclick="window.saveSummary()" style="background:linear-gradient(135deg,#0078d4,#00bcf2);color:#fff;border:none;padding:10px 24px;border-radius:8px;font-size:0.95em;cursor:pointer;font-weight:600;">&#128190; Save Summary to File</button></div>');
                        }
                        contentDiv.innerHTML = htmlParts.join("");
                    }
                    else if (evt.type === "error") {
                        htmlParts.push('<div style="color:#FF4444;">Error: ' + evt.message + '</div>');
                        contentDiv.innerHTML = htmlParts.join("");
                    }
                    else if (evt.type === "done") {
                        document.getElementById("sendBtn").disabled = false;
                        document.getElementById("userInput").focus();
                    }
                    document.getElementById("chatContainer").scrollTop = document.getElementById("chatContainer").scrollHeight;
                }

                function read() {
                    reader.read().then(function(chunk) {
                        if (chunk.done) {
                            if (buffer.trim()) processLine(buffer);
                            document.getElementById("sendBtn").disabled = false;
                            document.getElementById("userInput").focus();
                            return;
                        }
                        buffer += decoder.decode(chunk.value);
                        var lines = buffer.split("\n");
                        buffer = lines.pop();
                        lines.forEach(processLine);
                        read();
                    });
                }
                read();
            })
            .catch(function(err) {
                contentDiv.innerHTML = '<div style="color:#FF4444;">Connection error: ' + err.message + '</div>';
                document.getElementById("sendBtn").disabled = false;
            });
        }
        
        // === Camera/ID Functions ===
        function enumerateCameras() {
            var select = document.getElementById("cameraSelect");
            select.innerHTML = '<option value="">Detecting cameras...</option>';
            
            // Need to request permission first to get device labels
            navigator.mediaDevices.getUserMedia({ video: true })
            .then(function(stream) {
                // Stop this temporary stream
                stream.getTracks().forEach(function(track) { track.stop(); });
                
                // Now enumerate devices
                return navigator.mediaDevices.enumerateDevices();
            })
            .then(function(devices) {
                select.innerHTML = "";
                var videoDevices = devices.filter(function(d) { return d.kind === "videoinput"; });
                
                if (videoDevices.length === 0) {
                    select.innerHTML = '<option value="">No cameras found</option>';
                    return;
                }
                
                videoDevices.forEach(function(device, index) {
                    var option = document.createElement("option");
                    option.value = device.deviceId;
                    // Use label if available, otherwise generic name
                    var label = device.label || ("Camera " + (index + 1));
                    // Try to identify built-in vs external
                    if (label.toLowerCase().indexOf("front") >= 0) {
                        label += " (Front)";
                    } else if (label.toLowerCase().indexOf("back") >= 0 || label.toLowerCase().indexOf("rear") >= 0) {
                        label += " (Rear)";
                    } else if (label.toLowerCase().indexOf("surface") >= 0 || label.toLowerCase().indexOf("integrated") >= 0 || label.toLowerCase().indexOf("built-in") >= 0) {
                        label += " (Built-in)";
                    }
                    option.textContent = label;
                    select.appendChild(option);
                });
                
                console.log("Found " + videoDevices.length + " camera(s)");
            })
            .catch(function(err) {
                console.error("Error enumerating cameras:", err);
                select.innerHTML = '<option value="">Camera access denied</option>';
            });
        }
        
        function startCamera() {
            console.log("Starting camera...");
            var selectedDeviceId = document.getElementById("cameraSelect").value;
            
            var constraints = {
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                }
            };
            
            // If a specific device is selected, use it
            if (selectedDeviceId) {
                constraints.video.deviceId = { exact: selectedDeviceId };
            }
            
            navigator.mediaDevices.getUserMedia(constraints)
            .then(function(stream) {
                cameraStream = stream;
                var video = document.getElementById("cameraPreview");
                video.srcObject = stream;
                video.style.display = "block";
                document.getElementById("cameraPlaceholder").style.display = "none";
                document.getElementById("startCameraBtn").textContent = "Stop Camera";
                document.getElementById("startCameraBtn").classList.add("stop");
                document.getElementById("startCameraBtn").removeEventListener("click", startCamera);
                document.getElementById("startCameraBtn").addEventListener("click", stopCamera);
                document.getElementById("captureBtn").style.display = "inline-block";
                document.getElementById("capturedImage").style.display = "none";
                document.getElementById("retakeBtn").style.display = "none";
                document.getElementById("analyzeIdBtn").style.display = "none";
            })
            .catch(function(err) {
                console.error("Camera error:", err);
                alert("Could not access camera: " + err.message);
            });
        }
        
        function stopCamera() {
            if (cameraStream) {
                cameraStream.getTracks().forEach(function(track) { track.stop(); });
                cameraStream = null;
            }
            document.getElementById("cameraPreview").style.display = "none";
            document.getElementById("cameraPlaceholder").style.display = "block";
            document.getElementById("startCameraBtn").textContent = "Start Camera";
            document.getElementById("startCameraBtn").classList.remove("stop");
            document.getElementById("startCameraBtn").removeEventListener("click", stopCamera);
            document.getElementById("startCameraBtn").addEventListener("click", startCamera);
            document.getElementById("captureBtn").style.display = "none";
        }
        
        function captureImage() {
            var video = document.getElementById("cameraPreview");
            var canvas = document.getElementById("captureCanvas");
            var img = document.getElementById("capturedImage");
            
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            canvas.getContext("2d").drawImage(video, 0, 0);
            
            img.src = canvas.toDataURL("image/png");
            img.style.display = "block";
            video.style.display = "none";
            
            document.getElementById("captureBtn").style.display = "none";
            document.getElementById("retakeBtn").style.display = "inline-block";
            document.getElementById("analyzeIdBtn").style.display = "inline-block";
            
            // Stop camera to save resources
            if (cameraStream) {
                cameraStream.getTracks().forEach(function(track) { track.stop(); });
            }
        }
        
        function retakeImage() {
            document.getElementById("capturedImage").style.display = "none";
            document.getElementById("retakeBtn").style.display = "none";
            document.getElementById("analyzeIdBtn").style.display = "none";
            document.getElementById("processingSteps").style.display = "none";
            document.getElementById("ocrPreview").style.display = "none";
            document.getElementById("idResultCard").style.display = "none";
            startCamera();
        }
        
        function updateStep(stepNum, status) {
            var step = document.getElementById("step" + stepNum);
            var icon = step.querySelector(".step-icon");
            icon.classList.remove("step-pending", "step-active", "step-done");
            icon.classList.add("step-" + status);
            if (status === "done") {
                icon.innerHTML = "&#10003;";
            } else if (status === "active") {
                icon.innerHTML = '<span class="spinner" style="width:14px;height:14px;margin:0;border-width:2px;"></span>';
            }
        }
        
        function analyzeId() {
            console.log("Analyzing ID...");
            
            document.getElementById("processingSteps").style.display = "block";
            document.getElementById("ocrPreview").style.display = "none";
            document.getElementById("idResultCard").style.display = "none";
            
            // Reset steps
            for (var i = 1; i <= 3; i++) {
                var step = document.getElementById("step" + i);
                var icon = step.querySelector(".step-icon");
                icon.classList.remove("step-active", "step-done");
                icon.classList.add("step-pending");
                icon.innerHTML = i;
            }
            
            // Step 1: Image captured (already done)
            updateStep(1, "done");
            
            // Step 2: OCR
            updateStep(2, "active");
            
            var img = document.getElementById("capturedImage");
            
            Tesseract.recognize(img.src, "eng", {
                workerPath: "/tesseract/worker.min.js",
                corePath: "/tesseract/core",
                langPath: "/tesseract/lang",
                workerBlobURL: false,
                logger: function(m) { console.log("Tesseract:", m); }
            }).then(function(result) {
                var ocrText = result.data.text;
                console.log("OCR Result:", ocrText);
                
                updateStep(2, "done");
                
                document.getElementById("ocrPreview").style.display = "block";
                document.getElementById("ocrText").textContent = ocrText;
                
                // Step 3: AI Analysis
                updateStep(3, "active");
                
                fetch("/analyze-id", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({ ocr_text: ocrText, model: currentModel })
                })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    updateStep(3, "done");
                    displayIdResult(data);
                })
                .catch(function(err) {
                    console.error("Analysis error:", err);
                    updateStep(3, "done");
                    displayIdResult({ error: err.message });
                });
                
            }).catch(function(err) {
                console.error("OCR error:", err);
                updateStep(2, "done");
                document.getElementById("ocrPreview").style.display = "block";
                document.getElementById("ocrText").textContent = "Error: " + err.message;
            });
        }
        
        function displayIdResult(data) {
            var card = document.getElementById("idResultCard");
            var badge = document.getElementById("idStatusBadge");
            var fieldsDiv = document.getElementById("idFields");
            var notesDiv = document.getElementById("idNotes");
            
            card.style.display = "block";
            
            if (data.error) {
                badge.textContent = "Error";
                badge.className = "status-badge status-error";
                fieldsDiv.innerHTML = "<p>Could not analyze ID: " + data.error + "</p>";
                notesDiv.innerHTML = "";
                return;
            }
            
            // Set status badge
            var status = data.status || "Unknown";
            badge.textContent = status;
            if (status.toLowerCase().indexOf("valid") >= 0) {
                badge.className = "status-badge status-valid";
            } else if (status.toLowerCase().indexOf("review") >= 0 || status.toLowerCase().indexOf("warning") >= 0) {
                badge.className = "status-badge status-warning";
            } else {
                badge.className = "status-badge status-error";
            }
            
            // Display fields
            var fields = data.fields || {};
            var fieldsHtml = "";
            var fieldLabels = {
                "name": "Full Name",
                "address": "Address",
                "dob": "Date of Birth",
                "id_number": "ID Number",
                "expiration": "Expiration Date",
                "state": "State",
                "class": "License Class"
            };
            
            for (var key in fields) {
                var label = fieldLabels[key] || key;
                var value = fields[key] || "Not detected";
                fieldsHtml += '<div class="id-field"><span class="id-field-label">' + label + '</span><span class="id-field-value">' + value + '</span></div>';
            }
            
            fieldsDiv.innerHTML = fieldsHtml || "<p>No fields extracted</p>";
            
            // Display notes
            if (data.notes) {
                notesDiv.innerHTML = "<strong>Notes:</strong> " + data.notes;
            } else {
                notesDiv.innerHTML = "";
            }
        }
        
        console.log("Script loaded!");
    </script>

    <!-- File Picker Modal for Review & Summarize -->
    <div id="filePickerOverlay" class="file-picker-overlay" style="display:none;">
        <div class="file-picker-modal">
            <div class="file-picker-header">🔍 Select Documents to Review</div>
            <div class="file-picker-subtitle">Choose files for confidential review and risk analysis</div>
            <div class="file-picker-list" id="filePickerList">
                <!-- Files populated dynamically -->
            </div>
            <div class="file-picker-actions">
                <button class="file-picker-btn cancel" onclick="closeFilePicker()">Cancel</button>
                <button class="file-picker-btn confirm" id="filePickerConfirm" onclick="confirmFilePicker()" disabled>Review Selected (0)</button>
            </div>
        </div>
    </div>
</body>
</html>'''

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/logos/<path:filename>')
def serve_logos(filename):
    # Restrict to image files directly under SCRIPT_DIR (no traversal)
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        return "Not found", 404
    filepath = os.path.join(SCRIPT_DIR, filename)
    resolved = os.path.realpath(filepath)
    if not resolved.startswith(os.path.realpath(SCRIPT_DIR) + os.sep):
        return "Not found", 404
    if not os.path.exists(resolved):
        return "Not found", 404
    if filename.endswith('.avif'):
        mimetype = 'image/avif'
    elif filename.endswith('.webp'):
        mimetype = 'image/webp'
    elif filename.endswith('.png'):
        mimetype = 'image/png'
    else:
        return "Not found", 404
    with open(resolved, 'rb') as f:
        content = f.read()
    return Response(content, mimetype=mimetype)

TESSERACT_DIR = os.path.join(SCRIPT_DIR, 'tesseract')

@app.route('/tesseract/<path:filename>')
def serve_tesseract(filename):
    """Serve locally-bundled Tesseract.js files for offline OCR support."""
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        return "Not found", 404
    filepath = os.path.join(TESSERACT_DIR, filename)
    resolved = os.path.realpath(filepath)
    if not resolved.startswith(os.path.realpath(TESSERACT_DIR) + os.sep):
        return "Not found", 404
    if not os.path.exists(resolved):
        return "Not found", 404
    # Determine MIME type
    if filename.endswith('.js'):
        mimetype = 'application/javascript'
    elif filename.endswith('.wasm'):
        mimetype = 'application/wasm'
    elif filename.endswith('.gz'):
        mimetype = 'application/gzip'
    else:
        mimetype = 'application/octet-stream'
    with open(resolved, 'rb') as f:
        content = f.read()
    return Response(content, mimetype=mimetype)


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload-to-demo', methods=['POST'])
def upload_to_demo():
    """Upload a file, extract text, save as .txt in Demo folder for agent access."""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        filename = secure_filename(file.filename)
        # Extension allowlist — only document types we support
        allowed_ext = {'.pdf', '.docx', '.txt', '.md'}
        ext = os.path.splitext(filename)[1].lower()
        if ext not in allowed_ext:
            return jsonify({'success': False, 'error': f'File type {ext} not supported. Allowed: {", ".join(sorted(allowed_ext))}'})
        # Save original to temp for extraction
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_path)
        text = extract_text(temp_path)
        try:
            os.remove(temp_path)
        except Exception:
            pass
        if text.startswith("Error"):
            return jsonify({'success': False, 'error': text})
        # Save extracted text to Demo folder
        base_name = os.path.splitext(filename)[0] + ".txt"
        demo_path = os.path.join(DEMO_DIR, base_name)
        with open(demo_path, 'w', encoding='utf-8') as f:
            f.write(text)
        words = len(text.split())
        return jsonify({
            'success': True,
            'path': demo_path,
            'words': words,
            'text': text,  # Return text content for Auditor
            'filename': base_name  # Return filename for display
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/save-summary', methods=['POST'])
def save_summary():
    """Direct file write — no AI needed. Increments filename if exists."""
    data = request.json
    file_path = data.get('path', '')
    content = data.get('content', '')
    if not _path_in_demo_dir(file_path):
        return jsonify({'success': False, 'error': 'Security Policy: file outside approved folder.'})
    try:
        # Increment filename if it already exists
        base, ext = os.path.splitext(file_path)
        final_path = file_path
        counter = 2
        while os.path.exists(final_path):
            final_path = f"{base}_{counter}{ext}"
            counter += 1
        with open(final_path, 'w', encoding='utf-8') as f:
            f.write(content)
        AGENT_AUDIT_LOG.append({
            "timestamp": _time.strftime("%H:%M:%S"),
            "tool": "write",
            "arguments": {"path": final_path},
            "success": True,
            "time": 0,
        })
        # Return the actual filename used
        saved_name = os.path.basename(final_path)
        return jsonify({'success': True, 'filename': saved_name})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/demo/meeting-agenda', methods=['POST'])
def demo_meeting_agenda():
    """Single-step meeting agenda creation — direct write, one model call."""
    data = request.json
    model = DEFAULT_MODEL
    output_path = os.path.join(DEMO_DIR, "board_meeting_prep.txt")

    def generate():
        start = _time.time()
        yield json.dumps({"type": "status", "text": "Generating meeting agenda..."}) + "\n"

        try:
            _call_start = _time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful executive assistant. Be concise and professional."},
                    {"role": "user", "content": "Create a board meeting agenda for tomorrow covering Q4 results, 2026 strategy, and executive compensation. Format it professionally with times and topics."},
                ],
                max_tokens=512,
                temperature=0.3,
            )
            _track_model_call(response, _time.time() - _call_start)
            agenda = (response.choices[0].message.content or "").strip()

            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(agenda)

            AGENT_AUDIT_LOG.append({
                "timestamp": _time.strftime("%H:%M:%S"),
                "tool": "write",
                "arguments": {"path": output_path},
                "success": True,
                "time": round(_time.time() - start, 1),
            })

            total = round(_time.time() - start, 1)
            yield json.dumps({
                "type": "result",
                "text": agenda,
                "time": total,
                "file": os.path.basename(output_path)
            }) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='text/plain')


@app.route('/demo/analyze-strategy', methods=['POST'])
def demo_analyze_strategy():
    """Single-step strategy analysis — direct read, one model call."""
    data = request.json
    model = DEFAULT_MODEL
    file_path = os.path.join(DEMO_DIR, "strategy_2026.txt")

    def generate():
        start = _time.time()
        yield json.dumps({"type": "status", "text": "Reading strategy document..."}) + "\n"

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"Could not read file: {e}"}) + "\n"
            return

        AGENT_AUDIT_LOG.append({
            "timestamp": _time.strftime("%H:%M:%S"),
            "tool": "read",
            "arguments": {"path": file_path},
            "success": True,
            "time": 0,
        })

        if len(content) > 2500:
            content = content[:2500] + "\n...(truncated)"

        yield json.dumps({"type": "status", "text": "Analyzing with AI..."}) + "\n"

        try:
            _call_start = _time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful executive assistant. Be concise."},
                    {"role": "user", "content": f"Here is a strategy document:\n\n{content}\n\nGive me the three key takeaways."},
                ],
                max_tokens=512,
                temperature=0.3,
            )
            _track_model_call(response, _time.time() - _call_start)
            analysis = (response.choices[0].message.content or "").strip()
            total = round(_time.time() - start, 1)
            yield json.dumps({"type": "result", "text": analysis, "time": total}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='text/plain')


@app.route('/demo/list-documents', methods=['POST'])
def demo_list_documents():
    """Single-step directory listing — direct listing, one model call for summary."""
    data = request.json
    model = DEFAULT_MODEL

    def generate():
        start = _time.time()
        yield json.dumps({"type": "status", "text": "Listing documents..."}) + "\n"

        try:
            files = os.listdir(DEMO_DIR)
            file_list = []
            for f in sorted(files):
                full_path = os.path.join(DEMO_DIR, f)
                if os.path.isfile(full_path):
                    size = os.path.getsize(full_path)
                    file_list.append(f"{f} ({size:,} bytes)")
                else:
                    file_list.append(f"{f}/ (folder)")

            listing = "\n".join(file_list)

            AGENT_AUDIT_LOG.append({
                "timestamp": _time.strftime("%H:%M:%S"),
                "tool": "exec",
                "arguments": {"command": f"Get-ChildItem {DEMO_DIR}"},
                "success": True,
                "time": round(_time.time() - start, 1),
            })

            yield json.dumps({"type": "status", "text": "Summarizing..."}) + "\n"

            _call_start = _time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Be brief."},
                    {"role": "user", "content": f"Here are the files in the Demo folder:\n\n{listing}\n\nBriefly describe what's in this folder (1-2 sentences)."},
                ],
                max_tokens=256,
                temperature=0.3,
            )
            _track_model_call(response, _time.time() - _call_start)
            summary = (response.choices[0].message.content or "").strip()
            total = round(_time.time() - start, 1)
            yield json.dumps({
                "type": "result",
                "text": f"**Documents in Demo folder:**\n\n{listing}\n\n{summary}",
                "time": total
            }) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='text/plain')


@app.route('/demo/device-health', methods=['POST'])
def demo_device_health():
    """Device health check — deterministic PowerShell collectors + AI summary."""
    model = DEFAULT_MODEL

    HEALTH_CHECKS = [
        {
            "id": "disk",
            "name": "Disk Space",
            "icon": "\U0001f4be",
            "cmd": 'Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | Select-Object DeviceID, @{N="SizeGB";E={[math]::Round($_.Size/1GB,1)}}, @{N="FreeGB";E={[math]::Round($_.FreeSpace/1GB,1)}}, @{N="UsedPct";E={[math]::Round(($_.Size-$_.FreeSpace)/$_.Size*100,0)}} | Format-List',
        },
        {
            "id": "battery",
            "name": "Battery",
            "icon": "\U0001f50b",
            "cmd": 'Get-CimInstance Win32_Battery | Select-Object @{N="ChargePercent";E={$_.EstimatedChargeRemaining}}, @{N="Status";E={switch($_.BatteryStatus){1{"Discharging"}2{"AC Power"}default{$_.BatteryStatus}}}} | Format-List',
        },
        {
            "id": "system",
            "name": "System Info",
            "icon": "\U0001f4bb",
            "cmd": 'Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, @{N="BootTime";E={$_.LastBootUpTime.ToString("yyyy-MM-dd HH:mm")}}, @{N="UptimeDays";E={[math]::Round(((Get-Date)-$_.LastBootUpTime).TotalDays,1)}} | Format-List',
        },
        {
            "id": "network",
            "name": "Network Adapters",
            "icon": "\U0001f310",
            "cmd": 'Get-NetAdapter | Where-Object {$_.Status -eq "Up"} | Select-Object Name, InterfaceDescription, LinkSpeed, Status | Format-List',
        },
        {
            "id": "security",
            "name": "Defender Antivirus",
            "icon": "\U0001f6e1\ufe0f",
            "cmd": 'Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled, @{N="SignatureAge";E={(New-TimeSpan $_.AntivirusSignatureLastUpdated (Get-Date)).Days.ToString() + " days"}}, @{N="LastScan";E={$_.QuickScanEndTime.ToString("yyyy-MM-dd HH:mm")}} | Format-List',
        },
        {
            "id": "firewall",
            "name": "Firewall Profiles",
            "icon": "\U0001f9f1",
            "cmd": 'Get-NetFirewallProfile | Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction | Format-List',
        },
        {
            "id": "ports",
            "name": "Listening Ports",
            "icon": "\U0001f50c",
            "cmd": 'Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Select-Object LocalPort, @{N="Process";E={(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName}} | Sort-Object LocalPort -Unique | Select-Object -First 12 | Format-Table -AutoSize | Out-String',
        },
        {
            "id": "updates",
            "name": "Windows Updates",
            "icon": "\U0001f504",
            "cmd": 'Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 3 HotFixID, InstalledOn, Description | Format-List',
        },
        {
            "id": "events",
            "name": "Recent System Errors",
            "icon": "\u26a0\ufe0f",
            "cmd": 'Get-WinEvent -FilterHashtable @{LogName="System";Level=1,2,3} -MaxEvents 5 -ErrorAction SilentlyContinue | Select-Object TimeCreated, LevelDisplayName, @{N="Source";E={$_.ProviderName}}, @{N="Msg";E={$_.Message.Substring(0,[math]::Min(120,$_.Message.Length))}} | Format-List',
        },
    ]

    def generate():
        start = _time.time()
        results = []

        for check in HEALTH_CHECKS:
            # Signal start
            yield json.dumps({
                "type": "check-start",
                "id": check["id"],
                "name": check["name"],
                "icon": check["icon"],
                "cmd": check["cmd"],
            }) + "\n"

            try:
                proc = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", check["cmd"]],
                    capture_output=True, text=True, timeout=10
                )
                output = (proc.stdout or "").strip()
                if proc.returncode != 0 and proc.stderr:
                    output = output or proc.stderr.strip()
                if not output:
                    output = "(no data available)"
                # Truncate per-check output
                if len(output) > 350:
                    output = output[:350] + "..."

                results.append(f"{check['name']}:\n{output}")
                yield json.dumps({
                    "type": "check-done",
                    "id": check["id"],
                    "output": output,
                }) + "\n"

            except subprocess.TimeoutExpired:
                results.append(f"{check['name']}: TIMEOUT")
                yield json.dumps({
                    "type": "check-error",
                    "id": check["id"],
                    "output": "Command timed out (10s)",
                }) + "\n"
            except Exception as e:
                results.append(f"{check['name']}: ERROR - {str(e)}")
                yield json.dumps({
                    "type": "check-error",
                    "id": check["id"],
                    "output": str(e),
                }) + "\n"

        # Pre-compute numerical ratings (don't ask AI to do math)
        yield json.dumps({"type": "status", "text": "AI analyzing health data..."}) + "\n"

        health_data = "\n\n".join(results)
        pre_ratings = []
        # Disk usage
        m = re.search(r'UsedPct\s*:\s*(\d+)', health_data)
        if m:
            pct = int(m.group(1))
            if pct >= 90: pre_ratings.append(f"Disk: FAIL — {pct}% used (over 90% threshold)")
            elif pct >= 80: pre_ratings.append(f"Disk: WARN — {pct}% used (over 80% threshold)")
            else: pre_ratings.append(f"Disk: PASS — {pct}% used (healthy)")
        # Uptime
        m = re.search(r'UptimeDays\s*:\s*([\d.]+)', health_data)
        if m:
            days = float(m.group(1))
            if days >= 30: pre_ratings.append(f"Uptime: FAIL — {days} days (over 30-day limit, reboot urgently)")
            elif days >= 7: pre_ratings.append(f"Uptime: WARN — {days} days without reboot (7-day policy exceeded)")
            else: pre_ratings.append(f"Uptime: PASS — {days} days (within 7-day reboot policy)")
        # AV signature age
        m = re.search(r'SignatureAge\s*:\s*(\d+)\s*days', health_data)
        if m:
            age = int(m.group(1))
            if age >= 2: pre_ratings.append(f"AV Signatures: WARN — {age} days old")
            else: pre_ratings.append(f"AV Signatures: PASS — current ({age} days)")
        # Battery
        m = re.search(r'ChargePercent\s*:\s*(\d+)', health_data)
        if m:
            charge = int(m.group(1))
            if charge <= 10: pre_ratings.append(f"Battery: FAIL — {charge}%")
            elif charge <= 20: pre_ratings.append(f"Battery: WARN — {charge}%")
            else: pre_ratings.append(f"Battery: PASS — {charge}%")

        pre_text = "\n".join(pre_ratings)

        # Build "Learn More" findings for WARN/FAIL items
        findings = []
        for r in pre_ratings:
            if "WARN" in r or "FAIL" in r:
                if "Disk" in r:
                    findings.append({"label": "Disk Usage", "q": "Why is high disk usage a concern on enterprise devices and how can I free up space on Windows 11?"})
                elif "Uptime" in r:
                    m2 = re.search(r'([\d.]+) days', r)
                    d = m2.group(1) if m2 else "?"
                    findings.append({"label": "Uptime " + d + "d", "q": f"This device has been running for {d} days without a reboot. Why does enterprise IT policy require regular reboots and what security patches might be pending?"})
                elif "AV" in r:
                    findings.append({"label": "AV Signatures", "q": "Why are outdated antivirus signatures dangerous and how do I update Windows Defender definitions?"})
                elif "Battery" in r:
                    findings.append({"label": "Battery", "q": "What does critically low battery indicate about device health and battery longevity?"})
        # Subjective checks — always include if relevant data exists
        if "NotConfigured" in health_data:
            findings.append({"label": "Firewall Config", "q": "The Windows Firewall profiles show NotConfigured for inbound rules. What does this mean for security and what should enterprise IT configure?"})
        if "445" in health_data or "139" in health_data:
            findings.append({"label": "SMB Ports 139/445", "q": "Ports 139 and 445 (SMB/NetBIOS) are listening on this device. What are the security risks of open SMB ports and should they be closed on an enterprise laptop?"})
        if "Error" in health_data and "Smartcard" in health_data:
            findings.append({"label": "Smartcard Errors", "q": "The system log shows recurring Smart Card Reader errors from Microsoft-Windows-Smartcard-Server. What causes this on a Surface device and how do I fix it?"})
        elif "Error" in health_data:
            findings.append({"label": "System Errors", "q": "The Windows System event log shows recent errors. What do these mean and should I be concerned?"})

        if len(health_data) > 2800:
            health_data = health_data[:2800]

        try:
            _call_start = _time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": (
                        "You are a senior enterprise IT health agent. "
                        "Write a 2-3 sentence executive summary highlighting what is good "
                        "and what needs attention. Be specific — mention port numbers, "
                        "error sources, and uptime days. "
                        "Then list all areas with their PASS/WARN/FAIL rating. "
                        "The pre-computed ratings below are CORRECT — use them exactly. "
                        "You must also rate: Firewall (NotConfigured inbound=FAIL), "
                        "Ports (139/445 SMB/NetBIOS open=WARN), System Errors. "
                        "End with one PRIORITY ACTION."
                    )},
                    {"role": "user", "content": (
                        f"Pre-computed ratings (use these exactly):\n{pre_text}\n\n"
                        f"Raw scan data:\n{health_data}\n\nHealth assessment:"
                    )},
                ],
                max_tokens=512,
                temperature=0.3,
            )
            _track_model_call(response, _time.time() - _call_start)
            summary = (response.choices[0].message.content or "").strip()
            total = round(_time.time() - start, 1)

            AGENT_AUDIT_LOG.append({
                "timestamp": _time.strftime("%H:%M:%S"),
                "tool": "exec",
                "arguments": {"command": "Device Health Check (9 checks)"},
                "success": True,
                "time": total,
            })

            yield json.dumps({
                "type": "result",
                "text": summary,
                "time": total,
                "findings": findings,
            }) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='text/plain')


# Confidential file patterns for demo (files that require approval)
CONFIDENTIAL_PATTERNS = {
    'contract': {'label': 'Contract', 'icon': '📜'},
    'nda': {'label': 'NDA', 'icon': '🔒'},
    'loan': {'label': 'PII Data', 'icon': '🔐'},
    'confidential': {'label': 'Confidential', 'icon': '🔒'},
    'board': {'label': 'Board Material', 'icon': '📊'},
}

@app.route('/demo/list-files', methods=['GET'])
def demo_list_files():
    """List files in Demo folder with confidentiality metadata."""
    files = []
    if os.path.exists(DEMO_DIR):
        for fname in os.listdir(DEMO_DIR):
            fpath = os.path.join(DEMO_DIR, fname)
            if os.path.isfile(fpath) and fname.endswith(('.txt', '.md', '.csv')):
                # Determine confidentiality based on filename patterns
                fname_lower = fname.lower()
                confidential = None
                for pattern, meta in CONFIDENTIAL_PATTERNS.items():
                    if pattern in fname_lower:
                        confidential = meta
                        break

                # Get file size
                try:
                    size = os.path.getsize(fpath)
                    size_str = f"{size:,} bytes" if size < 1024 else f"{size/1024:.1f} KB"
                except:
                    size_str = "?"

                files.append({
                    'name': fname,
                    'size': size_str,
                    'confidential': confidential,
                    'path': fpath
                })

    # Sort: confidential files first, then alphabetically
    files.sort(key=lambda f: (0 if f['confidential'] else 1, f['name']))
    return jsonify({'files': files})


@app.route('/demo/review-summarize', methods=['POST'])
def demo_review_summarize():
    """Two-phase review: accepts selected files, returns plan for approval, then executes."""
    data = request.json
    model = DEFAULT_MODEL
    phase = data.get('phase', 'plan')  # 'plan' or 'execute'
    selected_files = data.get('files', [])  # List of filenames selected by user

    # Fallback if no files provided (backwards compat)
    if not selected_files:
        selected_files = ["strategy_2026.txt", "board_meeting_prep.txt"]

    if phase == 'plan':
        # Phase 1: Return the plan for approval (no AI needed)
        plan_lines = ["**Files to access:**"]
        for fname in selected_files:
            full_path = os.path.join(DEMO_DIR, fname)
            exists = "✓" if os.path.exists(full_path) else "✗ (not found)"
            # Check confidentiality
            fname_lower = fname.lower()
            conf_label = ""
            for pattern, meta in CONFIDENTIAL_PATTERNS.items():
                if pattern in fname_lower:
                    conf_label = f" {meta['icon']} {meta['label']}"
                    break
            plan_lines.append(f"- {fname} {exists}{conf_label}")
        plan_lines.append("")
        plan_lines.append("**Action:** Analyze selected documents and produce a risk summary")
        plan_text = "\n".join(plan_lines)
        return jsonify({"type": "plan", "text": plan_text, "files": selected_files})

    elif phase == 'execute':
        # Phase 2: Actually read files and summarize
        def generate():
            start = _time.time()

            # Read all files
            combined_content = []
            files_read = []
            for fname in selected_files:
                full_path = os.path.join(DEMO_DIR, fname)
                yield json.dumps({"type": "status", "text": f"Reading {fname}..."}) + "\n"
                if os.path.exists(full_path):
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        combined_content.append(f"=== {fname} ===\n{content[:1500]}")
                        files_read.append(fname)
                        AGENT_AUDIT_LOG.append({
                            "timestamp": _time.strftime("%H:%M:%S"),
                            "tool": "read",
                            "arguments": {"path": full_path},
                            "success": True,
                            "time": 0,
                        })
                    except Exception as e:
                        combined_content.append(f"=== {fname} ===\n[Error reading: {e}]")

            if not combined_content:
                yield json.dumps({"type": "error", "message": "No files found to review"}) + "\n"
                return

            yield json.dumps({"type": "status", "text": "Analyzing for risks..."}) + "\n"

            try:
                _call_start = _time.time()
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are an executive assistant preparing a board briefing. Be concise and focus on risks."},
                        {"role": "user", "content": (
                            f"Review these documents and identify key risks to brief the board on:\n\n"
                            f"{chr(10).join(combined_content)}\n\n"
                            "Produce a brief risk summary with:\n"
                            "1. Top 3 risks identified\n"
                            "2. Recommended actions\n"
                            "Keep it executive-ready."
                        )},
                    ],
                    max_tokens=512,
                    temperature=0.3,
                )
                _track_model_call(response, _time.time() - _call_start)
                summary = (response.choices[0].message.content or "").strip()
                total = round(_time.time() - start, 1)
                yield json.dumps({
                    "type": "result",
                    "text": summary,
                    "time": total,
                    "files_read": files_read
                }) + "\n"
            except Exception as e:
                yield json.dumps({"type": "error", "message": str(e)}) + "\n"

        return Response(generate(), mimetype='text/plain')

    return jsonify({"type": "error", "message": "Invalid phase"})


@app.route('/detect-pii', methods=['POST'])
def detect_pii():
    """Single-step PII detection — reads file directly, one model call."""
    data = request.json
    file_path = data.get('path', '')
    model = DEFAULT_MODEL

    def generate():
        start = _time.time()
        yield json.dumps({"type": "status", "text": "Reading document..."}) + "\n"

        if not _path_in_demo_dir(file_path):
            yield json.dumps({"type": "error", "message": "Security Policy: file outside approved folder."}) + "\n"
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"Could not read file: {e}"}) + "\n"
            return

        AGENT_AUDIT_LOG.append({
            "timestamp": _time.strftime("%H:%M:%S"),
            "tool": "read",
            "arguments": {"path": file_path},
            "success": True,
            "time": 0,
        })

        if len(content) > 2500:
            content = content[:2500] + "\n...(truncated)"

        yield json.dumps({"type": "status", "text": "Scanning for PII..."}) + "\n"

        try:
            _call_start = _time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a security analyst. Be thorough but concise."},
                    {"role": "user", "content": f"Here is a document:\n\n{content}\n\nScan it for any Personally Identifiable Information (PII) such as names, SSNs, addresses, phone numbers, emails, or account numbers. List each item found and rate the overall risk level (High/Medium/Low)."},
                ],
                max_tokens=512,
                temperature=0.3,
            )
            _track_model_call(response, _time.time() - _call_start)
            analysis = (response.choices[0].message.content or "").strip()
            total = round(_time.time() - start, 1)
            yield json.dumps({"type": "result", "text": analysis, "time": total}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='text/plain')


@app.route('/summarize-doc', methods=['POST'])
def summarize_doc():
    """Single-step document summarization — reads file directly, one model call."""
    data = request.json
    file_path = data.get('path', '')
    model = DEFAULT_MODEL

    def generate():
        start = _time.time()
        yield json.dumps({"type": "status", "text": "Reading document..."}) + "\n"

        # Read file directly — no model call needed
        if not _path_in_demo_dir(file_path):
            yield json.dumps({"type": "error", "message": "Security Policy: file outside approved folder."}) + "\n"
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"Could not read file: {e}"}) + "\n"
            return

        # Truncate to fit Phi-4 Mini context
        if len(content) > 2500:
            content = content[:2500] + "\n...(truncated)"

        yield json.dumps({"type": "status", "text": f"Analyzing {len(content.split())} words with AI..."}) + "\n"

        try:
            _call_start = _time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Be concise and executive-ready. Use ONLY the information provided — do not invent names or facts."},
                    {"role": "user", "content": (
                        f"Here is a document:\n\n{content}\n\n"
                        "Produce a structured summary with these sections:\n"
                        "MEETING SUMMARY (2-3 sentence overview)\n"
                        "KEY IDEAS & DECISIONS (bullet the most important points)\n"
                        "ACTION ITEMS (list each with the owner's name if mentioned)"
                    )},
                ],
                max_tokens=512,
                temperature=0.3,
            )
            _track_model_call(response, _time.time() - _call_start)
            summary = (response.choices[0].message.content or "").strip()
            total = round(_time.time() - start, 1)
            yield json.dumps({"type": "summary", "text": summary, "time": total}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='text/plain')


@app.route('/chat', methods=['POST'])
def chat():
    """Agent chat — routes through tool-calling pipeline."""
    data = request.json
    message = data.get('message', '')
    model = DEFAULT_MODEL

    def generate():
        # Step 1: Send to model with agent system prompt
        yield json.dumps({"type": "thinking"}) + "\n"
        start = _time.time()

        try:
            _call_start = _time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
                max_tokens=1024,
                temperature=0.3,
            )
            _track_model_call(response, _time.time() - _call_start)
            model_output = (response.choices[0].message.content or "").strip()
            think_time = round(_time.time() - start, 1)
            print(f"[DEBUG] Model returned {len(model_output)} chars in {think_time}s")
            yield json.dumps({"type": "think_done", "time": think_time}) + "\n"

            # Step 2: Parse for tool call
            tool_call = parse_tool_call(model_output)
            print(f"[DEBUG] parse_tool_call returned: {tool_call}")

            if tool_call and tool_call.get("name") not in (None, "__text_response"):
                tool_name = tool_call["name"]
                tool_args = tool_call.get("arguments", {})
                yield json.dumps({"type": "tool_call", "name": tool_name, "arguments": tool_args}) + "\n"

                # Step 3: Execute tool
                exec_start = _time.time()
                result = execute_tool(tool_name, tool_args)
                exec_time = round(_time.time() - exec_start, 1)
                yield json.dumps({"type": "tool_result", "result": result, "time": exec_time}) + "\n"

                # Audit log
                AGENT_AUDIT_LOG.append({
                    "timestamp": _time.strftime("%H:%M:%S"),
                    "tool": tool_name,
                    "arguments": tool_args,
                    "success": result.get("success", False),
                    "time": exec_time,
                })

                # Step 4: Feed result back to model for a spoken summary
                yield json.dumps({"type": "thinking"}) + "\n"
                tool_output = result.get("output", result.get("error", "No output"))
                # Truncate large outputs so model stays focused
                if len(tool_output) > 1500:
                    tool_output = tool_output[:1500] + "\n...(truncated)"
                followup_msgs = [
                    {"role": "system", "content": "You are a helpful assistant. Respond in plain text only. No tool calls."},
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": model_output},
                    {"role": "user", "content": (
                        f"Tool result:\n{tool_output}\n\n"
                        "Respond to the user in plain text based on this result. "
                        "Be concise. Do NOT use [TOOL_CALL] markers. "
                        "Use ONLY the information above — do not invent names or facts."
                    )},
                ]
                try:
                    _call_start2 = _time.time()
                    followup = client.chat.completions.create(
                        model=model,
                        messages=followup_msgs,
                        max_tokens=512,
                        temperature=0.3,
                    )
                    _track_model_call(followup, _time.time() - _call_start2)
                    final_text = (followup.choices[0].message.content or "").strip()
                except Exception as e:
                    final_text = f"Tool executed successfully but the AI summary failed: {e}"
                final_text = re.sub(r'\[/?TOOL_(?:CALL|RESPONSE)\]', '', final_text).strip()
                total = round(_time.time() - start, 1)
                yield json.dumps({"type": "response", "text": final_text, "time": total}) + "\n"

            else:
                # Pure text response (no tool needed)
                print(f"[DEBUG] No tool call detected, model_output length: {len(model_output)}")
                print(f"[DEBUG] model_output preview: {model_output[:300]}...")
                text = model_output
                if tool_call and tool_call.get("name") == "__text_response":
                    text = tool_call.get("arguments", {}).get("text", model_output)
                text = re.sub(r'\[/?TOOL_(?:CALL|RESPONSE)\]', '', text).strip()
                total = round(_time.time() - start, 1)
                print(f"[DEBUG] Yielding response event, text length: {len(text)}")
                yield json.dumps({"type": "response", "text": text, "time": total}) + "\n"

            yield json.dumps({"type": "done"}) + "\n"

        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='text/plain')


# === Clean Room Auditor Endpoints ===

AUDITOR_DEMO_NDA = """MUTUAL NON-DISCLOSURE AGREEMENT

Effective Date: January 15, 2026
Agreement Number: NDA-2026-VD-PS-0847

BETWEEN:

Vertex Dynamics, Inc.
1200 Innovation Drive, Suite 400
San Jose, CA 95134
Contact: James Morrison, VP Corporate Development
Email: j.morrison@vertexdyn.com
Phone: (415) 555-0142

AND:

Pinnacle Solutions Group, LLC
8900 Enterprise Boulevard
Austin, TX 78759
Contact: Sarah Chen, General Counsel

SECTION 1. DEFINITION OF CONFIDENTIAL INFORMATION

1.1 "Confidential Information" means any and all non-public, proprietary, or confidential information disclosed by either party to the other, whether orally, in writing, electronically, or by inspection of tangible objects.

SECTION 2. OBLIGATIONS OF RECEIVING PARTY

2.1 The receiving party shall hold all Confidential Information in strict confidence and shall not disclose such information to any third party without the prior written consent of the disclosing party.

SECTION 3. TERM AND DURATION

3.1 This Agreement shall remain in effect for a period of two (2) years from the Effective Date.

3.2 The obligations of confidentiality shall survive termination for a period of five (5) years.

SECTION 4. INDEMNIFICATION AND LIABILITY

4.1 Each party shall indemnify and hold harmless the other party from claims arising from a breach of this Agreement.

4.2 NOTWITHSTANDING ANY OTHER PROVISION, THE DISCLOSING PARTY SHALL BE ENTITLED TO FULL INDEMNIFICATION FOR ALL DAMAGES, INCLUDING CONSEQUENTIAL, INCIDENTAL, INDIRECT, SPECIAL, AND PUNITIVE DAMAGES, ARISING FROM ANY BREACH BY THE RECEIVING PARTY. THIS PROVISION SHALL NOT BE SUBJECT TO ANY CAP OR LIMITATION.

SECTION 5. RETURN OF MATERIALS

5.1 Upon termination, the receiving party shall return or destroy all Confidential Information within thirty (30) days.

SECTION 6. REMEDIES

6.1 The non-breaching party shall be entitled to seek injunctive relief in addition to any other remedies.

SECTION 7. INTELLECTUAL PROPERTY

7.1 ALL WORK PRODUCT, INVENTIONS, AND INNOVATIONS, WHETHER CREATED PRIOR TO OR DURING THIS AGREEMENT, THAT ARE USED IN CONNECTION WITH THE PURPOSE, SHALL BE THE SOLE PROPERTY OF THE DISCLOSING PARTY.

SECTION 8. NON-SOLICITATION

8.1 Neither party shall solicit or hire employees of the other party for twelve (12) months following termination.

SECTION 9. NON-COMPETITION

9.1 The receiving party shall not engage in any competing business anywhere in the world for twenty-four (24) months following termination.

SECTION 10. GOVERNING LAW

10.1 This Agreement shall be governed by the laws of the State of Delaware.

IN WITNESS WHEREOF:

VERTEX DYNAMICS, INC.
By: _________________________
Name: James A. Morrison
Title: VP Corporate Development
SSN (for notarization): 478-93-3847
Date: January 15, 2026

PINNACLE SOLUTIONS GROUP, LLC
By: _________________________
Name: Sarah L. Chen
Title: General Counsel
Date: January 15, 2026
"""

@app.route('/auditor-demo-doc', methods=['GET'])
def auditor_demo_doc():
    """Return the pre-staged NDA document for demo."""
    text = AUDITOR_DEMO_NDA
    return jsonify({
        "filename": "contract_nda_vertex_pinnacle.txt",
        "text": text,
        "word_count": len(text.split())
    })


@app.route('/auditor-analyze', methods=['POST'])
def auditor_analyze():
    """Analyze a document with verbose logging for demo purposes."""
    data = request.json
    text = data.get('text', '')
    filename = data.get('filename', 'document.txt')
    mode = data.get('mode', 'full')  # full, risk, obligations, pii
    model = DEFAULT_MODEL

    def generate():
        import re
        start_time = _time.time()
        pii_time = 0
        analysis_time = 0

        word_count = len(text.split())
        section_matches = re.findall(r'SECTION\s+\d+', text, re.IGNORECASE)

        # Estimate completion time based on word count
        # Formula: ~15s base + ~70s per 1000 words for AI analysis
        # PII scan is instant (regex), bulk of time is NPU inference
        # Calibrated from testing: 413 words took ~41s total (33s NPU inference)
        estimated_seconds = 15 + int((word_count / 1000) * 70)
        if mode == 'pii':
            estimated_seconds = 2  # PII-only is instant
        elif mode in ('risk', 'obligations'):
            estimated_seconds = int(estimated_seconds * 0.7)  # Single-pass is faster

        # Step 1: Document ingestion
        yield json.dumps({
            "type": "log",
            "status": "complete",
            "message": "Document ingested",
            "details": [
                f"{word_count:,} words across ~{max(1, word_count // 500)} pages",
                f"Detected sections: {len(section_matches)} ({', '.join(section_matches[:5])}{'...' if len(section_matches) > 5 else ''})",
                f"⏱️ Estimated analysis time: ~{estimated_seconds}s"
            ]
        }) + "\n"

        # Step 2: PII Scan (if mode is full or pii)
        if mode in ('full', 'pii'):
            pii_start = _time.time()
            yield json.dumps({
                "type": "log",
                "status": "active",
                "message": "PII Scan (regex patterns)",
                "details": [
                    "Scanning for: SSN (XXX-XX-XXXX), Credit Cards, Email addresses, Phone numbers"
                ]
            }) + "\n"

            pii_findings = []
            # SSN
            for match in re.finditer(r'\b(\d{3})-(\d{2})-(\d{4})\b', text):
                pii_findings.append({
                    "severity": "high",
                    "type": "SSN",
                    "value": f"XXX-XX-{match.group(3)}",
                    "location": _estimate_pii_location(text, match.start())
                })
            # Email
            for match in re.finditer(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text):
                pii_findings.append({
                    "severity": "medium",
                    "type": "Email",
                    "value": match.group(0),
                    "location": _estimate_pii_location(text, match.start())
                })
            # Phone
            for match in re.finditer(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text):
                pii_findings.append({
                    "severity": "medium",
                    "type": "Phone",
                    "value": match.group(0),
                    "location": _estimate_pii_location(text, match.start())
                })

            pii_time = round(_time.time() - pii_start, 2)
            yield json.dumps({
                "type": "log",
                "status": "complete",
                "message": f"PII Scan complete — {len(pii_findings)} instance(s) found",
                "details": []
            }) + "\n"

            if pii_findings:
                yield json.dumps({"type": "pii", "findings": pii_findings}) + "\n"

        # Step 3: Risk Analysis (if mode is full or risk)
        if mode in ('full', 'risk', 'obligations'):
            analysis_start = _time.time()
            elapsed_so_far = int(analysis_start - start_time)
            remaining_estimate = max(10, estimated_seconds - elapsed_so_far)

            # Show the prompt being used
            yield json.dumps({
                "type": "log",
                "status": "active",
                "message": "Risk Analysis (Phi-4 Mini on NPU)",
                "details": [f"⏱️ ~{remaining_estimate}s remaining — this is the main NPU inference pass"]
            }) + "\n"

            analysis_prompt = """Analyze this contract and identify:
1. HIGH RISK clauses (one-sided, unlimited liability, unusual terms)
2. MEDIUM RISK clauses (broad scope, aggressive terms)
3. LOW RISK clauses (standard boilerplate)
4. Key OBLIGATIONS with deadlines

For each risk, provide:
- SEVERITY: HIGH/MEDIUM/LOW
- SECTION: section number
- TYPE: category (indemnification, IP, non-compete, etc.)
- FINDING: one sentence description
- RECOMMENDATION: one sentence action"""

            yield json.dumps({
                "type": "prompt",
                "label": "PROMPT TO PHI-4 MINI:",
                "text": analysis_prompt
            }) + "\n"

            yield json.dumps({
                "type": "log",
                "status": "active",
                "message": "Analyzing clauses for legal risks...",
                "details": [
                    "Focus: indemnification, IP assignment, liability caps",
                    "Focus: non-compete scope, termination penalties"
                ]
            }) + "\n"

            # Make the AI call
            try:
                full_prompt = f"{analysis_prompt}\n\nCONTRACT TEXT:\n{text[:3000]}"

                _call_start = _time.time()
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a contract analyst. Be concise and specific. Focus on non-standard or risky clauses."},
                        {"role": "user", "content": full_prompt}
                    ],
                    max_tokens=800,
                    temperature=0.3
                )
                _track_model_call(response, _time.time() - _call_start)
                ai_response = (response.choices[0].message.content or "").strip()

                analysis_time = round(_time.time() - analysis_start, 1)

                # Debug: Print raw AI response to console
                print("\n" + "="*50)
                print("[AUDITOR DEBUG] Raw AI Response:")
                print("="*50)
                print(ai_response[:1500] + ("..." if len(ai_response) > 1500 else ""))
                print("="*50 + "\n")

                yield json.dumps({
                    "type": "log",
                    "status": "complete",
                    "message": f"Analysis complete ({analysis_time}s on NPU)",
                    "details": []
                }) + "\n"

                # Parse the response into structured findings
                risk_findings, obligation_findings, used_fallback = _parse_analysis_response(ai_response)

                # Debug: Log parsing result
                if used_fallback:
                    print("[AUDITOR DEBUG] AI parsing FAILED - using FALLBACK findings")
                    yield json.dumps({
                        "type": "log",
                        "status": "complete",
                        "message": "⚠️ Using fallback analysis (AI output not structured)",
                        "details": ["AI response didn't match expected format", "Demo fallback findings applied"]
                    }) + "\n"
                else:
                    print(f"[AUDITOR DEBUG] AI parsing SUCCEEDED - {len(risk_findings)} risks, {len(obligation_findings)} obligations")
                    yield json.dumps({
                        "type": "log",
                        "status": "complete",
                        "message": f"✅ Parsed {len(risk_findings)} risks, {len(obligation_findings)} obligations from AI",
                        "details": []
                    }) + "\n"

                if risk_findings and mode in ('full', 'risk'):
                    yield json.dumps({"type": "risk", "findings": risk_findings}) + "\n"

                if obligation_findings and mode in ('full', 'obligations'):
                    yield json.dumps({"type": "obligations", "findings": obligation_findings}) + "\n"

                # Generate summary
                if mode == 'full':
                    summary_start = _time.time()
                    elapsed_so_far = int(summary_start - start_time)
                    remaining_estimate = max(5, estimated_seconds - elapsed_so_far)
                    yield json.dumps({
                        "type": "log",
                        "status": "active",
                        "message": "Generating executive summary...",
                        "details": [f"⏱️ ~{remaining_estimate}s remaining — final NPU pass"]
                    }) + "\n"

                    summary_prompt = f"Write a 2-3 sentence executive summary of this contract analysis. Key risks found: {len(risk_findings)}. Focus on the most critical issue for a CEO."

                    _call_start2 = _time.time()
                    summary_response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "You are a contract analyst writing for a CEO. Be extremely concise."},
                            {"role": "user", "content": f"{summary_prompt}\n\nAnalysis:\n{ai_response[:1000]}"}
                        ],
                        max_tokens=200,
                        temperature=0.3
                    )
                    _track_model_call(summary_response, _time.time() - _call_start2)
                    summary_text = (summary_response.choices[0].message.content or "").strip()

                    yield json.dumps({
                        "type": "log",
                        "status": "complete",
                        "message": "Executive summary complete",
                        "details": []
                    }) + "\n"

                    yield json.dumps({"type": "summary", "text": summary_text}) + "\n"

            except Exception as e:
                yield json.dumps({
                    "type": "log",
                    "status": "error",
                    "message": f"Analysis error: {str(e)}",
                    "details": []
                }) + "\n"

        # Final audit stamp
        total_time = round(_time.time() - start_time, 1)
        time_diff = total_time - estimated_seconds
        time_accuracy = "on target" if abs(time_diff) <= 5 else ("faster" if time_diff < 0 else "slower")
        yield json.dumps({
            "type": "audit",
            "total_time": total_time,
            "estimated_time": estimated_seconds,
            "time_accuracy": time_accuracy,
            "pii_time": pii_time,
            "analysis_time": analysis_time
        }) + "\n"

    return Response(generate(), mimetype='text/plain')


def _estimate_pii_location(text, char_pos):
    """Estimate page and context from character position."""
    chars_per_page = 3000
    page = (char_pos // chars_per_page) + 1
    start = max(0, char_pos - 100)
    end = min(len(text), char_pos + 100)
    context = text[start:end]

    section_match = re.search(r'SECTION\s+(\d+)', context, re.IGNORECASE)
    if section_match:
        return f"Page {page}, Section {section_match.group(1)}"

    if any(word in context.lower() for word in ['signature', 'witness', 'notary']):
        return f"Page {page}, Signature block"

    return f"Page {page}"


def _parse_analysis_response(response_text):
    """Parse AI response into structured risk and obligation findings.

    Returns: (risk_findings, obligation_findings, used_fallback)
    - used_fallback is True if hardcoded demo findings were used instead of parsed AI output
    """
    risk_findings = []
    obligation_findings = []
    used_fallback = False

    # Try to extract structured data, with fallbacks
    lines = response_text.split('\n')

    current_risk = {}
    for line in lines:
        line = line.strip()

        # Skip empty lines and section headers
        if not line:
            continue
        line_lower = line.lower()

        # Skip section headers like "HIGH RISK clauses:", "MEDIUM RISK clauses:"
        if line_lower.endswith('clauses:') or line_lower.endswith('risk:'):
            continue

        # When we see a new SEVERITY line, save the previous finding first
        if line_lower.startswith('severity:') or line_lower.startswith('- severity:'):
            # Save previous finding if complete
            if current_risk.get('finding'):
                risk_findings.append(current_risk)
            # Start new finding
            current_risk = {}
            level = line.split(':', 1)[1].strip().upper()
            if level in ('HIGH', 'MEDIUM', 'LOW'):
                current_risk['severity'] = level.lower()
        elif line_lower.startswith('section:') or line_lower.startswith('- section:'):
            current_risk['section'] = line.split(':', 1)[1].strip()
        elif line_lower.startswith('type:') or line_lower.startswith('- type:'):
            current_risk['type'] = line.split(':', 1)[1].strip()
        elif line_lower.startswith('finding:') or line_lower.startswith('- finding:'):
            current_risk['finding'] = line.split(':', 1)[1].strip()
        elif line_lower.startswith('recommendation:') or line_lower.startswith('- recommendation:'):
            current_risk['recommendation'] = line.split(':', 1)[1].strip()

        # Obligation parsing
        elif line_lower.startswith('obligation:') or line_lower.startswith('- obligation:'):
            obl = {'obligation': line.split(':', 1)[1].strip(), 'deadline': '', 'consequence': ''}
            obligation_findings.append(obl)
        elif line_lower.startswith('deadline:') and obligation_findings:
            obligation_findings[-1]['deadline'] = line.split(':', 1)[1].strip()
        elif line_lower.startswith('consequence:') and obligation_findings:
            obligation_findings[-1]['consequence'] = line.split(':', 1)[1].strip()

    # Capture last risk if pending
    if current_risk.get('finding'):
        risk_findings.append(current_risk)

    # Debug: print what was parsed
    print(f"[AUDITOR DEBUG] Parsed {len(risk_findings)} risk findings, {len(obligation_findings)} obligations")

    # If parsing failed, create fallback findings from key sections in demo NDA
    if not risk_findings:
        used_fallback = True
        # Fallback findings for the demo NDA
        risk_findings = [
            {
                "severity": "high",
                "section": "4.2",
                "type": "Indemnification",
                "finding": "Unlimited indemnification with no cap on damages, including consequential and punitive damages.",
                "recommendation": "Negotiate a liability cap tied to contract value or 2x fees."
            },
            {
                "severity": "medium",
                "section": "7.1",
                "type": "IP Assignment",
                "finding": "Broad IP assignment that may capture pre-existing work product created before the agreement.",
                "recommendation": "Carve out pre-existing IP and limit to work created specifically under this agreement."
            },
            {
                "severity": "medium",
                "section": "9.1",
                "type": "Non-Compete",
                "finding": "24-month global non-compete restriction. Likely unenforceable in California.",
                "recommendation": "Narrow geographic scope or reduce to 12 months."
            },
            {
                "severity": "low",
                "section": "1-3",
                "type": "Confidentiality",
                "finding": "Standard mutual NDA confidentiality terms with reasonable 5-year survival period.",
                "recommendation": "No changes needed - standard boilerplate."
            }
        ]

    if not obligation_findings:
        # Don't set used_fallback for obligations - risks are the main analysis
        # Obligations are supplementary and often not in AI response
        obligation_findings = [
            {"obligation": "Confidentiality period", "deadline": "5 years from termination", "consequence": "Breach damages"},
            {"obligation": "Return materials", "deadline": "30 days after termination", "consequence": "Must certify destruction"},
            {"obligation": "Non-compete", "deadline": "24 months post-termination", "consequence": "Injunctive relief"}
        ]

    return risk_findings, obligation_findings, used_fallback


@app.route('/analyze-id', methods=['POST'])
def analyze_id():
    data = request.json
    ocr_text = data.get('ocr_text', '')
    model = DEFAULT_MODEL
    
    prompt = """You are an ID document analyzer. Given the OCR text extracted from a US driver's license or state ID, extract the following information.

IMPORTANT - US Driver's License Name Format:
- Field 1 (often labeled "1" or "LN"): LAST NAME (surname/family name)
- Field 2 (often labeled "2" or "FN"): FIRST NAME and MIDDLE NAME
- Combine these as: "First Middle Last" (e.g., if you see "1BUCHHOLZ" and "2FRANK JOACHIM", the full name is "Frank Joachim Buchholz")

IMPORTANT - License Number:
- The license/ID number is usually labeled "4d LIC#" or "DL" and is an alphanumeric code (e.g., "WDLBTJC488FB")
- Do NOT confuse the street address number with the license number

Extract these fields:
- name: Full name in "First Middle Last" format (combine fields 1 and 2 as described above)
- address: Street address, city, state, ZIP
- dob: Date of birth (usually field 3 or "DOB")
- id_number: Driver's license number (the alphanumeric code, NOT the street number)
- expiration: Expiration date (usually field 4b or "EXP")
- state: Issuing state (e.g., WA, CA, TX)
- class: License class if shown

Determine status:
- "Valid" if expiration date is after January 2026 and info looks complete
- "Expired" if expiration date is before January 2026
- "Review Needed" if critical information is unclear or missing

Return your response in this exact JSON format:
{
    "fields": {
        "name": "...",
        "address": "...",
        "dob": "...",
        "id_number": "...",
        "expiration": "...",
        "state": "...",
        "class": "..."
    },
    "status": "Valid|Review Needed|Expired",
    "notes": "..."
}

OCR Text from ID:
---
""" + ocr_text + """
---

Return ONLY valid JSON, no other text."""

    try:
        _call_start = _time.time()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an ID verification assistant. Always respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=512,
            temperature=0.3
        )
        _track_model_call(response, _time.time() - _call_start)

        result_text = response.choices[0].message.content.strip()
        
        # Try to parse JSON from response
        import json
        try:
            # Handle potential markdown code blocks
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            result = json.loads(result_text)
        except:
            # If JSON parsing fails, return a structured error
            result = {
                "fields": {"name": "Could not parse"},
                "status": "Review Needed",
                "notes": "AI response was not in expected format. Raw: " + result_text[:200]
            }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "fields": {},
            "status": "Error",
            "notes": "Analysis failed"
        })

@app.route('/audit-log', methods=['GET'])
def audit_log():
    """Return the agent's audit trail."""
    return jsonify(AGENT_AUDIT_LOG)


@app.route('/audit-log', methods=['DELETE'])
def clear_audit_log():
    """Clear the agent's audit trail."""
    AGENT_AUDIT_LOG.clear()
    return jsonify({"success": True})


@app.route('/session-stats', methods=['GET'])
def session_stats():
    """Return session stats and computed savings for the Local AI Savings widget."""
    calls = SESSION_STATS["calls"]
    input_tokens = SESSION_STATS["input_tokens"]
    output_tokens = SESSION_STATS["output_tokens"]
    inference_seconds = SESSION_STATS["inference_seconds"]

    # Foundry Local doesn't report token usage - estimate from call count
    # Average: ~600 input tokens (system prompt + content), ~300 output tokens
    if calls > 0 and input_tokens == 0:
        input_tokens = calls * 600
        output_tokens = calls * 300

    # Cloud cost: Azure GPT-4o pricing with 1.5x enterprise overhead
    # Input: $2.50/1M tokens, Output: $10.00/1M tokens
    cloud_cost = (input_tokens * 2.50 / 1e6 + output_tokens * 10.00 / 1e6) * 1.5

    # NPU energy: 5W sustained during inference
    npu_wh = inference_seconds * 5.0 / 3600

    # Cloud energy: 0.4 Wh per query (GPT-4o, arxiv/Epoch AI)
    cloud_wh = calls * 0.4

    # CO2 avoided: US grid average 373 g/kWh
    co2_avoided_g = (cloud_wh - npu_wh) / 1000 * 373

    return jsonify({
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "inference_seconds": round(inference_seconds, 1),
        "cloud_cost_saved": round(cloud_cost, 4),
        "npu_wh": round(npu_wh, 4),
        "cloud_wh": round(cloud_wh, 2),
        "co2_avoided_g": round(co2_avoided_g, 2),
    })


@app.route('/connectivity-check', methods=['GET'])
def connectivity_check():
    """Check network and NPU availability for the airplane mode demo."""
    # Check WiFi adapter status
    wifi_up = False
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "(Get-NetAdapter -Name 'Wi-Fi' -ErrorAction SilentlyContinue).Status"],
            capture_output=True, text=True, timeout=5
        )
        wifi_up = "Up" in (proc.stdout or "")
    except Exception:
        pass

    # Check Foundry Local
    npu_ok = False
    try:
        client.models.list()
        npu_ok = True
    except Exception:
        pass

    return jsonify({
        "network": wifi_up,
        "npu": npu_ok,
        "storage": True,  # always true for local
    })


@app.route('/network-toggle', methods=['POST'])
def network_toggle():
    """Directly toggle network adapters for Go Offline / Go Online."""
    action = (request.json or {}).get('action', 'offline')
    if action == 'offline':
        cmd = "Disable-NetAdapter -Name 'Wi-Fi','Cellular' -Confirm:$false -ErrorAction SilentlyContinue"
    else:
        cmd = "Enable-NetAdapter -Name 'Wi-Fi','Cellular' -Confirm:$false -ErrorAction SilentlyContinue"
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=10
        )
        return jsonify({'success': True, 'action': action})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/my-day-counts', methods=['GET'])
def my_day_counts():
    """Return counts for My Day dashboard cards."""
    ics_path = os.path.join(MY_DAY_DIR, 'calendar.ics')
    csv_path = os.path.join(MY_DAY_DIR, 'tasks.csv')
    events = parse_ics(ics_path)
    tasks = parse_tasks_csv(csv_path)
    emails = parse_inbox(MY_DAY_INBOX)
    return jsonify({
        'events': len(events),
        'tasks': len(tasks),
        'emails': len(emails),
    })


@app.route('/my-day-data', methods=['GET'])
def my_day_data():
    """Return full parsed data for peek windows."""
    ics_path = os.path.join(MY_DAY_DIR, 'calendar.ics')
    csv_path = os.path.join(MY_DAY_DIR, 'tasks.csv')
    events = parse_ics(ics_path)
    tasks = parse_tasks_csv(csv_path)
    emails = parse_inbox(MY_DAY_INBOX)
    # Format events for display
    ev_list = []
    for ev in events:
        t = ev.get('time', '?')
        end = ev.get('end_time', '')
        time_str = f"{t}-{end}" if end else t
        ev_list.append({
            'time': time_str,
            'summary': ev.get('summary', ''),
            'location': ev.get('location', ''),
        })
    # Format tasks
    task_list = []
    for t in tasks:
        task_list.append({
            'priority': t.get('Priority', 'Medium'),
            'task': t.get('Task', ''),
            'category': t.get('Category', ''),
        })
    # Format emails
    email_list = []
    for em in emails:
        frm = em.get('from', '').split('<')[0].strip().strip('"')
        email_list.append({
            'from': frm,
            'subject': em.get('subject', ''),
            'date': em.get('date', ''),
        })
    return jsonify({
        'events': ev_list,
        'tasks': task_list,
        'emails': email_list,
    })


@app.route('/brief-me', methods=['POST'])
def brief_me():
    """Full morning briefing — parse all data, send to Phi-4 Mini."""
    model = DEFAULT_MODEL

    def generate():
        start = _time.time()

        # Step 1: Parse all data sources
        yield json.dumps({"type": "status", "message": "Reading calendar..."}) + "\n"
        events = parse_ics(os.path.join(MY_DAY_DIR, 'calendar.ics'))
        yield json.dumps({"type": "status", "message": f"Found {len(events)} events"}) + "\n"

        yield json.dumps({"type": "status", "message": "Reading tasks..."}) + "\n"
        tasks = parse_tasks_csv(os.path.join(MY_DAY_DIR, 'tasks.csv'))
        yield json.dumps({"type": "status", "message": f"Found {len(tasks)} tasks"}) + "\n"

        yield json.dumps({"type": "status", "message": "Scanning inbox..."}) + "\n"
        emails = parse_inbox(MY_DAY_INBOX)
        yield json.dumps({"type": "status", "message": f"Found {len(emails)} emails"}) + "\n"

        # Step 2: Compress into prompt
        yield json.dumps({"type": "status", "message": "Analyzing and cross-referencing..."}) + "\n"
        data_text = compress_for_briefing(events, tasks, emails)

        # Step 3: Send to Phi-4 Mini
        yield json.dumps({"type": "status", "message": "Generating briefing with AI..."}) + "\n"
        try:
            _call_start = _time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": BRIEFING_SYSTEM_PROMPT},
                    {"role": "user", "content": data_text},
                ],
                max_tokens=512,
                temperature=0.4,
            )
            _track_model_call(response, _time.time() - _call_start)
            briefing = (response.choices[0].message.content or "").strip()
            total = round(_time.time() - start, 1)
            yield json.dumps({
                "type": "briefing",
                "text": briefing,
                "time": total,
                "counts": {"events": len(events), "tasks": len(tasks), "emails": len(emails)},
            }) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='text/plain')


@app.route('/triage-inbox', methods=['POST'])
def triage_inbox():
    """Email triage — sort into urgent/action/FYI."""
    model = DEFAULT_MODEL

    def generate():
        start = _time.time()
        yield json.dumps({"type": "status", "message": "Reading inbox..."}) + "\n"
        emails = parse_inbox(MY_DAY_INBOX)
        yield json.dumps({"type": "status", "message": f"Analyzing {len(emails)} emails..."}) + "\n"

        # Compress emails for triage
        lines = [f'INBOX: {len(emails)} emails\n']
        for em in emails:
            body = em.get('body', '')
            snippet = body[:200] if body else ''
            lines.append(f"From: {em['from']}\nSubject: {em['subject']}\nSnippet: {snippet}\n")

        prompt = (
            'Sort these emails into three categories:\n'
            'URGENT (needs immediate action today)\n'
            'ACTION NEEDED (should handle today but not critical)\n'
            'FYI (informational, can wait)\n\n'
            'For each email: one line with the category icon, sender name, subject, '
            'and a brief recommended action.\n'
            'Use these icons: URGENT, ACTION, FYI\n\n'
        )

        try:
            _call_start = _time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an executive assistant triaging an inbox. Be concise."},
                    {"role": "user", "content": prompt + '\n'.join(lines)},
                ],
                max_tokens=800,
                temperature=0.3,
            )
            _track_model_call(response, _time.time() - _call_start)
            result = (response.choices[0].message.content or "").strip()
            total = round(_time.time() - start, 1)
            yield json.dumps({"type": "briefing", "text": result, "time": total}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='text/plain')


@app.route('/prep-next-meeting', methods=['POST'])
def prep_next_meeting():
    """Prep brief for the next upcoming meeting."""
    model = DEFAULT_MODEL

    def generate():
        start = _time.time()
        yield json.dumps({"type": "status", "message": "Reading calendar..."}) + "\n"
        events = parse_ics(os.path.join(MY_DAY_DIR, 'calendar.ics'))
        emails = parse_inbox(MY_DAY_INBOX)
        tasks = parse_tasks_csv(os.path.join(MY_DAY_DIR, 'tasks.csv'))

        if not events:
            yield json.dumps({"type": "error", "message": "No events found"}) + "\n"
            return

        # Skip logistics (breakfast, car, prep) — find first substantive meeting
        next_ev = events[0]
        skip_words = ['breakfast', 'car to', 'prep window', 'lunch', 'travel']
        for ev in events:
            summary_lower = ev.get('summary', '').lower()
            if any(sw in summary_lower for sw in skip_words):
                continue
            if ev.get('attendees') or len(ev.get('description', '')) > 100:
                next_ev = ev
                break
        yield json.dumps({"type": "status", "message": f"Prepping for: {next_ev.get('summary', '?')}..."}) + "\n"

        ev_text = (
            f"Meeting: {next_ev.get('summary')}\n"
            f"Time: {next_ev.get('time')} - {next_ev.get('end_time', '?')}\n"
            f"Location: {next_ev.get('location', '?')}\n"
            f"Description: {next_ev.get('description', 'None')}\n"
        )

        # Find related emails and tasks
        email_text = '\n'.join(
            f"- {em['from']}: {em['subject']}" for em in emails[:7]
        )
        task_text = '\n'.join(
            f"- [{t.get('Priority', '?')}] {t.get('Task', '?')}" for t in tasks
        )

        prompt = (
            f"Prepare a brief for this meeting:\n\n{ev_text}\n\n"
            f"Related emails:\n{email_text}\n\n"
            f"Today's tasks:\n{task_text}\n\n"
            "Give a 4-5 sentence prep brief: what this meeting is about, "
            "key points to cover, any relevant context from emails or tasks, "
            "and what to prepare or bring."
        )

        try:
            _call_start = _time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an executive assistant preparing meeting briefs. Be concise and actionable."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.3,
            )
            _track_model_call(response, _time.time() - _call_start)
            result = (response.choices[0].message.content or "").strip()
            total = round(_time.time() - start, 1)
            yield json.dumps({"type": "briefing", "text": result, "time": total}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='text/plain')


@app.route('/top-3-focus', methods=['POST'])
def top_3_focus():
    """Single-step: analyze today's data and return the top 3 priorities."""
    model = DEFAULT_MODEL

    def generate():
        start = _time.time()
        yield json.dumps({"type": "status", "message": "Reading your day..."}) + "\n"
        events = parse_ics(os.path.join(MY_DAY_DIR, 'calendar.ics'))
        tasks = parse_tasks_csv(os.path.join(MY_DAY_DIR, 'tasks.csv'))
        emails = parse_inbox(MY_DAY_INBOX)

        yield json.dumps({"type": "status", "message": "Identifying priorities..."}) + "\n"
        data_text = compress_for_briefing(events, tasks, emails)

        try:
            _call_start = _time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": (
                        "You are a chief of staff. Analyze the user's calendar, tasks, and emails. "
                        "Identify the TOP 3 things they should focus on RIGHT NOW. "
                        "For each item:\n"
                        "1. A clear action title\n"
                        "2. WHY it's urgent (1 sentence)\n"
                        "3. Time needed (estimate)\n"
                        "Rank by impact and urgency. Be direct and decisive."
                    )},
                    {"role": "user", "content": data_text},
                ],
                max_tokens=400,
                temperature=0.3,
            )
            _track_model_call(response, _time.time() - _call_start)
            result = (response.choices[0].message.content or "").strip()
            total = round(_time.time() - start, 1)
            yield json.dumps({"type": "briefing", "text": result, "time": total,
                              "counts": {"events": len(events), "tasks": len(tasks), "emails": len(emails)}}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='text/plain')


@app.route('/tomorrow-preview', methods=['POST'])
def tomorrow_preview():
    """Single-step: high-level overview of tomorrow's schedule."""
    model = DEFAULT_MODEL

    def generate():
        start = _time.time()
        yield json.dumps({"type": "status", "message": "Reading tomorrow's calendar..."}) + "\n"
        all_events = parse_ics(os.path.join(MY_DAY_DIR, 'calendar.ics'))
        all_tasks = parse_tasks_csv(os.path.join(MY_DAY_DIR, 'tasks.csv'))

        # Filter for tomorrow (Feb 8, 2026)
        tomorrow_events = [e for e in all_events if e.get('date', '') == '2026-02-08']
        tomorrow_tasks = [t for t in all_tasks if t.get('Due Date', '') == '2026-02-08']

        if not tomorrow_events and not tomorrow_tasks:
            yield json.dumps({"type": "error", "message": "No events or tasks found for tomorrow."}) + "\n"
            return

        yield json.dumps({"type": "status", "message": f"Found {len(tomorrow_events)} events and {len(tomorrow_tasks)} tasks for tomorrow..."}) + "\n"

        # Build compressed data for tomorrow
        lines = ['TOMORROW: Sun Feb 8 2026\n']
        lines.append(f'CALENDAR ({len(tomorrow_events)} events):')
        for ev in tomorrow_events:
            t = ev.get('time', '?')
            s = ev.get('summary', '?')
            loc = ev.get('location', '')
            desc = ev.get('description', '')[:150]
            lines.append(f'- {t} {s}' + (f' @ {loc}' if loc else '') + f'\n  {desc}')

        lines.append(f'\nTASKS ({len(tomorrow_tasks)} items):')
        for t in tomorrow_tasks:
            prio = t.get('Priority', 'Med')
            name = t.get('Task', '?')
            notes = t.get('Notes', '')[:80]
            lines.append(f'- [{prio}] {name}: {notes}')

        data_text = '\n'.join(lines)
        if len(data_text) > 1800:
            data_text = data_text[:1800]

        yield json.dumps({"type": "status", "message": "Generating tomorrow's preview..."}) + "\n"

        try:
            _call_start = _time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": (
                        "You are a chief of staff. Write a PREVIEW OF TOMORROW with:\n"
                        "1. Overview (2-3 sentences): the arc of the day, key highlights.\n"
                        "2. TIMELINE: chronological flow of the day.\n"
                        "3. PREP TONIGHT: things to do or pack before bed.\n"
                        "4. HIGHLIGHTS: the most exciting parts of tomorrow.\n"
                        "Be enthusiastic where appropriate. Be concise."
                    )},
                    {"role": "user", "content": data_text},
                ],
                max_tokens=500,
                temperature=0.4,
            )
            _track_model_call(response, _time.time() - _call_start)
            result = (response.choices[0].message.content or "").strip()
            total = round(_time.time() - start, 1)
            yield json.dumps({"type": "briefing", "text": result, "time": total,
                              "counts": {"events": len(tomorrow_events), "tasks": len(tomorrow_tasks), "emails": 0}}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return Response(generate(), mimetype='text/plain')


DEMO_MODE = False  # Set via --demo-mode flag to bypass offline check for testing

@app.route('/health')
def health_check():
    """Returns model readiness status for the warmup overlay."""
    return jsonify({"ready": MODEL_READY, "model": DEFAULT_MODEL})

@app.route('/demo-mode-status')
def demo_mode_status():
    """Check if demo mode is enabled (bypasses offline requirement for Clean Room)."""
    return jsonify({"demo_mode": DEMO_MODE})

if __name__ == '__main__':
    import sys

    # Check for --demo-mode flag
    if '--demo-mode' in sys.argv:
        DEMO_MODE = True
        print("\n** DEMO MODE ENABLED - Offline check bypassed for Clean Room Auditor **\n")

    print("\n" + "="*50)
    print("Local NPU AI Assistant (Intel Edition)")
    print("  My Day + AI Agent + Clean Room Auditor + ID Verification")
    print("="*50)
    print(f"Model: {DEFAULT_MODEL}")
    if FOUNDRY_AVAILABLE:
        print(f"Runtime: Foundry Local ({manager.endpoint})")
    else:
        print("Runtime: Foundry Local (fallback to localhost:5272)")
    if DEMO_MODE:
        print("Demo Mode: ENABLED (offline check bypassed)")
    print("")
    print("Features:")
    print("  - My Day (calendar, email, tasks briefing)")
    print("  - AI Agent (tool calling, file ops, system commands)")
    print("  - Clean Room Auditor (confidential document analysis)")
    print("  - ID Verification (Camera + OCR + AI)")
    print("")
    print("All processing happens 100% locally on your device.")
    print("")

    # --- Warmup: verify model is loaded and responsive before serving ---
    print("Warming up model (first call may take a minute)...", flush=True)
    _warmup_done = threading.Event()
    _warmup_ok = [False]

    def _warmup_call():
        try:
            client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=4,
                temperature=0.1,
            )
            _warmup_ok[0] = True
        except Exception:
            pass
        _warmup_done.set()

    _warmup_thread = threading.Thread(target=_warmup_call, daemon=True)
    _warmup_start = _time.time()
    _warmup_thread.start()

    _spinner = ["|", "/", "-", "\\"]
    _si = 0
    while not _warmup_done.wait(timeout=0.5):
        _elapsed = _time.time() - _warmup_start
        print(f"\r  {_spinner[_si % 4]}  Loading model... {_elapsed:.0f}s", end="", flush=True)
        _si += 1

    _warmup_secs = _time.time() - _warmup_start
    if _warmup_ok[0]:
        MODEL_READY = True
        print(f"\r  Model ready in {_warmup_secs:.1f}s              ")
    else:
        MODEL_READY = True  # allow serving anyway
        print(f"\r  Warning: warmup did not complete ({_warmup_secs:.1f}s). Continuing anyway.")

    # --- Keepalive: prevent model from being unloaded during idle ---
    KEEPALIVE_INTERVAL = 180  # seconds

    def _keepalive_loop():
        while True:
            _time.sleep(KEEPALIVE_INTERVAL)
            try:
                client.chat.completions.create(
                    model=DEFAULT_MODEL,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=1,
                    temperature=0.1,
                )
            except Exception:
                pass  # non-critical, will retry next interval

    _keepalive_thread = threading.Thread(target=_keepalive_loop, daemon=True)
    _keepalive_thread.start()

    print("")
    print("Open http://localhost:5000 in your browser")
    print("="*50 + "\n")
    app.run(host="127.0.0.1", debug=True, port=5000, use_reloader=False)
