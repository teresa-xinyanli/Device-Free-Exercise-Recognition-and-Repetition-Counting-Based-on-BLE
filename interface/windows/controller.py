"""Single owner of the serial connection, files, model and workout state."""
import io
import queue
import time
from collections import deque
from model_bridge import ModelBridge
from serial_receiver import ReceiverStream,open_port
from session_store import Session
from workout import Workout

class Controller:
    def __init__(self,bridge,updates,commands,stop):
        self.bridge=bridge;self.updates=updates;self.commands=commands;self.stop=stop

    def post(self,event,value=None):self.updates.put((event,value))

    def run(self,port,target):
        session=None;stream=None;error=None;raw=io.BytesIO();header=b''
        buffer=deque();workout=Workout();last_source=None;origin=0;elapsed=0;last_at=None;last_predict=-1e9
        active=False;baseline=False;deadline=None;last_tick=None

        def save_set(item):
            if not item:return
            counts=item['counts'] or {'—':None if not workout.counting else 0}
            for action,count in counts.items():session.append(session.sets,[item['number'],item['start_s'],item['end_s'],action,count,'unavailable' if count is None else 'model_event'])

        def model_failure(exc):
            nonlocal active
            active=False;workout.counting=False;session.metadata['model_error']=str(exc)
            session.append(session.events,[elapsed,'model_error',str(exc)]);self.post('model_error',str(exc))

        def finish(reason=None):
            nonlocal session,active,deadline
            if session is None:return
            save_set(workout.end(elapsed));snapshot=workout.snapshot()
            session.metadata.update(sets=snapshot['sets'],counting_available=workout.counting)
            if baseline:
                session.metadata.update(calibration_applied=False,baseline_complete=bool(deadline and time.monotonic()>=deadline and session.metadata['samples']>=150),baseline_min_samples=150)
            session.append(session.events,[elapsed,'session_stop',reason or 'User ended session'])
            path=str(session.path);session.finish(reason,snapshot['counts'],elapsed,dict(stream.stats) if stream else {})
            session=None;active=False;deadline=None;buffer.clear();stream.raw_file=raw
            self.post('saved',(reason,path))

        try:
            with open_port(port) as connection:
                stream=ReceiverStream(connection,self.stop,raw,status=lambda s:self.post('status',s),target_mac=target)
                epoch=stream.handshake()
                if epoch is None:return
                header=raw.getvalue();raw.seek(0);raw.truncate();self.post('ready')
                while not self.stop.is_set():
                    try:command,payload=self.commands.get_nowait()
                    except queue.Empty:command=None
                    if command=='start' and session is None:
                        try:
                            if last_source is None or time.monotonic()-last_host>2:raise ValueError('Wait for fresh target packets before starting.')
                            baseline=payload['session_type']=='baseline';self.bridge.reset()
                            metadata=dict(payload);base=metadata.pop('output');origin=last_source;elapsed=0;host_anchor=time.monotonic()
                            counting=bool(self.bridge.model and self.bridge.info.get('supports_counting',False) and not baseline)
                            metadata.update(model=None if baseline else self.bridge.info,counting_available=counting,calibration_applied=False,
                                            source='esp32s3_serial',timestamp_kind='device_elapsed_since_record_start',device_epoch_s=origin,
                                            note='Raw serial includes connection preamble and preview context. Signal CSV starts at record start.')
                            session=Session(base,metadata);session.raw.write(header+raw.getvalue());session.raw.flush();stream.raw_file=session.raw
                            active=bool(self.bridge.model) and not baseline;workout=Workout(counting)
                            if not baseline:workout.begin(0)
                            deadline=time.monotonic()+30 if baseline else None;last_tick=None;buffer.clear();last_at=None;last_predict=-1e9
                            session.append(session.events,[0,'baseline_start' if baseline else 'workout_start','No manual exercise selection'])
                            self.post('started',(str(session.path),baseline,workout.snapshot()))
                        except Exception as exc:
                            if session is not None:raise
                            self.post('command_error',str(exc))
                    elif command=='end_set' and session and not baseline:
                        save_set(workout.end(elapsed));session.append(session.events,[elapsed,'set_end','Manual boundary; no repetitions added']);self.post('workout',workout.snapshot())
                    elif command=='next_set' and session and not baseline:
                        workout.begin(elapsed);buffer.clear();last_at=None
                        if active:
                            try:self.bridge.model.reset()
                            except Exception as exc:model_failure(exc)
                        session.append(session.events,[elapsed,'set_start',workout.current['number']]);self.post('workout',workout.snapshot())
                    elif command=='finish' and session:finish()
                    if deadline is not None:
                        remaining=max(0,int(deadline-time.monotonic()+.999))
                        if remaining!=last_tick:self.post('baseline_tick',remaining);last_tick=remaining
                        if remaining==0:finish()
                    row=stream.next_sample()
                    if row is None:
                        if session is None and raw.tell()>65536:raw.seek(0);raw.truncate()
                        continue
                    last_source=row.source_time_s;last_host=time.monotonic()
                    self.post('sample',(row.source_time_s-epoch,row.rssi_dbm,stream.stats['local_queue_drops_during_session']))
                    if session is None:
                        if raw.tell()>65536:raw.seek(0);raw.truncate()
                        continue
                    elapsed=row.source_time_s-origin
                    session.append(session.signal,[elapsed,row.rssi_dbm,row.device_id,row.source_time_s,time.monotonic()-host_anchor,row.callback_seq,row.queue_drops_total,'esp32s3_serial'])
                    session.metadata['samples']+=1;self.post('elapsed',elapsed)
                    if active:
                        try:
                            info=self.bridge.info
                            if last_at is not None and elapsed-last_at>info['max_gap_s']:
                                buffer.clear();self.bridge.model.reset();session.append(session.events,[elapsed,'model_gap_reset','Warming up']);self.post('gap')
                            buffer.append(dict(time_s=elapsed,rssi_dbm=row.rssi_dbm))
                            while len(buffer)>1 and buffer[1]['time_s']<elapsed-info['window_s']:buffer.popleft()
                            if elapsed-buffer[0]['time_s']>=info['window_s'] and elapsed-last_predict>=info['stride_s']:
                                begin=time.perf_counter();result=self.bridge.predict(list(buffer));latency=(time.perf_counter()-begin)*1000
                                session.append(session.predictions,[elapsed,result['action'],result['confidence'],round(latency,3)])
                                accepted=workout.accept(result['rep_events'])
                                for event in accepted:session.append(session.reps,[event['time_s'],event['action'],event['id'],event['set_number']])
                                self.post('prediction',(dict(result,time_s=elapsed),accepted,workout.snapshot()));last_predict=elapsed
                        except Exception as exc:model_failure(exc)
                    last_at=elapsed
        except Exception as exc:error=f'{type(exc).__name__}: {exc}'
        finally:
            if session is not None:
                try:finish(error)
                except Exception as exc:
                    error=(error or '')+' Save error: '+str(exc)
                    try:
                        session.raw.close()
                        for file in session.files:file.close()
                    except Exception:pass
            raw.close();self.post('disconnected',error)
