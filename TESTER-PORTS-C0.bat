@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
echo.
echo Diagnostic des ports C0 -- registre officiel, sans port de secours.
echo La presence sur le port ne prouve pas le fonctionnement du service.
echo.
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0Diagnostic-kOA-Digital-Ecosystem-CLI.py" ports --root "C:\mycode"
    set "ERR=!errorlevel!"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo ERREUR : Python 3 est requis.
        set "ERR=30"
    ) else (
        python "%~dp0Diagnostic-kOA-Digital-Ecosystem-CLI.py" ports --root "C:\mycode"
        set "ERR=!errorlevel!"
    )
)
echo.
echo Code resultat : !ERR!
echo Les rapports sont dans reports\Diagnostic-kOA-Digital-Ecosystem\ports-c0
pause
exit /b !ERR!
