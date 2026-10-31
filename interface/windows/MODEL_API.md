# Model adapter API v1

## Current interface behavior

Manifest field `supports_counting` must explicitly be `true` to enable counting. Missing/false means classification only: activity can display, but the repetition card/tab stay hidden and no events are counted. Set true only when a working counter is delivered and tested. There is no manual activity selection. Idle/other and unknown come from the adapter; the UI does not invent these classes from RSSI alone.

Manual set end/start commands are serialized with samples on the acquisition worker. Reps are counted only inside active sets, tagged with set_number and deduplicated across the entire session. Model reset on a new set clears temporal inference state, but event IDs must not be reused. A late confirmation for a prior set must not be assigned to the next set; timestamps before the new set boundary are ignored. Users should wait for delayed confirmations before finishing a set; the UI currently does not flush a model-specific pending cycle.

Connection preview creates no session or files. Workout and 30-second baseline captures are explicit recording modes. Baseline capture does NOT modify model preprocessing, thresholds or weights. A future calibration API and validated method are still needed.

Deliver a trusted local folder with manifest.json, adapter.py and weights. See model_template.

`load(model_dir: pathlib.Path) -> predictor`; predictor must implement `reset()` and `predict(samples)`.

Manifest: api_version=1; causal=true; name; version; labels (nonempty string list); window_s; stride_s; max_gap_s (positive finite seconds). Values MUST match training, not be chosen to match a test repetition count. Include dataset/training provenance in an extra field if available. Unknown is always allowed.

Input is an increasing list of dictionaries `{time_s, rssi_dbm}` using device elapsed seconds since START. A window includes one boundary sample at or just before the window start. No uniform sample rate is assumed. Adapter owns training-matched resampling, normalization, filters, feature order, confidence threshold, missing/insufficient sample handling. Use only current and past data; offline centered filters requiring future observations must be redesigned and revalidated for live use. Never normalize using the full future session.

Output:
```json
{"action":"squat","confidence":0.82,"rep_events":[{"id":"squat-12.450","time_s":12.45,"action":"squat"}]}
```

confidence may be null. Model score is not assumed calibrated. `unknown` is for uncertain/unsupported activities. `rep_events` defaults to []; each event must be inside current input time bounds. Events must be confirmed using available observations; timestamp can indicate the confirmed cycle's end. New IDs must have nondecreasing timestamps. Duplicate IDs are ignored across overlapping windows and gaps within a session. Construct stable IDs from activity + session-relative timestamp. reset() clears temporal state but MUST NOT cause recycled event IDs after a gap. A new app session clears app deduplication and all totals.

Never derive reps by summing classified windows. A classifier alone should return no events; label its manifest name as classification-only until a counter is provided. Prefer unknown/no event over inventing a count from insufficient signal.

Calls occur on the serial worker, not UI thread. Keep inference comfortably faster than stride_s; long blocking inference can back up USB reception. UI remains responsive but cannot forcibly cancel a hung adapter. Raw serial + callback diagnostics let you detect overload; test on actual hardware. Use a separate inference process if the production model cannot meet that budget.

Model exceptions disable inference for that session, are recorded in metadata/events, and radio logging continues. Gaps exceeding max_gap_s clear the input buffer and call model.reset(). First inference waits for a full window. UI clears stale class after 2 seconds without target packets; confirmed counts remain.

Package requirements: hand over exact Python version and dependency pins, feature names/order, label mapping, a small independent input/output fixture, and classifier/count validation results. The current frozen app contains no ML runtime libraries. Install actual model dependencies in .buildenv, add required PyInstaller hooks/hidden imports, rebuild and verify the frozen executable before delivery. Dynamic adapter imports alone cannot make sklearn/torch available in a frozen bundle.
