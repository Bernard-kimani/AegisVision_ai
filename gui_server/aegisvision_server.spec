# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification file for AegisVision AI Trading Server
Creates a standalone executable with all necessary dependencies
"""

import os
import sys
from pathlib import Path

# Get the current directory
block_cipher = None
current_dir = os.path.dirname(os.path.abspath(SPEC))

# Define paths
server_dir = os.path.join(current_dir, 'server')
storage_dir = os.path.join(current_dir, 'storage')
assets_dir = os.path.join(current_dir, 'assets')
config_dir = os.path.join(current_dir, 'config')
frontend_dist_dir = os.path.join(current_dir, 'frontend', 'dist')

# Data files to include
datas = [
    # Server modules
    (server_dir, 'server'),
    # Storage interfaces (PromptStore/TemplateImageStore local implementations)
    (storage_dir, 'storage'),
    # Default config
    (config_dir, 'config'),
]
# Assets (icons, etc.) - optional, only bundle if the directory actually exists
if os.path.isdir(assets_dir):
    datas.append((assets_dir, 'assets'))

# React frontend build output - NOT optional. main.py's frontend_url() loads
# frontend/dist/index.html when frozen; a build with no compiled frontend is
# a broken build, not a build with a missing extra. Run `npm run build`
# inside frontend/ (or let build_exe.bat do it) before building this spec.
if not os.path.isdir(frontend_dist_dir):
    raise SystemExit(
        "frontend/dist not found - run 'npm install && npm run build' inside "
        "gui_server/frontend/ before building this spec (build_exe.bat does this automatically)."
    )
datas.append((frontend_dist_dir, 'frontend/dist'))

# NOTE: templates_store/ and storage_data/ (audit log, saved prompts, uploaded
# template images) are deliberately NOT bundled here - they are the user's
# persistent runtime data, created next to the .exe on first run (see
# app_paths.get_app_root()), not read-only assets shipped inside the build.

# Hidden imports - modules that PyInstaller might miss
hiddenimports = [
    # App-level
    'app_paths',
    'active_strategy',
    'webview_api',

    # Desktop shell (embeds frontend/dist in a native window)
    'webview',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'clr_loader',
    'pythonnet',

    # Server modules
    'server.trading_server',
    'server.settings',
    'server.data.models',
    'server.data.sliding_window',
    'server.data.preprocessor',
    'server.utils.chart_generator',
    'server.news_fetcher',
    'server.agents.ingestor',
    'server.agents.vision_compliance',
    'server.agents.guardrail',
    'server.llm',
    'server.llm.base',
    'server.llm.gemini_provider',
    'server.llm.openai_provider',
    'server.llm.anthropic_provider',
    'server.audit.audit_log',

    # Storage interfaces
    'storage.prompt_store',
    'storage.template_image_store',
    'storage.template_compositor',
    'storage.active_strategy_store',
    'storage.supabase_sync',

    # Flask and dependencies
    'flask',
    'flask_cors',
    'werkzeug',
    'werkzeug.serving',
    'werkzeug.utils',
    'werkzeug.exceptions',
    'jinja2',
    'jinja2.ext',
    'markupsafe',

    # tkinter.messagebox: main.py's startup-failure error dialog fallback only
    # - not a GUI framework here, just a last-resort crash dialog.
    'tkinter',
    'tkinter.messagebox',
    # PIL: server-side template compositing (storage/template_compositor.py)
    # still runs regardless of GUI framework.
    'PIL',
    'PIL.Image',

    # Cryptography
    'cryptography',
    'cryptography.fernet',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.primitives.hashes',
    'cryptography.hazmat.primitives.kdf.pbkdf2',

    # Config / secrets
    'pydantic_settings',
    'dotenv',

    # HTTP requests
    'requests',
    'urllib3',
    'certifi',

    # Chart rendering (chart_generator.py needs these at runtime, not just for backtesting)
    'pandas',
    'numpy',
    'matplotlib',
    'matplotlib.backends.backend_agg',
    'mplfinance',
    'bs4',  # news_fetcher.py

    # Standard library modules that might be missed
    'threading',
    'json',
    'logging',
    'datetime',
    'base64',
    'getpass',
    'signal',
    'subprocess',
]

# Modules to exclude (reduce size).
# NOTE: numpy/pandas/matplotlib/PIL are NOT excluded - chart_generator.py
# (live chart rendering for every /analyze call) and template_tab.py (image
# previews) need them at runtime. Excluding them here previously would have
# made the packaged .exe crash the moment it tried to generate its first chart.
excludes = [
    # Development tools
    'pytest',
    'unittest',
    'doctest',
    'pdb',
    'pydoc',
    'profile',
    'cProfile',

    # Not needed GUI toolkits
    'PyQt5',
    'PyQt6',
    'PySide2',
    'PySide6',
    'wx',

    # Not needed scientific/ML libraries (we use pandas/numpy/matplotlib, not these)
    'scipy',
    'sklearn',
    'jupyter',
    'ipython',
    'cv2',
    'tensorflow',
    'torch',
    'keras',
]

# Analysis configuration
a = Analysis(
    ['main.py'],
    pathex=[current_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remove duplicate files
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Create executable
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AegisVision_AI_Server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compress executable
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True for debugging, False for release
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(assets_dir, 'icon.ico') if os.path.exists(os.path.join(assets_dir, 'icon.ico')) else None,
    version_file=None,  # Could add version info here
)

# Optional: Create a collection (for debug versions with separate files)
# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     name='AegisVision_AI_Server_Debug'
# )