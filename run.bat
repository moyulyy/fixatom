@echo off
setlocal
cd /d "%~dp0"
set "FIXATOMS_PYTHON=D:\miniconda3\envs\chem_env\python.exe"
if not exist "%FIXATOMS_PYTHON%" (
    echo Python environment not found: %FIXATOMS_PYTHON%
    echo Edit FIXATOMS_PYTHON in run.bat to point to your environment.
    pause
    exit /b 1
)
"%FIXATOMS_PYTHON%" "%~dp0app.py" %*
if errorlevel 1 pause
