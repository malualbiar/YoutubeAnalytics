@echo off
setlocal enabledelayedexpansion

echo ======================================================================
echo          YT Quid Desktop App - One-Click Production Build
echo ======================================================================
echo.

:: 1. Check Python
if exist "venv\Scripts\python.exe" (
    set "PY_CMD=venv\Scripts\python.exe"
    set "PYI_CMD=venv\Scripts\pyinstaller.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
    set "PYI_CMD=.venv\Scripts\pyinstaller.exe"
) else (
    set "PY_CMD=python"
    set "PYI_CMD=pyinstaller"
)

echo [1/4] Checking environment dependencies...
call %PY_CMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python dependencies.
    exit /b %errorlevel%
)

:: 2. Compile Backend
echo.
echo [2/4] Packaging embedded Django WSGI backend with PyInstaller...
call %PYI_CMD% server.spec --distpath dist-backend --workpath build-backend --clean --noconfirm
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller compilation failed.
    exit /b %errorlevel%
)

:: 3. Test Backend
echo.
echo [3/4] Verifying packaged server executable...
call dist-backend\server\server.exe --test
if %errorlevel% neq 0 (
    echo [ERROR] Server self-check failed.
    exit /b %errorlevel%
)
echo [OK] Backend self-check passed.

:: 4. Build Electron Desktop App
echo.
echo [4/4] Building Electron NSIS Installer and Portable Executables...
call npx electron-builder --win
if %errorlevel% neq 0 (
    echo [ERROR] Electron packaging failed.
    exit /b %errorlevel%
)

echo.
echo ======================================================================
echo [SUCCESS] Desktop build completed successfully!
echo Binaries available in: dist-electron\
echo   - Installer: dist-electron\YT Quid Setup 1.3.0.exe
echo   - Portable:  dist-electron\YT Quid 1.3.0.exe
echo ======================================================================
