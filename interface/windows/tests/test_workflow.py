"""Synthetic software fixtures only; these do not measure wireless recognition."""
import json
import queue
import tempfile
import threading
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from controller import Controller
from model_bridge import ModelBridge
from serial_receiver import Sample
from workout import Workout
from app_v2 import App

class WorkflowTests(unittest.TestCase):
    def test_manual_boundaries_do_not_count(self):
        w=Workout(True);w.begin(0);w.end(2);w.begin(3)
        self.assertEqual(w.snapshot()['counts'],{});self.assertEqual(w.current['number'],2)

    def test_rest_and_late_events_do_not_enter_next_set(self):
        w=Workout(True);w.begin(0)
        event=dict(id='a',time_s=1,action='squat')
        self.assertEqual(len(w.accept([event,event])),1);w.end(2)
        self.assertEqual(w.accept([dict(id='b',time_s=3,action='fly')]),[])
        w.begin(4)
        self.assertEqual(w.accept([dict(id='c',time_s=1.5,action='squat')]),[])
        w.accept([dict(id='d',time_s=5,action='fly')]);w.end(6)
        self.assertEqual(w.snapshot()['counts'],{'squat':1,'fly':1})

    def test_no_counting_capability_does_not_show_fake_zero(self):
        w=Workout(False);w.begin(0);w.accept([dict(id='a',time_s=1,action='squat')]);w.end(2)
        self.assertFalse(w.snapshot()['counting']);self.assertEqual(w.snapshot()['counts'],{})

    def run_controller(self,bridge=None,schedule=None,times=None,fail=False):
        updates=queue.Queue();commands=queue.Queue();stop=threading.Event();clock=[0.]
        bridge=bridge or ModelBridge();schedule=schedule or {};times=times or [i/4 for i in range(17)]
        with tempfile.TemporaryDirectory() as directory:
            iterator=iter(enumerate(times));base=Path(directory)/'recordings'
            class Stream:
                stats={'local_queue_drops_during_session':0}
                def __init__(self,connection,event,raw,**kwargs):self.raw_file=raw
                def handshake(self):return 100.
                def next_sample(self):
                    try:i,t=next(iterator)
                    except StopIteration:stop.set();return None
                    clock[0]=t
                    if i in schedule:
                        command=schedule[i]
                        payload=dict(output=str(base),session_type='baseline' if command=='baseline' else 'workout',participant='fixture',placement='test') if command in ('start','baseline') else None
                        commands.put(('start' if command=='baseline' else command,payload))
                    if fail and i==5:raise OSError('USB disconnected')
                    return Sample(100+t,-60,'aa:bb:cc:dd:ee:ff',i+1,0)
            with patch('controller.open_port',return_value=nullcontext(object())),patch('controller.ReceiverStream',Stream),patch('controller.time.monotonic',side_effect=lambda:clock[0]):
                Controller(bridge,updates,commands,stop).run('FAKE','')
            metas=[json.loads(path.read_text()) for path in base.glob('*/metadata.json')]
            events=[]
            while not updates.empty():events.append(updates.get())
            return metas,events,base.exists()

    def test_connect_preview_creates_no_files(self):
        metas,events,exists=self.run_controller()
        self.assertFalse(exists);self.assertEqual(metas,[]);self.assertTrue(any(k=='sample' for k,v in events))

    def test_multiple_sessions_and_sets_saved(self):
        metas,events,_=self.run_controller(schedule={0:'start',3:'end_set',5:'next_set',7:'finish',9:'start',13:'finish'})
        self.assertEqual(len(metas),2);self.assertEqual([len(m['sets']) for m in metas],[2,1])
        self.assertTrue(all(not m['counting_available'] and m['counts']=={} for m in metas))
        self.assertEqual(sum(k=='saved' for k,v in events),2)

    def test_disconnect_finalizes_partial_session(self):
        metas,events,_=self.run_controller(schedule={0:'start'},fail=True)
        self.assertEqual(len(metas),1);self.assertIn('USB disconnected',metas[0]['error']);self.assertIn('finished_at',metas[0])

    def test_baseline_completes_but_never_applies_calibration(self):
        metas,events,_=self.run_controller(schedule={0:'baseline'},times=[i/10 for i in range(310)])
        self.assertEqual(len(metas),1);self.assertTrue(metas[0]['baseline_complete']);self.assertFalse(metas[0]['calibration_applied']);self.assertEqual(metas[0]['sets'],[])

    def test_short_baseline_is_marked_incomplete(self):
        metas,_,_=self.run_controller(schedule={0:'baseline',8:'finish'})
        self.assertFalse(metas[0]['baseline_complete']);self.assertFalse(metas[0]['counting_available'])

    def test_model_fault_continues_signal_logging(self):
        b=ModelBridge();b.info=dict(name='TEST',labels=['squat'],window_s=.5,stride_s=.25,max_gap_s=.6,supports_counting=True)
        class Broken:
            def reset(self):pass
            def predict(self,samples):raise ValueError('fixture model fault')
        b.model=Broken();metas,_,_=self.run_controller(bridge=b,schedule={0:'start',15:'finish'})
        self.assertEqual(metas[0]['samples'],15);self.assertIn('fixture model fault',metas[0]['model_error']);self.assertIsNone(metas[0]['error'])

    def test_controller_counts_active_sets_only(self):
        b=ModelBridge();b.info=dict(name='TEST fixture',labels=['squat'],window_s=.5,stride_s=.25,max_gap_s=.6,supports_counting=True)
        class Events:
            def reset(self):pass
            def predict(self,samples):
                at=samples[-1]['time_s']
                return dict(action='squat',confidence=.8,rep_events=[dict(id=str(at),time_s=at,action='squat')])
        b.model=Events()
        meta=self.run_controller(bridge=b,schedule={0:'start',5:'end_set',8:'next_set',13:'finish'})[0][0]
        self.assertEqual([s['counts'] for s in meta['sets']],[{'squat':3},{'squat':3}])
        self.assertEqual(meta['counts'],{'squat':6});self.assertTrue(meta['counting_available'])

    def test_classifier_does_not_enable_counter_implicitly(self):
        b=ModelBridge();b.info=dict(name='TEST classifier',labels=['squat'],window_s=.5,stride_s=.25,max_gap_s=.6)
        class Classifier:
            def reset(self):pass
            def predict(self,samples):return dict(action='squat',confidence=.8,rep_events=[])
        b.model=Classifier();meta=self.run_controller(bridge=b,schedule={0:'start',13:'finish'})[0][0]
        self.assertFalse(meta['counting_available']);self.assertEqual(meta['counts'],{})

    def test_prediction_history_reads_scores_without_counting_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'predictions.csv'
            path.write_text('time_s,action,confidence,inference_ms\n2.25,squat,0.8,1\n4.25,unknown,,1\nnan,fly,0.7,1\n6,fly,nan,1\n',encoding='utf-8')
            self.assertEqual(App.read_prediction_rows(path),[('2.25s','Squat','80%'),('4.25s','Unknown','—')])

    def test_ui_prediction_timestamp_uses_session_time(self):
        b=ModelBridge();b.info=dict(name='fixture',labels=['squat'],window_s=.5,stride_s=.25,max_gap_s=.6)
        class Classifier:
            def reset(self):pass
            def predict(self,samples):return dict(action='squat',confidence=None)
        b.model=Classifier();metas,events,_=self.run_controller(bridge=b,schedule={0:'start',13:'finish'})
        predictions=[v[0] for k,v in events if k=='prediction']
        self.assertTrue(predictions);self.assertGreaterEqual(predictions[0]['time_s'],.5)
        self.assertFalse(metas[0]['counting_available'])

    def test_counter_widgets_follow_loaded_model_capability(self):
        import tkinter as tk
        root=tk.Tk();root.withdraw()
        try:
            a=App(root)
            self.assertEqual(a.metric_cards[3].winfo_manager(),'')
            a.bridge.model=object();a.bridge.info={'supports_counting':False};a.refresh_model_view()
            self.assertEqual(a.metric_cards[3].winfo_manager(),'')
            a.bridge.info['supports_counting']=True;a.refresh_model_view()
            self.assertEqual(a.metric_cards[3].winfo_manager(),'grid')
            a.unload_model();self.assertEqual(a.result_tabs.tab(a.rep_panel,'state'),'hidden')
            a.bridge.model=object();a.bridge.info={'supports_counting':True};a.refresh_model_view()
            self.assertEqual(a.result_tabs.tab(a.rep_panel,'state'),'normal')
            a.model_failed=True;a.refresh_model_view()
            self.assertEqual(a.metric_cards[3].winfo_manager(),'')
        finally:
            for callback in root.tk.call('after','info'):root.after_cancel(callback)
            root.destroy()

    def test_summary_distinguishes_incomplete_error_and_signal_only(self):
        self.assertIn('Incomplete',App.record_status({}))
        self.assertEqual(App.record_status(dict(finished_at='now',model=None)),'Signal only')
        self.assertIn('partial',App.record_status(dict(finished_at='now',model_error='bad')))

if __name__=='__main__':unittest.main()
