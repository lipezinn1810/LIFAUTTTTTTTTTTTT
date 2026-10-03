@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    python main.py %*
) else (
    py -3 main.py %*
)
set "resultado=%errorlevel%"
echo.
pause
exit /b %resultado%
