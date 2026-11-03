import csv
import json
import queue
import tempfile
import threading
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from model_bridge import ModelBridge
from session_store import Session
from serial_receiver import Sample
from app import App

def read_csv(path):
    with path.open(encoding='utf-8') as file:
        return list(csv.DictReader(file))

class Predictor:
    def __init__(self):self.resets=0
    def reset(self):self.resets+=1
    def predict(self,samples):
        return dict(action='squat',confidence=.8,rep_events=[dict(id='squat-1',time_s=1.,action='squat')])

def bridge():
    value=ModelBridge();value.model=Predictor()
    value.info=dict(name='Unit test only',version='test',labels=['squat'],window_s=1.,stride_s=.1,max_gap_s=.5)
    return value

class Tests(unittest.TestCase):
    def test_duplicate_events_not_double_counted(self):
        b=bridge();s=[dict(time_s=0,rssi_dbm=-60),dict(time_s=2,rssi_dbm=-65)]
        self.assertEqual(len(b.predict(s)['rep_events']),1)
        self.assertEqual(b.predict(s)['rep_events'],[])
        b.reset();self.assertEqual(len(b.predict(s)['rep_events']),1)

    def test_future_event_rejected(self):
        b=bridge()
        with self.assertRaises(ValueError):b.predict([dict(time_s=0),dict(time_s=.5)])

    def test_nan_confidence_rejected(self):
        b=bridge();b.model.predict=lambda s:dict(action='squat',confidence=float('nan'))
        with self.assertRaises(ValueError):b.predict([dict(time_s=0),dict(time_s=2)])

    def test_signal_and_predictions_separate(self):
        with tempfile.TemporaryDirectory() as path:
            s=Session(path,dict(model=None));s.append(s.signal,[1,-60,'tx',11,1,1,0,'esp32s3_serial'])
            s.metadata['samples']=1;s.finish(None,{},1,{})
            self.assertEqual(len(read_csv(s.path/'signal.csv')),1)
            self.assertEqual(read_csv(s.path/'predictions.csv'),[])
            self.assertIsNone(json.loads((s.path/'metadata.json').read_text())['error'])

    def run_worker(self, model, times, failure=None):
        with tempfile.TemporaryDirectory() as path:
            a=App.__new__(App);a.messages=queue.Queue();a.stop_event=threading.Event();a.bridge=model
            s=Session(path,dict(model=model.info));iterator=iter(enumerate(times))
            class Stream:
                stats={'local_queue_drops_during_session':0}
                def __init__(self,*args,**kwargs):pass
                def handshake(self):
                    if failure:raise RuntimeError(failure)
                    return 100.
                def next_sample(self):
                    try:i,t=next(iterator)
                    except StopIteration:a.stop_event.set();return None
                    return Sample(100+t,-60,'aa:bb:cc:dd:ee:ff',i+1,0)
            with patch('app.open_port',return_value=nullcontext(object())),patch('app.ReceiverStream',Stream):a.worker(s,'FAKE','')
            meta=json.loads((s.path/'metadata.json').read_text())
            preds=read_csv(s.path/'predictions.csv')
            events=read_csv(s.path/'events.csv')
            reps=read_csv(s.path/'repetitions.csv')
            return meta,preds,events,reps

    def test_worker_no_model_still_records(self):
        meta,preds,_,reps=self.run_worker(ModelBridge(),[0,.1,.2])
        self.assertEqual(meta['samples'],3);self.assertEqual(preds,[]);self.assertEqual(reps,[])

    def test_handshake_failure_saved(self):
        meta,_,_,_=self.run_worker(ModelBridge(),[],failure='Wrong receiver')
        self.assertIn('Wrong receiver',meta['error']);self.assertEqual(meta['samples'],0)

    def test_worker_real_adapter_contract_counts_once(self):
        meta,preds,_,reps=self.run_worker(bridge(),[i/10 for i in range(21)])
        self.assertEqual(meta['counts'],{'squat':1});self.assertGreater(len(preds),1);self.assertEqual(len(reps),1)

    def test_model_error_does_not_stop_radio(self):
        b=bridge();b.model.predict=lambda s:(_ for _ in ()).throw(ValueError('broken model'))
        meta,_,events,_=self.run_worker(b,[i/10 for i in range(21)])
        self.assertEqual(meta['samples'],21);self.assertIn('broken model',meta['model_error']);self.assertIsNone(meta['error'])
        self.assertTrue(any(e['event']=='model_error' for e in events))

    def test_gap_resets_model_and_suppresses_inference(self):
        b=bridge();meta,preds,events,_=self.run_worker(b,[0,.1,1.,1.1])
        self.assertEqual(preds,[]);self.assertEqual(b.model.resets,1)
        self.assertTrue(any(e['event']=='model_gap_reset' for e in events))

    def test_template_does_not_fake_predictions(self):
        with self.assertRaises(NotImplementedError):ModelBridge(Path(__file__).resolve().parents[1]/'model_template')

if __name__=='__main__':unittest.main()
