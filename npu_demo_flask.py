"""
Local NPU AI Assistant Demo
Document Analysis + Chat
Runs entirely on-device using Foundry Local + Snapdragon NPU
"""

import os
import time
from flask import Flask, render_template_string, request, Response, jsonify, send_from_directory
from openai import OpenAI
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')

# Create uploads folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Foundry Local OpenAI-compatible endpoint
client = OpenAI(
    base_url="http://localhost:5272/v1",
    api_key="not-needed"
)

# Available models
MODELS = {
    "phi-silica": "Phi Silica (Windows AI)",
    "phi-3.5-mini-instruct-qnn-npu:1": "Phi 3.5 Mini (NPU)",
    "qnn-deepseek-r1-distill-qwen-1.5b": "Deepseek R1 1.5B",
    "Phi-4-reasoning-14.7b-qnn": "Phi 4 Reasoning 14.7B"
}

DEFAULT_MODEL = "phi-silica"

def extract_text_from_pdf(filepath):
    """Extract text from PDF file"""
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
    """Extract text from Word document"""
    try:
        from docx import Document
        doc = Document(filepath)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text.strip()
    except Exception as e:
        return f"Error reading DOCX: {str(e)}"

def extract_text_from_txt(filepath):
    """Extract text from plain text file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        return f"Error reading TXT: {str(e)}"

def extract_text(filepath):
    """Extract text based on file extension"""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        return extract_text_from_pdf(filepath)
    elif ext == '.docx':
        return extract_text_from_docx(filepath)
    elif ext in ['.txt', '.md']:
        return extract_text_from_txt(filepath)
    else:
        return "Unsupported file type"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Local NPU AI Assistant</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            text-align: center;
            padding: 20px 0;
        }
        
        /* Logo section */
        .logos {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 35px;
            margin-bottom: 20px;
        }
        .logos img.surface-logo {
            height: 75px;
            width: auto;
            object-fit: contain;
        }
        .logos img.copilot-logo {
            height: 55px;
            width: auto;
            object-fit: contain;
        }
        .logo-divider {
            width: 2px;
            height: 60px;
            background: rgba(255,255,255,0.3);
        }
        
        h1 {
            font-size: 2.2em;
            margin-bottom: 10px;
        }
        .subtitle {
            color: #00BCF2;
            font-size: 1.1em;
        }
        .badge {
            display: inline-block;
            background: linear-gradient(90deg, #0078D4, #00BCF2);
            padding: 8px 16px;
            border-radius: 25px;
            font-weight: bold;
            margin: 15px 5px;
            font-size: 0.9em;
        }
        
        /* Offline indicator */
        .offline-badge {
            display: inline-block;
            background: linear-gradient(90deg, #107C10, #00CC6A);
            padding: 8px 16px;
            border-radius: 25px;
            font-weight: bold;
            margin: 15px 5px;
            font-size: 0.9em;
            animation: pulse 2s infinite;
        }
        .offline-badge.offline {
            background: linear-gradient(90deg, #FF8C00, #FFB900);
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.8; }
        }
        
        /* Model selector */
        .model-selector {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
            margin: 15px 0;
        }
        .model-selector label {
            font-size: 0.9em;
            opacity: 0.8;
        }
        .model-selector select {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.3);
            color: #fff;
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            cursor: pointer;
        }
        .model-selector select:focus {
            outline: 2px solid #00BCF2;
        }
        .model-selector select option {
            background: #1a1a2e;
            color: #fff;
        }
        
        /* Response timer */
        .response-timer {
            text-align: center;
            font-size: 0.85em;
            color: #00BCF2;
            margin-top: 10px;
            opacity: 0.9;
        }
        
        /* Tabs */
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .tab-btn {
            flex: 1;
            padding: 15px;
            background: rgba(255,255,255,0.1);
            border: 2px solid transparent;
            color: #fff;
            border-radius: 10px;
            cursor: pointer;
            font-size: 1em;
            transition: all 0.2s;
        }
        .tab-btn:hover {
            background: rgba(0,188,242,0.2);
        }
        .tab-btn.active {
            border-color: #00BCF2;
            background: rgba(0,188,242,0.3);
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        
        /* Document Upload Section */
        .upload-area {
            background: rgba(255,255,255,0.05);
            border: 2px dashed rgba(255,255,255,0.3);
            border-radius: 15px;
            padding: 40px;
            text-align: center;
            margin-bottom: 20px;
            transition: all 0.2s;
        }
        .upload-area:hover {
            border-color: #00BCF2;
            background: rgba(0,188,242,0.1);
        }
        .upload-area.dragover {
            border-color: #00BCF2;
            background: rgba(0,188,242,0.2);
        }
        #fileInput {
            display: none;
        }
        .upload-btn {
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
        .upload-btn:hover {
            transform: scale(1.05);
        }
        .file-info {
            background: rgba(0,188,242,0.2);
            padding: 15px;
            border-radius: 10px;
            margin: 15px 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .file-stats {
            font-size: 0.85em;
            opacity: 0.8;
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
        .summary-result h3 {
            color: #00BCF2;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .copy-btn {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.3);
            color: #fff;
            padding: 5px 12px;
            border-radius: 15px;
            cursor: pointer;
            font-size: 0.8em;
        }
        .copy-btn:hover {
            background: rgba(0,188,242,0.3);
        }
        .action-buttons {
            display: flex;
            gap: 10px;
            margin-top: 15px;
            flex-wrap: wrap;
        }
        .action-btn {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.3);
            color: #fff;
            padding: 10px 20px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .action-btn:hover {
            background: rgba(0,188,242,0.3);
            border-color: #00BCF2;
        }
        .action-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .action-btn.primary {
            background: linear-gradient(90deg, #0078D4, #00BCF2);
            border: none;
        }
        
        /* Document Q&A Section */
        .doc-qa-section {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }
        .doc-qa-section h4 {
            color: #00BCF2;
            margin-bottom: 10px;
        }
        .doc-input-area {
            display: flex;
            gap: 10px;
        }
        .doc-input-area input {
            flex: 1;
            padding: 12px 15px;
            border-radius: 10px;
            border: none;
            background: rgba(255,255,255,0.1);
            color: #fff;
            font-size: 0.95em;
        }
        .doc-input-area input:focus {
            outline: 2px solid #00BCF2;
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
        
        /* Chat Section */
        .chat-container {
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            min-height: 400px;
            max-height: 500px;
            overflow-y: auto;
        }
        .message {
            margin: 15px 0;
            padding: 15px;
            border-radius: 10px;
            animation: fadeIn 0.3s ease;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .user-msg {
            background: #0078D4;
            margin-left: 50px;
        }
        .assistant-msg {
            background: rgba(255,255,255,0.1);
            margin-right: 50px;
        }
        .role {
            font-size: 0.8em;
            opacity: 0.7;
            margin-bottom: 5px;
        }
        .quick-prompts {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        .quick-btn {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            color: #fff;
            padding: 10px 15px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .quick-btn:hover {
            background: rgba(0,188,242,0.3);
            border-color: #00BCF2;
        }
        .input-area {
            display: flex;
            gap: 10px;
        }
        #userInput {
            flex: 1;
            padding: 15px;
            border-radius: 10px;
            border: none;
            background: rgba(255,255,255,0.1);
            color: #fff;
            font-size: 1em;
        }
        #userInput:focus {
            outline: 2px solid #00BCF2;
        }
        #sendBtn {
            background: linear-gradient(90deg, #0078D4, #00BCF2);
            border: none;
            color: #fff;
            padding: 15px 30px;
            border-radius: 10px;
            cursor: pointer;
            font-weight: bold;
            font-size: 1em;
        }
        #sendBtn:hover {
            transform: scale(1.05);
        }
        #sendBtn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .typing::after {
            content: '▋';
            animation: blink 1s infinite;
        }
        @keyframes blink {
            50% { opacity: 0; }
        }
        
        /* Loading spinner */
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
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        footer {
            text-align: center;
            padding: 20px;
            opacity: 0.6;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <!-- Logos -->
            <div class="logos">
                <img class="surface-logo" src="/logos/surface-logo.png" alt="Microsoft Surface" onerror="this.style.display='none'">
                <div class="logo-divider"></div>
                <img class="copilot-logo" src="/logos/copilot-logo.avif" alt="Copilot+ PC" onerror="this.style.display='none'">
            </div>
            
            <h1>🚀 Local NPU AI Assistant</h1>
            <div class="subtitle">Document Analysis & Chat — 100% On-Device</div>
            
            <div>
                <span class="badge">⚡ Powered by NPU</span>
                <span class="offline-badge" id="offlineBadge">🌐 Online</span>
            </div>
            
            <!-- Model Selector -->
            <div class="model-selector">
                <label for="modelSelect">Model:</label>
                <select id="modelSelect" onchange="updateModel()">
                    <option value="phi-silica">Phi Silica (Windows AI)</option>
                    <option value="phi-3.5-mini-instruct-qnn-npu:1">Phi 3.5 Mini (NPU)</option>
                    <option value="qnn-deepseek-r1-distill-qwen-1.5b">Deepseek R1 1.5B</option>
                    <option value="Phi-4-reasoning-14.7b-qnn">Phi 4 Reasoning 14.7B</option>
                </select>
            </div>
        </header>

        <div class="tabs">
            <button class="tab-btn active" onclick="showTab('documents')">📄 Document Analysis</button>
            <button class="tab-btn" onclick="showTab('chat')">💬 Chat</button>
        </div>

        <!-- Document Analysis Tab -->
        <div id="documents-tab" class="tab-content active">
            <div class="upload-area" id="uploadArea">
                <div style="font-size: 3em; margin-bottom: 15px;">📁</div>
                <div style="font-size: 1.2em; margin-bottom: 10px;">Drop your document here or click to browse</div>
                <div style="opacity: 0.7;">Supports PDF, DOCX, TXT files • Max 16MB</div>
                <input type="file" id="fileInput" accept=".pdf,.docx,.txt,.md" onchange="handleFileSelect(event)">
                <button class="upload-btn" type="button" onclick="document.getElementById('fileInput').click();">Select File</button>
            </div>

            <div id="fileInfo" class="file-info" style="display: none;">
                <div>
                    <strong>📄 <span id="fileName"></span></strong>
                    <span style="opacity: 0.7; margin-left: 15px;"><span id="fileSize"></span></span>
                </div>
                <div class="file-stats">
                    <span id="wordCount"></span> words • <span id="charCount"></span> chars
                </div>
            </div>

            <div id="documentPreview" class="document-preview" style="display: none;"></div>

            <div class="action-buttons">
                <button class="action-btn" id="summarizeBtn" onclick="analyzeDocument('summarize')" disabled>📝 Summarize</button>
                <button class="action-btn" id="keyPointsBtn" onclick="analyzeDocument('keypoints')" disabled>🎯 Key Points</button>
                <button class="action-btn" id="questionsBtn" onclick="analyzeDocument('questions')" disabled>❓ Generate Questions</button>
                <button class="action-btn" id="simplifyBtn" onclick="analyzeDocument('simplify')" disabled>💡 Simplify</button>
            </div>

            <div id="summaryResult" class="summary-result" style="display: none;">
                <h3>
                    <span>📋 Analysis Result</span>
                    <button class="copy-btn" onclick="copyResult()">📋 Copy</button>
                </h3>
                <div id="summaryContent"></div>
                <div id="analysisTimer" class="response-timer"></div>
            </div>
            
            <!-- Ask About Document Section -->
            <div id="docQaSection" class="doc-qa-section" style="display: none;">
                <h4>💬 Ask About This Document</h4>
                <div class="doc-input-area">
                    <input type="text" id="docQuestion" placeholder="Ask a question about the document..." onkeypress="if(event.key==='Enter')askAboutDoc()">
                    <button onclick="askAboutDoc()">Ask</button>
                </div>
                <div id="docAnswer" class="summary-result" style="display: none; margin-top: 15px;">
                    <h3><span>💡 Answer</span></h3>
                    <div id="docAnswerContent"></div>
                    <div id="docAnswerTimer" class="response-timer"></div>
                </div>
            </div>
        </div>

        <!-- Chat Tab -->
        <div id="chat-tab" class="tab-content">
            <div class="quick-prompts">
                <button class="quick-btn" onclick="setPrompt('summarize')">📝 Summarize</button>
                <button class="quick-btn" onclick="setPrompt('email')">✉️ Draft Email</button>
                <button class="quick-btn" onclick="setPrompt('explain')">💡 Explain</button>
                <button class="quick-btn" onclick="clearChat()">🗑️ Clear</button>
            </div>

            <div class="chat-container" id="chatContainer">
                <div class="message assistant-msg">
                    <div class="role">Assistant</div>
                    <div>Hello! I'm running locally on your Snapdragon X NPU. How can I help you today?</div>
                </div>
            </div>

            <div class="input-area">
                <input type="text" id="userInput" placeholder="Type your message here..." onkeypress="if(event.key==='Enter')sendMessage()">
                <button id="sendBtn" onclick="sendMessage()">Send</button>
            </div>
            
            <div id="chatTimer" class="response-timer"></div>
        </div>

        <footer>
            Microsoft Surface + Copilot+ PC • Phi Silica on Snapdragon X NPU • All processing happens locally
        </footer>
    </div>

    <script>
        let documentText = '';
        let chatHistory = [];
        let currentModel = 'phi-silica';
        
        // Check online/offline status
        function updateOnlineStatus() {
            const badge = document.getElementById('offlineBadge');
            if (navigator.onLine) {
                badge.textContent = '🌐 Online';
                badge.classList.remove('offline');
            } else {
                badge.textContent = '✈️ Offline Mode';
                badge.classList.add('offline');
            }
        }
        
        window.addEventListener('online', updateOnlineStatus);
        window.addEventListener('offline', updateOnlineStatus);
        updateOnlineStatus();
        
        // Model selector
        function updateModel() {
            currentModel = document.getElementById('modelSelect').value;
            console.log('Model changed to:', currentModel);
        }

        // Tab switching
        function showTab(tab) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById(tab + '-tab').classList.add('active');
        }

        // File handling
        const uploadArea = document.getElementById('uploadArea');
        
        uploadArea.addEventListener('click', (e) => {
            if (e.target === uploadArea || e.target.tagName === 'DIV') {
                document.getElementById('fileInput').click();
            }
        });
        
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFile(files[0]);
            }
        });

        function handleFileSelect(event) {
            const file = event.target.files[0];
            if (file) {
                handleFile(file);
            }
        }

        function handleFile(file) {
            console.log('Uploading file:', file.name);
            document.getElementById('fileName').textContent = file.name;
            document.getElementById('fileSize').textContent = formatFileSize(file.size);
            document.getElementById('fileInfo').style.display = 'flex';
            
            // Upload file
            const formData = new FormData();
            formData.append('file', file);
            
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Server returned ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    documentText = data.text;
                    
                    // Update word/char counts
                    const words = documentText.split(/\\s+/).filter(w => w.length > 0).length;
                    const chars = documentText.length;
                    document.getElementById('wordCount').textContent = words.toLocaleString();
                    document.getElementById('charCount').textContent = chars.toLocaleString();
                    
                    // Show preview (first 500 chars)
                    const preview = documentText.length > 500 
                        ? documentText.substring(0, 500) + '...' 
                        : documentText;
                    document.getElementById('documentPreview').textContent = preview;
                    document.getElementById('documentPreview').style.display = 'block';
                    
                    // Enable buttons
                    document.getElementById('summarizeBtn').disabled = false;
                    document.getElementById('keyPointsBtn').disabled = false;
                    document.getElementById('questionsBtn').disabled = false;
                    document.getElementById('simplifyBtn').disabled = false;
                    
                    // Show Q&A section
                    document.getElementById('docQaSection').style.display = 'block';
                } else {
                    alert('Error: ' + data.error);
                }
            })
            .catch(error => {
                console.error('Upload error:', error);
                alert('Upload failed: ' + error.message);
            });
        }

        function formatFileSize(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        }
        
        function copyResult() {
            const content = document.getElementById('summaryContent').innerText;
            navigator.clipboard.writeText(content).then(() => {
                const btn = event.target;
                const originalText = btn.textContent;
                btn.textContent = '✓ Copied!';
                setTimeout(() => btn.textContent = originalText, 2000);
            });
        }

        async function analyzeDocument(type) {
            const prompts = {
                summarize: "Please provide a concise summary of this document in 3-4 paragraphs:",
                keypoints: "Extract the 5 most important key points from this document as a bullet list:",
                questions: "Generate 5 thoughtful questions that could be asked about this document:",
                simplify: "Explain the main ideas of this document in simple, easy-to-understand language:"
            };
            
            const resultDiv = document.getElementById('summaryResult');
            const contentDiv = document.getElementById('summaryContent');
            const timerDiv = document.getElementById('analysisTimer');
            
            resultDiv.style.display = 'block';
            contentDiv.innerHTML = '<span class="spinner"></span> Analyzing document...';
            timerDiv.textContent = '';
            
            // Disable buttons during processing
            document.querySelectorAll('.action-btn').forEach(btn => btn.disabled = true);
            
            const startTime = performance.now();
            
            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        text: documentText,
                        prompt: prompts[type],
                        model: currentModel
                    })
                });
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let result = '';
                
                while (true) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    result += chunk;
                    contentDiv.innerHTML = result;
                }
                
                const endTime = performance.now();
                const duration = ((endTime - startTime) / 1000).toFixed(2);
                timerDiv.textContent = `⚡ Generated in ${duration}s using ${currentModel}`;
                
            } catch (error) {
                contentDiv.innerHTML = `<span style="color:#ff6b6b">Error: ${error.message}</span>`;
            }
            
            // Re-enable buttons
            document.querySelectorAll('.action-btn').forEach(btn => btn.disabled = false);
        }
        
        // Ask about document
        async function askAboutDoc() {
            const question = document.getElementById('docQuestion').value.trim();
            if (!question || !documentText) return;
            
            const answerDiv = document.getElementById('docAnswer');
            const contentDiv = document.getElementById('docAnswerContent');
            const timerDiv = document.getElementById('docAnswerTimer');
            
            answerDiv.style.display = 'block';
            contentDiv.innerHTML = '<span class="spinner"></span> Thinking...';
            timerDiv.textContent = '';
            
            const startTime = performance.now();
            
            try {
                const response = await fetch('/ask-doc', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        text: documentText,
                        question: question,
                        model: currentModel
                    })
                });
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let result = '';
                
                while (true) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    result += chunk;
                    contentDiv.innerHTML = result;
                }
                
                const endTime = performance.now();
                const duration = ((endTime - startTime) / 1000).toFixed(2);
                timerDiv.textContent = `⚡ Generated in ${duration}s`;
                
            } catch (error) {
                contentDiv.innerHTML = `<span style="color:#ff6b6b">Error: ${error.message}</span>`;
            }
            
            document.getElementById('docQuestion').value = '';
        }

        // Chat functions
        const chatPrompts = {
            summarize: "Please summarize the following in 2-3 bullet points:\\n\\n",
            email: "Draft a professional email based on the following:\\n\\n",
            explain: "Explain this concept in simple terms:\\n\\n"
        };

        function setPrompt(type) {
            document.getElementById('userInput').value = chatPrompts[type];
            document.getElementById('userInput').focus();
        }

        function clearChat() {
            chatHistory = [];
            document.getElementById('chatContainer').innerHTML = `
                <div class="message assistant-msg">
                    <div class="role">Assistant</div>
                    <div>Hello! I'm running locally on your Snapdragon X NPU. How can I help you today?</div>
                </div>
            `;
            document.getElementById('chatTimer').textContent = '';
        }

        function addMessage(role, content) {
            const container = document.getElementById('chatContainer');
            const msgClass = role === 'user' ? 'user-msg' : 'assistant-msg';
            const roleLabel = role === 'user' ? 'You' : 'Assistant';
            
            const div = document.createElement('div');
            div.className = `message ${msgClass}`;
            div.innerHTML = `<div class="role">${roleLabel}</div><div class="content">${content}</div>`;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
            return div;
        }

        async function sendMessage() {
            const input = document.getElementById('userInput');
            const btn = document.getElementById('sendBtn');
            const timerDiv = document.getElementById('chatTimer');
            const message = input.value.trim();
            
            if (!message) return;
            
            input.value = '';
            btn.disabled = true;
            timerDiv.textContent = '';
            
            addMessage('user', message);
            chatHistory.push({role: 'user', content: message});
            
            const assistantDiv = addMessage('assistant', '<span class="typing">Thinking</span>');
            const contentDiv = assistantDiv.querySelector('.content');
            
            const startTime = performance.now();
            
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        messages: chatHistory,
                        model: currentModel
                    })
                });
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';
                
                while (true) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    fullResponse += chunk;
                    contentDiv.innerHTML = fullResponse;
                    document.getElementById('chatContainer').scrollTop = 
                        document.getElementById('chatContainer').scrollHeight;
                }
                
                chatHistory.push({role: 'assistant', content: fullResponse});
                
                const endTime = performance.now();
                const duration = ((endTime - startTime) / 1000).toFixed(2);
                timerDiv.textContent = `⚡ Generated in ${duration}s using ${currentModel}`;
                
            } catch (error) {
                contentDiv.innerHTML = `<span style="color:#ff6b6b">Error: ${error.message}</span>`;
            }
            
            btn.disabled = false;
            input.focus();
        }
    </script>
</body>
</html>
"""

