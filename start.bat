@echo off
cd /d "%~dp0"
python start.py
if errorlevel 9009 goto :try_py
goto :end
:try_py
py start.py
if errorlevel 9009 goto :no_python
goto :end
:no_python
echo [ERROR] Python not found in PATH.
echo Please install Python 3.10+ from https://www.python.org/downloads/
:end
pause
