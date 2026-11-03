"""Three-page workout UI; uses the original drawing and widget helpers."""
import csv
import json
import math
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from app import App as OriginalApp,BASE,BG,WHITE,INK,MUTED,TEAL
from serial.tools import list_ports
from serial_receiver import MAC
from model_bridge import ModelBridge
from controller import Controller

HOME=BASE.parent.parent if BASE.parent.name.startswith('release') else BASE

class App(OriginalApp):
    def __init__(self,root):
        self.root=root;root.title('Wireless Motion | MAS.S64');root.geometry('1180x820');root.minsize(1000,730);root.configure(bg=BG)
        self.messages=queue.Queue();self.commands=queue.Queue();self.stop_event=threading.Event();self.thread=None
        self.bridge=ModelBridge();self.points=deque(maxlen=600);self.connected=False;self.connecting=False;self.recording=False;self.pending=False
        self.baseline=False;self.last_packet=None;self.closing=False;self.advanced=None;self.latest_workout=None;self.recent_metadata={};self.model_failed=False
        self.port=tk.StringVar();self.target=tk.StringVar();self.participant=tk.StringVar(value='P01');self.placement=tk.StringVar(value='A')
        self.output=tk.StringVar(value=str(HOME/'sessions'));self.state=tk.StringVar(value='Not connected')
        self.model_text=tk.StringVar(value='Model not connected · signal only');self.action=tk.StringVar(value='—')
        self.confidence=tk.StringVar(value='Model not connected · signal only');self.repetitions=tk.StringVar(value='—');self.duration=tk.StringVar(value='00:00')
        self.set_text=tk.StringVar(value='Set 1 · not started');self.motion_state=tk.StringVar(value='Connect your receiver to begin')
        self.quality=tk.StringVar(value='Waiting for signal');self.detail=tk.StringVar(value='Power TX. Connect RX to this PC with a USB data cable.')
        self.signal_value=tk.StringVar(value='—');self.signal_note=tk.StringVar(value='Waiting for receiver packets')
        self.capability=tk.StringVar();self.prediction_note=tk.StringVar(value='No model loaded. Signal recording is available after connecting RX.')
        self.usb_text=tk.StringVar();self.rx_text=tk.StringVar(value='RX firmware: not checked');self.tx_text=tk.StringVar(value='TX packets: not checked')
        self.baseline_text=tk.StringVar(value='Optional: capture 30 seconds of still RSSI. This does not apply model calibration.')
        self.summary=tk.StringVar(value='Select a saved session to review its signal capture and model predictions.')
        style=ttk.Style();style.theme_use('clam');style.configure('TEntry',padding=6);style.configure('TCombobox',padding=6)
        style.configure('Treeview',font=('Segoe UI',10),rowheight=27,background=WHITE,fieldbackground=WHITE,borderwidth=0)
        style.configure('Treeview.Heading',font=('Segoe UI',10,'bold'),background=BG,padding=6)
        self.scroll_views={};self.build();self.refresh_model_view();self.refresh_ports();self.load_history();self.update_controls()
        root.bind('<MouseWheel>',self.scroll_page)
        root.protocol('WM_DELETE_WINDOW',self.close);root.after(100,self.poll)

    def note(self,parent,var,bg=WHITE):
        text=tk.Label(parent,textvariable=var,font=('Segoe UI',10),fg=MUTED,bg=bg,justify='left',anchor='w',wraplength=700)
        text.pack(fill='x',pady=6);parent.bind('<Configure>',lambda e:text.configure(wraplength=max(180,e.width-35)),add='+')

    def card(self,parent):
        box=tk.Frame(parent,bg=WHITE,padx=18,pady=12);box.pack(fill='x',pady=(0,12));return box

    def heading(self,parent,title,subtitle):
        self.label(parent,title,size=22,bold=True,bg=BG).pack(anchor='w')
        self.label(parent,subtitle,color=MUTED,bg=BG).pack(anchor='w',pady=(5,16))

    def scroll_page(self,event):
        if event.widget.winfo_class() in ('Treeview','Scrollbar'):return
        for name,viewport in self.scroll_views.items():
            if self.pages[name].winfo_ismapped():
                viewport.yview_scroll(-int(event.delta/120),'units');return 'break'

    def build(self):
        top=tk.Frame(self.root,bg=INK);top.pack(fill='x')
        brand=tk.Frame(top,bg=INK);brand.pack(side='left',padx=24,pady=14)
        self.label(brand,'WIRELESS / MOTION',size=19,color=WHITE,bold=True,bg=INK).pack(anchor='w')
        self.label(brand,'MAS.S64 · Device-free workout sensing',color='#B5C9D6',bg=INK).pack(anchor='w')
        self.label(top,var=self.state,color='#A9E4D7',bg=INK).pack(side='right',padx=24)
        body=tk.Frame(self.root,bg=BG);body.pack(fill='both',expand=True,padx=20,pady=18)
        side=tk.Frame(body,bg=WHITE,width=195,padx=12,pady=16);side.pack(side='left',fill='y',padx=(0,18));side.pack_propagate(False)
        self.label(side,'YOUR WORKOUT',size=9,color=MUTED,bold=True).pack(anchor='w',pady=(0,16));self.nav={}
        for name,title in [('prepare','01  Connect & prepare'),('live','02  Live workout'),('records','03  Session records')]:
            self.nav[name]=self.button(side,title,lambda n=name:self.show_page(n));self.nav[name].pack(fill='x',pady=4)
        self.settings_button=self.button(side,'Advanced settings',self.settings);self.settings_button.pack(side='bottom',fill='x',pady=8)
        self.label(side,'TX → BLE → RX → USB\nNo wearable required.',size=9,color=MUTED).pack(side='bottom',anchor='w',pady=12)
        main=tk.Frame(body,bg=BG);main.pack(side='left',fill='both',expand=True)
        self.pages={name:tk.Frame(main,bg=BG) for name in ('prepare','live','records')}
        self.build_prepare();self.build_live();self.build_records();self.show_page('prepare')

    def build_prepare(self):
        host=self.pages['prepare']
        viewport=tk.Canvas(host,bg=BG,highlightthickness=0)
        self.scroll_views['prepare']=viewport
        scroll=ttk.Scrollbar(host,orient='vertical',command=viewport.yview)
        viewport.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');viewport.pack(fill='both',expand=True)
        p=tk.Frame(viewport,bg=BG);window=viewport.create_window((0,0),window=p,anchor='nw')
        p.bind('<Configure>',lambda e:viewport.configure(scrollregion=viewport.bbox('all')))
        viewport.bind('<Configure>',lambda e:viewport.itemconfigure(window,width=e.width))
        self.heading(p,'A little setup. Then just move.','Connect the receiver, check the radio signal, and start a workout.')
        box=self.card(p);self.label(box,'01  Power & connect',bold=True).pack(anchor='w')
        self.label(box,'Power TX. Connect RX to this PC using a USB data cable.',color=MUTED).pack(anchor='w',pady=6)
        for var in (self.usb_text,self.rx_text,self.tx_text):self.label(box,var=var).pack(anchor='w',pady=2)
        row=tk.Frame(box,bg=WHITE);row.pack(fill='x',pady=(10,0))
        self.connect_button=self.button(row,'Connect device',self.connect,True);self.connect_button.pack(side='left')
        self.refresh_button=self.button(row,'Refresh ports',self.refresh_ports);self.refresh_button.pack(side='left',padx=8)
        self.disconnect_button=self.button(row,'Disconnect',self.disconnect);self.disconnect_button.pack(side='right')
        box=self.card(p);self.label(box,'02  Session details',bold=True).pack(anchor='w')
        row=tk.Frame(box,bg=WHITE);row.pack(fill='x',pady=8);self.info_fields=[]
        for title,var in [('Participant',self.participant),('Placement',self.placement)]:
            group=tk.Frame(row,bg=WHITE);group.pack(side='left',fill='x',expand=True,padx=(0,14))
            self.label(group,title,color=MUTED).pack(anchor='w');entry=ttk.Entry(group,textvariable=var);entry.pack(fill='x',pady=4);self.info_fields.append(entry)
        self.note(box,self.model_text)
        box=self.card(p);self.label(box,'03  Optional still baseline',bold=True).pack(anchor='w');self.note(box,self.baseline_text)
        self.baseline_button=self.button(box,'Record 30-second baseline',lambda:self.start('baseline'));self.baseline_button.pack(anchor='w')
        self.prepare_start=self.button(p,'Start workout →',self.start,True);self.prepare_start.pack(anchor='w',pady=4)
        self.note(p,self.detail,BG)

    def build_live(self):
        host=self.pages['live'];viewport=tk.Canvas(host,bg=BG,highlightthickness=0)
        self.scroll_views['live']=viewport
        scroll=ttk.Scrollbar(host,orient='vertical',command=viewport.yview)
        viewport.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');viewport.pack(fill='both',expand=True)
        p=tk.Frame(viewport,bg=BG);window=viewport.create_window((0,0),window=p,anchor='nw')
        p.bind('<Configure>',lambda e:viewport.configure(scrollregion=viewport.bbox('all')))
        viewport.bind('<Configure>',lambda e:viewport.itemconfigure(window,width=e.width))
        self.heading(p,'Signal & activity.','Watch the radio signal. Activity labels appear when a model is connected.')
        self.note(p,self.capability,BG)
        cards=tk.Frame(p,bg=BG);cards.pack(fill='x')
        self.metric_cards=[]
        for i,(title,var,sub) in enumerate([('CURRENT ACTIVITY',self.action,self.confidence),('RSSI · dBm',self.signal_value,self.signal_note),('SESSION TIME',self.duration,self.motion_state),('REPETITIONS IN SET',self.repetitions,self.set_text)]):
            box=tk.Frame(cards,bg=WHITE,padx=14,pady=12);box.grid(row=0,column=i,sticky='nsew',padx=(0,10 if i<2 else 0));cards.columnconfigure(i,weight=1,uniform='cards')
            self.metric_cards.append(box)
            self.label(box,title,size=9,color=MUTED,bold=True).pack(anchor='w');self.label(box,var=var,size=24,bold=True,color=TEAL if i==1 else INK).pack(anchor='w',pady=6)
            label=self.label(box,var=sub,size=9,color=MUTED);label.configure(wraplength=210,justify='left');label.pack(anchor='w')
            box.bind('<Configure>',lambda e,l=label:l.configure(wraplength=max(100,e.width-30)))
        row=tk.Frame(p,bg=BG);row.pack(fill='x',pady=12)
        self.end_set_button=self.button(row,'Finish set',lambda:self.send('end_set'));self.end_set_button.pack(side='left')
        self.next_set_button=self.button(row,'Start next set',lambda:self.send('next_set'),True);self.next_set_button.pack(side='left',padx=8)
        self.stop_button=self.button(row,'End & save session',self.stop);self.stop_button.pack(side='right')
        box=self.card(p);head=tk.Frame(box,bg=WHITE);head.pack(fill='x')
        self.label(head,'LIVE RSSI',bold=True).pack(side='left');self.label(head,var=self.quality,size=9,color=TEAL).pack(side='right')
        self.canvas=tk.Canvas(box,bg=WHITE,height=190,highlightthickness=0);self.canvas.pack(fill='x',pady=6);self.canvas.bind('<Configure>',lambda e:self.draw())
        self.label(box,'Raw radio signal · last 30 seconds · dBm · adaptive scale',size=9,color=MUTED).pack(anchor='w')
        self.note(p,self.detail,BG)
        self.result_tabs=ttk.Notebook(p);self.result_tabs.pack(fill='both',expand=True)
        self.prediction_panel=tk.Frame(self.result_tabs,bg=WHITE);self.result_tabs.add(self.prediction_panel,text='Activity predictions')
        self.note(self.prediction_panel,self.prediction_note)
        self.predictions=self.tree(self.prediction_panel,('time','activity','score'),('Time','Predicted activity','Model score'))
        self.predictions.configure(height=4)
        self.rep_panel=tk.Frame(self.result_tabs,bg=WHITE)
        self.events=self.tree(self.rep_panel,('time','set','activity','event'),('Time','Set','Activity','Event ID'))
        self.events.configure(displaycolumns=('time','set','activity'),height=4)

    def refresh_model_view(self):
        counting=bool(self.bridge.model and self.bridge.info.get('supports_counting',False) and not self.model_failed)
        self.metric_cards[3].grid() if counting else self.metric_cards[3].grid_remove()
        self.metric_cards[3].master.columnconfigure(3,weight=1 if counting else 0,uniform='cards' if counting else '')
        visible=str(self.rep_panel) in self.result_tabs.tabs()
        if counting:self.result_tabs.add(self.rep_panel,text='Confirmed repetitions')
        elif not counting and visible:self.result_tabs.hide(self.rep_panel)
        if self.model_failed:
            self.capability.set('Signal recording · model stopped');self.prediction_note.set('Model error. Earlier predictions are partial; raw signal recording continues.')
        elif not self.bridge.model:
            self.capability.set('Signal-only mode · no model loaded');self.prediction_note.set('No model loaded. Activity predictions will appear after a classifier is connected.')
        else:
            self.capability.set('Activity classification'+(' + repetition events' if counting else ' · classification only'))
            self.prediction_note.set('Predicted labels and model scores; these are not manual reference labels.')

    def build_records(self):
        p=self.pages['records'];self.heading(p,'Your sessions, in one place.','Review saved predictions, manual set boundaries and recording status.')
        box=self.card(p);self.note(box,self.summary)
        row=tk.Frame(box,bg=WHITE);row.pack(fill='x',pady=4)
        self.button(row,'Open selected folder',self.open_history).pack(side='left');self.button(row,'Open recordings',self.open_folder).pack(side='right')
        tabs=ttk.Notebook(p);tabs.pack(fill='both',expand=True)
        frame=tk.Frame(tabs,bg=WHITE);tabs.add(frame,text='Activity predictions')
        self.history_note=tk.StringVar(value='No session selected.');self.note(frame,self.history_note)
        self.prediction_history=self.tree(frame,('time','activity','score'),('Time','Predicted activity','Model score'))
        frame=tk.Frame(tabs,bg=WHITE);tabs.add(frame,text='Manual sets')
        self.set_history=self.tree(frame,('set','activity','count','span'),('Set','Activity','Repetitions','Time range'))
        self.set_history.configure(displaycolumns=('set','span'))
        self.label(p,'Saved sessions',bold=True,bg=BG).pack(anchor='w',pady=(12,6))
        frame=tk.Frame(p,bg=WHITE);frame.pack(fill='both',expand=True)
        self.history=self.tree(frame,('session','participant','mode','status'),('Session','Participant','Type','Status'))
        self.history.bind('<<TreeviewSelect>>',self.select_history);self.history.bind('<Double-1>',self.open_history)

    def show_page(self,name):
        for key,page in self.pages.items():
            page.pack_forget();self.nav[key].configure(bg='#E2F0F1' if key==name else WHITE,fg=TEAL if key==name else INK)
        self.pages[name].pack(fill='both',expand=True)
        if name=='live':self.root.after_idle(self.draw)

    def refresh_ports(self):
        try:
            self.available_ports=[p.device for p in list_ports.comports()]
            if self.port.get() not in self.available_ports:self.port.set(self.available_ports[0] if len(self.available_ports)==1 else '')
            self.usb_text.set(f'USB serial: {len(self.available_ports)} port(s) found' if self.available_ports else 'USB serial: no ports found — check RX cable')
        except Exception as exc:self.detail.set('USB scan error: '+str(exc))

    def settings(self):
        if self.thread and self.thread.is_alive():return
        if self.advanced and self.advanced.winfo_exists():self.advanced.lift();return
        dialog=tk.Toplevel(self.root);self.advanced=dialog;dialog.title('Advanced settings');dialog.geometry('620x460');dialog.transient(self.root)
        frame=tk.Frame(dialog,bg=WHITE,padx=24,pady=20);frame.pack(fill='both',expand=True)
        self.label(frame,'Device & model settings',size=16,bold=True).pack(anchor='w')
        self.label(frame,'Receiver USB port',color=MUTED).pack(anchor='w',pady=(14,4));ttk.Combobox(frame,textvariable=self.port,values=self.available_ports,state='readonly').pack(fill='x')
        self.label(frame,'TX MAC · optional',color=MUTED).pack(anchor='w',pady=(10,4));ttk.Entry(frame,textvariable=self.target).pack(fill='x')
        self.note(frame,self.model_text);row=tk.Frame(frame,bg=WHITE);row.pack(fill='x')
        self.button(row,'Choose model folder',self.load_model).pack(side='left');self.button(row,'Unload model',self.unload_model).pack(side='left',padx=6)
        self.button(frame,'Choose recording folder',self.choose_output).pack(anchor='w',pady=8);self.note(frame,self.output)
        self.button(frame,'Done',dialog.destroy,True).pack(anchor='e')

    def load_model(self):
        path=filedialog.askdirectory(title='Choose trusted model folder',parent=self.advanced)
        if not path:return
        try:
            bridge=ModelBridge(path);bridge.reset();self.bridge=bridge
            mode='recognition + counting' if bridge.info.get('supports_counting',False) else 'classification only'
            self.model_text.set(str(bridge.info['name'])+' · '+str(bridge.info['version'])+' · '+mode)
            self.model_failed=False;self.action.set('—');self.confidence.set('Ready · start a session to classify');self.refresh_model_view()
        except Exception as exc:messagebox.showerror('Cannot load model',str(exc),parent=self.advanced)

    def unload_model(self):
        self.bridge=ModelBridge();self.model_text.set('Model not connected · signal only');self.action.set('—');self.confidence.set('Model not connected · signal only')
        self.model_failed=False;self.refresh_model_view()

    def choose_output(self):
        path=filedialog.askdirectory(title='Choose recording folder',parent=self.advanced)
        if path:self.output.set(path);self.load_history()

    def open_history(self,event=None):
        selected=self.history.selection()
        if selected:os.startfile(str(Path(self.output.get())/selected[0]))

    @staticmethod
    def record_status(meta):
        if not meta.get('finished_at'):return 'Incomplete / still recording'
        if meta.get('error'):return 'Saved with recording error'
        if meta.get('model_error'):return 'Model failed · partial results'
        if meta.get('session_type')=='baseline':return 'Baseline captured' if meta.get('baseline_complete') else 'Baseline incomplete / insufficient samples'
        return 'Model output · unvalidated' if meta.get('model') else 'Signal only'

    def select_history(self,event=None):
        selected=self.history.selection()
        if not selected:return
        meta=self.recent_metadata.get(selected[0],{});self.set_history.delete(*self.set_history.get_children())
        self.prediction_history.delete(*self.prediction_history.get_children())
        try:
            rows=self.read_prediction_rows(Path(self.output.get())/selected[0]/'predictions.csv')
            for row in rows:self.prediction_history.insert('','end',values=row)
            self.history_note.set('Latest '+str(len(rows))+' saved predictions · model outputs, not reference labels.' if rows else 'No saved activity predictions in this session.')
        except (OSError,csv.Error) as exc:self.history_note.set('Cannot read predictions: '+str(exc))
        show_counts=bool(meta.get('counting_available') or meta.get('counts'))
        self.set_history.configure(displaycolumns=('set','activity','count','span') if show_counts else ('set','span'))
        totals=', '.join(f'{k}: {v}' for k,v in meta.get('counts',{}).items()) or 'No confirmed repetitions'
        if not meta.get('counting_available'):totals='Earlier counts are partial' if meta.get('counts') else ('Activity classification only' if meta.get('model') else 'Raw signal capture · no model predictions')
        if meta.get('session_type')=='baseline':totals='Still baseline only · no calibration algorithm applied'
        self.summary.set(f"{meta.get('participant','')} · Placement {meta.get('placement','')} · {meta.get('duration_s',0):.1f}s\n{self.record_status(meta)}\n{totals}"+ ('\n'+str(meta['error']) if meta.get('error') else ''))
        for item in meta.get('sets',[]):
            counts=item['counts'] or {'—':None if not meta.get('counting_available') else 0}
            for action,count in counts.items():self.set_history.insert('','end',values=(item['number'],action,'—' if count is None else count,f"{item['start_s']:.1f}–{item['end_s']:.1f}s"))

    @staticmethod
    def prediction_values(at,action,confidence):
        score='—' if confidence is None else f'{confidence:.0%}'
        return (f'{at:.2f}s',action.replace('_',' ').title(),score)

    @classmethod
    def read_prediction_rows(cls,path):
        if not path.exists():return []
        rows=deque(maxlen=1000)
        with path.open(encoding='utf-8-sig',newline='') as file:
            for row in csv.DictReader(file):
                try:
                    at=float(row['time_s']);score=float(row['confidence']) if row.get('confidence') else None
                    if not math.isfinite(at) or (score is not None and (not math.isfinite(score) or not 0<=score<=1)):continue
                    rows.append(cls.prediction_values(at,row['action'],score))
                except (KeyError,ValueError,TypeError):continue
        return list(rows)

    def load_history(self,select=None):
        self.history.delete(*self.history.get_children());self.recent_metadata={}
        for path in sorted(Path(self.output.get()).glob('*/metadata.json'),reverse=True)[:100]:
            try:
                meta=json.loads(path.read_text(encoding='utf-8'));self.recent_metadata[path.parent.name]=meta
                self.history.insert('','end',iid=path.parent.name,values=(path.parent.name,meta.get('participant',''),meta.get('session_type','workout'),self.record_status(meta)))
            except (OSError,ValueError):pass
        if select and self.history.exists(select):self.history.selection_set(select);self.select_history()

    def update_controls(self):
        running=self.connecting or self.connected
        for widget in (self.connect_button,self.refresh_button,self.settings_button):widget.configure(state='disabled' if running else 'normal')
        self.disconnect_button.configure(state='normal' if running and not self.recording else 'disabled')
        fresh=self.last_packet is not None and time.monotonic()-self.last_packet<2
        ready=self.connected and fresh and not self.recording and not self.pending
        for widget in (self.prepare_start,self.baseline_button):widget.configure(state='normal' if ready else 'disabled')
        self.stop_button.configure(state='normal' if self.recording and not self.pending else 'disabled')
        for field in self.info_fields:field.configure(state='disabled' if self.recording or self.pending else 'normal')
        current=(self.latest_workout or {}).get('current')
        self.end_set_button.configure(state='normal' if self.recording and not self.baseline and current and not self.pending else 'disabled')
        self.next_set_button.configure(state='normal' if self.recording and not self.baseline and not current and fresh and not self.pending else 'disabled')

    def connect(self):
        if self.thread and self.thread.is_alive():return
        self.refresh_ports()
        if not self.port.get():messagebox.showinfo('Choose receiver','Check RX data cable. If multiple USB ports exist, choose RX in Advanced settings.');return
        if self.target.get().strip() and not MAC.fullmatch(self.target.get().strip()):messagebox.showerror('TX MAC','Use aa:bb:cc:dd:ee:ff, or leave empty.');return
        if self.advanced and self.advanced.winfo_exists():self.advanced.destroy()
        self.commands=queue.Queue();self.stop_event.clear();self.connecting=True;self.last_packet=None;self.points.clear()
        self.rx_text.set('RX firmware: checking…');self.tx_text.set('TX packets: waiting');self.state.set('Connecting…')
        self.detail.set('Checking RX firmware. Close other serial programs. Allow up to 12 seconds.');self.update_controls()
        controller=Controller(self.bridge,self.messages,self.commands,self.stop_event)
        self.thread=threading.Thread(target=controller.run,args=(self.port.get(),self.target.get().strip()),daemon=True);self.thread.start()

    def start(self,kind='workout'):
        if not self.connected or self.recording or self.pending:return
        self.pending=True;self.commands.put(('start',dict(session_type=kind,participant=self.participant.get(),placement=self.placement.get(),output=self.output.get())));self.update_controls()

    def send(self,command):
        if not self.recording or self.pending:return
        self.pending=True;self.commands.put((command,None));self.update_controls()

    def stop(self):
        if self.recording:self.send('finish')

    def disconnect(self):self.stop_event.set();self.state.set('Disconnecting…')

    def close(self):
        if self.thread and self.thread.is_alive():self.closing=True;self.stop_event.set();self.state.set('Saving & closing…')
        else:self.root.destroy()

    def render_workout(self,snapshot):
        self.latest_workout=snapshot;current=snapshot['current']
        if current:
            self.set_text.set(f"Set {current['number']} · active");self.repetitions.set(str(sum(current['counts'].values())) if snapshot['counting'] else '—')
        else:self.set_text.set(f"{len(snapshot['sets'])} set(s) completed · resting");self.repetitions.set('—');self.motion_state.set('Rest · start next set when ready')

    def poll(self):
        redraw=False
        for _ in range(1000):
            try:kind,value=self.messages.get_nowait()
            except queue.Empty:break
            if kind=='status':self.detail.set(value)
            elif kind=='ready':
                self.connecting=False;self.connected=True;self.state.set('Connected · waiting for TX');self.rx_text.set('RX firmware: verified · protocol 2')
                self.detail.set('RX verified. Connection preview is not saved. Start a workout to record.')
            elif kind=='sample':
                at,rssi,drops=value;self.points.append((at,rssi));self.last_packet=time.monotonic();redraw=True
                recent=[p for p in self.points if p[0]>=at-5];rate=(len(recent)-1)/(recent[-1][0]-recent[0][0]) if len(recent)>1 else 0
                self.quality.set(f'{rssi} dBm · {rate:.1f} Hz · drops {drops}');self.tx_text.set(f'TX packets: receiving · {rate:.1f} Hz (not proof of recognition quality)')
                self.signal_value.set(str(rssi));self.signal_note.set(f'{rate:.1f} packets/s · {drops} queue drops')
                self.state.set('Recording baseline' if self.baseline and self.recording else ('Live · recording' if self.recording else 'Connected · preview only'))
            elif kind=='elapsed':self.duration.set(f'{int(value)//60:02d}:{int(value)%60:02d}')
            elif kind=='started':
                path,self.baseline,snapshot=value;self.recording=True;self.pending=False;self.session_path=Path(path);self.duration.set('00:00');self.events.delete(*self.events.get_children())
                self.action.set('—');self.render_workout(snapshot);self.confidence.set('Model warming up' if self.bridge.model and not self.baseline else 'Model not connected · signal only')
                self.predictions.delete(*self.predictions.get_children());self.model_failed=False;self.refresh_model_view()
                self.motion_state.set('Still baseline recording' if self.baseline else ('Recognizing…' if self.bridge.model else 'Signal recording only'))
                self.detail.set('Stand still for 30 seconds. Baseline capture does not apply calibration.' if self.baseline else 'Finish set marks a manual boundary. End & save session saves the full recording.')
                if not self.baseline:self.show_page('live')
            elif kind=='baseline_tick':self.baseline_text.set(f'Recording still baseline · {value}s remaining. No calibration algorithm is applied.')
            elif kind=='workout':
                self.pending=False;self.render_workout(value);self.action.set('—');self.confidence.set('Warming up' if value['current'] and self.bridge.model else 'Rest / no model prediction')
                if value['current']:self.motion_state.set('Recognizing…' if self.bridge.model else 'Signal recording only')
            elif kind=='prediction':
                result,accepted,snapshot=value;self.render_workout(snapshot)
                # Predictions are also saved during manual rest; set boundaries are not activity labels.
                self.predictions.insert('','end',values=self.prediction_values(result['time_s'],result['action'],result['confidence']))
                children=self.predictions.get_children()
                if len(children)>200:self.predictions.delete(children[0])
                self.predictions.yview_moveto(1)
                if snapshot['current']:
                    name=result['action'];self.action.set('Unknown' if name=='unknown' else name.replace('_',' ').title())
                    self.confidence.set('Model score unavailable' if result['confidence'] is None else f"Model score {result['confidence']:.0%}")
                    self.motion_state.set('Unable to classify' if name=='unknown' else ('Still / resting' if name in ('idle','other') else 'Recognizing movement'))
                for event in accepted:self.events.insert('','end',values=(f"{event['time_s']:.1f}s",event['set_number'],event['action'],event['id']));self.events.yview_moveto(1)
            elif kind=='gap':self.action.set('—');self.confidence.set('Signal gap · warming up');self.motion_state.set('Waiting for fresh model input')
            elif kind=='model_error':
                self.action.set('Unavailable');self.repetitions.set('—');self.confidence.set('Model failed · results partial');self.motion_state.set('Signal recording only');self.detail.set('Model error; raw recording continues: '+value)
                self.model_failed=True;self.refresh_model_view()
            elif kind=='command_error':self.pending=False;messagebox.showerror('Cannot start recording',value)
            elif kind=='saved':
                error,path=value;self.recording=False;self.pending=False;self.baseline=False;self.latest_workout=None;self.motion_state.set('Session saved')
                self.detail.set('Saved: '+path);self.baseline_text.set('Baseline captures are separate from calibration. Review capture status in Session records.')
                self.action.set('—');self.confidence.set('Session ended · no live prediction')
                self.load_history(Path(path).name);self.show_page('records')
            elif kind=='disconnected':
                self.connected=False;self.connecting=False;self.pending=False;self.recording=False;self.baseline=False;self.last_packet=None;self.state.set('Disconnected');self.rx_text.set('RX firmware: disconnected');self.tx_text.set('TX packets: not checked')
                self.action.set('—');self.confidence.set('Disconnected');self.quality.set('No fresh signal')
                self.signal_value.set('—');self.signal_note.set('Receiver disconnected')
                if self.closing:self.root.destroy();return
                if value:self.detail.set('Connection / save error: '+value);messagebox.showerror('Receiver connection',value)
        if redraw:self.draw()
        if self.connected and self.last_packet is not None and time.monotonic()-self.last_packet>2:
            self.state.set('Signal interrupted');self.action.set('—');self.confidence.set('Waiting for fresh signal');self.quality.set('No fresh target packets');self.tx_text.set('TX packets: interrupted — check TX power');self.motion_state.set('Signal interrupted')
            self.signal_value.set('—');self.signal_note.set('No fresh packets')
        self.update_controls();self.root.after(100,self.poll)

if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
