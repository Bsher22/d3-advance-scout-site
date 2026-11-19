@echo off
REM Publish the scouting site: build it, save it, send it to GitHub. Cloudflare picks it up from there.
REM Run from anywhere:  scouting\deploy\publish.bat
cd /d "%~dp0"
if not exist ".git" (
  echo This folder is not connected to GitHub yet. Run  connect_github.bat  first ^(see SETUP.md^).
  exit /b 1
)
python preflight.py || exit /b 1
python build_site.py || exit /b 1
git add -A || exit /b 1
git diff --cached --quiet
if not errorlevel 1 (
  echo Nothing has changed since the last publish.
  exit /b 0
)
git commit -q -m "Site update %date% %time:~0,5%" || exit /b 1
git push origin main || exit /b 1
echo.
echo Sent to GitHub. Cloudflare publishes it in a minute or two.
