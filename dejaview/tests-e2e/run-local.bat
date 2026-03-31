@echo off
setlocal
REM ──────────────────────────────────────────────────────────────────────────
REM run-local.bat — Run Phase 4 local video-recorded smoke tests on Windows.
REM
REM Automatically installs all prerequisites on first run:
REM   - Node.js LTS (via winget)
REM   - Visual C++ Build Tools (via winget)
REM   - Rust / Cargo (via winget)
REM   - MSVC environment (via vcvarsall.bat)
REM   - tauri-driver (via cargo install)
REM   - npm dependencies
REM
REM Only requirement: DejaView installed at the path below.
REM
REM Usage:
REM   run-local.bat              — run all flows
REM   run-local.bat smoke        — run smoke flows only
REM   run-local.bat long         — run long-running flows only
REM   run-local.bat flow <file>  — run a specific flow YAML
REM ──────────────────────────────────────────────────────────────────────────

set DEJAVIEW_BINARY_PATH=C:\Users\bekei\AppData\Local\Programs\DejaView\app.exe

if not exist "%DEJAVIEW_BINARY_PATH%" goto err_no_binary

REM ── Check for Node.js ──────────────────────────────────────────────────
where node >nul 2>nul
if errorlevel 1 goto install_node
goto node_ok

:install_node
echo Node.js not found. Installing via winget...
winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto err_node_install
echo.
echo Node.js installed. Refreshing PATH...
set "PATH=%PATH%;C:\Program Files\nodejs"
where node >nul 2>nul
if errorlevel 1 goto err_node_path
:node_ok

REM ── Ensure .cargo\bin is on PATH ────────────────────────────────────
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"

REM ── Check for Visual C++ Build Tools ──────────────────────────────────
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" goto vsbt_ok
set "VSWHERE=%ProgramFiles%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" goto vsbt_ok
goto install_vsbt

:install_vsbt
echo Visual C++ Build Tools not found. Installing via winget...
echo This is required by Rust to compile native code.
winget install Microsoft.VisualStudio.2022.BuildTools --accept-source-agreements --accept-package-agreements --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.Windows11SDK.26100 --includeRecommended"
if errorlevel 1 goto err_vsbt_install
echo.
echo Visual C++ Build Tools installed.
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" set "VSWHERE=%ProgramFiles%\Microsoft Visual Studio\Installer\vswhere.exe"
:vsbt_ok

REM ── Check for Rust / Cargo ────────────────────────────────────────────
where cargo >nul 2>nul
if errorlevel 1 goto install_rust
goto rust_ok

:install_rust
echo Rust not found. Installing via winget...
winget install Rustlang.Rust.MSVC --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto err_rust_install
echo.
echo Rust installed. Refreshing PATH...
set "PATH=%PATH%;%USERPROFILE%\.cargo\bin"
where cargo >nul 2>nul
if errorlevel 1 goto err_rust_path
:rust_ok

REM ── Load MSVC environment (link.exe) ──────────────────────────────────
where link >nul 2>nul
if not errorlevel 1 goto msvc_env_ok
echo Loading MSVC build environment...
REM Try common Build Tools install locations directly
set "VCVARS="
if exist "%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" set "VCVARS=%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
if exist "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" set "VCVARS=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
if exist "%ProgramFiles%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" set "VCVARS=%ProgramFiles%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"
if exist "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" set "VCVARS=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"
if "%VCVARS%"=="" goto err_msvc_env
call "%VCVARS%" x64 >nul 2>nul
where link >nul 2>nul
if errorlevel 1 goto err_msvc_env_load
:msvc_env_ok

REM ── Check for tauri-driver ────────────────────────────────────────────
where tauri-driver >nul 2>nul
if errorlevel 1 goto install_tauri_driver
goto tauri_driver_ok

:install_tauri_driver
echo tauri-driver not found. Installing via cargo...
echo This may take a few minutes on first run.
call cargo install tauri-driver
if errorlevel 1 goto err_tauri_driver
:tauri_driver_ok

