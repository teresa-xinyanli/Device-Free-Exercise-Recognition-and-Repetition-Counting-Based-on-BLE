@echo off
setlocal
pushd "%~dp0"
if exist "release_v3_1\Wireless Motion" (
  echo Build stopped: preserve the existing release and choose a new output path before rebuilding.
  goto done
)
if not exist ".buildenv\Scripts\python.exe" (
  py -3.12 -m venv .buildenv
  if errorlevel 1 goto failed
)
".buildenv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".buildenv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
".buildenv\Scripts\python.exe" -m PyInstaller --noconfirm --windowed --onedir --name "Wireless Motion" --distpath release_v3_1 --workpath .build_v3 --specpath .build_v3 app_v2.py
if errorlevel 1 goto failed
echo Build complete. Use Start.bat.
goto done
:failed
echo Build failed. Review the error above.
:done
pause
popd
endlocal
