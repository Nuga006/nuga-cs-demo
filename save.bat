@echo off
rem Save everything to git and push to GitHub with one command (no Claude, no tokens).
rem Usage, from the project folder:   .\save "what changed"
rem Without a message the date and time are used.
chcp 65001 >nul
cd /d "%~dp0"
set "MSG=%~1"
if "%MSG%"=="" set "MSG=Update %date% %time:~0,5%"
git add -A
git diff --cached --quiet
if not errorlevel 1 (
  echo Nothing to save - no changes.
  exit /b 0
)
git commit -m "%MSG%"
if errorlevel 1 exit /b 1
git push origin HEAD
if errorlevel 1 exit /b 1
echo.
echo Done: committed and pushed to GitHub.
