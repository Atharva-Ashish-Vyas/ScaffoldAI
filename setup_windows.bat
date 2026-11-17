@echo off
setlocal
cd /d "%~dp0"
py -3.10 --version >nul 2>&1
if errorlevel 1 (
    echo Python 3.10 was not found through the Windows Python launcher.
    echo Install Python 3.10 from python.org and enable the Python launcher.
    exit /b 1
)
py -3.10 -m venv .venv
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
if not exist ".env" copy ".env.example" ".env" >nul
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 exit /b 1
echo Setup completed. Edit .env then run start_windows.bat
