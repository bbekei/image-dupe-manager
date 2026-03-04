@echo off
REM build.bat — Build DejaView EXE and installer in one step.
REM
REM Usage:  cd dejaview
REM         resources\build.bat
REM
REM Prerequisites:
REM   - PyInstaller        (pip install pyinstaller)
REM   - Inno Setup 6       (https://jrsoftware.org/isinfo.php)

setlocal

REM Resolve project root (parent of resources\)
set "PROJECT_DIR=%~dp0.."
pushd "%PROJECT_DIR%"

echo ============================================================
echo  Step 1/3: Building DejaView EXE with PyInstaller
echo ============================================================
pyinstaller dejaview.spec --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed (DejaView).
    popd
    exit /b 1
)

echo.
echo ============================================================
echo  Step 2/3: Building DejaViewVerify EXE with PyInstaller
echo ============================================================
pyinstaller verify.spec --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed (DejaViewVerify).
    popd
    exit /b 1
)

echo.
echo ============================================================
echo  Step 3/3: Building installer with Inno Setup
echo ============================================================

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)

if not defined ISCC (
    echo.
    echo WARNING: Inno Setup 6 not found. EXE was built but installer was skipped.
    echo Install from https://jrsoftware.org/isinfo.php
    popd
    exit /b 0
)

"%ISCC%" installer.iss
if errorlevel 1 (
    echo.
    echo ERROR: Installer build failed.
    popd
    exit /b 1
)

echo.
echo ============================================================
echo  Build complete!
echo  EXE:       dist\DejaView\DejaView.exe
echo  Verifier:  dist\DejaViewVerify\DejaViewVerify.exe
echo  Installer: installer\DejaView_Setup.exe
echo ============================================================

popd
exit /b 0
