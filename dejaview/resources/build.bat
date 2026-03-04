@echo off
REM build.bat — Build DejaView EXE and installer in one step.
REM
REM Usage:  cd dejaview
REM         resources\build.bat
REM
REM Prerequisites:
REM   - PyInstaller        (pip install pyinstaller)
REM   - Inno Setup 6       (https://jrsoftware.org/isinfo.php)
REM
REM Output:
REM   dist\DejaView\DejaView.exe
REM   dist\DejaViewVerify\DejaViewVerify.exe
REM   installer\DejaView_Setup.exe
REM   build\build.log            (warnings and errors only)

setlocal

REM Resolve project root (parent of resources\)
set "PROJECT_DIR=%~dp0.."
pushd "%PROJECT_DIR%"

REM Initialize the log file (warnings and errors only).
set "BUILD_LOG=build\build.log"
if not exist "build" mkdir build
echo Build started: %DATE% %TIME% > "%BUILD_LOG%"
echo. >> "%BUILD_LOG%"

set "STEP_LOG=build\_step.tmp"

echo ============================================================
echo  Step 1/3: Building DejaView EXE with PyInstaller
echo ============================================================
pyinstaller dejaview.spec --noconfirm > "%STEP_LOG%" 2>&1
if errorlevel 1 (
    echo STEP 1 FAILED: PyInstaller - DejaView >> "%BUILD_LOG%"
    findstr /I "WARNING ERROR FATAL" "%STEP_LOG%" >> "%BUILD_LOG%"
    echo.
    echo ERROR: PyInstaller build failed. See %BUILD_LOG%
    popd
    exit /b 1
)
echo [Step 1] DejaView warnings: >> "%BUILD_LOG%"
findstr /I "WARNING ERROR FATAL" "%STEP_LOG%" >> "%BUILD_LOG%"
echo. >> "%BUILD_LOG%"

REM Verify DejaView EXE exists.
if not exist "dist\DejaView\DejaView.exe" (
    echo VERIFY FAILED: dist\DejaView\DejaView.exe not found >> "%BUILD_LOG%"
    echo.
    echo ERROR: DejaView.exe was not produced by PyInstaller.
    popd
    exit /b 1
)
echo   OK: dist\DejaView\DejaView.exe

echo.
echo ============================================================
echo  Step 2/3: Building DejaViewVerify EXE with PyInstaller
echo ============================================================
pyinstaller verify.spec --noconfirm > "%STEP_LOG%" 2>&1
if errorlevel 1 (
    echo STEP 2 FAILED: PyInstaller - DejaViewVerify >> "%BUILD_LOG%"
    findstr /I "WARNING ERROR FATAL" "%STEP_LOG%" >> "%BUILD_LOG%"
    echo.
    echo ERROR: DejaViewVerify build failed. See %BUILD_LOG%
    popd
    exit /b 1
)
echo [Step 2] DejaViewVerify warnings: >> "%BUILD_LOG%"
findstr /I "WARNING ERROR FATAL" "%STEP_LOG%" >> "%BUILD_LOG%"
echo. >> "%BUILD_LOG%"

REM Verify DejaViewVerify EXE exists.
if not exist "dist\DejaViewVerify\DejaViewVerify.exe" (
    echo VERIFY FAILED: dist\DejaViewVerify\DejaViewVerify.exe not found >> "%BUILD_LOG%"
    echo.
    echo ERROR: DejaViewVerify.exe was not produced by PyInstaller.
    popd
    exit /b 1
)
echo   OK: dist\DejaViewVerify\DejaViewVerify.exe

echo.
echo ============================================================
echo  Step 3/3: Building installer with Inno Setup
echo ============================================================

REM Locate ISCC.exe — assign to a variable first to avoid
REM ProgramFiles(x86) parentheses breaking CMD if-block parsing.
set "ISCC="
set "ISCC_X86=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
set "ISCC_X64=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if exist "%ISCC_X86%" (
    set "ISCC=%ISCC_X86%"
) else if exist "%ISCC_X64%" (
    set "ISCC=%ISCC_X64%"
)

if not defined ISCC (
    echo.
    echo WARNING: Inno Setup 6 not found. EXEs were built but installer was skipped.
    echo Install from https://jrsoftware.org/isinfo.php
    echo WARNING: Inno Setup 6 not found, installer skipped >> "%BUILD_LOG%"
    del /q "%STEP_LOG%" 2>nul
    popd
    exit /b 0
)

"%ISCC%" installer.iss > "%STEP_LOG%" 2>&1
if errorlevel 1 (
    echo STEP 3 FAILED: Inno Setup >> "%BUILD_LOG%"
    findstr /I "WARNING ERROR" "%STEP_LOG%" >> "%BUILD_LOG%"
    echo.
    echo ERROR: Installer build failed. See %BUILD_LOG%
    popd
    exit /b 1
)
echo [Step 3] Installer warnings: >> "%BUILD_LOG%"
findstr /I "WARNING ERROR" "%STEP_LOG%" >> "%BUILD_LOG%"
echo. >> "%BUILD_LOG%"

REM Verify installer exists.
if not exist "installer\DejaView_Setup.exe" (
    echo VERIFY FAILED: installer\DejaView_Setup.exe not found >> "%BUILD_LOG%"
    echo.
    echo ERROR: DejaView_Setup.exe was not produced by Inno Setup.
    popd
    exit /b 1
)
echo   OK: installer\DejaView_Setup.exe

REM Clean up temp file.
del /q "%STEP_LOG%" 2>nul

echo.
echo ============================================================
echo  Build complete!
echo  EXE:       dist\DejaView\DejaView.exe
echo  Verifier:  dist\DejaViewVerify\DejaViewVerify.exe
echo  Installer: installer\DejaView_Setup.exe
echo  Log:       %BUILD_LOG%
echo ============================================================

echo. >> "%BUILD_LOG%"
echo Build completed successfully: %DATE% %TIME% >> "%BUILD_LOG%"

popd
exit /b 0
