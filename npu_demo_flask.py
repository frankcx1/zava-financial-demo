"""
Local NPU AI Assistant Demo
Document Analysis + Chat + ID Verification
Runs entirely on-device using Foundry Local + Intel Core Ultra NPU
"""

import os
from flask import Flask, render_template_string, request, Response, jsonify
from openai import OpenAI
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

client = OpenAI(
    base_url="http://localhost:5272/v1",
    api_key="not-needed"
)

MODELS = {"phi-silica": "Phi Silica (Windows AI)"}
DEFAULT_MODEL = "phi-silica"

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
    <script src="https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }
        .container { max-width: 900px; margin: 0 auto; padding: 20px; }
        header { text-align: center; padding: 20px 0; }
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
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
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
        .upload-area {
            background: rgba(255,255,255,0.05);
            border: 2px dashed rgba(255,255,255,0.3);
            border-radius: 15px;
            padding: 40px;
            text-align: center;
            margin-bottom: 20px;
        }
        .upload-area:hover { border-color: #00BCF2; background: rgba(0,188,242,0.1); }
        #fileInput { display: none; }
        .upload-btn, .camera-btn {
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
        .file-info {
            background: rgba(0,188,242,0.2);
            padding: 15px;
            border-radius: 10px;
            margin: 15px 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .document-preview {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 15px;
            margin: 15px 0;
            max-height: 200px;
            overflow-y: auto;
            font-size: 0.9em;
            white-space: pre-wrap;
            text-align: left;
        }
        .summary-result {
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            padding: 20px;
            margin-top: 20px;
            min-height: 100px;
        }
        .summary-result h3 { color: #00BCF2; margin-bottom: 15px; display: flex; justify-content: space-between; }
        .copy-btn {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.3);
            color: #fff;
            padding: 5px 12px;
            border-radius: 15px;
            cursor: pointer;
            font-size: 0.8em;
        }
        .action-buttons { display: flex; gap: 10px; margin-top: 15px; flex-wrap: wrap; }
        .action-btn {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.3);
            color: #fff;
            padding: 10px 20px;
            border-radius: 20px;
            cursor: pointer;
        }
        .action-btn:hover { background: rgba(0,188,242,0.3); border-color: #00BCF2; }
        .action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .doc-qa-section { margin-top: 20px; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.1); }
        .doc-qa-section h4 { color: #00BCF2; margin-bottom: 10px; }
        .doc-input-area { display: flex; gap: 10px; }
        .doc-input-area input {
            flex: 1;
            padding: 12px 15px;
            border-radius: 10px;
            border: none;
            background: rgba(255,255,255,0.1);
            color: #fff;
        }
        .doc-input-area button {
            background: linear-gradient(90deg, #0078D4, #00BCF2);
            border: none;
            color: #fff;
            padding: 12px 25px;
            border-radius: 10px;
            cursor: pointer;
            font-weight: bold;
        }
        .chat-container {
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            min-height: 400px;
            max-height: 500px;
            overflow-y: auto;
        }
        .message { margin: 15px 0; padding: 15px; border-radius: 10px; }
        .user-msg { background: #0078D4; margin-left: 50px; }
        .assistant-msg { background: rgba(255,255,255,0.1); margin-right: 50px; }
        .role { font-size: 0.8em; opacity: 0.7; margin-bottom: 5px; }
        .quick-prompts { display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }
        .quick-btn {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            color: #fff;
            padding: 10px 15px;
            border-radius: 20px;
            cursor: pointer;
        }
        .quick-btn:hover { background: rgba(0,188,242,0.3); border-color: #00BCF2; }
        .input-area { display: flex; gap: 10px; }
        #userInput {
            flex: 1;
            padding: 15px;
            border-radius: 10px;
            border: none;
            background: rgba(255,255,255,0.1);
            color: #fff;
            font-size: 1em;
        }
        #sendBtn {
            background: linear-gradient(90deg, #0078D4, #00BCF2);
            border: none;
            color: #fff;
            padding: 15px 30px;
            border-radius: 10px;
            cursor: pointer;
            font-weight: bold;
        }
        #sendBtn:disabled { opacity: 0.5; cursor: not-allowed; }
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
        footer { text-align: center; padding: 20px; opacity: 0.6; font-size: 0.9em; }
        
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
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logos">
                <img class="surface-logo" src="/logos/surface-logo.png" alt="Microsoft Surface" onerror="this.style.display='none'">
                <div class="logo-divider"></div>
                <img class="copilot-logo" src="/logos/copilot-logo.avif" alt="Copilot+ PC" onerror="this.style.display='none'">
            </div>
            <h1>Local NPU AI Assistant</h1>
            <div class="subtitle">Document Analysis, Chat, and ID Verification - 100% On-Device</div>
            <div>
                <span class="badge">Powered by Intel Core Ultra NPU</span>
                <span class="offline-badge" id="offlineBadge">Online</span>
            </div>
            <div class="model-selector">
                <label for="modelSelect">Model:</label>
                <select id="modelSelect">
                    <option value="phi-silica">Phi Silica (Windows AI)</option>
                </select>
            </div>
        </header>

        <div class="tabs">
            <button class="tab-btn active" id="docTabBtn">Document Analysis</button>
            <button class="tab-btn" id="chatTabBtn">Chat</button>
            <button class="tab-btn" id="idTabBtn">ID Verification</button>
        </div>

        <!-- Document Analysis Tab -->
        <div id="documents-tab" class="tab-content active">
            <div class="upload-area" id="uploadArea">
                <div style="font-size: 3em; margin-bottom: 15px;">&#128193;</div>
                <div style="font-size: 1.2em; margin-bottom: 10px;">Drop your document here or click to browse</div>
                <div style="opacity: 0.7;">Supports PDF, DOCX, TXT files - Max 16MB</div>
                <input type="file" id="fileInput" accept=".pdf,.docx,.txt,.md">
                <button class="upload-btn" type="button" id="selectFileBtn">Select File</button>
            </div>

            <div id="fileInfo" class="file-info" style="display: none;">
                <div>
                    <strong>File: <span id="fileName"></span></strong>
                    <span style="opacity: 0.7; margin-left: 15px;"><span id="fileSize"></span></span>
                </div>
                <div><span id="wordCount"></span> words - <span id="charCount"></span> chars</div>
            </div>

            <div id="documentPreview" class="document-preview" style="display: none;"></div>

            <div class="action-buttons">
                <button class="action-btn" id="summarizeBtn" disabled>Summarize</button>
                <button class="action-btn" id="keyPointsBtn" disabled>Key Points</button>
                <button class="action-btn" id="questionsBtn" disabled>Generate Questions</button>
                <button class="action-btn" id="simplifyBtn" disabled>Simplify</button>
                <button class="action-btn" id="piiDetectBtn" style="background: linear-gradient(90deg, #D41C00, #FF6B35); border: none;" disabled>Detect PII</button>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <select id="translateLang" style="background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3); color: #fff; padding: 10px 15px; border-radius: 20px;" disabled>
                        <option value="Spanish">Spanish</option>
                        <option value="French">French</option>
                        <option value="German">German</option>
                        <option value="Italian">Italian</option>
                        <option value="Portuguese">Portuguese</option>
                        <option value="Chinese (Simplified)">Chinese (Simplified)</option>
                        <option value="Japanese">Japanese</option>
                        <option value="Korean">Korean</option>
                        <option value="Arabic">Arabic</option>
                        <option value="Hindi">Hindi</option>
                        <option value="Russian">Russian</option>
                        <option value="Dutch">Dutch</option>
                        <option value="Polish">Polish</option>
                        <option value="Vietnamese">Vietnamese</option>
                        <option value="Thai">Thai</option>
                    </select>
                    <button class="action-btn" id="translateBtn" disabled>Translate</button>
                </div>
            </div>

            <div id="summaryResult" class="summary-result" style="display: none;">
                <h3>
                    <span>Analysis Result</span>
                    <button class="copy-btn" id="copyBtn">Copy</button>
                </h3>
                <div id="summaryContent"></div>
                <div id="analysisTimer" class="response-timer"></div>
            </div>
            
            <div id="docQaSection" class="doc-qa-section" style="display: none;">
                <h4>Ask About This Document</h4>
                <div class="doc-input-area">
                    <input type="text" id="docQuestion" placeholder="Ask a question about the document...">
                    <button id="askDocBtn">Ask</button>
                </div>
                <div id="docAnswer" class="summary-result" style="display: none; margin-top: 15px;">
                    <h3><span>Answer</span></h3>
                    <div id="docAnswerContent"></div>
                    <div id="docAnswerTimer" class="response-timer"></div>
                </div>
            </div>
        </div>

        <!-- Chat Tab -->
        <div id="chat-tab" class="tab-content">
            <div class="quick-prompts">
                <button class="quick-btn" id="qpSummarize">Summarize</button>
                <button class="quick-btn" id="qpEmail">Draft Email</button>
                <button class="quick-btn" id="qpExplain">Explain</button>
                <button class="quick-btn" id="qpClear">Clear</button>
            </div>

            <div class="chat-container" id="chatContainer">
                <div class="message assistant-msg">
                    <div class="role">Assistant</div>
                    <div>Hello! I am running locally on your Intel Core Ultra NPU. How can I help you today?</div>
                </div>
            </div>

            <div class="input-area">
                <input type="text" id="userInput" placeholder="Type your message here...">
                <button id="sendBtn">Send</button>
            </div>
            
            <div id="chatTimer" class="response-timer"></div>
        </div>

        <!-- ID Verification Tab -->
        <div id="id-tab" class="tab-content">
            <div class="privacy-note">
                <span class="privacy-icon">&#128274;</span>
                <div>
                    <strong>100% Local Processing</strong><br>
                    Your ID image and data never leave this device. Camera capture, OCR, and AI analysis all run locally.
                </div>
            </div>
            
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
                    <div class="step-status">Phi Silica on NPU (Local)</div>
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
        </div>

        <footer>
            Microsoft Surface + Copilot+ PC - Phi Silica on Intel Core Ultra NPU - All processing happens locally
        </footer>
    </div>

    <script>
        console.log("Script starting...");
        
        var documentText = "";
        var chatHistory = [];
        var currentModel = "phi-silica";
        var cameraStream = null;
        
        document.addEventListener("DOMContentLoaded", function() {
            console.log("DOM loaded, setting up event handlers...");
            
            // Tab switching
            function switchTab(activeTab) {
                document.querySelectorAll(".tab-btn").forEach(function(btn) {
                    btn.classList.remove("active");
                });
                document.querySelectorAll(".tab-content").forEach(function(content) {
                    content.classList.remove("active");
                });
                document.getElementById(activeTab + "TabBtn").classList.add("active");
                document.getElementById(activeTab.replace("doc", "documents").replace("id", "id") + "-tab").classList.add("active");
            }
            
            document.getElementById("docTabBtn").addEventListener("click", function() {
                switchTab("doc");
                document.getElementById("documents-tab").classList.add("active");
                document.getElementById("chat-tab").classList.remove("active");
                document.getElementById("id-tab").classList.remove("active");
            });
            
            document.getElementById("chatTabBtn").addEventListener("click", function() {
                document.querySelectorAll(".tab-btn").forEach(function(btn) { btn.classList.remove("active"); });
                document.querySelectorAll(".tab-content").forEach(function(c) { c.classList.remove("active"); });
                document.getElementById("chatTabBtn").classList.add("active");
                document.getElementById("chat-tab").classList.add("active");
            });
            
            document.getElementById("idTabBtn").addEventListener("click", function() {
                document.querySelectorAll(".tab-btn").forEach(function(btn) { btn.classList.remove("active"); });
                document.querySelectorAll(".tab-content").forEach(function(c) { c.classList.remove("active"); });
                document.getElementById("idTabBtn").classList.add("active");
                document.getElementById("id-tab").classList.add("active");
            });
            
            // File upload handlers
            document.getElementById("selectFileBtn").addEventListener("click", function() {
                document.getElementById("fileInput").click();
            });
            
            document.getElementById("uploadArea").addEventListener("click", function(e) {
                if (e.target.id !== "selectFileBtn") {
                    document.getElementById("fileInput").click();
                }
            });
            
            document.getElementById("fileInput").addEventListener("change", function(e) {
                var file = e.target.files[0];
                if (file) handleFile(file);
            });
            
            // Document action buttons
            document.getElementById("summarizeBtn").addEventListener("click", function() { analyzeDocument("summarize"); });
            document.getElementById("keyPointsBtn").addEventListener("click", function() { analyzeDocument("keypoints"); });
            document.getElementById("questionsBtn").addEventListener("click", function() { analyzeDocument("questions"); });
            document.getElementById("simplifyBtn").addEventListener("click", function() { analyzeDocument("simplify"); });
            document.getElementById("translateBtn").addEventListener("click", function() { analyzeDocument("translate"); });
            document.getElementById("piiDetectBtn").addEventListener("click", function() { analyzeDocument("pii"); });
            
            document.getElementById("copyBtn").addEventListener("click", function() {
                var content = document.getElementById("summaryContent").innerText;
                navigator.clipboard.writeText(content);
                this.textContent = "Copied!";
                var btn = this;
                setTimeout(function() { btn.textContent = "Copy"; }, 2000);
            });
            
            document.getElementById("askDocBtn").addEventListener("click", askAboutDoc);
            document.getElementById("docQuestion").addEventListener("keypress", function(e) {
                if (e.key === "Enter") askAboutDoc();
            });
            
            // Chat handlers
            document.getElementById("sendBtn").addEventListener("click", sendMessage);
            document.getElementById("userInput").addEventListener("keypress", function(e) {
                if (e.key === "Enter") sendMessage();
            });
            
            document.getElementById("qpSummarize").addEventListener("click", function() {
                document.getElementById("userInput").value = "Please summarize the following text:\n\n";
                document.getElementById("userInput").focus();
            });
            document.getElementById("qpEmail").addEventListener("click", function() {
                document.getElementById("userInput").value = "Help me draft a professional email about:\n\n";
                document.getElementById("userInput").focus();
            });
            document.getElementById("qpExplain").addEventListener("click", function() {
                document.getElementById("userInput").value = "Please explain this concept in simple terms:\n\n";
                document.getElementById("userInput").focus();
            });
            document.getElementById("qpClear").addEventListener("click", function() {
                chatHistory = [];
                document.getElementById("chatContainer").innerHTML = '<div class="message assistant-msg"><div class="role">Assistant</div><div>Chat cleared! How can I help you?</div></div>';
            });
            
            document.getElementById("modelSelect").addEventListener("change", function() {
                currentModel = this.value;
            });
            
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
                if (navigator.onLine) {
                    badge.textContent = "Online";
                    badge.classList.remove("offline");
                } else {
                    badge.textContent = "Offline Mode";
                    badge.classList.add("offline");
                }
            }
            window.addEventListener("online", updateOnlineStatus);
            window.addEventListener("offline", updateOnlineStatus);
            updateOnlineStatus();
            
            console.log("All event handlers set up!");
        });
        
        // === Document Functions ===
        function formatFileSize(bytes) {
            if (bytes < 1024) return bytes + " B";
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
            return (bytes / (1024 * 1024)).toFixed(1) + " MB";
        }
        
        function handleFile(file) {
            document.getElementById("fileName").textContent = file.name;
            document.getElementById("fileSize").textContent = formatFileSize(file.size);
            document.getElementById("fileInfo").style.display = "flex";
            
            var formData = new FormData();
            formData.append("file", file);
            
            fetch("/upload", { method: "POST", body: formData })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) {
                    documentText = data.text;
                    var preview = document.getElementById("documentPreview");
                    preview.textContent = documentText.substring(0, 1000) + (documentText.length > 1000 ? "..." : "");
                    preview.style.display = "block";
                    document.getElementById("wordCount").textContent = documentText.split(/\s+/).length;
                    document.getElementById("charCount").textContent = documentText.length;
                    document.getElementById("summarizeBtn").disabled = false;
                    document.getElementById("keyPointsBtn").disabled = false;
                    document.getElementById("questionsBtn").disabled = false;
                    document.getElementById("simplifyBtn").disabled = false;
                    document.getElementById("translateBtn").disabled = false;
                    document.getElementById("translateLang").disabled = false;
                    document.getElementById("piiDetectBtn").disabled = false;
                    document.getElementById("docQaSection").style.display = "block";
                } else {
                    alert("Error: " + data.error);
                }
            });
        }
        
        function analyzeDocument(type) {
            var targetLang = document.getElementById("translateLang").value;
            var prompts = {
                "summarize": "Please provide a concise summary of this document:",
                "keypoints": "List the key points from this document:",
                "questions": "Generate 5 important questions that could be asked about this document:",
                "simplify": "Explain this document in simple terms that anyone could understand:",
                "translate": "Translate the following document to " + targetLang + ". Provide only the translation, no explanations:",
                "pii": "Scan this document and list all Personally Identifiable Information (PII) found.\n\nList each item like this:\n- SSN: 123-45-6789\n- Credit Card: 4532-XXXX-XXXX-5567\n- Name: John Smith\n- Phone: (555) 123-4567\n- Email: example@email.com\n- Address: 123 Main St, City, ST 12345\n- DOB: 01/15/1985\n- Bank Account: XXXXXXX1234\n- Driver License: XX-123456\n- Passport: 123456789\n\nAt the end, state the total count and risk level (High/Medium/Low).\n\nFind ALL PII - be thorough.\n\nDocument:"
            };
            
            var resultDiv = document.getElementById("summaryResult");
            var contentDiv = document.getElementById("summaryContent");
            var timerDiv = document.getElementById("analysisTimer");
            
            resultDiv.style.display = "block";
            contentDiv.innerHTML = '<span class="spinner"></span> Analyzing...';
            timerDiv.textContent = "";
            
            var startTime = performance.now();
            
            fetch("/analyze", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ text: documentText, prompt: prompts[type], model: currentModel })
            })
            .then(function(r) { return r.body.getReader(); })
            .then(function(reader) {
                var decoder = new TextDecoder();
                var result = "";
                function read() {
                    reader.read().then(function(chunk) {
                        if (chunk.done) {
                            var duration = ((performance.now() - startTime) / 1000).toFixed(2);
                            timerDiv.textContent = "Generated in " + duration + "s";
                            return;
                        }
                        result += decoder.decode(chunk.value);
                        contentDiv.innerHTML = result;
                        read();
                    });
                }
                read();
            });
        }
        
        function askAboutDoc() {
            var question = document.getElementById("docQuestion").value.trim();
            if (!question) return;
            
            var answerDiv = document.getElementById("docAnswer");
            var contentDiv = document.getElementById("docAnswerContent");
            var timerDiv = document.getElementById("docAnswerTimer");
            
            answerDiv.style.display = "block";
            contentDiv.innerHTML = '<span class="spinner"></span> Thinking...';
            
            var startTime = performance.now();
            
            fetch("/ask-doc", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ text: documentText, question: question, model: currentModel })
            })
            .then(function(r) { return r.body.getReader(); })
            .then(function(reader) {
                var decoder = new TextDecoder();
                var result = "";
                function read() {
                    reader.read().then(function(chunk) {
                        if (chunk.done) {
                            var duration = ((performance.now() - startTime) / 1000).toFixed(2);
                            timerDiv.textContent = "Generated in " + duration + "s";
                            return;
                        }
                        result += decoder.decode(chunk.value);
                        contentDiv.innerHTML = result;
                        read();
                    });
                }
                read();
            });
            
            document.getElementById("docQuestion").value = "";
        }
        
        // === Chat Functions ===
        function addMessage(role, content) {
            var container = document.getElementById("chatContainer");
            var div = document.createElement("div");
            div.className = "message " + (role === "user" ? "user-msg" : "assistant-msg");
            div.innerHTML = '<div class="role">' + (role === "user" ? "You" : "Assistant") + '</div><div class="content">' + content + '</div>';
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
            return div;
        }
        
        function sendMessage() {
            var input = document.getElementById("userInput");
            var message = input.value.trim();
            if (!message) return;
            
            input.value = "";
            document.getElementById("sendBtn").disabled = true;
            
            addMessage("user", message);
            chatHistory.push({role: "user", content: message});
            
            var assistantDiv = addMessage("assistant", '<span class="spinner"></span> Thinking...');
            var contentDiv = assistantDiv.querySelector(".content");
            var startTime = performance.now();
            
            fetch("/chat", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ messages: chatHistory, model: currentModel })
            })
            .then(function(r) { return r.body.getReader(); })
            .then(function(reader) {
                var decoder = new TextDecoder();
                var fullResponse = "";
                function read() {
                    reader.read().then(function(chunk) {
                        if (chunk.done) {
                            chatHistory.push({role: "assistant", content: fullResponse});
                            var duration = ((performance.now() - startTime) / 1000).toFixed(2);
                            document.getElementById("chatTimer").textContent = "Generated in " + duration + "s";
                            document.getElementById("sendBtn").disabled = false;
                            document.getElementById("userInput").focus();
                            return;
                        }
                        fullResponse += decoder.decode(chunk.value);
                        contentDiv.innerHTML = fullResponse;
                        document.getElementById("chatContainer").scrollTop = document.getElementById("chatContainer").scrollHeight;
                        read();
                    });
                }
                read();
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
</body>
</html>'''

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/logos/<path:filename>')
def serve_logos(filename):
    filepath = os.path.join(SCRIPT_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            content = f.read()
        if filename.endswith('.avif'):
            mimetype = 'image/avif'
        elif filename.endswith('.webp'):
            mimetype = 'image/webp'
        else:
            mimetype = 'image/png'
        return Response(content, mimetype=mimetype)
    return "Not found", 404

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        text = extract_text(filepath)
        try:
            os.remove(filepath)
        except:
            pass
        if text.startswith("Error"):
            return jsonify({'success': False, 'error': text})
        return jsonify({'success': True, 'text': text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json
    text = data.get('text', '')
    prompt = data.get('prompt', 'Summarize this document:')
    model = data.get('model', DEFAULT_MODEL)
    
    max_chars = 6000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Document truncated due to length...]"
    
    def generate():
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful document analysis assistant."},
                    {"role": "user", "content": f"{prompt}\n\n---\n\n{text}"}
                ],
                stream=True,
                max_tokens=1024,
                temperature=0.5
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"Error: {str(e)}"
    
    return Response(generate(), mimetype='text/plain')

@app.route('/ask-doc', methods=['POST'])
def ask_about_doc():
    data = request.json
    text = data.get('text', '')
    question = data.get('question', '')
    model = data.get('model', DEFAULT_MODEL)
    
    max_chars = 5000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Document truncated...]"
    
    def generate():
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Answer questions about the provided document accurately."},
                    {"role": "user", "content": f"Document:\n{text}\n\nQuestion: {question}"}
                ],
                stream=True,
                max_tokens=512,
                temperature=0.5
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"Error: {str(e)}"
    
    return Response(generate(), mimetype='text/plain')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    messages = data.get('messages', [])
    model = data.get('model', DEFAULT_MODEL)
    
    def generate():
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": "You are a helpful AI assistant running locally on an NPU. Be concise and friendly."}] + messages,
                stream=True,
                max_tokens=512,
                temperature=0.7
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"Error: {str(e)}"
    
    return Response(generate(), mimetype='text/plain')

@app.route('/analyze-id', methods=['POST'])
def analyze_id():
    data = request.json
    ocr_text = data.get('ocr_text', '')
    model = data.get('model', DEFAULT_MODEL)
    
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
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an ID verification assistant. Always respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=512,
            temperature=0.3
        )
        
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

if __name__ == '__main__':
    print("\n" + "="*50)
    print("Local NPU AI Assistant (Intel Edition)")
    print("  Document Analysis + Chat + ID Verification")
    print("="*50)
    print(f"Default Model: {DEFAULT_MODEL}")
    print("")
    print("Features:")
    print("  - Document Analysis (PDF, DOCX, TXT)")
    print("  - AI Chat")
    print("  - ID Verification (Camera + OCR + AI)")
    print("")
    print("All processing happens 100% locally on your device.")
    print("")
    print("Open http://localhost:5000 in your browser")
    print("="*50 + "\n")
    app.run(debug=True, port=5000, use_reloader=False)
