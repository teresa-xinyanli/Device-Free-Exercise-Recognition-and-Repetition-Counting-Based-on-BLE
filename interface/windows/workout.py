"""Manual set boundaries never create repetitions."""
from collections import Counter

class Workout:
    def __init__(self,counting=False):
        self.counting=counting;self.sets=[];self.current=None;self.seen=set()

    def begin(self,at):
        if self.current is not None:raise ValueError('Finish the current set first.')
        self.current=dict(number=len(self.sets)+1,start_s=at,end_s=None,counts={})

    def accept(self,events):
        accepted=[]
        for event in events:
            if event['id'] in self.seen:continue
            self.seen.add(event['id'])
            if not self.counting or self.current is None or event['time_s']<self.current['start_s']:continue
            counts=self.current['counts'];action=event['action'];counts[action]=counts.get(action,0)+1
            accepted.append(dict(event,set_number=self.current['number']))
        return accepted

    def end(self,at):
        if self.current is None:return None
        item=self.current;item['end_s']=max(at,item['start_s']);self.sets.append(item);self.current=None
        return item

    def snapshot(self):
        total=Counter()
        for item in self.sets+([self.current] if self.current else []):total.update(item['counts'])
        return dict(current=dict(self.current,counts=dict(self.current['counts'])) if self.current else None,
                    sets=[dict(s,counts=dict(s['counts'])) for s in self.sets],counts=dict(total),counting=self.counting)
