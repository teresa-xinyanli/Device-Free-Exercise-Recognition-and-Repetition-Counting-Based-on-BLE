# Wireless Motion — Windows interface preview

Windows desktop interface for the MAS.S64 device-free exercise sensing project.
The receiver sends BLE RSSI over USB; the interface provides connection checks,
live RSSI, recording, manual set boundaries, prediction views and session review.

**Current status:** no trained model is bundled or automatically loaded. Without a
model the app records/displays signal only. A classification-only adapter enables
activity predictions without repetition counts. Repetition counting remains
unimplemented and unvalidated; the UI exposes counting only for an explicitly
counting-capable adapter. A captured still baseline does not apply calibration.

## Run without Python

1. Download `Wireless-Motion-Windows-v0.3.1.zip` from the
   [interface preview release](https://github.com/teresa-xinyanli/Device-Free-Exercise-Recognition-and-Repetition-Counting-Based-on-BLE/releases/tag/interface-v0.3.1).
2. Extract the ZIP fully. Keep `Wireless Motion.exe` and `_internal` together.
3. Open `Wireless Motion/Start.bat` or `Wireless Motion.exe`.
4. Power TX; connect RX with a USB data cable. Close other serial loggers.
5. Choose **Connect device**, check firmware and target TX packets, enter
   Participant/Placement, and choose **Start workout** to save a recording.
6. **Finish set** marks a manual boundary; **End & save session** saves the session.

The preview expects the project's protocol-2 RX firmware (`RX_RAW_GAP_v3`).
Windows may need the USB driver appropriate to the receiver's USB interface.
No Arduino session is required for boards that are already programmed.

## Run the source

Use Python 3.12 with Tkinter on Windows (the preview was built with Python 3.12.10).
From this directory:

```powershell
.\Install.bat
.\Start.bat
```

`Install.bat` creates a local `.venv` and installs `pyserial`. `Start.bat` first uses
an existing local packaged executable; otherwise it starts `app_v2.py` from `.venv`.
The filename `app_v2.py` is retained for compatibility and is the current entry point.
`app.py` supplies shared widgets/plotting and is not the current standalone entry point.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The current 25 tests cover software behavior using fixtures and a Tkinter UI check;
they do not demonstrate real exercise recognition or counting accuracy. Run tests
in a Windows desktop session because the UI check creates a Tkinter window.

To build a fresh executable, run `Build.bat`. It uses an isolated `.buildenv`, runs
the tests, and refuses to overwrite `release_v3_1/Wireless Motion` if it exists.
Preserve existing releases/recordings and choose a new output directory for later builds.

## Keep model development separate

This snapshot only adds `interface/` on the `interface-windows-app` branch.
It does not merge into or move `main`. The model developer can continue pushing
model/training files to `main`; later, a PR can add the interface directory alongside them.
Future edits to the same `interface/` paths will still need normal Git conflict review.

The app does not search the repository or auto-import model/training files.
In **Advanced settings**, select a trusted adapter folder containing
`manifest.json`, `adapter.py` and the team's own model artifacts. It may live
outside this interface directory. See [`MODEL_API.md`](MODEL_API.md).

Model delivery must include preprocessing/feature code, feature order, label mapping,
window/stride settings, dependency versions, model artifacts and independent test
examples. The adapter owns training-matched resampling and feature extraction;
the app supplies irregular timestamped RSSI samples. The template is deliberately
nonfunctional and must not be presented as a trained model.

The frozen preview contains no scikit-learn/PyTorch runtime. When the real model is
available, install/pin its dependencies, add PyInstaller hooks as needed, rebuild,
and validate both source and executable on real boards. Model weights alone do
not make the current preview perform recognition.

## Saved files

Each explicit session writes `signal.csv`, `raw_serial.txt`, `predictions.csv`,
`events.csv`, `metadata.json`, `sets.csv` and `repetitions.csv`. Predictions and
manual boundaries are separate from raw radio data. Empty prediction/repetition
files are expected without a model/counter. Preview-only connection creates no session.

Source runs save under this directory's `sessions/`. The portable download saves
under `Wireless Motion/sessions/`. Choose another output directory in Advanced settings.
Experiment recordings, local backups, virtual environments, caches and generated
executables are excluded from source control. The original training logger/data
collection project is not replaced by this interface.

See [中文操作说明](README_中文.md) for detailed device and workout steps.
