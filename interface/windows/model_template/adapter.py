"""Integration skeleton ONLY. This is not a trained model or repetition detector."""

def load(model_dir):
    # Load frozen preprocessing, feature order, classifier and repetition detector here.
    # No untrusted pickle/joblib files. Load only your team's own artifacts.
    raise NotImplementedError('Template only. Your teammate must implement load(), reset() and predict().')

class Predictor:
    def reset(self):
        """Clear temporal state on a new session or signal gap.

        Repetition IDs must still be unique across gap resets within a session.
        Use action + absolute session timestamp to construct stable IDs.
        """
        pass

    def predict(self, samples):
        """samples: list of {time_s: float, rssi_dbm: int}, increasing device time.

        Run YOUR training-matched causal resampling, filtering, normalization and
        feature extraction. Samples are irregular; the app does NOT resample.
        Model must use only available/past data. Do not normalize with future data.
        Never increment a repetition just because a window is classified as squat.
        Return a stable event id for each completed repetition. Repeated overlapping
        windows may return the same event id; the app deduplicates those events.

        Output example (not implemented):
        {"action":"squat", "confidence":0.8,
         "rep_events":[{"id":"squat-12.450", "time_s":12.45,"action":"squat"}]}
        confidence may be None. Return action='unknown' for uncertain predictions.
        rep_events=[] means no confirmed repetitions, NOT one repetition/window.
        Classification-only adapters must return rep_events=[] and be clearly
        described as classification-only in their manifest name/documentation.
        """
        raise NotImplementedError
