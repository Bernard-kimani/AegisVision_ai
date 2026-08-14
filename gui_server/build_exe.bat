@echo off
echo ========================================
echo   AegisVision AI Trading Server - Build Script
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ and add it to PATH
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

REM Check if pip is available
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: pip is not available
    echo Please ensure pip is installed with Python
    pause
    exit /b 1
)

echo Installing/upgrading dependencies...
echo.

REM Install dependencies
pip install -r requirements.txt --upgrade
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    echo Please check requirements.txt and internet connection
    pause
    exit /b 1
)

echo.
echo Dependencies installed successfully!
echo.

echo Building React frontend...
echo.
pushd frontend
call npm install
if %errorlevel% neq 0 (
    echo ERROR: npm install failed in frontend\
    popd
    pause
    exit /b 1
)
call npm run build
if %errorlevel% neq 0 (
    echo ERROR: Frontend build failed
    popd
    pause
    exit /b 1
)
popd

echo.
echo Frontend built successfully!
echo.

REM Clean previous builds
if exist "build" (
    echo Cleaning previous build directory...
    rmdir /s /q "build"
)

if exist "dist" (
    echo Cleaning previous dist directory...
    rmdir /s /q "dist"
)

echo.
echo Building executable with PyInstaller...
echo This may take several minutes...
echo.

REM Build the executable
pyinstaller aegisvision_server.spec --clean
if %errorlevel% neq 0 (
    echo ERROR: PyInstaller build failed
    echo Please check the error messages above
    pause
    exit /b 1
)

echo.
echo ========================================
echo           BUILD SUCCESSFUL!
echo ========================================
echo.

REM Check if executable was created
if exist "dist\AegisVision_AI_Server.exe" (
    echo Executable created: dist\AegisVision_AI_Server.exe
    
    REM Get file size
    for %%A in ("dist\AegisVision_AI_Server.exe") do (
        set size=%%~zA
        set /a sizeMB=!size!/1048576
    )
    
    echo File size: %sizeMB% MB
    echo.
    echo You can now run the executable:
    echo   dist\AegisVision_AI_Server.exe
    echo.
    echo Or copy it to any Windows machine - no Python installation required!
    echo.
    
    REM Ask if user wants to run the executable
    set /p choice="Do you want to test the executable now? (y/n): "
    if /i "%choice%"=="y" (
        echo.
        echo Starting executable...
        start "" "dist\AegisVision_AI_Server.exe"
    )
) else (
    echo ERROR: Executable was not created
    echo Please check the PyInstaller output above for errors
)

echo.
echo Build process completed.
pause