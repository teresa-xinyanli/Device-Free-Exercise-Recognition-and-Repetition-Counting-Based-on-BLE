@echo off
setlocal
pushd "%~dp0"
if exist "release_v3_1\Wireless Motion\Wireless Motion.exe" (
  start "" "release_v3_1\Wireless Motion\Wireless Motion.exe"
) else if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "app_v2.py"
) else (
  echo Run Install.bat once, or download the portable ZIP from the interface release.
  echo See README.md and README_中文.md.
  pause
)
popd
endlocal