# Serve logo files
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/logos/<path:filename>')
def serve_logos(filename):
    filepath = os.path.join(SCRIPT_DIR, filename)
    print(f"Trying to serve: {filepath}")
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            content = f.read()
        # Determine mimetype
        if filename.endswith('.avif'):
            mimetype = 'image/avif'
        elif filename.endswith('.webp'):
            mimetype = 'image/webp'
        else:
            mimetype = 'image/png'
        return Response(content, mimetype=mimetype)
    else:
        print(f"NOT FOUND: {filepath}")
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
        
        # Extract text
        text = extract_text(filepath)
        
        # Clean up uploaded file
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
    
    # Truncate text if too long (model context limits)
    max_chars = 6000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Document truncated due to length...]"
    
    def generate():
        try:
            system_msg = {
                "role": "system",
                "content": "You are a helpful document analysis assistant. Provide clear, well-structured analysis."
            }
            user_msg = {
                "role": "user",
                "content": f"{prompt}\n\n---\n\n{text}"
            }
            
            stream = client.chat.completions.create(
                model=model,
                messages=[system_msg, user_msg],
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
    
    # Truncate text if too long
    max_chars = 5000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Document truncated...]"
    
    def generate():
        try:
            system_msg = {
                "role": "system",
                "content": "You are a helpful assistant. Answer questions about the provided document accurately and concisely."
            }
            user_msg = {
                "role": "user",
                "content": f"Based on this document:\n\n---\n{text}\n---\n\nQuestion: {question}"
            }
            
            stream = client.chat.completions.create(
                model=model,
                messages=[system_msg, user_msg],
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
            system_msg = {
                "role": "system",
                "content": "You are a helpful AI assistant running locally on an NPU. Be concise and friendly."
            }
            
            stream = client.chat.completions.create(
                model=model,
                messages=[system_msg] + messages,
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

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 Local NPU AI Assistant")
    print("   Document Analysis + Chat")
    print("="*50)
    print(f"Default Model: {DEFAULT_MODEL}")
    print("Available Models:", list(MODELS.keys()))
    print("")
    print(f"Script directory: {SCRIPT_DIR}")
    print("Logo files expected:")
    for logo in ['surface-logo.png', 'copilot-logo.avif']:
        path = os.path.join(SCRIPT_DIR, logo)
        status = "✓ Found" if os.path.exists(path) else "✗ Missing"
        print(f"  - {logo}: {status}")
    print("")
    print("Open http://localhost:5000 in your browser")
    print("="*50 + "\n")
    app.run(debug=True, port=5000, use_reloader=False)
