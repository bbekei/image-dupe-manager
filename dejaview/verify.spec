# -*- mode: python ; coding: utf-8 -*-
"""
verify.spec — PyInstaller build spec for the Deletion Verifier tool.

Build command:
    cd dejaview
    pyinstaller verify.spec --noconfirm

Output:  dist/DejaViewVerify/  (one-folder bundle)
"""

block_cipher = None

a = Analysis(
    ['verify_main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Bundle the verification logic module alongside the exe.
        ('tests/e2e/verify_deletions.py', '.'),
    ],
    hiddenimports=[
        'PyQt6.sip',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'pandas',
        'scipy',
        'IPython',
        'jupyter',
        'pytest',
        'pytest_qt',
        'pytest_cov',
        # Exclude the main app modules not needed by the verifier.
        'google',
        'googleapiclient',
        'google_auth_oauthlib',
        'google_auth_httplib2',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DejaViewVerify',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app — no console window
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DejaViewVerify',
)
