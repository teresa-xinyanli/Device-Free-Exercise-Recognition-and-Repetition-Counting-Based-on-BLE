"""Append-only observations; predictions are stored separately from radio samples."""
import csv
import json
from datetime import datetime
from pathlib import Path

class Session:
    def __init__(self, base, metadata):
        self.path = Path(base) / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        self.path.mkdir(parents=True, exist_ok=False)
        self.metadata = dict(metadata, started_at=datetime.now().astimezone().isoformat(), samples=0)
        self.files = []
        self.signal = self.table('signal.csv', ['time_s','rssi_dbm','device_id','source_time_s','host_time_s','callback_seq','queue_drops_total','source'])
        self.predictions = self.table('predictions.csv', ['time_s','action','confidence','inference_ms'])
        self.reps = self.table('repetitions.csv', ['time_s','action','id','set_number'])
        self.sets = self.table('sets.csv', ['set_number','start_s','end_s','action','repetitions','count_status'])
        self.events = self.table('events.csv', ['time_s','event','detail'])
        self.raw = (self.path/'raw_serial.txt').open('wb')
        self.write_meta()

    def table(self, name, fields):
        file = (self.path/name).open('w',newline='',encoding='utf-8')
        writer = csv.writer(file)
        writer.writerow(fields)
        file.flush()
        self.files.append(file)
        return writer,file

    @staticmethod
    def append(table, row):
        writer,file = table
        writer.writerow(row)
        file.flush()

    def write_meta(self):
        (self.path/'metadata.json').write_text(json.dumps(self.metadata,ensure_ascii=False,indent=2),encoding='utf-8')

    def finish(self, error, counts, duration, diagnostics):
        self.metadata.update(error=error, counts=counts, duration_s=duration, receiver_diagnostics=diagnostics,
                             finished_at=datetime.now().astimezone().isoformat())
        try:
            self.write_meta()
        finally:
            self.raw.close()
            for file in self.files:
                file.close()
