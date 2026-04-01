# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for NPU Demo Flask App
# Build with: pyinstaller npu-demo.spec

import os
import sys

block_cipher = None
app_dir = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(app_dir, 'npu_demo_flask.py')],
    pathex=[app_dir],
    binaries=[],
    datas=[
        (os.path.join(app_dir, 'demo_data'), 'demo_data'),
        (os.path.join(app_dir, 'tesseract'), 'tesseract'),
        # Include logo files
        (os.path.join(app_dir, 'surface-logo.png'), '.'),
        (os.path.join(app_dir, 'copilot-logo.avif'), '.'),
        (os.path.join(app_dir, 'flagstar-logo-official.png'), '.'),
    ],
    hiddenimports=[
        'flask',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.debug',
        'jinja2',
        'markupsafe',
        'openai',
        'openai.resources',
        'openai._client',
        'pypdf',
        'PyPDF2',
        'docx',
        'requests',
        'foundry_local',
        'email',
        'email.mime',
        'email.mime.text',
        'csv',
        'hashlib',
        'platform',
        'subprocess',
        'threading',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'torch',
        'tensorflow',
        'pytest',
        'unittest',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='npu-demo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='npu-demo',
)
