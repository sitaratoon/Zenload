@echo off
setlocal

REM Check for Python installation
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Python is required but not installed. Please install Python first.
    exit /b 1
)

REM Check for Git installation
where git >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Git is required but not installed. Please install Git first.
    exit /b 1
)

REM Clone or update repository
if not exist .git (
    echo Cloning Zenload repository...
    git clone https://github.com/RoninReilly/Zenload.git .
) else (
    echo Updating repository...
    git pull
)

REM Create and activate virtual environment
echo Setting up Python virtual environment...
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Create run script
echo Creating run script...
(
echo @echo off
echo call venv\Scripts\activate.bat
echo python main.py
) > run.bat

echo.
echo ===========================================
echo Deployment completed successfully!
echo.
echo To start the bot:
echo Simply run run.bat
echo.
echo To update the bot:
echo Just run deploy.bat again
echo.
echo The bot will create necessary directories (downloads, cookies)
echo automatically on first run
echo ===========================================

endlocal