REM ── Install npm dependencies ───────────────────────────────────────────
REM node_modules may contain Linux-native binaries (esbuild etc.) if the
REM repo is shared between WSL and Windows. Check for the Windows esbuild
REM package; if missing, delete node_modules and reinstall for Windows.
if not exist "node_modules" goto do_npm_install
if not exist "node_modules\edgedriver" goto do_npm_install
if exist "node_modules\@esbuild\win32-x64" goto npm_ok
echo Detected node_modules from a different platform. Reinstalling for Windows...
rmdir /s /q node_modules
:do_npm_install
call npm install
if errorlevel 1 goto err_npm
:npm_ok

REM ── Parse arguments ────────────────────────────────────────────────────
set DEJAVIEW_TEST_SUITE=all
set DEJAVIEW_TEST_FLOW=

if "%1"=="" goto run
if "%1"=="smoke" goto set_smoke
if "%1"=="long" goto set_long
if "%1"=="flow" goto set_flow

echo Unknown argument: %1
echo Usage: run-local.bat [smoke ^| long ^| flow ^<file^>]
exit /b 1

:set_smoke
echo Running smoke flows...
set DEJAVIEW_TEST_SUITE=smoke
goto run

:set_long
echo Running long-running flows...
set DEJAVIEW_TEST_SUITE=long-running
goto run

:set_flow
if "%2"=="" goto err_no_flow
echo Running flow: %2
set DEJAVIEW_TEST_FLOW=%2
goto run

REM ── Error handlers ─────────────────────────────────────────────────────

:err_no_binary
echo ERROR: DejaView binary not found at %DEJAVIEW_BINARY_PATH%
echo Update DEJAVIEW_BINARY_PATH in this file if the app is installed elsewhere.
exit /b 1

:err_node_install
echo ERROR: Could not install Node.js via winget.
echo Install Node.js manually from https://nodejs.org/ and re-run this script.
exit /b 1

:err_node_path
echo ERROR: Node.js was installed but is not on PATH.
echo Close this terminal, open a new one, and re-run this script.
exit /b 1

:err_vsbt_install
echo ERROR: Could not install Visual C++ Build Tools via winget.
echo Install manually: https://visualstudio.microsoft.com/visual-cpp-build-tools/
echo Select "Desktop development with C++" workload.
exit /b 1

:err_rust_install
echo ERROR: Could not install Rust via winget.
echo Install Rust manually from https://rustup.rs/ and re-run this script.
exit /b 1

:err_rust_path
echo ERROR: Rust was installed but cargo is not on PATH.
echo Close this terminal, open a new one, and re-run this script.
exit /b 1

:err_msvc_env
echo ERROR: vcvarsall.bat not found. The C++ workload may not be installed.
echo Run this in an admin terminal:
echo   winget install Microsoft.VisualStudio.2022.BuildTools --override "--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
echo Or open Visual Studio Installer, select Build Tools, and add "Desktop development with C++".
exit /b 1

:err_msvc_env_load
echo ERROR: vcvarsall.bat ran but link.exe is still not available.
echo Try opening "x64 Native Tools Command Prompt for VS 2022" and running
echo this script from there.
exit /b 1

:err_tauri_driver
echo ERROR: Could not install tauri-driver via cargo.
echo Try manually: cargo install tauri-driver
exit /b 1

:err_npm
echo ERROR: npm install failed.
exit /b 1

:err_no_flow
echo ERROR: Specify a flow file. Example: run-local.bat flow flows\smoke-basic.yaml
exit /b 1

REM ── Run tests ──────────────────────────────────────────────────────────

:run
echo.
echo Prerequisites OK: node, cargo, tauri-driver, npm deps
echo.

call npm run test:local
echo.
echo Recordings saved to: %~dp0recordings\
dir /b /ad "%~dp0recordings\" 2>nul
