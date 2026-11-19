@echo off
REM One time only: turn this folder into its own repository and send it to GitHub.
REM   connect_github.bat https://github.com/YOUR-NAME/d3-advance-scout-site.git
cd /d "%~dp0"
if "%~1"=="" (
  echo Give the address of the PRIVATE repository you created on GitHub, for example:
  echo   connect_github.bat https://github.com/YOUR-NAME/d3-advance-scout-site.git
  exit /b 1
)
if exist ".git" (
  echo This folder is already a repository. To publish, run  publish.bat
  exit /b 1
)
python preflight.py || exit /b 1
python build_site.py || exit /b 1
git init -q -b main || exit /b 1
git remote add origin %1 || exit /b 1
git add -A || exit /b 1
git commit -q -m "Scouting site" || exit /b 1
echo Sending about 180 MB to GitHub. This can take several minutes...
git push -u origin main || exit /b 1
echo.
echo Done. Now connect the repository in Cloudflare (SETUP.md, step 4).
