"""Wireless Motion: local Windows BLE sensing dashboard. No simulated predictions."""
import csv
import json
import os
import queue
import sys
import threading
import time
from collections import Counter, deque
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from serial.tools import list_ports
from serial_receiver import ReceiverStream, open_port, MAC
from model_bridge import ModelBridge
from session_store import Session

BASE = Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
BG='#F3F5F8'; WHITE='#FFFFFF'; INK='#192C3C'; MUTED='#697A8A'; TEAL='#087F8C'; LINE='#E3E9EF'

class App:
    def __init__(self, root):
        self.root=root
        root.title('Wireless Motion | MAS.S64')
        root.geometry('1220x850'); root.minsize(1080,780); root.configure(bg=BG)
        self.messages=queue.Queue(); self.stop_event=threading.Event(); self.thread=None
        self.bridge=ModelBridge(); self.points=deque(maxlen=600); self.counts=Counter()
        self.last_packet=None; self.session_path=None; self.closing=False; self.elapsed=0
        self.state=tk.StringVar(value='Ready to connect')
        self.port=tk.StringVar(); self.participant=tk.StringVar(value='P01'); self.placement=tk.StringVar(value='A')
        self.target=tk.StringVar(); self.output=tk.StringVar(value=str(BASE/'sessions'))
        self.model_text=tk.StringVar(value='No model connected')
        self.action=tk.StringVar(value='—'); self.confidence=tk.StringVar(value='Waiting for model')
        self.repetitions=tk.StringVar(value='—'); self.duration=tk.StringVar(value='00:00')
        self.quality=tk.StringVar(value='No signal yet'); self.detail=tk.StringVar(value='Power TX. Connect RX to this PC with a USB data cable.')
        style=ttk.Style(); style.theme_use('clam')
        style.configure('TCombobox',padding=7); style.configure('TEntry',padding=7)
        style.configure('Treeview',font=('Segoe UI',10),rowheight=29,background=WHITE,fieldbackground=WHITE,borderwidth=0)
        style.configure('Treeview.Heading',font=('Segoe UI',10,'bold'),background=BG,padding=7)
        self.build()
        self.refresh_ports(); self.load_history()
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll)

    def label(self,parent,text=None,var=None,size=10,color=INK,bold=False,bg=WHITE):
        return tk.Label(parent,text=text,textvariable=var,font=('Segoe UI',size,'bold' if bold else 'normal'),fg=color,bg=bg,anchor='w')

    def button(self,parent,text,command,primary=False):
        return tk.Button(parent,text=text,command=command,font=('Segoe UI',10,'bold'),bg=TEAL if primary else WHITE,
                         fg=WHITE if primary else INK,activebackground='#DAEEF0',relief='flat',bd=0,padx=14,pady=7,cursor='hand2')

    def build(self):
        top=tk.Frame(self.root,bg=INK,height=84);top.pack(fill='x');top.pack_propagate(False)
        brand=tk.Frame(top,bg=INK);brand.pack(side='left',padx=26,pady=14)
        self.label(brand,'WIRELESS / MOTION',size=19,color=WHITE,bold=True,bg=INK).pack(anchor='w')
        self.label(brand,'MAS.S64  ·  Device-free exercise sensing',size=10,color='#B5C9D6',bg=INK).pack(anchor='w',pady=(3,0))
        self.label(top,var=self.state,size=11,color='#A9E4D7',bg=INK).pack(side='right',padx=26)
        body=tk.Frame(self.root,bg=BG);body.pack(fill='both',expand=True,padx=22,pady=20)
        side=tk.Frame(body,bg=WHITE,width=268,padx=18,pady=18);side.pack(side='left',fill='y',padx=(0,20));side.pack_propagate(False)
        self.label(side,'01   DEVICE & SESSION',size=10,bold=True,color=TEAL).pack(anchor='w',pady=(0,6))
        self.fields=[]
        for title,var in [('Receiver USB port',self.port),('Participant',self.participant),('Placement',self.placement),('TX MAC · optional',self.target)]:
            self.label(side,title,color=MUTED).pack(anchor='w',pady=(5,3))
            field=ttk.Combobox(side,textvariable=var,state='readonly') if var is self.port else ttk.Entry(side,textvariable=var)
            field.pack(fill='x');self.fields.append(field)
        self.refresh=self.button(side,'Refresh USB ports',self.refresh_ports);self.refresh.pack(fill='x',pady=(5,10))
        self.label(side,'02   MODEL',bold=True,color=TEAL).pack(anchor='w')
        self.label(side,var=self.model_text,size=10).pack(anchor='w',pady=(10,4))
        self.model_button=self.button(side,'Choose model folder',self.load_model);self.model_button.pack(fill='x')
        note=self.label(side,'Load your team’s adapter to\nenable recognition and counting.',size=9,color=MUTED)
        note.pack(anchor='w',pady=(4,10))
        self.label(side,'03   WORKOUT',bold=True,color=TEAL).pack(anchor='w')
        self.start_button=self.button(side,'Connect & start session',self.start,True);self.start_button.pack(fill='x',pady=(12,8))
        self.stop_button=self.button(side,'Stop & save',self.stop);self.stop_button.pack(fill='x');self.stop_button.config(state='disabled')
        self.folder_button=self.button(side,'Choose save folder',self.choose_output);self.folder_button.pack(fill='x',pady=(14,0))
        self.button(side,'Open recordings',self.open_folder).pack(fill='x',pady=4)
        self.label(side,'TX → BLE → RX → USB\nNo wearable required.',size=9,color=MUTED).pack(anchor='w',pady=(8,0))
        main=tk.Frame(body,bg=BG);main.pack(side='left',fill='both',expand=True)
        self.label(main,'Your movement, sensed wirelessly.',size=23,bold=True,bg=BG).pack(anchor='w')
        self.label(main,'Live radio signal · model predictions · confirmed repetitions',color=MUTED,bg=BG).pack(anchor='w',pady=(6,18))
        cards=tk.Frame(main,bg=BG);cards.pack(fill='x')
        for i,(title,var,sub) in enumerate([('CURRENT ACTIVITY',self.action,self.confidence),('REPETITIONS',self.repetitions,None),('SESSION TIME',self.duration,None)]):
            card=tk.Frame(cards,bg=WHITE,padx=18,pady=15);card.grid(row=0,column=i,sticky='nsew',padx=(0,12 if i<2 else 0));cards.columnconfigure(i,weight=1)
            self.label(card,title,size=9,color=MUTED,bold=True).pack(anchor='w')
            self.label(card,var=var,size=26,color=TEAL if i==1 else INK,bold=True).pack(anchor='w',pady=(8,0))
            self.label(card,var=sub if sub else None,text=None if sub else ('All confirmed model events' if i==1 else 'Current recording'),size=9,color=MUTED).pack(anchor='w',pady=(4,0))
        chart=tk.Frame(main,bg=WHITE,padx=18,pady=14);chart.pack(fill='x',pady=(16,12))
        header=tk.Frame(chart,bg=WHITE);header.pack(fill='x')
        self.label(header,'LIVE RSSI',bold=True).pack(side='left')
        self.label(header,var=self.quality,size=9,color=TEAL).pack(side='right')
        self.canvas=tk.Canvas(chart,bg=WHITE,height=190,highlightthickness=0);self.canvas.pack(fill='x',pady=(10,0));self.canvas.bind('<Configure>',lambda e:self.draw())
        self.label(chart,'Raw BLE RSSI · last 30 seconds · dBm · vertical scale adapts to the signal',size=9,color=MUTED).pack(anchor='w')
        notice=tk.Frame(main,bg='#E6EFF3',padx=12,pady=9);notice.pack(fill='x',pady=(0,12))
        tk.Label(notice,textvariable=self.detail,font=('Segoe UI',10),fg=INK,bg='#E6EFF3',anchor='w',justify='left',wraplength=750).pack(fill='x')
        tabs=ttk.Notebook(main);tabs.pack(fill='both',expand=True)
        event_frame=tk.Frame(tabs,bg=WHITE);history_frame=tk.Frame(tabs,bg=WHITE)
        tabs.add(event_frame,text='   Repetition timeline   ');tabs.add(history_frame,text='   Saved sessions   ')
        self.events=self.tree(event_frame,('time','activity','event'),('Time','Activity','Confirmed repetition'))
        self.history=self.tree(history_frame,('session','participant','mode','count'),('Session','Participant','Model','Total reps'))
        self.history.bind('<Double-1>',self.open_history)
        self.label(main,'Research prototype  /  model output is separate from observed radio data',size=9,color=MUTED,bg=BG).pack(anchor='w',pady=(10,0))
        self.draw()

    def tree(self,parent,columns,headings):
        tree=ttk.Treeview(parent,columns=columns,show='headings',height=4)
        scroll=ttk.Scrollbar(parent,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');tree.pack(fill='both',expand=True)
        for key,title in zip(columns,headings):tree.heading(key,text=title);tree.column(key,width=120,stretch=True)
        return tree

    def refresh_ports(self):
        try:
            ports=list(list_ports.comports());self.fields[0]['values']=[p.device for p in ports]
            if self.port.get() not in [p.device for p in ports]:self.port.set(ports[0].device if len(ports)==1 else '')
            if not ports:self.detail.set('No USB serial port found. Connect RX using a data cable, then refresh.')
        except Exception as exc:messagebox.showerror('USB ports',str(exc))

    def load_model(self):
        path=filedialog.askdirectory(title='Select trusted model folder containing manifest.json and adapter.py')
        if not path:return
        try:
            bridge=ModelBridge(path)
            bridge.reset();self.bridge=bridge
            self.model_text.set(str(bridge.info['name'])[:26]+' · '+str(bridge.info['version']))
            self.detail.set('Model loaded. Its preprocessing and repetition detector run through the adapter.')
        except Exception as exc:messagebox.showerror('Model could not be loaded',str(exc))

    def choose_output(self):
        path=filedialog.askdirectory(title='Choose folder for new sessions')
        if path:self.output.set(path);self.load_history()

    def open_folder(self):
        path=Path(self.output.get())
        if path.exists():os.startfile(str(path))
        else:messagebox.showinfo('Recordings','The recordings folder is created when you start your first session.')

    def open_history(self,event):
        selected=self.history.selection()
        if selected:os.startfile(str(Path(self.output.get())/selected[0]))

    def load_history(self):
        self.history.delete(*self.history.get_children())
        for path in sorted(Path(self.output.get()).glob('*/metadata.json'),reverse=True)[:100]:
            try:
                meta=json.loads(path.read_text(encoding='utf-8'))
                model=meta.get('model') or {}
                count=sum(meta.get('counts',{}).values()) if model else '—'
                self.history.insert('', 'end',iid=path.parent.name,values=(path.parent.name,meta.get('participant',''),model.get('name','Signal only'),count))
            except (ValueError,OSError):pass

    def busy(self,active):
        for widget in self.fields+[self.refresh,self.model_button,self.folder_button,self.start_button]:
            widget.config(state='disabled' if active else ('readonly' if widget is self.fields[0] else 'normal'))
        self.stop_button.config(state='normal' if active else 'disabled')

    def start(self):
        if self.thread and self.thread.is_alive():return
        if not self.port.get():messagebox.showinfo('Select RX','Select the USB port for receiver B.');return
        if self.target.get().strip() and not MAC.fullmatch(self.target.get().strip()):messagebox.showerror('TX MAC','Use aa:bb:cc:dd:ee:ff, or leave empty.');return
        try:
            self.bridge.reset()
            session=Session(self.output.get(),dict(participant=self.participant.get(),placement=self.placement.get(),
                           serial_port=self.port.get(),model=self.bridge.info,source='esp32s3_serial',
                           timestamp_kind='device_elapsed_since_START',synchronization_note='Host labels are not RF hardware timestamps.'))
        except Exception as exc:messagebox.showerror('Cannot start',str(exc));return
        self.session_path=session.path;self.points.clear();self.counts.clear();self.events.delete(*self.events.get_children())
        self.last_packet=None;self.elapsed=0;self.duration.set('00:00');self.quality.set('Waiting for RX')
        self.action.set('—');self.confidence.set('Warming up' if self.bridge.model else 'Model not connected')
        self.repetitions.set('0' if self.bridge.model else '—')
        self.stop_event.clear();self.busy(True);self.state.set('Connecting receiver…')
        self.detail.set('Checking receiver firmware. Close other serial programs. This can take up to 12 seconds.')
        self.thread=threading.Thread(target=self.worker,args=(session,self.port.get(),self.target.get().strip()),daemon=True);self.thread.start()

    def worker(self,session,port,target):
        error=None;stream=None;counts=Counter();elapsed=0;buffer=deque();last_predict=-1e9;last_at=None;active=self.bridge.model is not None
        try:
            with open_port(port) as connection:
                stream=ReceiverStream(connection,self.stop_event,session.raw,status=lambda s:self.messages.put(('status',s)),target_mac=target)
                epoch=stream.handshake()
                if epoch is None:return
                anchor=time.monotonic();session.metadata['device_epoch_s']=epoch
                session.append(session.events,[0,'receiver_ready',port]);self.messages.put(('ready',None))
                while not self.stop_event.is_set():
                    row=stream.next_sample()
                    if row is None:continue
                    elapsed=row.source_time_s-epoch
                    sample=dict(time_s=elapsed,rssi_dbm=row.rssi_dbm)
                    session.append(session.signal,[elapsed,row.rssi_dbm,row.device_id,row.source_time_s,time.monotonic()-anchor,row.callback_seq,row.queue_drops_total,'esp32s3_serial'])
                    session.metadata['samples']+=1
                    self.messages.put(('sample',(elapsed,row.rssi_dbm,stream.stats['local_queue_drops_during_session'])))
                    if active:
                        info=self.bridge.info
                        if last_at is not None and elapsed-last_at > info['max_gap_s']:
                            buffer.clear();self.bridge.model.reset()
                            session.append(session.events,[elapsed,'model_gap_reset','Insufficient continuity; warming up again'])
                            self.messages.put(('gap',None))
                        buffer.append(sample)
                        while len(buffer)>1 and buffer[1]['time_s'] < elapsed-info['window_s']:buffer.popleft()
                        if elapsed-buffer[0]['time_s']>=info['window_s'] and elapsed-last_predict>=info['stride_s']:
                            try:
                                begin=time.perf_counter();result=self.bridge.predict(list(buffer));latency=(time.perf_counter()-begin)*1000
                                session.append(session.predictions,[elapsed,result['action'],result['confidence'],round(latency,3)])
                                for event in result['rep_events']:
                                    counts[event['action']]+=1
                                    session.append(session.reps,[event['time_s'],event['action'],event['id']])
                                self.messages.put(('prediction',(result,dict(counts))))
                                last_predict=elapsed
                            except Exception as exc:
                                active=False
                                session.metadata['model_error']=str(exc)
                                session.append(session.events,[elapsed,'model_error',str(exc)])
                                self.messages.put(('model_error',str(exc)))
                    last_at=elapsed
        except Exception as exc:
            error=f'{type(exc).__name__}: {exc}'
        finally:
            try:
                session.append(session.events,[elapsed,'session_stop',error or 'User stopped'])
                session.finish(error,dict(counts),elapsed,stream.stats if stream else {})
            except Exception as exc:error=(error or '')+' Save error: '+str(exc)
            self.messages.put(('finished',(error,str(session.path))))

    def stop(self):
        self.stop_event.set();self.stop_button.config(state='disabled');self.state.set('Saving session…')

    def close(self):
        if self.thread and self.thread.is_alive():self.closing=True;self.stop()
        else:self.root.destroy()

    def poll(self):
        redraw=False
        for _ in range(1000):
            try:kind,value=self.messages.get_nowait()
            except queue.Empty:break
            if kind=='status':self.detail.set(value)
            elif kind=='ready':
                self.state.set('Live · awaiting BLE signal');self.last_packet=time.monotonic()
                self.detail.set('Keep both boards and cables fixed. Signal is recorded automatically. '+('Model is warming up.' if self.bridge.model else 'Load a model between sessions to enable recognition and counting.'))
            elif kind=='sample':
                at,rssi,drops=value;self.elapsed=at;self.points.append((at,rssi));self.last_packet=time.monotonic();redraw=True
                self.duration.set(f'{int(at)//60:02d}:{int(at)%60:02d}');self.state.set('Live · recording')
                recent=[p for p in self.points if p[0]>=at-5]
                rate=(len(recent)-1)/(recent[-1][0]-recent[0][0]) if len(recent)>1 else 0
                self.quality.set(f'{rssi} dBm  ·  {rate:.1f} Hz  ·  queue drops {drops}')
            elif kind=='prediction':
                result,self.counts=value;self.action.set(result['action'].replace('_',' ').title())
                self.confidence.set('Confidence unavailable' if result['confidence'] is None else f"Model score {result['confidence']:.0%}")
                self.repetitions.set(str(sum(self.counts.values())))
                for event in result['rep_events']:
                    self.events.insert('','end',values=(f"{event['time_s']:.1f} s",event['action'],event['id']))
                    self.events.yview_moveto(1)
            elif kind=='gap':
                self.action.set('—');self.confidence.set('Signal gap · warming up');self.detail.set('Signal interruption. Model state reset; previous confirmed counts are preserved.')
            elif kind=='model_error':
                self.action.set('Unavailable');self.confidence.set('Model stopped');self.detail.set('Model error. Radio recording continues: '+value)
            elif kind=='finished':
                error,path=value;self.busy(False);self.last_packet=None;self.state.set('Saved with error' if error else 'Session saved')
                self.detail.set(('Connection / saving error: '+error+' | ' if error else 'Saved: ')+path)
                self.load_history()
                if self.closing:self.root.destroy();return
                if error:messagebox.showerror('Session ended',error+'\n\nFiles: '+path)
        if redraw:self.draw()
        if self.last_packet is not None and time.monotonic()-self.last_packet>2:
            self.state.set('Signal interrupted');self.action.set('—');self.confidence.set('Waiting for fresh signal')
            self.quality.set('No fresh target packets')
        self.root.after(100,self.poll)

    def draw(self):
        c=self.canvas;c.delete('all');w=max(c.winfo_width(),500);h=190;left=44;right=w-14;top=14;bottom=h-26
        end=max(30,self.points[-1][0]) if self.points else 30;start=end-30
        visible=[p for p in self.points if p[0]>=start]
        low=min(p[1] for p in visible)-3 if visible else -90;high=max(p[1] for p in visible)+3 if visible else -40
        for i in range(5):
            y=top+(bottom-top)*i/4;value=high-(high-low)*i/4
            c.create_line(left,y,right,y,fill=LINE);c.create_text(left-7,y,text=f'{value:.0f}',anchor='e',fill=MUTED,font=('Segoe UI',9))
        for i in range(7):
            x=left+(right-left)*i/6;c.create_text(x,bottom+16,text=f'{start+5*i:.0f}s',fill=MUTED,font=('Segoe UI',9))
        if len(visible)>1:
            coords=[]
            for t,rssi in visible:coords.extend([left+(t-start)/30*(right-left),bottom-(rssi-low)/(high-low)*(bottom-top)])
            c.create_line(*coords,fill=TEAL,width=1.6)
        else:c.create_text((left+right)/2,(top+bottom)/2,text='Your live wireless signal will appear here',fill=MUTED,font=('Segoe UI',11))

if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
