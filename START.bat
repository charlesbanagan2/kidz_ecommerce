@echo off
echo ========================================
echo Kids ^& Baby E-commerce Platform
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from python.org
    pause
    exit /b 1
)

echo Python detected: 
python --version
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    echo Virtual environment created.
    echo.
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
echo.

REM Install/update dependencies
echo Installing dependencies...
pip install -r requirements_fixed.txt --quiet
echo Dependencies installed.
echo.

REM Create upload directories if they don't exist
if not exist "static\uploads\" mkdir static\uploads
if not exist "static\uploads\documents\" mkdir static\uploads\documents
if not exist "static\uploads\categories\" mkdir static\uploads\categories

REM Run the application
echo ========================================
echo Starting application...
echo ========================================
echo.
echo Access the app at: http://localhost:5000
echo Admin login: admin@kidscommerce.com / admin123
echo.
echo Press CTRL+C to stop the server
echo ========================================
echo.

python run.py

pause
