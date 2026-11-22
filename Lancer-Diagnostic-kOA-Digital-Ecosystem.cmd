@echo off
setlocal
cd /d "%~dp0"
where pyw >nul 2>&1
if not errorlevel 1 (
    start "" pyw -3 "%~dp0Diagnostic-kOA-Digital-Ecosystem.pyw"
    exit /b 0
)
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw "%~dp0Diagnostic-kOA-Digital-Ecosystem.pyw"
    exit /b 0
)
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0Diagnostic-kOA-Digital-Ecosystem.pyw"
    exit /b %errorlevel%
)
echo Python 3.10+ avec Tkinter est requis. Ouvrez un terminal et lancez :
echo py -3 "%~dp0Diagnostic-kOA-Digital-Ecosystem.pyw"
pause
exit /b 1
