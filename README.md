# Device-Free Exercise Recognition and Repetition Counting Based on BLE

This repository currently publishes an **offline BLE RSSI exercise classifier**. The latest release is `exclude_Person02_Fly5_20261030_194752`, trained with scikit-learn 1.9.1. It recognizes **Fly, JumpingJack, and Squat**. Standing/Idle detection and repetition counting are **not implemented** in this model release.

## Quick start

Use Python 3.12 or 3.13:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python predict.py --input examples/format_example.csv --output predictions.csv
python -m unittest discover -s tests -v
```

The example is synthetic and demonstrates the CSV format only; it is not an accuracy benchmark. No original participant recordings are included.

## Input and prediction

Each CSV row must contain `rssi_00` through `rssi_19`: **20 finite RSSI values in dBm, sampled at 10 Hz across a two-second window**. Keep the same transmitter/receiver geometry and preprocessing used during training. This release does not filter or normalize RSSI amplitudes before the saved feature transformer.

```bash
python predict.py --input your_windows.csv --output predictions.csv --model global
python predict.py --input your_windows.csv --output predictions.csv --model Person01
```

`--model` accepts `global`, `Person01`, `Person02`, or `Person03`. Each personalized model is intended for its corresponding known participant. Output includes the predicted action and uncalibrated class scores. Idle or an unknown action will still receive one of the three exercise labels; scores are not validated confidence guarantees.

Models are under `models/`; `models/manifest.json` records SHA256 checksums and the input contract. `rssi_features.py` must remain importable when loading these joblib files. Models use 19 statistical/autocorrelation/spectral features, with the saved feature mode selecting the applicable subset.

## Training data and exclusions

The global model uses **408 exercise windows from 54 independent recordings and three participants**. All 63 Idle windows are excluded. `Person02-Fly-Front-10-5.csv` (10 windows) is excluded from training and parameter selection following a data audit and user-directed exclusion. Its source recording was retained locally.

Global and cross-person evaluation retain all **418 original exercise test windows**, including that recording when it is held out. Thus, improvement is not created by removing difficult test examples. Every training/test split separates complete `source_session` groups. Input data, raw captures, and duplicate training/test CSVs are not bundled with this model publication.

## Results

| Evaluation | Accuracy | Macro-F1 |
|---|---:|---:|
| Global RF, held-out recordings (5 outer folds) | 51.0% | 0.501 |
| Global RF, leave-one-person-out | 28.2% | 0.250 |
| Person01, personal recording-grouped validation | 83.9% | 0.819 |
| Person02, personal recording-grouped validation | 55.5% | 0.506 |
| Person03, personal recording-grouped validation | 60.2% | 0.593 |

Person01 and Person03 datasets/models were unchanged by the exclusion; their existing verified results are retained. Personal and global results have different evaluation populations and should not be interpreted as a controlled improvement comparison.

These are **exploratory results**, not an independent external benchmark: the excluded recording was selected after inspecting earlier test results. Only three participants and one recorded geometry were available. Cross-person performance remains weak. Full per-class metrics, exclusions, verification results, and recording-group split definitions are in `evaluation/`.

## Reproduce training with local data

Obtain the matching `washed-data/training_windows.csv` separately. Keep all metadata, including `window_id`, `source_file`, `source_session`, `subject`, and `action`.

```bash
python train.py --data /path/to/washed-data --output local_results
# Refit weights only, without repeating all held-out evaluations:
python train.py --data /path/to/washed-data --output local_results --skip-evaluation
```

Training excludes Idle and the specified recording in every training and inner tuning split. The default reproduces the published recording partitions; it rejects data whose exercise window IDs do not match those partitions. Parameter selection uses grouped inner validation and Macro-F1. All reported tests are outer held-out predictions; predictions from full-data refits are not test scores. The saved deployment models in this repository are full-data refits.

## Upstream implementation

Random Forest implementation: [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn), BSD-3-Clause. The upstream license is in `third_party/LICENSE.scikit-learn`. See `requirements.txt` for the exact runtime versions used for this release.
