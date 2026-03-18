# sidecar/sidecar.spec — PyInstaller spec for building dejaview-sidecar.exe
# Used by the GitHub Actions Windows runner in Step 7.
# Run from the dejaview/ directory: pyinstaller sidecar/sidecar.spec
import sys
from pathlib import Path
from PyInstaller.building.build_main import Analysis, PYZ, EXE

block_cipher = None

a = Analysis(
    ['sidecar/sidecar_main.py'],
    pathex=[str(Path.cwd())],
    binaries=[],
    datas=[
        ('resources/', 'resources/'),
        ('version.py', '.'),
    ],
    hiddenimports=[
        'backend.api',
        'core.scanner',
        'core.executor',
        'core.hasher',
        'core.perf_monitor',
        'core.selection',
        'core.similarity',
        'core.similarity_selection',
        'core.sort_chain',
        'core.trash',
        'data.compression',
        'data.db',
        'data.export',
        'data.sync',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['PyQt6', 'webview', 'pywebview'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='dejaview-sidecar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
