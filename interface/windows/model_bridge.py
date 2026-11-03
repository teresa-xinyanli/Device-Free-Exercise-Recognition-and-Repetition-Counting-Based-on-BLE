"""Versioned adapter for causal classification AND repetition events."""
import importlib.util
import json
import math
import sys
from pathlib import Path

class ModelBridge:
    def __init__(self, directory=None):
        self.model = None
        self.info = None
        self.seen = set()
        self.last_event_time = -1.0
        if directory is not None:
            directory = Path(directory).resolve()
            self.info = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
            if self.info.get('api_version') != 1 or self.info.get('causal') is not True:
                raise ValueError('Model must declare api_version=1 and causal=true.')
            if 'supports_counting' in self.info and not isinstance(self.info['supports_counting'],bool):
                raise ValueError('supports_counting must be true or false.')
            for field in ('name', 'version', 'labels', 'window_s', 'stride_s', 'max_gap_s'):
                if field not in self.info:
                    raise ValueError('Missing model field: ' + field)
            if not isinstance(self.info['labels'], list) or not self.info['labels'] or any(not isinstance(x,str) or not x for x in self.info['labels']):
                raise ValueError('labels must be a nonempty list of names.')
            for field in ('window_s', 'stride_s', 'max_gap_s'):
                if not isinstance(self.info[field], (int,float)) or not math.isfinite(self.info[field]) or self.info[field] <= 0:
                    raise ValueError(field + ' must be finite and positive.')
            self.info['directory'] = str(directory)
            # A model folder is trusted local Python code, selected by the user.
            if str(directory) not in sys.path:
                sys.path.insert(0, str(directory))
            spec = importlib.util.spec_from_file_location('wireless_user_adapter', directory / 'adapter.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.model = module.load(directory)

    def reset(self):
        self.seen.clear()
        self.last_event_time = -1.0
        if self.model is not None:
            self.model.reset()

    def predict(self, samples):
        result = self.model.predict(samples)
        label = result.get('action', 'unknown')
        confidence = result.get('confidence')
        if label not in self.info['labels'] and label != 'unknown':
            raise ValueError('Unexpected action: ' + str(label))
        if confidence is not None and (not isinstance(confidence,(int,float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError('confidence must be null or a number in [0,1].')
        events = []
        for event in result.get('rep_events', []):
            key = event.get('id')
            at = event.get('time_s')
            action = event.get('action')
            if not isinstance(key,str) or not key or action not in self.info['labels']:
                raise ValueError('Each repetition needs a stable string id and supported action.')
            if not isinstance(at,(int,float)) or not math.isfinite(at) or not samples[0]['time_s'] <= at <= samples[-1]['time_s']:
                raise ValueError('Repetition timestamp must be inside the current input window.')
            if key not in self.seen:
                if at < self.last_event_time:
                    raise ValueError('New repetition events must be chronological.')
                self.seen.add(key)
                self.last_event_time = at
                events.append(dict(id=key, time_s=at, action=action))
        return dict(action=label, confidence=confidence, rep_events=events)
