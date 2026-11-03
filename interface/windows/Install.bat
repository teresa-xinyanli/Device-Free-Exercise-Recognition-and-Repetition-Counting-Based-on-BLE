@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Ready. Double-click Start.bat.
goto done
:failed
echo Setup failed. Install Python 3.12 with Tkinter, then run this file again.
:done
pause
popd
endlocal
