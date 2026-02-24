# -*- mode: python ; coding: utf-8 -*-
"""
dejaview.spec — PyInstaller build specification (plan §Phase 7).

Build command:
    cd dejaview
    pyinstaller dejaview.spec

Output:  dist/DejaView/  (one-folder bundle)
"""

import os
import sys
from pathlib import Path

# Locate Qt Hungarian translation from the PyQt6 installation.
import PyQt6
_pyqt6_dir = Path(PyQt6.__file__).parent
_qt_translations = _pyqt6_dir / "Qt6" / "translations"
_qt_hu_qm = _qt_translations / "qt_hu.qm"
if not _qt_hu_qm.exists():
    print(f"WARNING: qt_hu.qm not found at {_qt_hu_qm}")

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # App Hungarian translation (compiled .qm)
        ('resources/i18n/app_hu.qm', 'resources/i18n'),
        # Qt base Hungarian translation (standard button labels, dialogs)
        (str(_qt_hu_qm), 'resources/i18n'),
        # User guide files (Feature Request 1 — Help Menu)
        ('resources/help/USER_GUIDE.md', 'resources/help'),
        ('resources/help/USER_GUIDE_HU.md', 'resources/help'),
        # Google OAuth2 client secrets (bundled per plan §Security)
        # Uncomment when client_secrets.json is created:
        ('resources/client_secrets.json', 'resources'),
    ],
    hiddenimports=[
        'PyQt6.sip',
        'google.auth.transport.requests',
        'google_auth_oauthlib.flow',
        'googleapiclient.discovery',
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
        'IPython',
        'jupyter',
        'pytest',
        'pytest_qt',
        'pytest_cov',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DejaView',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app — no console window
    disable_windowed_traceback=False,
    # Uncomment when an .ico file is added to resources/icons/:
    # icon='resources/icons/dejaview.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DejaView',
)
